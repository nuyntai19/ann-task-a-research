#!/usr/bin/env python3
"""Validate fbin/ibin layout and exact top-10 for 2 queries (no numpy required)."""
import argparse
import heapq
import math
import struct
from array import array
from pathlib import Path


def header(path, n_expected, d_expected, per_element):
    path = Path(path)
    with path.open('rb') as f:
        n, d = struct.unpack('<II', f.read(8))
    expected = 8 + n * d * per_element
    if (n, d) != (n_expected, d_expected) or path.stat().st_size != expected:
        raise ValueError(f'wrong file dimensions or length for {path}: n={n} d={d} bytes={path.stat().st_size}')
    return n, d


def load_float(path, count):
    with open(path, 'rb') as f:
        f.seek(8)
        values = array('f')
        values.fromfile(f, count)
        if values.itemsize != 4:
            raise ValueError('non-IEEE float32 platform')
        return values


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--base', required=True)
    ap.add_argument('--queries', required=True)
    ap.add_argument('--gt', required=True)
    a = ap.parse_args()
    bn, d = header(a.base, 100000, 128, 4)
    qn, qd = header(a.queries, 300, 128, 4)
    gn, gk = header(a.gt, 300, 100, 8)
    with open(a.gt, 'rb') as f:
        f.seek(8)
        ids = array('I')
        ids.fromfile(f, gn*gk)
        distances = array('f')
        distances.fromfile(f, gn*gk)
    if ids.itemsize != 4 or len(ids) != 30000:
        raise ValueError('wrong uint32 dtype')
    invalid = sum(v >= bn for v in ids)
    duplicate10 = sum(len(set(ids[i*gk:i*gk+10])) < 10 for i in range(qn))
    if invalid or duplicate10:
        raise ValueError(f'invalid gt IDs={invalid}, duplicate-top10-rows={duplicate10}')
    print(f'R70_GT_SHAPE_PASS base={bn}x{d} queries={qn}x{qd} gt={gn}x{gk} invalid_ids=0')
    base = load_float(a.base, bn*d)
    query = load_float(a.queries, qn*d)
    for qi in [0, 17]:
        q = query[qi*d:(qi+1)*d]
        # No numpy required; only 2 queries, full exact scan across all 100k vectors.
        best = heapq.nsmallest(10, (
            (sum((float(base[idx*d+j]) - float(q[j]))**2 for j in range(d)), idx)
            for idx in range(bn)
        ))
        ids10 = set(ids[qi*gk:qi*gk+10]); correct10 = set(idx for _, idx in best)
        overlap = len(ids10 & correct10)
        # Tie-safe: every claimed GT top-10 member must be within the true k-th distance.
        kth = best[-1][0]
        bad = 0
        for idx in ids10:
            sq = sum((float(base[idx*d+j]) - float(q[j]))**2 for j in range(d))
            if sq > kth + max(1e-4, abs(kth)*1e-6):
                bad += 1
        print(f'R70_GT_EXACT_SAMPLE query={qi} overlap_top10={overlap}/10 bad_gt_top10={bad} exact_d10_sq={kth:.7f}')
        if bad:
            raise ValueError('Ground truth top10 not exact for supplied base/query: DO NOT use this GT')
    print('R70_GT_VALIDATION_PASS exact_top10_checked_for_2_queries=TRUE')

if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print('R70_GT_VALIDATION_FAIL', str(e))
        raise SystemExit(1)
