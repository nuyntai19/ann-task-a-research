#!/usr/bin/env python3
"""Dense (search-free) graph construction prototype: pair sets fixed in advance.

Stage 1  leaves: L k-means leaders (Lloyd on a sample), every point joins its m
         nearest leaders' leaves; inside every leaf an exact float GEMM gives
         every member its top-C candidates; a point's candidate list is the
         merge over its m leaves.  (The 2-bit proxy filter is lossless inside a
         pool -- evp-FINDINGS.md -- so the quality question is asked with exact
         distances; the proxy only changes the kernel's bytes.)
Stage 2  occlusion prune (Vamana/GRAFT rule, slack alpha) of each point's
         candidates to at most R out-neighbours, vectorised over batches.
Stage 3  reverse edges added, lists over R re-pruned.
Output   ParlayANN/fg graph file (u32 n, u32 maxdeg, u32 deg[n], rows), to be
         served by ParlayANN's search (-graph_path) for d@recall.

    OUT=results/dense python3 bench/dense_build.py --data data/glove_norm_X.npy \
        --leaders 240 --m 5 --C 200 --R 64 --alpha 1.0 --out g.graph
Cosine data must be L2-normalised (similarity = dot; distance = 2-2*dot).
"""
import argparse, time, json, numpy as np

def kmeans_leaders(X, L, iters, rng):
    leaders = X[rng.choice(len(X), L, replace=False)].copy()
    S = X[rng.choice(len(X), min(200000, len(X)), replace=False)]
    for _ in range(iters):
        asg = np.argmax(S @ leaders.T, axis=1)
        for l in range(L):
            mem = S[asg == l]
            if len(mem): c = mem.mean(0); leaders[l] = c / max(np.linalg.norm(c), 1e-9)
    return leaders

def top_leaders(X, leaders, m):
    out = np.empty((len(X), m), dtype=np.int32)
    for s in range(0, len(X), 65536):
        S = X[s:s+65536] @ leaders.T
        idx = np.argpartition(-S, m - 1, axis=1)[:, :m]
        out[s:s+65536] = idx
    return out

def stage1(X, memb, m_of, C, log):
    """per point: top-C candidates (ids, sims) merged over its leaves."""
    n = len(X); cand = np.full((n, C), -1, np.int32); csim = np.full((n, C), -np.inf, np.float32)
    pairs = 0; t0 = time.time()
    for l, M in enumerate(memb):
        XM = X[M]; XMT = XM.T.copy(); pairs += len(M) * len(M)
        for s in range(0, len(M), 2048):
            rows = M[s:s+2048]; S = X[rows] @ XMT                      # (r, |M|)
            S[np.arange(len(rows)), np.arange(s, s + len(rows))] = -np.inf   # drop self
            k = min(C, len(M) - 1)
            top = np.argpartition(-S, k - 1, axis=1)[:, :k]; vals = np.take_along_axis(S, top, axis=1)
            # merge with existing lists
            ids = np.concatenate([cand[rows], M[top]], axis=1); sv = np.concatenate([csim[rows], vals], axis=1)
            # dedupe: same id may come from two leaves; keep the larger sim (identical anyway)
            order = np.argsort(-sv, axis=1, kind="stable"); ids = np.take_along_axis(ids, order, axis=1); sv = np.take_along_axis(sv, order, axis=1)
            dup = np.zeros_like(ids, dtype=bool)
            for j in range(1, ids.shape[1]):                          # mark later duplicates (lists are short)
                dup[:, j] = (ids[:, :j] == ids[:, j:j+1]).any(axis=1) & (ids[:, j] >= 0)
            sv[dup] = -np.inf; order = np.argsort(-sv, axis=1, kind="stable")
            ids = np.take_along_axis(ids, order, axis=1)[:, :C]; sv = np.take_along_axis(sv, order, axis=1)[:, :C]
            cand[rows] = ids; csim[rows] = sv
        if l % 20 == 0: log(f"  leaf {l}/{len(memb)} |M|={len(M)} pairs so far {pairs/1e9:.1f}G  {time.time()-t0:.0f}s")
    return cand, csim, pairs

