#!/usr/bin/env python3
"""R72.4: verify 12 pinned SIFT1M graphs and independently SEARCH-evaluate all 12.

Reads original R72 pilot/quality output and R72 repeats; no graph construction, no
source modifications, no mutation of existing inputs. Reuses audited graph and
native log validators in R72_sift1m_quality_kit/r72_quality_pilot.py.

A PASS here means graph structure and native SEARCH execution are valid. It does
not mean non-inferiority/equivalence is statistically proven.
"""
from __future__ import annotations

import argparse
from datetime import datetime
import importlib.util
import json
import math
import os
from pathlib import Path
import statistics
import subprocess
import sys

ARMS = ("A_stock", "B_h17", "C_tier", "D_h17_tier")
BEAMS = (10, 20, 40, 80, 160)
SEARCH_ORDER = (
    "r1_A_stock", "r1_D_h17_tier", "r1_B_h17", "r1_C_tier",
    "r2_D_h17_tier", "r2_A_stock", "r2_C_tier", "r2_B_h17",
    "r3_B_h17", "r3_C_tier", "r3_A_stock", "r3_D_h17_tier",
)


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def resolve(p):
    return p.expanduser().resolve()


def get_quality_module(path):
    require(path.is_file(), f"missing quality helper: {path}")
    spec = importlib.util.spec_from_file_location("r72_pinned_quality_helpers", path)
    require(spec is not None and spec.loader is not None, f"cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    for method in ("check_manifest", "inspect_graph", "read_time", "parse_search", "sha256", "shape"):
        require(callable(getattr(module, method, None)), f"missing helper {method}")
    require(tuple(module.ARMS) == ARMS and tuple(module.BEAMS) == BEAMS,
            "quality helper expected arms/beams differ")
    return module


def verify_labels(logfile, arm, helper):
    require(logfile.is_file(), f"BUILD log missing: {logfile}")
    data = logfile.read_text(errors="replace")
    reservoir, selection = helper.LABELS[arm]
    require(f"R70_RESERVOIR_VARIANT={reservoir}" in data and
            f"R71_SELECTION_VARIANT={selection}" in data,
            f"wrong arm labels in {logfile}")


def compare_record(record, wall, rss, stats, tag):
    require(record is not None, f"no pinned run record for {tag}")
    require(math.isclose(float(record["wall"]), wall, abs_tol=0.005),
            f"BUILD wall changed from pinned summary: {tag}")
    require(int(record["rss"]) == rss, f"BUILD RSS changed from pinned summary: {tag}")
    require(int(record["graph_bytes"]) == stats["graph_bytes"],
            f"BUILD graph length changed from pinned summary: {tag}")
    require(record["graph_sha256"] == stats["sha256"],
            f"BUILD graph SHA256 changed from pinned summary: {tag}")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    for key in ("pilot", "repeats", "pilot-quality", "binary", "base", "queries", "gt", "out", "quality-tool"):
        ap.add_argument("--" + key, dest=key.replace("-", "_"), type=Path, required=True)
    ap.add_argument("--plan-only", action="store_true", help="validate metadata, never run SEARCH")
    args = ap.parse_args()
    for key in ("pilot", "repeats", "pilot_quality", "binary", "base", "queries", "gt", "out", "quality_tool"):
        setattr(args, key, resolve(getattr(args, key)))

    h70 = args.pilot.parent
    require(args.pilot.is_dir() and args.pilot.name.startswith("r72-sift1m-pilot-4t-"),
            "unexpected pilot folder")
    require(args.repeats.is_dir() and args.repeats.parent == h70 and
            args.repeats.name.startswith("r72-sift1m-repeats-4t-"),
            "unexpected repeats folder")
    require(args.out.parent == h70 and args.out.name.startswith("r72-quality-12-"),
            "output folder must be a new r72-quality-12-* directory directly under H70")
    require(not args.out.exists(), "output folder exists; preserving it")
    require(args.binary.is_file() and os.access(args.binary, os.X_OK),
            "missing/nonexecutable native SIFT1M search evaluator")
    helper = get_quality_module(args.quality_tool)
    helper.shape(args.base, 1_000_000, 128, 4)
    helper.shape(args.queries, 10_000, 128, 4)
    helper.shape(args.gt, 10_000, 100, 8)

    helper.check_manifest(args.pilot, args.base)
    helper.check_manifest(args.repeats, args.base)
    require((args.pilot / "inputs.sha256").read_bytes() ==
            (args.repeats / "inputs.sha256").read_bytes(),
            "pilot/repeat input manifests differ")
    print("R72_12_INPUT_MANIFEST_PASS", flush=True)

    pinned = json.loads((args.repeats / "r72_repeats_summary.json").read_text())
    require(pinned.get("kind") == "R72_SIFT1M_BUILD_3_PER_ARM", "invalid repeat summary")
    require(resolve(Path(pinned["pilot"])) == args.pilot and
            resolve(Path(pinned["repeats"])) == args.repeats,
            "repeat summary points to different runs")
    summaries = pinned.get("summary", {})
    require(set(summaries) == set(ARMS), "repeat summary arms mismatch")
    records = {}
    for arm in ARMS:
        runs = summaries[arm]["runs"]
        require(len(runs) == 3 and {int(e["round"]) for e in runs} == {1, 2, 3},
                f"missing/duplicate BUILD rounds for {arm}")
        for rec in runs:
            tag = f'r{int(rec["round"])}_{arm}'
            require(tag not in records, f"duplicate run record {tag}")
            records[tag] = rec
    require(set(records) == set(SEARCH_ORDER), "BUILD record names do not match expected schedule")

    # Ground the previously validated pilot metadata and its graph hashes before reusing it.
    require(args.pilot_quality.is_file(), "pilot-quality JSON missing")
    pilot_quality = json.loads(args.pilot_quality.read_text())
    require(pilot_quality.get("kind") == "R72_SIFT1M_FOUR_ARM_PILOT_QUALITY", "unexpected pilot-quality report")
    require(resolve(Path(pilot_quality["source_run"])) == args.pilot,
            "pilot-quality report does not match given pilot")
    for key in ("base", "queries", "gt"):
        require(resolve(Path(pilot_quality[key])) == getattr(args, key),
                f"{key} path does not match the prior native quality evaluation")
    require(pilot_quality["native_evaluator_sha256"] == helper.sha256(args.binary),
            "native evaluator changed since pilot SEARCH evaluation")
    prior_by_arm = {e["variant"]: e for e in pilot_quality["runs"]}
    require(set(prior_by_arm) == set(ARMS), "pilot quality missing an arm")

    if args.plan_only:
        for tag in SEARCH_ORDER:
            round_no, arm = tag.split("_", 1)
            folder = args.pilot if round_no == "r1" else args.repeats
            stem = arm if round_no == "r1" else tag
            for suffix in (".graph", ".log", ".time"):
                require((folder / (stem + suffix)).is_file(), f"missing {tag}{suffix}")
        print("R72_12_PLAN_ONLY_PASS graph_files=12 search_rerun=12 new_builds=0", flush=True)
        return

    args.out.mkdir(mode=0o755)
    out = {"kind": "R72_SIFT1M_12_GRAPH_QUALITY", "created_at": datetime.now().astimezone().isoformat(),
           "pilot": str(args.pilot), "repeats": str(args.repeats),
           "pilot_quality": str(args.pilot_quality), "evaluator": str(args.binary),
           "evaluator_sha256": helper.sha256(args.binary),
           "quality_helper": str(args.quality_tool), "quality_helper_sha256": helper.sha256(args.quality_tool),
           "input_sha256": {key: helper.sha256(getattr(args, key)) for key in ("base", "queries", "gt")},
           "graph_stats": {}, "search": {}, "build": {},
           "search_threads": 1, "build_threads": 4,
           "k": 10, "beam_sizes": list(BEAMS), "queries_count": 10000,
           "limitations": [
               "Only three BUILD graphs per arm, one SIFT1M dataset, one 4-thread configuration.",
               "Native SEARCH QPS measured once per graph, order and caching can influence timing.",
               "Graph structural validity and SEARCH completion do not prove Recall equivalence.",
               "Exactness of the full ground truth set is not established by the two-query sample check.",
               "Saved graph topology can vary at 4 threads; no concurrent parity proof.",
           ]}

    # New r2/r3 graphs receive the *full* structural check; r1 graphs are
    # rehashed and checked against previously validated, pinned pilot-quality.
    for tag in SEARCH_ORDER:
        round_no, arm = tag.split("_", 1)
        folder = args.pilot if round_no == "r1" else args.repeats
        stem = arm if round_no == "r1" else tag
        graph = folder / (stem + ".graph")
        verify_labels(folder / (stem + ".log"), arm, helper)
        wall, rss = helper.read_time(folder / (stem + ".time"))
        if round_no == "r1":
            s = prior_by_arm[arm]["graph_stats"]
            require(s["sha256"] == helper.sha256(graph), f"pilot graph SHA changed {tag}")
            require(s["n"] == 1_000_000 and s["max_degree"] == 64 and
                    s["invalid_neighbor_ids"] == 0 and s["duplicate_neighbors"] == 0 and
                    s["self_loops"] == 0, f"pilot graph not previously validated {tag}")
            require(int(s["graph_bytes"]) == graph.stat().st_size,
                    f"pilot graph size changed {tag}")
            s = dict(s)
            checked = "pinned_pilot_quality_sha256_revalidated"
        else:
            s = helper.inspect_graph(graph)
            checked = "full_structure_check"
        compare_record(records[tag], wall, rss, s, tag)
        out["graph_stats"][tag] = {"arm": arm, "round": int(round_no[1:]),
                                   "graph": str(graph), "validation": checked, **s}
        out["build"][tag] = {"wall_sec": wall, "rss_kib": rss}
        print(f'R72_12_GRAPH_VALID {tag} arcs={s["arcs"]} '
              f'bytes={s["graph_bytes"]} validation={checked}', flush=True)
    print("R72_ALL_12_GRAPHS_VALID_PASS", flush=True)

    env = os.environ.copy()
    env["PARLAY_NUM_THREADS"] = "1"
    for tag in SEARCH_ORDER:
        graph = out["graph_stats"][tag]["graph"]
        cmd = [str(args.binary), graph, str(args.base), str(args.queries), str(args.gt)]
        print("R72_12_SEARCH_START", tag, flush=True)
        try:
            proc = subprocess.run(cmd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                  text=True, timeout=1800, check=False)
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(f"SEARCH timeout for {tag}") from exc
        log_file = args.out / f"{tag}.recall.log"
        log_file.write_text(proc.stdout)
        require(proc.returncode == 0, f"SEARCH failed for {tag} rc={proc.returncode}; log={log_file}")
        out["search"][tag] = helper.parse_search(proc.stdout)
        print(f"R72_12_SEARCH_RUN_PASS {tag} beams=5", flush=True)

    comparisons = {}
    for beam in BEAMS:
        all_arms = {}
        for arm in ARMS:
            rr = [out["search"][f"r{r}_{arm}"][str(beam)] for r in (1, 2, 3)]
            rec = [float(x["recall"]) for x in rr]
            qps = [float(x["qps"]) for x in rr]
            all_arms[arm] = {"recall_median": statistics.median(rec),
                             "recall_min": min(rec), "recall_max": max(rec),
                             "recall_runs": rec, "qps_median": statistics.median(qps),
                             "qps_runs": qps}
        a, d = all_arms["A_stock"], all_arms["D_h17_tier"]
        delta_pp = (d["recall_median"] - a["recall_median"]) * 100
        qps_delta = (d["qps_median"] / a["qps_median"] - 1) * 100
        comparisons[str(beam)] = {"arms": all_arms, "D_minus_A_recall_pp": delta_pp,
                                  "D_minus_A_qps_percent": qps_delta}
        print(f'R72_12_RECALL_COMPARE beam={beam} '
              f'A_median={a["recall_median"]:.6f} D_median={d["recall_median"]:.6f} '
              f'D_minus_A_pp={delta_pp:+.4f} '
              f'A_range=[{a["recall_min"]:.6f},{a["recall_max"]:.6f}] '
              f'D_range=[{d["recall_min"]:.6f},{d["recall_max"]:.6f}] '
              f'A_QPS_median={a["qps_median"]:.2f} '
              f'D_QPS_median={d["qps_median"]:.2f} '
              f'D_QPS_delta_pct={qps_delta:+.2f}', flush=True)
    out["comparisons"] = comparisons
    output = args.out / "r72_quality_12_summary.json"
    with output.open("x") as f:
        json.dump(out, f, indent=2)
        f.write("\n")
    print(f"R72_12_GRAPH_QUALITY_TECHNICAL_PASS output={output}", flush=True)
    print("R72_QUALITY_INTERPRETATION_REQUIRED no_auto_equivalence_claim=TRUE", flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"R72_12_QUALITY_FAIL {type(e).__name__}: {e}", file=sys.stderr, flush=True)
        sys.exit(1)
