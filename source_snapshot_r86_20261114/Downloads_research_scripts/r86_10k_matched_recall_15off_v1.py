#!/usr/bin/env python3
"""R86: read-only 10k-query matched-Recall search on 15 existing SIFT100K OFF graphs.

Only writes isolated evidence files under --out; never rebuilds or edits ANN sources.
Run directly with python3 (not a sourced shell script). All failed gates stop the run.
"""
import argparse
import csv
import hashlib
import json
import os
import re
import shutil
import statistics
import struct
import subprocess
import sys
from pathlib import Path

BEAMS_DEFAULT = "40,48,56,64,72,80,96,112,128,144,160,192,224,256"
TARGETS = (0.990, 0.998)
ARM_PREFIXES = (
    ("A0", "stock_C160_K1024_N2_off_r"),
    ("A1", "h17_C160_K1024_N2_off_r"),
    ("A2", "h17_C64_K1024_N2_off_r"),
    ("A3", "h17_C64_K512_N2_off_r"),
    ("A4", "h17_C64_K512_N1_off_r"),
)
GRAPH_HASHES = {
    "stock_C160_K1024_N2_off_r1": "f1727131d7427c4132ed48468c026f97f09e0b5fe7d94a56d26f4a46c0885978",
    "stock_C160_K1024_N2_off_r2": "02c1ff2104309a59e7bb51016966a2e847aa1913e39c99f8010b8acca787d909",
    "stock_C160_K1024_N2_off_r3": "57252481ace67e1fb9e6c55c223e3e01b707cb5898744519c4b136cd4e5d7877",
    "h17_C160_K1024_N2_off_r1": "18809c747d38ee1dfa26053bb6b3650dd0adf26f798ef47a0f6250e81530d841",
    "h17_C160_K1024_N2_off_r2": "5bae9f4eff8b05eb5f0ed521d2044ce80601cfd620741a01da13fcdfbbc67f92",
    "h17_C160_K1024_N2_off_r3": "a40f45b31954ac483133b807ce7e1591e5d76fd34fa6638ebc28ce29c53948f6",
    "h17_C64_K1024_N2_off_r1": "3ae4f18205c2841f0045e94d006dc6dda15357554f789610bafcb8b6e58cb4d1",
    "h17_C64_K1024_N2_off_r2": "2606931d8c07234a157b5d151381e9b46b067c6e91ed016847869d2d2b85ce2b",
    "h17_C64_K1024_N2_off_r3": "5f4853c48efeeacfe2dd447169975c2bef6a8b804d4bebddabc49062a7402d45",
    "h17_C64_K512_N2_off_r1": "2311777f6c807410bac87669c297a8ff247960d4f8583bb63c29eaea0458c1c4",
    "h17_C64_K512_N2_off_r2": "13c117fcecdb02b9b55f53280da3621ee68cc6f9dea5095e71e54bb247e0f731",
    "h17_C64_K512_N2_off_r3": "096ad8491d70c8357d8540b76b086ae16f89c59cde7048d00b5c2f1a50678691",
    "h17_C64_K512_N1_off_r1": "aa7234e667ddfb3f681fccaa78ec8eeb7304f76e0d25cfd45ee640c9ddbe4b5b",
    "h17_C64_K512_N1_off_r2": "5872d07e3b4d737f20227cc0496ba2608ed1ca4ea35d7640184c4bab6a86b0f9",
    "h17_C64_K512_N1_off_r3": "d4f312f54f1cb0e1a0bc28f3899b358986ee5d4053e67cc57b48486abf300202",
}
PINNED_INPUTS = {
    "base": ("data/sift100k.fbin", "e50ff1bc34bcc6d1c97dd001023c09a666971cde64605cc06671ed8a8ff1ed12", 100000, 128, 4),
    "queries": ("data/sift1m_queries.fbin", "9b0082b67d0ac55b4c7d42216560344567ad87ce3e75a9d5214a0762f1c15d65", 10000, 128, 4),
    "gt": ("experiments/H85/r85_b1_controlled/step8e_gt10k/sift100k_sift1mqueries10k_exact100.ibin", "70d25b3fff9d68ee3571931cc28e36f03d77c8bb4eea089ca206e5e709be8e28", 10000, 100, 8),
    "evaluator": ("experiments/H85/r85_b1_controlled/step8e_native_eval/r85_b1_100k_graph_recall", "3698f915ef3b7369aee527b6bb126512c0e31eb677a46480a5526cf4f909c64a", None, None, None),
}
ROW_RE = re.compile(r"^R72_RECALL_ROW beam=(\d+) recall=([0-9.eE+-]+) qps=([0-9.eE+-]+) avg_cmps=(\d+) avg_visited=(\d+)\s*$")
RAW_FIELDS = ["arm", "run_id", "graph_sha256", "build_rep", "search_rep", "beam", "recall_at10", "qps", "avg_cmps", "avg_visited", "qps_inverse_us_NOT_LATENCY", "evaluator_sha256", "query_count", "cpu_logic", "log_file"]
GRAPH_FIELDS = ["arm", "run_id", "graph_sha256", "build_rep", "target_recall", "beam_low", "beam_high", "recall_low", "recall_high", "beam_interpolated", "cmps_interpolated", "qps_interpolated_from_time", "throughput_equivalent_us_interpolated_NOT_P95", "status"]
ARM_FIELDS = ["arm", "target_recall", "graphs", "median_beam_interpolated", "median_cmps_interpolated", "median_qps_interpolated", "median_throughput_equivalent_us_NOT_P95", "status"]


