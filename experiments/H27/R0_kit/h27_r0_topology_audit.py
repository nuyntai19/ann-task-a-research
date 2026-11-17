#!/usr/bin/env python3
"""H27-R0 read-only exact directed edge-set comparison of PiPNN Graph<uint32_t> files.
Format grounded in ParAlg/PiPNN algorithms/utils/graph.h, commit 443a328dc71a3b7be753d52ca2b3c9a4ba77f3fd:
uint32 n, uint32 max_degree, uint32 degrees[n], uint32 neighbors[sum(degrees)].
No graph mutations; outputs diagnostics, not novelty or causal identification.
"""
import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile

try:
    import numpy as np
except ImportError as e:
    raise SystemExit('H27R0_BLOCKED: numpy missing in active Python environment') from e

LABELS = ('r1_stock', 'r1_top2', 'r2_stock', 'r2_top2')
PAIRS = [('r1_stock','r1_top2'),('r2_stock','r2_top2'),('r1_stock','r2_stock'),('r1_top2','r2_top2')]
SCHEMA = 'PiPNN Graph<uint32_t> v1 (2 uint32 header + n degrees + concatenated uint32 neighbor IDs)'


def sha256(p):
    h=hashlib.sha256()
    with open(p,'rb') as f:
        while True:
            b=f.read(4*1024*1024)
            if not b:break
            h.update(b)
    return h.hexdigest()

class Graph:
    def __init__(self, path, expected_n=None):
        self.path=Path(path).resolve()
        if not self.path.is_file():raise ValueError(f'Graph file missing: {self.path}')
        if self.path.stat().st_size % 4 != 0:raise ValueError(f'File size not multiple of uint32: {self.path}')
        if self.path.stat().st_size < 12:raise ValueError('Graph file too small')
        self.mm=np.memmap(self.path,dtype='<u4',mode='r')
        self.n=int(self.mm[0]);self.max_degree=int(self.mm[1])
        if not (2 <= self.n <= 2_000_000_000):raise ValueError('Bad n')
        if expected_n is not None and self.n != expected_n:raise ValueError(f'Expected n={expected_n} but found {self.n}')
        if not (1 <= self.max_degree <= 4096):raise ValueError('Implausible max_degree')
        if self.mm.size < 2+self.n:raise ValueError('Truncated degree array')
        self.degree=self.mm[2:2+self.n]
        if np.any(self.degree > self.max_degree):raise ValueError('Node degree exceeds file max_degree')
        self.offset=np.empty(self.n+1,dtype=np.int64)
        self.offset[0]=0
        np.cumsum(self.degree.astype(np.int64),out=self.offset[1:])
        self.edge_count=int(self.offset[-1])
        want=2+self.n+self.edge_count
        if len(self.mm) != want:raise ValueError(f'Invalid file size: got {len(self.mm)} u32, expected {want}')
        self.edges=self.mm[2+self.n:]
        if self.edges.size and int(np.max(self.edges)) >= self.n:raise ValueError('Invalid neighbor ID >=n')

    def keys(self,lo,hi):
        counts=self.degree[lo:hi]
        src=np.repeat(np.arange(lo,hi,dtype=np.uint64),counts.astype(np.int64))
        dst=self.edges[int(self.offset[lo]):int(self.offset[hi])].astype(np.uint64)
        k=(src<<np.uint64(32)) | dst
        return np.unique(k)

    def summarize(self, batch=8192, bfs=False):
        indegree=np.zeros(self.n,dtype=np.int64)
        self_edges=0;dup_entries=0;unique_count=0
        for lo in range(0,self.n,batch):
            hi=min(self.n,lo+batch)
            dst=self.edges[int(self.offset[lo]):int(self.offset[hi])]
            if dst.size:indegree += np.bincount(dst.astype(np.int64),minlength=self.n)
            uniques=self.keys(lo,hi)
            unique_count+=len(uniques)
            dup_entries+=len(dst)-len(uniques)
            self_edges+=int(np.count_nonzero((uniques>>np.uint64(32))==(uniques&np.uint64(0xffffffff))))
        result={
            'path':str(self.path),'sha256':sha256(self.path),'n':self.n,
            'max_degree':self.max_degree,'edge_occurrences':self.edge_count,
            'unique_directed_edge_keys':unique_count,'duplicate_edge_occurrences':dup_entries,
            'degree_zero':int(np.count_nonzero(self.degree==0)),
            'indegree_zero':int(np.count_nonzero(indegree==0)),
            'indegree_p50':float(np.median(indegree)),'indegree_p99':float(np.percentile(indegree,99)),
            'self_edge_unique_keys':self_edges,
            'mean_outdegree':float(self.edge_count/self.n)
        }
        if bfs:
            from collections import deque
            seen=bytearray(self.n)
            seen[0]=1;q=deque([0]);visited=1
            while q:
                u=q.popleft()
                for v in self.edges[int(self.offset[u]):int(self.offset[u+1])]:
                    v=int(v)
                    if not seen[v]:seen[v]=1;visited+=1;q.append(v)
            result['reachable_from_entry0']=visited
        return result


