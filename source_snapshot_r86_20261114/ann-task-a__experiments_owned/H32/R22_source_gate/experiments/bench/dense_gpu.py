#!/usr/bin/env python3
"""GPU candidate stage of the dense construction: leaders + memberships (CuPy),
then per leaf a fused brute-force kNN on the GPU (FAISS knn_gpu: GEMM + k-select)
with a running per-point top-C merge on the host. Writes the candidate lists
(n x C int32, -1 padded, nearest first) for `fg --dense-cands`, which runs the
prune, the spine and the evaluation exactly as the CPU build does.

    python3 dense_gpu.py --data data/glove_norm_X.npy --out results/cands_A.i32 \
        --leaders 240 --m 5 --C 200

Cosine data must be L2-normalised (similarity = inner product). The k-means
sums use scatter-add on the GPU (unfixed float order), so the leaves can differ
slightly between runs; the per-leaf kNN itself is exact.
"""
import argparse, time, numpy as np, cupy as cp, faiss

def sync(): cp.cuda.Stream.null.synchronize()

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True); ap.add_argument("--out", required=True)
    ap.add_argument("--leaders", type=int, default=240); ap.add_argument("--m", type=int, default=5)
    ap.add_argument("--C", type=int, default=200); ap.add_argument("--kmeans", type=int, default=10)
    ap.add_argument("--seed", type=int, default=1)
    a = ap.parse_args(); rng = np.random.default_rng(a.seed)
    X_h = np.ascontiguousarray(np.load(a.data), dtype=np.float32); n, d = X_h.shape; L, m, C = a.leaders, a.m, a.C
    t_all = time.time()
    X = cp.asarray(X_h)
    print(f"dense_gpu n={n} d={d} L={L} m={m} C={C} faiss {faiss.__version__} on {cp.cuda.runtime.getDeviceProperties(0)['name'].decode()}", flush=True)

    # ---- 1. leaders: seeded sample, Lloyd iterations on the GPU ----
    t = time.time()
    samp = cp.asarray(rng.choice(n, min(200000, n), replace=False)); S = X[samp]
    leaders = X[cp.asarray(rng.choice(n, L, replace=False))].copy()
    for _ in range(a.kmeans):
        asg = cp.argmax(S @ leaders.T, axis=1)
        sums = cp.zeros((L, d), cp.float32); cnt = cp.zeros(L, cp.float32)
        cp.add.at(sums, asg, S); cp.add.at(cnt, asg, 1.0)
        newl = sums / cp.maximum(cnt, 1)[:, None]
        newl /= cp.maximum(cp.linalg.norm(newl, axis=1, keepdims=True), 1e-9)
        leaders = cp.where((cnt > 0)[:, None], newl, leaders)
    del S; sync(); t_lead = time.time() - t

    # ---- 2. memberships (m nearest leaders) + leaf lists ----
    t = time.time()
    memb = cp.empty((n, m), cp.int32)
    for s in range(0, n, 65536):
        sims = X[s:s+65536] @ leaders.T
        memb[s:s+65536] = cp.argpartition(-sims, m - 1, axis=1)[:, :m].astype(cp.int32)
    memb_h = cp.asnumpy(memb); del memb, X, leaders; cp.get_default_memory_pool().free_all_blocks()
    order = np.argsort(memb_h.ravel(), kind="stable"); ids = np.repeat(np.arange(n, dtype=np.int32), m)[order]
    lptr = np.searchsorted(memb_h.ravel()[order], np.arange(L + 1))
    t_memb = time.time() - t
    sizes = np.diff(lptr); print(f"leaves: mean {sizes.mean():.0f} max {sizes.max()}  leaders {t_lead:.2f}s memberships {t_memb:.2f}s", flush=True)

    # ---- 3. per-leaf exact kNN on the GPU, running top-C per point kept on the GPU ----
    res = faiss.StandardGpuResources(); res.setTempMemory(1 << 30)
    cand = cp.full((n, C), -1, cp.int32); cdist = cp.full((n, C), cp.inf, cp.float32)
    pairs = 0; t = time.time(); t_gpu = 0.0
    for l in range(L):
        M_h = ids[lptr[l]:lptr[l+1]]; sz = len(M_h); pairs += sz * sz
        XM = np.ascontiguousarray(X_h[M_h]); k = min(C + 1, sz)
        t0 = time.time()
        Dk, Ik = faiss.knn_gpu(res, XM, XM, k, metric=faiss.METRIC_INNER_PRODUCT)   # (sz, k) similarities, local ids
        t_gpu += time.time() - t0
        M = cp.asarray(M_h); Dk = 1.0 - cp.asarray(Dk); Ik = M[cp.asarray(Ik)]
        Dk[Ik == M[:, None]] = cp.inf                                # drop self
        ids2 = cp.concatenate([cand[M], Ik], axis=1); dd2 = cp.concatenate([cdist[M], Dk], axis=1)
        o = cp.argsort(ids2, axis=1); ids2 = cp.take_along_axis(ids2, o, axis=1); dd2 = cp.take_along_axis(dd2, o, axis=1)
        dup = cp.zeros_like(ids2, dtype=cp.bool_); dup[:, 1:] = (ids2[:, 1:] == ids2[:, :-1]) & (ids2[:, 1:] >= 0)
        dd2 = cp.where(dup, cp.inf, dd2)
        o = cp.argpartition(dd2, C - 1, axis=1)[:, :C]
        cand[M] = cp.take_along_axis(ids2, o, axis=1); cdist[M] = cp.take_along_axis(dd2, o, axis=1)
        del M, Dk, Ik, ids2, dd2, o, dup
        if l % 40 == 0: sync(); print(f"  leaf {l}/{L} sz={sz} pairs {pairs/1e9:.1f}G  gpu-knn {t_gpu:.1f}s total {time.time()-t:.1f}s", flush=True)
    sync(); t_cand = time.time() - t
    del res; cp.get_default_memory_pool().free_all_blocks()
    for s in range(0, n, 65536):                                   # final per-row order, in chunks (memory)
        o = cp.argsort(cdist[s:s+65536], axis=1)
        cand[s:s+65536] = cp.take_along_axis(cand[s:s+65536], o, axis=1); cdist[s:s+65536] = cp.take_along_axis(cdist[s:s+65536], o, axis=1)
        cand[s:s+65536] = cp.where(cp.isinf(cdist[s:s+65536]), -1, cand[s:s+65536])
    cand = cp.asnumpy(cand); cdist = cp.asnumpy(cdist)
    cand.astype(np.int32).tofile(a.out)
    print(f"candidates: {pairs/1e9:.1f} G pairs (ordered; both (p,c) and (c,p)); gpu kNN {t_gpu:.2f}s = {pairs/t_gpu/1e9:.2f} G pairs/s, "
          f"merge+transfer {t_cand-t_gpu:.2f}s; stage {t_cand:.2f}s; mean candidates/pt {float((cand >= 0).sum(axis=1).mean()):.1f}; "
          f"total {time.time()-t_all:.1f}s; wrote {a.out}", flush=True)

if __name__ == "__main__":
    main()
