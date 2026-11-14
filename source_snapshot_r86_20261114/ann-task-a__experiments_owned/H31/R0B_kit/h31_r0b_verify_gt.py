#!/usr/bin/env python3
"""H31-R0b: non-destructive verification of ParlayANN groundTruth<uint32> layout.
GT: <uint32 n,k> then n*k uint32 neighbor IDs then n*k float32 distances.
Validates layout and full payload on the known SIFT1M dataset; does NOT verify exact kNN.
"""
from __future__ import annotations
import argparse
from array import array
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import struct
import sys
import tempfile

EXPECTED_SIFT_N=1_000_000
EXPECTED_QUERY_N=10_000
EXPECTED_QUERY_D=128
EXPECTED_BASE_D=128
EXPECTED_GT_K=100
REFERENCE_VAMANA_SHA='84b2935cb9f25e9ad53044099901c8c1e6cb4de059975882e8d91bca66aa5259'

def filehash(p:Path):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):
            h.update(block)
    return h.hexdigest()

def inspect_fbin(path:Path,expect_n:int,expect_d:int):
    path=path.expanduser().resolve(strict=True)
    if path.stat().st_size<8: raise ValueError(f'Truncated fbin header: {path}')
    with path.open('rb') as f:n,d=struct.unpack('<II',f.read(8))
    want=8+n*d*4
    if (n,d)!=(expect_n,expect_d) or path.stat().st_size!=want:
        raise ValueError(f'Invalid fbin header/size: {path} n={n} d={d} size={path.stat().st_size} expected_n={expect_n} expected_d={expect_d} expected_bytes={want}')
    return dict(path=str(path),status='STRUCTURE_PASS',n=n,d=d,bytes=want)

def inspect_gt(path:Path,base_n:int,queries_n:int,min_k:int=10):
    path=path.expanduser().resolve(strict=True)
    fsize=path.stat().st_size
    if fsize<8: raise ValueError('GT file too short')
    with path.open('rb') as f:
        n,k=struct.unpack('<II',f.read(8))
        if n!=queries_n or not(min_k<=k<=100_000):
            raise ValueError(f'GT n/k invalid n={n} k={k}, queries={queries_n}, min_k={min_k}')
        cnt=n*k
        want=8+8*cnt
        if fsize!=want:raise ValueError(f'GT size invalid: observed {fsize}, expected {want} for u32 IDs + f32 distances')
        if cnt>50_000_000:raise ValueError('GT too large for bounded scan')
        # Read two CONTIGUOUS arrays separately. Do not decode as interleaved (id,dist) pairs or uint64 IDs.
        id_bytes=f.read(4*cnt)
        if len(id_bytes)!=4*cnt:raise ValueError('GT truncated ID block')
        ids=array('I');ids.frombytes(id_bytes)
        del id_bytes
        bad_id_count=sum(int(v>=base_n) for v in ids)
        first_ids=list(ids[:min(k,10)])
        if bad_id_count:
            raise ValueError(f'{bad_id_count} ground-truth IDs outside valid [0,{base_n-1}]')
        dist_bytes=f.read(4*cnt)
        if len(dist_bytes)!=4*cnt:raise ValueError('GT truncated distance block')
        ds=array('f');ds.frombytes(dist_bytes)
        del dist_bytes
        invalid_dist=sum(int(not math.isfinite(x) or x<0) for x in ds)
        if invalid_dist:raise ValueError(f'{invalid_dist} invalid Euclidean GT distance values')
        # Informational only: ParlayGT should rank increasing distances but tiny float rounding is possible.
        unsorted_rows=0
        for row in range(n):
            sub=ds[row*k:(row+1)*k]
            if any(sub[i]+1e-3<sub[i-1] for i in range(1,k)):
                unsorted_rows+=1
        extra=f.read(1)
        if extra:raise ValueError('Unexpected trailing GT bytes')
        first_ds=[round(float(x),6) for x in ds[:min(k,10)]]
    return dict(path=str(path),status='STRUCTURE_AND_FULL_ID_DISTANCE_VALUE_PASS',n=n,k=k,bytes=fsize,
                layout='header:u32[n,k]; uint32[n*k] IDs; float32[n*k] distances',
                expected_bytes=want,ids_bytes=4*cnt,distances_bytes=4*cnt,
                all_ids_in_base_range=True,all_distances_finite_nonnegative=True,
                distance_order_warnings_rows=unsorted_rows,
                first_query_first_ids=first_ids,first_query_first_distances=first_ds,sha256=filehash(path),
                caution='Does not independently recompute exact nearest-neighbor ground truth or verify query/base vectors semantics.')

