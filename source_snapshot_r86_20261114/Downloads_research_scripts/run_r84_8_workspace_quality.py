#!/usr/bin/env python3
"""R84.8: search-only Recall/QPS on the six pinned R84.7 D0/W SIFT100K graphs.

All six graph builds already exist. Never rebuild graphs, modify H70/H84 source,
overwrite existing outputs or push to Git. Uses the exact H70 R70 recall evaluator
and 300-query/GT fixture verified during R83.8 and R83.10. The quality screen
is exploratory; R84.7's two-metric BUILD verdict remains HOLD regardless.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import platform
import statistics
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

PIN = "443a328dc71a3b7be753d52ca2b3c9a4ba77f3fd"
R83_8_HELPER_SHA = "84c213fa1d89015ee5b0b524c1cc64808b7b7e844c4861bbd2cf4325992f67bf"
BASE_SHA = "e50ff1bc34bcc6d1c97dd001023c09a666971cde64605cc06671ed8a8ff1ed12"
QUERY_SHA = "9e9328e3f0488840d3f12efcc3b0f6af940dd398fb7b6d178d72bd1e1c0f9d74"
GT_SHA = "e038aff5970977d0ee925b4357295bd81817b99b35e11bbab783fd64e0715e7f"
EVAL_SHA = "f3999051c6cc96434ea26d2faedd3ac632ed8d20be342e15c92fd4b905a33fe9"
BINARY_SHA = {
    "D0": "7340ce1817f1272d0137bb02ef8dea79756a5fa9252037d29afc3af670f6e48f",
    "W": "b79cada58551a8893c1c6fb81fd868ecd521830825ae1eb21ed887e46ec8ef95",
}
# Verbatim hashes/arcs from the user's successful six native R84.7 BUILD logs.
GRAPHS = {
    "r1_D0": ("71f7d0653408d2aec30de17e5b283e39e85a3eb9c6d8e646a537a900a9fb068d", 2267604),
    "r1_W":  ("5475e96fb6bd621e347285e522d09a9b5901135979d5933dd703d7ae5a079e9a", 2267609),
    "r2_W":  ("e7c0d38761d00baa5c7a9fa035d49129b3248f7d60eca453c5c0cedce4da6c8c", 2267600),
    "r2_D0": ("a63d1154817a29edfb40c6c701ddd73d3eb7c4b7e60cf1ae6985c85ad4d3be0d", 2267612),
    "r3_D0": ("9321a584745791b9c4c7fe4f13dd09b4919c1d58d5e69f51e9a96c6c7f7107a8", 2267611),
    "r3_W":  ("a327ff6acaf4c65eeee95f85acafb2030c59f0f51466157b97b80ce751ae4be4", 2267623),
}
PLAN = tuple(GRAPHS)
BEAMS = (10, 20, 40, 80, 160)
CPUS = (0, 2, 4, 6)
RUNREL = Path("experiments/H84/r84_7_workspace_pcore4_sift100k")
QUALITYDIR = "quality_r84_8"
STATUS_BUILD = "R84_7_TWO_METRIC_SCREEN_HOLD_OR_NO_GO"


def need(ok: bool, reason: str) -> None:
    if not ok:
        raise RuntimeError(reason)


def sha(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for part in iter(lambda: f.read(1 << 20), b""):
            h.update(part)
    return h.hexdigest()


def load_helper(p: Path):
    need(p.is_file() and sha(p) == R83_8_HELPER_SHA,
         f"R84_8_R83_8_V3_HELPER_MISSING_OR_HASH_MISMATCH {p}")
    spec = importlib.util.spec_from_file_location("r84_8_pinned_r83_8_helper", p)
    need(spec is not None and spec.loader is not None, "R84_8_HELPER_IMPORT_SPEC_MISSING")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def affinity():
    need(hasattr(os, "sched_getaffinity"), "R84_8_AFFINITY_API_UNAVAILABLE")
    allowed = tuple(sorted(os.sched_getaffinity(0)))
    need(allowed == CPUS,
         f"R84_8_SEARCH_AFFINITY_MISMATCH got={allowed} expected={CPUS}; use taskset -c 0,2,4,6")
    print("R84_8_SEARCH_PCORE4_AFFINITY_PASS cpus=0,2,4,6", flush=True)


def calculate_quality(rows, helper):
    results = []
    bad_recall = 0
    bad_qps = 0
    for i, beam in enumerate(BEAMS):
        groups = {}
        for arm in ("D0", "W"):
            recall = [helper.recall_val(rows[f"r{r}_{arm}"]["beams"][i]) for r in (1, 2, 3)]
            qps = [helper.qps_val(rows[f"r{r}_{arm}"]["beams"][i]) for r in (1, 2, 3)]
            need(all(v is not None and 0 <= v <= 1 for v in recall),
                 f"R84_8_RECALL_SCHEMA_MISSING beam={beam} arm={arm}")
            need(all(v is not None and v > 0 for v in qps),
                 f"R84_8_QPS_SCHEMA_MISSING beam={beam} arm={arm}")
            groups[arm] = {"recall": recall, "qps": qps}
        d, w = groups["D0"], groups["W"]
        rd, rw = statistics.median(d["recall"]), statistics.median(w["recall"])
        qd, qw = statistics.median(d["qps"]), statistics.median(w["qps"])
        delta = rw - rd
        ratio = qw / qd
        if delta < -0.005:
            bad_recall += 1
        if ratio < 0.90:
            bad_qps += 1
        results.append({
            "beam": beam,
            "median_recall_D0": rd,
            "median_recall_W": rw,
            "median_recall_W_minus_D0": delta,
            "paired_recall_deltas_W_minus_D0": [rw_i - rd_i for rw_i, rd_i in zip(w["recall"], d["recall"])],
            "median_qps_D0": qd,
            "median_qps_W": qw,
            "median_qps_W_over_D0": ratio,
            "raw": groups,
        })
    if bad_recall:
        verdict = "R84_8_RECALL_PILOT_REVIEW_HOLD"
    elif bad_qps >= 2:
        verdict = "R84_8_QPS_PILOT_REVIEW_HOLD"
    else:
        verdict = "R84_8_TECHNICAL_RECALL_SCREEN_PASS_NOT_STATISTICAL_PROOF"
    return {
        "beams": results,
        "verdict": verdict,
        "recall_median_drop_review_threshold": -0.005,
        "qps_median_ratio_review_threshold": 0.90,
        "qps_bad_beams_to_trigger_review": 2,
        "notes": [
            "Same pinned R70 evaluator on the six pre-existing R84.7 4t graphs",
            "Beam sequence 10,20,40,80,160, 300 heldout SIFT100K queries, k=10",
            "Three graphs per arm; exploratory thresholds are not statistical noninferiority tests",
            "QPS may vary with CPU frequency, cache, host load and evaluation order",
            "R84.7 wall speedup 0.74% is below the predeclared 3% screen regardless of quality verdict",
        ],
    }


def selftest(helper):
    helper.selftest()
    need(len(GRAPHS) == 6 and len(set(GRAPHS)) == 6, "R84_8_GRAPH_PIN_COUNT_FAIL")
    need(set(GRAPHS) == {f"r{r}_{a}" for r in (1,2,3) for a in ("D0","W")},
         "R84_8_GRAPH_PIN_NAMES_FAIL")
    sample = "\n".join(
        [f"R70_RECALL_ROW beam={beam} recall={min(1.0, 0.80 + i*0.05)} qps={10000-i*1000}"
         for i, beam in enumerate(BEAMS)] + ["R70_RECALL_EVAL_PASS"])
    parsed = helper.extract_rows(sample)
    synthetic = {f"r{r}_{a}": {"beams": parsed} for r in (1,2,3) for a in ("D0","W")}
    checks = calculate_quality(synthetic, helper)
    need(checks["verdict"] == "R84_8_TECHNICAL_RECALL_SCREEN_PASS_NOT_STATISTICAL_PROOF",
         "R84_8_SELFTEST_PERFECT_PARITY_FAILED")
    synthetic["r1_W"]["beams"] = [dict(x) for x in parsed]
    synthetic["r2_W"]["beams"] = [dict(x) for x in parsed]
    synthetic["r3_W"]["beams"] = [dict(x) for x in parsed]
    for r in (1,2,3):
        synthetic[f"r{r}_W"]["beams"][0]["recall"] = .7
    need(calculate_quality(synthetic, helper)["verdict"] == "R84_8_RECALL_PILOT_REVIEW_HOLD",
         "R84_8_SELFTEST_RECALL_DROP_NOT_CAUGHT")
    print("R84_8_RECALL_PARSER_AND_MEDIANS_SELFTEST_PASS", flush=True)


def preflight(root, helper):
    affinity()
    run = root / RUNREL
    summary = run / "r84_7_summary.json"
    need(summary.is_file(), "R84_8_R84_7_SUMMARY_MISSING")
    data = json.loads(summary.read_text())
    need(data.get("status") == STATUS_BUILD, "R84_8_BUILD_VERDICT_CHANGED_OR_INCOMPLETE")
    need(data.get("experiment") == "R84.7" and data.get("source_commit") == PIN,
         "R84_8_BUILD_EXPERIMENT_OR_COMMIT_MISMATCH")
    need(data.get("threads") == 4 and data.get("cpus") == list(CPUS),
         "R84_8_BUILD_THREADS_OR_PCORE_AFFINITY_MISMATCH")
    need(data.get("binary_sha256") == BINARY_SHA and data.get("base_sha256") == BASE_SHA,
         "R84_8_BUILD_BINARY_OR_BASE_PIN_MISMATCH")
    need(data.get("ordered_runs") == list(PLAN), "R84_8_BUILD_SCHEDULE_MISMATCH")
    need(set(data.get("runs", {})) == set(PLAN), "R84_8_SIX_BUILD_RESULTS_INCOMPLETE")
    ratios = data.get("W_over_D0_medians", {})
    need(.99 < ratios.get("wall_s", -1) < 1 and .67 < ratios.get("peakRSS_KiB", -1) < .69,
         "R84_8_REPORTED_BUILD_RATIOS_UNEXPECTED")
    for arm, pin in BINARY_SHA.items():
        binary = root / "experiments/H84/r84_5_matched_native_binary" / arm / "neighbors-pipnn_FLOAT_T_EUCLIDEAN"
        need(binary.is_file() and sha(binary) == pin, f"R84_8_{arm}_ELF_BINARY_MISMATCH")
    base = root / "data/sift100k.fbin"
    query = root / "data/sift100k_queries_300.fbin"
    gt = root / "data/sift100k_gt300.ibin"
    helper.validate_matrix(base, (100000,128))
    helper.validate_matrix(query, (300,128))
    helper.validate_matrix(gt, (300,100), payload_bytes_per_slot=8)
    for title, path, pin in (("BASE",base,BASE_SHA),("QUERY",query,QUERY_SHA),("GT",gt,GT_SHA)):
        need(sha(path) == pin, f"R84_8_{title}_SHA256_MISMATCH")
    evaluator = helper.find_evaluator(root)
    need(sha(evaluator) == EVAL_SHA, "R84_8_H70_EVALUATOR_HASH_MISMATCH")
    previous = root / "experiments/H83/r83_9_newpc_pcore4_sift100k/quality_r83_10/r83_10_quality_summary.json"
    need(previous.is_file(), "R84_8_PRIOR_R83_10_QUALITY_REPORT_MISSING")
    old = json.loads(previous.read_text())
    need(old.get("evaluator_sha256") == EVAL_SHA and
         old.get("status") == "R83_10_TECHNICAL_RECALL_SCREEN_PASS_NOT_STATISTICAL_PROOF",
         "R84_8_PRIOR_R83_10_EVALUATOR_OR_QUALITY_MISMATCH")
    for tag, (pin, arc_count) in GRAPHS.items():
        item = data["runs"][tag]
        arm = tag.partition("_")[2]
        need(item.get("tag") == tag and item.get("variant") == arm and
             item.get("rep") == int(tag[1]) and item.get("exit_code") == 0 and
             item.get("threads") == 4 and item.get("binary_sha256") == BINARY_SHA[arm],
             f"R84_8_BUILD_MANIFEST_MISMATCH {tag}")
        graph_record = item.get("graph", {})
        need(graph_record.get("sha256") == pin and graph_record.get("arcs") == arc_count and
             graph_record.get("vertices") == 100000 and graph_record.get("maximum_degree") == 64,
             f"R84_8_GRAPH_PIN_RECORD_MISMATCH {tag}")
        helper.check_graph(run / tag / "graph.bin", graph_record)
    out = run / QUALITYDIR
    need(not out.exists(), f"R84_8_OUTPUT_EXISTS_FAIL_CLOSED {out}")
    print("R84_8_PINNED_SIX_D0_W_GRAPHS_AND_EVALUATOR_PASS", flush=True)
    print("R84_8_EVALUATOR_SHA256", EVAL_SHA, flush=True)
    print("R84_8_R84_7_BUILD_STATUS", STATUS_BUILD, flush=True)
    return run, summary, out, base, query, gt, evaluator


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.home()/"ann-task-a")
    parser.add_argument("--helper", type=Path,
                        default=Path.home()/"Downloads/run_r83_8_v3_evaluator_locator.py")
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--selftest", action="store_true")
    action.add_argument("--dry-run", action="store_true")
    action.add_argument("--run", action="store_true")
    opt = parser.parse_args()
    helper = load_helper(opt.helper.expanduser())
    selftest(helper)
    if opt.selftest:
        return
    root = opt.root.expanduser().resolve()
    run, summary, out, base, query, gt, evaluator = preflight(root, helper)
    if opt.dry_run:
        print("R84_8_DRY_RUN_PASS_NO_SEARCH", flush=True)
        return
    out.mkdir(mode=0o755, exist_ok=False)
    report = out / "r84_8_quality_summary.json"
    obj = {
        "experiment":"R84.8", "status":"STARTED",
        "source_report": str(summary),"source_report_sha256": sha(summary),
        "evaluator_sha256": EVAL_SHA,"query_sha256": QUERY_SHA,"gt_sha256": GT_SHA,
        "affinity":list(CPUS),"search_host": {"node":platform.node(),"kernel":platform.release()},
        "created_at_utc": datetime.now(timezone.utc).isoformat(), "rows":{},
    }
    report.write_text(json.dumps(obj, indent=2) + "\n")
    try:
        for tag in PLAN:
            print(f"R84_8_SEARCH_START graph={tag}", flush=True)
            log = out / f"{tag}.recall.log"
            with log.open("x") as fp:
                try:
                    result = subprocess.run(
                        [str(evaluator), str(run/tag/"graph.bin"), str(base), str(query), str(gt)],
                        cwd=out, stdout=fp, stderr=subprocess.STDOUT, timeout=300, check=False)
                    code = result.returncode
                except subprocess.TimeoutExpired:
                    code = 124
            need(code == 0, f"R84_8_EVALUATOR_EXIT_{code} graph={tag} log={log}")
            parsed = helper.extract_rows(log.read_text(errors="replace"))
            obj["rows"][tag] = {
                "arm":tag.partition("_")[2],"rep":int(tag[1]),
                "beams":parsed,"log":str(log),
            }
            report.write_text(json.dumps(obj, indent=2) + "\n")
            print(f"R84_8_SEARCH_PASS graph={tag} rows={len(parsed)}", flush=True)
        assessment = calculate_quality(obj["rows"], helper)
        obj["assessment"] = assessment
        obj["status"] = assessment["verdict"]
        obj["research_decision"] = "R84.7 HOLD on the predeclared two-metric BUILD screen (wall gain ~0.74% < 3%), independent of Recall result. W remains a memory-focused candidate. No SIFT1M and no Git push."
        report.write_text(json.dumps(obj, indent=2) + "\n")
        summary_rows = [{k:v for k,v in row.items() if k != "raw"} for row in assessment["beams"]]
        print("R84_8_MEDIANS " + json.dumps(summary_rows, sort_keys=True), flush=True)
        print(obj["status"], flush=True)
        print("R84_8_R84_7_BUILD_TWO_METRIC_SCREEN_REMAINS_HOLD", flush=True)
        print("R84_8_NO_NEW_BUILD_NO_SIFT1M_NO_PUSH", flush=True)
        print("R84_8_REPORT", report, flush=True)
    except Exception as ex:
        obj["status"] = "STOP_INCOMPLETE"
        obj["error"] = str(ex)
        report.write_text(json.dumps(obj, indent=2) + "\n")
        raise


if __name__ == "__main__":
    try:
        main()
    except Exception as ex:
        print("R84_8_STOP", ex, file=sys.stderr, flush=True)
        sys.exit(1)
