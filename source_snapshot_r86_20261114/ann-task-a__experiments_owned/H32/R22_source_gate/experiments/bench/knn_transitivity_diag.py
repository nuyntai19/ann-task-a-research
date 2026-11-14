# Transitivity of the exact kNN graph vs the cost of covering it with blocks.
# Conjecture: the pairs a clique cover (symmetric k-means leaves, m memberships)
# needs to cover a fraction rho of true kNN pairs is governed by how transitive
# G_k is (reciprocity, clustering, shared neighbours, two-hop expansion).
# Sampled: P = 2,000 random points, exact 10-NN of P and of every q in N(P).
# Usage: python bench/knn_transitivity_diag.py [corpus ...]   (L2 on *_X.npy;
# glove_norm / wiki are unit-norm, so L2 ranks = cosine ranks)
import numpy as np, sys, time, os
DATA = "/Users/elchavez/code/claude/sat-forest/data"
K, NP, CELL, SEED = 10, 2000, 1400, 0

try:
    import faiss
except ImportError:
    faiss = None
_FIX = {}
def knn(X, x2, qidx, k, qb=1024, cb=262_144):
    if faiss is not None:                       # d0: exact flat search, multithreaded
        if id(X) not in _FIX:
            _FIX.clear(); ix = faiss.IndexFlatL2(X.shape[1]); ix.add(X); _FIX[id(X)] = ix
        Dd, Ii = _FIX[id(X)].search(X[qidx], k + 1)
        keep = Ii != qidx[:, None]; keep[keep.all(1), -1] = False
        return Ii[keep].reshape(len(qidx), k).astype(np.int64), np.sqrt(np.maximum(Dd[keep].reshape(len(qidx), k), 0))
    n = len(X); I = np.empty((len(qidx), k), np.int64); Dk = np.empty((len(qidx), k), np.float32)
    for s in range(0, len(qidx), qb):
        qi = qidx[s:s + qb]; Q = X[qi]; q2 = x2[qi][:, None]
        bI = np.empty((len(qi), 0), np.int64); bD = np.empty((len(qi), 0), np.float32)
        for c in range(0, n, cb):
            D = q2 - 2.0 * (Q @ X[c:c + cb].T) + x2[None, c:c + cb]
            r = np.nonzero((qi >= c) & (qi < c + cb))[0]; D[r, qi[r] - c] = np.inf
            p = np.argpartition(D, k - 1, axis=1)[:, :k]
            bI = np.hstack([bI, p + c]); bD = np.hstack([bD, np.take_along_axis(D, p, 1)])
            if bI.shape[1] > k:
                p = np.argpartition(bD, k - 1, axis=1)[:, :k]; bI = np.take_along_axis(bI, p, 1); bD = np.take_along_axis(bD, p, 1)
        o = np.argsort(bD, 1); I[s:s + qb] = np.take_along_axis(bI, o, 1); Dk[s:s + qb] = np.maximum(np.take_along_axis(bD, o, 1), 0)
    return I, np.sqrt(Dk)

def lloyd(X, L, iters=10, ns=200_000, seed=1):
    rng = np.random.default_rng(seed); ns = min(ns, len(X)); Q = X[rng.choice(len(X), ns, replace=False)]
    C = Q[:L].copy()
    for _ in range(iters):
        a = nearest(Q, C, 1)[:, 0]
        for l in range(L):
            msk = a == l
            if msk.any(): C[l] = Q[msk].mean(0)
    return C

def nearest(X, C, m, b=8192):
    c2 = (C ** 2).sum(1); ids = np.empty((len(X), m), np.int32)
    for s in range(0, len(X), b):
        q = X[s:s + b]; D = -2.0 * (q @ C.T) + c2[None, :]
        p = np.argpartition(D, m - 1, axis=1)[:, :m]; o = np.argsort(np.take_along_axis(D, p, 1), 1)
        ids[s:s + b] = np.take_along_axis(p, o, 1)
    return ids