def verify_inventory(p:Path):
    with p.open(encoding='utf-8') as f:d=json.load(f)
    if set(d.get('graph_roles',{}))!={'VAMANA','STOCK','TOP2'}:raise ValueError('Original H31 inventory has missing/extra graph roles')
    gt=d.get('dataset',{}).get('gt',{})
    for role in ('VAMANA','STOCK','TOP2'):
        sha=d['graph_roles'][role].get('sha256')
        if not isinstance(sha,str) or len(sha)!=64:raise ValueError(f'Missing SHA for {role} in old inventory')
    return dict(original_inventory=str(p.resolve()),original_ground_truth_status=gt.get('status'),
                original_ground_truth_size=gt.get('bytes'),
                vamana_sha256=d['graph_roles']['VAMANA']['sha256'],
                vamana_matches_historical_sha256=d['graph_roles']['VAMANA']['sha256']==REFERENCE_VAMANA_SHA,
                graph_sha256={k:d['graph_roles'][k]['sha256'] for k in ('VAMANA','STOCK','TOP2')},
                caution='These hashes are read from the existing inventory; graph files are NOT rescanned or rehashed in R0b.')

def make_test_gt(p,ids,dist,n,k):
    with p.open('wb') as f:
        f.write(struct.pack('<II',n,k))
        f.write(struct.pack('<'+'I'*len(ids),*ids))
        f.write(struct.pack('<'+'f'*len(dist),*dist))

def selftest():
    with tempfile.TemporaryDirectory() as td:
        t=Path(td)
        p=t/'a.gt'
        make_test_gt(p,[1,2,3,2,3,1],[1,2,3,1.5,2.5,3.5],2,3)
        x=inspect_gt(p,base_n=4,queries_n=2,min_k=3)
        assert x['status'].endswith('PASS') and x['bytes']==56 and x['first_query_first_ids'][:3]==[1,2,3]
        p.write_bytes(p.read_bytes()[:-4]);
        try:inspect_gt(p,base_n=4,queries_n=2,min_k=3)
        except ValueError:pass
        else:raise AssertionError('Truncated GT falsely accepted')
        make_test_gt(p,[1,2,9,2,3,1],[1,2,3,1.5,2.5,3.5],2,3)
        try:inspect_gt(p,base_n=4,queries_n=2,min_k=3)
        except ValueError:pass
        else:raise AssertionError('Out-of-range ID falsely accepted')
        make_test_gt(p,[1,2,3,2,3,1],[1,2,float('nan'),1.5,2.5,3.5],2,3)
        try:inspect_gt(p,base_n=4,queries_n=2,min_k=3)
        except ValueError:pass
        else:raise AssertionError('NaN distance falsely accepted')
        base=t/'x.fbin';base.write_bytes(struct.pack('<II',2,128)+bytes(2*128*4))
        assert inspect_fbin(base,2,128)['status']=='STRUCTURE_PASS'
    print('H31R0B_PARLAY_GT_LAYOUT_FAIL_CLOSED_SELFTEST_PASS')

