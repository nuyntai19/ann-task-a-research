#!/usr/bin/env python3
"""R74.2: validate & SEARCH-evaluate eight saved SIFT1M CPU-affinity graphs.

READ-ONLY for all input graphs, manifests, source, binaries. Writes only to a
previously non-existent --out directory. No BUILD. Results are descriptive.
"""
from __future__ import annotations

import argparse
from datetime import datetime
import importlib.util
import json
import math
import os
from pathlib import Path
import re
from statistics import median
import subprocess
import sys

ARMS = ("A_stock", "D_h17_tier")
MODES = ("U", "P")
BEAMS = (10, 20, 40, 80, 160)
SCHEDULE = (
    "r1_U_A_stock", "r1_P_A_stock", "r1_P_D_h17_tier", "r1_U_D_h17_tier",
    "r2_U_D_h17_tier", "r2_P_D_h17_tier", "r2_P_A_stock", "r2_U_A_stock",
)


def need(ok: bool, message: str):
    if not ok:
        raise RuntimeError(message)


def canonical(v: Path) -> Path:
    return v.expanduser().resolve()


def load_helper(path: Path):
    need(path.is_file(), f"R72 quality helper missing: {path}")
    spec = importlib.util.spec_from_file_location("r74_quality_helper", path)
    need(spec is not None and spec.loader is not None, "cannot load R72 quality helper")
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    for name in ("sha256", "shape", "inspect_graph", "read_time", "parse_search"):
        need(callable(getattr(helper, name, None)), f"R72 helper missing {name}")
    need(tuple(helper.BEAMS) == BEAMS, "helper beam protocol differs")
    return helper


