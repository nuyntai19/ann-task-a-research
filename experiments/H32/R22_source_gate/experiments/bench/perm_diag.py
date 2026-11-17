#!/usr/bin/env python3
"""Fragility of the permutant order, and coverage by L independent partitions.

For a seeded sample of base points and their exact 10-NN (GEMM over the
whole base): the share of neighbour pairs sharing the first permutant and
the first two, the mean Spearman footrule between their k-permutations, and
the coverage curve -- the share of neighbour pairs that fall in the same
size-capped trie block in at least one of L independent permutant sets.

    python perm_diag.py --data X.npy --S 1000 --k 8 --B 1000 --lmax 4 --tables 10 --sample 1000
"""
import argparse, time, numpy as np, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from perm_cands import permutations, trie_cut

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True); ap.add_argument("--S", type=int, default=1000); ap.add_argument("--k", type=int, default=8)
    ap.add_argument("--B", type=int, default=1000); ap.add_argument("--Bmin", type=int, default=100); ap.add_argument("--lmax", type=int, default=4)
    ap.add_argument("--tables", type=int, default=10); ap.add_argument("--sample", type=int, default=1000); ap.add_argument("--knn", type=int, default=10)
    a = ap.parse_args()
    X = np.ascontiguousarray(np.load(a.data), np.float32); n, d = X.shape
    src = np.sort(np.random.default_rng(0).choice(n, a.sample, replace=False)); Xs = X[src]
    t = time.time(); D = np.empty((a.sample, n), np.float32); q2 = (Xs ** 2).sum(1)[:, None]
    for s in range(0, n, 100_000):
        B_ = X[s:s + 100_000]; D[:, s:s + 100_000] = q2 - 2.0 * (Xs @ B_.T) + (B_ ** 2).sum(1)[None, :]
    D[np.arange(a.sample), src] = np.inf
    nn = np.argpartition(D, a.knn - 1, axis=1)[:, :a.knn]           # exact 10-NN per source
    print(f"exact {a.knn}-NN of {a.sample} points: {time.time()-t:.0f}s", flush=True)
    pairs_x = np.repeat(src, a.knn); pairs_y = nn.ravel()
    cov_any = np.zeros(len(pairs_x), bool); cov_curve = []
    for tbl in range(a.tables):
        rng = np.random.default_rng(1 + tbl); P = np.sort(rng.choice(n, size=a.S, replace=False))
        sig = permutations(X, P, a.k)
        if tbl == 0:
            same1 = (sig[pairs_x, 0] == sig[pairs_y, 0]).mean()
            same2 = ((sig[pairs_x, 0] == sig[pairs_y, 0]) & (sig[pairs_x, 1] == sig[pairs_y, 1])).mean()
            # footrule between k-permutations: sum over permutants in x's list of |pos_x - pos_y|, pos_y = k if absent
            fr = []
            for x, y in zip(pairs_x[:5000], pairs_y[:5000]):
                px, py = sig[x], sig[y]; posy = {p: i for i, p in enumerate(py)}
                fr.append(sum(abs(i - posy.get(p, a.k)) for i, p in enumerate(px)))
            print(f"table 0: P(same first permutant)={same1:.3f}  P(same 2-prefix)={same2:.3f}  "
                  f"footrule(k={a.k}) mean {np.mean(fr):.1f} (max {a.k*a.k}); shared permutants mean "
                  f"{np.mean([len(set(sig[x]) & set(sig[y])) for x, y in zip(pairs_x[:5000], pairs_y[:5000])]):.2f} of {a.k}", flush=True)
        assigned, nb, _, _, _ = trie_cut(sig, a.S, a.B, a.lmax, a.Bmin)
        sizes = np.bincount(assigned, minlength=nb)
        same_block = assigned[pairs_x] == assigned[pairs_y]
        cov_any |= same_block; cov_curve.append(cov_any.mean())
        print(f"table {tbl}: blocks {nb} (median {np.median(sizes):.0f}, max {sizes.max()}), pairs/2 {(sizes.astype(np.float64)**2).sum()/2/1e9:.2f} G; "
              f"same-block share {same_block.mean():.3f}; coverage by best of {tbl+1} tables {cov_any.mean():.3f}", flush=True)
    print("coverage curve:", " ".join(f"L{i+1}={c:.3f}" for i, c in enumerate(cov_curve)))
    print("independence would give:", " ".join(f"L{i+1}={1-(1-cov_curve[0])**(i+1):.3f}" for i in range(a.tables)))

if __name__ == "__main__":
    main()
