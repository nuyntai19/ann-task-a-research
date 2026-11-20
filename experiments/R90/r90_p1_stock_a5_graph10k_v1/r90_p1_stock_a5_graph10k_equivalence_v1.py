#!/usr/bin/env python3
"""R90-P1 isolated native SIFT10K source-parity + A5 dryrun coverage gate.

Commands: selftest, preflight, pilot, audit. Never overwrites old outputs,
never edits original stock/A5 source or original data. No ANN Search/QPS.
"""
from __future__ import annotations
import argparse
from array import array
import hashlib
import json
import mmap
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import time

PROTO = "R90_P1_STOCK_A5_SIFT10K_SOURCE_PARITY_V1"
R90_UPSTREAM = "443a328dc71a3b7be753d52ca2b3c9a4ba77f3fd"
R90_RESEARCH = "938698037f2c3d419a9ea6e370a99ff4fd4c4beb"
R90_P0_SCRIPT_SHA = "93d7e6f88084d3363ad4aba77d53c8be82119d50471b698680e79910e0fa06c7"
STOCK_ELF_SHA = "31b337316f69c5945dc78a14be16217e7f0bf901e7af5d752a3af17bdb337225"
A5_ELF_SHA = "aebdae764f3e79ff709546787c22e3df910dbb1934851ce7ddfaf4927ff10fa2"
EXPECTED_STOCK_CPP = "43d30d9959dbad6c4736e9d6d942cb8a5a7aeab3db389249865cd9f96c7d2ebd"
EXPECTED_A5_CPP = "315747c65f10ce3783b0622682b1237741ac307e21a8484e627e18fb00c24340"
BINARY = Path("algorithms/PipNN/neighbors-pipnn_FLOAT_T_EUCLIDEAN")
FRACTIONS = (0.01, 0.10, 0.25)
ARMS = (
    ("stock_N2", "stock", 2, "off", None),
    ("stock_N1", "stock", 1, "off", None),
    ("a5_off_N2", "a5", 2, "off", None),
    ("a5_all_N2", "a5", 2, "all", None),
    ("a5_none_N2", "a5", 2, "none", None),
    ("a5_dryrun_q001", "a5", 2, "dryrun", 0.01),
    ("a5_dryrun_q010", "a5", 2, "dryrun", 0.10),
    ("a5_dryrun_q025", "a5", 2, "dryrun", 0.25),
)

class Hold(RuntimeError):
    pass


def require(ok, label):
    if not ok:
        raise Hold("R90_P1_" + label + "_HOLD")


def sha(path):
    x = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            x.update(b)
    return x.hexdigest()


def regular(path):
    p = Path(path)
    require(p.is_file() and not p.is_symlink(), "MISSING_OR_LINK_" + p.name)
    return p


def base_paths():
    root = Path.home() / "ann-task-a"
    p0 = root / "experiments/R90/r90_p0_stock_a5_compile_gate_v1"
    output = root / "experiments/R90/r90_p1_stock_a5_graph10k_v1"
    source = root / "data/sift100k.fbin"
    script = Path.home() / "Downloads/r90_p0_stock_a5_compile_gate_v1.py"
    return root, p0, output, source, script


def fbin_info(path):
    path = regular(path)
    with path.open("rb") as f:
        b = f.read(8)
    require(len(b) == 8, "FBIN_HEADER")
    n, d = struct.unpack("<II", b)
    require(n >= 10000 and d == 128, "EXPECTED_SIFT_128D_10K")
    require(path.stat().st_size == 8 + n * d * 4, "FBIN_BYTES")
    return n, d


def one_cpu():
    try:
        cpus = os.sched_getaffinity(0)
        require(len(cpus) > 0, "NO_CPU_AFFINITY")
        return min(cpus)
    except AttributeError:
        raise Hold("R90_P1_CPU_AFFINITY_NOT_SUPPORTED_HOLD")


