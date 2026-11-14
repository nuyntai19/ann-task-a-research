#!/usr/bin/env python3
"""Oracle entry points for the router study.

A router over a uniform alpha-sample returns the query's nearest sample
point; its rank in the true ordering of the whole database is geometric with
mean 1/alpha. So "start the beam at the query's r-th true neighbour" is the
oracle for a router over an alpha ~ 1/r sample, and sweeping r prices router
precision without building a router.

Writes one int32 file per rank (nq entries, one entry point per query) for
`fg --entry-list`. Ranks below the gold width come from the gold file; deeper
ranks are brute-forced.

    python3 oracle_entries.py --data data/glove_norm_X.npy \
        --queries data/glove_norm_Q.npy --gold data/glove_gold.npy \
        --metric ip --out results/router/glove --ranks 0 1 5 10 25 50 100 1000 10000
"""
import argparse, os, time, numpy as np

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True); ap.add_argument("--queries", required=True)
    ap.add_argument("--gold", required=True); ap.add_argument("--out", required=True)
    ap.add_argument("--metric", default="ip", choices=["ip", "l2"])
    ap.add_argument("--ranks", type=int, nargs="+",
                    default=[0, 1, 2, 5, 10, 25, 50, 100, 250, 500, 1000, 2500, 5000, 10000])
    ap.add_argument("--chunk", type=int, default=256)
    ap.add_argument("--multi", type=int, nargs="+", default=[],
                    help="widths b: also write a b-column file at ranks r,2r,..,br "
                         "for each rank r in --ranks (the b nearest sample points of "
                         "an alpha ~ 1/r router, whose true ranks are ~r,2r,..)")
    a = ap.parse_args()
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)

    X = np.ascontiguousarray(np.load(a.data), dtype=np.float32)
    Q = np.ascontiguousarray(np.load(a.queries), dtype=np.float32)
    gold = np.load(a.gold).astype(np.int32)
    n, d = X.shape; nq = Q.shape[0]; gk = gold.shape[1]
    ranks = sorted(set(a.ranks))
    for b in a.multi:
        ranks = sorted(set(ranks) | {r * j for r in a.ranks for j in range(1, b + 1)})
    rmax = max(ranks)
    print(f"n={n} d={d} nq={nq} gold_k={gk} metric={a.metric} ranks<={rmax}", flush=True)

    ent = {r: np.full(nq, -1, np.int32) for r in ranks}
    shallow = [r for r in ranks if r < gk]
    for r in shallow:
        ent[r] = gold[:, r].astype(np.int32)
    deep = [r for r in ranks if r >= gk]

    if deep:
        K = rmax + 1
        xn = (X * X).sum(1) if a.metric == "l2" else None
        t0 = time.time()
        for s in range(0, nq, a.chunk):
            e = min(s + a.chunk, nq)
            sim = Q[s:e] @ X.T                      # (c, n)
            score = -sim if a.metric == "ip" else (xn[None, :] - 2.0 * sim)
            part = np.argpartition(score, K - 1, axis=1)[:, :K]
            ordv = np.take_along_axis(score, part, axis=1).argsort(axis=1, kind="stable")
            top = np.take_along_axis(part, ordv, axis=1)      # (c, K) nearest first
            for r in deep:
                ent[r][s:e] = top[:, r]
            if s == 0:                               # validate against the gold file
                agree = float((top[:, :min(gk, 10)] == gold[s:e, :min(gk, 10)]).mean())
                print(f"  brute force agrees with gold on the first 10 columns: {agree:.4f}", flush=True)
            if (s // a.chunk) % 8 == 0:
                print(f"  {e}/{nq} queries  {time.time()-t0:.1f}s", flush=True)

    for r in ranks:
        assert (ent[r] >= 0).all() and (ent[r] < n).all(), f"rank {r} has invalid ids"
        p = f"{a.out}_r{r}.i32"
        ent[r].astype(np.int32).tofile(p)
        uniq = len(np.unique(ent[r]))
        print(f"  rank {r:>6}  alpha ~ {1.0/max(r,1)*100:7.3f}%   {uniq} distinct entry points -> {p}")

    for b in a.multi:
        for r in a.ranks:
            if r == 0: continue
            cols = [ent[r * j] for j in range(1, b + 1)]
            m = np.stack(cols, axis=1).astype(np.int32)      # (nq, b), nearest first
            p = f"{a.out}_r{r}_b{b}.i32"
            m.tofile(p)
            print(f"  multi b={b} at ranks {[r*j for j in range(1,b+1)]} -> {p}")

if __name__ == "__main__":
    main()
