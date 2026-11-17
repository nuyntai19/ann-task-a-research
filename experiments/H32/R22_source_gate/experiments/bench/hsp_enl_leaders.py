#!/usr/bin/env python3
"""Initial leaders for fg --dense-leaders-file: (a) HSP-smoothed once (each of
L random points replaced by the mean of itself + its HSP neighbours) and
(b) r rounds of HSP-enlarged Lloyd (center = mean of the data of own cell +
HSP-neighbour cells, on a 200k sample). Cosine corpora: centers normalised.
    python hsp_enl_leaders.py X.npy L rounds metric out_prefix [seed]
"""
import numpy as np, sys, time
data, L, rounds, metric, out = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), sys.argv[4], sys.argv[5]
seed = int(sys.argv[6]) if len(sys.argv) > 6 else 1
X = np.load(data, mmap_mode="r"); n, d = X.shape; rng = np.random.default_rng(seed)
samp = np.sort(rng.choice(n, min(n, 200_000), replace=False)); Q = np.ascontiguousarray(X[samp], np.float32)
W = Q[:L].copy()
def norm(C): return C / np.maximum(np.linalg.norm(C, axis=1, keepdims=True), 1e-12) if metric == "cosine" else C
def hsp_nbrs(C):
    c2 = (C ** 2).sum(1); DW = np.sqrt(np.maximum(c2[:, None] - 2.0 * (C @ C.T) + c2[None, :], 0)); np.fill_diagonal(DW, np.inf)
    nb = []
    for p in range(L):
        kept = []
        for u in np.argsort(DW[p]):
            if not np.isfinite(DW[p, u]): continue
            if all(DW[v, u] >= DW[p, u] for v in kept): kept.append(u)
        nb.append(kept)
    return nb
t = time.time(); nb = hsp_nbrs(W)
Ws = norm(np.array([W[[p] + nb[p]].mean(0) for p in range(L)], np.float32)); Ws.tofile(f"{out}_hsp1_L{L}.f32")
print(f"{data}: n={n} d={d} L={L} HSP deg {np.mean([len(x) for x in nb]):.1f}; smoothed leaders written ({time.time()-t:.0f}s)", flush=True)
C = W.copy(); c2q = (Q ** 2).sum(1)
for r in range(rounds):
    nb = hsp_nbrs(C); cc = (C ** 2).sum(1); a = np.empty(len(Q), np.int32)
    for s in range(0, len(Q), 8192):
        q = Q[s:s+8192]; a[s:s+8192] = (c2q[s:s+8192, None] - 2.0 * (q @ C.T) + cc[None, :]).argmin(1)
    members = [np.nonzero(a == l)[0] for l in range(L)]; Cn = C.copy()
    for l in range(L):
        idx = np.concatenate([members[l]] + [members[q] for q in nb[l]])
        if len(idx): Cn[l] = Q[idx].mean(0)
    C = norm(Cn)
C.astype(np.float32).tofile(f"{out}_enl{rounds}_L{L}.f32")
print(f"  enlarged-Lloyd {rounds} rounds written ({time.time()-t:.0f}s)", flush=True)