def preflight(verbose=True):
    _, p0, output, source, p0script = base_paths()
    regular(p0script)
    require(sha(p0script) == R90_P0_SCRIPT_SHA, "P0_SCRIPT_SHA")
    require(fbin_info(source)[1] == 128, "DATA_SHAPE")
    require(shutil.which("taskset") is not None and shutil.which("git") is not None, "SYSTEM_BINARIES")
    receipt = json.loads(regular(p0 / "RECEIPT.json").read_text())
    require(receipt["upstream_commit"] == R90_UPSTREAM, "UPSTREAM_COMMIT")
    require(receipt["research_commit"] == R90_RESEARCH, "RESEARCH_COMMIT")
    binary = {}
    for arm, want in (("stock", STOCK_ELF_SHA), ("a5", A5_ELF_SHA)):
        data = receipt["arms"][arm]
        actual_bin = p0 / f"{arm}_build" / BINARY
        require(Path(data["bin_path"]).resolve() == actual_bin.resolve(), arm + "_BINARY_PATH")
        require(sha(regular(actual_bin)) == want == data["elf_sha256"], arm + "_ELF_SHA")
        src = p0 / f"{arm}_source/algorithms/PipNN/pipnn.h"
        want_cpp = EXPECTED_STOCK_CPP if arm == "stock" else EXPECTED_A5_CPP
        require(sha(regular(src)) == want_cpp == data["pipnn_h_sha256"], arm + "_SOURCE_SHA")
        require(sha(regular(p0 / f"{arm}_source/algorithms/PipNN/pipnn_utils.h")) == data["pipnn_utils_h_sha256"], arm + "_UTILS_SHA")
        require(data["macro"] == ("OFF" if arm == "stock" else "ON"), arm + "_MACRO")
        binary[arm] = str(actual_bin)
    require(output != p0 and not output.is_relative_to(p0), "OUTPUT_INSIDE_BUILD_TREE")
    if verbose:
        print("R90_P1_SOURCE_2_ELF_SHA_P0_RECEIPT_DATA_10K_PREFLIGHT_PASS", json.dumps({
            "stock_elf_sha": STOCK_ELF_SHA, "a5_elf_sha": A5_ELF_SHA,
            "input": str(source), "n": fbin_info(source)[0], "cpu": one_cpu(), "output": str(output)
        }, sort_keys=True), flush=True)
    return {"p0": p0, "output": output, "source": source, "script": p0script,
            "cpu": one_cpu(), "binary": binary, "p0_receipt_sha": sha(p0 / "RECEIPT.json")}


def create_prefix(source, dst):
    n, d = fbin_info(source)
    need = 10000 * d * 4
    with source.open("rb") as src, dst.open("xb") as dest:
        hdr = src.read(8)
        require(struct.unpack("<II", hdr) == (n,d), "FBIN_MUTATED")
        dest.write(struct.pack("<II",10000,d))
        remaining = need
        while remaining:
            c = src.read(min(1 << 20, remaining))
            require(bool(c), "FBIN_TRUNCATED")
            dest.write(c)
            remaining -= len(c)
    require(dst.stat().st_size == 8 + need, "PREFIX_SIZE")
    require(fbin_info(dst) == (10000,128), "PREFIX_HEADER")
    return sha(dst)


def graph_audit(path):
    path = regular(path)
    canon = hashlib.sha256()
    fsize = path.stat().st_size
    with path.open("rb") as f:
        hdr = f.read(8)
        require(len(hdr) == 8, "GRAPH_HEADER")
        n, bound = struct.unpack("<II", hdr)
        require((n,bound) == (10000,64), "GRAPH_N_R")
        dbytes = f.read(n * 4)
        require(len(dbytes) == n*4, "GRAPH_DEGREES")
        degrees = struct.unpack("<" + "I"*n, dbytes)
        require(max(degrees) <= bound and sum(degrees) > 0, "GRAPH_DEGREE_BOUNDS")
        arcs = sum(degrees)
        require(fsize == 8 + n*4 + arcs*4, "GRAPH_BYTES")
        with mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mm:
            off = 8 + n*4
            canon.update(struct.pack("<II", n,bound))
            for u, deg in enumerate(degrees):
                row = struct.unpack_from("<" + "I"*deg, mm, off) if deg else ()
                require(all(0 <= x < n and x != u for x in row) and len(set(row)) == deg, f"GRAPH_INVALID_ROW_{u}")
                canon.update(struct.pack("<I", deg))
                for v in sorted(row): canon.update(struct.pack("<I", v))
                off += deg*4
            require(off == fsize, "GRAPH_END_OFFSET")
    return {"n": n, "bound":bound, "arcs":arcs, "bytes":fsize,
            "raw_sha256":sha(path), "canonical_sha256":canon.hexdigest()}


