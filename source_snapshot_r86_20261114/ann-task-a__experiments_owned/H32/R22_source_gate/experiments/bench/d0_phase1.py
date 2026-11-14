#!/usr/bin/env python3
"""FGRAFT Phase 1 -- paired, repeated build wall-clock on d0 (64 threads).

Every system is built once per block in a seeded random order; the block is
the pairing unit.  Per build we record the system's own build timer, its
build distance count where the code exposes one (fg: total build count;
Vamana: BUILD_DISTANCES from patches/parlayann-build-distance-counter.patch),
the fg quality fingerprint (edges, completeness, recall ladder) and the
full stdout.  The manifest (results.rows with {block, system, build_s}) is
rewritten after every block and is consumed by graft-ann/bench/paired_stats.py.

    FG=<graft-ann>/src/fg PIPNN=<PiPNN> DATA=data BLOCKS=10 DS=glove \
        python3 bench/d0_phase1.py

Arms: GRAFT frozen (published profiles), FGRAFT (--harvest-blocks B),
Vamana (authors' params, 2-pass), PiPNN, hnswlib M16/M32 (in-process,
efC 200, seed 100).  Labels all start with "graft"/"fgraft" vs baselines so
paired_stats pairs every GRAFT-family arm against every baseline.
"""
import gc, json, os, pathlib, random, re, subprocess, sys, time

FG = os.environ["FG"]; PIPNN = pathlib.Path(os.environ["PIPNN"])
DATA = pathlib.Path(os.environ.get("DATA", "data"))
BLOCKS = int(os.environ.get("BLOCKS", "10")); COOL = float(os.environ.get("COOL", "5"))
THREADS = int(os.environ.get("THREADS", str(os.cpu_count()))); SEED = int(os.environ.get("SEED", "1"))
DS = os.environ.get("DS", "glove").split(",")
OUT = pathlib.Path(os.environ.get("OUT", "results/phase1")); OUT.mkdir(parents=True, exist_ok=True)
VAMANA = PIPNN / "build/algorithms/vamana/neighbors-vamana_FLOAT_T_EUCLIDEAN"
PIPNNB = PIPNN / "build/algorithms/PipNN/neighbors-pipnn_FLOAT_T_EUCLIDEAN"
EF_LADDER = ["60", "80", "120", "200", "300", "400", "600"]

def npy(name, kind):
    for cand in (DATA / f"{name}_norm_{kind}.npy", DATA / f"{name}_{kind}.npy"):
        if cand.exists(): return str(cand)
    raise FileNotFoundError(f"{name}_{kind}.npy")

def fg_cmd(name, metric, T, ef, blocks=0):
    c = [FG, "--data", npy(name, "X"), "--queries", npy(name, "Q"), "--gold", npy(name, "gold"),
         "--metric", metric, "--T", str(T), "--harvest", str(ef), "--harvest-cap", "64",
         "--threads", str(THREADS), "--seed", str(SEED), "--ef", *EF_LADDER]
    if blocks: c += ["--harvest-blocks", str(blocks)]
    return c

def parlay_cmd(binary, name, R, L, alpha, two_pass):
    return [str(binary), "-base_path", str(DATA / f"{name}_base.fbin"), "-query_path", str(DATA / f"{name}_query.fbin"),
            "-gt_path", str(DATA / f"{name}_gt100"), "-file_type", "bin", "-data_type", "float",
            "-dist_func", "Euclidian", "-R", str(R), "-L", str(L), "-alpha", str(alpha),
            "-two_pass", str(two_pass), "-k", "10"]

