#!/usr/bin/env python3
"""H32-R15: Read-only comparison of the pinned PiPNN Stock vs H17 Top2 graph.

No index build, ANN search, source/binary modifications, graph edits, or novelty claims.
Validation: SHA256, graph schema, H32-R14 paired query report.
Python >= 3.9, little-endian host. Standard library only.
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
import mmap
import struct
import sys
import tempfile
from collections import Counter
from datetime import datetime
from pathlib import Path

EXPECTED_N = 1_000_000
SPEC = {
    'STOCK': {
        'path': 'experiments/H26/H26_profile_20261026_222107_gcgcqF/r1_stock.graph',
        'sha': 'ce1cd7c5ae97b79972df2b30235a0844b88a6c8a983ce731ca3afca494d7095d',
        'bytes': 95_174_232, 'edges': 22_793_556,
    },
    'TOP2': {
        'path': 'experiments/H26/H26_profile_20261026_222107_gcgcqF/r1_top2.graph',
        'sha': '73646a2b5655e16939ca804c598818460152803c20f6932e6e9286acd334c5c6',
        'bytes': 95_176_264, 'edges': 22_794_064,
    },
}
class FailClosed(Exception):
    pass

def require(test, message):
    if not test:
        raise FailClosed(message)

def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(4*1024*1024), b''):
            h.update(chunk)
    return h.hexdigest()

def newest_results(base, pattern, required):
    candidates = sorted([p for p in base.glob(pattern) if p.is_dir() and (p/required).is_file()], reverse=True)
    require(bool(candidates), 'REQUIRED_PROVENANCE_NOT_FOUND '+pattern)
    return candidates[0]

def open_graph(path, spec, verify_sha=True):
    require(path.is_file(), 'GRAPH_NOT_FOUND '+str(path))
    size = path.stat().st_size
    if verify_sha:
        require(size == spec['bytes'], 'GRAPH_BYTES_MISMATCH '+str(path))
        require(digest(path) == spec['sha'], 'GRAPH_SHA256_MISMATCH '+str(path))
    fd = path.open('rb')
    try:
        mm = mmap.mmap(fd.fileno(), 0, access=mmap.ACCESS_READ)
        n, maxdeg = struct.unpack_from('<II', mm, 0)
        require(n > 0 and 0 < maxdeg <= n, 'INVALID_GRAPH_HEADER '+str(path))
        if verify_sha:
            require(n == EXPECTED_N, 'GRAPH_N_MISMATCH')
        require(size >= 8+4*n, 'GRAPH_TOO_SHORT')
        degrees = memoryview(mm)[8:8+4*n].cast('I')
        edges = memoryview(mm)[8+4*n:].cast('I')
        require(max(degrees) <= maxdeg, 'DEGREE_OVER_MAX '+str(path))
        total = sum(degrees)
        require(size == 8 + 4*n + 4*total, 'GRAPH_CSR_LENGTH_INVALID '+str(path))
        require(len(edges) == total, 'GRAPH_EDGE_LENGTH_MISMATCH')
        if verify_sha:
            require(total == spec['edges'], 'GRAPH_ARC_COUNT_MISMATCH '+str(path))
        return fd, mm, n, maxdeg, degrees, edges
    except Exception:
        fd.close()
        raise

def compare_edges(deg_a, edges_a, deg_b, edges_b, n, sample_cap=100):
    require(len(deg_a)==n and len(deg_b)==n, 'GRAPH_NODE_COUNT_DIFFERENT')
    off_a=off_b=0
    ctr=Counter()
    changed_samples=[]
    edge_samples=[]
    changed_per_node=[]
    for i in range(n):
        a_len=int(deg_a[i]); b_len=int(deg_b[i])
        a=tuple(edges_a[off_a:off_a+a_len]); b=tuple(edges_b[off_b:off_b+b_len])
        off_a += a_len
        off_b += b_len
        require(all(0<=x<n for x in a) and all(0<=x<n for x in b), 'INVALID_NEIGHBOR_ID_AT_NODE_'+str(i))
        ctr['nodes_total']+=1
        if a_len!=b_len:
            ctr['nodes_degree_changed']+=1
        if a==b:
            ctr['nodes_same_order']+=1
            continue
        ca, cb = Counter(a), Counter(b)
        if ca==cb:
            ctr['nodes_same_multiset_different_order']+=1
            if len(changed_samples)<sample_cap:
                changed_samples.append({'vertex_id':i,'kind':'ORDER_ONLY','stock_degree':a_len,'top2_degree':b_len,
                                        'stock_head':list(a[:12]),'top2_head':list(b[:12])})
            continue
        ctr['nodes_changed_edge_multiset']+=1
        common=sum((ca&cb).values())
        rem=ca-cb; add=cb-ca
        removed=sum(rem.values()); added=sum(add.values())
        require(common+removed==a_len and common+added==b_len, 'MULTISET_COUNTS_INCONSISTENT_'+str(i))
        ctr['common_arcs_multiset']+=common
        ctr['stock_only_arcs_multiset']+=removed
        ctr['top2_only_arcs_multiset']+=added
        ctr['max_per_node_symdiff']=max(ctr['max_per_node_symdiff'],removed+added)
        ctr['nodes_with_added_arc']+=int(added>0)
        ctr['nodes_with_removed_arc']+=int(removed>0)
        if len(changed_samples)<sample_cap:
            changed_samples.append({'vertex_id':i,'kind':'EDGE_SET_OR_MULTIPLICITY_CHANGED',
                'stock_degree':a_len,'top2_degree':b_len,
                'removed_count':removed,'added_count':added,
                'removed_sample':list(rem.elements())[:12],
                'added_sample':list(add.elements())[:12]})
        changed_per_node.append((i,a_len,b_len,removed,added,common))
        if len(edge_samples)<sample_cap:
            for target in rem.elements():
                if len(edge_samples)>=sample_cap:break
                edge_samples.append({'source':i,'target':target,'only_in':'STOCK'})
            for target in add.elements():
                if len(edge_samples)>=sample_cap:break
                edge_samples.append({'source':i,'target':target,'only_in':'TOP2'})
    require(off_a==len(edges_a) and off_b==len(edges_b), 'OFFSETS_NOT_EXHAUSTED')
    ctr['graph_a_arcs']=int(off_a)
    ctr['graph_b_arcs']=int(off_b)
    # Identity rows and order-only rows contribute all their edges to the shared arc multiset.
    ctr['common_arcs_multiset']=int(off_a-ctr['stock_only_arcs_multiset'])
    require(ctr['common_arcs_multiset']==off_b-ctr['top2_only_arcs_multiset'],'ARC_DIFFERENCE_ACCOUNTING_FAILED')
    require(ctr['top2_only_arcs_multiset']-ctr['stock_only_arcs_multiset']==off_b-off_a,'EDGE_DELTA_ACCOUNTING_FAILED')
    ctr['jaccard_arc_multiset']=(ctr['common_arcs_multiset']/(ctr['common_arcs_multiset']+ctr['stock_only_arcs_multiset']+ctr['top2_only_arcs_multiset']))
    ctr['changed_edge_vertex_fraction']=ctr['nodes_changed_edge_multiset']/n
    ctr['same_order_vertex_fraction']=ctr['nodes_same_order']/n
    return ctr,changed_samples,edge_samples,changed_per_node

def confirm_r14(exp):
    r14 = newest_results(exp, 'H32_R14_2*', 'h32_r14_report.json')
    report=json.loads((r14/'h32_r14_report.json').read_text(encoding='utf-8'))
    require(report.get('status')=='PASS_R13_QUERY_PAIRED_AUDIT_READONLY', 'R14_STATUS_NOT_PASS')
    pair=report['pairs']['STOCK__TOP2']
    require(report['N_QUERY']==10000 and report['TOP_K']==10, 'R14_NQUERY_K_MISMATCH')
    require(pair['queries_same_prediction_order']==10000 and pair['queries_same_prediction_set']==10000, 'R14_PREDICTION_PARITY_NOT_CONFIRMED')
    require(pair['total_prediction_overlap_ids']==100000, 'R14_PREDICTION_OVERLAP_NOT_FULL')
    r13dir=Path(report['source_dirs']['R13'])
    require(r13dir.is_dir() and (r13dir/'h32_r13_report.json').is_file(), 'R13_ORIGINAL_PROVENANCE_MISSING')
    r13=json.loads((r13dir/'h32_r13_report.json').read_text(encoding='utf-8'))
    require(r13.get('status')=='PASS_SOURCE_BASED_PREDICTION_CAPTURE_WITH_AGGREGATE_GATE', 'R13_STATUS_NOT_PASS')
    for role in ('STOCK','TOP2'):
        require(r13['roles'][role]['graph_sha256']==SPEC[role]['sha'], 'R13_GRAPH_SHA_NOT_PINNED_'+role)
        require(r13['roles'][role]['aggregate_recall_parity_pass'] is True, 'R13_RECALL_NOT_PASSED_'+role)
    return r14, r13dir

def audit(root):
    require(sys.byteorder=='little','ONLY_LITTLE_ENDIAN_HOST_SUPPORTED')
    root=root.expanduser().resolve()
    exp=root/'experiments/H32'
    require(exp.is_dir(),'H32_EXPERIMENTS_DIR_NOT_FOUND')
    r14,r13=confirm_r14(exp)
    file_a=root/SPEC['STOCK']['path']
    file_b=root/SPEC['TOP2']['path']
    fd_a=fd_b=mm_a=mm_b=deg_a=deg_b=edges_a=edges_b=None
    try:
        fd_a,mm_a,n_a,m_a,deg_a,edges_a=open_graph(file_a,SPEC['STOCK'])
        fd_b,mm_b,n_b,m_b,deg_b,edges_b=open_graph(file_b,SPEC['TOP2'])
        require(n_a==n_b==EXPECTED_N,'GRAPH_NODE_COUNT_DIFFERENT')
        counts,samples,edge_samples,changed=compare_edges(deg_a,edges_a,deg_b,edges_b,n_a)
    finally:
        # Release all views before closing mmaps, keeping original inputs untouched.
        for view in (deg_a,deg_b,edges_a,edges_b):
            if view is not None:view.release()
        for mm in (mm_a,mm_b):
            if mm is not None:mm.close()
        for fd in (fd_a,fd_b):
            if fd is not None:fd.close()
    require(counts['graph_a_arcs']==SPEC['STOCK']['edges'] and counts['graph_b_arcs']==SPEC['TOP2']['edges'],'ARC_COUNT_GATE_FAIL')
    out=exp/('H32_R15_'+datetime.now().strftime('%Y%m%d_%H%M%S_%f'))
    out.mkdir()
    with (out/'h32_r15_changed_vertices.csv').open('w',encoding='utf-8',newline='') as f:
        w=csv.writer(f)
        w.writerow(['vertex_id','stock_degree','top2_degree','stock_only_arcs','top2_only_arcs','common_arcs'])
        w.writerows(changed)
    with (out/'h32_r15_arc_diff_samples.csv').open('w',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=['source','target','only_in']);w.writeheader();w.writerows(edge_samples)
    report={
      'status':'PASS_STOCK_TOP2_EDGE_MULTISETS_AUDIT_READONLY',
      'root':str(root),
      'provenance':{'R14':str(r14),'R13':str(r13),'stock_sha256':SPEC['STOCK']['sha'],'top2_sha256':SPEC['TOP2']['sha']},
      'counts':dict(counts),'changed_vertex_samples':samples,
      'limits':['A changed edge cannot be attributed to Top2 optimization without controlled identical BUILD seed and construction-state provenance.',
                'Agreement of 10,000 Q100 query predictions does not imply equivalence for every query, beam or dataset.',
                'No new BUILD/ANN SEARCH; no measured performance improvement from this audit.',
                'Graph budgets between Vamana and PiPNN remain unmatched.',
                'No H33, no algorithm novelty claim.']}
    (out/'h32_r15_report.json').write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    lines=[
      'H32-R15 | STOCK vs TOP2 PINNED EDGE-MULTISET COMPARISON',
      'OVERALL=PASS_STOCK_TOP2_EDGE_MULTISETS_AUDIT_READONLY',
      'NO BUILD / NO ANN SEARCH / NO GRAPH MODIFICATION',
      'R14_PAIRED_Q100_OUTPUT=IDENTICAL_ORDER_FOR_10000_QUERIES',
      f'R14_PROVENANCE={r14}',
      f'STOCK_SHA256={SPEC["STOCK"]["sha"]}',
      f'TOP2_SHA256={SPEC["TOP2"]["sha"]}',
      f'STOCK_ARCS={counts["graph_a_arcs"]}',
      f'TOP2_ARCS={counts["graph_b_arcs"]}',
      f'NET_ARC_DELTA_TOP2_MINUS_STOCK={counts["graph_b_arcs"]-counts["graph_a_arcs"]}',
      f'NODES_SAME_ORDER={counts["nodes_same_order"]}',
      f'NODES_SAME_MULTISET_DIFF_ORDER={counts["nodes_same_multiset_different_order"]}',
      f'NODES_CHANGED_EDGE_MULTISET={counts["nodes_changed_edge_multiset"]}',
      f'NODES_DEGREE_CHANGED={counts["nodes_degree_changed"]}',
      f'COMMON_DIRECTED_ARCS_MULTISET={counts["common_arcs_multiset"]}',
      f'STOCK_ONLY_ARCS_MULTISET={counts["stock_only_arcs_multiset"]}',
      f'TOP2_ONLY_ARCS_MULTISET={counts["top2_only_arcs_multiset"]}',
      f'EDGE_MULTISET_JACCARD={counts["jaccard_arc_multiset"]:.9f}',
      f'CHANGED_VERTEX_FRACTION={counts["changed_edge_vertex_fraction"]:.9f}',
      f'MAX_SYMMETRIC_ARC_DIFF_PER_VERTEX={counts["max_per_node_symdiff"]}',
      'CAUSAL_ATTRIBUTION=BLOCKED_BUILD_SEED_AND_INTERMEDIATE_STATES_NOT_CONTROLLED',
      'NO H33 / NO NOVELTY CLAIM',
      'H32R15_DONE='+str(out)
    ]
    (out/'h32_r15_summary.txt').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print('\n'.join(lines))

def write_synthetic_graph(p, rows, maxdeg=4):
    n=len(rows)
    with p.open('wb') as f:
        f.write(struct.pack('<II',n,maxdeg))
        for row in rows:
            require(len(row)<=maxdeg,'BAD_SELFTEST_DEG')
            f.write(struct.pack('<I',len(row)))
        for row in rows:
            for v in row:require(v<n,'BAD_SELFTEST_ID')
            f.write(struct.pack('<'+'I'*len(row),*row))

def selftest():
    with tempfile.TemporaryDirectory() as td:
        a=Path(td)/'a.graph';b=Path(td)/'b.graph'
        write_synthetic_graph(a, [[1,2],[0],[0,1],[]])
        write_synthetic_graph(b, [[2,1],[0,2],[0,1],[]])
        fd_a=fd_b=mm_a=mm_b=da=db=ea=eb=None
        try:
            fd_a,mm_a,n,m,da,ea=open_graph(a,{},False)
            fd_b,mm_b,n2,m2,db,eb=open_graph(b,{},False)
            ctr,_,_,ch=compare_edges(da,ea,db,eb,n)
            require(ctr['nodes_same_multiset_different_order']==1,'ORDER_ONLY_SELFTEST')
            require(ctr['nodes_changed_edge_multiset']==1,'CHANGED_ROW_SELFTEST')
            require(ctr['stock_only_arcs_multiset']==0 and ctr['top2_only_arcs_multiset']==1,'DIFF_COUNTER_SELFTEST')
            require(ctr['nodes_same_order']==2,'SAME_ORDER_SELFTEST')
            require(len(ch)==1,'CHANGED_DETAILS_SELFTEST')
        finally:
            for v in (da,db,ea,eb):
                if v is not None:v.release()
            for v in (mm_a,mm_b):
                if v is not None:v.close()
            for v in (fd_a,fd_b):
                if v is not None:v.close()
    print('H32R15_SYNTHETIC_SELFTEST_PASS (NO REAL SIFT1M CHECKED)')

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode',required=True,choices=('selftest','audit'))
    parser.add_argument('--root',default='~/ann-task-a')
    args=parser.parse_args()
    try:
        if args.mode=='selftest':selftest()
        else:audit(Path(args.root))
    except (FailClosed,ValueError,OSError,KeyError,TypeError,IndexError,struct.error,json.JSONDecodeError) as exc:
        print('H32R15_FAIL_CLOSED='+str(exc),file=sys.stderr)
        sys.exit(2)
if __name__=='__main__':main()
