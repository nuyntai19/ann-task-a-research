#!/usr/bin/env python3
"""EVP (Connor-Dearle-Claydon 2-bit ternary quantisation) as a candidate filter on GloVe.

For nq queries: proxy similarity against ALL n base vectors, top-K proxy candidates,
recall of the true 10-NN (answer key) at K.  The ternary scalar product equals the
bitwise b2sp exactly, so it is computed here as a GEMM over {-1,0,1} vectors.
Variants: tt = ternary query x ternary data (the paper's b2sp); tf = ternary query x
float data ("hybrid", masked addition); ft = float query x ternary data; ff = exact.

    python3 bench/evp_recall.py --data data/glove_norm_X.npy --queries data/glove_norm_Q.npy \
        --gold data/glove_gold.npy --nq 1000 --x 25 50 66 100
"""
import argparse, time, numpy as np

def tern(U, x):
    """nearest {x,d} EVP vertex: +-1 on the x largest |u_i|, 0 elsewhere."""
    d = U.shape[1]
    if x >= d: return np.sign(U).astype(np.float32)
    thr = -np.partition(-np.abs(U), x - 1, axis=1)[:, x - 1:x]     # x-th largest |u_i| per row
    V = np.where(np.abs(U) >= thr, np.sign(U), 0).astype(np.float32)
    return V

def recall_at(sims_fn, Q_side, X_side, gold, Ks, chunk=100):
    n = X_side.shape[0]; nq = Q_side.shape[0]; Kmax = max(Ks); hits = {K: 0.0 for K in Ks}
    for s in range(0, nq, chunk):
        S = sims_fn(Q_side[s:s + chunk], X_side)                     # (chunk, n) similarity, higher = closer
        top = np.argpartition(-S, Kmax, axis=1)[:, :Kmax]
        vals = np.take_along_axis(S, top, axis=1); order = np.argsort(-vals, axis=1, kind="stable")
        top = np.take_along_axis(top, order, axis=1)
        for i in range(top.shape[0]):
            g = set(gold[s + i, :10].tolist())
            for K in Ks: hits[K] += len(g & set(top[i, :K].tolist())) / 10
    return {K: hits[K] / nq for K in Ks}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True); ap.add_argument("--queries", required=True); ap.add_argument("--gold", required=True)
    ap.add_argument("--nq", type=int, default=1000); ap.add_argument("--x", type=int, nargs="+", default=[25, 50, 66, 100])
    ap.add_argument("--K", type=int, nargs="+", default=[10, 50, 100, 200, 500, 1000, 2000])
    a = ap.parse_args()
    X = np.ascontiguousarray(np.load(a.data), dtype=np.float32); Q = np.ascontiguousarray(np.load(a.queries)[:a.nq], dtype=np.float32)
    gold = np.load(a.gold)[:a.nq]; n, d = X.shape
    print(f"GloVe n={n} d={d} nq={a.nq}; recall of true 10-NN among top-K proxy candidates (K={a.K})", flush=True)
    XT = X.T.copy()
    dot = lambda A, B: A @ B
    t0 = time.time(); r = recall_at(lambda q, b: dot(q, b), Q, XT, gold, a.K); print(f"{'exact float (ff)':24s}" + "".join(f"{r[K]:7.3f}" for K in a.K) + f"   [{time.time()-t0:.0f}s]", flush=True)
    for x in a.x:
        VX = tern(X, x); VQ = tern(Q, x); VXT = VX.T.copy()
        for name, qs, xs in (("tt (b2sp)", VQ, VXT), ("tf (tern q, float x)", VQ, XT), ("ft (float q, tern x)", Q, VXT)):
            t0 = time.time(); r = recall_at(lambda q, b: dot(q, b), qs, xs, gold, a.K)
            print(f"x={x:3d} {name:20s}" + "".join(f"{r[K]:7.3f}" for K in a.K) + f"   [{time.time()-t0:.0f}s]", flush=True)
        nz = (VX != 0).sum(1); print(f"      nonzeros/vector: mean {nz.mean():.1f}", flush=True)

if __name__ == "__main__":
    main()