SYSTEMS = {
  "glove": {
    "graft-T32-ef600":       fg_cmd("glove", "cosine", 32, 600),
    "graft-T16-ef400":       fg_cmd("glove", "cosine", 16, 400),
    "fgraft-T8-ef400-B8":    fg_cmd("glove", "cosine", 8, 400, 8),
    "fgraft-T8-ef400-B32":   fg_cmd("glove", "cosine", 8, 400, 32),
    "vamana-R100-L200-a1.0-2pass": parlay_cmd(VAMANA, "glove", 100, 200, 1.0, 1),
    "pipnn-R100-L200":       parlay_cmd(PIPNNB, "glove", 100, 200, 1.0, 0),
    "hnswlib-M16": ("hnsw", 16), "hnswlib-M32": ("hnsw", 32),
  },
  "sift": {
    "graft-T4-ef400":        fg_cmd("sift", "l2", 4, 400),
    "graft-T16-ef400":       fg_cmd("sift", "l2", 16, 400),
    "fgraft-T4-ef400-B8":    fg_cmd("sift", "l2", 4, 400, 8),
    "fgraft-T2-ef400-B8":    fg_cmd("sift", "l2", 2, 400, 8),
    "fgraft-T4-ef400-B32":   fg_cmd("sift", "l2", 4, 400, 32),
    "vamana-R64-L128-a1.15-2pass": parlay_cmd(VAMANA, "sift", 64, 128, 1.15, 1),
    "pipnn-R64-L128":        parlay_cmd(PIPNNB, "sift", 64, 128, 1.15, 0),
    "hnswlib-M16": ("hnsw", 16), "hnswlib-M32": ("hnsw", 32),
  },
}
def dense_cmd(name, metric, L, m, C, prune, alpha):
    return [FG, "--data", npy(name, "X"), "--queries", npy(name, "Q"), "--gold", npy(name, "gold"),
            "--metric", metric, "--T", "1", "--harvest", "400", "--harvest-cap", "64", "--harvest-alpha", str(alpha),
            "--dense", str(L), "--dense-m", str(m), "--dense-C", str(C), "--dense-prune", str(prune),
            "--threads", str(THREADS), "--seed", str(SEED), "--ef", *EF_LADDER]

# Phase 1b: the dense (search-free) construction against the baselines it must beat.
SYSTEMS_DENSE = {
  "glove": {
    "dense-L240-m5-C200-p1":     dense_cmd("glove", "cosine", 240, 5, 200, 1, 1.0),
    "vamana-R100-L200-a1.0-2pass": parlay_cmd(VAMANA, "glove", 100, 200, 1.0, 1),
    "hnswlib-M16": ("hnsw", 16),
  },
  "sift": {
    "dense-L240-m5-C200-p1-a1.0":  dense_cmd("sift", "l2", 240, 5, 200, 1, 1.0),
    "dense-L240-m5-C200-p1-a1.15": dense_cmd("sift", "l2", 240, 5, 200, 1, 1.15),
    "vamana-R64-L128-a1.15-2pass": parlay_cmd(VAMANA, "sift", 64, 128, 1.15, 1),
    "graft-T4-ef400":              fg_cmd("sift", "l2", 4, 400),
  },
}
# Campaign 2026-09-22 (R1): re-pair the dense arms on the FINAL kernel --
# symmetric scan (TB=128) + blocked SAT spine. Phase 1b's numbers were taken
# on the one-sided kernel; the graph is byte-identical, so only the build
# times move. Both spine settings are paired because the paper reports both
# (the spine is the connectivity guarantee; on GloVe it is insurance).
def dense2(name, metric, L, spine=1, alpha=1.0):
    c = dense_cmd(name, metric, L, 5, 200, 1, alpha)
    return c + ["--dense-spine", str(spine)]

