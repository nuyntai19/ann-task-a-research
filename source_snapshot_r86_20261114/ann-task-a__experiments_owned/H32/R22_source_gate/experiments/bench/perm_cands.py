#!/usr/bin/env python3
"""Permutation-prefix trie partition for the dense construction (author, 2026-09-29).

Every object's k-permutation (its k nearest permutants, in order; exact by
GEMM) is inserted in a prefix trie; the trie is cut where a subtree has at
most B objects (hub cells split by the next permutant, small cells stay
whole), and the cut subtrees are the blocks. Memberships: the object's own
block plus the blocks reached by the adjacent-swap variants of its prefix
(PP-Index's footrule neighbours), `--swaps` of them. Candidate rows = the
union of the members of an object's blocks (n x C int32, -1 padded, self
removed) for `fg --dense-cands ... --harvest-cand 200`. Reports the block
size distribution, sum(block^2)/2 (the GEMM cost) and the effective pool.

    python perm_cands.py --data X.npy --S 1000 --k 8 --B 1000 --lmax 4 --swaps 3 --C 4000 --out prefix
"""
import argparse, time, numpy as np


def permutations(X, P, k, block=8192):
    Ps = np.ascontiguousarray(X[P], np.float32); n2 = (Ps ** 2).sum(1)
    ids = np.empty((len(X), k), np.int32)
    for a in range(0, len(X), block):
        q = X[a:a + block]
        D = (q ** 2).sum(1)[:, None] - 2.0 * (q @ Ps.T) + n2[None, :]
        p = np.argpartition(D, k - 1, axis=1)[:, :k]
        o = np.argsort(np.take_along_axis(D, p, 1), 1)
        ids[a:a + block] = np.take_along_axis(p, o, 1)
    return ids


