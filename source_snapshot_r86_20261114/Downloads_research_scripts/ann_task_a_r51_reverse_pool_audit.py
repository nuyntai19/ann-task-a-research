#!/usr/bin/env python3
"""H32-R51 — isolated, READ-ONLY same-build R26a candidate-pool / graph loss audit.

Do not confuse R41 exact BASE-neighbor rows with heldout ANN query Recall.
Do NOT combine cross-build H18 leaf data with R26a candidate pool.

Usage:
  python3 ann_task_a_r51_reverse_pool_audit.py selftest
  python3 -u ann_task_a_r51_reverse_pool_audit.py audit \
    > experiments/H51/r51_audit.stdout 2> experiments/H51/r51_audit.stderr

Inputs: existing R41 32-anchor exact-kNN JSON, same-build R26a graph and C160 pool.
No new exact-kNN scans, BUILD, native search or changes to existing reports.
"""
import argparse
from collections import Counter, defaultdict
from hashlib import sha256
import json
import re
from pathlib import Path
from tempfile import TemporaryDirectory
import struct
import sys

try:
    import numpy as np
except ImportError:
    raise SystemExit('Requires installed numpy (same as previous R41 diagnostics)')

GRAPH = Path('experiments/H32/H32_R26a_pool_20261029_172452_132314/dump.graph')
POOL = Path('experiments/H32/H32_R26a_pool_20261029_172452_132314/dump.candidates.i32')
R41 = Path('experiments/H41/r41_exact32.json')
OUTPUT = Path('experiments/H51/r51_reverse_pool_audit.json')
GRAPH_PIN = 'd497f6d19fff4b7db6436f960d036755e375be92483c03ec0b9ed61968d17bef'
POOL_PIN = '7e22a4ca2b71bd560560f7e4aa2a1f2dcad46b8f25ae48ca8ea014c17086f9e8'
N = 1_000_000
C = 160
EXPECTED_SOURCES = 32
EXPECTED_SLOTS = 320
EXPECTED_DIRECT = 207
EXPECTED_POOL = 278
EXPECTED_2HOP_TOTAL = 300
EXPECTED_MISSING_POOL = 42
EXPECTED_PRUNED = 71