def command(arm, binary, prefix, graph):
    return ["taskset", "-c", str(one_cpu()), binary,
        "-base_path", str(prefix), "-graph_outfile", str(graph),
        "-num_clusters", str(arm[2]), "-cluster_size", "1024",
        "-top_level_leaders", "100", "-fanout_scheme", "10,3,1",
        "-mst_deg", "2", "-prune", "1", "-prune_all", "1",
        "-prune_degree", "64", "-table_size", "160", "-hash_bits", "12",
        "-alpha", "1.1", "-k", "0"]


def mode_env(arm):
    env = os.environ.copy()
    env.update({"PARLAY_NUM_THREADS":"1", "OMP_NUM_THREADS":"1", "OPENBLAS_NUM_THREADS":"1",
        "MKL_NUM_THREADS":"1", "VECLIB_MAXIMUM_THREADS":"1", "R90_A5_MODE":arm[3]})
    if arm[4] is not None:
        env["R90_A5_FRACTION"] = str(arm[4])
    else:
        env.pop("R90_A5_FRACTION",None)
    return env


def parse(log, arm):
    text = log.read_text(errors="replace")
    require("R90_A5_MODE=" in text if arm[1] == "a5" else True, arm[0] + "_MODE_LOG")
    if arm[1] == "a5":
        require(f"R90_A5_MODE={arm[3]}" in text, arm[0] + "_MODE_MISMATCH")
    c = re.findall(r"^# of comparisons during clustering:\s*(\d+)\s*$", text, re.M)
    require(len(c) == arm[2], arm[0] + "_PASS_COUNT")
    coverage = None
    if arm[3] in ("dryrun", "all", "none") and arm[1] == "a5":
        hits = re.findall(r"^R90_A5_LEAF_SCREEN total=(\d+) eligible=(\d+) WL_total=(\d+) WL_eligible=(\d+) gate=(\d+)\s*$", text, re.M)
        require(len(hits)==1, arm[0]+"_COVERAGE_MISSING")
        total,eligible,wl,wl_eligible,gate = map(int,hits[0])
        require(total>0 and wl>0 and 0<=eligible<=total and 0<=wl_eligible<=wl,arm[0]+"_COVERAGE_BOUNDS")
        require(gate==(0 if arm[3]=="dryrun" else 1),arm[0]+"_GATE_MODE")
        if arm[3]=="all":
            require((total,wl)==(eligible,wl_eligible),arm[0]+"_ALL_NOT_ELIGIBLE")
        if arm[3]=="none":
            require(eligible==0 and wl_eligible==0,arm[0]+"_NONE_ELIGIBLE")
        coverage = {"total_leaves":total, "eligible_leaves":eligible,
          "wl_total":wl,"wl_eligible":wl_eligible,
          "eligible_leaf_pct":round(100*eligible/total,6),
          "eligible_wl_pct":round(100*wl_eligible/wl,6),"gate":gate}
    return {"WP_cumulative":[int(x) for x in c],"coverage":coverage}


