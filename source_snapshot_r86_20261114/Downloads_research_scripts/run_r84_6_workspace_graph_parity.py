#!/usr/bin/env python3
"""R84.6: one-P-core exact graph parity gate for matched R84.5 D0/W native ELF.

Creates four small, real 8192-vector PiPNN graph builds: D0, W, W, D0.
All source, binary, and dataset provenance is fail-closed. It validates each
binary graph and checks both same-arm repeatability and cross-arm ordered
adjacency byte identity. A byte mismatch is diagnosed, never disguised as pass.
No SIFT100K full benchmark, no query/Recall, no Git, no H70/H80 edits.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shlex
import struct
import subprocess
import sys
import tempfile
import time
from pathlib import Path

PIN = "443a328dc71a3b7be753d52ca2b3c9a4ba77f3fd"
TARGET = "neighbors-pipnn_FLOAT_T_EUCLIDEAN"
BASE_SHA = "e50ff1bc34bcc6d1c97dd001023c09a666971cde64605cc06671ed8a8ff1ed12"
PREFIX_SHA = "b11f72a0bb36ce195ec06bc28e02a722098b8bd13ecb35ca8af2ff65fe85fbed"
PINS = {
    "algorithms/PipNN/pipnn.h": "f4391ad8712d7757423dca872f9042c3271660dffde384a85b93854b9692f288",
    "algorithms/PipNN/pipnn_utils.h": "7083e8183554a1cb586b70cdb4c57920f49ec5a50680096aecf6b873f596595d",
    "algorithms/utils/graph.h": "17e51779f32db56c9c50b6d514a8ff68539fd19b734804df3abdb63f88dd443e",
    "algorithms/utils/r70_two_tier_lshgraph.h": "ac0bece4804c7bc552b30db0df57ee92492033065cef62330ddb58a19d470af1",
}
BINARY_PINS = {
    "D0": "7340ce1817f1272d0137bb02ef8dea79756a5fa9252037d29afc3af670f6e48f",
    "W": "b79cada58551a8893c1c6fb81fd868ecd521830825ae1eb21ed887e46ec8ef95",
}
R84_BASE = Path("experiments/H70/pipnn-clean-443a328")
R84_STAGE_D0 = Path("experiments/H84/r84_4_workspace_stage_syntax")
R84_STAGE_W = Path("experiments/H84/r84_4b_workspace_syntax_fix")
R84_BIN = Path("experiments/H84/r84_5_matched_native_binary")
DEST = Path("experiments/H84/r84_6_workspace_graph_parity_1t")
ROWS, DIM, MAX_DEG = 8192, 128, 64


def need(ok: bool, msg: str) -> None:
    if not ok:
        raise RuntimeError(msg)


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fp:
        for chunk in iter(lambda: fp.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def read_json(path: Path) -> dict:
    need(path.is_file(), f"R84_6_MISSING_REPORT {path}")
    return json.loads(path.read_text())


def dataset_header(path: Path) -> tuple[int, int]:
    need(path.is_file(), f"R84_6_DATASET_MISSING {path}")
    with path.open("rb") as fp:
        b = fp.read(8)
    need(len(b) == 8, "R84_6_INVALID_FBIN_HEADER")
    n, d = struct.unpack("<II", b)
    need(n >= ROWS and d == DIM, f"R84_6_INVALID_FBIN_SHAPE {n}x{d}")
    need(path.stat().st_size == 8 + n*d*4, "R84_6_INVALID_FBIN_LENGTH")
    return n, d


def checked_affinity() -> list[int]:
    need(hasattr(os, "sched_getaffinity"), "R84_6_AFFINITY_NOT_AVAILABLE")
    cpus = sorted(os.sched_getaffinity(0))
    need(cpus == [0], f"R84_6_MUST_PIN_LOGICAL_CPU_0 got={cpus}")
    print("R84_6_ONE_PCORE_AFFINITY_GATE_PASS cpus=0 threads=1", flush=True)
    return cpus


def provenance(root: Path) -> tuple[dict[str, Path], Path]:
    source = root / R84_BASE
    need(source.is_dir(), "R84_6_H70_SOURCE_MISSING")
    head = subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"], text=True).strip()
    need(head == PIN, "R84_6_PINNED_COMMIT_FAIL")
    for rel, val in PINS.items():
        need(sha(source / rel) == val, f"R84_6_PINNED_SOURCE_SHA_FAIL {rel}")

    d0stage = root / R84_STAGE_D0 / "D0"
    wstage = root / R84_STAGE_W / "W"
    d0head = d0stage / "algorithms/PipNN/pipnn_utils.h"
    whead = wstage / "algorithms/PipNN/pipnn_utils.h"
    need(d0head.is_file() and whead.is_file(), "R84_6_MISSING_STAGE_HEADERS")
    need(sha(d0head) == PINS["algorithms/PipNN/pipnn_utils.h"], "R84_6_D0_STAGE_SHA_FAIL")
    r4 = read_json(root / R84_STAGE_D0 / "r84_4_summary.json")
    r4b = read_json(root / R84_STAGE_W / "r84_4b_summary.json")
    r5 = read_json(root / R84_BIN / "r84_5_summary.json")
    need(r4.get("source_commit") == PIN, "R84_6_R84_4_PIN_FAIL")
    need(r4.get("arms", {}).get("D0", {}).get("exit_code") == 0, "R84_6_D0_SYNTAX_GATE_FAIL")
    need(r4b.get("status") == "R84_4B_W_FULL_INSTANTIATION_SYNTAX_PASS" and
         r4b.get("exit_code") == 0, "R84_6_W_SYNTAX_GATE_FAIL")
    need(sha(whead) == r4b.get("corrected_header_sha256"), "R84_6_W_STAGE_SHA_FAIL")
    need(r5.get("status") == "R84_5_PAIRED_NATIVE_BINARY_BUILD_PASS" and
         r5.get("source_commit") == PIN, "R84_6_R84_5_PAIRED_BINARY_GATE_FAIL")
    expected_header = {"D0": sha(d0head), "W": sha(whead)}
    binaries = {}
    for arm in ("D0", "W"):
        for rel in ("pipnn.h", "neighbors.h"):
            need(sha((d0stage if arm == "D0" else wstage) / "algorithms/PipNN" / rel)
                 == sha(source / "algorithms/PipNN" / rel),
                 f"R84_6_{arm}_STAGED_HEADER_NOT_PINNED {rel}")
        for linked in ("utils", "bench"):
            pointer = (d0stage if arm == "D0" else wstage) / "algorithms" / linked
            need(pointer.is_symlink() and
                 pointer.resolve() == (source / "algorithms" / linked).resolve(),
                 f"R84_6_{arm}_{linked}_SYMLINK_BAD")
        g = r5.get("variants", {}).get(arm, {})
        need(g.get("compile_exit") == 0 and g.get("link_exit") == 0,
             f"R84_6_{arm}_COMPILE_LINK_GATE_FAIL")
        need(g.get("binary_sha256") == BINARY_PINS[arm] and
             g.get("source_header_sha256") == expected_header[arm],
             f"R84_6_{arm}_REPORT_HASH_GATE_FAIL")
        binary = root / R84_BIN / arm / TARGET
        need(binary.is_file() and binary.read_bytes()[:4] == b"\x7fELF" and
             sha(binary) == BINARY_PINS[arm], f"R84_6_{arm}_ELF_SHA_FAIL")
        need(Path(g.get("binary_path", "")).resolve() == binary.resolve(),
             f"R84_6_{arm}_REPORTED_BINARY_PATH_FAIL")
        compile_text = (binary.parent / "compile_command.txt").read_text()
        argv = shlex.split(compile_text)
        for define in ("-DUSE_DATATYPE_FLOAT_T", "-DUSE_DISTANCE_EUCLIDEAN",
                       "-DR70_TWO_TIER=1", "-DR71_H17_TOP2=1",
                       f"-DR84_LEAF_WORKSPACE={0 if arm == 'D0' else 1}"):
            need(argv.count(define) == 1, f"R84_6_{arm}_COMPILER_FLAG_FAIL {define}")
        link_text = (binary.parent / "link_command.txt").read_text()
        link_argv = shlex.split(link_text)
        need(str(binary) in link_argv and str(binary.parent / "neighborsTime.C.o") in link_argv,
             f"R84_6_{arm}_LINK_SPEC_FAIL")
        binaries[arm] = binary
    need(not (root / DEST).exists(), "R84_6_OUTPUT_EXISTS_FAIL_CLOSED")
    base = root / "data/sift100k.fbin"
    n, d = dataset_header(base)
    need(sha(base) == BASE_SHA, "R84_6_SIFT100K_PINNED_SHA_FAIL")
    print(f"R84_6_SOURCE_STAGE_AND_MATCHED_BINARY_GATES_PASS n_base={n} dim={d}", flush=True)
    print("R84_6_BINARY_SHA256", json.dumps(BINARY_PINS, sort_keys=True), flush=True)
    return binaries, base


def make_prefix(base: Path, dest: Path):
    need(not dest.exists(), "R84_6_PREFIX_EXISTS")
    with base.open("rb") as fp:
        fp.seek(8)
        payload = fp.read(ROWS*DIM*4)
    need(len(payload) == ROWS*DIM*4, "R84_6_PREFIX_NOT_ENOUGH_ROWS")
    with dest.open("xb") as fp:
        fp.write(struct.pack("<II", ROWS, DIM))
        fp.write(payload)
    need(sha(dest) == PREFIX_SHA, "R84_6_PREFIX_HASH_MISMATCH_VS_R83_6")
    print(f"R84_6_PINNED_DATASET_PREFIX_PASS rows={ROWS} dim={DIM} sha256={PREFIX_SHA}", flush=True)


def parse_graph(graph: Path, n_expected=ROWS, max_degree=MAX_DEG):
    need(graph.is_file(), f"R84_6_GRAPH_MISSING {graph}")
    raw = graph.read_bytes()
    need(len(raw) >= 8, "R84_6_GRAPH_SHORT_HEADER")
    n, cap = struct.unpack_from("<II", raw, 0)
    need((n, cap) == (n_expected, max_degree), f"R84_6_GRAPH_BAD_HEADER n={n} cap={cap}")
    need(len(raw) >= 8+4*n, "R84_6_GRAPH_TRUNCATED_DEGREES")
    degrees = struct.unpack_from(f"<{n}I", raw, 8)
    need(all(k <= cap for k in degrees), "R84_6_GRAPH_DEGREE_OVER_CAP")
    arcs = sum(degrees)
    need(len(raw) == 8 + 4*n + 4*arcs,
         f"R84_6_GRAPH_LENGTH_MISMATCH length={len(raw)} arcs={arcs}")
    entries = struct.unpack_from(f"<{arcs}I", raw, 8+4*n)
    need(all(u < n for u in entries), "R84_6_GRAPH_VERTEX_ID_OUT_OF_RANGE")
    offsets = []
    t = 0
    repeat = selfedges = 0
    for u,k in enumerate(degrees):
        row = entries[t:t+k]
        repeat += k-len(set(row))
        selfedges += row.count(u)
        offsets.append((t,t+k))
        t += k
    need(t == arcs, "R84_6_GRAPH_ARC_CURSOR_FAIL")
    meta = {"n":n, "max_degree":cap, "arcs":arcs, "bytes":len(raw),
            "sha256":hashlib.sha256(raw).hexdigest(),
            "duplicate_neighbor_entries":repeat, "self_edges":selfedges}
    return meta, (degrees,entries,offsets)


def diff_graph(a,b):
    deg_a,nb_a,pos_a = a
    deg_b,nb_b,pos_b = b
    degree_rows = ordered_rows = unordered_rows = 0
    examples=[]
    for u in range(len(deg_a)):
        arow = nb_a[pos_a[u][0]:pos_a[u][1]]
        brow = nb_b[pos_b[u][0]:pos_b[u][1]]
        if deg_a[u] != deg_b[u]: degree_rows += 1
        if arow != brow:
            ordered_rows += 1
            if sorted(arow) != sorted(brow): unordered_rows += 1
            if len(examples)<5:
                examples.append({"u":u, "a_degree":len(arow), "b_degree":len(brow),
                                 "a_head":list(arow[:10]), "b_head":list(brow[:10])})
    return {"different_degree_rows":degree_rows,
            "different_ordered_adjacency_rows":ordered_rows,
            "different_unordered_adjacency_rows":unordered_rows,
            "examples":examples}


def build_flags(dataset:Path,graph:Path):
    return ["-base_path",str(dataset),"-graph_outfile",str(graph),
            "-num_clusters","2","-cluster_size","1024", "-fanout","30",
            "-fanout_scheme","10,3,1", "-top_level_leaders","100",
            "-mst_deg","2", "-alpha","1.2", "-prune","1",
            "-prune_all","1", "-prune_degree",str(MAX_DEG),
            "-table_size","160", "-hash_bits","12", "-k","0"]


def selftest():
    with tempfile.TemporaryDirectory(prefix="r84_6_tiny_graph_") as td:
        path=Path(td)/"small.bin"
        # n3, maxDegree2, degrees [1,2,0], edge IDs [1,0,2]
        valid=(struct.pack("<II",3,2)+struct.pack("<3I",1,2,0)+
               struct.pack("<3I",1,0,2))
        path.write_bytes(valid)
        meta, obj=parse_graph(path,3,2)
        need(meta["arcs"]==3, "R84_6_SELFTEST_ARCS_FAIL")
        need(diff_graph(obj,obj)["different_ordered_adjacency_rows"]==0,
             "R84_6_SELFTEST_IDENTICAL_GRAPH_FAIL")
        path.write_bytes(valid[:-4]+struct.pack("<I",3))
        try: parse_graph(path,3,2)
        except RuntimeError as e:
            need("VERTEX_ID_OUT_OF_RANGE" in str(e),"R84_6_SELFTEST_REJECTION_WRONG")
        else: raise RuntimeError("R84_6_SELFTEST_BAD_GRAPH_ACCEPTED")
        flags=build_flags(Path("/tmp/base.fbin"),Path("/tmp/graph.bin"))
        need(flags[flags.index("-cluster_size")+1]=="1024" and
             flags[flags.index("-table_size")+1]=="160",
             "R84_6_SELFTEST_BUILD_FLAGS_BAD")
    print("R84_6_RUNNER_SELFTEST_PASS",flush=True)


def run_builds(root:Path,output:Path,sample:Path,binaries:dict):
    need(Path("/usr/bin/time").is_file(),"R84_6_GNU_TIME_MISSING")
    env=os.environ.copy()
    for k in ("PARLAY_NUM_THREADS","OMP_NUM_THREADS","OPENBLAS_NUM_THREADS",
              "MKL_NUM_THREADS","BLIS_NUM_THREADS","VECLIB_MAXIMUM_THREADS"):
        env[k]="1"
    results={}
    graph_info={}
    indexes={"D0":0,"W":0}
    for arm in ("D0","W","W","D0"):
        indexes[arm]+=1
        key=f"{arm}_r{indexes[arm]}"
        dst=output/key
        dst.mkdir(mode=0o755,exist_ok=False)
        graph=dst/"graph.bin"
        cmd=[str(binaries[arm]),*build_flags(sample,graph)]
        (dst/"command.json").write_text(json.dumps({"argv":cmd,"env_thread_vars":
             {k:env[k] for k in env if k in ("PARLAY_NUM_THREADS","OMP_NUM_THREADS",
             "OPENBLAS_NUM_THREADS","MKL_NUM_THREADS","BLIS_NUM_THREADS","VECLIB_MAXIMUM_THREADS")},
             "affinity":[0]},indent=2)+"\n")
        print(f"R84_6_BUILD_START arm={arm} run={key} threads=1 cpu=0",flush=True)
        now=time.perf_counter()
        with (dst/"build.log").open("x") as fp:
            proc=subprocess.run(["/usr/bin/time","-f",
               "R84_6_WALL_SECONDS=%e\nR84_6_PEAK_RSS_KiB=%M",
               "-o",str(dst/"resource.log"),*cmd],
               cwd=root,env=env,stdout=fp,stderr=subprocess.STDOUT,
               timeout=240,check=False)
        info={"arm":arm,"run":key,"exit_code":proc.returncode,
              "binary_sha256":BINARY_PINS[arm],
              "python_elapsed_s":round(time.perf_counter()-now,5)}
        (dst/"result.json").write_text(json.dumps(info,indent=2)+"\n")
        need(proc.returncode==0,
             f"R84_6_{key}_EXECUTION_FAILED_EXIT_{proc.returncode} log={dst/'build.log'}")
        logtext=(dst/"build.log").read_text(errors="replace")
        need("R70_RESERVOIR_VARIANT=TIER_B64_C160" in logtext and
             "R71_SELECTION_VARIANT=H17_PACKED_TOP2" in logtext,
             f"R84_6_{key}_SOURCE_MARKERS_MISSING log={dst/'build.log'}")
        meta,graphdata=parse_graph(graph)
        measured=(dst/"resource.log").read_text()
        fields=dict(re.findall(r"(R84_6_(?:WALL_SECONDS|PEAK_RSS_KiB))=([0-9.]+)",measured))
        need(len(fields)==2, f"R84_6_{key}_RESOURCE_METRICS_MISSING")
        info.update(meta)
        info["wall_s"]=float(fields["R84_6_WALL_SECONDS"])
        info["peakRSS_KiB"]=int(float(fields["R84_6_PEAK_RSS_KiB"]))
        (dst/"result.json").write_text(json.dumps(info,indent=2)+"\n")
        results[key]=info
        graph_info[key]=graphdata
        print(f"R84_6_BUILD_RESULT arm={arm} run={key} wall_s={info['wall_s']:.4f} "
              f"peakRSS_KiB={info['peakRSS_KiB']} arcs={info['arcs']} "
              f"graph_sha256={info['sha256']}",flush=True)
    return results,graph_info


def comparisons(results,graphs):
    checks={"D0_REPEAT":("D0_r1","D0_r2"),
            "W_REPEAT":("W_r1","W_r2"),
            "D0_W_R1":("D0_r1","W_r1"),
            "D0_W_R2":("D0_r2","W_r2")}
    out={}
    for label,(a,b) in checks.items():
        item=diff_graph(graphs[a],graphs[b])
        item["byte_identical"]=results[a]["sha256"]==results[b]["sha256"]
        out[label]=item
        print("R84_6_GRAPH_COMPARE",label,json.dumps(item,sort_keys=True),flush=True)
    same=out["D0_REPEAT"]["byte_identical"] and out["W_REPEAT"]["byte_identical"]
    cross=out["D0_W_R1"]["byte_identical"] and out["D0_W_R2"]["byte_identical"]
    if same and cross:
        return out,"R84_6_1T_EXACT_GRAPH_PARITY_PASS"
    if not same:
        return out,"R84_6_1T_SAME_ARM_NONDETERMINISM_STRICT_PARITY_BLOCKED"
    return out,"R84_6_1T_CROSS_ARM_GRAPH_DRIFT_INVESTIGATE"


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root",type=Path,default=Path.home()/"ann-task-a")
    mode=parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--selftest",action="store_true")
    mode.add_argument("--dry-run",action="store_true")
    mode.add_argument("--run",action="store_true")
    args=parser.parse_args()
    selftest()
    if args.selftest: return
    checked_affinity()
    root=args.root.expanduser().resolve()
    binaries,source=provenance(root)
    print(f"R84_6_PREFLIGHT_PASS mode={'dry-run' if args.dry_run else 'run'}",flush=True)
    if args.dry_run:
        print(f"R84_6_DRY_RUN_PASS_NO_WRITES planned_dir={root/DEST}",flush=True)
        return
    out=root/DEST
    out.mkdir(mode=0o755,parents=True,exist_ok=False)
    sample=out/"sift8k_prefix.fbin"
    report=out/"r84_6_summary.json"
    summary={"experiment":"R84.6","status":"R84_6_STARTED",
             "source_commit":PIN,"sample_path":str(sample),
             "source_base_sha256":BASE_SHA,"expected_prefix_sha256":PREFIX_SHA,
             "threads":1,"affinity_cpus":[0],
             "binary_sha256":BINARY_PINS,"runs":{}}
    report.write_text(json.dumps(summary,indent=2)+"\n")
    try:
        make_prefix(source,sample)
        runs,graphdatas=run_builds(root,out,sample,binaries)
        summary["runs"]=runs
        v,status=comparisons(runs,graphdatas)
        summary["comparisons"]=v
        summary["status"]=status
        report.write_text(json.dumps(summary,indent=2)+"\n")
        print(status,flush=True)
        print("R84_6_ONLY_SIFT8K_SINGLE_THREAD_NOT_4T_BENCHMARK_NOT_RECALL_NO_PUSH",flush=True)
        print("R84_6_REPORT",report,flush=True)
        need(status=="R84_6_1T_EXACT_GRAPH_PARITY_PASS",status)
    except Exception as e:
        if summary["status"]=="R84_6_STARTED":
            summary["status"]="R84_6_STOP_INCOMPLETE_REVIEW_LOGS"
            summary["error"]=str(e)
            summary["completed_runs"]=sorted(p.name for p in out.iterdir() if p.is_dir())
            report.write_text(json.dumps(summary,indent=2)+"\n")
        raise


if __name__=="__main__":
    try: main()
    except Exception as e:
        print("R84_6_STOP",str(e),file=sys.stderr,flush=True)
        sys.exit(2)