def run(name, nsub=0):
    t0 = time.time()
    X = np.load(name if name.endswith(".npy") else f"{DATA}/{name}_X.npy", mmap_mode="r")
    if nsub and nsub < len(X): X = X[np.sort(np.random.default_rng(7).choice(len(X), nsub, replace=False))]
    X = np.ascontiguousarray(X, np.float32); n = len(X); x2 = (X ** 2).sum(1)
    P = np.sort(np.random.default_rng(SEED).choice(n, NP, replace=False))
    NPi, NPd = knn(X, x2, P, K)
    Qs = np.unique(NPi); NQi, _ = knn(X, x2, Qs, K)
    nbr = dict(zip(Qs.tolist(), map(set, NQi.tolist())))
    recip, cc, shared, expn, recip_p = [], [], [], [], []
    for p, row in zip(P.tolist(), NPi.tolist()):
        S = set(row)
        recip += [p in nbr[q] for q in row]
        cc.append(np.mean([r in nbr[q] for q in row for r in row if r != q]))
        recip_p.append(np.mean([p in nbr[q] for q in row]))
        shared += [len(S & nbr[q]) / K for q in row]
        U = S | {p}
        for q in row: U |= nbr[q]
        expn.append((len(U) - 1) / K)                      # 1 = perfectly clustered, K+1 = tree-like
    d = NPd; lid = -1.0 / np.mean(np.log(np.maximum(d[:, :-1], 1e-30) / d[:, -1:]), axis=1)
    tt = time.time() - t0
    if os.environ.get("TRANS_NOCOST"):
        print(f"\n== {name}  n={n} d={X.shape[1]}  (graph stats only, {tt:.0f}s)")
        print(f"  LID(MLE,k10) median {np.median(lid):.1f}   reciprocity {np.mean(recip):.3f}   clustering {np.mean(cc):.3f}"
              f"   shared-nbr {np.mean(shared):.3f}   2-hop expansion {np.mean(expn):.2f} (of 1..{K+1})")
        cc = np.array(cc)
        print(f"  local clustering: q10 {np.quantile(cc,.1):.3f} q25 {np.quantile(cc,.25):.3f} median {np.median(cc):.3f}  frac cc<0.03 {np.mean(cc<0.03):.3f}  frac cc==0 {np.mean(cc==0):.3f}", flush=True)
        return
    # cost side: symmetric k-means leaves, mean cell ~CELL, m memberships
    L = max(16, round(n / CELL)); C = lloyd(X, L); top = nearest(X, C, 12)
    px = np.repeat(P, K); py = NPi.ravel(); curve = []
    for m in range(1, 13):
        t = top[:, :m]; leaf = np.zeros(L, np.int64)
        for j in range(m): leaf += np.bincount(t[:, j], minlength=L)
        cov = np.mean([len(set(a) & set(b)) > 0 for a, b in zip(t[px].tolist(), t[py].tolist())])
        pool = leaf[t[P]].sum(1).mean()                    # candidates per point
        curve.append((m, cov, pool, (leaf.astype(np.float64) ** 2).sum() / 2 / 1e9))
    def at(rho):
        for (m0, c0, p0, _), (m1, c1, p1, _) in zip(curve, curve[1:]):
            if c0 < rho <= c1: return p0 + (p1 - p0) * (rho - c0) / (c1 - c0)
        return float("nan")
    print(f"\n== {name}{' sub' if nsub else ''}  n={n} d={X.shape[1]}  (graph stats {tt:.0f}s, total {time.time()-t0:.0f}s)")
    print(f"  LID(MLE,k10) median {np.median(lid):.1f}   reciprocity {np.mean(recip):.3f}   clustering {np.mean(cc):.3f}"
          f"   shared-nbr {np.mean(shared):.3f}   2-hop expansion {np.mean(expn):.2f} (of 1..{K+1})")
    print(f"  k-means L={L}: " + "  ".join(f"m{m}:{c:.3f}@{p/1e3:.1f}k" for m, c, p, _ in curve))
    cc = np.array(cc); rp = np.array(recip_p); rk = lambda a: np.argsort(np.argsort(a))
    print(f"  local clustering: q10 {np.quantile(cc,.1):.3f} q25 {np.quantile(cc,.25):.3f} median {np.median(cc):.3f}  frac cc<0.03 {np.mean(cc<0.03):.3f}  frac cc==0 {np.mean(cc==0):.3f}")
    for m in (2, 4):
        t = top[:, :m]; covp = np.array([len(set(a) & set(b)) > 0 for a, b in zip(t[px].tolist(), t[py].tolist())]).reshape(NP, K).mean(1)
        q = np.quantile(cc, [0.25, 0.5, 0.75]); b = np.digitize(cc, q)
        sp = lambda a: np.corrcoef(rk(a), rk(covp))[0, 1]
        print(f"  within-corpus m={m}: cover by clustering quartile " + " ".join(f"{covp[b==i].mean():.3f}" for i in range(4))
              + f"   Spearman(cover, clustering) {sp(cc):+.2f}  (cover, reciprocity) {sp(rp):+.2f}  (cover, LID) {sp(lid):+.2f}")
    mk = lambda rho: next((m0 + (rho - c0) / (c1 - c0) for (m0, c0, *_), (m1, c1, *_) in zip(curve, curve[1:]) if c0 < rho <= c1), float("nan"))
    print(f"  memberships needed: m@0.85 {mk(0.85):.2f}  m@0.90 {mk(0.90):.2f}  m@0.95 {mk(0.95):.2f}")
    print(f"  pool/pt at cover 0.85: {at(0.85)/1e3:.1f}k ({at(0.85)/n:.2%} of n)   at 0.90: {at(0.90)/1e3:.1f}k ({at(0.90)/n:.2%} of n)", flush=True)

NSUB = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 0
for c in ([a for a in sys.argv[1:] if not a.isdigit()] or ["sift", "glove_norm", "wiki", "gist"]): run(c, NSUB)
