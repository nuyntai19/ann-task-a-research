#!/usr/bin/env python3
"""R85-0f: pinned Stock vs D0 SIFT1M benchmark on physical P-cores.

Read-only with respect to H70/H84 sources and artifacts. Writes only to
experiments/H85/r85_0_matched_baseline/runs_<timestamp>/.
"""
from __future__ import annotations

import argparse
import array
import csv
import datetime as dt
import hashlib
import json
import os
import pathlib
import re
import shlex
import shutil
import struct
import subprocess
import sys
import time
from statistics import median

ROOT = pathlib.Path.home() / "ann-task-a"
BASEOUT = ROOT / "experiments/H85/r85_0_matched_baseline"
SRC = ROOT / "experiments/H70/pipnn-clean-443a328"
BINNAME = "neighbors-pipnn_FLOAT_T_EUCLIDEAN"
BINARIES = {
    "A": BASEOUT / "build_stock/algorithms/PipNN" / BINNAME,
    "D0": BASEOUT / "build_d0/algorithms/PipNN" / BINNAME,
}
EXPECTED_BINARY_SHA = {
    "A": "e07853b3e1832e2d9a95d6ed8ed6660bf34bc719dffcfd78789f6f672c6a05a5",
    "D0": "5e4620d45c0d43c091038c3edac2b863983310b4e40a970943a307db87950d9b",
}
EXPECTED_SOURCE = {
    "algorithms/PipNN/pipnn.h": "f4391ad8712d7757423dca872f9042c3271660dffde384a85b93854b9692f288",
    "algorithms/PipNN/pipnn_utils.h": "7083e8183554a1cb586b70cdb4c57920f49ec5a50680096aecf6b873f596595d",
}
EXPECTED_GIT = "443a328dc71a3b7be753d52ca2b3c9a4ba77f3fd"
CORE_SETS = {4: [0, 2, 4, 6], 6: [0, 2, 4, 6, 8, 10]}
DATA_FILES = {
    "base": (ROOT / "data/sift1m.fbin", 1000000, 128, 4),
    "query": (ROOT / "data/sift1m_queries.fbin", 10000, 128, 4),
    "gt": (ROOT / "data/sift1m_gt.ibin", 10000, 100, 8),
}
EVAL = ROOT / "experiments/H70/build-r70/algorithms/PipNN/r72_graph_recall"
BEAMS = (10, 20, 40, 80, 160)
TIME_PATTERN = re.compile(r"R85_TIME wall_s=([0-9.]+) peak_rss_kib=(\d+)")
RECALL_PATTERN = re.compile(r"R72_RECALL_ROW beam=(\d+) recall=([0-9.Ee+-]+) qps=([0-9.Ee+-]+) avg_cmps=([0-9.Ee+-]+) avg_visited=([0-9.Ee+-]+)")


def fail(msg: str) -> None:
    raise RuntimeError(msg)


