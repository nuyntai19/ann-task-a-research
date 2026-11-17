#!/usr/bin/env python3
"""Edge diagnostic for dumped fg graphs: how far do the edges reach?

For a seeded sample of source nodes, every out-edge p->q gets the rank of q
in p's exact nearest-neighbour order over the whole base and the ratio
d(p,q) / d(p, 10th-NN). Reports the rank histogram and distance ratios per
graph, so two graphs of equal completeness can be compared on edge reach.

    python3 edge_diag.py --data gist_X.npy --sample 1000 g1.graph g2.graph ...
"""
import argparse, numpy as np, time

def load_graph(path):
    with open(path, "rb") as f:
        n, maxdeg = np.fromfile(f, np.uint32, 2); sizes = np.fromfile(f, np.uint32, n)
        flat = np.fromfile(f, np.uint32)
    off = np.zeros(n + 1, np.int64); off[1:] = np.cumsum(sizes)
    assert off[-1] == flat.size, (off[-1], flat.size)
    return int(n), int(maxdeg), sizes, off, flat

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("graphs", nargs="+"); ap.add_argument("--data", required=True)
    ap.add_argument("--sample", type=int, default=1000); ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args()
    X = np.load(a.data, mmap_mode="r"); n = X.shape[0]
    src = np.sort(np.random.default_rng(a.seed).choice(n, a.sample, replace=False))
    Xs = np.ascontiguousarray(X[src], np.float32); Xn2 = None
    t = time.time(); ranks_all = {}; ratio_all = {}
    # exact distances from the sample sources to the whole base, blocked
    D = np.empty((a.sample, n), np.float32); q2 = (Xs ** 2).sum(1)[:, None]
    for s in range(0, n, 100_000):
        B = np.ascontiguousarray(X[s:s + 100_000], np.float32)
        D[:, s:s + 100_000] = q2 - 2.0 * (Xs @ B.T) + (B ** 2).sum(1)[None, :]
    D[np.arange(a.sample), src] = np.inf
    order = np.argsort(D, axis=1); rank = np.empty_like(order); rank[np.arange(a.sample)[:, None], order] = np.arange(n)[None, :]
    d10 = np.sqrt(np.maximum(D[np.arange(a.sample), order[:, 9]], 0))
    print(f"exact ranks for {a.sample} sources: {time.time()-t:.0f}s")
    bins = [1, 10, 30, 100, 300, 1000, 3000, 10000, 30000, 100000, n]
    print(f"{'graph':<32}{'deg':>6}{'r<=10':>7}{'<=100':>7}{'<=1k':>7}{'<=10k':>7}{'>10k':>7}{'>100k':>7}  d/d10: p50   p90   p99   max   | true10 covered")
    for g in a.graphs:
        n_g, maxdeg, sizes, off, flat = load_graph(g)
        rk = []; ra = []; cov = 0
        for i, p in enumerate(src):
            nb = flat[off[p]:off[p + 1]].astype(np.int64)
            r = rank[i, nb]; rk.append(r); ra.append(np.sqrt(np.maximum(D[i, nb], 0)) / max(d10[i], 1e-12))
            cov += np.isin(order[i, :10], nb).sum()
        rk = np.concatenate(rk); ra = np.concatenate(ra); m = rk.size
        h = lambda lo, hi: np.mean((rk >= lo) & (rk < hi))
        print(f"{g.split('/')[-1]:<32}{m/a.sample:6.1f}{h(0,10):7.3f}{h(0,100):7.3f}{h(0,1000):7.3f}{h(0,10000):7.3f}{h(10000,n):7.3f}{h(100000,n):7.3f}"
              f"  {np.percentile(ra,50):6.2f}{np.percentile(ra,90):6.2f}{np.percentile(ra,99):6.2f}{ra.max():6.2f}   | {cov/(10*a.sample):.3f}")

if __name__ == "__main__":
    main()
