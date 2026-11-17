#!/usr/bin/env python3
"""Within-leaf candidate recall for the dense construction (GloVe, laptop).

Leaves: L random leaders; every point (and query) joins the leaves of its m
nearest leaders (one level, like PiPNN's top level). For a query q the
candidate pool is the union of its m leaves. We report
  ceiling  = fraction of the true 10-NN inside the pool (leaf recall),
  ft@K     = recall of the true 10-NN among the top-K by float-query x 2-bit-data
             proxy inside the pool (what stage 2 re-ranks),
  ff@K     = same with exact float (the pool's own ceiling at K),
  pool     = mean pool size (proxy pairs per point = pool size).

    python3 bench/evp_leaves.py --data .. --queries .. --gold .. --nq 1000 \
        --leaders 240 700 1400 --m 1 2 3 5 --x 50 --K 200 500 1000
"""
import argparse, time, numpy as np
from evp_recall import tern

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True); ap.add_argument("--queries", required=True); ap.add_argument("--gold", required=True)
    ap.add_argument("--nq", type=int, default=1000); ap.add_argument("--x", type=int, default=50)
    ap.add_argument("--leaders", type=int, nargs="+", default=[240, 700, 1400]); ap.add_argument("--m", type=int, nargs="+", default=[1, 2, 3, 5])
    ap.add_argument("--K", type=int, nargs="+", default=[200, 500, 1000]); ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--kmeans", type=int, default=0, help="Lloyd iterations on a 200k sample (0 = random leaders)")
    a = ap.parse_args(); rng = np.random.default_rng(a.seed)
    X = np.ascontiguousarray(np.load(a.data), dtype=np.float32); Q = np.ascontiguousarray(np.load(a.queries)[:a.nq], dtype=np.float32)
    gold = np.load(a.gold)[:a.nq, :10]; n, d = X.shape
    VX = tern(X, a.x)                                   # 2-bit data side (as float for the GEMM; exact ternary values)
    mmax = max(a.m)
    print(f"GloVe n={n} nq={a.nq} x={a.x}; K={a.K}", flush=True)
    print(f"{'L':>6}{'m':>3}{'leaf':>8}{'pool':>8}{'ceiling':>9}" + "".join(f"{'ft@'+str(K):>8}{'ff@'+str(K):>8}" for K in a.K), flush=True)
    for L in a.leaders:
        leaders = X[rng.choice(n, L, replace=False)]
        if a.kmeans:
            S_ = X[rng.choice(n, 200000, replace=False)]
            for it in range(a.kmeans):
                asg = np.argmax(S_ @ leaders.T, axis=1)
                for l in range(L):
                    mem = S_[asg == l]
                    if len(mem): c = mem.mean(0); leaders[l] = c / max(np.linalg.norm(c), 1e-9)
        # m nearest leaders for every base point and query (cosine = dot on unit vectors)
        def top_leaders(A):
            out = np.empty((A.shape[0], mmax), dtype=np.int32)
            for s in range(0, A.shape[0], 65536):
                S = A[s:s+65536] @ leaders.T
                out[s:s+65536] = np.argpartition(-S, mmax - 1, axis=1)[:, :mmax] if mmax < L else np.argsort(-S, axis=1)[:, :mmax]
                # order the m by similarity
                vals = np.take_along_axis(S, out[s:s+65536], axis=1); o = np.argsort(-vals, axis=1); out[s:s+65536] = np.take_along_axis(out[s:s+65536], o, axis=1)
            return out
        t0 = time.time(); bl = top_leaders(X); ql = top_leaders(Q)
        for m in a.m:
            # leaf membership lists for m memberships per point
            memb = [[] for _ in range(L)]
            for j in range(m):
                order = np.argsort(bl[:, j], kind="stable"); ids = bl[order, j]
                bounds = np.searchsorted(ids, np.arange(L + 1))
                for l in range(L): memb[l].append(order[bounds[l]:bounds[l+1]])
            memb = [np.concatenate(v) for v in memb]; leaf_sizes = np.array([len(v) for v in memb])
            ceil = 0.0; pools = 0.0; hit_ft = {K: 0.0 for K in a.K}; hit_ff = {K: 0.0 for K in a.K}
            for i in range(a.nq):
                pool = np.unique(np.concatenate([memb[l] for l in ql[i, :m]])); pools += len(pool)
                g = set(gold[i].tolist()); inpool = g & set(pool.tolist()); ceil += len(inpool) / 10
                s_ft = VX[pool] @ Q[i]; s_ff = X[pool] @ Q[i]
                for K in a.K:
                    k = min(K, len(pool))
                    top = pool[np.argpartition(-s_ft, k - 1)[:k]]; hit_ft[K] += len(g & set(top.tolist())) / 10
                    top = pool[np.argpartition(-s_ff, k - 1)[:k]]; hit_ff[K] += len(g & set(top.tolist())) / 10
            print(f"{L:6d}{m:3d}{leaf_sizes.mean():8.0f}{pools/a.nq:8.0f}{ceil/a.nq:9.3f}" +
                  "".join(f"{hit_ft[K]/a.nq:8.3f}{hit_ff[K]/a.nq:8.3f}" for K in a.K) + f"   [{time.time()-t0:.0f}s]", flush=True)

if __name__ == "__main__":
    main()
