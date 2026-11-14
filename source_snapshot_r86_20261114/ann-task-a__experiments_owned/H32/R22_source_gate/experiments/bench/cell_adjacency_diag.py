#!/usr/bin/env python3
"""Enlarged Voronoi cells (author, 2026-09-29): a permutant's cell plus the
cells the data witness as adjacent -- q is adjacent to p when a point of
p's cell has q as its second-nearest permutant (the data witness the
Delaunay edges of the permutant set). For a sample of points and their
exact 10-NN: the witnessed degree of each cell, how concentrated the
citations are, and the coverage of true-neighbour pairs by
  (a) own cell + the top-m co-cited cells (cell level), against
  (b) the cells of the point's own m nearest permutants (point level),
at the pool size each implies. Runs locally on the laptop.

    python cell_adjacency_diag.py --data gist_X.npy --S 1000 --sample 1000
"""
import argparse, time, numpy as np

def permutations(X, P, k, block=8192):
    Ps = np.ascontiguousarray(X[P], np.float32); n2 = (Ps ** 2).sum(1)
    ids = np.empty((len(X), k), np.int32)
    for a in range(0, len(X), block):
        q = X[a:a + block]; D = (q ** 2).sum(1)[:, None] - 2.0 * (q @ Ps.T) + n2[None, :]
        p = np.argpartition(D, k - 1, axis=1)[:, :k]; o = np.argsort(np.take_along_axis(D, p, 1), 1)
        ids[a:a + block] = np.take_along_axis(p, o, 1)
    return ids

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--data", required=True); ap.add_argument("--S", type=int, default=1000)
    ap.add_argument("--k", type=int, default=16); ap.add_argument("--sample", type=int, default=1000); ap.add_argument("--knn", type=int, default=10)
    a = ap.parse_args(); t = time.time()
    X = np.ascontiguousarray(np.load(a.data), np.float32); n, d = X.shape
    P = np.sort(np.random.default_rng(1).choice(n, a.S, replace=False)); sig = permutations(X, P, a.k)
    print(f"n={n} d={d} S={a.S}: permutations in {time.time()-t:.0f}s", flush=True)
    src = np.sort(np.random.default_rng(0).choice(n, a.sample, replace=False)); Xs = X[src]; t = time.time()
    D = np.empty((a.sample, n), np.float32); q2 = (Xs ** 2).sum(1)[:, None]
    for s in range(0, n, 100_000):
        B = X[s:s + 100_000]; D[:, s:s + 100_000] = q2 - 2.0 * (Xs @ B.T) + (B ** 2).sum(1)[None, :]
    D[np.arange(a.sample), src] = np.inf; nn = np.argpartition(D, a.knn - 1, axis=1)[:, :a.knn]; del D
    print(f"exact {a.knn}-NN of {a.sample} points in {time.time()-t:.0f}s", flush=True)
    cell = sig[:, 0]; size = np.bincount(cell, minlength=a.S)
    # witnessed adjacency: (cell, 2nd-nearest) citations
    W = np.zeros((a.S, a.S), np.int32); np.add.at(W, (sig[:, 0], sig[:, 1]), 1); np.fill_diagonal(W, 0)
    deg = (W > 0).sum(1); tot = W.sum(1)
    order = np.argsort(-W, axis=1)                      # co-cited cells, most cited first
    cum = np.cumsum(np.take_along_axis(W, order, 1), 1) / np.maximum(tot, 1)[:, None]
    print(f"cell size mean {size.mean():.0f} median {np.median(size):.0f} max {size.max()}; witnessed degree (2nd-nearest citations): "
          f"mean {deg.mean():.0f} median {np.median(deg):.0f} min {deg.min()} max {deg.max()} of {a.S-1}; "
          f"citation share in top 5 / 10 / 20 / 50 cells: {cum[:,4].mean():.2f} / {cum[:,9].mean():.2f} / {cum[:,19].mean():.2f} / {cum[:,49].mean():.2f}", flush=True)
    px = np.repeat(src, a.knn); py = nn.ravel(); cx, cy = cell[px], cell[py]
    print(f"true-neighbour pairs: same cell {np.mean(cx == cy):.3f}")
    print(f"{'m':>4} | {'cell+top-m co-cited: cover':>28} {'pool':>7} | {'m nearest permutants: cover':>28} {'pool':>7} | {'top-m co-cited ∪ m nearest':>28} {'pool':>7}")
    for m in (1, 2, 3, 5, 10, 20, 50, 100):
        top = order[:, :m]                                                   # S x m
        inA = (cy == cx) | (top[cx] == cy[:, None]).any(1)
        poolA = size[cx] + size[top[cx]].sum(1)
        inB = (sig[px, :m + 1] == cy[:, None]).any(1)                        # own + next m nearest permutants
        poolB = size[sig[px, :m + 1]].sum(1)
        inC = inA | inB; poolC = poolA + poolB - size[cx]
        print(f"{m:>4} | {inA.mean():>28.3f} {poolA.mean():>7.0f} | {inB.mean():>28.3f} {poolB.mean():>7.0f} | {inC.mean():>28.3f} {poolC.mean():>7.0f}")

if __name__ == "__main__":
    main()
