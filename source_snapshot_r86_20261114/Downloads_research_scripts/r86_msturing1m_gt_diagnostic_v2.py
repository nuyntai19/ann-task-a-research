#!/usr/bin/env python3
"""Read-only MS-Turing-1M ground-truth diagnostic. No downloads, writes, or BUILD.

Checks the exact SHA pins from the completed 2026-11-14 download, the
benchmark's split [int32 IDs][float32 auxiliary distances] layout, records
negative/nonfinite distance diagnostics, and independently brute-forces top100
IDs for selected queries against the full 1M-base vector prefix. Does not
invent/recompute a ground-truth file.
"""
import argparse
import hashlib
import math
import struct
import sys
from pathlib import Path

EXPECTED = {
    "base.1M.fbin": (400000008, "44e83e1dd4c65999b75873101adc5ac06ca900d259a2befd05c2c3aa28ff4042", (1000000,100)),
    "query.public.100K.fbin": (40000008, "48d087a17bec15a5ec9ea526fe9bd14ac31bbbb5cd200817b341adbb77695644", (100000,100)),
    "groundtruth.public.100K.ibin": (80000008, "fa5acf5ab262b42355296e99f920e6aa863f48820ca6f70fa37ca7966634c344", (100000,100)),
}
N,D,Q,K = 1000000,100,100000,100

def require(ok, message):
    if not ok:
        raise RuntimeError(message)

def sha256(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda: f.read(8*1024*1024), b''):
            h.update(b)
    return h.hexdigest()

def read_and_check_files(dest):
    for name, (size,digest,shape) in EXPECTED.items():
        f=dest/name
        require(f.is_file(), f'MISSING {f}')
        require(f.stat().st_size==size, f'FILE_SIZE_MISMATCH {name} got={f.stat().st_size} expected={size}')
        with f.open('rb') as stream:
            hdr=struct.unpack('<II',stream.read(8))
        require(hdr==shape, f'HEADER_MISMATCH {name} got={hdr} wanted={shape}')
        actual=sha256(f)
        require(actual==digest, f'SHA_MISMATCH {name} got={actual} expected={digest}')
        print(f'PIN_HEADER_SIZE_SHA_PASS {name} sha256={actual}',flush=True)

def distance_diagnostic(dist):
    import numpy as np
    negative=nonfinite=nan=posinf=neginf=monotonic_drops=zero=0
    minv=math.inf;maxv=-math.inf
    for a in range(0,Q,2000):
        z=np.asarray(dist[a:min(Q,a+2000)])
        finite=np.isfinite(z)
        good=z[finite]
        if good.size:
            minv=min(minv,float(good.min()));maxv=max(maxv,float(good.max()))
            negative+=int(np.count_nonzero(good<0))
            zero+=int(np.count_nonzero(good==0))
        nonfinite+=int(np.count_nonzero(~finite))
        nan+=int(np.count_nonzero(np.isnan(z)))
        posinf+=int(np.count_nonzero(np.isposinf(z)))
        neginf+=int(np.count_nonzero(np.isneginf(z)))
        neighbors_ok=finite[:,1:] & finite[:,:-1]
        monotonic_drops+=int(np.count_nonzero((z[:,1:] < z[:,:-1]-1.e-5) & neighbors_ok))
    print('GT_DISTANCE_DIAGNOSTICS',f'finite_min={minv}',f'finite_max={maxv}',
          f'negative={negative}',f'zero={zero}',f'nonfinite={nonfinite}',
          f'nan={nan}',f'posinf={posinf}',f'neginf={neginf}',
          f'finite_adjacent_decreases={monotonic_drops}',flush=True)
    for q in (0,50000,99999):
        print(f'GT_DISTANCE_QUERY_SAMPLE q={q} values={np.asarray(dist[q,:10]).tolist()}',flush=True)
    return {'negative':negative,'nonfinite':nonfinite,'drops':monotonic_drops}