SYSTEMS_DENSE2 = {
  "glove": {
    "dense-L240-spine1":           dense2("glove", "cosine", 240, 1),
    "dense-L240-spine0":           dense2("glove", "cosine", 240, 0),
    "vamana-R100-L200-a1.0-2pass": parlay_cmd(VAMANA, "glove", 100, 200, 1.0, 1),
    # no hnswlib arm: the module is absent on d0 and the baseline is unaffected
    # by the kernel work -- its paired HL comes from Phase 1b (0.281 [0.280,0.282]).
  },
  "sift": {
    "dense-L240-spine1":           dense2("sift", "l2", 240, 1),
    "dense-L700-spine1":           dense2("sift", "l2", 700, 1),
    "dense-L1400-spine1":          dense2("sift", "l2", 1400, 1),
    "vamana-R64-L128-a1.15-2pass": parlay_cmd(VAMANA, "sift", 64, 128, 1.15, 1),
    "graft-T4-ef400":              fg_cmd("sift", "l2", 4, 400),
  },
}
# Table 3 re-pairing (2026-09-28, review): every row of paper 2's GloVe table
# from ONE paired run in the current environment -- the reviewer objected to
# the hnswlib row being carried from Phase 1b. PiPNN's command is Phase 1b's
# (its -R/-L are ignored by PiPNN; the graph is prune_degree 64), relabelled.
SYSTEMS_TABLE3 = {
  "glove": {
    "dense-L240-spine1":           dense2("glove", "cosine", 240, 1),
    "dense-L240-spine0":           dense2("glove", "cosine", 240, 0),
    "vamana-R100-L200-a1.0-2pass": parlay_cmd(VAMANA, "glove", 100, 200, 1.0, 1),
    "graft-T32-ef600":             fg_cmd("glove", "cosine", 32, 600),
    "pipnn-defaults-d64":          parlay_cmd(PIPNNB, "glove", 100, 200, 1.0, 0),
    "hnswlib-M16": ("hnsw", 16),
  },
}
if os.environ.get("ARMSET") == "table3": SYSTEMS = SYSTEMS_TABLE3
if os.environ.get("ARMSET") == "dense": SYSTEMS = SYSTEMS_DENSE
if os.environ.get("ARMSET") == "dense2": SYSTEMS = SYSTEMS_DENSE2
METRIC_H = {"glove": "cosine", "sift": "l2"}

RE = dict(
  trees=re.compile(r"trees ([0-9.]+)s \(\d+ threads\), ([0-9.]+)M dist"),
  overlay=re.compile(r"overlay\+backlinks ([0-9.]+)s"),
  harvest=re.compile(r"harvest ef=\d+.*? ([0-9.]+)s\n"),
  edges=re.compile(r"edges: (\d+) directed \(([0-9.]+)/vertex, max (\d+)\)"),
  compl=re.compile(r"local completeness \(k=10, sample\): ([0-9.]+)"),
  fg_ladder=re.compile(r"^\s+(\d+)\s+([0-9.]+)\s+(\d+)\s+\d+\s*$", re.M),
  parlay_built=re.compile(r"Graph built in ([0-9.]+) seconds"),
  parlay_dist=re.compile(r"BUILD_DISTANCES (\d+)"),
  parlay_ladder=re.compile(r"recall = ([0-9.]+), QPS = [0-9.e+]+, Q = (\d+).*?average cmps = (\d+)"),
  dense=re.compile(r"leaders ([0-9.]+)s candidates ([0-9.]+)s prune ([0-9.]+)s \(\d+ threads\), ([0-9.]+)M dist"),
)

