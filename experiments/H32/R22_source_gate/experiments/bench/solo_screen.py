#!/usr/bin/env python3
"""Two measurements for a 2-bit SOLO stream.

(A) SCREEN. Inside a routed pool (the union of the ks lists a query visits),
    how large a pass set does each proxy need before an exact re-rank of that
    pass set recovers the pool's own ceiling? Compares SQ8, SQ4, EVP 2-bit
    with a float query (ft) and EVP 2-bit both sides (tt).

(B) ROUTER. Coverage at fixed ks when the router itself ranks the sample in
    float, SQ8 or 2 bits. Coverage is recall for an exact exhaustive scan
    (SOLO's Prop. 1), so a lossy router degrades the certificate, not just
    the speed.

Structure mirrors SOLO: S = uniform alpha-sample; every object joins the
lists of its b nearest sample points; a query scans the lists of its ks
nearest sample points.
"""
import argparse, time, numpy as np

def sq_codes(X, bits):
    """Per-dimension uniform scalar quantisation; returns the dequantised array."""
    lo = X.min(0); hi = X.max(0); rng = np.maximum(hi - lo, 1e-12)
    L = (1 << bits) - 1
    C = np.rint((X - lo) / rng * L).astype(np.uint8 if bits <= 8 else np.uint16)
    return (C.astype(np.float32) / L) * rng + lo

def evp(X, x=None):
    """{x,d} EVP: keep the x largest |u_i| as +-1, zero the rest (x = d/2)."""
    n, d = X.shape
    x = x or d // 2
    T = np.zeros_like(X, dtype=np.float32)
    idx = np.argpartition(-np.abs(X), x - 1, axis=1)[:, :x]
    np.put_along_axis(T, idx, np.sign(np.take_along_axis(X, idx, axis=1)), axis=1)
    return T

