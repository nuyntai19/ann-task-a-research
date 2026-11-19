#!/usr/bin/env python3
"""R90-P4R v1: repeat native MS-Turing1M Search QPS on nine frozen P4 graphs.

Independent 100K-query Search evaluations at beams 368 and 880; three NEW
replications per graph (27 evaluator processes, 54 observed beam rows).
No BUILD, no source edit, no old artifact rewrite. Fail-closed SHA and audit gates.
Output is separate. Interrupted runs preserve records and can safely resume only
when no partial log remains; never automatically delete, truncate, or overwrite.

Use: python3 SCRIPT selftest | preflight | run | audit
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import shutil
import statistics
import subprocess
import sys
import time

HOME = Path.home()
ROOT = HOME / "ann-task-a"
P4M = HOME / "Downloads/r90_p4m_mst1m_matched_recall_100kq_v1_1.py"
P4M_SHA = "f4399963634717f21a0fd14cd52d0c6b7f55e1c63b1dd487f58398238edc0e5e"
P4M_REPORT_SHA = "8f7286a415fcd2465449110a0ef53b43402e6b6976e2adc20517cd15a8d8f3b2"
OUT = ROOT / "experiments/R90/r90_p4r_mst1m_repeated_qps_v1"
ARMS = ("stock", "h17", "fast")
BEAMS = (368, 880)
ROUNDS = 3
QUERY_COUNT = 100000
CPU = 0
TAG = "R90_P4R_V1"
REGEX = re.compile(
    r"^R72_RECALL_ROW\s+beam=(\d+)\s+recall=([\deE.+-]+)\s+"
    r"qps=([\deE.+-]+)\s+avg_cmps=([\deE.+-]+)\s+"
    r"avg_visited=([\deE.+-]+)\s*$", re.M,
)


def need(cond, why):
    if not cond:
        raise RuntimeError(TAG + "_HOLD_" + str(why))


def safe_file(path):
    path = Path(path)
    return path.is_file() and not path.is_symlink()


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for b in iter(lambda: f.read(4 * 1024 * 1024), b""):
            h.update(b)
    return h.hexdigest()


def read_json(path):
    need(safe_file(path), "MISSING_OR_SYMLINK_" + Path(path).name)
    return json.loads(Path(path).read_text(encoding="utf8"))


def atomic(path, obj, create=False):
    path = Path(path)
    tmp = Path(str(path) + ".part")
    need(not tmp.exists() and not tmp.is_symlink(), "PART_EXISTS_" + path.name)
    if create:
        need(not path.exists() and not path.is_symlink(), "OUTPUT_EXISTS_" + path.name)
    else:
        need(safe_file(path), "EXPECTED_OUTPUT_MISSING_" + path.name)
    with tmp.open("x", encoding="utf8") as f:
        json.dump(obj, f, indent=2, sort_keys=True, allow_nan=False)
        f.write("\n")
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def parse_native(stdout):
    need("R85_A1C_DYNAMIC_BEAMS count=2" in stdout, "NATIVE_BEAM_COUNT")
    need("R72_RECALL_INPUT_PASS graph_nodes=1000000 queries=100000 gt_k=" in stdout,
         "NATIVE_QUERY_GT_HEADER")
    need("R72_RECALL_EVAL_PASS" in stdout, "NATIVE_EVALUATOR_PASS")
    rows = {}
    for m in REGEX.finditer(stdout):
        beam = int(m.group(1))
        need(beam in BEAMS and beam not in rows, "NATIVE_DUPLICATE_OR_WRONG_BEAM")
        recall, qps, cmps, visited = (float(m.group(k)) for k in (2, 3, 4, 5))
        need(all(map(math.isfinite, (recall, qps, cmps, visited)))
             and 0 <= recall <= 1 and qps > 0 and visited > 0 and cmps > 0,
             "NATIVE_INVALID_NUMBER")
        rows[str(beam)] = {
            "recall_at10": recall,
            "qps": qps,
            "latency_us_throughput_proxy_NOT_p95": 1e6 / qps,
            "avg_visited": visited,
            "legacy_avg_cmps_raw_UNTRUSTED": cmps,
            "avg_cmps_status": ("INVALID_COUNTER_32BIT_R86_V4" if beam >= 800
                                else "LEGACY_UNVERIFIED_DO_NOT_USE_AS_64BIT_NDC"),
        }
    need(set(rows) == {str(b) for b in BEAMS}, "NATIVE_TWO_BEAM_ROW_COVERAGE")
    return rows


def jobs():
    # Interleave all three arms within each block; rotate the order each round.
    return [(rnd, rep, ARMS[(idx + rnd + rep - 2) % 3])
            for rnd in range(1, ROUNDS + 1)
            for rep in (1, 2, 3) for idx in range(3)]


def frozen():
    need(safe_file(P4M) and sha256(P4M) == P4M_SHA, "ORIGINAL_P4M_RUNNER_SHA")
    spec = importlib.util.spec_from_file_location("frozen_r90_p4m_v11", str(P4M))
    need(spec is not None and spec.loader is not None, "IMPORT_P4M_SOURCE")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    need(tuple(mod.ARMS) == ARMS and mod.BEAMS ==
         (320, 352, 368, 384, 800, 848, 880, 896), "P4M_SOURCE_PROTOCOL")
    p, original_p4q, receipt = mod.prior_verified()
    full = mod.OUT / "full_manifest.json"
    report = mod.OUT / "full_matched_summary.json"
    need(safe_file(full) and safe_file(report), "FROZEN_P4M_EVIDENCE_MISSING")
    need(sha256(report) == P4M_REPORT_SHA, "FROZEN_P4M_SUMMARY_SHA")
    state, summary = read_json(full), read_json(report)
    need(state.get("status") == "FULL_9_GRAPH_COMPLETE" and
         state.get("script_sha") == P4M_SHA and
         state.get("p4q_frozen_source") == receipt and
         state.get("beams") == list(mod.BEAMS), "FROZEN_P4M_MANIFEST")
    need(len(state.get("searches", [])) == 9, "FROZEN_P4M_SEARCH_COVERAGE")
    seen = set()
    for record in state["searches"]:
        k = (record["arm"], record["rep"])
        need(k not in seen and k[0] in ARMS and k[1] in (1, 2, 3), "FROZEN_GRAPH_KEYS")
        seen.add(k)
        mod.verify_one(record, p, original_p4q)
    need(seen == {(a, r) for a in ARMS for r in (1, 2, 3)}, "ALL_NINE_GRAPHS")
    need(summary == mod.expected_report(state, original_p4q) and
         summary.get("status") == "BRACKETED_QUALITY_FLOORS_ON_TESTED_GRID",
         "FROZEN_P4M_REPORT_MISMATCH")
    for arm in ARMS:
        need(summary["per_arm"][arm]["0.99"]["selected_beams"] == [368] * 3 and
             summary["per_arm"][arm]["0.998"]["selected_beams"] == [880] * 3,
             "FROZEN_P4M_QUALITY_FLOOR")
    need(shutil.which("taskset") and safe_file("/usr/bin/time") and
         CPU in os.sched_getaffinity(0), "NATIVE_CPU0_OR_TIME_UNAVAILABLE")
    old = {(r["arm"], r["rep"]): r for r in state["searches"]}
    pin = {
        "protocol": TAG,
        "new_runner_sha": sha256(Path(__file__)),
        "p4m_runner_sha": P4M_SHA,
        "p4m_full_manifest_sha": sha256(full),
        "p4m_summary_sha": P4M_REPORT_SHA,
        "p4q_receipt": receipt,
        "evaluator_sha": p.EVAL_SHA,
        "dataset_sha": p.DATA_SHA,
        "graph_sha": {f"{arm}_r{rep}": old[(arm, rep)]["graph_sha"]
                      for arm in ARMS for rep in (1, 2, 3)},
        "n_queries": QUERY_COUNT, "cpu": CPU, "threads": 1,
        "beams": list(BEAMS), "new_rounds_per_graph": ROUNDS,
        "new_evaluator_calls": len(jobs()),
        "historical_p4m_qps_not_mixed_into_new_repeats": True,
    }
    return p, old, pin


def checked_record(rec, job, p, old, pin):
    rnd, rep, arm = job
    tag = f"round{rnd}_rep{rep}_{arm}"
    name = OUT / "logs" / tag
    order = BEAMS if rnd % 2 else tuple(reversed(BEAMS))
    graph = Path(old[(arm, rep)]["graph"])
    cmd = [str(p.EVAL), str(graph), str(p.BASE), str(p.QUERY),
           str(p.GT), ",".join(str(b) for b in order)]
    need(rec["round"] == rnd and rec["build_rep"] == rep and rec["arm"] == arm
         and rec["graph_sha"] == pin["graph_sha"][f"{arm}_r{rep}"]
         and rec["evaluator_sha"] == pin["evaluator_sha"]
         and rec["command"] == cmd and rec["beams_in_order"] == list(order)
         and rec["cpu"] == CPU and rec["nqueries"] == QUERY_COUNT
         and rec["threads"] == 1 and rec["status"] == "NATIVE_SEARCH_PASS",
         "RECEIPT_FIELDS_" + tag)
    sout, tfile = Path(str(name) + ".stdout"), Path(str(name) + ".time")
    for path, key in ((sout, "stdout"), (tfile, "timefile")):
        need(safe_file(path) and rec[key] == str(path) and
             rec[key + "_sha"] == sha256(path), "LOG_SHA_" + tag + "_" + key)
    need("Exit status: 0" in tfile.read_text(errors="replace"), "TIME_EXIT_" + tag)
    rows = parse_native(sout.read_text(errors="replace"))
    need(rec["rows"] == rows, "PARSE_OR_LOG_DRIFT_" + tag)
    for beam in BEAMS:
        original = old[(arm, rep)]["rows"][str(beam)]["recall_at10"]
        need(abs(rows[str(beam)]["recall_at10"] - original) <= 0.00005,
             "RECALL_DRIFT_" + tag + "_b" + str(beam))
    return rows


def run_one(job, p, old, pin):
    rnd, rep, arm = job
    tag = f"round{rnd}_rep{rep}_{arm}"
    base = OUT / "logs" / tag
    stdout, timefile = (Path(str(base) + ext) for ext in (".stdout", ".time"))
    tmpout, tmptime = (Path(str(p) + ".part") for p in (stdout, timefile))
    need(all(not f.exists() and not f.is_symlink() for f in
             (stdout, timefile, tmpout, tmptime)), "PREEXISTING_JOB_OUTPUT_" + tag)
    order = BEAMS if rnd % 2 else tuple(reversed(BEAMS))
    graph = Path(old[(arm, rep)]["graph"])
    need(safe_file(graph) and sha256(graph) == pin["graph_sha"][f"{arm}_r{rep}"],
         "FROZEN_GRAPH_SHA_" + tag)
    cmd = [str(p.EVAL), str(graph), str(p.BASE), str(p.QUERY),
           str(p.GT), ",".join(str(b) for b in order)]
    env = dict(os.environ, LC_ALL="C", PARLAY_NUM_THREADS="1", OMP_NUM_THREADS="1")
    full = ["/usr/bin/time", "-v", "-o", str(tmptime),
            "taskset", "-c", str(CPU), *cmd]
    print(TAG + "_NATIVE_START", tag, "beams", list(order), flush=True)
    begin = time.monotonic()
    with tmpout.open("x") as f:
        proc = subprocess.run(full, stdout=f, stderr=subprocess.STDOUT,
                              env=env, timeout=7200, check=False)
    elapsed = time.monotonic() - begin
    need(proc.returncode == 0, "NATIVE_PROCESS_NONZERO_" + tag + "_" + str(proc.returncode))
    need(safe_file(tmptime) and "Exit status: 0" in
         tmptime.read_text(errors="replace"), "NATIVE_TIME_NONZERO_" + tag)
    rows = parse_native(tmpout.read_text(errors="replace"))
    for beam in BEAMS:
        baseline = old[(arm, rep)]["rows"][str(beam)]["recall_at10"]
        need(abs(rows[str(beam)]["recall_at10"] - baseline) <= 0.00005,
             "NEW_RECALL_ANCHOR_DRIFT_" + tag + "_b" + str(beam))
    os.replace(tmpout, stdout)
    os.replace(tmptime, timefile)
    rec = {"round": rnd, "build_rep": rep, "arm": arm,
           "graph_sha": pin["graph_sha"][f"{arm}_r{rep}"],
           "evaluator_sha": pin["evaluator_sha"],
           "beams_in_order": list(order), "command": cmd,
           "cpu": CPU, "nqueries": QUERY_COUNT, "threads": 1,
           "stdout": str(stdout), "stdout_sha": sha256(stdout),
           "timefile": str(timefile), "timefile_sha": sha256(timefile),
           "wall_s_diagnostic_not_used_as_qps": elapsed,
           "rows": rows, "status": "NATIVE_SEARCH_PASS"}
    checked_record(rec, job, p, old, pin)
    print(TAG + "_NATIVE_PASS", tag,
          "qps368", round(rows["368"]["qps"], 4),
          "qps880", round(rows["880"]["qps"], 4), flush=True)
    return rec


def expected_summary(state):
    data = {(r["round"], r["build_rep"], r["arm"]): r for r in state["records"]}
    byarm = {}
    for arm in ARMS:
        byarm[arm] = {}
        for beam in BEAMS:
            per_graph = []
            for rep in (1, 2, 3):
                vals = [data[(rnd, rep, arm)]["rows"][str(beam)]["qps"]
                        for rnd in range(1, ROUNDS + 1)]
                recalls = [data[(rnd, rep, arm)]["rows"][str(beam)]["recall_at10"]
                           for rnd in range(1, ROUNDS + 1)]
                per_graph.append({"build_rep": rep, "qps_repeats": vals,
                                  "qps_median": statistics.median(vals),
                                  "qps_min": min(vals), "qps_max": max(vals),
                                  "recall_repeats": recalls})
            byarm[arm][str(beam)] = {
                "per_graph": per_graph,
                "mean_of_three_graph_median_qps": statistics.mean(x["qps_median"] for x in per_graph),
                "median_of_three_graph_median_qps": statistics.median(x["qps_median"] for x in per_graph),
                "n_independent_graphs": 3, "new_search_repeats_per_graph": ROUNDS}
    comparisons = {}
    for base, candidate in (("h17", "fast"), ("stock", "fast"), ("stock", "h17")):
        comparisons[base + "_to_" + candidate] = {}
        for beam in BEAMS:
            x = byarm[base][str(beam)]["mean_of_three_graph_median_qps"]
            y = byarm[candidate][str(beam)]["mean_of_three_graph_median_qps"]
            pergraph = []
            for rep in range(3):
                a = byarm[base][str(beam)]["per_graph"][rep]["qps_median"]
                b = byarm[candidate][str(beam)]["per_graph"][rep]["qps_median"]
                pergraph.append(100 * (b / a - 1))
            comparisons[base + "_to_" + candidate][str(beam)] = {
                "ratio_of_mean_graph_medians": y / x,
                "qps_change_pct": 100 * (y / x - 1),
                "per_paired_build_block_qps_change_pct": pergraph}
    return {"status": "REPEATED_100KQ_NATIVE_QPS_AUDIT_PASS",
            "dataset": "MS-Turing1M", "beams": list(BEAMS),
            "nine_frozen_graphs": True,
            "independent_graphs_per_arm": 3,
            "new_search_repeats_per_graph": ROUNDS,
            "native_search_calls": len(jobs()),
            "observed_beam_rows": len(jobs()) * len(BEAMS),
            "p4m_historical_search_not_pooled": True,
            "by_arm": byarm, "comparisons": comparisons,
            "no_formal_noninferiority_equivalence": True,
            "no_measured_p95_p99": True,
            "no_valid_highbeam_avg_cmps": True,
            "stock_R86_vs_h17_fast_R90_vintage_confound": True,
            "qps_latency_proxy_not_per_query_p95": True,
            "guidance": "Compare three graph-level medians; 27 evaluator calls are NOT 27 independent graph replicates."}


def selftest():
    for order in (BEAMS, tuple(reversed(BEAMS))):
        s = "R85_A1C_DYNAMIC_BEAMS count=2\n"
        s += "R72_RECALL_INPUT_PASS graph_nodes=1000000 queries=100000 gt_k=100\n"
        s += "".join(f"R72_RECALL_ROW beam={b} recall={0.99042 if b==368 else 0.99808} "
                     f"qps={1267.9 if b==368 else 570.25} avg_cmps={16000 if b==368 else 4294954990} "
                     "avg_visited=730\n" for b in order)
        s += "R72_RECALL_EVAL_PASS\n"
        rows = parse_native(s)
        need(rows["880"]["avg_cmps_status"] == "INVALID_COUNTER_32BIT_R86_V4"
             and rows["368"]["qps"] > 0, "SELFTEST_NATIVE_PARSER")
    need(len(jobs()) == 27 and len(set(jobs())) == 27, "SELFTEST_JOBS")
    print(TAG + "_SELFTEST_PASS_PARSER_REVERSE_BEAMS_27JOBS", flush=True)


def preflight():
    need(not OUT.exists() and not OUT.is_symlink(), "OUTPUT_ROOT_ALREADY_EXISTS")
    need(OUT.parent.is_dir(), "R90_PROJECT_FOLDER_MISSING")
    p, old, pin = frozen()
    need(len(pin["graph_sha"]) == 9, "SHA_GRAPH_COVERAGE")
    print(TAG + "_PREFLIGHT_PASS_FROZEN_NINE_GRAPHS_P4Q_P4M_EVAL_DATA_SHA",
          "queries", QUERY_COUNT, "new_calls", len(jobs()), "beams", list(BEAMS),
          "CPU", CPU, flush=True)


def run():
    p, old, pin = frozen()
    if not OUT.exists() and not OUT.is_symlink():
        need(OUT.parent.is_dir(), "OUT_PARENT_MISSING")
        OUT.mkdir(mode=0o700)
        (OUT / "logs").mkdir(mode=0o700)
        state = {"status": "RUNNING", "pin": pin, "records": [],
                 "job_order": [list(j) for j in jobs()],
                 "no_build": True}
        atomic(OUT / "progress.json", state, create=True)
    else:
        need(OUT.is_dir() and not OUT.is_symlink()
             and (OUT / "logs").is_dir() and not (OUT / "logs").is_symlink(),
             "OUT_ROOT_INVALID")
        need(not (OUT / "summary.json").exists(), "AUDITED_ALREADY_STOP")
        state = read_json(OUT / "progress.json")
    need(state.get("pin") == pin and state.get("job_order") == [list(j) for j in jobs()]
         and state.get("no_build") is True, "PROGRESS_PIN_OR_PLAN_DRIFT")
    done = [tuple(r[k] for k in ("round", "build_rep", "arm")) for r in state["records"]]
    need(done == jobs()[:len(done)] and len(done) <= len(jobs()), "RESUME_RECORD_ORDER")
    for job, rec in zip(jobs(), state["records"]):
        checked_record(rec, job, p, old, pin)
    for job in jobs()[len(done):]:
        state["records"].append(run_one(job, p, old, pin))
        atomic(OUT / "progress.json", state)
    state["status"] = "NATIVE_ALL_27_DONE_AUDIT_REQUIRED"
    atomic(OUT / "progress.json", state)
    print(TAG + "_RUN_27_OF_27_COMPLETE_AUDIT_REQUIRED", flush=True)


def audit():
    p, old, pin = frozen()
    state = read_json(OUT / "progress.json")
    need(state.get("pin") == pin and state.get("status") ==
         "NATIVE_ALL_27_DONE_AUDIT_REQUIRED" and
         state.get("job_order") == [list(j) for j in jobs()] and
         len(state["records"]) == len(jobs()), "FINAL_MANIFEST_COVERAGE")
    for job, rec in zip(jobs(), state["records"]):
        checked_record(rec, job, p, old, pin)
    summary = expected_summary(state)
    final = OUT / "summary.json"
    if final.exists():
        need(read_json(final) == summary, "SUMMARY_DRIFT_EXISTING")
    else:
        atomic(final, summary, create=True)
    print(TAG + "_AUDIT_PASS_9GRAPHS_3NEW_REPEATS_2BEAMS_100KQ", flush=True)
    print(TAG + "_SUMMARY", str(final), "sha256", sha256(final), flush=True)
    for beam in BEAMS:
        print(TAG + "_FAST_VS_H17_BEAM", beam,
              "pct", summary["comparisons"]["h17_to_fast"][str(beam)]["qps_change_pct"],
              flush=True)


def main():
    need(len(sys.argv) == 2 and sys.argv[1] in
         ("selftest", "preflight", "run", "audit"),
         "USAGE_selftest_preflight_run_audit")
    globals()[sys.argv[1]]()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(TAG + "_HOLD", type(exc).__name__, str(exc), file=sys.stderr, flush=True)
        sys.exit(2)