def pilot():
    a = preflight()
    output = a["output"]
    require(not output.exists() and not output.is_symlink(), "OUTPUT_EXISTS_NO_OVERWRITE")
    output.mkdir(parents=True,exist_ok=False)
    (output/"logs").mkdir()
    (output/"graphs").mkdir()
    prefix = output/"sift10k_prefix.fbin"
    prefix_sha = create_prefix(a["source"],prefix)
    audit = {"protocol":PROTO,"p0_receipt_sha256":a["p0_receipt_sha"],
        "input_source":str(a["source"]), "input_sha256":sha(a["source"]),
        "prefix_sha256":prefix_sha,"cpu":a["cpu"],
        "parameters":{"C":160,"K":1024,"N":[1,2],"R":64,"fanout":"10,3,1","mst_deg":2},
        "arms":{},"comparison":{},"notes":"10K one-core graph correctness only; not timing result, not Search or 1M"}
    for arm in ARMS:
        name, kind, n, mode, fraction=arm
        graph = output/"graphs"/(name+".graph")
        log = output/"logs"/(name+".log")
        require(not graph.exists() and not log.exists(),"ARM_OUTPUT_EXISTS_"+name)
        cmd = command(arm,a["binary"][kind],prefix,graph)
        env=mode_env(arm)
        print("R90_P1_NATIVE_GRAPH_START",json.dumps({"arm":name,"mode":mode,"N":n,"frac":fraction,"cpu":a["cpu"]},sort_keys=True),flush=True)
        t0=time.perf_counter()
        with log.open("x",encoding="utf-8") as f:
            f.write("CMD "+json.dumps(cmd)+"\n");f.flush()
            p=subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT,env=env,check=False)
        wall=time.perf_counter()-t0
        if p.returncode:
            print("R90_P1_FAILURE_TAIL",log.read_text(errors="replace").splitlines()[-20:],flush=True)
            raise Hold("R90_P1_NATIVE_GRAPH_"+name+"_EXIT_"+str(p.returncode)+"_HOLD")
        g=graph_audit(graph)
        metrics=parse(log,arm)
        audit["arms"][name]={"kind":kind,"mode":mode,"N":n,"fraction":fraction,
            "elf_sha256":STOCK_ELF_SHA if kind=="stock" else A5_ELF_SHA,
            "graph":str(graph),"log":str(log),"graph_audit":g,"metrics":metrics,
            "command":cmd,"log_sha256":sha(log),"wall_diagnostic_s":round(wall,6)}
        print("R90_P1_GRAPH_NATIVE_RECEIPT_PASS",json.dumps({"arm":name,"arcs":g["arcs"],"sha":g["raw_sha256"],"coverage":metrics["coverage"]},sort_keys=True),flush=True)
        (output/"partial_receipt.json").write_text(json.dumps(audit,indent=2,sort_keys=True)+"\n")
    stock_n2=audit["arms"]["stock_N2"]["graph_audit"]
    stock_n1=audit["arms"]["stock_N1"]["graph_audit"]
    for n in ["a5_off_N2","a5_all_N2","a5_dryrun_q001","a5_dryrun_q010","a5_dryrun_q025"]:
        g=audit["arms"][n]["graph_audit"]
        same_raw=(g["raw_sha256"]==stock_n2["raw_sha256"])
        same_canonical=(g["canonical_sha256"]==stock_n2["canonical_sha256"])
        audit["comparison"][n] = {"baseline":"stock_N2","same_raw":same_raw,"same_canonical":same_canonical}
        print("R90_P1_N2_GRAPH_EQ",n, "RAW",same_raw,"CANONICAL",same_canonical,flush=True)
        require(same_raw and same_canonical,"N2_PARITY_"+n)
    g=audit["arms"]["a5_none_N2"]["graph_audit"]
    same_raw=g["raw_sha256"]==stock_n1["raw_sha256"]
    same_canonical=g["canonical_sha256"]==stock_n1["canonical_sha256"]
    audit["comparison"]["a5_none_N2"]={"baseline":"stock_N1","same_raw":same_raw,"same_canonical":same_canonical}
    print("R90_P1_N1_GRAPH_EQ a5_none_N2 RAW",same_raw,"CANONICAL",same_canonical,flush=True)
    require(same_raw and same_canonical,"N1_PARITY_NONE")
    for n in ["a5_dryrun_q001","a5_dryrun_q010","a5_dryrun_q025"]:
        v=audit["arms"][n]["metrics"]["coverage"]
        print("R90_P1_DRYRUN_COVERAGE",n,json.dumps(v,sort_keys=True),flush=True)
    (output/"RECEIPT.json").write_text(json.dumps(audit,indent=2,sort_keys=True)+"\n")
    print("R90_P1_10K_STOCK_N2_OFF_DRYRUN_ALL_AND_N1_NONE_BYTE_GRAPH_PARITY_PASS",flush=True)
    print("R90_P1_NO_A5_GATE_GRAPH_NO_SEARCH_NO_QPS_GAIN",flush=True)