def one_build(label, spec, X, name):
    rec = {"system": label}
    if isinstance(spec, tuple):                       # hnswlib, in-process
        import hnswlib
        idx = hnswlib.Index(space=METRIC_H[name], dim=X.shape[1])
        idx.init_index(max_elements=X.shape[0], ef_construction=200, M=spec[1], random_seed=100)
        t0 = time.perf_counter(); idx.add_items(X, num_threads=THREADS); dt = time.perf_counter() - t0
        del idx; gc.collect()
        rec.update(build_s=round(dt, 3), process_wall_s=round(dt, 2)); return rec, ""
    t0 = time.perf_counter(); p = subprocess.run(spec, capture_output=True, text=True)
    out = p.stdout + p.stderr
    rec.update(process_wall_s=round(time.perf_counter() - t0, 2), rc=p.returncode)
    if label.startswith("dense"):
        dm = RE["dense"].search(out)
        if dm:
            rec.update(leaders_s=float(dm.group(1)), candidates_s=float(dm.group(2)), prune_s=float(dm.group(3)),
                       gdist=float(dm.group(4)) / 1000)
            rec["build_s"] = round(rec["leaders_s"] + rec["candidates_s"] + rec["prune_s"], 3)
        e = RE["edges"].search(out); c = RE["compl"].search(out)
        if e: rec.update(edges=int(e.group(1)), avg_deg=float(e.group(2)), max_deg=int(e.group(3)))
        if c: rec["completeness"] = float(c.group(1))
        rec["ladder"] = [(int(a), float(r), int(d)) for a, r, d in RE["fg_ladder"].findall(out)]
    elif label.startswith(("graft", "fgraft")):
        tr, ov, hv = RE["trees"].search(out), RE["overlay"].search(out), RE["harvest"].search(out)
        if tr and hv:
            rec.update(trees_s=float(tr.group(1)), gdist=float(tr.group(2)) / 1000,
                       overlay_s=float(ov.group(1)) if ov else 0.0, harvest_s=float(hv.group(1)))
            rec["build_s"] = round(rec["trees_s"] + rec["overlay_s"] + rec["harvest_s"], 3)
        e = RE["edges"].search(out); c = RE["compl"].search(out)
        if e: rec.update(edges=int(e.group(1)), avg_deg=float(e.group(2)), max_deg=int(e.group(3)))
        if c: rec["completeness"] = float(c.group(1))
        rec["ladder"] = [(int(a), float(r), int(d)) for a, r, d in RE["fg_ladder"].findall(out)]
    else:
        m = RE["parlay_built"].search(out); d = RE["parlay_dist"].search(out)
        if m: rec["build_s"] = float(m.group(1))
        if d: rec["gdist"] = int(d.group(1)) / 1e9
        rec["ladder"] = [(int(q), float(r), int(c)) for r, q, c in RE["parlay_ladder"].findall(out)]
    if "build_s" not in rec: rec["error"] = out[-2000:]
    return rec, out

def run(name):
    import numpy as np
    systems = SYSTEMS[name]
    X = np.ascontiguousarray(np.load(npy(name, "X")), dtype=np.float32)
    rng = random.Random(SEED * 1000 + len(name)); rows = []
    outf = OUT / f"phase1{os.environ.get('TAG', '')}-{name}-d0-s{SEED}.json"
    print(f"[{name}] n={len(X)} systems={list(systems)} blocks={BLOCKS} cool={COOL}s threads={THREADS}", flush=True)
    for b in range(BLOCKS):
        order = list(systems); rng.shuffle(order)
        for pos, label in enumerate(order):
            if COOL and (b or pos): time.sleep(COOL)
            rec, out = one_build(label, systems[label], X, name)
            rec.update(block=b, pos=pos, t=time.time()); rows.append(rec)
            (OUT / f"{name}-b{b:02d}-{label}.log").write_text(out)
            fp = f" gdist {rec['gdist']:.2f}G" if "gdist" in rec else ""
            fp += f" compl {rec['completeness']:.3f}" if "completeness" in rec else ""
            print(f"[{name}] block {b} pos {pos} {label:30s} build {rec.get('build_s', float('nan')):8.1f} s"
                  f" (process {rec['process_wall_s']:.0f} s){fp}{'  ERROR' if 'error' in rec else ''}", flush=True)
            if "error" in rec: print(rec["error"][-600:], flush=True)
            json.dump({"dataset": {"name": name, "n": int(len(X)), "d": int(X.shape[1])},
                       "config": {"seed": SEED, "blocks_planned": BLOCKS, "blocks_done": b + 1, "cool_s": COOL,
                                  "threads": THREADS, "systems": {k: (list(v) if isinstance(v, tuple) else v) for k, v in systems.items()},
                                  "hnswlib_efC": 200, "hnswlib_seed": 100},
                       "results": {"rows": rows},
                       "notes": "d0 4-socket Xeon E7-4809 v3, 64 threads, otherwise idle; block = pairing unit, "
                                "seeded random order within block; stats: graft-ann/bench/paired_stats.py"},
                      open(outf, "w"), indent=1)
    print(f"[{name}] wrote {outf}", flush=True); del X; gc.collect()

if __name__ == "__main__":
    for ds in DS: run(ds)
    print("DONE", flush=True)
