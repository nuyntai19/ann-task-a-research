#!/usr/bin/env python3
"""Build a reproducible SIFT/Deep/GloVe subset with FRESH exact top-10 GT.

Read-only source arrays, deterministic base sampling; no ANN graph construction.
Supports float32 NPY, fvecs, and uint8 bvecs. Output is X/Q/gold NPY.

Example:
 python3 h24_prepare_real_subset.py --base ~/ann-task-a/data/sift_base.fvecs \
   --query ~/ann-task-a/data/sift_query.fvecs --out ~/ann-task-a/experiments/H24/data50k \
   --nbase 50000 --nquery 200 --seed 42
"""
import argparse
import hashlib
import json
from pathlib import Path
import time
import numpy as np


def read_vectors(path: Path):
    path = path.expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(f'Không tìm thấy dữ liệu: {path}')
    suf = path.suffix.lower()
    if suf == '.npy':
        A = np.load(path, mmap_mode='r', allow_pickle=False)
        if A.ndim != 2 or A.dtype.kind not in 'fiu':
            raise ValueError('NPY phải là mảng 2D vector số')
        return A
    if suf == '.fbin':
        with path.open('rb') as f:
            hdr = np.fromfile(f, dtype='<i4', count=2)

        if len(hdr) != 2:
            raise ValueError('Invalid fbin header')

        n, d = map(int, hdr)

        if n < 1 or d < 1 or d > 100000:
            raise ValueError(f'Invalid fbin shape: {n}x{d}')

        if path.stat().st_size != 8 + n * d * 4:
            raise ValueError('fbin file size does not match header')

        return np.memmap(
            path,
            dtype='<f4',
            mode='r',
            offset=8,
            shape=(n, d)
        )

    if suf not in ('.fvecs', '.bvecs'):
        raise ValueError('Định dạng hỗ trợ: .npy, .fvecs, .bvecs')
    with path.open('rb') as f:
        d = int(np.frombuffer(f.read(4), dtype='<i4')[0])
    if d < 1 or d > 100000:
        raise ValueError('Số chiều bất thường trong header')
    # fvecs: 4-byte dimension prefix and d float32 values
    # bvecs: 4-byte dimension prefix and d uint8 values
    stride = 4 + (4 * d if suf == '.fvecs' else d)
    size = path.stat().st_size
    if size % stride:
        raise ValueError(f'{suf} file size {size} not divisible by stride {stride}')
    n = size // stride
    if suf == '.fvecs':
        mm = np.memmap(path, dtype='<i4', mode='r', shape=(n, d + 1))
        if int(mm[0, 0]) != d or int(mm[-1, 0]) != d:
            raise ValueError('Inconsistent fvecs dimension headers')
        return mm[:, 1:].view('<f4')
    mm = np.memmap(path, dtype='u1', mode='r', shape=(n, stride))
    if int(np.frombuffer(mm[0, :4].tobytes(), dtype='<i4')[0]) != d:
        raise ValueError('Inconsistent bvecs dimension header')
    return mm[:, 4:]


def exact_gt(X, Q, k=10, metric='l2', bchunk=4096, qchunk=32):
    """Ground truth on exactly this X; vectorized blocked dot products, no NxQ matrix.
    For ties, stable sort candidate ids by (distance, id). Float32 cosine
    computations are for dataset consistency, not numerical certification at ties.
    """
    if X.shape[0] < k:
        raise ValueError('Cần >= k base vectors')
    n, d = X.shape
    norms_x = np.einsum('ij,ij->i', X, X) if metric == 'l2' else None
    if metric == 'cos':
        xnorm = np.maximum(np.linalg.norm(X, axis=1), 1e-30)
    output = np.empty((Q.shape[0], k), dtype=np.int32)
    for qstart in range(0, len(Q), qchunk):
        qs = np.ascontiguousarray(Q[qstart:qstart+qchunk], dtype=np.float32)
        if metric == 'cos':
            qs = qs / np.maximum(np.linalg.norm(qs, axis=1, keepdims=True), 1e-30)
        qn = len(qs)
        bestd = np.full((qn, k), np.inf, dtype=np.float32)
        besti = np.full((qn, k), -1, dtype=np.int32)
        q_sq = np.einsum('ij,ij->i', qs, qs)[:, None] if metric == 'l2' else None
        for bstart in range(0, n, bchunk):
            xb = np.ascontiguousarray(X[bstart:bstart+bchunk], dtype=np.float32)
            if metric == 'cos':
                xb = xb / xnorm[bstart:bstart+len(xb), None]
            dd = qs @ xb.T
            if metric == 'l2':
                dd *= -2.0
                dd += q_sq
                dd += norms_x[None, bstart:bstart+len(xb)]
                np.maximum(dd, 0, out=dd)
            else:
                dd *= -1.0
            cand_i = np.broadcast_to(np.arange(bstart, bstart+len(xb), dtype=np.int32)[None, :], dd.shape)
            pool_d = np.concatenate((bestd, dd), axis=1)
            pool_i = np.concatenate((besti, cand_i), axis=1)
            # Full lexicographic ordering of (distance,ID) avoids losing
            # a smaller-ID tie at the k-th boundary (argpartition would).
            idx = np.lexsort((pool_i, pool_d), axis=1)[:, :k]
            bestd = np.take_along_axis(pool_d, idx, axis=1)
            besti = np.take_along_axis(pool_i, idx, axis=1)
        output[qstart:qstart+qn] = besti
    return output


