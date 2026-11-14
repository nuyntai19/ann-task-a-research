import numpy as np, time, sys
sys.path.insert(0, "bench")
from cell_adjacency_diag import permutations
X = np.ascontiguousarray(np.load("/Users/elchavez/code/claude/sat-forest/data/gist_X.npy"), np.float32); n, d = X.shape; S = 1000
P = np.sort(np.random.default_rng(1).choice(n, S, replace=False)); sig = permutations(X, P, 16)
src = np.sort(np.random.default_rng(0).choice(n, 1000, replace=False)); Xs = X[src]
D = np.empty((1000, n), np.float32); q2 = (Xs ** 2).sum(1)[:, None]
for s in range(0, n, 100_000):
    B = X[s:s + 100_000]; D[:, s:s + 100_000] = q2 - 2.0 * (Xs @ B.T) + (B ** 2).sum(1)[None, :]
D[np.arange(1000), src] = np.inf; nn = np.argpartition(D, 9, axis=1)[:, :10]; del D
cell = sig[:, 0]; size = np.bincount(cell, minlength=S).astype(np.float64)
px = np.repeat(src, 10); py = nn.ravel(); cx, cy = cell[px], cell[py]
def adjacency(orders):   # citation matrix from 2nd (and 3rd...) nearest permutants
    W = np.zeros((S, S), np.float64)
    for j in orders: np.add.at(W, (sig[:, 0], sig[:, j]), 1)
    np.fill_diagonal(W, 0); return W
def report(name, W):
    for norm, lab in ((np.ones(S), "raw count"), (size, "count / |q|"), (np.sqrt(size), "count / sqrt|q|")):
        R = W / norm[None, :]; order = np.argsort(-R, axis=1)
        row = f"{name:<22}{lab:<16}"
        for m in (5, 10, 20, 50):
            top = order[:, :m]; inA = (cy == cx) | (top[cx] == cy[:, None]).any(1); pool = size[cx] + size[top[cx]].sum(1)
            row += f" m={m}: {inA.mean():.3f}@{pool.mean()/1e3:.0f}k"
        print(row, flush=True)
print(f"{'adjacency':<22}{'ranking':<16} coverage@pool (own cell + top-m adjacent cells)")
report("2nd nearest", adjacency([1]))
report("2nd+3rd nearest", adjacency([1, 2]))
report("2nd..5th nearest", adjacency([1, 2, 3, 4]))
# symmetric mutual adjacency (edge weight = W+W^T), rate-normalised
W = adjacency([1]); Wsym = W + W.T
report("2nd, symmetric", Wsym)
print("reference, point level (own + m nearest permutants):", " ".join(f"m={m}: {((sig[px, :m + 1] == cy[:, None]).any(1)).mean():.3f}@{size[sig[px, :m + 1]].sum(1).mean()/1e3:.0f}k" for m in (5, 10, 15)))