def occlusion_prune(X, cand, csim, R, alpha, batch=2048):
    """Vamana rule: candidates by increasing distance; c is kept unless some kept k has
    alpha * d(k, c) <= d(p, c).  Returns padded (n, R) int32 rows (-1 = none)."""
    n, C = cand.shape; out = np.full((n, R), -1, np.int32); ndist = 0
    for s in range(0, n, batch):
        ids = cand[s:s+batch]; sims = csim[s:s+batch]; b = len(ids)
        valid = ids >= 0; safe = np.where(valid, ids, 0)
        dp = 2 - 2 * np.where(valid, sims, -1)                                  # d(p, c), inf-ish for invalid
        V = X[safe]                                                             # (b, C, d)
        G = np.matmul(V, V.transpose(0, 2, 1)); D = 2 - 2 * G; ndist += b * C * (C - 1) // 2   # d(k, c) among candidates
        kept = np.zeros((b, C), bool); nk = np.zeros(b, np.int32)
        for j in range(C):                                                      # candidates already sorted by distance
            ok = valid[:, j] & (nk < R)
            occl = (kept & (alpha * D[:, :, j] <= dp[:, j:j+1])).any(axis=1)
            keep = ok & ~occl; kept[:, j] = keep; nk += keep
        for i in range(b):
            k = ids[i][kept[i]]; out[s + i, :len(k)] = k[:R]
    return out, ndist

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True); ap.add_argument("--out", required=True)
    ap.add_argument("--leaders", type=int, default=240); ap.add_argument("--m", type=int, default=5); ap.add_argument("--kmeans", type=int, default=10)
    ap.add_argument("--C", type=int, default=200); ap.add_argument("--R", type=int, default=64); ap.add_argument("--alpha", type=float, default=1.0)
    ap.add_argument("--seed", type=int, default=1)
    a = ap.parse_args(); rng = np.random.default_rng(a.seed); T = {}
    log = lambda s: print(s, flush=True)
    X = np.ascontiguousarray(np.load(a.data), dtype=np.float32); n, d = X.shape
    log(f"dense build n={n} d={d} L={a.leaders} m={a.m} C={a.C} R={a.R} alpha={a.alpha}")
    t = time.time(); leaders = kmeans_leaders(X, a.leaders, a.kmeans, rng); bl = top_leaders(X, leaders, a.m)
    memb = [np.nonzero((bl == l).any(axis=1))[0] for l in range(a.leaders)]
    sizes = np.array([len(M) for M in memb]); T["leaves_s"] = time.time() - t
    log(f"leaves: mean {sizes.mean():.0f} max {sizes.max()} min {sizes.min()}  ({T['leaves_s']:.0f}s)")
    t = time.time(); cand, csim, pairs = stage1(X, memb, bl, a.C, log); T["stage1_s"] = time.time() - t; T["stage1_pairs"] = pairs
    log(f"stage 1: {pairs/1e9:.1f} G pairs, {T['stage1_s']:.0f}s; mean candidates/pt {(cand>=0).sum(1).mean():.0f}")
    t = time.time(); rows, nd2 = occlusion_prune(X, cand, csim, a.R, a.alpha); T["stage2_s"] = time.time() - t; T["stage2_dist"] = nd2
    log(f"stage 2: pruned to mean degree {(rows>=0).sum(1).mean():.1f}, {nd2/1e9:.1f} G candidate-candidate distances, {T['stage2_s']:.0f}s")
    # stage 3: reverse edges, re-prune lists over R
    t = time.time()
    src = np.repeat(np.arange(n, dtype=np.int32), a.R); dst = rows.ravel(); ok = dst >= 0; src = src[ok]; dst = dst[ok]
    allsrc = np.concatenate([src, dst]); alldst = np.concatenate([dst, src])
    order = np.argsort(allsrc, kind="stable"); allsrc = allsrc[order]; alldst = alldst[order]
    bounds = np.searchsorted(allsrc, np.arange(n + 1)); deg = np.diff(bounds)
    log(f"stage 3: after reverse edges mean degree {deg.mean():.1f} max {deg.max()}; re-pruning {int((deg > a.R).sum())} lists")
    final = [None] * n; big = np.nonzero(deg > a.R)[0]
    # build candidate matrices for the big ones (dedupe, sort by distance) and prune in batches
    Cmax = int(deg[big].max()) if len(big) else 0
    if len(big):
        cb = np.full((len(big), Cmax), -1, np.int32); sb = np.full((len(big), Cmax), -np.inf, np.float32)
        for i, p in enumerate(big):
            nb = np.unique(alldst[bounds[p]:bounds[p+1]]); nb = nb[nb != p]
            sims = X[nb] @ X[p]; o = np.argsort(-sims, kind="stable"); cb[i, :len(nb)] = nb[o]; sb[i, :len(nb)] = sims[o]
        pr, nd3 = occlusion_prune(X, cb, sb, a.R, a.alpha, batch=512); T["stage3_dist"] = nd3
        for i, p in enumerate(big): final[p] = pr[i][pr[i] >= 0]
    for p in range(n):
        if final[p] is None:
            nb = np.unique(alldst[bounds[p]:bounds[p+1]]); final[p] = nb[nb != p]
    T["stage3_s"] = time.time() - t
    degs = np.array([len(f) for f in final], np.uint32); log(f"final: mean degree {degs.mean():.1f} max {degs.max()}  ({T['stage3_s']:.0f}s)")
    with open(a.out, "wb") as f:
        np.array([n, degs.max()], np.uint32).tofile(f); degs.tofile(f)
        np.concatenate(final).astype(np.uint32).tofile(f)
    T["total_s"] = sum(v for k, v in T.items() if k.endswith("_s")); log(json.dumps(T)); log(f"wrote {a.out}")

if __name__ == "__main__":
    main()