def log(msg):
    print(msg, flush=True)


def fail(msg):
    raise RuntimeError(msg)


def sha256(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def check_shape(path, n, d, element_bytes):
    with path.open("rb") as f:
        header = f.read(8)
    if len(header) != 8 or struct.unpack("<II", header) != (n, d):
        fail("BAD_FILE_HEADER: " + str(path))
    expected_size = 8 + n * d * element_bytes
    if path.stat().st_size != expected_size:
        fail(f"BAD_FILE_SIZE: {path} got={path.stat().st_size} expected={expected_size}")


def parse_rows(text, beams):
    if "R72_RECALL_INPUT_PASS" not in text or "R72_RECALL_EVAL_PASS" not in text:
        fail("EVALUATOR_MISSING_PASS_MARKERS")
    got = {}
    for line in text.splitlines():
        match = ROW_RE.fullmatch(line.strip())
        if match:
            b, recall, qps, cmps, visited = match.groups()
            b = int(b)
            if b in got:
                fail(f"DUPLICATE_BEAM: {b}")
            record = dict(beam=b, recall_at10=float(recall), qps=float(qps), avg_cmps=int(cmps), avg_visited=int(visited))
            if not (0 <= record["recall_at10"] <= 1 and record["qps"] > 0):
                fail(f"INVALID_RECALL_QPS: {record}")
            got[b] = record
    if set(got) != set(beams):
        fail(f"EXPECTED_BEAMS_{beams}_GOT_{sorted(got)}")
    return [got[b] for b in beams]


def write_csv(path, records, fields):
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(records)
    os.replace(tmp, path)


def make_summary(all_runs, beams, reps):
    grouped = {}
    for item in all_runs:
        grouped.setdefault(item["run_id"], []).append(item)
    graph_rows = []
    arm_rows = []
    for arm, prefix in ARM_PREFIXES:
        for build_rep in range(1, 4):
            run_id = prefix + str(build_rep)
            samples = grouped.get(run_id, [])
            if len(samples) != reps:
                fail(f"MISSING_SEARCH_REPETITIONS_FOR_{run_id}: {len(samples)} instead of {reps}")
            by_beam = {}
            for beam in beams:
                arr = [next(x for x in item["rows"] if x["beam"] == beam) for item in samples]
                if any(x["recall_at10"] != arr[0]["recall_at10"] or x["avg_cmps"] != arr[0]["avg_cmps"] or x["avg_visited"] != arr[0]["avg_visited"] for x in arr):
                    fail(f"NONDETERMINISTIC_RECALL_OR_WORK_{run_id}_beam{beam}")
                qps = statistics.median(x["qps"] for x in arr)
                by_beam[beam] = dict(
                    recall=arr[0]["recall_at10"], cmps=arr[0]["avg_cmps"],
                    qps=qps, throughput_us=statistics.median(1e6 / x["qps"] for x in arr)
                )
            recalls = [by_beam[b]["recall"] for b in beams]
            if any(recalls[i] > recalls[i+1]+1e-7 for i in range(len(recalls)-1)):
                fail(f"NON_MONOTONIC_RECALL_{run_id}: {recalls}")
            for target in TARGETS:
                bracket = None
                for j in range(len(beams)-1):
                    a, b = beams[j], beams[j+1]
                    lo, hi = by_beam[a], by_beam[b]
                    if lo["recall"] <= target <= hi["recall"] and hi["recall"] > lo["recall"]:
                        bracket = (a,b,lo,hi)
                        break
                if bracket is None:
                    graph_rows.append(dict(arm=arm, run_id=run_id, graph_sha256=GRAPH_HASHES[run_id],build_rep=build_rep,target_recall=target,status="NOT_BRACKETED"))
                    continue
                a,b,lo,hi=bracket
                fraction=(target-lo["recall"])/(hi["recall"]-lo["recall"])
                cmps=lo["cmps"]+fraction*(hi["cmps"]-lo["cmps"])
                equiv_us=lo["throughput_us"]+fraction*(hi["throughput_us"]-lo["throughput_us"])
                graph_rows.append(dict(
                    arm=arm,run_id=run_id,graph_sha256=GRAPH_HASHES[run_id],build_rep=build_rep,
                    target_recall=target,beam_low=a,beam_high=b,recall_low=lo["recall"],
                    recall_high=hi["recall"],beam_interpolated=a+fraction*(b-a),
                    cmps_interpolated=cmps,throughput_equivalent_us_interpolated_NOT_P95=equiv_us,
                    qps_interpolated_from_time=1e6/equiv_us,status="INTERPOLATED_FROM_ACTUAL_BEAMS"
                ))
        for target in TARGETS:
            rows=[r for r in graph_rows if r["arm"]==arm and r["target_recall"]==target and r["status"].startswith("INTERPOLATED")]
            if len(rows)!=3:
                arm_rows.append(dict(arm=arm,target_recall=target,graphs=len(rows),status="HOLD_GRAPH_TARGET_NOT_BRACKETED"))
                continue
            arm_rows.append(dict(
                arm=arm,target_recall=target,graphs=3,
                median_beam_interpolated=statistics.median(r["beam_interpolated"] for r in rows),
                median_cmps_interpolated=statistics.median(r["cmps_interpolated"] for r in rows),
                median_qps_interpolated=statistics.median(r["qps_interpolated_from_time"] for r in rows),
                median_throughput_equivalent_us_NOT_P95=statistics.median(r["throughput_equivalent_us_interpolated_NOT_P95"] for r in rows),
                status="GRAPH_HIERARCHICAL_MEDIAN_MATCHED_RECALL"
            ))
    return graph_rows, arm_rows


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root",type=Path,default=Path.home()/"ann-task-a")
    ap.add_argument("--out",type=Path,help="Isolated output folder; default under 00_PROJECT_HOME")
    ap.add_argument("--cpu",type=int,default=0,help="Logical CPU ID; verify P-core mapping separately")
    ap.add_argument("--reps",type=int,default=5)
    ap.add_argument("--beams",default=BEAMS_DEFAULT)
    ap.add_argument("--preflight-only",action="store_true")
    ap.add_argument("--max-processes",type=int,default=0,help="Run at most N new search processes (0=all); resumable")
    args=ap.parse_args()
    root=args.root.resolve()
    out=args.out or root/"00_PROJECT_HOME/05_RESULTS_AND_COUNTERS/R86_10K_MATCHED_RECALL_15OFF_v1_0"
    out=out.resolve()
    if args.reps!=5:
        fail("REPS_MUST_BE_5_FOR_PREREGISTERED_CAMPAIGN")
    beams=[int(v) for v in args.beams.split(",")]
    if len(beams)!=len(set(beams)) or beams!=sorted(beams) or any(b<10 or b>512 for b in beams):
        fail("INVALID_BEAM_LIST")
    if beams != [int(x) for x in BEAMS_DEFAULT.split(",")]:
        fail("BEAM_LIST_CHANGED_FROM_PRE_REGISTERED_CAMPAIGN")
    if args.cpu not in os.sched_getaffinity(0):
        fail(f"CPU_NOT_ALLOWED_{args.cpu}: {sorted(os.sched_getaffinity(0))}")
    if not shutil.which("taskset"):
        fail("TASKSET_NOT_INSTALLED")
    paths={}
    log("===== PINNED INPUT PREFLIGHT =====")
    for key,(rel,digest,n,d,bytes_per_elem) in PINNED_INPUTS.items():
        path=root/rel
        if not path.is_file():
            fail(f"MISSING_{key}: {path}")
        actual=sha256(path)
        if actual!=digest:
            fail(f"SHA_FAIL_{key}: {actual} expected {digest}")
        if n is not None:
            check_shape(path,n,d,bytes_per_elem)
        paths[key]=path
        log(f"{key} SHA_PASS {actual}")
    bench=root/"experiments/R86/benchmarks/sift100k_a0a4_hw85_7ueCvd"
    graphs=[]
    log("===== VERIFY ALL 15 EXISTING OFF GRAPHS =====")
    for arm,prefix in ARM_PREFIXES:
        for rep in (1,2,3):
            run_id=prefix+str(rep)
            path=bench/run_id/(run_id+".graph")
            if not path.is_file():
                fail(f"GRAPH_MISSING: {path}")
            if sha256(path)!=GRAPH_HASHES[run_id]:
                fail(f"GRAPH_SHA_FAIL: {run_id}")
            with path.open("rb") as f:
                if struct.unpack("<II",f.read(8))!=(100000,64):
                    fail(f"GRAPH_HEADER_FAIL: {run_id}")
            graphs.append(dict(arm=arm,run_id=run_id,build_rep=rep,graph_sha256=GRAPH_HASHES[run_id],path=str(path)))
            log(f"{arm} {run_id} GRAPH_SHA_PASS")
    manifest={
        "campaign":"R86_10K_MATCHED_RECALL_15OFF_v1_0",
        "source":"R85-B1 ORIGINAL BINARY / verified 10k exact GT",
        "beams":beams,"targets":TARGETS,"reps":args.reps,"cpu_logical_id":args.cpu,
        "parlay_num_threads":1,"query_count":10000,
        "pin_sha":{name: PINNED_INPUTS[name][1] for name in PINNED_INPUTS},
        "graphs":graphs,"metric_notes":"avg_cmps native counter, not certified NDC; 1e6/QPS throughput-equivalent, not p95/p99/query latency; interpolation per graph first",
    }
    log("R86_10K_15OFF_PREFLIGHT_PASS")
    if args.preflight_only:
        return
    out.mkdir(parents=True,exist_ok=True)
    rawdir=out/"raw_logs"
    rawdir.mkdir(exist_ok=True)
    mfile=out/"manifest.json"
    if mfile.exists():
        if json.loads(mfile.read_text())!=manifest:
            fail("EXISTING_MANIFEST_DIFFERS_STOP_NO_OVERWRITE")
    else:
        mfile.write_text(json.dumps(manifest,indent=2,ensure_ascii=False)+"\n")
    env=os.environ.copy()
    env["PARLAY_NUM_THREADS"]="1"
    launched=0
    total=0
    for search_rep in range(1,args.reps+1):
        ordered=graphs[:]
        if search_rep%2==0:
            ordered.reverse()
        shift=((search_rep-1)//2)%len(ordered)
        ordered=ordered[shift:]+ordered[:shift]
        for g in ordered:
            total+=1
            stem=f"{g['run_id']}__s{search_rep}"
            logfile=rawdir/(stem+".log")
            receipt=rawdir/(stem+".json")
            if receipt.exists():
                r=json.loads(receipt.read_text())
                expected=dict(run_id=g["run_id"],search_rep=search_rep,graph_sha256=g["graph_sha256"],cpu=args.cpu)
                if any(r.get(k)!=v for k,v in expected.items()) or [x["beam"] for x in r.get("rows",[])]!=beams or not logfile.is_file():
                    fail("INVALID_EXISTING_RECEIPT_STOP: "+stem)
                log("SKIP_VERIFIED_RECEIPT "+stem)
                continue
            if logfile.exists():
                fail("UNPAIRED_LOG_STOP: "+str(logfile))
            cmd=["taskset","-c",str(args.cpu),str(paths["evaluator"]),g["path"],str(paths["base"]),str(paths["queries"]),str(paths["gt"]),args.beams]
            log(f"RUN {total}/{len(graphs)*args.reps} {g['arm']} {stem} cpu={args.cpu}")
            p=subprocess.run(cmd,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
            if p.returncode!=0:
                (rawdir/(stem+".FAILED.log")).write_text(p.stdout)
                fail(f"EVALUATOR_EXIT_{p.returncode}: {stem}; see .FAILED.log")
            rows=parse_rows(p.stdout,beams)
            tmp=logfile.with_suffix(".log.tmp")
            tmp.write_text(p.stdout)
            os.replace(tmp,logfile)
            payload=dict(arm=g["arm"],run_id=g["run_id"],graph_sha256=g["graph_sha256"],build_rep=g["build_rep"],search_rep=search_rep,cpu=args.cpu,rows=rows)
            tmp=receipt.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(payload,indent=2)+"\n")
            os.replace(tmp,receipt)
            launched+=1
            log(f"PASS {stem} rows={len(rows)}")
            if args.max_processes and launched>=args.max_processes:
                log(f"PARTIAL_SAFE_STOP_AFTER_{launched}_NEW_PROCESSES")
                return
    all_runs=[]
    raw=[]
    for g in graphs:
        for rep in range(1,args.reps+1):
            stem=f"{g['run_id']}__s{rep}"
            r=json.loads((rawdir/(stem+".json")).read_text())
            all_runs.append(r)
            for row in r["rows"]:
                raw.append(dict(arm=g["arm"],run_id=g["run_id"],graph_sha256=g["graph_sha256"],build_rep=g["build_rep"],search_rep=rep,
                    **row,qps_inverse_us_NOT_LATENCY=1e6/row["qps"],evaluator_sha256=PINNED_INPUTS["evaluator"][1],query_count=10000,cpu_logic=args.cpu,log_file="raw_logs/"+stem+".log"))
    write_csv(out/"raw_search_rows.csv",raw,RAW_FIELDS)
    graph_rows,arm_rows=make_summary(all_runs,beams,args.reps)
    write_csv(out/"matched_per_graph.csv",graph_rows,GRAPH_FIELDS)
    write_csv(out/"matched_arm_summary.csv",arm_rows,ARM_FIELDS)
    log(f"R86_10K_MATCHED_15OFF_COMPLETED raw_rows={len(raw)} per_graph={len(graph_rows)} arm_rows={len(arm_rows)}")
    for a in arm_rows:
        log(json.dumps(a,ensure_ascii=False))
    if any(a["status"].startswith("HOLD") for a in arm_rows):
        log("MATCHED_TARGET_BRACKET_HOLD_REVIEW_OUTPUT")
    else:
        log("MATCHED_TARGET_BRACKETS_ALL_PASS_INTERPOLATION_IS_NOT_DIRECT_MEASUREMENT")


if __name__=="__main__":
    try:
        main()
    except Exception as exc:
        log("R86_10K_CAMPAIGN_HOLD: "+str(exc))
        sys.exit(2)
