#!/usr/bin/env python3
"""Supercells from the Half-Space Proximal graph of the witnesses (author,
2026-09-29): HSP on the permutants (alpha = 1 occlusion: process the other
witnesses nearest-first, keep u unless an already-kept v has d(v,u) < d(p,u)),
every object assigned to its nearest witness; a cell's supercell = own cell
+ the cells of its HSP neighbours (first hop; optionally second hop, or the
m nearest HSP neighbours). Coverage of true-neighbour pairs vs pool, GIST.
"""
import numpy as np, sys, time
sys.path.insert(0, "bench")
from cell_adjacency_diag import permutations
X = np.ascontiguousarray(np.load("/Users/elchavez/code/claude/sat-forest/data/gist_X.npy"), np.float32); n, d = X.shape; S = 1000
P = np.sort(np.random.default_rng(1).choice(n, S, replace=False)); W = X[P]
src = np.sort(np.random.default_rng(0).choice(n, 1000, replace=False)); Xs = X[src]
D = np.empty((1000, n), np.float32); q2 = (Xs ** 2).sum(1)[:, None]
for s in range(0, n, 100_000):
    B = X[s:s + 100_000]; D[:, s:s + 100_000] = q2 - 2.0 * (Xs @ B.T) + (B ** 2).sum(1)[None, :]
D[np.arange(1000), src] = np.inf; nn = np.argpartition(D, 9, axis=1)[:, :10]; del D
sig = permutations(X, P, 16); cell = sig[:, 0]; size = np.bincount(cell, minlength=S).astype(np.float64)
px = np.repeat(src, 10); py = nn.ravel(); cx, cy = cell[px], cell[py]
# HSP on the witnesses
w2 = (W ** 2).sum(1); DW = np.sqrt(np.maximum(w2[:, None] - 2.0 * (W @ W.T) + w2[None, :], 0)); np.fill_diagonal(DW, np.inf)
t = time.time(); hsp = []
for p in range(S):
    order = np.argsort(DW[p]); kept = []
    for u in order:
        if not np.isfinite(DW[p, u]): continue
        if all(DW[v, u] >= DW[p, u] for v in kept): kept.append(u)
    hsp.append(kept)
deg = np.array([len(h) for h in hsp])
print(f"HSP on {S} witnesses in {time.time()-t:.0f}s: degree mean {deg.mean():.1f} median {np.median(deg):.0f} min {deg.min()} max {deg.max()}  (witnessed Delaunay degree was ~93)")
adj1 = [set(h) for h in hsp]
adj1s = [adj1[p] | {q for q in range(S) if p in adj1[q]} for p in range(S)]      # symmetrised
adj2 = [set().union(*[adj1s[q] for q in adj1s[p]]) | adj1s[p] for p in range(S)]  # two hops
def cover(neigh):
    inA = np.array([(cy[i] == cx[i]) or (cy[i] in neigh[cx[i]]) for i in range(len(px))])
    pool = np.array([size[cx[i]] + sum(size[q] for q in neigh[cx[i]]) for i in range(len(px))])
    return inA.mean(), pool.mean() / 1e3
print(f"{'supercell':<40}{'coverage':>10}{'pool':>8}")
for name, neigh in (("own + HSP neighbours (directed)", adj1), ("own + HSP neighbours (symmetrised)", adj1s), ("own + HSP two hops", adj2)):
    c, p = cover(neigh); print(f"{name:<40}{c:>10.3f}{p:>7.0f}k")
for m in (5, 10, 20):   # m nearest HSP neighbours (by distance)
    neigh = [set(sorted(adj1s[p], key=lambda q: DW[p, q])[:m]) for p in range(S)]
    c, p = cover(neigh); print(f"{'own + ' + str(m) + ' nearest HSP neighbours':<40}{c:>10.3f}{p:>7.0f}k")
for m in (5, 10, 20, 50):  # reference: m nearest witnesses (no HSP), cell level
    neigh = [set(np.argsort(DW[p])[:m]) for p in range(S)]
    c, p = cover(neigh); print(f"{'own + ' + str(m) + ' nearest witnesses (cell level)':<40}{c:>10.3f}{p:>7.0f}k")
print("reference, point level (own + m nearest permutants):", " ".join(f"m={m}: {((sig[px, :m + 1] == cy[:, None]).any(1)).mean():.3f}@{size[sig[px, :m + 1]].sum(1).mean()/1e3:.0f}k" for m in (5, 10, 15)))
