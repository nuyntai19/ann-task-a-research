#!/usr/bin/env python3
"""R85-A1: matched H17 flat-C160 / flat-C64 / TwoTier-C160 ablation.

This runner reuses (and SHA-pins) the R85-0f preflight/graph parser. It never
modifies H70-H84 sources or results, and uses only a new H85/R85-A1 directory.
The H17 binary is compiled once; C64 and C160 use that SAME executable and
only change the -table_size CLI argument. Three counterbalanced rounds on
4 distinct P-cores, then quality via the pinned R72 native evaluator.

Actions:
  --selftest                   no local project files needed
  --prepare                    compile and pin H17-only flat-reservoir binary
  --dry-run                    show nine commands, do not build any ANN graph
  --run-build                  run nine SIFT1M BUILDs, preserve all graphs/logs
  --run-quality RUN_DIRECTORY  evaluate only the nine already saved graphs
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import time
from statistics import median

ROOT = Path.home() / "ann-task-a"
SOURCE = ROOT / "experiments/H70/pipnn-clean-443a328"
R85_0 = ROOT / "experiments/H85/r85_0_matched_baseline"
OUT = ROOT / "experiments/H85/r85_a1_capacity_ablation"
BUILD_H17 = OUT / "build_h17_flat"
H17_EXE = BUILD_H17 / "algorithms/PipNN/neighbors-pipnn_FLOAT_T_EUCLIDEAN"
H17_MANIFEST = OUT / "h17_binary_manifest.json"
OLD_SCRIPT = Path.home() / "Downloads/run_r85_0f_matched_sift1m.py"
OLD_SCRIPT_SHA = "1e76bef61f16a15516d88c6249a3e07e5f47f0f54b1be31c00ac8942382f2d59"
EVAL_SHA = "3c2294efa1d7fb5d89c79ca5bf9c1eaca86247f7246e6d6d7c6c94549d08ed57"
H17_ARM = {"B160", "B64"}
ARMS = ("B160", "B64", "D0")
P_CORES = (0, 2, 4, 6)
BEAMS = (10, 20, 40, 80, 160)
# Avoid accidental interpretation of a pilot heuristic as formal equivalence.
SCREEN_DELTA_RECALL = 0.001  # absolute recall = 0.1 percentage point
TIME_PATTERN = re.compile(r"R85A1_TIME wall_s=([0-9.]+) peak_rss_kib=(\d+)")
RECALL_PATTERN = re.compile(
    r"R72_RECALL_ROW beam=(\d+) recall=([0-9.Ee+-]+) "
    r"qps=([0-9.Ee+-]+) avg_cmps=([0-9.Ee+-]+) avg_visited=([0-9.Ee+-]+)"
)


def die(message):
    raise RuntimeError(message)


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def load_pinned_previous():
    if not OLD_SCRIPT.is_file() or sha256(OLD_SCRIPT) != OLD_SCRIPT_SHA:
        die("Old R85-0f runner absent/changed. Required: " + str(OLD_SCRIPT))
    spec = importlib.util.spec_from_file_location("r85_0f_pinned", OLD_SCRIPT)
    if spec is None or spec.loader is None:
        die("Cannot load pinned R85-0f runner")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run(args, *, log: Path | None = None, env=None):
    if log is None:
        p = subprocess.run(args, check=False, text=True, capture_output=True, env=env)
        if p.returncode:
            die(f"command failed rc={p.returncode}: {shlex.join(args)}\n"
                + (p.stdout + p.stderr)[-5000:])
        return p.stdout
    with log.open("w", encoding="utf-8") as f:
        f.write("# COMMAND " + shlex.join(args) + "\n")
        f.flush()
        p = subprocess.run(args, check=False, stdout=f,
                           stderr=subprocess.STDOUT, text=True, env=env, cwd=ROOT)
    if p.returncode:
        die(f"Command rc={p.returncode}; details: {log}")
    return log.read_text(encoding="utf-8", errors="replace")


def atomic_json(p: Path, data):
    temp = p.with_suffix(p.suffix + ".tmp")
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(p)


def target_commands(build_dir: Path):
    p = build_dir / "compile_commands.json"
    if not p.is_file():
        die(f"Missing compilation database {p}")
    rows = json.loads(p.read_text(encoding="utf-8"))
    commands = {}
    for e in rows:
        cmd = shlex.split(e["command"]) if e.get("command") else e.get("arguments", [])
        if not any("neighbors-pipnn_FLOAT_T_EUCLIDEAN.dir" in x for x in cmd):
            continue
        source = Path(e["file"]).name
        if source not in ("cmake_pch.hxx.cxx", "neighborsTime.C"):
            die(f"Unexpected target source in compilation database: {source}")
        if source in commands:
            die(f"Duplicate compile source entry {source}")
        commands[source] = cmd
    if set(commands) != {"cmake_pch.hxx.cxx", "neighborsTime.C"}:
        die(f"Missing PCH / neighborsTime source compile commands: {list(commands)}")
    return commands


def macro_and_flags(build_dir: Path):
    cmds = target_commands(build_dir)
    out = {}
    for key, tokens in cmds.items():
        macros = {x for x in tokens if x.startswith("-D")}
        if not {"-O3", "-DNDEBUG", "-march=native"}.issubset(set(tokens)):
            die(f"{build_dir}/{key}: missing optimized flags")
        # Exact compilers and other features must agree with D0 for both entries.
        out[key] = {
            "macros": macros,
            "controls": {x for x in tokens if x.startswith((
                "-O", "-march=", "-mtune=", "-std=", "-ffast-math", "-fopenmp", "-mavx", "-mfma"))},
            "compiler": tokens[0],
        }
    return out


def audit_h17_compiler():
    b = macro_and_flags(BUILD_H17)
    d = macro_and_flags(R85_0 / "build_d0")
    for key in b:
        bm, dm = b[key]["macros"], d[key]["macros"]
        if "-DR71_H17_TOP2=1" not in bm or "-DR70_TWO_TIER=1" in bm:
            die(f"H17-only macro mismatch: {key}")
        if {"-DR71_H17_TOP2=1", "-DR70_TWO_TIER=1"} - dm:
            die(f"D0 macro mismatch: {key}")
        # Remove only the intended Tier difference; H17 must be identical.
        if bm != dm - {"-DR70_TWO_TIER=1"}:
            die(f"Other compile-time macro difference: {key}: {bm ^ dm}")
        if b[key]["controls"] != d[key]["controls"]:
            die(f"Other optimization/language flag difference: {key}")
        if b[key]["compiler"] != d[key]["compiler"]:
            die(f"Compiler executable mismatch for {key}")
    return {"H17": "ON", "TwoTier": "OFF", "matched_to_D0": True}


def verify_b_manifest():
    if not H17_MANIFEST.is_file():
        die(f"H17 binary not pinned; run --prepare: {H17_MANIFEST}")
    m = json.loads(H17_MANIFEST.read_text(encoding="utf-8"))
    if not H17_EXE.is_file() or not os.access(H17_EXE, os.X_OK):
        die(f"Missing executable {H17_EXE}")
    if sha256(H17_EXE) != m["h17_sha256"]:
        die("Pinned H17 binary SHA changed")
    if m["d0_sha256"] != sha256(R85_0 / "build_d0/algorithms/PipNN/neighbors-pipnn_FLOAT_T_EUCLIDEAN"):
        die("D0 binary changed since H17 preparation")
    audit_h17_compiler()
    return m


def prepare(old):
    # Reuse complete validated R85-0f source/binary/dataset/CPU preflight.
    meta = old.check_inputs()
    if not shutil.which("cmake"):
        die("cmake is missing")
    OUT.mkdir(parents=True, exist_ok=True)
    if H17_MANIFEST.exists():
        m = verify_b_manifest()
        print("R85_A1_H17_ALREADY_PREPARED " + m["h17_sha256"])
        return
    if (BUILD_H17 / "CMakeCache.txt").exists():
        cache = (BUILD_H17 / "CMakeCache.txt").read_text(errors="replace")
        for expected in ("R71_USE_H17:BOOL=ON", "R70_USE_TIER:BOOL=OFF"):
            if expected not in cache:
                die("Existing H17 CMakeCache has incorrect feature options. Don't overwrite it.")
    print("R85_A1_H17_CONFIGURE_START", flush=True)
    run(["cmake", "-S", str(SOURCE), "-B", str(BUILD_H17),
         "-DCMAKE_BUILD_TYPE=Release", "-DCMAKE_EXPORT_COMPILE_COMMANDS=ON",
         "-DR71_USE_H17=ON", "-DR70_USE_TIER=OFF"],
        log=OUT / "configure_h17.log")
    print("R85_A1_H17_NATIVE_COMPILE_START", flush=True)
    run(["cmake", "--build", str(BUILD_H17), "--target",
         "neighbors-pipnn_FLOAT_T_EUCLIDEAN", "--parallel", "2"],
        log=OUT / "compile_h17.log")
    if not H17_EXE.is_file():
        die(f"No H17 executable: {H17_EXE}")
    defs = audit_h17_compiler()
    # Source must remain unchanged through CMake build.
    old.check_inputs()
    m = {
        "h17_path": str(H17_EXE), "h17_sha256": sha256(H17_EXE),
        "d0_path": str(old.BINARIES["D0"]),
        "d0_sha256": sha256(old.BINARIES["D0"]),
        "h17_feature_flags": defs, "source_head": old.EXPECTED_GIT,
        "source_sha256": meta["source_hashes"],
        "origin": "R85-A1 H17 flat C160/C64; compare to R85-0f D0 on same PC",
    }
    atomic_json(H17_MANIFEST, m)
    print("R85_A1_H17_ONLY_NATIVE_BUILD_MATCHED_PASS sha256=" + m["h17_sha256"], flush=True)
    print("R85_A1_H17_MANIFEST " + str(H17_MANIFEST), flush=True)


def schedule():
    # Latin-square: every arm appears once in each temporal position.
    orders = (("B160", "B64", "D0"),
              ("B64", "D0", "B160"),
              ("D0", "B160", "B64"))
    return [(rep, arm) for rep, order in enumerate(orders, 1) for arm in order]


def bin_and_capacity(old, arm):
    if arm == "D0":
        return old.BINARIES["D0"], 160, "TIER_B64_C160"
    if arm == "B160":
        return H17_EXE, 160, "STOCK_FLAT_C160"
    if arm == "B64":
        return H17_EXE, 64, "STOCK_FLAT_C64"
    die("Bad arm " + arm)


def build_command(old, arm: str, graph_path: Path):
    exe, cap, _ = bin_and_capacity(old, arm)
    args = old.build_cmd("D0", 4, graph_path)
    args[0] = str(exe)
    pos = args.index("-table_size")
    args[pos + 1] = str(cap)
    return args


def preflight(old):
    meta = old.check_inputs()
    b_manifest = verify_b_manifest()
    if sha256(old.EVAL) != EVAL_SHA:
        die("R72 evaluator SHA mismatch; expected " + EVAL_SHA)
    stat = os.statvfs(OUT)
    free_gib = stat.f_bavail * stat.f_frsize / 1024**3
    if free_gib < 3:
        die(f"Insufficient disk for 9 graphs: {free_gib:.2f} GiB")
    # Double-check matched CLI protocol: B160 and B64 differ solely in C.
    a = build_command(old, "B160", Path("/tmp/r85_a1.graph"))
    b = build_command(old, "B64", Path("/tmp/r85_a1.graph"))
    pa = a.index("-table_size") + 1
    pb = b.index("-table_size") + 1
    assert pa == pb
    assert [(i, v) for i, v in enumerate(a) if i != pa] == [
        (i, v) for i, v in enumerate(b) if i != pb]
    return {"pinned_previous_runner_sha256": OLD_SCRIPT_SHA,
            "h17_binary": b_manifest, "r85_0_preflight": meta,
            "evaluator_sha256": EVAL_SHA,
            "hypothesis": "Does fixed flat-C64 dominate H17+TwoTier-C160 under matched quality?",
            "protocol": {"dataset": "SIFT1M, float32 Euclidean", "threads": 4,
                         "physical_cores": list(P_CORES), "reps": 3,
                         "arms": list(ARMS), "order": [list(x) for x in [
                             ("B160", "B64", "D0"), ("B64", "D0", "B160"),
                             ("D0", "B160", "B64")]],
                         "only_changed_dimension_B160_vs_B64": "-table_size",
                         "quality": "heldout 10k query, beam 10/20/40/80/160",
                         "no_search_during_build": True}}


def build_runs(old, meta):
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    run_dir = OUT / f"runs_{stamp}"
    run_dir.mkdir(parents=True, exist_ok=False)
    meta["started_at_utc"] = dt.datetime.now(dt.timezone.utc).isoformat()
    meta["run_dir"] = str(run_dir)
    atomic_json(run_dir / "manifest.json", meta)
    rows = []
    plan = schedule()
    for n, (rep, arm) in enumerate(plan, 1):
        tag = f"t4_r{rep}_{arm}"
        graph = run_dir / f"{tag}.graph"
        log = run_dir / f"{tag}.log"
        tlog = run_dir / f"{tag}.time"
        exe, cap, reservoir_marker = bin_and_capacity(old, arm)
        env = dict(os.environ)
        env["PARLAY_NUM_THREADS"] = "4"
        cmd = ["taskset", "-c", ",".join(map(str, P_CORES)), "/usr/bin/time",
               "-f", "R85A1_TIME wall_s=%e peak_rss_kib=%M", "-o", str(tlog)] + \
              build_command(old, arm, graph)
        print(f"R85_A1_BUILD_START {n}/9 tag={tag} C={cap}", flush=True)
        before = time.perf_counter()
        output = run(cmd, log=log, env=env)
        host_wall = time.perf_counter() - before
        if f"R70_RESERVOIR_VARIANT={reservoir_marker}" not in output:
            die(f"Wrong reservoir provenance in {log}")
        if "R71_SELECTION_VARIANT=H17_PACKED_TOP2" not in output:
            die(f"Wrong selection provenance in {log}")
        timed = TIME_PATTERN.search(tlog.read_text())
        if timed is None:
            die(f"Missing wall/rss metrics {tlog}")
        wall, rss = float(timed.group(1)), int(timed.group(2))
        graph_info = old.check_graph(graph)
        row = {"tag": tag, "threads": 4, "rep": rep, "arm": arm,
               "capacity": cap, "binary_sha256": sha256(exe),
               "wall_s": wall, "peak_rss_kib": rss,
               "host_wall_s": round(host_wall, 3),
               "log": str(log), "graph": str(graph), **graph_info}
        rows.append(row)
        atomic_json(run_dir / "build_results.json", rows)
        print(f"R85_A1_BUILD_PASS tag={tag} wall_s={wall:.3f} "
              f"peakRSS_KiB={rss} arcs={graph_info['arcs']} "
              f"graph_sha256={graph_info['graph_sha256']}", flush=True)
    summary = summarize_build(rows)
    atomic_json(run_dir / "build_summary.json", summary)
    print("R85_A1_ALL_9_BUILDS_AND_STRUCTURAL_SCREENS_PASS", flush=True)
    print("R85_A1_BUILD_SUMMARY " + json.dumps(summary, ensure_ascii=False), flush=True)
    print("R85_A1_RESULTS_DIR " + str(run_dir), flush=True)


def summarize_build(rows):
    out = {}
    for arm in ARMS:
        data = [r for r in rows if r["arm"] == arm]
        if len(data) != 3:
            die("Missing 3 BUILD reps for " + arm)
        out[arm] = {
            "median_wall_s": median(r["wall_s"] for r in data),
            "median_peak_rss_kib": median(r["peak_rss_kib"] for r in data),
            "median_arcs": median(r["arcs"] for r in data),
            "all_wall_s": [r["wall_s"] for r in data],
            "all_peak_rss_kib": [r["peak_rss_kib"] for r in data],
        }
    for left, right in (("B64", "D0"), ("B160", "D0"), ("B64", "B160")):
        out[f"{left}_vs_{right}"] = {
            "wall_pct": 100 * (out[left]["median_wall_s"] / out[right]["median_wall_s"] - 1),
            "rss_pct": 100 * (out[left]["median_peak_rss_kib"] / out[right]["median_peak_rss_kib"] - 1),
        }
    out["status"] = "BUILD_PASS_PENDING_QUALITY_AND_MATCHED_RECALL"
    return out


def quality(old, run_dir: Path):
    if run_dir.parent.resolve() != OUT.resolve():
        die("Quality input must be a run directly inside the R85-A1 output directory")
    expected_manifest = run_dir / "manifest.json"
    results = run_dir / "build_results.json"
    summary = run_dir / "build_summary.json"
    if not expected_manifest.is_file() or not results.is_file() or not summary.is_file():
        die("Missing complete R85-A1 BUILD manifest/results/summary")
    rows = json.loads(results.read_text())
    if len(rows) != 9 or [(r["rep"], r["arm"]) for r in rows] != schedule():
        die("Invalid count/order in R85-A1 BUILD results")
    m = preflight(old)
    qdir = run_dir / "quality"
    if qdir.exists():
        die("Quality directory already exists; will not overwrite: " + str(qdir))
    # Verify all graphs before executing the first SEARCH.
    for r in rows:
        p = Path(r["graph"])
        if not p.is_file() or sha256(p) != r["graph_sha256"]:
            die(f"Graph SHA changed: {p}")
        exe, cap, _ = bin_and_capacity(old, r["arm"])
        if sha256(exe) != r["binary_sha256"] or r["capacity"] != cap:
            die("Binary/capacity provenance mismatch for " + r["tag"])
    qdir.mkdir()
    metrics = []
    for i, r in enumerate(rows, 1):
        env = dict(os.environ)
        env["PARLAY_NUM_THREADS"] = "4"
        cmd = ["taskset", "-c", ",".join(map(str, P_CORES)), str(old.EVAL),
               r["graph"], str(old.DATA_FILES["base"][0]),
               str(old.DATA_FILES["query"][0]), str(old.DATA_FILES["gt"][0])]
        log = qdir / (r["tag"] + ".log")
        print(f"R85_A1_QUALITY_START {i}/9 tag={r['tag']}", flush=True)
        output = run(cmd, log=log, env=env)
        if "R72_RECALL_INPUT_PASS" not in output or "R72_RECALL_EVAL_PASS" not in output:
            die("Evaluator incomplete for " + r["tag"])
        matches = RECALL_PATTERN.findall(output)
        if len(matches) != 5 or set(int(x[0]) for x in matches) != set(BEAMS):
            die(f"Wrong number of beams for {r['tag']}")
        for beam, recall, qps, cmp_, visit in matches:
            entry = {"tag": r["tag"], "rep": r["rep"], "arm": r["arm"],
                     "beam": int(beam), "recall": float(recall),
                     "qps": float(qps), "avg_cmps": float(cmp_),
                     "avg_visited": float(visit)}
            if not 0 <= entry["recall"] <= 1 or not all(math.isfinite(entry[k]) and entry[k] > 0 for k in ("qps", "avg_cmps", "avg_visited")):
                die("Invalid evaluator metrics for " + r["tag"])
            metrics.append(entry)
        atomic_json(qdir / "quality_results.json", metrics)
        print(f"R85_A1_QUALITY_PASS tag={r['tag']} beams=5", flush=True)
    means = summarize_quality(metrics)
    atomic_json(qdir / "quality_medians.json", means)
    print("R85_A1_ALL_9_SEARCH_PASS_RECALL_REQUIRES_INTERPRETATION", flush=True)
    print("R85_A1_QUALITY_SUMMARY " + str(qdir / "quality_medians.json"), flush=True)
    print("R85_A1_RECALL_DELTAS_PP_BY_BEAM " + json.dumps([
        {"beam": x["beam"], "B64_minus_D0_pp": x["B64_minus_D0_recall_pp"],
         "B160_minus_D0_pp": x["B160_minus_D0_recall_pp"]} for x in means]), flush=True)


def summarize_quality(rows):
    out = []
    for beam in BEAMS:
        d = {"threads": 4, "beam": beam}
        for arm in ARMS:
            q = [r for r in rows if r["arm"] == arm and r["beam"] == beam]
            if len(q) != 3:
                die("Missing three quality runs for arm=" + arm + " beam=" + str(beam))
            for metric in ("recall", "qps", "avg_cmps", "avg_visited"):
                d[f"{arm}_{metric}_median"] = median(r[metric] for r in q)
            d[f"{arm}_recall_spread"] = [r["recall"] for r in q]
        for arm in ("B64", "B160"):
            d[f"{arm}_minus_D0_recall_pp"] = 100 * (d[f"{arm}_recall_median"] - d["D0_recall_median"])
            d[f"{arm}_vs_D0_cmps_ratio"] = d[f"{arm}_avg_cmps_median"] / d["D0_avg_cmps_median"]
        out.append(d)
    return out


def selftest():
    assert len(schedule()) == 9
    assert sorted([x[1] for x in schedule()]).count("D0") == 3
    assert [arm for r, arm in schedule() if r == 1] == ["B160", "B64", "D0"]
    assert [arm for r, arm in schedule() if r == 3] == ["D0", "B160", "B64"]
    assert all(sorted([arm for r, arm in schedule() if r == k]) == sorted(ARMS) for k in (1,2,3))
    fake = []
    for rep, arm in schedule():
        fake.append({"rep": rep, "arm": arm, "wall_s": 30+rep, "peak_rss_kib": 1000000+rep, "arcs": 100000})
    assert set(summarize_build(fake)) >= set(ARMS)
    print("R85_A1_SELFTEST_PASS")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--selftest", action="store_true")
    g.add_argument("--prepare", action="store_true")
    g.add_argument("--dry-run", action="store_true")
    g.add_argument("--run-build", action="store_true")
    g.add_argument("--run-quality", metavar="R85_A1_RUN_DIRECTORY", type=Path)
    args = p.parse_args()
    if args.selftest:
        selftest(); return
    old = load_pinned_previous()
    if args.prepare:
        prepare(old); return
    meta = preflight(old)
    print("R85_A1_PINNED_SOURCE_H17_D0_DATA_CPU_EVALUATOR_PASS", flush=True)
    if args.dry_run:
        for i, (rep, arm) in enumerate(schedule(), 1):
            exe, cap, _ = bin_and_capacity(old, arm)
            cmd = ["taskset", "-c", ",".join(map(str, P_CORES)),
                   "env", "PARLAY_NUM_THREADS=4"] + build_command(
                       old, arm, Path(f"<new_run>/t4_r{rep}_{arm}.graph"))
            print(f"[{i}/9] arm={arm} cap={cap} exe_sha={sha256(exe)} " + shlex.join(cmd))
        print("R85_A1_DRY_RUN_PASS_NO_ANN_BUILD_NO_SEARCH")
    elif args.run_build:
        build_runs(old, meta)
    else:
        quality(old, args.run_quality.resolve())


if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError, ValueError, AssertionError, KeyError, TypeError) as exc:
        print("R85_A1_FAIL_CLOSED " + repr(exc), file=sys.stderr)
        sys.exit(1)
