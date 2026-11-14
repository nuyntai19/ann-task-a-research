#!/usr/bin/env python3
"""Subset-hashed localizer candidates (author, 2026-09-25): a random sample S,
each object's k nearest sample points (exact, GEMM), then every j-subset of
that k-group is a hash key; the objects colliding on a key are one local
neighbourhood (bucket). An object's candidate set is the union of its
C(k,j) buckets, filled smallest-bucket-first (the most specific keys) up to
C, written as n x C int32 (-1 padded, self removed) for `fg --dense-cands`.
j = 1 is the single-id form (`--dense-kmeans 0`); j = 2 (pairs) and j = 3
(triples) are the finer partitions with no fg flag.

    python hash_cands.py --data X.npy --alpha 0.02 --k 16 --j 2 --C 2000 \
        --out prefix [--sig sig.npy] [--stats-only]
"""
import argparse, itertools, time, numpy as np


def signatures(X, S, k, block=8192):
    Xs = np.ascontiguousarray(X[S], np.float32); n2 = (Xs ** 2).sum(1)
    ids = np.empty((len(X), k), np.uint32)
    for a in range(0, len(X), block):
        q = X[a:a + block]
        D = (q ** 2).sum(1)[:, None] - 2.0 * (q @ Xs.T) + n2[None, :]
        p = np.argpartition(D, k - 1, axis=1)[:, :k]
        o = np.argsort(np.take_along_axis(D, p, 1), 1)
        ids[a:a + block] = np.take_along_axis(p, o, 1)
    return ids


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True); ap.add_argument("--out", required=True)
    ap.add_argument("--alpha", type=float, default=0.02); ap.add_argument("--k", type=int, default=16)
    ap.add_argument("--j", type=int, default=2); ap.add_argument("--C", type=int, default=2000)
    ap.add_argument("--seed", type=int, default=1); ap.add_argument("--sig", default=None, help="signature .npy to reuse (k_sig >= k, ascending)")
    ap.add_argument("--stats-only", action="store_true"); ap.add_argument("--chunk", type=int, default=20000)
    a = ap.parse_args()
    X = np.ascontiguousarray(np.load(a.data), np.float32); n, d = X.shape
    m = int(a.alpha * n); rng = np.random.default_rng(a.seed)
    S = np.sort(rng.choice(n, size=m, replace=False))
    print(f"hash_cands n={n} d={d} |S|={m} k={a.k} j={a.j} C={a.C}", flush=True)
    t = time.time()
    if a.sig:
        sig = np.load(a.sig)[:, :a.k]; print(f"  signatures reused from {a.sig}")
    else:
        sig = signatures(X, S, a.k); np.save(f"{a.out}_sig_k{a.k}.npy", sig)
        print(f"  signatures: {time.time()-t:.0f}s ({n*m/1e9:.1f} G pairs), saved", flush=True)
    del X
    # canonical keys: sort ids within the row, then all j-subsets
    srt = np.sort(sig.astype(np.int64), axis=1)
    combos = np.array(list(itertools.combinations(range(a.k), a.j)))
    npk = len(combos)
    keys = np.zeros((n, npk), np.int64)
    for c in range(a.j):
        keys = keys * m + srt[:, combos[:, c]]
    t = time.time()
    uniq, inv, cnt = np.unique(keys.ravel(), return_inverse=True, return_counts=True)
    inv = inv.reshape(n, npk); nb = len(uniq)
    ub = (cnt[inv] - 1).sum(1)                      # per-object union upper bound (self excluded)
    print(f"  buckets: {nb} keys from {n*npk} memberships ({time.time()-t:.0f}s); size mean {cnt.mean():.1f} "
          f"median {np.median(cnt):.0f} p90 {np.percentile(cnt,90):.0f} p99 {np.percentile(cnt,99):.0f} max {cnt.max()}; "
          f"singletons {np.mean(cnt==1):.3f}", flush=True)
    print(f"  per-object union bound: mean {ub.mean():.0f} median {np.median(ub):.0f} p10 {np.percentile(ub,10):.0f} "
          f"p90 {np.percentile(ub,90):.0f} max {ub.max()}; objects with bound < C: {np.mean(ub < a.C):.3f}; "
          f"sum pairs/2 = {ub.sum()/2/1e9:.2f} G (all-pairs cost bound)", flush=True)
    if a.stats_only: return
    # bucket CSR: members of each key
    order = np.argsort(inv.ravel(), kind="stable"); bidx = (order // npk).astype(np.int32)
    bptr = np.zeros(nb + 1, np.int64); bptr[1:] = np.cumsum(cnt)
    out = np.memmap(f"{a.out}_C{a.C}.i32", dtype=np.int32, mode="w+", shape=(n, a.C))
    t = time.time(); trunc = 0; short = 0
    for s in range(0, n, a.chunk):
        e = min(n, s + a.chunk); c = e - s
        B = inv[s:e]; Sz = cnt[B]
        o = np.argsort(Sz, axis=1, kind="stable")           # smallest buckets first
        B = np.take_along_axis(B, o, 1); Sz = np.take_along_axis(Sz, o, 1)
        # expand only as many buckets as needed: cumulative size up to 4C (dedup shrinks it)
        keep = (np.cumsum(Sz, axis=1) - Sz) < 4 * a.C
        rows = np.repeat(np.arange(c), keep.sum(1)); bk = B[keep]; pos = np.cumsum(keep, axis=1)[keep] - 1
        ln = cnt[bk]; tot = int(ln.sum())
        starts = bptr[bk]; rep_rows = np.repeat(rows, ln); rep_pos = np.repeat(pos, ln)
        offs = np.arange(tot) - np.repeat(np.cumsum(ln) - ln, ln)
        cand = bidx[np.repeat(starts, ln) + offs]
        sel = cand != (rep_rows + s)                          # drop self
        rep_rows, rep_pos, cand = rep_rows[sel], rep_pos[sel], cand[sel]
        key = rep_rows.astype(np.int64) * n + cand
        o2 = np.lexsort((rep_pos, key)); key, rep_rows, rep_pos, cand = key[o2], rep_rows[o2], rep_pos[o2], cand[o2]
        first = np.ones(len(key), bool); first[1:] = key[1:] != key[:-1]   # dedup, keep most specific
        rep_rows, rep_pos, cand = rep_rows[first], rep_pos[first], cand[first]
        o3 = np.lexsort((rep_pos, rep_rows)); rep_rows, cand = rep_rows[o3], cand[o3]
        rank = np.arange(len(rep_rows)) - np.searchsorted(rep_rows, rep_rows, side="left")
        buf = np.full((c, a.C), -1, np.int32); ok = rank < a.C
        buf[rep_rows[ok], rank[ok]] = cand[ok]
        lens = np.bincount(rep_rows, minlength=c); trunc += int((lens > a.C).sum()); short += int((lens < a.C).sum())
        out[s:e] = buf
        print(f"  rows {e}/{n}  {time.time()-t:.0f}s", flush=True)
    out.flush()
    print(f"  done: rows truncated to C {trunc} ({trunc/n:.3f}), rows shorter than C {short} ({short/n:.3f}); file {a.out}_C{a.C}.i32", flush=True)


if __name__ == "__main__":
    main()
