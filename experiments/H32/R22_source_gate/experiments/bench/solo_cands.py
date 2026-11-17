#!/usr/bin/env python3
"""SOLO/MISIFU candidate stage for the dense construction (PLAN-SPLIT follow-up).

Sample S (|S| = alpha n, seeded), exact signatures (each object's k_b nearest
sample points, by GEMM), inverted index over S, then for every object the
count-ranked top-C objects sharing sample neighbours with it (misifu's C++
scoreboard merge, the objects' own signatures as query terms). Writes one
n x C int32 file per C (-1 padded, self removed) for `fg --dense-cands`,
which runs prune, spine and evaluation exactly as the CPU build does.

    .venv/bin/python solo_cands.py --data gist_X.npy --alpha 0.02 --kb 32 \
        --C 500,1000,2000,4000 --out /mnt/raid/.../solo/gist_a0.02_kb32
"""
import argparse, time, numpy as np, misifu


class GemmInner:
    """Exact inner index by blocked GEMM (squared L2), sorted ascending."""
    def __init__(self, block=8192): self.block = block
    def build(self, Xs):
        self.Xs = np.ascontiguousarray(Xs, np.float32); self.n2 = (self.Xs ** 2).sum(1)
    def search(self, Q, k):
        Q = np.ascontiguousarray(Q, np.float32); ids = np.empty((len(Q), k), np.uint32)
        dst = np.empty((len(Q), k), np.float32)
        for a in range(0, len(Q), self.block):
            q = Q[a:a + self.block]
            D = (q ** 2).sum(1)[:, None] - 2.0 * (q @ self.Xs.T) + self.n2[None, :]
            p = np.argpartition(D, k - 1, axis=1)[:, :k]
            dp = np.take_along_axis(D, p, 1); o = np.argsort(dp, 1)
            ids[a:a + self.block] = np.take_along_axis(p, o, 1); dst[a:a + self.block] = np.take_along_axis(dp, o, 1)
        return ids, dst


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True); ap.add_argument("--out", required=True)
    ap.add_argument("--alpha", type=float, default=0.02); ap.add_argument("--kb", type=int, default=32)
    ap.add_argument("--C", default="500,1000,2000,4000"); ap.add_argument("--threads", type=int, default=64)
    ap.add_argument("--seed", type=int, default=1); ap.add_argument("--chunk", type=int, default=100_000)
    ap.add_argument("--scoring", default="count"); ap.add_argument("--cap", type=int, default=0, help="posting-list cap (0 = none; overlong lists keep the closest postings)")
    a = ap.parse_args(); Cs = sorted(int(c) for c in a.C.split(",")); Cmax = Cs[-1]
    X = np.ascontiguousarray(np.load(a.data), np.float32); n, d = X.shape
    print(f"solo_cands n={n} d={d} alpha={a.alpha} k_b={a.kb} C={Cs} scoring={a.scoring} cap={a.cap} threads={a.threads}", flush=True)

    t0 = time.time()
    idx = misifu.MISIFU(alpha=a.alpha, k_b=a.kb, inner=GemmInner(), cap=a.cap, seed=a.seed, n_threads=a.threads).fit(X)
    m = len(idx.sample_idx); t_fit = time.time() - t0
    sig = np.ascontiguousarray(idx.signatures, np.uint32)
    ll = np.asarray(idx._inv.list_lengths(), np.float64)
    print(f"  fit: |S|={m} signatures+postings {t_fit:.1f}s ({n*m/1e9:.1f} G sample pairs, GEMM); "
          f"posting length mean {ll.mean():.0f} max {ll.max():.0f}", flush=True)
    # inner-index self-check against misifu's brute kNN on a few rows
    chk = np.random.default_rng(0).choice(n, 256, replace=False)
    bi = misifu.inner.BruteInner(n_threads=a.threads); bi.build(X[idx.sample_idx]); ref, _ = bi.search(X[chk], a.kb)
    agree = np.mean([len(set(ref[i]) & set(sig[chk[i]])) / a.kb for i in range(len(chk))])
    print(f"  signature check vs misifu brute kNN: mean set agreement {agree:.4f}", flush=True)

    # merge ordering check: are lists sorted by shared count, descending?
    flat, off = idx._inv.batch_merge(sig[:8], Cmax + 1, a.scoring, a.threads, 0, None)
    mono = True
    for i in range(8):
        row = flat[off[i]:off[i + 1]]
        cnt = np.array([np.isin(sig[j], sig[i]).sum() for j in row])
        mono &= bool(np.all(np.diff(cnt) <= 0))
    mono = mono and a.scoring == "count"
    print(f"  merge lists descending by score: {mono} (single merge at C={Cmax} with prefixes; otherwise one merge per C)", flush=True)

    outs = {C: np.memmap(f"{a.out}_C{C}.i32", dtype=np.int32, mode="w+", shape=(n, C)) for C in Cs}  # raw rows, no header: fg freads n x C int32
    t_merge = 0.0; t_io = 0.0; short = 0
    for s in range(0, n, a.chunk):
        e = min(n, s + a.chunk); t = time.time()
        merged = {}
        if mono:
            merged[Cmax] = idx._inv.batch_merge(sig[s:e], Cmax + 1, a.scoring, a.threads, 0, None)
        else:
            for C in Cs: merged[C] = idx._inv.batch_merge(sig[s:e], C + 1, a.scoring, a.threads, 0, None)
        t_merge += time.time() - t; t = time.time()
        for C in Cs:
            flat, off = merged[Cmax] if mono else merged[C]
            buf = np.full((e - s, C), -1, np.int32)
            for i in range(e - s):
                row = flat[off[i]:off[i + 1]].astype(np.int64); row = row[row != s + i][:C]
                buf[i, :len(row)] = row; short += len(row) < C
            outs[C][s:e] = buf
        t_io += time.time() - t
        print(f"  rows {e}/{n}  merge {t_merge:.0f}s  write {t_io:.0f}s", flush=True)
    for o in outs.values(): o.flush()
    print(f"  done: fit {t_fit:.1f}s merge {t_merge:.1f}s ({t_merge/n*1e3:.3f} ms/row) write {t_io:.1f}s; "
          f"short rows {short}; files {a.out}_C*.i32", flush=True)


if __name__ == "__main__":
    main()
