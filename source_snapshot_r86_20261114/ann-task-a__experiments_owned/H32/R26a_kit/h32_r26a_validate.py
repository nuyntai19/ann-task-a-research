#!/usr/bin/env python3
"""H32-R26a: memory-bounded structural parser for PiPNN native graph & pool.
No neural or ANN search; no writes to graph or candidate input files.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import struct
import sys
import numpy as np

N = 1_000_000
DIM = 128
C = 160

def sha256(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(8*1024*1024), b''):
            h.update(block)
    return h.hexdigest()


def graph_check(path, n=N, cap=32):
    path = Path(path)
    size = path.stat().st_size
    if size < 8 + 4*n or size % 4: raise ValueError(f'GRAPH_BAD_SIZE={path}')
    x = np.memmap(path, mode='r', dtype='<u4')
    nn, maxdeg = map(int, x[:2])
    if nn != n or maxdeg != cap: raise ValueError(f'GRAPH_HEADER={nn},{maxdeg}, expected={n},{cap}')
    deg = x[2:2+n]
    if np.any(deg > cap): raise ValueError('GRAPH_BAD_DEGREE')
    offsets = np.empty(n+1, dtype=np.int64)
    offsets[0] = 0
    np.cumsum(deg, dtype=np.int64, out=offsets[1:])
    arcs = int(offsets[-1]); expected = 8 + 4*(n+arcs)
    if expected != size: raise ValueError(f'GRAPH_EDGE_COUNT_MISMATCH size={size} expected={expected} arcs={arcs}')
    adj = x[2+n:]
    # Validate IDs, self-loops and duplicate source-destination arcs without
    # materializing all N*degree source IDs in memory.
    for a in range(0,n,25_000):
        b=min(a+25_000,n)
        lo=int(offsets[a]); hi=int(offsets[b]); dst=adj[lo:hi]
        if np.any(dst >= n): raise ValueError(f'GRAPH_OUT_OF_RANGE_ROWS={a}:{b}')
        src=np.repeat(np.arange(a,b,dtype=np.uint32), deg[a:b].astype(np.int64))
        if len(src)!=len(dst): raise ValueError('GRAPH_INTERNAL_INDEX_ERROR')
        if np.any(src==dst): raise ValueError(f'GRAPH_SELF_LOOP_ROWS={a}:{b}')
        keys=(src.astype(np.uint64)<<np.uint64(32))|dst.astype(np.uint64)
        if np.unique(keys).size!=len(keys): raise ValueError(f'GRAPH_DUP_ARCS_ROWS={a}:{b}')
    return {'vertices':n,'header_max_degree':maxdeg,'arcs':arcs,'graph_bytes':size,
            'isolated_vertices':int(np.count_nonzero(deg==0)),
            'avg_degree':round(arcs/n,6),'sha256':sha256(path)}


def dump_check(path, n=N, c=C):
    path=Path(path)
    size=path.stat().st_size;expected=n*c*4
    if size != expected: raise ValueError(f'DUMP_BAD_SIZE={size}; expected={expected}')
    X=np.memmap(path, dtype='<i4', mode='r',shape=(n,c))
    candidate_total=0; nonempty=0; self_count=0
    for a in range(0,n,10_000):
        b=min(n,a+10_000);p=X[a:b]
        if np.any((p < -1)|(p>=n)):
            raise ValueError(f'DUMP_INVALID_CANDIDATE_ID_ROWS={a}:{b}')
        if np.any((p[:,1:]!=-1)&np.maximum.accumulate(p[:,:-1]==-1,axis=1)):
            raise ValueError(f'DUMP_NONCONTIGUOUS_PADDING_ROWS={a}:{b}')
        mask=p>=0;cnt=int(np.count_nonzero(mask))
        candidate_total+=cnt;nonempty+=int(np.count_nonzero(np.any(mask,axis=1)))
        self_count+=int(np.count_nonzero(p==np.arange(a,b,dtype=np.int32)[:,None]))
    return {'rows':n,'capacity':c,'dump_bytes':size,'candidate_slots_populated':candidate_total,
            'mean_candidates':round(candidate_total/n,6),'rows_with_candidates':nonempty,
            'self_candidate_slots':self_count,'sha256':sha256(path)}


def selftest():
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        p=Path(d)/'tiny.graph';q=Path(d)/'tiny.i32'
        # n=4, cap=2, 5 directed arcs, with no self or duplicates.
        p.write_bytes(struct.pack('<'+'I'*11,4,2,2,1,1,1,1,2,0,3,1))
        assert graph_check(p,4,2)['arcs']==5
        q.write_bytes(struct.pack('<'+'i'*12,1,2,-1,0,-1,-1,0,3,-1,2,-1,-1))
        assert dump_check(q,4,3)['candidate_slots_populated']==6
        # Mutation must be caught by the validator.
        bad=Path(d)/'bad.i32'
        bad.write_bytes(struct.pack('<'+'i'*12,-1,2,-1,0,-1,-1,0,3,-1,2,-1,-1))
        try: dump_check(bad,4,3)
        except ValueError: pass
        else: raise AssertionError('bad padding not rejected')
    print('R26A_VALIDATOR_SELFTEST_PASS')


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--mode',choices=['selftest','audit'],required=True)
    ap.add_argument('--out'); a=ap.parse_args()
    if a.mode=='selftest':selftest();return
    out=Path(a.out); no=graph_check(out/'nodump.graph');dump=graph_check(out/'dump.graph')
    pool=dump_check(out/'dump.candidates.i32')
    same=no['sha256']==dump['sha256']
    report={'status':'R26A_SOURCE_POOL_GRAPH_GATE_PASS' if same else 'R26A_GRAPH_MISMATCH_INVESTIGATE',
            'n':N,'d':DIM,'candidate_c':C,'nograph_dump_invariance':same,
            'nodump_graph':no,'dump_graph':dump,'candidate_dump':pool,
            'limitations':['single source revision and seed','two sequential builds, not paired counterbalanced performance benchmark',
              'no heldout ANN query Recall or QPS','no matched graph budget or PiPNN II native baseline',
              'no physical RAM bandwidth bottleneck diagnosis']}
    (out/'r26a_report.json').write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n')
    lines=[f'R26A_GATE={report["status"]}',f'R26A_GRAPH_NONINTERFERENCE={"PASS" if same else "FAIL"}',
           f'R26A_GRAPH_ARCS_NODUMP={no["arcs"]}',f'R26A_GRAPH_ARCS_DUMP={dump["arcs"]}',
           f'R26A_GRAPH_SHA_NODUMP={no["sha256"]}',f'R26A_GRAPH_SHA_DUMP={dump["sha256"]}',
           f'R26A_POOL_SHA256={pool["sha256"]}',f'R26A_POOL_MEAN_CANDIDATES={pool["mean_candidates"]}',
           f'R26A_POOL_ROWS_WITH_CANDIDATES={pool["rows_with_candidates"]}',
           f'R26A_POOL_SELF_SLOTS={pool["self_candidate_slots"]}',
           'R26A_SIFT1M_BUILD_COUNTS=2 (NOT SPEED BENCHMARK REPLICATION)',
           'R26A_ANN_SEARCH_EXECUTED=NO','R26A_FGRAFT_ENDING_EXECUTED=NO',
           'R26A_PIPNN_II_EXECUTED=NO']
    (out/'r26a_summary.txt').write_text('\n'.join(lines)+'\n')
    print('\n'.join(lines))
    if not same: raise SystemExit(3)

if __name__=='__main__':main()
