#!/usr/bin/env python3
"""Write initial leaders for fg --dense-leaders-file: L random points (seed)
and their HSP-smoothed version (each replaced by the mean of itself and its
HSP neighbours, 1 hop). Raw float32 L x d."""
import numpy as np, sys
data, L, seed, out = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), sys.argv[4]
X = np.load(data, mmap_mode="r"); n, d = X.shape
idx = np.sort(np.random.default_rng(seed).choice(n, L, replace=False)); W = np.ascontiguousarray(X[idx], np.float32)
w2 = (W ** 2).sum(1); DW = np.sqrt(np.maximum(w2[:, None] - 2.0 * (W @ W.T) + w2[None, :], 0)); np.fill_diagonal(DW, np.inf)
nb = []
for p in range(L):
    kept = []
    for u in np.argsort(DW[p]):
        if not np.isfinite(DW[p, u]): continue
        if all(DW[v, u] >= DW[p, u] for v in kept): kept.append(u)
    nb.append(set(kept))
nbs = [nb[p] | {q for q in range(L) if p in nb[q]} for p in range(L)]
Ws = np.array([W[[p] + sorted(nbs[p])].mean(0) for p in range(L)], np.float32)
W.tofile(f"{out}_random_L{L}.f32"); Ws.tofile(f"{out}_hsp1_L{L}.f32")
print(f"L={L} d={d}: HSP degree mean {np.mean([len(s) for s in nbs]):.1f}; wrote {out}_random_L{L}.f32 and {out}_hsp1_L{L}.f32")