def audit():
    a=preflight(False)
    output=a["output"]
    data=json.loads(regular(output/"RECEIPT.json").read_text())
    require(data["protocol"]==PROTO and data["p0_receipt_sha256"]==a["p0_receipt_sha"],"RECEIPT_ORIGIN")
    require(sha(output/"sift10k_prefix.fbin")==data["prefix_sha256"],"PREFIX_SHA")
    require(sha(a["source"])==data["input_sha256"],"INPUT_SHA")
    for name,kind,n,mode,fraction in ARMS:
        z=data["arms"][name]
        require((z["kind"],z["mode"],z["N"],z["fraction"])==(kind,mode,n,fraction),"ARM_ID_"+name)
        require(z["elf_sha256"]==(STOCK_ELF_SHA if kind=="stock" else A5_ELF_SHA),"ELF_"+name)
        require(sha(regular(z["log"]))==z["log_sha256"],"LOG_SHA_"+name)
        require(graph_audit(z["graph"])==z["graph_audit"],"GRAPH_SHA_"+name)
        require(parse(regular(z["log"]),(name,kind,n,mode,fraction))==z["metrics"],"METRICS_"+name)
    for name,c in data["comparison"].items():
        g=data["arms"][name]["graph_audit"]
        b=data["arms"][c["baseline"]]["graph_audit"]
        require(g["raw_sha256"]==b["raw_sha256"] and g["canonical_sha256"]==b["canonical_sha256"],"PARITY_"+name)
    require(len(data["comparison"])==6,"COMPARE_COUNT")
    print("R90_P1_8_NATIVE_10K_GRAPHS_INPUT_ELF_LOG_PAIRED_PARITY_AND_COVERAGE_SHA_AUDIT_PASS",flush=True)


def selftest():
    with tempfile.TemporaryDirectory() as tmp:
        p=Path(tmp)/"sift.fbin"
        n,d=10002,128
        with p.open("wb") as f:
            f.write(struct.pack("<II",n,d))
            f.write(b"\0"*(n*d*4))
        require(fbin_info(p)==(n,d),"SELFTEST_DATA")
        out=Path(tmp)/"prefix.fbin"
        create_prefix(p,out)
        require(fbin_info(out)==(10000,128),"SELFTEST_PREFIX")
        g=Path(tmp)/"g.graph"
        with g.open("wb") as f:
            f.write(struct.pack("<II",10000,64))
            ds=[1,1]+[0]*9998
            f.write(struct.pack("<"+"I"*10000,*ds))
            f.write(struct.pack("<II",1,0))
        q=graph_audit(g)
        require(q["arcs"]==2,"SELFTEST_GRAPH")
        log=Path(tmp)/"a5.log"
        log.write_text("R90_A5_MODE=dryrun\n# of comparisons during clustering: 10\n# of comparisons during clustering: 20\nR90_A5_LEAF_SCREEN total=50 eligible=20 WL_total=10000 WL_eligible=3000 gate=0\n")
        data=parse(log,("a5_dryrun_q010","a5",2,"dryrun",0.1))
        require(data["coverage"]["eligible_wl_pct"]==30.0,"SELFTEST_COVERAGE")
    require(len(ARMS)==8,"SELFTEST_ARMS")
    print("R90_P1_SELFTEST_FBIN_GRAPH_CANONICAL_COVERAGE_AND_8ARM_CONTRACT_PASS",flush=True)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("mode",choices=["selftest","preflight","pilot","audit"])
    x=p.parse_args()
    try:
        {"selftest":selftest,"preflight":preflight,"pilot":pilot,"audit":audit}[x.mode]()
    except (Hold, OSError, KeyError, ValueError, subprocess.SubprocessError, json.JSONDecodeError) as exc:
        print("R90_P1_HOLD",str(exc),file=sys.stderr,flush=True)
        sys.exit(2)

if __name__=="__main__":
    main()
