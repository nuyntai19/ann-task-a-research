#!/usr/bin/env python3
"""The bandwidth wall made visible: build distance throughput vs n across the
cache boundary, for a search-based builder (fg frozen T16/ef400), the tuned
incremental baseline (Vamana R100/L200 2-pass) and a blocked GEMM.

For each n (prefix of GloVe-100, L2-normalised): write the subset + answer
key, build with fg and Vamana (64 threads), record build distances / build
seconds, and time a float32 GEMM with the same order of distance count.
Working set per n = n * 4d bytes (fg pads d to 112); d0's L3 is 20 MB per
socket, 80 MB total.

    FG=<fg> PIPNN=<PiPNN> DATA=data OUT=results/cache_sweep python3 bench/cache_sweep.py
"""
import json, os, pathlib, re, subprocess, time
import numpy as np

FG = os.environ["FG"]; PIPNN = pathlib.Path(os.environ["PIPNN"])
DATA = pathlib.Path(os.environ.get("DATA", "data")); OUT = pathlib.Path(os.environ.get("OUT", "results/cache_sweep"))
THREADS = int(os.environ.get("THREADS", "64")); SEED = 1
NS = [int(x) for x in os.environ.get("NS", "20000,50000,100000,200000,500000,1183514").split(",")]
VAMANA = PIPNN / "build/algorithms/vamana/neighbors-vamana_FLOAT_T_EUCLIDEAN"
OUT.mkdir(parents=True, exist_ok=True); SUB = DATA / "sub"; SUB.mkdir(exist_ok=True)

X = np.load(DATA / "glove_norm_X.npy", mmap_mode="r"); Q = np.load(DATA / "glove_norm_Q.npy")
d = X.shape[1]

def fbin(p, A):
    with open(p, "wb") as f:
        np.array(A.shape, dtype=np.uint32).tofile(f); np.ascontiguousarray(A, dtype=np.float32).tofile(f)

def subset(n):
    xs, qs, gs, xb, qb, gt = (SUB / f"g{n}_X.npy", SUB / f"g{n}_Q.npy", SUB / f"g{n}_gold.npy",
                              SUB / f"g{n}_base.fbin", SUB / f"g{n}_query.fbin", SUB / f"g{n}_gt100")
    if gt.exists(): return xs, qs, gs, xb, qb, gt
    Xn = np.ascontiguousarray(X[:n], dtype=np.float32); np.save(xs, Xn); np.save(qs, Q); fbin(xb, Xn); fbin(qb, Q)
    gold = np.empty((Q.shape[0], 100), dtype=np.int32); d2 = np.empty_like(gold, dtype=np.float32)
    for s in range(0, Q.shape[0], 500):
        sims = Q[s:s+500] @ Xn.T
        idx = np.argpartition(-sims, 100, axis=1)[:, :100]; rows = np.arange(idx.shape[0])[:, None]
        order = np.argsort(-sims[rows, idx], axis=1, kind="stable"); g = idx[rows, order]
        gold[s:s+500] = g; d2[s:s+500] = 2 - 2 * sims[rows, g]
    np.save(gs, gold)
    with open(gt, "wb") as f:
        np.array(gold.shape, dtype=np.uint32).tofile(f); gold.astype(np.uint32).tofile(f); d2.tofile(f)
    return xs, qs, gs, xb, qb, gt

def run(cmd):
    t0 = time.perf_counter(); p = subprocess.run(cmd, capture_output=True, text=True)
    return p.stdout + p.stderr, time.perf_counter() - t0

def fg_build(n, xs, qs, gs):
    out, wall = run([FG, "--data", str(xs), "--queries", str(qs), "--gold", str(gs), "--metric", "cosine",
                     "--T", "16", "--harvest", "400", "--harvest-cap", "64", "--threads", str(THREADS),
                     "--seed", str(SEED), "--ef", "100"])
    (OUT / f"fg-n{n}.log").write_text(out)
    tr = re.search(r"trees ([0-9.]+)s \(\d+ threads\), ([0-9.]+)M dist", out)
    ov = re.search(r"overlay\+backlinks ([0-9.]+)s", out); hv = re.search(r"harvest ef=\d+.*? ([0-9.]+)s\n", out)
    if not (tr and hv): return {"error": out[-800:]}
    b = float(tr.group(1)) + (float(ov.group(1)) if ov else 0) + float(hv.group(1))
    return {"build_s": round(b, 3), "gdist": float(tr.group(2)) / 1000, "trees_s": float(tr.group(1)), "harvest_s": float(hv.group(1))}

def vamana_build(n, xb, qb, gt):
    out, wall = run([str(VAMANA), "-base_path", str(xb), "-query_path", str(qb), "-gt_path", str(gt), "-file_type", "bin",
                     "-data_type", "float", "-dist_func", "Euclidian", "-R", "100", "-L", "200", "-alpha", "1.0",
                     "-two_pass", "1", "-k", "10"])
    (OUT / f"vamana-n{n}.log").write_text(out)
    m = re.search(r"Graph built in ([0-9.]+) seconds", out); c = re.search(r"BUILD_DISTANCES (\d+)", out)
    if not (m and c): return {"error": out[-800:]}
    return {"build_s": float(m.group(1)), "gdist": int(c.group(1)) / 1e9}

def gemm_rate(n):
    """float32 GEMM distances/s at this n: X[:n] @ X[:b].T, n*b ~ 2e9 pairs, best of 3."""
    Xn = np.ascontiguousarray(X[:n], dtype=np.float32); b = int(min(n, max(1000, 2e9 // n)))
    B = np.ascontiguousarray(Xn[:b].T)
    Xn @ B[:, :64]  # warm
    best = 1e9
    for _ in range(3):
        t0 = time.perf_counter(); S = Xn @ B; dt = time.perf_counter() - t0; best = min(best, dt)
    return {"pairs": n * b, "s": best, "rate": n * b / best, "b": b}

res = {"machine": "d0", "threads": THREADS, "d": d, "rows": []}
print(f"{'n':>9}{'MB':>7}{'fg s':>8}{'fg G':>7}{'fg Gd/s':>9}{'vam s':>8}{'vam G':>7}{'vam Gd/s':>9}{'gemm Gd/s':>10}", flush=True)
for n in NS:
    xs, qs, gs, xb, qb, gt = subset(n)
    g = gemm_rate(n); f = fg_build(n, xs, qs, gs); v = vamana_build(n, xb, qb, gt)
    row = {"n": n, "working_set_MB": n * 4 * 112 / 1e6, "fg": f, "vamana": v, "gemm": g}
    res["rows"].append(row); json.dump(res, open(OUT / "cache_sweep.json", "w"), indent=1)
    fr = f.get("gdist", 0) / f.get("build_s", 1) if "gdist" in f else float("nan")
    vr = v.get("gdist", 0) / v.get("build_s", 1) if "gdist" in v else float("nan")
    print(f"{n:9d}{row['working_set_MB']:7.0f}{f.get('build_s', float('nan')):8.1f}{f.get('gdist', float('nan')):7.2f}{fr:9.3f}"
          f"{v.get('build_s', float('nan')):8.1f}{v.get('gdist', float('nan')):7.2f}{vr:9.3f}{g['rate']/1e9:10.2f}", flush=True)
print("DONE", flush=True)
