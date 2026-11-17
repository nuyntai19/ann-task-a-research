import numpy as np, time, sys
sys.path.insert(0, "bench")
from cell_adjacency_diag import permutations
X = np.ascontiguousarray(np.load("/Users/elchavez/code/claude/sat-forest/data/gist_X.npy"), np.float32); n, d = X.shape
src = np.sort(np.random.default_rng(0).choice(n, 1000, replace=False)); Xs = X[src]
D = np.empty((1000, n), np.float32); q2 = (Xs ** 2).sum(1)[:, None]
for s in range(0, n, 100_000):
    B = X[s:s + 100_000]; D[:, s:s + 100_000] = q2 - 2.0 * (Xs @ B.T) + (B ** 2).sum(1)[None, :]
D[np.arange(1000), src] = np.inf; nn = np.argpartition(D, 9, axis=1)[:, :10]; del D
px = np.repeat(src, 10); py = nn.ravel()
def lloyd(L, iters=10, ns=200_000, seed=1):
    rng = np.random.default_rng(seed); samp = rng.choice(n, ns, replace=False); C = X[samp[:L]].copy()
    for _ in range(iters):
        ids = permutations(X[samp], np.arange(L), 1, block=8192) if False else None
        Q = X[samp]; c2 = (C ** 2).sum(1); a = np.empty(ns, np.int32)
        for s in range(0, ns, 8192):
            q = Q[s:s+8192]; Dd = (q**2).sum(1)[:, None] - 2.0 * (q @ C.T) + c2[None, :]; a[s:s+8192] = Dd.argmin(1)
        for l in range(L):
            m = a == l
            if m.any(): C[l] = Q[m].mean(0)
    return C
def nearest_leaders(C, m):
    c2 = (C ** 2).sum(1); ids = np.empty((n, m), np.int32)
    for s in range(0, n, 8192):
        q = X[s:s+8192]; Dd = (q**2).sum(1)[:, None] - 2.0 * (q @ C.T) + c2[None, :]
        p = np.argpartition(Dd, m - 1, axis=1)[:, :m]; o = np.argsort(np.take_along_axis(Dd, p, 1), 1); ids[s:s+8192] = np.take_along_axis(p, o, 1)
    return ids
def report(name, top, m, L):
    top = top[:, :m]; leaf = np.zeros(L, np.int64)
    for j in range(m): leaf += np.bincount(top[:, j], minlength=L)          # leaf sizes (multi-membership)
    cell = np.bincount(top[:, 0], minlength=L)                                # primary cells
    sym = np.array([len(set(top[x]) & set(top[y])) > 0 for x, y in zip(px, py)])
    one = (top[px] == top[py, 0][:, None]).any(1)                             # y's primary cell among x's m
    pool_sym = leaf[top[px]].sum(1); pool_one = cell[top[px]].sum(1)
    pairs_sym = (leaf.astype(np.float64)**2).sum()/2; pairs_one = (leaf.astype(np.float64) * cell).sum()
    print(f"{name:<34} symmetric leaves: cover {sym.mean():.3f} pool {pool_sym.mean()/1e3:.0f}k pairs {pairs_sym/1e9:.1f} G | one-sided (citers x cell): cover {one.mean():.3f} pool {pool_one.mean()/1e3:.0f}k pairs {pairs_one/1e9:.1f} G", flush=True)
t = time.time(); C = lloyd(700); topk = nearest_leaders(C, 15); print(f"k-means L700 (10 Lloyd it.): {time.time()-t:.0f}s")
report("k-means L700, m=5 (paper)", topk, 5, 700)
report("k-means L700, m=10", topk, 10, 700)
report("k-means L700, m=15", topk, 15, 700)
Pr = np.sort(np.random.default_rng(1).choice(n, 1000, replace=False)); topr = permutations(X, Pr, 16)
for m in (5, 10, 15): report(f"random L1000, m={m}", topr, m, 1000)
