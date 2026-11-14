#!/usr/bin/env python3
"""R73: verify saved SIFT1M 2t/8t graphs and evaluate native PiPNN Recall.

Read-only input validation. No BUILD; writes only into a NEW output folder.
Uses the pinned R72 graph validator and native SIFT1M search evaluator.
Results are descriptive, not a proof of equivalence or scaling superiority.
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
import statistics
import subprocess
import sys

ARMS = ("A_stock", "D_h17_tier")
BEAMS = (10, 20, 40, 80, 160)
SCHEDULE = ("r1_A_stock", "r1_D_h17_tier", "r2_D_h17_tier", "r2_A_stock")


def require(condition: bool, message: str):
    if not condition:
        raise RuntimeError(message)


def resolve(path: Path) -> Path:
    return path.expanduser().resolve()


def load_helper(path: Path):
    require(path.is_file(), f"missing R72 quality helper: {path}")
    spec = importlib.util.spec_from_file_location("r73_r72_helper", path)
    require(spec is not None and spec.loader is not None, f"cannot import helper: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    for fn in ("sha256", "shape", "inspect_graph", "read_time", "parse_search"):
        require(callable(getattr(module, fn, None)), f"missing R72 helper function {fn}")
    require(tuple(module.BEAMS) == BEAMS, "R72 evaluator beams differ from pinned R73")
    return module


def check_sha256_manifest(path: Path, expected_paths: set[Path], helper):
    require(path.is_file(), f"input manifest missing: {path}")
    rows = {}
    for raw in path.read_text().splitlines():
        match = re.fullmatch(r"([a-f0-9]{64})\s+\*?(.+)", raw)
        require(match is not None, f"invalid SHA256 input manifest line: {raw!r}")
        expected, filepath = match.groups()
        p = resolve(Path(filepath))
        require(p in expected_paths and p not in rows, f"unexpected/duplicate manifest input {p}")
        require(p.is_file(), f"missing manifest input {p}")
        actual = helper.sha256(p)
        require(expected == actual, f"SHA256 input changed: {p}")
        rows[p] = actual
    require(set(rows) == expected_paths, "manifest misses SIFT1M base/A/D inputs")
    return rows


def check_graph_manifest(path: Path, graphs: dict[str, Path], helper):
    require(path.is_file(), f"graph SHA256 manifest missing: {path}")
    rows = {}
    expected_paths = {p: tag for tag, p in graphs.items()}
    for raw in path.read_text().splitlines():
        match = re.fullmatch(r"([a-f0-9]{64})\s+\*?(.+)", raw)
        require(match is not None, f"invalid graph manifest line {raw!r}")
        expected, filepath = match.groups()
        p = resolve(Path(filepath))
        require(p in expected_paths and p not in rows, f"unexpected/duplicate graph manifest path {p}")
        require(expected == helper.sha256(p), f"graph SHA256 differs from recorded manifest: {p}")
        rows[p] = expected
    require(set(rows) == set(expected_paths), "graph manifest missing one or more of the 4 graph files")


def median(values):
    return statistics.median(values)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for label in ("two", "eight", "quality-4t", "binary", "base", "queries", "gt", "quality-tool", "out"):
        parser.add_argument("--" + label, required=True, type=Path, dest=label.replace("-", "_"))
    parser.add_argument("--plan-only", action="store_true")
    args = parser.parse_args()
    for label in ("two", "eight", "quality_4t", "binary", "base", "queries", "gt", "quality_tool", "out"):
        setattr(args, label, resolve(getattr(args, label)))

    h70 = args.two.parent
    require(args.two.is_dir() and args.two.name.startswith("r73-sift1m-2t-"), "unexpected 2-thread directory")
    require(args.eight.is_dir() and args.eight.parent == h70 and
            args.eight.name.startswith("r73-sift1m-8t-"), "unexpected 8-thread directory")
    require(args.out.parent == h70 and args.out.name.startswith("r73-quality-2t8t-"),
            "output must be a NEW r73-quality-2t8t-* directory inside H70")
    require(not args.out.exists(), f"output directory exists, refusing overwrite: {args.out}")
    require(args.binary.is_file() and os.access(args.binary, os.X_OK), "native evaluator missing/nonexecutable")

    helper = load_helper(args.quality_tool)
    helper.shape(args.base, 1_000_000, 128, 4)
    helper.shape(args.queries, 10_000, 128, 4)
    helper.shape(args.gt, 10_000, 100, 8)

    expected_inputs = {args.base} | {h70 / "r71-bin" / a for a in ARMS}
    require(all(p.is_file() for p in expected_inputs), "SIFT1M base or R71 binary missing")
    sha_two = check_sha256_manifest(args.two / "inputs.sha256", expected_inputs, helper)
    sha_eight = check_sha256_manifest(args.eight / "inputs.sha256", expected_inputs, helper)
    require(sha_two == sha_eight, "2t and 8t input manifest contents differ")

    require(args.quality_4t.is_file(), "pinned 4t R72 quality result missing")
    q4 = json.loads(args.quality_4t.read_text())
    require(q4.get("kind") == "R72_SIFT1M_12_GRAPH_QUALITY" and q4.get("build_threads") == 4,
            "unexpected 4-thread quality summary")
    require(q4.get("evaluator_sha256") == helper.sha256(args.binary), "native evaluator differs from 4t evaluation")
    for key in ("base", "queries", "gt"):
        require(q4["input_sha256"][key] == helper.sha256(getattr(args, key)),
                f"{key} content differs from validated 4-thread experiment")
    require(len(q4.get("graph_stats", {})) == 12 and len(q4.get("search", {})) == 12,
            "4t quality report lacks 12 evaluated graphs")
    print("R73_PINNED_INPUTS_AND_4T_QUALITY_PASS", flush=True)

    runs: dict[str, dict] = {}
    for threads, root in ((2, args.two), (8, args.eight)):
        expected_graphs = {tag: resolve(root / (tag + ".graph")) for tag in SCHEDULE}
        for tag, graph in expected_graphs.items():
            require(graph.is_file() and graph.stat().st_size > 0, f"graph missing: {tag} {graph}")
            log = root / (tag + ".log")
            timefile = root / (tag + ".time")
            require(log.is_file() and timefile.is_file(), f"BUILD log/time missing for {tag}")
            _, arm = tag.split("_", 1)
            labels = helper.LABELS[arm]
            logtext = log.read_text(errors="replace")
            require(f"R70_RESERVOIR_VARIANT={labels[0]}" in logtext and
                    f"R71_SELECTION_VARIANT={labels[1]}" in logtext,
                    f"binary feature labels wrong for {threads}t {tag}")
            wall, rss = helper.read_time(timefile)
            runs[f"{threads}t_{tag}"] = {"threads": threads, "tag": tag, "arm": arm,
                                         "graph": str(graph), "build_wall_sec": wall,
                                         "build_peak_rss_kib": rss}
        if not args.plan_only:
            check_graph_manifest(root / "graphs.sha256", expected_graphs, helper)
        else:
            require((root / "graphs.sha256").is_file(), "graph hash manifest missing")
    if args.plan_only:
        print("R73_QUALITY_PLAN_ONLY_PASS graph_files=8 search_runs=8 new_builds=0", flush=True)
        return

    args.out.mkdir(mode=0o755)
    report = {"kind": "R73_SIFT1M_2T_8T_GRAPH_QUALITY", "created_at": datetime.now().astimezone().isoformat(),
              "source_2t": str(args.two), "source_8t": str(args.eight), "quality_4t": str(args.quality_4t),
              "quality_tool": str(args.quality_tool), "quality_tool_sha256": helper.sha256(args.quality_tool),
              "native_evaluator": str(args.binary), "native_evaluator_sha256": helper.sha256(args.binary),
              "input_sha256": {k: helper.sha256(getattr(args, k)) for k in ("base", "queries", "gt")},
              "k": 10, "beams": list(BEAMS), "num_queries": 10_000, "search_threads": 1,
              "runs": runs, "comparisons": {}, "scaling": {},
              "limitations": [
                  "2 and 8 thread conditions have only 2 BUILDs per arm; 4 threads has 3.",
                  "One hardware machine, one SIFT1M dataset, fixed BUILD parameters.",
                  "SEARCH QPS measured once per graph; order/cache noise possible.",
                  "GT full 10k queries not independently recomputed; only sample validated.",
                  "Graph validity and similar medians do not establish exact equivalence under concurrency.",
              ]}
    for key, rec in runs.items():
        stat = helper.inspect_graph(Path(rec["graph"]))
        rec["graph_stats"] = stat
        print(f'R73_GRAPH_VALID {key} arcs={stat["arcs"]} bytes={stat["graph_bytes"]}', flush=True)
    print("R73_EIGHT_GRAPHS_STRUCTURALLY_VALID_PASS", flush=True)

    env = os.environ.copy()
    env["PARLAY_NUM_THREADS"] = "1"
    for key, rec in runs.items():
        print("R73_SEARCH_START", key, flush=True)
        cmd = [str(args.binary), rec["graph"], str(args.base), str(args.queries), str(args.gt)]
        try:
            process = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                     env=env, text=True, check=False, timeout=1800)
        except subprocess.TimeoutExpired as e:
            raise RuntimeError(f"SEARCH timed out for {key}") from e
        log = args.out / f"{key}.recall.log"
        log.write_text(process.stdout)
        require(process.returncode == 0, f"SEARCH failed {key} rc={process.returncode}; log={log}")
        rec["search"] = helper.parse_search(process.stdout)
        print(f"R73_SEARCH_RUN_PASS {key} beams=5", flush=True)
    print("R73_EIGHT_SEARCH_RUNS_PASS", flush=True)

    for threads in (2, 4, 8):
        for arm in ARMS:
            if threads == 4:
                build = [q4["build"][f"r{r}_{arm}"] for r in (1, 2, 3)]
                walls = [float(x["wall_sec"]) for x in build]
                rsses = [int(x["rss_kib"]) for x in build]
            else:
                rr = [runs[f"{threads}t_r{r}_{arm}"] for r in (1, 2)]
                walls = [x["build_wall_sec"] for x in rr]
                rsses = [x["build_peak_rss_kib"] for x in rr]
            report["scaling"][f"{threads}t_{arm}"] = {
                "wall_runs": walls, "rss_runs_kib": rsses,
                "wall_median": median(walls), "rss_median_kib": median(rsses),
            }
            print(f"R73_SCALING_ARM threads={threads} arm={arm} "
                  f"wall_median={median(walls):.3f}s rss_median={median(rsses):.0f}KiB "
                  f"wall_runs={walls} rss_runs={rsses}", flush=True)
        a = report["scaling"][f"{threads}t_A_stock"]
        d = report["scaling"][f"{threads}t_D_h17_tier"]
        print(f'R73_SCALING_D_VS_A threads={threads} '
              f'wall_pct={(d["wall_median"]/a["wall_median"]-1)*100:+.2f}% '
              f'rss_pct={(d["rss_median_kib"]/a["rss_median_kib"]-1)*100:+.2f}%', flush=True)

    for threads in (2, 8):
        report["comparisons"][str(threads)] = {}
        for beam in BEAMS:
            values = {}
            for arm in ARMS:
                rr = [runs[f"{threads}t_r{r}_{arm}"]["search"][str(beam)] for r in (1, 2)]
                values[arm] = {"recall_runs": [x["recall"] for x in rr],
                               "recall_median": median([x["recall"] for x in rr]),
                               "qps_runs": [x["qps"] for x in rr],
                               "qps_median": median([x["qps"] for x in rr])}
            a, d = values["A_stock"], values["D_h17_tier"]
            rec_diff_pp = (d["recall_median"] - a["recall_median"]) * 100
            qps_diff_pct = (d["qps_median"] / a["qps_median"] - 1) * 100
            report["comparisons"][str(threads)][str(beam)] = {
                "arms": values, "recall_delta_pp": rec_diff_pp, "qps_delta_percent": qps_diff_pct}
            print(f'R73_RECALL_COMPARE threads={threads} beam={beam} '
                  f'A={a["recall_median"]:.6f} D={d["recall_median"]:.6f} '
                  f'D_minus_A_pp={rec_diff_pp:+.4f} QPS_delta_pct={qps_diff_pct:+.2f}', flush=True)

    output = args.out / "r73_scaling_quality_summary.json"
    with output.open("x") as file:
        json.dump(report, file, indent=2)
        file.write("\n")
    print("R73_THREAD_SCALING_QUALITY_TECHNICAL_PASS output=" + str(output), flush=True)
    print("R73_INTERPRETATION_REQUIRED no_equivalence_claim=TRUE", flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"R73_THREAD_QUALITY_FAIL {type(error).__name__}: {error}", file=sys.stderr, flush=True)
        sys.exit(1)