def brute_force_query(base,queries,ids,dists,qid):
    import numpy as np
    q=np.asarray(queries[qid],dtype=np.float32)
    require(np.isfinite(q).all(),f'QUERY_NOT_FINITE q={qid}')
    best_val=np.empty(0,dtype=np.float32)
    best_id=np.empty(0,dtype=np.int64)
    for start in range(0,N,20000):
        stop=min(start+20000,N)
        data=np.asarray(base[start:stop],dtype=np.float32)
        require(np.isfinite(data).all(),f'BASE_NOT_FINITE start={start} stop={stop}')
        delta=data-q
        squares=np.einsum('ij,ij->i',delta,delta,optimize=True)
        require(np.isfinite(squares).all(),f'COMPUTED_DISTANCE_INVALID q={qid}')
        ix=np.argpartition(squares,K-1)[:K]
        both_v=np.concatenate((best_val,squares[ix]))
        both_id=np.concatenate((best_id,start+ix.astype(np.int64)))
        chosen=np.argpartition(both_v,K-1)[:K]
        best_val=both_v[chosen]
        best_id=both_id[chosen]
    expected_set=set(map(int,best_id))
    gt_ids=np.asarray(ids[qid],dtype=np.int64)
    require(len(set(map(int,gt_ids)))==K,f'GT_DUPLICATE_IDS q={qid}')
    got_set=set(map(int,gt_ids))
    overlap=len(got_set & expected_set)
    cutoff=float(best_val.max())
    minval=float(best_val.min())
    tol=max(0.05,2e-5*cutoff)
    top_id=int(gt_ids[0]);diff=np.asarray(base[top_id],dtype=np.float32)-q
    top_sq=float(np.dot(diff,diff))
    require(top_sq <= minval+tol,f'GT_TOP1_NOT_EXACT q={qid} gt_id={top_id} gt_sq={top_sq} best_sq={minval}')
    missing=got_set-expected_set
    if missing:
        delta=np.asarray(base[list(missing)],dtype=np.float32)-q
        outside=np.einsum('ij,ij->i',delta,delta,optimize=True)
        worst=float(outside.max())
        require(worst <= cutoff+tol,f'GT_TOP100_NOT_EXACT q={qid} overlap={overlap} worst_missed_sq={worst} cutoff_sq={cutoff} tolerance={tol}')
    observed=float(dists[qid,0]);computed=math.sqrt(top_sq)
    ratios={
        'L2':abs(observed-computed),
        'L2_SQUARED':abs(observed-top_sq),
        'NEG_L2':abs(observed+computed),
        'NEG_L2_SQUARED':abs(observed+top_sq)
    }
    print(f'GT_EXACT_TOP100_IDS_PASS q={qid} direct_overlap={overlap}/{K} tied_cutoff_tolerance_sq={tol:.5g} root_sq={top_sq:.8g} root_l2={computed:.8g} stored_distance={observed:.8g} distance_convention_candidate={min(ratios,key=ratios.get)} distance_convention_error={min(ratios.values()):.5g}',flush=True)

def main():
    import numpy as np
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',type=Path,default=Path.home()/'ann-task-a')
    p.add_argument('--spotchecks',type=int,default=3)
    opt=p.parse_args()
    require(opt.spotchecks in (1,2,3),'SPOTCHECKS_MUST_BE_1_2_OR_3')
    dest=opt.root/'data'/'MSTuring_1M_v1'
    require(dest.is_dir(),f'FOLDER_MISSING {dest}')
    read_and_check_files(dest)
    base=np.memmap(dest/'base.1M.fbin',mode='r',dtype='<f4',offset=8,shape=(N,D))
    queries=np.memmap(dest/'query.public.100K.fbin',mode='r',dtype='<f4',offset=8,shape=(Q,D))
    gt=dest/'groundtruth.public.100K.ibin'
    ids=np.memmap(gt,mode='r',dtype='<i4',offset=8,shape=(Q,K))
    dists=np.memmap(gt,mode='r',dtype='<f4',offset=8+4*Q*K,shape=(Q,K))
    mni=int(ids.min());mxi=int(ids.max())
    require(0<=mni<=mxi<N,f'GT_IDS_OUT_OF_RANGE min={mni} max={mxi}')
    print(f'GT_ALL_ID_RANGE_PASS min={mni} max={mxi} n={N}',flush=True)
    diag=distance_diagnostic(dists)
    for qid in [0,Q//2,Q-1][:opt.spotchecks]:
        brute_force_query(base,queries,ids,dists,qid)
    print('R86_MSTURING1M_GT_ID_ONLY_EXACT_SPOTCHECK_PASS',flush=True)
    if diag['nonfinite'] or diag['negative'] or diag['drops']:
        print('GT_AUXILIARY_DISTANCE_COLUMN_REQUIRES_INVESTIGATION_NOT_CERTIFIED',flush=True)
        print('DISTANCE_TIE_AWARE_RECALL_NOT_APPROVED; ID_ONLY_RECALL_CAN_BE_EVALUATED_AFTER_EVALUATOR_PIN',flush=True)
    else:
        print('GT_AUXILIARY_DISTANCE_BASIC_SANITY_PASS; DISTANCE_CONVENTION_STILL_REQUIRES_MATCHING_EXACT_VALUES',flush=True)
    print('R86_MSTURING1M_READONLY_DIAGNOSTIC_COMPLETE_NO_WRITES',flush=True)

if __name__=='__main__':
    try:main()
    except (OSError,ValueError,RuntimeError) as e:
        print('R86_MSTURING1M_DIAGNOSTIC_HOLD',str(e),file=sys.stderr,flush=True)
        sys.exit(2)
