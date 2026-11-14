#!/usr/bin/env python3
"""HSP-enlarged Lloyd (author, 2026-09-29): each round = HSP on the current
leaders -> assign the sample to nearest leader -> enlarged cell = own cell +
the cells of the leader's HSP neighbours -> new center = mean of the
enlarged cell's points. Compared with plain Lloyd round by round (L 700,
m 5, symmetric leaves; recall of true-neighbour pairs @ pool, pairs, max leaf).
"""
import numpy as np, sys
sys.path.insert(0, "bench")
exec(open("bench/kmeans_init_diag.py").read().split("W0 = Q[:L].copy()")[0])   # data, assign, lloyd_step, evaluate, hsp neighbourhoods
def hsp_nbrs(W, sym=True):
    w2 = (W ** 2).sum(1); DW = np.sqrt(np.maximum(w2[:, None] - 2.0 * (W @ W.T) + w2[None, :], 0)); np.fill_diagonal(DW, np.inf)
    nb = []
    for p in range(L):
        kept = []
        for u in np.argsort(DW[p]):
            if not np.isfinite(DW[p, u]): continue
            if all(DW[v, u] >= DW[p, u] for v in kept): kept.append(u)
        nb.append(set(kept))
    return [nb[p] | {q for q in range(L) if p in nb[q]} for p in range(L)] if sym else nb
def enlarged_step(C, sym):
    a = assign(C, Q, 1)[:, 0]; nbs = hsp_nbrs(C, sym); Cn = C.copy()
    members = [np.nonzero(a == l)[0] for l in range(L)]
    for l in range(L):
        idx = np.concatenate([members[l]] + [members[q] for q in nbs[l]])
        if len(idx): Cn[l] = Q[idx].mean(0)
    return Cn, np.mean([len(s) for s in nbs])
W0 = Q[:L].copy()
print(f"{'round':<6}{'plain Lloyd':<34}{'HSP-enlarged Lloyd (directed)':<34}{'HSP-enlarged Lloyd (symmetric)':<34}")
Cl, Cd, Cs = W0.copy(), W0.copy(), W0.copy()
for r in range(0, 8):
    if r > 0:
        Cl = lloyd_step(Cl); Cd, dd = enlarged_step(Cd, False); Cs, ds = enlarged_step(Cs, True)
    out = [evaluate(C) for C in (Cl, Cd, Cs)]
    print(f"{r:<6}" + "".join(f"{rec:.3f}@{p:.0f}k|{g:.1f}G|{mx//1000}k{'':<12}" for rec, p, g, mx in out), flush=True)