def compare(a,b,batch=8192):
    if a.n!=b.n:raise ValueError('Cannot compare graphs with different n')
    inter=0;union=0;add=0;remove=0;changed=0;ch_degree=0
    for lo in range(0,a.n,batch):
        hi=min(a.n,lo+batch)
        x=a.keys(lo,hi);y=b.keys(lo,hi)
        # Sorted unique key arrays; each src ID occurs in exactly one batch.
        both=np.intersect1d(x,y,assume_unique=True)
        count_both=int(both.size)
        inter+=count_both;union+=len(x)+len(y)-count_both
        x_only=np.setdiff1d(x,y,assume_unique=True)
        y_only=np.setdiff1d(y,x,assume_unique=True)
        remove+=len(x_only);add+=len(y_only)
        if x_only.size or y_only.size:
            sources=np.concatenate((x_only>>np.uint64(32),y_only>>np.uint64(32)))
            changed+=int(np.unique(sources).size)
        ch_degree+=int(np.count_nonzero(a.degree[lo:hi]!=b.degree[lo:hi]))
    return {'graph_a':a.path.name,'graph_b':b.path.name,
            'common_directed_keys':inter,'union_directed_keys':union,
            'jaccard':(inter/union if union else 1.0),
            'removed_keys_a_to_b':remove,'added_keys_a_to_b':add,
            'symmetric_difference_keys':add+remove,
            'symmetric_difference_fraction_of_union':((add+remove)/union if union else 0),
            'changed_neighbor_set_rows':changed,
            'changed_neighbor_set_row_fraction':changed/a.n,
            'changed_outdegree_rows':ch_degree}


def discover(root):
    root=Path(root).expanduser().resolve()
    if not root.is_dir():raise ValueError(f'Directory not found: {root}')
    candidates={x:[] for x in LABELS}
    for p in root.rglob('*'):
        if not p.is_file() or p.suffix.lower() not in ('.graph','.bin'):continue
        # Force label to be part of filename, not ancestor directory.
        name=p.stem.lower()
        hits=[x for x in LABELS if x in name]
        if len(hits)==1:candidates[hits[0]].append(p)
    return candidates


def choose_candidates(candidates):
    missing=[k for k,v in candidates.items() if len(v)!=1]
    if missing:
        for k,v in candidates.items():print(f'{k}: {len(v)} candidate(s): '+', '.join(str(x) for x in v),file=sys.stderr)
        raise ValueError('Expected EXACTLY one .graph or .bin for each label; use --graph label=path explicitly')
    return {k:v[0] for k,v in candidates.items()}


def parse_explicit(items):
    out={}
    for it in items:
        if '=' not in it:raise ValueError('--graph expects label=/absolute/path.graph')
        k,path=it.split('=',1)
        if k not in LABELS or k in out:raise ValueError('Duplicate or unknown graph label: '+k)
        out[k]=Path(path).expanduser()
    if set(out)!=set(LABELS):raise ValueError('Specify all four labels: '+', '.join(LABELS))
    return out


def selftest():
    with tempfile.TemporaryDirectory() as t:
        def write(name,rows):
            deg=[len(x) for x in rows]
            arr=np.array([len(rows),max(deg)]+deg+[z for row in rows for z in row],dtype='<u4')
            f=Path(t)/name;arr.tofile(f);return f
        a=Graph(write('r1_stock.graph',[[1,2],[2],[3],[4],[5],[]]),expected_n=6)
        b=Graph(write('r1_top2.graph',[[1,3],[2],[3],[4],[5],[]]),expected_n=6)
        c=Graph(write('r2_stock.graph',[[2,1],[2],[3],[4],[5],[]]),expected_n=6)
        o=compare(a,b,batch=2);order=compare(a,c,batch=2)
        assert o['changed_neighbor_set_rows']==1,o
        assert o['removed_keys_a_to_b']==1 and o['added_keys_a_to_b']==1,o
        assert o['common_directed_keys']==5 and o['union_directed_keys']==7,o
        assert order['changed_neighbor_set_rows']==0,order
        qa=a.summarize(batch=2,bfs=True)
        assert qa['reachable_from_entry0']==6,qa
        assert qa['unique_directed_edge_keys']==6,qa
        invalid=write('bad.graph',[[1],[8]])
        try:Graph(invalid,expected_n=2)
        except ValueError:pass
        else:raise AssertionError('Invalid ID accepted')
    print('H27R0_GRAPH_SCHEMA_AND_EXACT_EDGE_SET_SELFTEST_PASS')


