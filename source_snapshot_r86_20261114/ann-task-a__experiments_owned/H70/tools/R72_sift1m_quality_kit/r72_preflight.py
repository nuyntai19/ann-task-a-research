#!/usr/bin/env python3
"""Check SIFT1M base/query/GT shape, GT IDs, and optionally exact top-10 for 2 queries.
Read-only; numpy is used for an efficient streaming exact sample check.
"""
from pathlib import Path
import argparse
import math
import struct
import sys


def require(cond, message):
    if not cond:
        raise RuntimeError(message)


def check(path, dims, bytes_per_cell, name):
    require(path.is_file(), f'{name} missing: {path}')
    with path.open('rb') as f:
        b = f.read(8)
    require(len(b) == 8, f'{name} short header')
    n, d = struct.unpack('<II', b)
    require((n, d) == dims, f'{name} unexpected shape {(n, d)} != {dims}')
    require(path.stat().st_size == 8 + n*d*bytes_per_cell,
            f'{name} unexpected file length {path.stat().st_size}')
    print(f'R72_DATA_{name}_SHAPE_PASS n={n} dim={d} bytes={path.stat().st_size}', flush=True)
    return n, d


def main():
    a = argparse.ArgumentParser(description=__doc__)
    for key in ('base', 'queries', 'gt'):
        a.add_argument('--'+key, type=Path, required=True)
    args = a.parse_args()
    for key in ('base','queries','gt'):
        setattr(args, key, getattr(args,key).expanduser().resolve())
    n, d = check(args.base, (1000000,128), 4, 'BASE')
    nq, dq = check(args.queries, (10000,128), 4, 'QUERY')
    ng, k = check(args.gt, (10000,100), 8, 'GT')
    require(nq == ng and dq == d, 'query vs gt shape mismatch')
    try:
        import numpy as np
    except ImportError as e:
        raise RuntimeError('R72_NUMPY_REQUIRED for independent GT sample validation; no changes made') from e
    ids = np.memmap(args.gt, dtype='<u4', mode='r', offset=8, shape=(ng,k))
    distances = np.memmap(args.gt, dtype='<f4', mode='r', offset=8 + ng*k*4, shape=(ng,k))
    require(bool(np.all(ids < n)), 'GT contains invalid neighbor IDs')
    require(bool(np.isfinite(distances).all()), 'GT contains nonfinite distances')
    require(bool(np.all(distances >= 0)), 'GT contains negative distances')
    dup = sum(len(set(map(int, ids[i,:10]))) < 10 for i in range(nq))
    require(dup == 0, f'GT duplicate top-10 IDs for {dup} queries')
    print('R72_GT_STRUCTURE_PASS invalid_ids=0 duplicate_top10_rows=0', flush=True)
    base = np.memmap(args.base, dtype='<f4', mode='r', offset=8, shape=(n,d))
    queries = np.memmap(args.queries, dtype='<f4', mode='r', offset=8, shape=(nq,d))
    for qi in (0,17):
        q = np.asarray(queries[qi], dtype=np.float64)
        # Keep only the 10 best per block. float64 ensures stable squared-distance arithmetic.
        candidates = []
        for start in range(0, n, 8192):
            end = min(start + 8192, n)
            block = np.asarray(base[start:end], dtype=np.float64)
            block -= q
            squared = np.einsum('ij,ij->i', block, block, optimize=True)
            top = np.argpartition(squared, min(9,len(squared)-1))[:10]
            candidates.extend((float(squared[j]), start + int(j)) for j in top)
        closest = sorted(candidates)[:10]
        exact_ids = {idx for _, idx in closest}
        gt_ids = {int(x) for x in ids[qi,:10]}
        overlap = len(exact_ids & gt_ids)
        threshold = closest[-1][0]
        tolerance = max(1e-4, abs(threshold)*1e-6)
        bad_gt = 0
        for i in gt_ids:
            v = np.asarray(base[i], dtype=np.float64) - q
            sq = float(v @ v)
            bad_gt += sq > threshold + tolerance
        print(f'R72_GT_EXACT_SAMPLE query={qi} overlap_top10={overlap}/10 '
              f'bad_gt_top10={bad_gt} exact_d10_sq={threshold:.7f}', flush=True)
        require(bad_gt == 0, f'GT exact top-10 sample mismatch for query {qi}')
    print('R72_GT_VALIDATION_PASS exact_top10_checked_for_2_queries=TRUE', flush=True)

if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print(f'R72_GT_VALIDATION_FAIL {type(e).__name__}: {e}', file=sys.stderr, flush=True)
        sys.exit(1)