def sha(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        while True:
            chunk = f.read(2**20)
            if not chunk: break
            h.update(chunk)
    return h.hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--base')
    p.add_argument('--query')
    p.add_argument('--out')
    p.add_argument('--nbase', type=int, default=50000)
    p.add_argument('--nquery', type=int, default=200)
    p.add_argument('--seed', type=int, default=42)
    p.add_argument('--metric', choices=['l2', 'cos'], default='l2')
    p.add_argument('--bchunk', type=int, default=4096)
    p.add_argument('--qchunk', type=int, default=32)
    p.add_argument('--selftest', action='store_true')
    args = p.parse_args()
    if args.selftest:
        rng=np.random.default_rng(19)
        x=rng.normal(size=(97,13)).astype(np.float32)
        q=rng.normal(size=(11,13)).astype(np.float32)
        got=exact_gt(x,q,k=10,bchunk=15,qchunk=4)
        d=np.sum((q[:,None,:]-x[None,:,:])**2,axis=-1)
        true=np.argsort(d,axis=1,kind='stable')[:,:10]
        assert np.array_equal(got,true), f'GT mismatch {got[0]} vs {true[0]}'
        # Deliberately duplicate columns to test tie-breaking at the kth boundary.
        xx=np.zeros((25,4), dtype=np.float32)
        qq=np.zeros((3,4), dtype=np.float32)
        z=exact_gt(xx,qq,k=10,bchunk=7,qchunk=2)
        assert np.array_equal(z[0], np.arange(10)), z[0]
        print('SELFTEST PASS: blocked exact top-10 and deterministic tie break agree with brute force')
        return
    if not args.base or not args.query or not args.out:
        p.error('--base, --query, --out are required unless --selftest')
    if args.nbase<1000 or args.nquery<100 or args.bchunk<10 or args.qchunk<1:
        p.error('Need nbase>=1000, nquery>=100, bchunk>=10, qchunk>=1')
    srcx,srcq=Path(args.base),Path(args.query)
    Xsrc,Qsrc=read_vectors(srcx),read_vectors(srcq)
    if Xsrc.shape[1]!=Qsrc.shape[1]:
        p.error('Base/query dimension mismatch')
    if args.nbase>len(Xsrc) or args.nquery>len(Qsrc):
        p.error('Requested subset larger than source dataset')
    out=Path(args.out).expanduser().resolve()
    if out.exists() and any((out / z).exists() for z in ['X.npy','Q.npy','gold.npy','manifest.json']):
        p.error(f'Refuse overwrite existing subset: {out}')
    rng=np.random.default_rng(args.seed)
    base_ids=np.sort(rng.choice(len(Xsrc),args.nbase,replace=False))
    # Taking the first nquery provided benchmark queries is intentional and deterministic.
    X=np.ascontiguousarray(Xsrc[base_ids],dtype=np.float32)
    Q=np.ascontiguousarray(Qsrc[:args.nquery],dtype=np.float32)
    if not np.isfinite(X).all() or not np.isfinite(Q).all():
        p.error('Source contains NaN/Inf')
    t0=time.monotonic()
    gold=exact_gt(X,Q,k=10,metric=args.metric,bchunk=args.bchunk,qchunk=args.qchunk)
    out.mkdir(parents=True,exist_ok=True)
    np.save(out/'X.npy',X)
    np.save(out/'Q.npy',Q)
    np.save(out/'gold.npy',gold)
    np.save(out/'base_source_ids.npy',base_ids.astype(np.int32))
    man={'protocol':'H24 SMALL REAL DATA SUBSET','n':len(X),'d':X.shape[1],'nq':len(Q),'metric':args.metric,
         'seed':args.seed,'base_source':str(srcx.expanduser().resolve()),'query_source':str(srcq.expanduser().resolve()),
         'random_base_subset':True,'query_selection':'first nquery external benchmark queries',
         'groundtruth':'Recomputed exhaustive top-10 against sampled base; original full-SIFT gold not reused',
         'groundtruth_seconds':round(time.monotonic()-t0,3),
         'files':{z:sha(out/z) for z in ['X.npy','Q.npy','gold.npy','base_source_ids.npy']}}
    (out/'manifest.json').write_text(json.dumps(man,indent=2,ensure_ascii=False))
    print(json.dumps(man,indent=2,ensure_ascii=False))


if __name__=='__main__':main()