def topk_cols(S, k):
    """indices of the k largest per row, best first"""
    p = np.argpartition(-S, k - 1, axis=1)[:, :k]
    o = np.take_along_axis(S, p, axis=1).argsort(axis=1)[:, ::-1]
    return np.take_along_axis(p, o, axis=1)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True); ap.add_argument("--queries", required=True)
    ap.add_argument("--gold", required=True); ap.add_argument("--tag", required=True)
    ap.add_argument("--alpha", type=float, default=0.02)
    ap.add_argument("--b", type=int, default=8, help="build-side assignment rank")
    ap.add_argument("--ks", type=int, nargs="+", default=[8, 16, 32, 64, 128])
    ap.add_argument("--nq", type=int, default=200)
    ap.add_argument("--k", type=int, default=10)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--chunk", type=int, default=20000)
    a = ap.parse_args()
    rng = np.random.default_rng(a.seed)

    X = np.ascontiguousarray(np.load(a.data), dtype=np.float32)
    Q = np.ascontiguousarray(np.load(a.queries), dtype=np.float32)[:a.nq]
    gold = np.load(a.gold).astype(np.int64)[:a.nq, :a.k]
    n, d = X.shape; nq = Q.shape[0]
    ns = max(int(round(a.alpha * n)), a.b + 1)
    S_ids = rng.choice(n, ns, replace=False).astype(np.int64)
    print(f"[{a.tag}] n={n} d={d} nq={nq} |S|={ns} (alpha={a.alpha:.3%}) b={a.b}", flush=True)

    # ---- proxies, materialised once (dequantised: score = float query . dequantised code)
    t = time.time()
    P = {"exact": X, "sq8": sq_codes(X, 8), "sq4": sq_codes(X, 4), "evp_ft": evp(X)}
    Qp = {"exact": Q, "sq8": Q, "sq4": Q, "evp_ft": Q, "evp_tt": evp(Q)}
    P["evp_tt"] = P["evp_ft"]
    print(f"  proxies built {time.time()-t:.1f}s "
          f"(bytes/vector: exact {4*d}, sq8 {d}, sq4 {d//2}, evp {d//4})", flush=True)

    # ---- build-side assignment: each object joins its b nearest sample points
    t = time.time()
    Sx = X[S_ids]
    asg = np.empty((n, a.b), np.int32)
    for s in range(0, n, a.chunk):
        e = min(s + a.chunk, n)
        asg[s:e] = topk_cols(X[s:e] @ Sx.T, a.b).astype(np.int32)
    order = np.argsort(asg.ravel(), kind="stable")
    members = np.repeat(np.arange(n, dtype=np.int64), a.b)[order]
    lptr = np.searchsorted(asg.ravel()[order], np.arange(ns + 1))
    print(f"  assignment {time.time()-t:.1f}s; lists mean {np.diff(lptr).mean():.0f} "
          f"max {np.diff(lptr).max()}", flush=True)

    # ---- routers: rank the sample under each proxy
    routers = {"float": Q @ Sx.T,
               "sq8": Q @ P["sq8"][S_ids].T,
               "evp_ft": Q @ P["evp_ft"][S_ids].T,
               "evp_tt": Qp["evp_tt"] @ P["evp_ft"][S_ids].T}
    route = {m: topk_cols(v, max(a.ks)) for m, v in routers.items()}

    # ---- (B) coverage of the true k-NN by the ks routed lists
    print(f"\n(B) ROUTER: coverage of the true {a.k}-NN by the ks routed lists")
    print(f"{'ks':>6}{'scanned':>10}" + "".join(f"{m:>10}" for m in route))
    cov = {m: {} for m in route}
    for ks in a.ks:
        sc = []
        for m in route:
            c, frac = 0.0, 0.0
            for i in range(nq):
                sel = route[m][i, :ks]
                pool = np.unique(np.concatenate([members[lptr[j]:lptr[j+1]] for j in sel]))
                c += np.isin(gold[i], pool).mean(); frac += len(pool) / n
            cov[m][ks] = c / nq; sc.append(c / nq)
            if m == "float": frac_f = frac / nq
        print(f"{ks:>6}{frac_f:9.3%}" + "".join(f"{v:10.4f}" for v in sc), flush=True)

    # ---- (A) screen: pass set needed to recover the pool ceiling
    KS = [10, 20, 50, 100, 200, 500, 1000, 2000, 5000]
    for ks in a.ks:
        print(f"\n(A) SCREEN at ks={ks}: recall@{a.k} after exact re-rank of the proxy's top-K")
        print(f"{'K':>7}" + "".join(f"{m:>10}" for m in ["sq8", "sq4", "evp_ft", "evp_tt"])
              + f"{'ceiling':>10}")
        pools = []
        for i in range(nq):
            sel = route["float"][i, :ks]
            pools.append(np.unique(np.concatenate([members[lptr[j]:lptr[j+1]] for j in sel])))
        ceil = np.mean([np.isin(gold[i], pools[i]).mean() for i in range(nq)])
        rows = {m: {} for m in ["sq8", "sq4", "evp_ft", "evp_tt"]}
        for K in KS:
            out = []
            for m in rows:
                r = 0.0
                for i in range(nq):
                    pl = pools[i]
                    if len(pl) <= K: cand = pl
                    else:
                        sc = Qp[m][i] @ P[m][pl].T
                        cand = pl[np.argpartition(-sc, K - 1)[:K]]
                    ex = Q[i] @ X[cand].T
                    top = cand[np.argpartition(-ex, min(a.k, len(cand)) - 1)[:a.k]]
                    r += np.isin(gold[i], top).mean()
                rows[m][K] = r / nq; out.append(r / nq)
            print(f"{K:>7}" + "".join(f"{v:10.4f}" for v in out) + f"{ceil:10.4f}", flush=True)
            if all(v >= ceil - 1e-9 for v in out): break

if __name__ == "__main__":
    main()
