#!/usr/bin/env python3
"""R84.7 — matched SIFT100K four-P-core D0 versus Adaptive Leaf Workspace W.

Independent 6-BUILD pilot on i5-14600KF; provenance gated by R84.4/4b/5/6.
No source edits, no rebuild of binaries, no SEARCH/Recall, no SIFT1M, no Git.
All new files only in experiments/H84/r84_7_workspace_pcore4_sift100k/.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import shlex
import statistics
import struct
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

PIN = "443a328dc71a3b7be753d52ca2b3c9a4ba77f3fd"
TARGET = "neighbors-pipnn_FLOAT_T_EUCLIDEAN"
BASE_SHA = "e50ff1bc34bcc6d1c97dd001023c09a666971cde64605cc06671ed8a8ff1ed12"
GRAPH_8K_SHA = "9546734326e6045d6fe777d6d1725a76161bad65ba373f2b78b4efeda9a4b1ae"
BINARY_SHA = {
    "D0": "7340ce1817f1272d0137bb02ef8dea79756a5fa9252037d29afc3af670f6e48f",
    "W":  "b79cada58551a8893c1c6fb81fd868ecd521830825ae1eb21ed887e46ec8ef95",
}
SOURCE_SHA = {
    "algorithms/PipNN/pipnn.h": "f4391ad8712d7757423dca872f9042c3271660dffde384a85b93854b9692f288",
    "algorithms/PipNN/pipnn_utils.h": "7083e8183554a1cb586b70cdb4c57920f49ec5a50680096aecf6b873f596595d",
    "algorithms/utils/graph.h": "17e51779f32db56c9c50b6d514a8ff68539fd19b734804df3abdb63f88dd443e",
    "algorithms/utils/r70_two_tier_lshgraph.h": "ac0bece4804c7bc552b30db0df57ee92492033065cef62330ddb58a19d470af1",
}
N, DIM, MAX_DEG, THREADS, REPS = 100000, 128, 64, 4, 3
CPU_SET = (0, 2, 4, 6)
PLAN = (("D0", 1), ("W", 1), ("W", 2), ("D0", 2), ("D0", 3), ("W", 3))
PHASES = ("buckets time", "build leaf time", "Final prune time")
H70 = Path("experiments/H70/pipnn-clean-443a328")
STAGE_D0 = Path("experiments/H84/r84_4_workspace_stage_syntax")
STAGE_W = Path("experiments/H84/r84_4b_workspace_syntax_fix")
BINDIR = Path("experiments/H84/r84_5_matched_native_binary")
PARITY_DIR = Path("experiments/H84/r84_6_workspace_graph_parity_1t")
OUTREL = Path("experiments/H84/r84_7_workspace_pcore4_sift100k")


def need(ok: bool, marker: str):
    if not ok:
        raise RuntimeError(marker)


def sha(path: Path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def read_json(path: Path):
    need(path.is_file(), f"R84_7_REQUIRED_REPORT_MISSING {path}")
    return json.loads(path.read_text())


def affinity():
    need(hasattr(os, "sched_getaffinity"), "R84_7_NO_AFFINITY_API")
    got = tuple(sorted(os.sched_getaffinity(0)))
    need(got == CPU_SET,
         f"R84_7_AFFINITY_MISMATCH got={got} expected={CPU_SET}; use taskset -c 0,2,4,6")
    cores = []
    for cpu in got:
        base = Path(f"/sys/devices/system/cpu/cpu{cpu}/topology")
        socket_path = base / "physical_package_id"
        core_path = base / "core_id"
        need(socket_path.is_file() and core_path.is_file(), f"R84_7_TOPOLOGY_MISSING_CPU{cpu}")
        cores.append((int(socket_path.read_text()), int(core_path.read_text())))
    need(len(set(cores)) == 4 and len({k[0] for k in cores}) == 1,
         f"R84_7_SMT_OR_SOCKET_CONFLICT physical={cores}")
    print("R84_7_PCORE4_AFFINITY_GATE_PASS cpus=0,2,4,6 physical_cores=4", flush=True)
    return {str(c): {"package": k[0], "core": k[1]} for c, k in zip(got, cores)}


def dataset(path: Path):
    need(path.is_file(), f"R84_7_BASE_MISSING {path}")
    with path.open("rb") as f:
        header = f.read(8)
    need(len(header) == 8, "R84_7_BAD_FBIN_HEADER")
    n, d = struct.unpack("<II", header)
    need((n, d) == (N, DIM) and path.stat().st_size == 8+N*DIM*4,
         f"R84_7_BASE_SHAPE_MISMATCH rows={n} dim={d}")
    need(sha(path) == BASE_SHA, "R84_7_BASE_SHA_MISMATCH")
    return path


def inspect_graph(path: Path, expected_n=N, expected_degree=MAX_DEG):
    need(path.is_file(), f"R84_7_GRAPH_MISSING {path}")
    b = path.read_bytes()
    need(len(b) >= 8 + 4*expected_n, "R84_7_GRAPH_TOO_SHORT")
    n, degree_cap = struct.unpack_from("<II", b, 0)
    need((n, degree_cap) == (expected_n, expected_degree),
         f"R84_7_GRAPH_BAD_HEADER got={n},{degree_cap}")
    degrees = struct.unpack_from(f"<{n}I", b, 8)
    need(all(d <= degree_cap for d in degrees), "R84_7_GRAPH_DEGREE_OVERFLOW")
    arcs = sum(degrees)
    need(len(b) == 8+4*n+4*arcs, "R84_7_GRAPH_LENGTH_MISMATCH")
    edges = struct.unpack_from(f"<{arcs}I", b, 8+4*n)
    need(all(0 <= e < n for e in edges), "R84_7_GRAPH_EDGE_OUT_OF_RANGE")
    self_arcs = dup_arcs = cursor = 0
    for u, degree in enumerate(degrees):
        row = edges[cursor:cursor+degree]
        self_arcs += row.count(u)
        dup_arcs += degree-len(set(row))
        cursor += degree
    need(cursor == arcs, "R84_7_GRAPH_CURSOR_MISMATCH")
    return {"vertices":n, "maximum_degree":degree_cap, "arcs":arcs,
            "graph_bytes":len(b), "sha256":hashlib.sha256(b).hexdigest(),
            "self_arcs":self_arcs, "duplicate_neighbors":dup_arcs}


def phases(text):
    out = {}
    for name in PHASES:
        vals = [float(x) for x in re.findall(
            re.escape(name)+r"\s*:\s*([0-9]+(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?)",
            text, flags=re.I)]
        out[name] = {"count":len(vals), "values_s":vals, "sum_s":round(sum(vals), 6)}
    return out


def command(binary, base, graph):
    return [str(binary), "-base_path", str(base), "-graph_outfile", str(graph),
            "-num_clusters", "2", "-cluster_size", "1024", "-fanout", "30",
            "-fanout_scheme", "10,3,1", "-top_level_leaders", "100",
            "-mst_deg", "2", "-alpha", "1.2", "-prune", "1",
            "-prune_all", "1", "-prune_degree", "64", "-table_size", "160",
            "-hash_bits", "12", "-k", "0"]


def provenance(root):
    source = root/H70
    need(source.is_dir(), "R84_7_H70_SOURCE_NOT_FOUND")
    githead = subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"], text=True).strip()
    need(githead == PIN, "R84_7_H70_COMMIT_NOT_PINNED")
    for relative, value in SOURCE_SHA.items():
        path = source / relative
        need(path.is_file() and sha(path) == value,
             f"R84_7_H70_SOURCE_SHA_FAIL {relative}")

    r4 = read_json(root/STAGE_D0/"r84_4_summary.json")
    r4b = read_json(root/STAGE_W/"r84_4b_summary.json")
    r5 = read_json(root/BINDIR/"r84_5_summary.json")
    r6 = read_json(root/PARITY_DIR/"r84_6_summary.json")
    need(r4.get("source_commit") == PIN and
         r4.get("arms",{}).get("D0",{}).get("exit_code") == 0,
         "R84_7_R84_4_D0_GATE_FAIL")
    need(r4b.get("status") == "R84_4B_W_FULL_INSTANTIATION_SYNTAX_PASS" and
         r4b.get("exit_code") == 0, "R84_7_R84_4B_W_GATE_FAIL")
    need(r5.get("status") == "R84_5_PAIRED_NATIVE_BINARY_BUILD_PASS" and
         r5.get("source_commit") == PIN,
         "R84_7_R84_5_BINARY_GATE_FAIL")
    need(r6.get("status") == "R84_6_1T_EXACT_GRAPH_PARITY_PASS" and
         r6.get("source_commit") == PIN and r6.get("threads") == 1,
         "R84_7_R84_6_PARITY_GATE_FAIL")
    r6runs = r6.get("runs", {})
    need(all(r6runs.get(k,{}).get("sha256") == GRAPH_8K_SHA
             for k in ("D0_r1", "D0_r2", "W_r1", "W_r2")),
         "R84_7_R84_6_GRAPH_SHA_OR_RUN_COUNT_FAIL")
    need(r6.get("binary_sha256") == BINARY_SHA,
         "R84_7_R84_6_BINARY_SHA_MISMATCH")

    bins = {}
    for arm in BINARY_SHA:
        stage = root/(STAGE_D0 if arm == "D0" else STAGE_W)/arm
        util = stage/"algorithms/PipNN/pipnn_utils.h"
        need(util.is_file(), f"R84_7_{arm}_UTILS_MISSING")
        expected_header_sha = (SOURCE_SHA["algorithms/PipNN/pipnn_utils.h"] if arm == "D0"
                               else r4b.get("corrected_header_sha256"))
        need(sha(util) == expected_header_sha, f"R84_7_{arm}_UTILS_SHA_FAIL")
        for name in ("pipnn.h", "neighbors.h"):
            need(sha(stage/"algorithms/PipNN"/name) ==
                 sha(source/"algorithms/PipNN"/name),
                 f"R84_7_{arm}_{name}_STAGE_NOT_PINNED")
        for name in ("utils", "bench"):
            target = stage/"algorithms"/name
            need(target.is_symlink() and target.resolve() ==
                 (source/"algorithms"/name).resolve(),
                 f"R84_7_{arm}_{name}_SOURCE_LINK_FAIL")
        record = r5.get("variants",{}).get(arm,{})
        binary = root/BINDIR/arm/TARGET
        need(record.get("binary_sha256") == BINARY_SHA[arm] and
             record.get("source_header_sha256") == expected_header_sha and
             record.get("compile_exit") == 0 and record.get("link_exit") == 0,
             f"R84_7_{arm}_R84_5_RECORD_FAIL")
        need(binary.is_file() and os.access(binary, os.X_OK) and
             binary.read_bytes()[:4] == b"\x7fELF" and
             sha(binary) == BINARY_SHA[arm],
             f"R84_7_{arm}_ELF_BINARY_SHA_FAIL")
        need(Path(record.get("binary_path", "")).resolve() == binary.resolve(),
             f"R84_7_{arm}_REPORTED_BINARY_PATH_FAIL")
        cmdfile = binary.parent/"compile_command.txt"
        need(cmdfile.is_file(), f"R84_7_{arm}_COMPILER_COMMAND_MISSING")
        cc = shlex.split(cmdfile.read_text())
        for define in ("-DUSE_DATATYPE_FLOAT_T", "-DUSE_DISTANCE_EUCLIDEAN",
                       "-DR70_TWO_TIER=1", "-DR71_H17_TOP2=1",
                       f"-DR84_LEAF_WORKSPACE={0 if arm == 'D0' else 1}"):
            need(cc.count(define) == 1, f"R84_7_{arm}_COMPILER_FLAG_NOT_PINNED {define}")
        bins[arm] = binary
    print("R84_7_SOURCE_STAGE_BINARY_AND_1T_PARITY_GATES_PASS", flush=True)
    print("R84_7_MATCHED_BINARY_SHA256", json.dumps(BINARY_SHA, sort_keys=True), flush=True)
    return bins, {"r84_4":sha(root/STAGE_D0/"r84_4_summary.json"),
                  "r84_4b":sha(root/STAGE_W/"r84_4b_summary.json"),
                  "r84_5":sha(root/BINDIR/"r84_5_summary.json"),
                  "r84_6":sha(root/PARITY_DIR/"r84_6_summary.json")}


def machine():
    cpuinfo = Path("/proc/cpuinfo")
    model = None
    if cpuinfo.is_file():
        for line in cpuinfo.read_text(errors="replace").splitlines():
            if line.startswith("model name"):
                model = line.partition(":")[2].strip()
                break
    freq = {}
    for c in CPU_SET:
        p = Path(f"/sys/devices/system/cpu/cpu{c}/cpufreq/scaling_governor")
        freq[str(c)] = p.read_text().strip() if p.is_file() else None
    return {"cpu_model":model,"kernel":platform.release(),
            "machine":platform.machine(),"scaling_governor":freq}


def selftest():
    from tempfile import TemporaryDirectory
    with TemporaryDirectory() as td:
        p = Path(td)/"small.bin"
        good = struct.pack("<2I",3,2)+struct.pack("<3I",1,2,0)+struct.pack("<3I",1,0,2)
        p.write_bytes(good)
        need(inspect_graph(p, 3, 2)["arcs"] == 3, "R84_7_SELFTEST_GRAPH_PARSE_FAIL")
        p.write_bytes(good[:-4]+struct.pack("<I", 3))
        try: inspect_graph(p, 3, 2)
        except RuntimeError as e:
            need("EDGE_OUT_OF_RANGE" in str(e), "R84_7_SELFTEST_BAD_REJECTION")
        else: raise RuntimeError("R84_7_SELFTEST_BAD_GRAPH_ACCEPTED")
    parsed = phases("Parlay time: buckets time: 0.3\nParlay time: build leaf time: 2.2\nFinal prune time: 0.15")
    need(abs(parsed["buckets time"]["sum_s"]-0.3)<1e-8,
         "R84_7_SELFTEST_PHASE_PARSE_FAIL")
    args = command(Path("/tmp/bin"), Path("/tmp/base"), Path("/tmp/graph"))
    need(args[args.index("-cluster_size")+1] == "1024" and
         args[args.index("-table_size")+1] == "160", "R84_7_SELFTEST_FLAGS_FAIL")
    need(PLAN == (("D0",1),("W",1),("W",2),("D0",2),("D0",3),("W",3)),
         "R84_7_SELFTEST_SCHEDULE_FAIL")
    print("R84_7_RUNNER_SELFTEST_PASS", flush=True)


def run_one(root, out, base, binaries, env, arm, rep):
    key = f"r{rep}_{arm}"
    directory = out/key
    directory.mkdir(mode=0o755, exist_ok=False)
    graph = directory/"graph.bin"
    argv = command(binaries[arm], base, graph)
    (directory/"command.json").write_text(json.dumps({"argv":argv, "threads":4,
        "affinity":list(CPU_SET),"env_thread_vars":{k:env[k] for k in (
        "PARLAY_NUM_THREADS", "OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
        "BLIS_NUM_THREADS","VECLIB_MAXIMUM_THREADS")}}, indent=2)+"\n")
    print(f"R84_7_BUILD_START run={key} variant={arm} threads=4 cpus=0,2,4,6", flush=True)
    try:
        with (directory/"build.log").open("x") as f:
            proc = subprocess.run(["/usr/bin/time","-f",
                "R84_7_GNU_WALL_S=%e\nR84_7_PEAK_RSS_KiB=%M",
                "-o",str(directory/"resource.log"),*argv],cwd=root,env=env,
                stdout=f,stderr=subprocess.STDOUT,timeout=240,check=False)
        code = proc.returncode
    except subprocess.TimeoutExpired:
        code = 124
    (directory/"exit_code.txt").write_text(str(code)+"\n")
    need(code == 0, f"R84_7_{key}_BUILD_FAILED_{code} log={directory/'build.log'}")
    logtext = (directory/"build.log").read_text(errors="replace")
    need("R70_RESERVOIR_VARIANT=TIER_B64_C160" in logtext and
         "R71_SELECTION_VARIANT=H17_PACKED_TOP2" in logtext,
         f"R84_7_{key}_VARIANT_LOG_MARKER_MISSING")
    phaseinfo = phases(logtext)
    need(phaseinfo["buckets time"]["count"] >= 2 and
         phaseinfo["build leaf time"]["count"] >= 2 and
         phaseinfo["Final prune time"]["count"] >= 1,
         f"R84_7_{key}_PHASE_COUNT_UNEXPECTED {json.dumps(phaseinfo)}")
    resource = (directory/"resource.log").read_text(errors="replace")
    pairs = dict(re.findall(r"(R84_7_(?:GNU_WALL_S|PEAK_RSS_KiB))=([0-9.]+)", resource))
    need(len(pairs) == 2, f"R84_7_{key}_RESOURCE_METRICS_MISSING")
    gr = inspect_graph(graph)
    result = {"variant":arm,"rep":rep,"tag":key,"threads":THREADS,
              "wall_s":float(pairs["R84_7_GNU_WALL_S"]),
              "peakRSS_KiB":int(pairs["R84_7_PEAK_RSS_KiB"]),
              "binary_sha256":BINARY_SHA[arm],"graph":gr,"phases":phaseinfo,
              "exit_code":code,"graph_path":str(graph)}
    (directory/"result.json").write_text(json.dumps(result,indent=2)+"\n")
    print(f"R84_7_BUILD_RESULT run={key} variant={arm} wall_s={result['wall_s']:.4f} "
          f"peakRSS_KiB={result['peakRSS_KiB']} arcs={gr['arcs']} sha256={gr['sha256']} "
          f"bucket_s={phaseinfo['buckets time']['sum_s']:.4f} "
          f"leaf_s={phaseinfo['build leaf time']['sum_s']:.4f}",flush=True)
    return result


def summarize(runs):
    by = {arm:sorted((v for v in runs.values() if v["variant"]==arm),
                      key=lambda r:r["rep"]) for arm in BINARY_SHA}
    need(all(len(v)==3 for v in by.values()), "R84_7_INCOMPLETE_PAIR_COUNT")
    medians = {}
    for arm, rr in by.items():
        medians[arm] = {k:statistics.median([r[k] for r in rr])
                        for k in ("wall_s","peakRSS_KiB")}
        medians[arm].update({k:statistics.median([r["phases"][k]["sum_s"] for r in rr])
                             for k in PHASES})
    ratios = {k:medians["W"][k]/medians["D0"][k]
              for k in ("wall_s","peakRSS_KiB")}
    paired = []
    for rep in range(1,4):
        d,w=by["D0"][rep-1],by["W"][rep-1]
        paired.append({"rep":rep,"wall_W_minus_D0_s":round(w["wall_s"]-d["wall_s"],6),
                       "rss_W_minus_D0_KiB":w["peakRSS_KiB"]-d["peakRSS_KiB"],
                       "wall_W_over_D0":round(w["wall_s"]/d["wall_s"],6),
                       "rss_W_over_D0":round(w["peakRSS_KiB"]/d["peakRSS_KiB"],6),
                       "graph_sha_equal":w["graph"]["sha256"]==d["graph"]["sha256"]})
    wins={"wall":sum(x["wall_W_minus_D0_s"]<0 for x in paired),
          "rss":sum(x["rss_W_minus_D0_KiB"]<0 for x in paired)}
    # Predeclared exploratory screen, not statistical significance.
    gain=(ratios["wall_s"]<=0.97 and ratios["peakRSS_KiB"]<=0.98)
    if gain and wins["wall"]>=2 and wins["rss"]>=2:
        verdict="R84_7_TWO_METRIC_PILOT_SCREEN_GO_RECALL_PENDING"
    elif gain:
        verdict="R84_7_MEDIAN_TWO_METRIC_WIN_PAIR_DIRECTION_MIXED_HOLD"
    else:
        verdict="R84_7_TWO_METRIC_SCREEN_HOLD_OR_NO_GO"
    return {"medians":medians,"W_over_D0_medians":ratios,"paired":paired,
            "paired_wins":wins,"thresholds":{"wall_ratio_max":0.97,
            "rss_ratio_max":0.98,"min_win_count_per_metric":2},"verdict":verdict}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root",type=Path,default=Path.home()/"ann-task-a")
    group=p.add_mutually_exclusive_group(required=True)
    group.add_argument("--selftest",action="store_true")
    group.add_argument("--dry-run",action="store_true")
    group.add_argument("--run",action="store_true")
    opt=p.parse_args()
    selftest()
    if opt.selftest:
        return
    root=opt.root.expanduser().resolve()
    affinity_info=affinity()
    binaries, inputs=provenance(root)
    base=dataset(root/"data/sift100k.fbin")
    need(Path("/usr/bin/time").is_file(),"R84_7_GNU_TIME_NOT_AVAILABLE")
    out=root/OUTREL
    need(not out.exists(),f"R84_7_OUTPUT_EXISTS_FAIL_CLOSED {out}")
    print(f"R84_7_BASE_SHA256 {BASE_SHA} rows={N} dim={DIM}",flush=True)
    print("R84_7_PREFLIGHT_PASS_NO_BUILD",flush=True)
    if opt.dry_run:
        print(f"R84_7_DRY_RUN_PASS_NO_WRITES planned_dir={out}",flush=True)
        return
    out.mkdir(parents=True,exist_ok=False)
    env=os.environ.copy()
    env.update({"PARLAY_NUM_THREADS":"4","OMP_NUM_THREADS":"1",
                "OPENBLAS_NUM_THREADS":"1","MKL_NUM_THREADS":"1",
                "BLIS_NUM_THREADS":"1","VECLIB_MAXIMUM_THREADS":"1"})
    summary={"experiment":"R84.7","source_commit":PIN,"status":"STARTED",
             "base_path":str(base),"base_sha256":BASE_SHA,
             "binary_sha256":BINARY_SHA,"source_reports_sha256":inputs,
             "threads":4,"cpus":list(CPU_SET),"core_topology":affinity_info,
             "hardware":machine(),"ordered_runs":[f"r{rep}_{arm}" for arm,rep in PLAN],
             "created_at_utc":datetime.now(timezone.utc).isoformat(),
             "runs":{},"note":"New-PC 4 P-core BUILD only. 4t graph SHAs may differ across repeated runs; full Recall pending."}
    report=out/"r84_7_summary.json"
    report.write_text(json.dumps(summary,indent=2)+"\n")
    print("R84_7_MATCHED_PCORE4_SIFT100K_BUILD_START",flush=True)
    try:
        for arm,rep in PLAN:
            record=run_one(root,out,base,binaries,env,arm,rep)
            summary["runs"][record["tag"]]=record
            report.write_text(json.dumps(summary,indent=2)+"\n")
        assessment=summarize(summary["runs"])
        summary.update(assessment)
        summary["status"]=assessment["verdict"]
        report.write_text(json.dumps(summary,indent=2)+"\n")
        print("R84_7_MEDIANS "+json.dumps(assessment["medians"],sort_keys=True),flush=True)
        print("R84_7_RATIOS "+json.dumps(assessment["W_over_D0_medians"],sort_keys=True),flush=True)
        print("R84_7_PAIRED "+json.dumps(assessment["paired"],sort_keys=True),flush=True)
        print(assessment["verdict"],flush=True)
        print("R84_7_GRAPH_STRUCTURAL_VALIDATION_PASS_6_OF_6",flush=True)
        print("R84_7_NOT_CURRENT_GRAPH_RECALL_NOT_SIFT1M_NOT_STATISTICAL_PROOF_NO_PUSH",flush=True)
        print("R84_7_REPORT",report,flush=True)
    except Exception as e:
        summary["status"]="R84_7_STOP_INCOMPLETE"
        summary["error"]=str(e)
        report.write_text(json.dumps(summary,indent=2)+"\n")
        raise


if __name__=="__main__":
    try:
        main()
    except Exception as e:
        print("R84_7_STOP",str(e),file=sys.stderr,flush=True)
        sys.exit(2)