def main():
    ap=argparse.ArgumentParser(description='H27-R0 PiPNN graph stability diagnostic; read-only.')
    ap.add_argument('--mode',choices=['selftest','discover','run'],default='discover')
    ap.add_argument('--root',default='~/ann-task-a/experiments/H26/H26_profile_20261026_222107_gcgcqF')
    ap.add_argument('--graph',action='append',default=[],help='Override discovery: label=/path/to/file.graph (4 labels)')
    ap.add_argument('--out',default=None)
    ap.add_argument('--expected-n',type=int,default=1_000_000)
    ap.add_argument('--batch',type=int,default=8192)
    ap.add_argument('--bfs',action='store_true',help='Also perform directed entry0 BFS on each graph')
    args=ap.parse_args()
    try:
        if args.mode=='selftest':selftest();return
        if args.batch<=0:raise ValueError('batch must be positive')
        paths=parse_explicit(args.graph) if args.graph else choose_candidates(discover(args.root)) if args.mode=='run' else None
        if args.mode=='discover':
            for k,v in discover(args.root).items():
                print(f'{k}: {len(v)} candidate(s)')
                for f in v:print(f'  {f} ({f.stat().st_size:,} bytes)')
            print('H27R0_DISCOVER_DONE')
            return
        graphs={k:Graph(p,args.expected_n) for k,p in paths.items()}
        ans={'study':'H27_R0_EXACT_DIRECTED_EDGE_SET_STABILITY_AUDIT',
             'date_utc':dt.datetime.now(dt.timezone.utc).isoformat(),
             'schema':SCHEMA,'mode':'READ_ONLY','graphs':{},'comparisons':{},
             'warnings':['Independent BUILD variation is not isolated scheduler randomness; check seeds, process/thread configs and input hashes.',
                         'Exact directed edge-set differences are not evidence of Recall/QPS differences.',
                         'ParlayANN 2024 already studies deterministic parallel graph construction; novelty NOT established.',
                         'No causal attribution or graph editing; topology stability is only a triage gate.']}
        for k,g in graphs.items():ans['graphs'][k]=g.summarize(args.batch,args.bfs)
        for a,b in PAIRS:
            ans['comparisons'][a+'_vs_'+b]=compare(graphs[a],graphs[b],args.batch)
        out=Path(args.out).expanduser().resolve() if args.out else Path('~/ann-task-a/experiments/H27').expanduser() / ('H27_R0_topology_'+dt.datetime.now().strftime('%Y%m%d_%H%M%S'))
        out.mkdir(parents=True,exist_ok=False)
        (out/'h27_r0_summary.json').write_text(json.dumps(ans,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        lines=['H27-R0 EXACT GRAPH TOPOLOGY STABILITY (read-only / no BUILD)',
               'PiPNN pinned graph format, each file SHA256 checked.',
               'Graph differences are OBSERVATIONS, not demonstrated schedule-only effect or novelty.',
               'LABEL          N       EDGES         IND0   DEGD0     DUP    REACH0(optional)']
        for k,x in ans['graphs'].items():
            lines.append(f"{k:<12s} {x['n']:>8,d} {x['edge_occurrences']:>12,d} {x['indegree_zero']:>8,d} {x['degree_zero']:>7,d} {x['duplicate_edge_occurrences']:>7,d}  {x.get('reachable_from_entry0','not run')}")
        lines+=['','PAIR                                  JACCARD       SYMDIFF_KEYS    CHANGED_ROWS      CHANGED_%']
        for k,x in ans['comparisons'].items():
            lines.append(f"{k:<37s} {x['jaccard']:>9.7f} {x['symmetric_difference_keys']:>15,d} {x['changed_neighbor_set_rows']:>15,d} {100*x['changed_neighbor_set_row_fraction']:>12.5f}%")
        lines+=['','Decision gate (HEURISTIC; not proof): if topology variation is tiny and quality stable, NO-GO for schedule-stability project. If material, first identify random-seed/algorithm/graph-write confounds before any algorithm proposal.',
                'ParlayANN determinism is strong prior art. H27-R0 is a diagnostic only.',f'H27R0_DONE={out}']
        (out/'h27_r0_summary.txt').write_text('\n'.join(lines)+'\n',encoding='utf-8')
        print('\n'.join(lines))
    except (ValueError,AssertionError,OSError,MemoryError) as e:
        print('H27R0_FAIL_CLOSED: '+str(e),file=sys.stderr);sys.exit(2)
if __name__=='__main__':main()