def sha256(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def run_capture(args: list[str], **kwargs) -> str:
    proc = subprocess.run(args, text=True, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, **kwargs)
    if proc.returncode:
        fail(f"Command failed {proc.returncode}: {shlex.join(args)}\n{proc.stderr[-3000:]}")
    return proc.stdout.strip()


def check_inputs() -> dict:
    for prog in ("taskset", "/usr/bin/time"):
        if not shutil.which(prog):
            fail(f"Missing command: {prog}")
    if run_capture(["git", "-C", str(SRC), "rev-parse", "HEAD"]) != EXPECTED_GIT:
        fail("H70 Git HEAD changed")
    sources = {}
    for rel, expected in EXPECTED_SOURCE.items():
        path = SRC / rel
        got = sha256(path)
        if got != expected:
            fail(f"Pinned source mismatch {rel}: {got} != {expected}")
        sources[rel] = got
    # Additional potentially dirty H70 files are preserved, never reset.
    hashes = {}
    for arm, path in BINARIES.items():
        if not path.is_file() or not os.access(path, os.X_OK):
            fail(f"Missing executable: {path}")
        got = sha256(path)
        if got != EXPECTED_BINARY_SHA[arm]:
            fail(f"Binary SHA mismatch for {arm}: {got}")
        hashes[arm] = got

    # Verify the actual compiler command for both arms, not only CMake cache.
    defs = {}
    common_flags = None
    for arm, subdir in (("A", "build_stock"), ("D0", "build_d0")):
        p = BASEOUT / subdir / "compile_commands.json"
        commands = json.loads(p.read_text())
        matched = [e for e in commands if
                   "neighbors-pipnn_FLOAT_T_EUCLIDEAN.dir" in
                   e.get("command", " ".join(e.get("arguments", [])))]
        if len(matched) < 2:
            fail(f"Missing target compile commands for {arm}")
        flagsets = []
        for e in matched:
            toks = shlex.split(e["command"]) if e.get("command") else e["arguments"]
            d = {x for x in toks if x.startswith("-D")}
            flagsets.append(d)
            has_h17 = "-DR71_H17_TOP2=1" in d
            has_tier = "-DR70_TWO_TIER=1" in d
            if has_h17 != (arm == "D0") or has_tier != (arm == "D0"):
                fail(f"{arm}: feature-flag mismatch")
            if not {"-O3", "-march=native", "-DNDEBUG"}.issubset(set(toks)):
                fail(f"{arm}: optimized compiler flags missing")
        defs[arm] = flagsets
    # Compare non-experimental feature macros across both arms.
    for i in range(2):
        common_a = {x for x in defs["A"][i] if not x.startswith(("-DR70_TWO_TIER", "-DR71_H17_TOP2"))}
        common_d = {x for x in defs["D0"][i] if not x.startswith(("-DR70_TWO_TIER", "-DR71_H17_TOP2"))}
        if common_a != common_d:
            fail(f"Compiler macro mismatch beyond experimental flags in entry {i}")

    dataset_meta = {}
    for name, (path, n_expected, d_expected, bytes_per_item) in DATA_FILES.items():
        with path.open("rb") as f:
            head = f.read(8)
        if len(head) != 8:
            fail(f"Truncated header: {path}")
        n, d = struct.unpack("<II", head)
        expected_size = 8 + n_expected * d_expected * bytes_per_item
        if (n, d, path.stat().st_size) != (n_expected, d_expected, expected_size):
            fail(f"Unexpected shape/size: {path}: {n},{d},{path.stat().st_size}")
        dataset_meta[name] = {"path": str(path), "rows": n, "cols": d,
                              "bytes": expected_size, "sha256": sha256(path)}

    # GT is two consecutive blocks: n*k uint32 IDs, then n*k float32 distances.
    # Verify the ID block, not the distinct floating point distance block.
    with DATA_FILES["gt"][0].open("rb") as f:
        f.seek(8)
        remaining = 10000 * 100
        while remaining:
            count = min(remaining, 131072)
            ids = array.array("I")
            ids.frombytes(f.read(4 * count))
            if sys.byteorder != "little":
                ids.byteswap()
            if len(ids) != count or max(ids) >= 1000000:
                fail("GT ID block invalid or contains out-of-range IDs")
            remaining -= count

    cpus_needed = set(CORE_SETS[6])
    allowed = os.sched_getaffinity(0)
    if not cpus_needed.issubset(allowed):
        fail(f"P-core CPU IDs not in allowed affinity set: {sorted(cpus_needed-allowed)}")
    seen = set()
    for cpu in CORE_SETS[6]:
        base = pathlib.Path(f"/sys/devices/system/cpu/cpu{cpu}/topology")
        package = int((base / "physical_package_id").read_text().strip())
        core = int((base / "core_id").read_text().strip())
        if (package, core) in seen:
            fail("Selected CPUs share a physical core")
        seen.add((package, core))

    stat = os.statvfs(BASEOUT)
    free_gib = stat.f_bavail * stat.f_frsize / (1024 ** 3)
    if free_gib < 5:
        fail(f"Insufficient disk free: {free_gib:.2f} GiB (need >=5 GiB)")
    # Fail early rather than risking OOM. Previous Stock RSS ~2.8GiB.
    memavail = 0
    for line in pathlib.Path("/proc/meminfo").read_text().splitlines():
        if line.startswith("MemAvailable:"):
            memavail = int(line.split()[1])
    if memavail < 6 * 1024 * 1024:
        fail(f"MemAvailable too low: {memavail} KiB")
    return {"source_head": EXPECTED_GIT, "source_hashes": sources,
            "binaries": hashes, "datasets": dataset_meta,
            "cpu_sets": CORE_SETS, "free_disk_gib": round(free_gib, 2),
            "available_memory_kib": memavail}


def build_cmd(arm: str, threads: int, graph_path: pathlib.Path) -> list[str]:
    # Exact R72 config recorded in project Google Doc, 04-05 Nov 2026.
    # No query/GT arguments means BUILD-only (point_range nullptr => size 0).
    return [
        str(BINARIES[arm]),
        "-base_path", str(DATA_FILES["base"][0]),
        "-graph_outfile", str(graph_path),
        "-num_clusters", "2",
        "-cluster_size", "1024",
        "-top_level_leaders", "100",
        "-fanout_scheme", "10,3,1",
        "-mst_deg", "2",
        "-prune", "1",
        "-prune_all", "1",
        "-prune_degree", "64",
        "-table_size", "160",
        "-hash_bits", "12",
        "-alpha", "1.1",
        "-k", "0",
    ]


def check_graph(p: pathlib.Path) -> dict:
    with p.open("rb") as f:
        header = f.read(8)
        if len(header) != 8:
            fail(f"Bad graph header: {p}")
        n, dg = struct.unpack("<II", header)
        if (n, dg) != (1000000, 64):
            fail(f"Graph n/maxdegree mismatch: {p}: {n},{dg}")
        sizes = array.array("I")
        sizes.fromfile(f, n)
        if sys.byteorder != "little":
            sizes.byteswap()
        if any(x > dg for x in sizes):
            fail(f"Invalid outdegree in {p}")
        arc_count = sum(sizes)
        if arc_count < n:
            fail(f"Suspiciously sparse graph in {p}: {arc_count}")
        expected_size = 8 + 4 * n + 4 * arc_count
        if p.stat().st_size != expected_size:
            fail(f"Graph file length mismatch: {p}, expected {expected_size}")
        edges = array.array("I")
        edges.fromfile(f, arc_count)
        if sys.byteorder != "little":
            edges.byteswap()
        if edges and max(edges) >= n:
            fail(f"Edge destination out of bounds in {p}")
    return {"nodes": n, "degree_bound": dg, "arcs": arc_count,
            "bytes": expected_size, "graph_sha256": sha256(p),
            "screen": "PASS_HEADER_DEGREE_BOUNDS_EDGE_IDS_AND_LENGTH"}


def write_json(path: pathlib.Path, value) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w") as f:
        json.dump(value, f, indent=2, ensure_ascii=False)
        f.write("\n")
    tmp.replace(path)


def cases():
    # Counterbalanced 3 rounds per CPU configuration.
    for threads in (4, 6):
        for round_number, order in ((1, ("A", "D0")),
                                    (2, ("D0", "A")),
                                    (3, ("A", "D0"))):
            for arm in order:
                yield threads, round_number, arm


def run_build(meta: dict) -> None:
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    run_dir = BASEOUT / ("runs_" + stamp)
    run_dir.mkdir(parents=True, exist_ok=False)
    meta["started_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
    meta["run_dir"] = str(run_dir)
    meta["protocol"] = {"arms": ["A", "D0"], "threads": [4, 6],
                        "reps": 3, "order": "A-D0/D0-A/A-D0",
                        "query_during_build": False,
                        "source": "R72 SIFT1M config; reproducibility rerun on new CPU"}
    write_json(run_dir / "manifest.json", meta)
    rows = []
    schedule = list(cases())
    for idx, (threads, rep, arm) in enumerate(schedule, start=1):
        tag = f"t{threads}_r{rep}_{arm}"
        graph = run_dir / (tag + ".graph")
        log = run_dir / (tag + ".log")
        metric = run_dir / (tag + ".time")
        affinity = ",".join(map(str, CORE_SETS[threads]))
        env = dict(os.environ)
        env["PARLAY_NUM_THREADS"] = str(threads)
        cmd = ["taskset", "-c", affinity,
               "/usr/bin/time", "-f", "R85_TIME wall_s=%e peak_rss_kib=%M",
               "-o", str(metric)] + build_cmd(arm, threads, graph)
        print(f"R85_0F_BUILD_START {idx}/{len(schedule)} tag={tag} "
              f"cpus={affinity}", flush=True)
        start = time.perf_counter()
        with log.open("w") as f:
            f.write("# R85_CMD " + shlex.join(cmd) + "\n")
            f.flush()
            p = subprocess.run(cmd, env=env, stdout=f, stderr=subprocess.STDOUT,
                               cwd=str(ROOT))
        wall_host = time.perf_counter() - start
        if p.returncode:
            fail(f"BUILD FAILED for {tag} rc={p.returncode}; see {log}. "
                 "No source or historical files were modified.")
        output = log.read_text(errors="replace")
        expected_reservoir = ("STOCK_FLAT_C160" if arm == "A" else "TIER_B64_C160")
        expected_select = ("STOCK_HIGHWAY" if arm == "A" else "H17_PACKED_TOP2")
        if f"R70_RESERVOIR_VARIANT={expected_reservoir}" not in output:
            fail(f"Wrong R70 provenance in {log}")
        if f"R71_SELECTION_VARIANT={expected_select}" not in output:
            fail(f"Wrong R71 provenance in {log}")
        txt = metric.read_text()
        m = TIME_PATTERN.search(txt)
        if not m:
            fail(f"Missing /usr/bin/time metrics for {tag}: {txt}")
        wall, rss = float(m.group(1)), int(m.group(2))
        info = check_graph(graph)
        row = {"tag": tag, "threads": threads, "rep": rep,
               "arm": arm, "cpus": affinity, "wall_s": wall,
               "peak_rss_kib": rss, "host_wall_s": round(wall_host, 3),
               "graph": str(graph), "log": str(log), **info}
        rows.append(row)
        write_json(run_dir / "build_results.json", rows)
        print(f"R85_0F_BUILD_PASS tag={tag} wall_s={wall:.2f} "
              f"peakRSS_KiB={rss} arcs={info['arcs']} "
              f"graph_sha256={info['graph_sha256']}", flush=True)

    report = make_summary(rows)
    write_json(run_dir / "build_summary.json", report)
    print("R85_0F_ALL_12_BUILDS_AND_STRUCTURAL_SCREENS_PASS", flush=True)
    print("R85_0F_BUILD_SUMMARY " + json.dumps(report, ensure_ascii=False), flush=True)
    print(f"R85_0F_RESULTS_DIR {run_dir}", flush=True)


def make_summary(rows: list[dict]) -> dict:
    result = {}
    for threads in (4, 6):
        out = {}
        for arm in ("A", "D0"):
            subset = [r for r in rows if r["threads"] == threads and r["arm"] == arm]
            if len(subset) != 3:
                fail(f"Missing rows for t{threads} {arm}")
            out[arm] = {"median_wall_s": median(r["wall_s"] for r in subset),
                        "median_peak_rss_kib": median(r["peak_rss_kib"] for r in subset),
                        "median_arcs": median(r["arcs"] for r in subset)}
        out["D0_vs_A"] = {
            "wall_change_pct": 100 * (out["D0"]["median_wall_s"] / out["A"]["median_wall_s"] - 1),
            "rss_change_pct": 100 * (out["D0"]["median_peak_rss_kib"] / out["A"]["median_peak_rss_kib"] - 1),
        }
        result[str(threads)] = out
    for arm in ("A", "D0"):
        result[f"scale_4_to_6_{arm}"] = result["4"][arm]["median_wall_s"] / result["6"][arm]["median_wall_s"]
    result["status"] = "BUILD_PASS_PENDING_RECALL"
    return result


def run_quality(run_dir: pathlib.Path) -> None:
    if not EVAL.is_file() or not os.access(EVAL, os.X_OK):
        fail(f"SIFT1M evaluator missing: {EVAL}")
    rows = json.loads((run_dir / "build_results.json").read_text())
    if len(rows) != 12:
        fail("Need all 12 verified BUILD results before quality")
    report = []
    qual_dir = run_dir / "quality"
    if qual_dir.exists():
        fail(f"Quality folder exists; won't overwrite: {qual_dir}")
    qual_dir.mkdir()
    for idx, row in enumerate(rows, 1):
        graph = pathlib.Path(row["graph"])
        if sha256(graph) != row["graph_sha256"]:
            fail(f"Graph hash changed: {graph}")
        tag = row["tag"]
        log = qual_dir / f"{tag}.log"
        affinity = row["cpus"]
        cmd = ["taskset", "-c", affinity, str(EVAL), str(graph),
               str(DATA_FILES["base"][0]), str(DATA_FILES["query"][0]),
               str(DATA_FILES["gt"][0])]
        env = dict(os.environ)
        env["PARLAY_NUM_THREADS"] = str(row["threads"])
        print(f"R85_0F_QUALITY_START {idx}/12 tag={tag}", flush=True)
        with log.open("w") as f:
            f.write("# R85_CMD " + shlex.join(cmd) + "\n")
            f.flush()
            p = subprocess.run(cmd, env=env, stdout=f, stderr=subprocess.STDOUT,
                               cwd=str(ROOT))
        output = log.read_text(errors="replace")
        if p.returncode or "R72_RECALL_EVAL_PASS" not in output:
            fail(f"Quality evaluation failed for {tag}; see {log}")
        found = RECALL_PATTERN.findall(output)
        if len(found) != 5 or {int(x[0]) for x in found} != set(BEAMS):
            fail(f"Missing recall rows for {tag}; see {log}")
        for beam, recall, qps, cmp_, visited in found:
            rr = {"tag": tag, "threads": row["threads"], "rep": row["rep"],
                  "arm": row["arm"], "beam": int(beam),
                  "recall": float(recall), "qps": float(qps),
                  "avg_cmps": float(cmp_), "avg_visited": float(visited)}
            if not 0 <= rr["recall"] <= 1 or rr["qps"] <= 0:
                fail(f"Quality numbers invalid for {tag}")
            report.append(rr)
        write_json(qual_dir / "quality_results.json", report)
        print(f"R85_0F_QUALITY_PASS tag={tag} beams=5", flush=True)
    medians = []
    for threads in (4, 6):
        for beam in BEAMS:
            item = {"threads": threads, "beam": beam}
            for arm in ("A", "D0"):
                data = [r for r in report if r["threads"] == threads and
                        r["arm"] == arm and r["beam"] == beam]
                if len(data) != 3:
                    fail("Missing quality records")
                item[f"{arm}_recall_median"] = median(r["recall"] for r in data)
                item[f"{arm}_qps_median"] = median(r["qps"] for r in data)
            item["delta_recall_D0_minus_A"] = item["D0_recall_median"] - item["A_recall_median"]
            medians.append(item)
    write_json(qual_dir / "quality_medians.json", medians)
    print("R85_0F_ALL_12_SEARCH_PASS_RECALL_REQUIRES_INTERPRETATION", flush=True)
    print(f"R85_0F_QUALITY_SUMMARY {qual_dir/'quality_medians.json'}", flush=True)


def selftest() -> None:
    assert len(list(cases())) == 12
    assert list(cases())[:4] == [(4,1,"A"),(4,1,"D0"),(4,2,"D0"),(4,2,"A")]
    assert list(cases())[-2:] == [(6,3,"A"),(6,3,"D0")]
    assert len(build_cmd("A", 4, pathlib.Path("/tmp/test.graph"))) > 20
    print("R85_0F_SELFTEST_PASS")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_mutually_exclusive_group(required=True)
    actions.add_argument("--selftest", action="store_true")
    actions.add_argument("--dry-run", action="store_true")
    actions.add_argument("--run-build", action="store_true")
    actions.add_argument("--run-quality", type=pathlib.Path, metavar="RUN_DIRECTORY")
    args = parser.parse_args()
    if args.selftest:
        selftest()
        return
    if args.run_quality is not None:
        run_quality(args.run_quality.resolve())
        return
    meta = check_inputs()
    if args.dry_run:
        print("R85_0F_PINNED_SOURCE_BINARY_DATA_CPU_STORAGE_PASS")
        print("R85_0F_DRY_RUN_NO_BUILD_NO_SEARCH")
        for i, (threads, rep, arm) in enumerate(cases(), 1):
            affinity = ",".join(map(str, CORE_SETS[threads]))
            fake_graph = BASEOUT / f"<new_run_dir>/t{threads}_r{rep}_{arm}.graph"
            print(f"[{i:02d}] CPUs={affinity} threads={threads} arm={arm} "
                  + shlex.join(build_cmd(arm, threads, fake_graph)))
        return
    if args.run_build:
        print("R85_0F_PINNED_SOURCE_BINARY_DATA_CPU_STORAGE_PASS", flush=True)
        run_build(meta)


if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError, ValueError, AssertionError) as exc:
        print(f"R85_0F_FAIL_CLOSED {type(exc).__name__}: {exc}", file=sys.stderr)
        sys.exit(1)