def trie_cut(sig, S, B, lmax, Bmin):
    """Cut the prefix trie: a subtree of <= B objects is a block; a subtree
    larger than B is split by the next permutant, and its children smaller
    than Bmin are merged into one residual block (key = parent*(S+1) + S)."""
    n = len(sig); assigned = np.full(n, -1, np.int64); key = np.zeros(n, np.int64)
    active = np.arange(n); nb = 0; bkeys, bids, depth_of = {}, {}, []
    R = S + 1                                                # radix: S permutants + residual symbol S
    for d in range(1, lmax + 1):
        key[active] = key[active] * R + sig[active, d - 1]
        if d > 1:                                            # merge tiny children into the parent's residual
            u, inv, cnt = np.unique(key[active], return_inverse=True, return_counts=True)
            tiny = (cnt < Bmin)[inv]
            key[active[tiny]] = (key[active[tiny]] // R) * R + S
        u, inv, cnt = np.unique(key[active], return_inverse=True, return_counts=True)
        isb = (cnt <= B) | (d == lmax) | ((u % R) == S)
        ids = np.full(len(u), -1, np.int64); ids[isb] = nb + np.arange(int(isb.sum()))
        sel = isb[inv]; assigned[active[sel]] = ids[inv[sel]]
        bkeys[d] = u[isb]; bids[d] = ids[isb]; depth_of += [d] * int(isb.sum()); nb += int(isb.sum())
        active = active[~sel]
        if len(active) == 0: break
    assert (assigned >= 0).all()
    return assigned, nb, bkeys, bids, np.array(depth_of)


def lookup(sigv, S, lmax, bkeys, bids):
    """Block of a (variant) permutation: the first depth at which its prefix,
    or its parent's residual, is a block."""
    n = len(sigv); found = np.full(n, -1, np.int64); key = np.zeros(n, np.int64); R = S + 1
    for d in range(1, lmax + 1):
        key = key * R + sigv[:, d - 1]
        if d not in bkeys or len(bkeys[d]) == 0: continue
        for probe in (key, (key // R) * R + S):
            pos = np.minimum(np.searchsorted(bkeys[d], probe), len(bkeys[d]) - 1)
            hit = (bkeys[d][pos] == probe) & (found < 0)
            found[hit] = bids[d][pos[hit]]
    return found


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True); ap.add_argument("--out", required=True)
    ap.add_argument("--S", type=int, default=1000); ap.add_argument("--k", type=int, default=8)
    ap.add_argument("--B", type=int, default=1000); ap.add_argument("--Bmin", type=int, default=100); ap.add_argument("--lmax", type=int, default=4)
    ap.add_argument("--swaps", type=int, default=3); ap.add_argument("--C", type=int, default=4000)
    ap.add_argument("--seed", type=int, default=1); ap.add_argument("--sig", default=None)
    ap.add_argument("--chunk", type=int, default=20000); ap.add_argument("--tables", type=int, default=1, help="independent permutant sets; one own-block membership per table")
    a = ap.parse_args()
    X = np.ascontiguousarray(np.load(a.data), np.float32); n, d = X.shape
    rng = np.random.default_rng(a.seed); P = np.sort(rng.choice(n, size=a.S, replace=False))
    print(f"perm_cands n={n} d={d} S={a.S} k={a.k} B={a.B} Bmin={a.Bmin} lmax={a.lmax} swaps={a.swaps} C={a.C}", flush=True)
    t = time.time()
    if a.sig: sig = np.load(a.sig)[:, :a.k].astype(np.int32); print(f"  permutations reused from {a.sig}")
    else: sig = permutations(X, P, a.k); np.save(f"{a.out}_perm_S{a.S}_k{a.k}.npy", sig); print(f"  permutations: {time.time()-t:.0f}s ({n*a.S/1e9:.2f} G pairs)", flush=True)
    del X
    assert a.k >= max(a.lmax, a.swaps + 1)
    tables = []   # per table: (assigned, sizes, order, bptr)
    Mcols = []
    gpairs = 0.0
    for tbl in range(a.tables):
        if tbl > 0:
            rng_t = np.random.default_rng(a.seed + tbl); P_t = np.sort(rng_t.choice(n, size=a.S, replace=False))
            Xf = np.ascontiguousarray(np.load(a.data), np.float32); sig_t = permutations(Xf, P_t, a.k); del Xf
        else:
            sig_t = sig
        t = time.time(); assigned, nb, bkeys, bids, depth_of = trie_cut(sig_t, a.S, a.B, a.lmax, a.Bmin)
        sizes = np.bincount(assigned, minlength=nb); gpairs += (sizes.astype(np.float64)**2).sum()/2
        print(f"  table {tbl}: trie cut {nb} blocks; depth counts {np.bincount(depth_of)[1:].tolist()}; size mean {sizes.mean():.0f} median {np.median(sizes):.0f} p99 {np.percentile(sizes,99):.0f} max {sizes.max()}; pairs/2 {(sizes.astype(np.float64)**2).sum()/2/1e9:.2f} G", flush=True)
        order = np.argsort(assigned, kind="stable"); bptr = np.zeros(nb + 1, np.int64); bptr[1:] = np.cumsum(sizes)
        tables.append((sizes, order, bptr))
        cols = [assigned]
        if tbl == 0:
            for i in range(a.swaps):
                sv = sig_t.copy(); sv[:, [i, i + 1]] = sv[:, [i + 1, i]]
                cols.append(lookup(sv, a.S, a.lmax, bkeys, bids))
        Mt = np.stack(cols, 1)
        for j in range(1, Mt.shape[1]):
            for i in range(j): Mt[:, j] = np.where(Mt[:, j] == Mt[:, i], -1, Mt[:, j])
        Mcols.append((tbl, Mt))
    print(f"  all tables: sum(block^2)/2 = {gpairs/1e9:.2f} G pairs; memberships per object {sum((Mt>=0).sum(1).mean() for _, Mt in Mcols):.2f}", flush=True)
    out = np.memmap(f"{a.out}_C{a.C}.i32", dtype=np.int32, mode="w+", shape=(n, a.C))
    t = time.time(); tot_len = 0; trunc = 0
    for s in range(0, n, a.chunk):
        e = min(n, s + a.chunk); c = e - s
        rows_all, cand_all = [], []
        for tbl, Mt in Mcols:
            sizes, order, bptr = tables[tbl]
            Mc = Mt[s:e]; rows_i, bl = np.nonzero(Mc >= 0); bk = Mc[rows_i, bl]
            ln = sizes[bk]; total = int(ln.sum())
            rep_rows = np.repeat(rows_i, ln); offs = np.arange(total) - np.repeat(np.cumsum(ln) - ln, ln)
            rows_all.append(rep_rows); cand_all.append(order[np.repeat(bptr[bk], ln) + offs])
        rep_rows = np.concatenate(rows_all); cand = np.concatenate(cand_all)
        sel = cand != (rep_rows + s); rep_rows, cand = rep_rows[sel], cand[sel]
        key = np.unique(rep_rows.astype(np.int64) * n + cand)
        rr = (key // n).astype(np.int64); cc = (key % n).astype(np.int32)
        rank = np.arange(len(rr)) - np.searchsorted(rr, rr, side="left")
        buf = np.full((c, a.C), -1, np.int32); ok = rank < a.C; buf[rr[ok], rank[ok]] = cc[ok]
        lens = np.bincount(rr, minlength=c); tot_len += int(np.minimum(lens, a.C).sum()); trunc += int((lens > a.C).sum())
        out[s:e] = buf
    out.flush()
    print(f"  rows written in {time.time()-t:.0f}s: effective pool (mean row length) {tot_len/n:.0f}; rows truncated at C {trunc} ({trunc/n:.3f}); file {a.out}_C{a.C}.i32", flush=True)


if __name__ == "__main__":
    main()
