#!/usr/bin/env python3
"""Warm-started k-means for the leaves (author, 2026-09-29): does the
initialisation change the cells' recall per pool, and how many Lloyd
iterations does each start need? Numpy replica of fg's Lloyd (sample of
200k, L leaders, m memberships; reproduces fg's pair count at 10 it.).
Inits: fg's (first L sample points), k-means++, HSP-smoothed (each witness
replaced by the centroid of itself + its HSP neighbours; 1 and 2 hops).
Metric: recall of true-neighbour pairs inside the symmetric m-leaves, the
pool, the pair count (sum leaf^2/2) and the largest leaf, at 0..10 iterations.
"""
import numpy as np, sys, time
sys.path.insert(0, "bench")
X = np.ascontiguousarray(np.load("/Users/elchavez/code/claude/sat-forest/data/gist_X.npy"), np.float32); n, d = X.shape
L, m, NS = 700, 5, 200_000
src = np.sort(np.random.default_rng(0).choice(n, 1000, replace=False)); Xs = X[src]
D = np.empty((1000, n), np.float32); q2 = (Xs ** 2).sum(1)[:, None]
for s in range(0, n, 100_000):
    B = X[s:s + 100_000]; D[:, s:s + 100_000] = q2 - 2.0 * (Xs @ B.T) + (B ** 2).sum(1)[None, :]
D[np.arange(1000), src] = np.inf; nn = np.argpartition(D, 9, axis=1)[:, :10]; del D
px = np.repeat(src, 10); py = nn.ravel()
rng = np.random.default_rng(1); samp = rng.choice(n, NS, replace=False); Q = X[samp]
def assign(C, P, k):
    c2 = (C ** 2).sum(1); ids = np.empty((len(P), k), np.int32)
    for s in range(0, len(P), 8192):
        q = P[s:s+8192]; Dd = (q**2).sum(1)[:, None] - 2.0 * (q @ C.T) + c2[None, :]
        if k == 1: ids[s:s+8192, 0] = Dd.argmin(1)
        else:
            p = np.argpartition(Dd, k - 1, axis=1)[:, :k]; o = np.argsort(np.take_along_axis(Dd, p, 1), 1); ids[s:s+8192] = np.take_along_axis(p, o, 1)
    return ids
def lloyd_step(C):
    a = assign(C, Q, 1)[:, 0]; Cn = C.copy()
    for l in range(L):
        mk = a == l
        if mk.any(): Cn[l] = Q[mk].mean(0)
    return Cn
def evaluate(C):
    top = assign(C, X, m); leaf = np.zeros(L, np.int64)
    for j in range(m): leaf += np.bincount(top[:, j], minlength=L)
    tx, ty = top[px], top[py]
    sym = np.array([len(set(a) & set(b)) > 0 for a, b in zip(tx, ty)])
    pool = leaf[tx].sum(1).mean() / 1e3; pairs = (leaf.astype(np.float64)**2).sum() / 2 / 1e9
    return sym.mean(), pool, pairs, leaf.max()
def kpp(seed=1):
    r = np.random.default_rng(seed); C = [Q[r.integers(NS)]]; d2 = ((Q - C[0])**2).sum(1)
    for _ in range(L - 1):
        i = r.choice(NS, p=d2 / d2.sum()); C.append(Q[i]); d2 = np.minimum(d2, ((Q - Q[i])**2).sum(1))
    return np.array(C, np.float32)
def hsp_smooth(W, hops):
    w2 = (W ** 2).sum(1); DW = np.sqrt(np.maximum(w2[:, None] - 2.0 * (W @ W.T) + w2[None, :], 0)); np.fill_diagonal(DW, np.inf)
    nb = []
    for p in range(L):
        kept = []
        for u in np.argsort(DW[p]):
            if not np.isfinite(DW[p, u]): continue
            if all(DW[v, u] >= DW[p, u] for v in kept): kept.append(u)
        nb.append(set(kept))
    nbs = [nb[p] | {q for q in range(L) if p in nb[q]} for p in range(L)]
    if hops == 2: nbs = [set().union(*[nbs[q] for q in nbs[p]]) | nbs[p] for p in range(L)]
    return np.array([W[[p] + sorted(nbs[p])].mean(0) for p in range(L)], np.float32), np.mean([len(s) for s in nbs])
W0 = Q[:L].copy()   # fg's init: the first L sample points
inits = {"fg (random sample points)": W0, "k-means++": kpp()}
for h in (1, 2):
    C, dg = hsp_smooth(W0, h); inits[f"HSP-smoothed, {h} hop (deg {dg:.0f})"] = C
print(f"L={L} m={m}, symmetric leaves; columns: it -> recall @ pool | pairs G | max leaf")
for name, C0 in inits.items():
    C = C0.copy(); row = f"{name:<34}"; t = time.time()
    for it in range(0, 11):
        if it in (0, 1, 2, 3, 5, 10):
            r, p, g, mx = evaluate(C); row += f" {it:>2}: {r:.3f}@{p:.0f}k|{g:.1f}G|{mx//1000:.0f}k"
        if it < 10: C = lloyd_step(C)
    print(row, f"({time.time()-t:.0f}s)", flush=True)
