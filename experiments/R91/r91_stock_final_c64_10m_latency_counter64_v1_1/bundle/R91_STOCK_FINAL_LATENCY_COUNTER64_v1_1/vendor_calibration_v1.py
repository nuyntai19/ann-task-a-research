#!/usr/bin/env python3
"""R91 G6 10M C512/C64 — pinned, isolated, repeated Search-only experiment.

No BUILD, no graph mutation, no source compilation, no overwrites. Ten fixed beams per native invocation across two 10M graphs.
Measured Recall/QPS at sampled beams; linear matched-floor interpolation is exploratory.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
import os
import re
import shutil
import signal
import statistics
import subprocess
import sys
import time
from pathlib import Path

TAG = "R91_G6_10M_MATCHED_RECALL_CALIB_V1"
H = Path.home()
ROOT = H / "ann-task-a"
R91 = ROOT / "experiments/R91"
PARENT = R91 / "r91_g6_mst10m_c512_c64_pair_v1_3"
OUT = R91 / "r91_g6_mst10m_matched_recall_calib_v1"
EVAL = R91 / "r91_g1b_v2_native_eval_mst10m_exactguard_v1_1/r91_mst10m_recall_exactguard_v2"
BASE = ROOT / "data/MSTuring_10M_v1/base.10M.fbin"
QUERY = ROOT / "data/MSTuring_10M_v1/query.public.100K.fbin"
GT = ROOT / "data/MSTuring_10M_v1/groundtruth.public.100K.ibin"
MEMORY_MAX = 24*1024**3
BEAMS = (512, 544, 560, 576, 608, 1664, 1728, 1760, 1792, 1856)
ARMS = ("C512", "C64")
TARGETS = (0.990, 0.998)
PAIRED = R91 / "r91_g6_mst10m_paired_search_3r_v1"
PAIRED_PINS = {"preflight.json":"0d04fca67e6ff6364b6ddafb9a593502c86af2e6ecf648e59cb9b775c1022105",
               "paired_search_summary.json":"0a28e7c5ef6d84a1953735a809ab5ae75d8e39532ad357e8efb7b7f09ed51091"}
FILE_PINS = {
    "preflight.json": "0e968c761d749f3098956b1d1226923b67d67c050a5fc10b95b40f44e076a14e",
    "build_pair_audit.json": "e4816122d38bded111b158c227a6d28ef2d1d28130e38cefc83f45e4e41beb3b",
    "search_pair_audit.json": "9604f05dc7ca220ce06dbd8f891048328a801441701da5dbfe50c4e1c67a834d",
    "runs/C512/receipt.json": "b520f072d7c782a5efcb3ca5f3573d4bf9eddf1270861b06cafb1cdc37272082",
    "runs/C64/receipt.json": "b10c89d2075046b91b8d738cd9c245e9a3ba74e920c6281e676c2db0916475e6",
    "search/C512/receipt.json": "9ea0862279df3b9cf3641d2b0f12e6a7e56e0e5cb25e5da2fe0a5ebc984106a7",
    "search/C64/receipt.json": "874eaafa5ea6d746de7f9131745cbd0b64477601ae52f8c1129a330a7f393ec1",
}
GRAPH_PINS = {
    "C512": "5924279e3065953f407003fd7217476f04b214295c4f3801db510628c9e6c443",
    "C64": "4c54e712c1ba859201a33a8754534c9e3f855664c63db1075a4cf7803dea6e8d",
}
DATA_PINS = {
    BASE: "e7756f6b54a07e8af171c7644ce2e1be6d7053ee2a2c30c4b02f99e85984b700",
    QUERY: "48d087a17bec15a5ec9ea526fe9bd14ac31bbbb5cd200817b341adbb77695644",
    GT: "77b558bd3b77e4cc1149384996b953b040e412477eb0df9889718fc13e17aff2",
    EVAL: "394c6564750722001897254939ba4895e0d7ae6a6dbab44748c30937ea0413c9",
}
LINE = re.compile(r"^R72_RECALL_ROW\s+beam=(\d+)\s+recall=([^\s]+)\s+qps=([^\s]+)\s+avg_cmps=([^\s]+)\s+avg_visited=([^\s]+)\s*$", re.M)


def require(condition, reason):
    if not condition:
        raise RuntimeError(f"{TAG}_HOLD_{reason}")


def regular(p):
    p = Path(p)
    return p.is_file() and not p.is_symlink()


def sha(p):
    require(regular(p), "MISSING_OR_SYMLINK_" + Path(p).name)
    h = hashlib.sha256()
    with Path(p).open("rb") as f:
        for chunk in iter(lambda: f.read(8<<20), b""):
            h.update(chunk)
    return h.hexdigest()


def pin(p, digest, label):
    require(sha(p) == digest, "SHA_MISMATCH_"+label)


def jload(p):
    require(regular(p), "JSON_MISSING_"+Path(p).name)
    with Path(p).open(encoding="utf-8") as f:
        return json.load(f)


def atom(p, data):
    p = Path(p)
    require(not p.exists() and not p.is_symlink(), "OUTPUT_EXISTS_"+p.name)
    temp = p.with_name(p.name+".part")
    require(not temp.exists() and not temp.is_symlink(), "PART_EXISTS_"+p.name)
    with temp.open("x", encoding="utf-8") as f:
        json.dump(data, f, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False)
        f.write("\n")
        f.flush()
        os.fsync(f.fileno())
    os.replace(temp, p)


def source_integrity(check_bulk):
    require(PARENT.is_dir() and not PARENT.is_symlink(), "PARENT_MISSING")
    for name, digest in FILE_PINS.items():
        pin(PARENT/name, digest, "PARENT_"+name.replace("/","_"))
    require(PAIRED.is_dir() and not PAIRED.is_symlink(), "PAIRED_PARENT_MISSING")
    for name, digest in PAIRED_PINS.items():
        pin(PAIRED/name, digest, "PAIRED_"+name.replace("/","_"))
    pre = jload(PARENT/"preflight.json")
    bld = jload(PARENT/"build_pair_audit.json")
    srch = jload(PARENT/"search_pair_audit.json")
    pr = jload(PAIRED/"preflight.json")
    ps = jload(PAIRED/"paired_search_summary.json")
    require(pre["status"] == "PREFLIGHT_PASS_NO_BUILD", "PARENT_PREFLIGHT_STATUS")
    require(bld["status"] == "TWO_10M_NATIVE_BUILDS_FULL_GRAPH_WORK_RESOURCE_AUDIT_PASS_SEARCH_NOT_RUN", "PARENT_BUILD_STATUS")
    require(srch["status"] == "TWO_10M_NATIVE_FIXED_BEAM_SEARCH_AUDIT_PASS" and srch["search_valid_for_both"], "PARENT_SEARCH_STATUS")
    require(srch["build_pair_sha"] == FILE_PINS["build_pair_audit.json"], "PARENT_SEARCH_BUILD_LINK")
    require(pre["inputs"]["g6_elf"] == bld["protocol"]["source_sha"], "PARENT_ELF_LINK")
    require(pre["protocol"]["cap_options"] == [512,64] and pre["protocol"]["max_mem_bytes"] == MEMORY_MAX and pre["protocol"]["swap_bytes"] == 0, "PARENT_PROTOCOL")
    require(pr["status"] == "PREFLIGHT_PASS_NO_NATIVE_SEARCH" and ps["status"] == "THREE_ROUND_PAIRED_FIXED_BEAM_SEARCH_AUDIT_PASS", "PAIRED_STATUS")
    require(ps["preflight_sha256"] == PAIRED_PINS["preflight.json"] and ps["parent_build_sha256"] == FILE_PINS["build_pair_audit.json"] and ps["parent_search_sha256"] == FILE_PINS["search_pair_audit.json"], "PAIRED_LINEAGE")
    require(ps["order"] == [["C512","C64"],["C64","C512"],["C512","C64"]], "PAIRED_ORDER")
    require(ps["graph_sha256"] == GRAPH_PINS, "PAIRED_GRAPH_PIN")
    require(len(ps["slots"]) == 6, "PAIRED_SLOT_COUNT")
    for z in ps["slots"]:
        require(z["arm"] in ARMS, "PAIRED_BAD_ARM")
        pin(PAIRED/"slots"/z["slot"]/"receipt.json", z["receipt_sha256"], "PAIRED_RECEIPT_"+z["slot"])
    for arm in ARMS:
        br = jload(PARENT/"runs"/arm/"receipt.json")
        srec = jload(PARENT/"search"/arm/"receipt.json")
        require(br["status"] == "BUILD_GRAPH_WORK_AUDIT_PASS" and br["error"] is None, "PARENT_BUILD_RECEIPT_"+arm)
        require(srec["status"] == "SEARCH_AUDITABLE_NATIVE_PASS" and srec["error"] is None and srec["quality_floor_pass"], "PARENT_SEARCH_RECEIPT_"+arm)
        require(br["graph"]["sha256"] == GRAPH_PINS[arm] == bld[arm]["graph_sha"] == srec["graph_sha256"], "PARENT_GRAPH_LINK_"+arm)
        require(srec["eval_binary_sha256"] == DATA_PINS[EVAL] and srec["build_receipt_sha256"] == FILE_PINS[f"runs/{arm}/receipt.json"], "PARENT_EVAL_RECEIPT_LINK_"+arm)
        require(srch["source_receipts"][arm] == FILE_PINS[f"search/{arm}/receipt.json"], "PARENT_SEARCH_RECEIPT_LINK_"+arm)
        require(br["graph"]["full_all_vertices_audit"] and br["graph"]["nodes"] == 10000000, "PARENT_GRAPH_AUDIT_"+arm)
    if check_bulk:
        for p, digest in DATA_PINS.items():
            pin(p,digest,"DATA_"+p.name)
        require(EVAL.is_file() and os.access(EVAL,os.X_OK),"EVAL_NOT_EXECUTABLE")
        for arm,digest in GRAPH_PINS.items():
            pin(PARENT/"runs"/arm/"graph.bin",digest,"GRAPH_"+arm)
    else:
        pin(EVAL,DATA_PINS[EVAL],"EXACTGUARD_ELF")
    return srch


def cgroup(strict):
    p = Path("/proc/self/cgroup")
    require(regular(p), "CGROUP_PROC_MISSING")
    lines = [line.split("::", 1)[1] for line in p.read_text().splitlines() if line.startswith("0::")]
    require(len(lines) == 1 and lines[0].startswith("/user.slice/") and ".." not in Path(lines[0]).parts, "NO_USER_CGROUP_V2")
    root = Path("/sys/fs/cgroup") / lines[0].lstrip("/")
    names = ["memory.max","memory.swap.max","memory.swap.current","memory.current","memory.peak","memory.events"]
    v = {name: (root/name).read_text().strip() if regular(root/name) else None for name in names}
    if strict:
        require(v["memory.max"] == str(MEMORY_MAX), "CGROUP_24GIB_LIMIT_MISSING")
        require(v["memory.swap.max"] == "0" and v["memory.swap.current"] == "0", "CGROUP_SWAP_NOT_ZERO")
    return root, v


def evparse(s):
    result = {}
    for line in (s or "").splitlines():
        x = line.split()
        if len(x) == 2:
            try: result[x[0]] = int(x[1])
            except ValueError: pass
    return result


def mem_available_kib():
    txt = Path("/proc/meminfo").read_text()
    m = re.search(r"^MemAvailable:\s+(\d+)\s+kB", txt, re.M)
    require(m is not None, "MEMAVAILABLE_NOT_FOUND")
    return int(m.group(1))


def disk_free_gib():
    return shutil.disk_usage(R91).free / 1024**3


def environment_gate():
    require(sys.platform == "linux" and os.name == "posix", "NOT_LINUX")
    require(all(Path(x).is_file() for x in ("/usr/bin/time","/usr/bin/taskset")), "DEPENDENCIES_MISSING")
    require(shutil.which("systemd-run") is not None, "SYSTEMD_RUN_MISSING")
    require(0 in os.sched_getaffinity(0), "CPU_0_NOT_AVAILABLE")
    require(mem_available_kib() >= 10*1024**2, "HOST_MEMAVAILABLE_LT_10GIB")
    require(disk_free_gib() >= 8, "DISK_FREE_LT_8GIB")


def parse_stdout(s):
    require(s.count(f"R85_A1C_DYNAMIC_BEAMS count={len(BEAMS)}") == 1, "BEAM_COUNT_MARKER")
    inp = [x for x in s.splitlines() if x.startswith("R72_RECALL_INPUT_PASS ")]
    require(len(inp) == 1 and all(k in inp[0] for k in ("graph_nodes=10000000", "queries=100000", "gt_k=100")), "SEARCH_INPUT_PROOF")
    require(s.count("R72_RECALL_EVAL_PASS") == 1, "EVAL_END_MARKER")
    out = []
    for m in LINE.finditer(s):
        try:
            beam = int(m.group(1)); rec = float(m.group(2)); qps = float(m.group(3)); vis = float(m.group(5))
        except ValueError: require(False, "INVALID_METRIC")
        require(0 <= rec <= 1 and math.isfinite(rec) and qps > 0 and math.isfinite(qps) and vis >= 0 and math.isfinite(vis), "METRIC_RANGE")
        out.append({"beam":beam,"recall_at10":rec,"qps":qps,"avg_visited":vis,"inverse_qps_us_not_p95":1e6/qps})
    require([x["beam"] for x in out] == list(BEAMS), "MISSING_BEAMS_OR_WRONG_ORDER")
    return out


def timeparse(p):
    s = Path(p).read_text(errors="replace")
    def val(label):
        m = re.search(r"^\s*"+re.escape(label)+r":\s*([^\n]+)", s, re.M)
        return m.group(1).strip() if m else None
    return {
        "exit_status":val("Exit status"),
        "max_rss_kib":int(val("Maximum resident set size (kbytes)") or 0),
        "major_faults":int(val("Major (requiring I/O) page faults") or -1),
        "swaps":int(val("Swaps") or -1),
        "file_system_inputs":int(val("File system inputs") or -1),
        "file_system_outputs":int(val("File system outputs") or -1),
    }


def resources_good(m):
    if m.get("status") != "COMPLETED" or m.get("exit_code") != 0 or m.get("sampled_peak_swap") != 0 or m.get("swap_after") != 0:
        return False
    if not (0 < m.get("cg_peak_bytes",0) < MEMORY_MAX and m.get("min_available_kib",0) >= int(1.5*1024**2) and m.get("min_disk_gib",0) >= 8):
        return False
    e = m.get("events_delta",{})
    return all(e.get(k,0) == 0 for k in ("max","oom","oom_kill","oom_group_kill","high"))


def monitor(cmd, stdout, stderr, scope, max_seconds=7200):
    root, vals = scope
    orig = evparse(vals["memory.events"])
    state = {"status":"RUNNING", "samples":0, "sampled_peak_swap":0, "min_available_kib":mem_available_kib(),
             "min_disk_gib":disk_free_gib(), "exit_code":None, "max_seconds":max_seconds}
    env = os.environ.copy()
    env.update({"PARLAY_NUM_THREADS":"1", "OMP_NUM_THREADS":"1", "OPENBLAS_NUM_THREADS":"1", "MKL_NUM_THREADS":"1", "LC_ALL":"C"})
    begin = time.monotonic()
    p = None
    try:
        with stdout.open("x") as fo, stderr.open("x") as fe:
            p = subprocess.Popen(cmd,stdout=fo,stderr=fe,env=env,start_new_session=True)
            while True:
                rc = p.poll()
                _,v = cgroup(False)
                state["samples"] += 1
                state["sampled_peak_swap"] = max(state["sampled_peak_swap"], int(v["memory.swap.current"] or 0))
                state["min_available_kib"] = min(state["min_available_kib"],mem_available_kib())
                state["min_disk_gib"] = min(state["min_disk_gib"],disk_free_gib())
                current_events = evparse(v["memory.events"])
                delta = {k:current_events.get(k,0)-orig.get(k,0) for k in current_events}
                trouble = ((time.monotonic()-begin>max_seconds) or state["sampled_peak_swap"]>0 or
                           state["min_available_kib"]<int(1.5*1024**2) or state["min_disk_gib"]<8 or
                           any(delta.get(k,0)>0 for k in ("max","oom","oom_kill","oom_group_kill","high")))
                if rc is not None:
                    break
                if trouble:
                    state["status"] = "ABORTED_RESOURCE_OR_TIMEOUT"
                    os.killpg(p.pid,signal.SIGTERM)
                    try: p.wait(timeout=6)
                    except subprocess.TimeoutExpired:
                        os.killpg(p.pid,signal.SIGKILL)
                        p.wait(timeout=10)
                    break
                time.sleep(1)
    except BaseException:
        if p is not None and p.poll() is None:
            os.killpg(p.pid,signal.SIGTERM)
            try: p.wait(timeout=6)
            except subprocess.TimeoutExpired:
                os.killpg(p.pid,signal.SIGKILL)
                p.wait(timeout=10)
        raise
    _,v = cgroup(False)
    latest = evparse(v["memory.events"])
    state.update({"exit_code":p.returncode,"elapsed_s":time.monotonic()-begin,
                  "cg_peak_bytes":int(v["memory.peak"] or 0), "swap_after":int(v["memory.swap.current"] or 0),
                  "events_delta":{k:latest.get(k,0)-orig.get(k,0) for k in latest}})
    if state["status"] == "RUNNING": state["status"] = "COMPLETED"
    return state




def verify_preflight():
    j = jload(OUT / "preflight.json")
    require(j["status"] == "PREFLIGHT_PASS_NO_NATIVE_CALIBRATION", "PREFLIGHT_STATUS")
    require(j["script_sha256"] == sha(Path(__file__)), "PREFLIGHT_SCRIPT_SHA_DRIFT")
    require(j["parent_search_sha256"] == FILE_PINS["search_pair_audit.json"], "PREFLIGHT_PARENT_SEARCH_DRIFT")
    require(j["paired_summary_sha256"] == PAIRED_PINS["paired_search_summary.json"], "PREFLIGHT_PAIRED_SUMMARY_DRIFT")
    require(j["beams"] == list(BEAMS) and j["targets"] == list(TARGETS), "PREFLIGHT_GRID_DRIFT")
    return j


def preflight():
    require(not OUT.exists() and not OUT.is_symlink(), "OUTPUT_ROOT_EXISTS")
    environment_gate()
    source_integrity(check_bulk=True)
    OUT.mkdir(parents=True, exist_ok=False)
    atom(OUT / "preflight.json", {
        "status": "PREFLIGHT_PASS_NO_NATIVE_CALIBRATION", "script_sha256": sha(Path(__file__)),
        "parent_preflight_sha256": FILE_PINS["preflight.json"],
        "parent_build_sha256": FILE_PINS["build_pair_audit.json"],
        "parent_search_sha256": FILE_PINS["search_pair_audit.json"],
        "paired_preflight_sha256": PAIRED_PINS["preflight.json"],
        "paired_summary_sha256": PAIRED_PINS["paired_search_summary.json"],
        "source_graph_sha256": GRAPH_PINS,
        "evaluator_sha256": DATA_PINS[EVAL],
        "data_sha256": {p.name:h for p,h in DATA_PINS.items() if p!=EVAL},
        "memory_max_bytes": MEMORY_MAX, "swap_max_bytes":0, "cpu_search":"0",
        "beams":list(BEAMS), "targets":list(TARGETS), "arms":list(ARMS), "n_queries":100000,
        "claims_limit":"10-beam fixed-grid measured Search. Interpolated QPS at same target Recall is an estimate, not native exactly matched Recall. One frozen graph/arm; no p95/p99 or significance claim."
    })
    print(TAG+"_PREFLIGHT_PASS_NO_SEARCH "+sha(OUT/"preflight.json"),flush=True)


def calibration_slot(arm):
    require(arm in ARMS,"UNKNOWN_ARM")
    scope = cgroup(True)
    environment_gate()
    verify_preflight()
    source_integrity(check_bulk=False)
    # Re-pin original source data bytes and the complete graph immediately before native Search.
    for p,digest in DATA_PINS.items():
        pin(p,digest,"SLOT_INPUT_"+p.name)
    if arm=="C64":
        require(jload(OUT/"runs"/"C512"/"receipt.json").get("status")=="CALIBRATION_SLOT_PASS","PRIOR_C512_NOT_PASS")
    graph = PARENT/"runs"/arm/"graph.bin"
    pin(graph,GRAPH_PINS[arm],"GRAPH_BEFORE_"+arm)
    target=OUT/"runs"/arm
    require(not target.exists() and not target.is_symlink(),"SLOT_COLLISION_"+arm)
    target.mkdir(parents=True,exist_ok=False)
    tm,so,se=(target/name for name in ("native.time","native.stdout","native.stderr"))
    cmd=["/usr/bin/time","-v","-o",str(tm),"/usr/bin/taskset","-c","0",str(EVAL),str(graph),str(BASE),str(QUERY),str(GT),",".join(map(str,BEAMS))]
    atom(target/"preregister.json",{
        "arm":arm,"command":cmd,"graph_sha256":GRAPH_PINS[arm],"eval_sha256":DATA_PINS[EVAL],
        "script_sha256":sha(Path(__file__)),"preflight_sha256":sha(OUT/"preflight.json"),
        "search_only":True,"interpolation_is_not_exact_matched_recall":True,
        "cgroup_root":str(scope[0]),"timestamp":time.time()
    })
    print(TAG+"_START_SLOT_"+arm,flush=True)
    mon=monitor(cmd,so,se,scope,max_seconds=10800)
    err=None;metrics=None;gnu=None
    try:
        require(resources_good(mon),"RESOURCE_OR_NATIVE_EXIT")
        require(se.stat().st_size==0,"SEARCH_STDERR_NOT_EMPTY")
        gnu=timeparse(tm)
        require(gnu["exit_status"]=="0" and gnu["swaps"]==0 and gnu["max_rss_kib"]>0,"GNU_TIME_EXIT_OR_SWAP")
        require(gnu["major_faults"]>=0 and gnu["file_system_inputs"]>=0,"GNU_TIME_NEGATIVE_COUNTER")
        metrics=parse_stdout(so.read_text(errors="replace"))
        orig=jload(PARENT/"search_pair_audit.json")["results"][arm]
        for old in orig:
            curr=next(x for x in metrics if x["beam"]==old["beam"])
            require(abs(curr["recall_at10"]-old["recall_at10"])<=5e-8,"RECALL_REFERENCE_DRIFT_"+arm)
            require(abs(curr["avg_visited"]-old["avg_visited"])<=0.01,"VISITS_REFERENCE_DRIFT_"+arm)
        pin(graph,GRAPH_PINS[arm],"GRAPH_AFTER_"+arm)
    except Exception as exc:
        err=str(exc)
    receipt={"status":"CALIBRATION_SLOT_PASS" if err is None else "CALIBRATION_SLOT_HOLD_PRESERVE_OUTPUT",
             "arm":arm,"error":err,"graph_sha256":GRAPH_PINS[arm],
             "parent_build_sha256":FILE_PINS["build_pair_audit.json"],
             "parent_search_sha256":FILE_PINS["search_pair_audit.json"],
             "preflight_sha256":sha(OUT/"preflight.json"),
             "beams":list(BEAMS),"resource":mon,"gnu_time":gnu,"metrics":metrics,
             "files_sha256":{p.name:sha(p) for p in (so,se,tm) if regular(p)}}
    atom(target/"receipt.json",receipt)
    print(TAG+"_"+receipt["status"]+"_"+arm+" receipt_sha256 "+sha(target/"receipt.json"),flush=True)
    require(err is None,"CALIBRATION_SLOT_FAILED_"+arm)


def estimate_at_target(metrics, target):
    require([m["beam"] for m in metrics]==list(BEAMS),"INTERP_BEAM_GRID")
    # Report a non-monotone Recall curve instead of silently interpolating it.
    monotone=all(metrics[i]["recall_at10"]+5e-8>=metrics[i-1]["recall_at10"] for i in range(1,len(metrics)))
    item={"target_recall":target,"recall_monotone_non_decreasing":monotone}
    if not monotone:
        return {**item,"status":"NOT_INTERPOLATED_NONMONOTONE_RECALL"}
    for i in range(1,len(metrics)):
        low,high=metrics[i-1],metrics[i]
        if low["recall_at10"]<target<=high["recall_at10"]:
            dr=high["recall_at10"]-low["recall_at10"]
            if dr<=0:
                return {**item,"status":"NOT_INTERPOLATED_ZERO_RECALL_GAP"}
            t=(target-low["recall_at10"])/dr
            require(-1e-10<=t<=1+1e-10,"INTERP_FRACTION_OUTSIDE_RANGE")
            return {**item,"status":"LINEAR_INTERPOLATION_ESTIMATE_ONLY",
                    "lower_measured_beam":low["beam"],"upper_measured_beam":high["beam"],
                    "lower_measured_recall":low["recall_at10"],"upper_measured_recall":high["recall_at10"],
                    "lower_measured_qps":low["qps"],"upper_measured_qps":high["qps"],
                    "fraction":t,"estimated_beam":low["beam"]+t*(high["beam"]-low["beam"]),
                    "estimated_qps":low["qps"]+t*(high["qps"]-low["qps"]) }
    return {**item,"status":"NOT_INTERPOLATED_TARGET_UNBRACKETED"}


def make_summary(slots):
    require(len(slots)==2 and [x["arm"] for x in slots]==list(ARMS),"SUMMARY_ARMS")
    fits={arm:{str(target):estimate_at_target(next(s for s in slots if s["arm"]==arm)["metrics"],target)
               for target in TARGETS} for arm in ARMS}
    comparisons={}
    for t in TARGETS:
        left,right=(fits[arm][str(t)] for arm in ARMS)
        if all(x["status"]=="LINEAR_INTERPOLATION_ESTIMATE_ONLY" for x in (left,right)):
            comparisons[str(t)]={"status":"ESTIMATED_AT_SAME_TARGET_RECALL_NOT_NATIVE_MATCH",
                 "target_recall":t,"estimated_qps_C512":left["estimated_qps"],"estimated_qps_C64":right["estimated_qps"],
                 "estimated_ratio_C64_over_C512":right["estimated_qps"]/left["estimated_qps"],
                 "estimated_delta_percent":100*(right["estimated_qps"]/left["estimated_qps"]-1)}
        else:
            comparisons[str(t)]={"status":"MATCHED_ESTIMATE_UNAVAILABLE","target_recall":t,
                                 "C512_status":left["status"],"C64_status":right["status"]}
    return {"status":"TEN_BEAM_BOTH_GRAPHS_NATIVE_CALIBRATION_AUDIT_PASS",
        "parent_preflight_sha256":FILE_PINS["preflight.json"],
        "parent_build_sha256":FILE_PINS["build_pair_audit.json"],
        "parent_search_sha256":FILE_PINS["search_pair_audit.json"],
        "paired_summary_sha256":PAIRED_PINS["paired_search_summary.json"],
        "preflight_sha256":sha(OUT/"preflight.json"),"graph_sha256":GRAPH_PINS,
        "beams":list(BEAMS),"targets":list(TARGETS),"slots":slots,
        "interpolated_by_arm":fits,"estimated_same_recall_comparison":comparisons,
        "limitations":["Measured fixed-beam Recall/QPS is native; interpolated QPS is model estimate, not measured at precisely matched Recall",
          "Fixed source graphs one per arm and one Search calibration process per arm; no statistical matched-Recall speedup claim",
          "True crossing may occur between measured beams; not proof global minimum beam",
          "Legacy high-beam avg_cmps int32 untrusted and omitted; QPS inverse is not p95/p99 query latency",
          "No BUILD, compile, graph mutation, or source modification"]}


def audit(verify_only=False):
    verify_preflight()
    source_integrity(check_bulk=False)
    slots=[]
    for arm in ARMS:
        d=OUT/"runs"/arm
        j=jload(d/"receipt.json")
        require(j["status"]=="CALIBRATION_SLOT_PASS" and j["arm"]==arm and j["error"] is None,"INVALID_RECEIPT_"+arm)
        require(j["beams"]==list(BEAMS) and j["graph_sha256"]==GRAPH_PINS[arm],"GRAPH_OR_GRID_DRIFT_"+arm)
        require(j["preflight_sha256"]==sha(OUT/"preflight.json"),"SLOT_PRELFIGHT_DRIFT_"+arm)
        require(j["parent_search_sha256"]==FILE_PINS["search_pair_audit.json"],"SLOT_SOURCE_DRIFT_"+arm)
        require(resources_good(j["resource"]),"SLOT_RESOURCES_DRIFT_"+arm)
        require(j["gnu_time"]["exit_status"]=="0" and j["gnu_time"]["swaps"]==0,"SLOT_TIME_DRIFT_"+arm)
        for name,digest in j["files_sha256"].items():
            pin(d/name,digest,"SLOT_LOG_"+arm+"_"+name)
        require(set(j["files_sha256"])=={"native.stdout","native.stderr","native.time"},"SLOT_LOG_INVENTORY_"+arm)
        require((d/"native.stderr").stat().st_size==0,"SLOT_STDERR_DRIFT_"+arm)
        parsed=parse_stdout((d/"native.stdout").read_text(errors="replace"))
        require(parsed==j["metrics"],"PARSE_READBACK_DRIFT_"+arm)
        reference=jload(PARENT/"search_pair_audit.json")["results"][arm]
        for old in reference:
            curr=next(x for x in parsed if x["beam"]==old["beam"])
            require(abs(curr["recall_at10"]-old["recall_at10"])<=5e-8,"RECALL_REFERENCE_DRIFT_"+arm)
            require(abs(curr["avg_visited"]-old["avg_visited"])<=0.01,"VISIT_REFERENCE_DRIFT_"+arm)
        for key,target in ((576,.990),(1792,.998)):
            require(next(x["recall_at10"] for x in parsed if x["beam"]==key)>=target,"KNOWN_BEAM_RECALL_FLOOR_DRIFT_"+arm)
        slots.append({"arm":arm,"receipt_sha256":sha(d/"receipt.json"),
            "metrics":parsed,"cgroup_peak_bytes":j["resource"]["cg_peak_bytes"],
            "resource_status":j["resource"]["status"]})
    for arm,digest in GRAPH_PINS.items():
        pin(PARENT/"runs"/arm/"graph.bin",digest,"GRAPH_FINAL_"+arm)
    summary=make_summary(slots)
    if verify_only:
        require(jload(OUT/"matched_recall_calibration_summary.json")==summary,"SUMMARY_READBACK_MISMATCH")
    else:
        atom(OUT/"matched_recall_calibration_summary.json",summary)
    print(TAG+("_READONLY_AUDIT_PASS " if verify_only else "_TEN_BEAM_TWO_GRAPH_CALIBRATION_AUDIT_PASS ")+sha(OUT/"matched_recall_calibration_summary.json"),flush=True)
    for target in TARGETS:
        print(TAG+"_TARGET_"+str(target)+" "+json.dumps(summary["estimated_same_recall_comparison"][str(target)],sort_keys=True),flush=True)


def selftest():
    require(MEMORY_MAX==25769803776 and len(BEAMS)==10 and sorted(BEAMS)==list(BEAMS),"STATIC_GRID")
    require(BEAMS==(512,544,560,576,608,1664,1728,1760,1792,1856),"GRID_DRIFT")
    require(TARGETS==(.990,.998) and ARMS==("C512","C64"),"TARGET_OR_ARM_DRIFT")
    require(EVAL==R91/"r91_g1b_v2_native_eval_mst10m_exactguard_v1_1/r91_mst10m_recall_exactguard_v2","EXACTGUARD_PATH_DRIFT")
    require(PAIRED==R91/"r91_g6_mst10m_paired_search_3r_v1","PAIRED_PATH_DRIFT")
    require(DATA_PINS[EVAL]=="394c6564750722001897254939ba4895e0d7ae6a6dbab44748c30937ea0413c9","EVAL_SHA_DRIFT")
    fixture="R85_A1C_DYNAMIC_BEAMS count=10\nR72_RECALL_INPUT_PASS graph_nodes=10000000 queries=100000 gt_k=100\n"
    recall=[.989, .9895, .9897, .99114603, .992, .9979, .99797, .99801, .99810398, .99825]
    qps=[900,875,860,803,780,335,332,329,325,321]
    visit=[440,450,460,480,500,960,975,983,999,1010]
    for i,b in enumerate(BEAMS):
        fixture+=f"R72_RECALL_ROW beam={b} recall={recall[i]} qps={qps[i]} avg_cmps=-1 avg_visited={visit[i]}\n"
    fixture+="R72_RECALL_EVAL_PASS\n"
    p=parse_stdout(fixture)
    require(len(p)==10 and [x["beam"] for x in p]==list(BEAMS),"PARSE_10_BEAMS")
    for bad in (fixture.replace("count=10","count=2"), fixture.replace("beam=1856","beam=1857"),
                fixture.replace("queries=100000","queries=1000"), fixture.replace("qps=900","qps=nan"),
                fixture.replace("R72_RECALL_EVAL_PASS","EVALUATOR_NOT_DONE")):
        try: parse_stdout(bad)
        except RuntimeError: pass
        else: require(False,"MALFORMED_OUTPUT_WAS_ACCEPTED")
    for t in TARGETS:
        f=estimate_at_target(p,t)
        require(f["status"]=="LINEAR_INTERPOLATION_ESTIMATE_ONLY" and f["estimated_qps"]>0,"VALID_BRACKET_MISSING")
    below=[{**x,"recall_at10":.97} for x in p]
    require(estimate_at_target(below,.998)["status"]=="NOT_INTERPOLATED_TARGET_UNBRACKETED","EXTRAPOLATION_FORBIDDEN")
    crooked=[dict(x) for x in p];crooked[2]["recall_at10"]-=.001
    require(estimate_at_target(crooked,.990)["status"]=="NOT_INTERPOLATED_NONMONOTONE_RECALL","NONMONOTONE_NOT_CAUGHT")
    good={"status":"COMPLETED","exit_code":0,"sampled_peak_swap":0,"swap_after":0,"cg_peak_bytes":8*1024**3,
          "min_available_kib":4*1024**2,"min_disk_gib":100,"events_delta":{"max":0,"oom":0,"oom_kill":0,"oom_group_kill":0,"high":0}}
    require(resources_good(good),"CLEAN_RESOURCE_REJECTED")
    for patch in ({"sampled_peak_swap":1},{"swap_after":1},{"cg_peak_bytes":MEMORY_MAX},{"events_delta":{"oom":1}},{"min_available_kib":1}):
        require(not resources_good({**good,**patch}),"RESOURCE_MUTATION_ACCEPTED")
    print(TAG+"_SELFTEST_PASS_10BEAM_PINS_PARSER_MUTATIONS_INTERPOLATION_NO_EXTRAPOLATION_RESOURCE_GATES_SEARCH_ONLY",flush=True)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("mode",choices=("selftest","scopecheck","preflight","run-arm","audit"))
    parser.add_argument("--arm",choices=ARMS)
    parser.add_argument("--verify-only",action="store_true")
    args=parser.parse_args()
    try:
        require(not args.verify_only or args.mode=="audit","VERIFY_ONLY_AUDIT_MODE_REQUIRED")
        if args.mode=="selftest":selftest()
        elif args.mode=="scopecheck":
            scope=cgroup(True);print(TAG+"_SCOPE_PROBE_PASS_24GIB_ZERO_SWAP "+str(scope[0]),flush=True)
        elif args.mode=="preflight":preflight()
        elif args.mode=="run-arm":
            require(args.arm is not None,"ARM_REQUIRED");calibration_slot(args.arm)
        else:audit(verify_only=args.verify_only)
    except Exception as exc:
        print(TAG+"_HOLD "+type(exc).__name__+" "+str(exc),file=sys.stderr,flush=True)
        sys.exit(2)

if __name__=="__main__":main()
