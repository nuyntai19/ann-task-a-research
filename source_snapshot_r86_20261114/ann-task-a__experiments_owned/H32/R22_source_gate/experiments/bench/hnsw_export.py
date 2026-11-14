#!/usr/bin/env python3
"""hnswlib on the common searcher (REVIEW-002: "hnswlib quality missing").

Builds hnswlib (M, efC 200, seed 100 = Table 3's arm) on X, reports its own
search ladder (recall@k, QPS; hnswlib exposes no distance counter), saves the
index and exports its LEVEL-0 graph in ParlayANN's format (n, maxdeg, degrees,
ids) by parsing hnswlib's documented save format, so ParlayANN grades it with
the same searcher, beam ladder and distance counter as every other row.
Caveat stated with every number: ParlayANN searches the level-0 graph flat
from point 0; hnswlib's own search descends the hierarchy first.
Usage: hnsw_export.py X.npy Q.npy gold.npy M out_prefix [threads]
"""
import numpy as np, sys, time, hnswlib
Xp, Qp, Gp, M, out = sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4]), sys.argv[5]
threads = int(sys.argv[6]) if len(sys.argv) > 6 else 64
X = np.ascontiguousarray(np.load(Xp), np.float32); Q = np.ascontiguousarray(np.load(Qp), np.float32)
gold = np.load(Gp); n, d = X.shape
idx = hnswlib.Index(space="l2", dim=d)            # cosine corpora are unit-norm: same ranking
idx.init_index(max_elements=n, ef_construction=200, M=M, random_seed=100)
t0 = time.perf_counter(); idx.add_items(X, np.arange(n), num_threads=threads); bt = time.perf_counter() - t0
print(f"hnswlib M{M} efC200: build {bt:.1f} s, n={n} d={d}", flush=True)
for k in (10, 100):
    for ef in (10, 20, 40, 80, 120, 200, 300, 400, 600, 800, 1200, 1600):
        if ef < k: continue
        idx.set_ef(ef); t0 = time.perf_counter(); lab, _ = idx.knn_query(Q, k=k, num_threads=threads); qt = time.perf_counter() - t0
        rec = np.mean([len(set(a) & set(b[:k])) / k for a, b in zip(lab.tolist(), gold[:, :k].tolist())])
        print(f"  native k={k} ef={ef}: recall {rec:.4f}  QPS {len(Q)/qt:.0f}", flush=True)
idx.save_index(f"{out}.hnsw"); del idx
# ---- parse hnswlib's save format (hnswalg.h saveIndex) ----------------------
with open(f"{out}.hnsw", "rb") as f:
    h = np.frombuffer(f.read(96), np.uint8)
    off0, maxel, cnt, sz, lab_off, data_off = np.frombuffer(h[:48].tobytes(), np.uint64)
    maxlevel, enter = np.frombuffer(h[48:56].tobytes(), np.int32)
    maxM, maxM0, Mm = np.frombuffer(h[56:80].tobytes(), np.uint64)
    cnt, sz, off0, lab_off = int(cnt), int(sz), int(off0), int(lab_off); maxM0 = int(maxM0)
    L0 = np.frombuffer(f.read(cnt * sz), np.uint8).reshape(cnt, sz)
lk = L0[:, off0:off0 + 4 * (maxM0 + 1)].copy().view(np.uint32)          # [count | maxM0 ids]
deg = (lk[:, 0] & 0xFFFF).astype(np.int64)
label = L0[:, lab_off:lab_off + 8].copy().view(np.uint64)[:, 0].astype(np.int64)
order = np.empty(cnt, np.int64); order[label] = np.arange(cnt)          # label -> internal
degs = deg[order].astype(np.uint32)
with open(f"{out}_level0.graph", "wb") as g:
    np.array([cnt, int(degs.max())], np.uint32).tofile(g); degs.tofile(g)
    for s0 in range(0, cnt, 4_000_000):                                   # vectorised, row order = label order
        o = order[s0:s0 + 4_000_000]; R = lk[o, 1:]
        label[R[np.arange(maxM0)[None, :] < deg[o][:, None]]].astype(np.uint32).tofile(g)
print(f"level-0 graph: n={cnt} maxM0={maxM0} mean degree {deg.mean():.1f} max {deg.max()}; "
      f"maxlevel {int(maxlevel)} entry {int(enter)} -> {out}_level0.graph", flush=True)