def sha_file(p):
    h=sha256()
    with p.open('rb') as f:
        for chunk in iter(lambda: f.read(8 * 1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def ints(x, expected=10):
    if isinstance(x, (list, tuple)) and len(x)==expected:
        if all(isinstance(v,(int,np.integer)) and not isinstance(v,bool) for v in x):
            return [int(v) for v in x]
    return None


def norm_source(row):
    """No guessing from arbitrary ten-element arrays. Recognize explicit kNN keys."""
    if not isinstance(row, dict):
        return None
    sid = None
    for k in ('source_id','source','source_point_id','base_id','anchor_id','point_id','src_id','u','id'):
        if k in row and isinstance(row[k], (int,np.integer)) and not isinstance(row[k],bool):
            sid=int(row[k]);break
    if sid is None:
        return None
    knn = None
    for k in ('knn10_ids','knn_10_ids','exact_knn10_ids','exact_top10_ids','top10_ids',
              'true_top10_ids','gt10_ids','knn10','exact_top10'):
        if k in row:
            knn=ints(row[k]);
            if knn is not None: break
    if knn is None:
        for k,v in row.items():
            if 'knn' in k.lower() or 'top10' in k.lower():
                if isinstance(v,dict):
                    for kk in ('ids','neighbor_ids','point_ids','top10_ids'):
                        if kk in v:
                            knn=ints(v[kk]);
                            if knn is not None: break
                if knn is not None:break
    if knn is None:
        return None
    return (sid,knn)


def extract_r41(d):
    """Accept nested report wrappers; require 32 unambiguous source→exact10 rows."""
    candidates=[]
    visited=0
    def rec(obj, depth=0):
        nonlocal visited
        if depth>8 or visited>300000:
            return
        visited+=1
        if isinstance(obj, dict):
            z=norm_source(obj)
            if z is not None:candidates.append(z)
            for v in obj.values():
                if isinstance(v,(list,dict)):rec(v,depth+1)
        elif isinstance(obj,list):
            for v in obj:
                if isinstance(v,(list,dict)):rec(v,depth+1)
    rec(d)
    by={}
    for sid,knn in candidates:
        if sid in by and knn!=by[sid]:
            raise ValueError(f'R41 source {sid} has conflicting exact10 rows')
        by[sid]=knn
    if len(by)!=EXPECTED_SOURCES:
        typ = (list(d)[:30] if isinstance(d,dict) else type(d).__name__)
        sample = []
        for key in ('per_source','sources','results','source_results','anchors'):
            if isinstance(d,dict) and key in d:
                v=d[key]
                sample = list(v[0])[:30] if isinstance(v,list) and v and isinstance(v[0],dict) else list(v)[:30] if isinstance(v,dict) else []
                break
        raise ValueError(f'R41 exact 32 source rows not extracted (found {len(by)}). '
                         f'Root keys={typ}; sample row keys={sample}. Refuse to infer IDs.')
    for sid,knn in by.items():
        if sid<0 or sid>=N or len(knn)!=10 or len(set(knn))!=10 or sid in knn or any(v<0 or v>=N for v in knn):
            raise ValueError(f'R41 source or 10 GT IDs invalid: source={sid}, knn={knn}')
    return by


class Pool:
    def __init__(self,path=POOL,n=N,c=C,expected_sha=POOL_PIN):
        self.path=path;self.n=n;self.c=c
        if path.stat().st_size!=n*c*4:
            raise ValueError(f'Candidate pool byte length mismatch: {path.stat().st_size}')
        self.sha = sha_file(path)
        if expected_sha is not None and self.sha!=expected_sha:
            raise ValueError(f'Candidate pool SHA mismatch: {self.sha}')
        self.a=np.memmap(path,dtype='<i4',mode='r',shape=(n,c))
        self.cache={}
    def neighbors(self,v):
        if v in self.cache: return self.cache[v]
        if not (0<=v<self.n):raise ValueError(f'Pool node out of range: {v}')
        raw=self.a[v]
        arr=[int(x) for x in raw if x!=-1]
        if any(x<0 or x>=self.n or x==v for x in arr) or len(set(arr))!=len(arr):
            raise ValueError(f'Pool candidate row invalid at v={v}')
        # Detect malformed non-terminal -1 padding (expected source export format).
        if len(arr)<self.c and np.any(raw[:len(arr)]==-1):
            raise ValueError(f'Nonterminal -1 pool padding at v={v}')
        z=frozenset(arr)
        self.cache[v]=z
        return z


def classify(sources,pool,g):
    rows=[];by_kind=defaultdict(Counter)
    for s in sorted(sources):
        srcpool=pool.neighbors(s)
        srcgraph=set(g.neighbors(s))
        if s in srcgraph or len(srcgraph)!=len(set(srcgraph)):
            raise ValueError(f'Graph source row invalid s={s}')
        for r,t in enumerate(sources[s],start=1):
            direct=t in srcgraph
            inpool=t in srcpool
            if direct:
                kind='DIRECT'
            elif inpool:
                kind='CAPTURED_BUT_PRUNED'
            else:
                kind='MISSING_BEFORE_POOL'
            inverse_pool=s in pool.neighbors(t)
            inverse_graph=s in g.neighbors(t)
            graph2=sum(t in g.neighbors(w) for w in srcgraph)
            graph_then_candidate=sum(t in pool.neighbors(w) for w in srcgraph)
            row={'source_id':s,'exact_base_GT_rank':r,'target_id':t,
                 'class':kind,'source_graph_degree':len(srcgraph),
                 'source_pool_degree':len(srcpool),
                 'reverse_candidate_in_pool':bool(inverse_pool),
                 'reverse_direct_edge_in_graph':bool(inverse_graph),
                 'directed_graph_hops_le_2':bool(direct or graph2),
                 'graph_2hop_witnesses':graph2,
                 'graph_then_candidate_2hop_witnesses':graph_then_candidate,
                 'graph_neighbor_can_offer_target_as_candidate':graph_then_candidate>0}
            rows.append(row)
            by_kind[kind]['slots']+=1
            for k in ('reverse_candidate_in_pool','reverse_direct_edge_in_graph',
                      'directed_graph_hops_le_2','graph_neighbor_can_offer_target_as_candidate'):
                by_kind[kind][k]+=int(row[k])
    return rows,{kind:dict(cnt) for kind,cnt in sorted(by_kind.items())}


def summarize(rows,strict=True):
    count=Counter(x['class'] for x in rows)
    direct=count['DIRECT']; pruned=count['CAPTURED_BUT_PRUNED']; missing=count['MISSING_BEFORE_POOL']
    pool=direct+pruned
    reach=sum(x['directed_graph_hops_le_2'] for x in rows)
    summary={'slots':len(rows),'direct_graph':direct,'in_source_pool':pool,
             'missing_before_pool':missing,'captured_but_pruned':pruned,
             'reachable_directed_within_two_graph_hops':reach}
    if strict and summary!={'slots':EXPECTED_SLOTS,'direct_graph':EXPECTED_DIRECT,
                             'in_source_pool':EXPECTED_POOL,
                             'missing_before_pool':EXPECTED_MISSING_POOL,
                             'captured_but_pruned':EXPECTED_PRUNED,
                             'reachable_directed_within_two_graph_hops':EXPECTED_2HOP_TOTAL}:
        raise ValueError(f'R41/R43 replica mismatch. Observed {summary}; expected historical counts. '
                         'Do NOT extrapolate from different artifact / source selection.')
    return summary


def selftest():
    class G:
        def __init__(self):self.d={0:[1],1:[2],2:[],3:[0],4:[]}
        def neighbors(self,v):return self.d.get(v,[])
    class P:
        def __init__(self):self.d={0:[1,2],1:[2,3],2:[],3:[0],4:[]}
        def neighbors(self,v):return set(self.d.get(v,[]))
    sources={0:[1,2,3,4]}
    rows,groups=classify(sources,P(),G())
    assert [r['class'] for r in rows]==['DIRECT','CAPTURED_BUT_PRUNED','MISSING_BEFORE_POOL','MISSING_BEFORE_POOL']
    assert rows[2]['reverse_candidate_in_pool'] and rows[2]['reverse_direct_edge_in_graph']
    assert rows[2]['graph_neighbor_can_offer_target_as_candidate'] and not rows[2]['directed_graph_hops_le_2']
    assert rows[1]['directed_graph_hops_le_2'] and rows[1]['graph_2hop_witnesses']==1
    assert summarize(rows,strict=False)=={'slots':4,'direct_graph':1,'in_source_pool':2,
              'missing_before_pool':2,'captured_but_pruned':1,'reachable_directed_within_two_graph_hops':2}
    obj={'per_source':[{'source_id':i,'knn10_ids':[j for j in range(i+1,i+11)]} for i in range(32)]}
    try: extract_r41(obj)
    except ValueError as e:
        # Indices and IDs are valid, but the toy sets are not self-overlapping at n1m.
        raise AssertionError(e)
    # Test the native binary layout and the actual mmap wrappers, not only mocks.
    from ann_task_a_r47_r8_q160_topology import DirectedGraph
    with TemporaryDirectory() as folder:
        p=Path(folder)
        # 5-node native format: header, 5 degrees, concatenated directed IDs.
        graph_bytes=(struct.pack('<II',5,3)
                     +struct.pack('<5I',1,1,0,1,0)
                     +struct.pack('<3I',1,2,0))
        gp=p/'toy.graph';gp.write_bytes(graph_bytes)
        arr=np.full((5,3),-1,dtype='<i4')
        arr[0,:2]=[1,2];arr[1,:2]=[2,3];arr[3,0]=0
        pp=p/'toy.i32'; pp.write_bytes(arr.tobytes())
        pool=Pool(pp,n=5,c=3,expected_sha=None)
        with DirectedGraph(gp,expected_hash=sha_file(gp),expected_n=5) as native:
            disk_rows,disk_groups=classify(sources,pool,native)
            assert disk_rows==rows and disk_groups==groups
        bad=p/'bad.i32';bad.write_bytes(b'no')
        try:Pool(bad,n=5,c=3,expected_sha=None)
        except ValueError:pass
        else:raise AssertionError('Malformed pool not rejected')
    print('R51_SELFTEST_PASS: R41 extraction, native mmap graph/pool, reverse pool/graph, 2-hop, corruption gates')


def audit():
    if OUTPUT.exists():
        raise FileExistsError(f'Output already exists; refusing overwrite: {OUTPUT}')
    if not R41.is_file():raise FileNotFoundError(f'R41 JSON missing: {R41}')
    from ann_task_a_r47_r8_q160_topology import DirectedGraph
    raw=json.loads(R41.read_text())
    sources=extract_r41(raw)
    print(f'R51_R41_EXACT32_INPUT_PASS sources={len(sources)} slots=320',flush=True)
    with DirectedGraph(GRAPH,expected_hash=GRAPH_PIN,expected_n=N) as graph:
        if graph.cap!=32 or graph.arcs!=22797630:
            raise ValueError(f'R26a graph cap/arc changed: cap={graph.cap},arcs={graph.arcs}')
        pool=Pool()
        print('R51_R26A_GRAPH_POOL_SHA_PASS',flush=True)
        rows,groups=classify(sources,pool,graph)
        sums=summarize(rows,strict=True)
    print('R51_R41_R43_COUNTS_REPLICATION_PASS 207/278/320; 42+71; 300/320 twohop',flush=True)
    result={'audit':'R51_REVERSE_POOL_GRAPH_READONLY_PASS',
            'provenance':{'r41_json':str(R41),'r41_sha256':sha_file(R41),
                'source_ids_sorted':[int(v) for v in sorted(sources)],
                'graph_sha256':GRAPH_PIN,'pool_sha256':POOL_PIN,'n':N,'capacity':C,
                'same_build_source':'R26a candidate dump and original graph from same build',
                'h18_leaves_used':False,
                'exact_GT':'base-anchor top10, not ANN heldout query GT',
                'no_new_build_or_search':True},
            'summary':sums,'by_category':groups,'per_target':rows,
            'limitations':['Reverse pool observation does not prove a pair was evaluated/proposed in either direction.',
                           'A reverse edge or 2-hop path is not native beam-search access or recall.',
                           'R41 32 base anchors were sampled; counts are descriptive and may be noisy.',
                           'No mutation, graph construction, or algorithm novelty shown.']}
    OUTPUT.parent.mkdir(parents=True,exist_ok=True)
    with OUTPUT.open('x') as f:json.dump(result,f,indent=2,ensure_ascii=False);f.write('\n')
    for kind,grp in groups.items():
        print(f'R51_GROUP {kind} '+str(grp),flush=True)
    print('R51_REVERSE_POOL_GRAPH_READONLY_PASS',flush=True)
    print('OUTPUT',OUTPUT,flush=True)


def main():
    a=argparse.ArgumentParser()
    a.add_argument('action',choices=['selftest','audit'])
    args=a.parse_args()
    try:
        if args.action=='selftest':selftest()
        else:audit()
    except Exception as e:
        print('R51_FAIL:',e,file=sys.stderr)
        return 2
    return 0

if __name__=='__main__':sys.exit(main())