def run(args):
    root=Path(args.root).expanduser().resolve(strict=True)
    inv=Path(args.inventory).expanduser().resolve(strict=True)
    old=verify_inventory(inv)
    base=inspect_fbin(root/'data'/'sift1m.fbin',EXPECTED_SIFT_N,EXPECTED_BASE_D)
    queries=inspect_fbin(root/'data'/'sift1m_queries.fbin',EXPECTED_QUERY_N,EXPECTED_QUERY_D)
    gt=inspect_gt(root/'data'/'sift1m_gt.ibin',EXPECTED_SIFT_N,EXPECTED_QUERY_N,10)
    status='INPUT_DATA_STRUCTURE_AND_GT_VALUES_PASS'
    report={'study':'H31_R0B_GT_LAYOUT_CORRECTION','schema_source':'ParlayANN@a48c6a3 algorithms/utils/types.h groundTruth<uint> constructor, lines 48-70 and save lines 85-96',
            'status':status,'base':base,'queries':queries,'gt':gt,'original_inventory':old,
            'guardrails':['No graph BUILD or SEARCH','Does NOT overwrite any original graph, dataset or H31_R0 inventory.',
                          'H31_R0b fixes false STRUCTURE_FAIL caused by missing float32 distance array in GT size model.',
                          'Correct file layout/ID range/finite distances do NOT prove ground truth computed on same base/query version.',
                          'Vamana SHA historical match proves byte identity with recorded prior graph, NOT code/flags/seed lineage.']}
    if args.out:
        folder=Path(args.out).expanduser().resolve()
    else:
        folder=root/'experiments'/'H31'/('H31_R0B_'+datetime.now().strftime('%Y%m%d_%H%M%S'))
    folder.mkdir(parents=True,exist_ok=False)
    (folder/'h31_r0b_gt_corrected.json').write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    lines=['H31-R0b ParlayANN groundTruth layout verification (READ ONLY)',
           f'BASE: {base["status"]} n={base["n"]} d={base["d"]} bytes={base["bytes"]:,}',
           f'QUERIES: {queries["status"]} n={queries["n"]} d={queries["d"]} bytes={queries["bytes"]:,}',
           f'GT: {gt["status"]} n={gt["n"]} k={gt["k"]} bytes={gt["bytes"]:,}',
           f'GT_IDS_BYTES={gt["ids_bytes"]:,} GT_DISTANCES_BYTES={gt["distances_bytes"]:,}',
           f'GT_ALL_IDS_VALID={gt["all_ids_in_base_range"]} GT_FINITE_NONNEGATIVE_DISTANCES={gt["all_distances_finite_nonnegative"]}',
           f'GT_DISTANCE_ORDER_WARNING_ROWS={gt["distance_order_warnings_rows"]} (warning only)',
           f'VAMANA_SHA_MATCHES_RECORDED_HISTORICAL={old["vamana_matches_historical_sha256"]} (hash from original inventory)',
           'NO NEW BUILD, NO NEW SEARCH, NO GRAPH RE-HASH; source data unchanged.',
           'NO NOVELTY, NO MATCHED GRAPH BUDGET/RECALL/QPS CLAIM.',
           f'H31R0B_DONE={folder}']
    summary='\n'.join(lines)+'\n'
    (folder/'h31_r0b_summary.txt').write_text(summary,encoding='utf-8')
    print(summary,end='')

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--mode',choices=['selftest','run'],default='selftest')
    p.add_argument('--root',default='~/ann-task-a')
    p.add_argument('--inventory',default='~/ann-task-a/experiments/H31/H31_R0_20261028_003956/h31_r0_inventory.json')
    p.add_argument('--out')
    args=p.parse_args()
    if sys.byteorder!='little' or array('I').itemsize!=4 or array('f').itemsize!=4:
        sys.exit('H31R0B_BLOCKED: little-endian uint32 and float32 native arrays required')
    try:
        if args.mode=='selftest': selftest()
        else:run(args)
    except (ValueError,AssertionError,OSError,KeyError,MemoryError) as e:
        sys.exit('H31R0B_FAIL_CLOSED: '+str(e))
if __name__=='__main__':main()
