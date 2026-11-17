#!/usr/bin/env python3
"""Adaptive memberships (results/transitivity-FINDINGS.md): give extra
memberships only to the points whose kNN neighbourhood is not clique-like.

Per corpus: exact 10-NN of every point (faiss flat, cached), local clustering
cc(p) (oracle score), two build-time proxies -- cc on the approximate 10-NN
graph a pilot m=2 leaf pass produces (its pairs are a subset of the final
build's, so it costs nothing extra in a real implementation) and the leader
margin d1/d2 -- then a cover-vs-pairs frontier on sampled true pairs for
uniform m and for two-level policies m(p) = m_hi on the hardest fraction f,
m_lo elsewhere. Writes fg --dense-m-file files (n uint8) for, per score:
  A = the most cover at <= the pairs of uniform m=5 (the paper's point)
  B = the fewest pairs at >= the cover of uniform m=5
Usage: adaptive_m_prep.py X.npy L out_prefix [threads]
"""
import numpy as np, sys, time, os, faiss
X_path, L, out = sys.argv[1], int(sys.argv[2]), sys.argv[3]
threads = int(sys.argv[4]) if len(sys.argv) > 4 else 64
faiss.omp_set_num_threads(threads)
K, NS, MMAX, SEED = 10, 20000, 10, 0
t0 = time.time()
def log(*a): print(f"[{time.time()-t0:7.0f}s]", *a, flush=True)
X = np.ascontiguousarray(np.load(X_path), np.float32); n, d = X.shape
log(f"{X_path}: n={n} d={d} L={L}")

# ---- exact 10-NN (cached) ---------------------------------------------------
kp = f"{out}_knn10.npy"
if os.path.exists(kp):
    N = np.load(kp)
else:
    ix = faiss.IndexFlatL2(d); ix.add(X); N = np.empty((n, K), np.int32)
    for s in range(0, n, 65536):
        _, I = ix.search(X[s:s + 65536], K + 1)
        own = np.arange(s, min(n, s + 65536))[:, None]
        keep = I != own                                   # drop self; if self absent (duplicates) drop the last
        keep[keep.all(1), -1] = False
        N[s:s + len(I)] = I[keep].reshape(len(I), K)
    np.save(kp, N); del ix
log("exact 10-NN done")

def clustering(G):
    cc = np.empty(len(G), np.float32)
    for s in range(0, len(G), 100_000):
        g = G[s:s + 100_000]; A = G[g]                    # (b, K, K): neighbours of each neighbour
        E = (A[:, :, None, :] == g[:, None, :, None]).any(-1)   # E[p,i,j]: g[p,j] in N(g[p,i])
        cc[s:s + len(g)] = E.sum((1, 2)) / (K * (K - 1))
    return cc
cc = clustering(N); log(f"oracle cc: mean {cc.mean():.3f} q10 {np.quantile(cc,.1):.3f} frac0 {np.mean(cc==0):.3f}")

# ---- leaders (Lloyd, as fg: 10 iterations on a 200k sample) ---------------
def nearest(Q, C, m, b=16384):
    c2 = (C ** 2).sum(1); ids = np.empty((len(Q), m), np.int32); ds = np.empty((len(Q), m), np.float32)
    for s in range(0, len(Q), b):
        q = Q[s:s + b]; D = -2.0 * (q @ C.T) + c2[None, :]
        p = np.argpartition(D, m - 1, axis=1)[:, :m]; dd = np.take_along_axis(D, p, 1); o = np.argsort(dd, 1)
        ids[s:s + b] = np.take_along_axis(p, o, 1); ds[s:s + b] = np.take_along_axis(dd, o, 1) + (q ** 2).sum(1)[:, None]
    return ids, np.sqrt(np.maximum(ds, 0))
rng = np.random.default_rng(1); smp = X[rng.choice(n, min(n, 200_000), replace=False)]; C = smp[:L].copy()
for _ in range(10):
    a = nearest(smp, C, 1)[0][:, 0]
    for l in range(L):
        msk = a == l
        if msk.any(): C[l] = smp[msk].mean(0)
top, tdist = nearest(X, C, MMAX); log("leaders + memberships done")
margin = tdist[:, 0] / np.maximum(tdist[:, 1], 1e-30)    # -> 1 at a boundary