def parse_manifest(file: Path, expected: set[Path], helper, label: str, do_hash: bool = True):
    need(file.is_file(), f"{label} SHA256 manifest missing: {file}")
    found: dict[Path, str] = {}
    for line in file.read_text().splitlines():
        m = re.fullmatch(r"([0-9a-f]{64})\s+\*?(.+)", line)
        need(m is not None, f"{label} manifest malformed line {line!r}")
        hash_, path_ = m.groups()
        path = canonical(Path(path_))
        need(path in expected and path not in found, f"{label} extra/duplicate {path}")
        need(path.is_file(), f"{label} missing file {path}")
        if do_hash:
            need(helper.sha256(path) == hash_, f"{label} hash mismatch: {path}")
        found[path] = hash_
    need(set(found) == expected, f"{label} manifest not equal to expected files")
    return found


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("run", "quality-4t", "binary", "base", "queries", "gt", "quality-tool", "out"):
        p.add_argument("--" + name, type=Path, required=True, dest=name.replace("-", "_"))
    p.add_argument("--plan-only", action="store_true")
    args = p.parse_args()
    for name in ("run", "quality_4t", "binary", "base", "queries", "gt", "quality_tool", "out"):
        setattr(args, name, canonical(getattr(args, name)))

    h70 = args.run.parent
    need(args.run.is_dir() and args.run.name.startswith("r74-affinity-4t-"),
         "expected R74 saved affinity experiment")
    need(args.out.parent == h70 and args.out.name.startswith("r74-affinity-quality-"),
         "output must be NEW r74-affinity-quality-* directory under H70")
    need(not args.out.exists(), "output exists, refusing overwrite")
    need(args.binary.is_file() and os.access(args.binary, os.X_OK),
         "native r72_graph_recall missing/nonexecutable")
    need(args.quality_4t.is_file(), "pinned R72 4t quality summary missing")

    helper = load_helper(args.quality_tool)
    helper.shape(args.base, 1_000_000, 128, 4)
    helper.shape(args.queries, 10_000, 128, 4)
    helper.shape(args.gt, 10_000, 100, 8)
    need(tuple(helper.BEAMS) == BEAMS, "beam mismatch")

    expected_input_files = {args.base} | {canonical(h70 / "r71-bin" / arm) for arm in ARMS}
    inputs = parse_manifest(args.run / "inputs.sha256", expected_input_files,
                            helper, "R74 input", do_hash=True)
    q4 = json.loads(args.quality_4t.read_text())
    need(q4.get("kind") == "R72_SIFT1M_12_GRAPH_QUALITY" and q4.get("build_threads") == 4,
         "4-thread reference has wrong experiment kind")
    need(len(q4.get("graph_stats", {})) == 12 and len(q4.get("search", {})) == 12,
         "4-thread reference missing graph/SEARCH results")
    need(q4.get("evaluator_sha256") == helper.sha256(args.binary),
         "native SEARCH evaluator differs from 4-thread validated report")
    input_hashes = {key: helper.sha256(getattr(args, key)) for key in ("base", "queries", "gt")}
    for key, sha in input_hashes.items():
        need(q4["input_sha256"].get(key) == sha, f"{key} differs from R72 4t input")
    print("R74_INPUTS_AND_R72_REFERENCE_SHA256_PASS entries=3", flush=True)

    runs: dict[str, dict] = {}
    graph_files = set()
    for tag in SCHEDULE:
        m = re.fullmatch(r"r([12])_([UP])_(A_stock|D_h17_tier)", tag)
        need(m is not None, f"invalid scheduled tag: {tag}")
        round_, mode, arm = m.groups()
        graph = canonical(args.run / f"{tag}.graph")
        log = args.run / f"{tag}.log"
        time = args.run / f"{tag}.time"
        need(graph.is_file() and graph.stat().st_size > 0, f"graph missing: {graph}")
        need(log.is_file() and time.is_file(), f"log/time missing: {tag}")
        text = log.read_text(errors="replace")
        reservoir, selection = helper.LABELS[arm]
        need(f"R70_RESERVOIR_VARIANT={reservoir}" in text, f"wrong reservoir: {tag}")
        need(f"R71_SELECTION_VARIANT={selection}" in text, f"wrong selector: {tag}")
        wall, rss = helper.read_time(time)
        need(math.isfinite(wall) and wall > 0 and rss > 0, f"invalid time/RSS: {tag}")
        runs[tag] = {
            "round": int(round_), "mode": mode, "arm": arm, "graph": str(graph),
            "build_wall_sec": wall, "build_rss_kib": rss,
            "allowed_cpus": "0-7" if mode == "U" else "0,2,4,6",
        }
        graph_files.add(graph)
    need(len(graph_files) == 8, "expected eight distinct graphs")
    parse_manifest(args.run / "graphs.sha256", graph_files, helper, "R74 graph",
                   do_hash=not args.plan_only)

    if args.plan_only:
        print("R74_AFFINITY_QUALITY_PLAN_ONLY_PASS graph_files=8 search_runs=8 new_builds=0", flush=True)
        return

    args.out.mkdir(mode=0o755)
    report = {
        "kind": "R74_SIFT1M_AFFINITY_4T_EIGHT_GRAPH_QUALITY",
        "created_at": datetime.now().astimezone().isoformat(),
        "experiment": str(args.run), "reference_4t": str(args.quality_4t),
        "native_evaluator": str(args.binary), "native_evaluator_sha256": helper.sha256(args.binary),
        "helper": str(args.quality_tool), "helper_sha256": helper.sha256(args.quality_tool),
        "dataset_sha256": input_hashes, "build_binary_manifest": {str(k): v for k, v in inputs.items()},
        "k": 10, "beams": list(BEAMS), "query_count": 10_000, "search_workers": 1,
        "runs": runs, "comparisons": {},
        "limitations": [
            "Only two BUILD runs per mode/arm; no statistical claim about affinity causality.",
            "SEARCH QPS measured once per graph, can be influenced by cache/frequency/load.",
            "Four Parlay workers are not individually pinned to distinct CPUs within mask 0,2,4,6.",
            "GT on 10k queries has not been independently recomputed exhaustively.",
            "Graph structural validity and near-equal Recall do not prove concurrent semantic equivalence.",
        ],
    }
    for tag in SCHEDULE:
        stats = helper.inspect_graph(Path(runs[tag]["graph"]))
        runs[tag]["graph_stats"] = stats
        print(f'R74_GRAPH_VALID {tag} arcs={stats["arcs"]} bytes={stats["graph_bytes"]}', flush=True)
    print("R74_AFFINITY_EIGHT_GRAPHS_VALID_PASS", flush=True)

    env = os.environ.copy()
    env["PARLAY_NUM_THREADS"] = "1"
    for tag in SCHEDULE:
        print("R74_SEARCH_START", tag, flush=True)
        cmd = [str(args.binary), runs[tag]["graph"], str(args.base), str(args.queries), str(args.gt)]
        try:
            completed = subprocess.run(cmd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                       text=True, timeout=1800, check=False)
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(f"SEARCH timeout: {tag}") from exc
        (args.out / f"{tag}.recall.log").write_text(completed.stdout)
        need(completed.returncode == 0, f"SEARCH failed {tag} rc={completed.returncode}")
        runs[tag]["search"] = helper.parse_search(completed.stdout)
        print(f"R74_SEARCH_RUN_PASS {tag} beams=5", flush=True)
    print("R74_AFFINITY_EIGHT_SEARCH_RUNS_PASS", flush=True)

    for mode in MODES:
        report["comparisons"][mode] = {}
        for arm in ARMS:
            records = [runs[f"r{r}_{mode}_{arm}"] for r in (1, 2)]
            wall_med = median([rec["build_wall_sec"] for rec in records])
            rss_med = median([rec["build_rss_kib"] for rec in records])
            report["comparisons"][mode][arm] = {"wall_median": wall_med, "rss_median_kib": rss_med}
            print(f"R74_AFFINITY_ARM mode={mode} arm={arm} wall_median={wall_med:.3f}s rss_median={rss_med:.0f}KiB", flush=True)
        stock = report["comparisons"][mode]["A_stock"]
        combo = report["comparisons"][mode]["D_h17_tier"]
        print(f'R74_AFFINITY_BUILD_COMPARE mode={mode} D_wall_pct={(combo["wall_median"]/stock["wall_median"]-1)*100:+.2f} '
              f'D_rss_pct={(combo["rss_median_kib"]/stock["rss_median_kib"]-1)*100:+.2f}', flush=True)

        for beam in BEAMS:
            recs = {}
            for arm in ARMS:
                rr = [runs[f"r{r}_{mode}_{arm}"]["search"][str(beam)] for r in (1, 2)]
                recs[arm] = {
                    "recall_median": median([x["recall"] for x in rr]),
                    "qps_median": median([x["qps"] for x in rr]),
                    "runs": rr,
                }
            a, d = recs["A_stock"], recs["D_h17_tier"]
            diff_recall_pp = (d["recall_median"] - a["recall_median"]) * 100
            diff_qps_pct = (d["qps_median"] / a["qps_median"] - 1) * 100
            report["comparisons"][mode][str(beam)] = {
                "arms": recs, "recall_diff_pp": diff_recall_pp, "qps_diff_pct": diff_qps_pct
            }
            print(f'R74_RECALL_COMPARE mode={mode} beam={beam} A={a["recall_median"]:.6f} '
                  f'D={d["recall_median"]:.6f} D_minus_A_pp={diff_recall_pp:+.4f} '
                  f'QPS_delta_pct={diff_qps_pct:+.2f}', flush=True)

    for arm in ARMS:
        u = report["comparisons"]["U"][arm]["wall_median"]
        p_ = report["comparisons"]["P"][arm]["wall_median"]
        print(f"R74_PIN_VS_UNPIN arm={arm} wall_delta_pct={(p_/u-1)*100:+.2f}", flush=True)

    outjson = args.out / "r74_affinity_quality_summary.json"
    with outjson.open("x") as file:
        json.dump(report, file, indent=2)
        file.write("\n")
    print(f"R74_AFFINITY_QUALITY_TECHNICAL_PASS output={outjson}", flush=True)
    print("R74_INTERPRETATION_REQUIRED no_auto_equivalence_claim=TRUE", flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"R74_AFFINITY_QUALITY_FAIL {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
        sys.exit(1)