# ---- pilot proxy: approximate 10-NN from the m=2 leaves, then cc -----------
cid = np.full((n, 2 * (K + 1)), -1, np.int64); cdd = np.full((n, 2 * (K + 1)), np.inf, np.float32)
x2 = (X ** 2).sum(1)
for l in range(L):
    mem = np.nonzero((top[:, 0] == l) | (top[:, 1] == l))[0]
    if len(mem) < 2: continue
    slot = np.where(top[mem, 0] == l, 0, 1)
    for s in range(0, len(mem), 8192):
        r = mem[s:s + 8192]
        D = x2[r][:, None] - 2.0 * (X[r] @ X[mem].T) + x2[mem][None, :]
        D[np.arange(len(r)), np.arange(s, s + len(r))] = np.inf
        kk = min(K + 1, len(mem) - 1)
        p = np.argpartition(D, kk - 1, axis=1)[:, :kk]
        off = slot[s:s + len(r)] * (K + 1)
        cols = off[:, None] + np.arange(kk)[None, :]
        cid[r[:, None], cols] = mem[p]; cdd[r[:, None], cols] = np.take_along_axis(D, p, 1)
Np = np.empty((n, K), np.int32)
for s in range(0, n, 200_000):
    ii = cid[s:s + 200_000]; dd = cdd[s:s + 200_000].copy()
    o = np.argsort(dd, 1); ii = np.take_along_axis(ii, o, 1); dd = np.take_along_axis(dd, o, 1)
    dup = np.zeros_like(ii, bool); dup[:, 1:] = ii[:, 1:] == ii[:, :-1]     # same id twice (both leaves) -> equal distance, adjacent
    dd[dup | (ii < 0)] = np.inf; o = np.argsort(dd, 1, kind="stable")[:, :K]
    Np[s:s + len(ii)] = np.take_along_axis(ii, o, 1)
cc_pilot = clustering(Np)
pilot_rec = np.mean([len(set(a) & set(b)) / K for a, b in zip(N[:5000].tolist(), Np[:5000].tolist())])
log(f"pilot graph recall@10 {pilot_rec:.3f}; spearman(cc, cc_pilot) {np.corrcoef(np.argsort(np.argsort(cc)), np.argsort(np.argsort(cc_pilot)))[0,1]:.3f}")

# ---- frontier on sampled true pairs -----------------------------------------
P = np.sort(np.random.default_rng(SEED).choice(n, NS, replace=False)); px = np.repeat(P, K); py = N[P].ravel()
tx, ty = top[px], top[py]
def evaluate(mv):
    leaf = np.zeros(L, np.int64)
    for j in range(MMAX):
        leaf += np.bincount(top[mv > j, j], minlength=L)
    ax = np.where(np.arange(MMAX)[None, :] < mv[px][:, None], tx, -1)
    ay = np.where(np.arange(MMAX)[None, :] < mv[py][:, None], ty, -2)
    cov = (ax[:, :, None] == ay[:, None, :]).any((1, 2)).mean()
    return cov, (leaf.astype(np.float64) ** 2).sum() / 2 / 1e9
uni = {m: evaluate(np.full(n, m, np.uint8)) for m in range(1, MMAX + 1)}
for m, (c, p) in uni.items(): log(f"uniform m={m:2d}: cover {c:.4f}  pairs {p:7.2f} G")
c0, p0 = uni[5]
hard = {"oracle": -cc, "pilot": -cc_pilot, "margin": margin}
with open(f"{out}_policies.txt", "w") as fo:
    for name, h in hard.items():
        rk = np.argsort(np.argsort(-h, kind="stable"), kind="stable") / n     # 0 = hardest
        res = []
        for f in (0.05, 0.1, 0.2, 0.3, 0.5):
            for lo in (1, 2, 3, 4):
                for hi in range(lo + 1, MMAX + 1):
                    mv = np.where(rk < f, hi, lo).astype(np.uint8); c, p = evaluate(mv)
                    res.append((f, lo, hi, c, p, mv.mean()))
        A = max((r for r in res if r[4] <= p0), key=lambda r: r[3], default=None)
        B = min((r for r in res if r[3] >= c0), key=lambda r: r[4], default=None)
        for tag, r in (("A", A), ("B", B)):
            if r is None: log(f"{name} {tag}: none"); continue
            f, lo, hi, c, p, mm = r
            np.where(rk < f, hi, lo).astype(np.uint8).tofile(f"{out}_{name}_{tag}.u8")
            line = (f"{name} {tag}: f={f} m_lo={lo} m_hi={hi} (mean m {mm:.2f})  cover {c:.4f} (uniform m5 {c0:.4f})  "
                    f"pairs {p:.2f} G (uniform m5 {p0:.2f})")
            log(line); fo.write(line + "\n")
log("done")
