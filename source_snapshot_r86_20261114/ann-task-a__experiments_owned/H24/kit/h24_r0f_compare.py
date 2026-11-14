#!/usr/bin/env python3
"""H24-R0f read-only common-search comparison PiPNN vs GRAFT Dense LOW/HIGH.

The only possible ANN BUILDs are two exact provenance-matched re-BUILDs
of GRAFT Dense LOW/HIGH, required solely when their CSR graph exports are
missing. Outputs are always isolated under experiments/H24/r0f_common_search.
No STH or selective rescue is implemented here.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import struct
import subprocess
import sys
import time
from statistics import median

import numpy as np

PROJECT = Path.home() / "ann-task-a"
EXPECTED_REV = "a032c2d6cfb2c087d3b8abca028c745186501976"
EFS = [60, 100, 140, 200, 300, 400]
ARMS = ("pipnn", "low", "high")
GOALS = (.99, .995, .998)
RESULT_RE = re.compile(r"^RESULT\s+(.*)$",re.M)


def fbin_memmap(path):
    path=Path(path)
    with path.open("rb") as f:
        n,d=struct.unpack("<ii", f.read(8))
    if n<=0 or d<=0 or d>10000 or path.stat().st_size!=8+4*n*d:
        raise ValueError(f"invalid fbin: {path}")
    return np.memmap(path, mode="r", dtype="<f4", offset=8, shape=(n,d))


def fn_sha(path):
    h=hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda:f.read(4*1024*1024), b""):
            h.update(chunk)
    return h.hexdigest()


def check_identity(source_dir, base, query):
    """Guard against comparing graphs built with different vertex ID order."""
    manifest=json.loads((source_dir/"manifest.json").read_text())
    if manifest.get("n")!=1_000_000 or manifest.get("nq")!=1000 or manifest.get("metric")!="l2" or manifest.get("seed")!=42:
        raise RuntimeError("sample manifest does not match registered H24-R0e SIFT1M seed42 protocol")
    if Path(manifest["base_source"]).resolve()!=base.resolve() or Path(manifest["query_source"]).resolve()!=query.resolve():
        raise RuntimeError("source file paths do not match H24-R0e registered sources")
    X=np.load(source_dir/"X.npy",mmap_mode="r",allow_pickle=False)
    Q=np.load(source_dir/"Q.npy",mmap_mode="r",allow_pickle=False)
    G=np.load(source_dir/"gold.npy",mmap_mode="r",allow_pickle=False)
    source_ids=np.load(source_dir/"base_source_ids.npy",mmap_mode="r",allow_pickle=False)
    if X.shape!=(1_000_000,128) or Q.shape!=(1000,128) or G.shape!=(1000,10) or source_ids.shape!=(1_000_000,):
        raise RuntimeError(f"invalid H24 sample shapes X={X.shape}, Q={Q.shape}, G={G.shape}, ids={source_ids.shape}")
    if X.dtype!=np.float32 or Q.dtype!=np.float32 or G.dtype.kind not in "iu":
        raise RuntimeError("H24 data types differ from expected float32/int32")
    # The full-size sorted sample must be identity. Verify *every* entry (not one sample).
    for start in range(0,1_000_000,100_000):
        end=min(start+100_000,1_000_000)
        if not np.array_equal(source_ids[start:end],np.arange(start,end,dtype=np.int32)):
            raise RuntimeError("H24 Dense vector order differs from PiPNN original order. STOP; requires graph remapping")
    xb=fbin_memmap(base);qq=fbin_memmap(query)
    if xb.shape!=(1_000_000,128) or qq.shape[0]<1000 or qq.shape[1]!=128:
        raise RuntimeError("original SIFT base/query header mismatch")
    # Full comparison by disjoint small blocks, no 1 GiB temporary data duplication.
    for st in range(0,1_000_000,32768):
        if not np.array_equal(X[st:st+32768],xb[st:st+32768]):
            raise RuntimeError(f"H24 dense X.npy differs from PiPNN base at row {st}")
    if not np.array_equal(Q,qq[:1000]):
        raise RuntimeError("H24 Q.npy differs from first 1000 original SIFT queries")
    if int(G.min())<0 or int(G.max())>=1_000_000:
        raise RuntimeError("H24 gold ID out of range")
    for name in ("X.npy","Q.npy","gold.npy","base_source_ids.npy"):
        expected=manifest.get("files",{}).get(name)
        if expected and fn_sha(source_dir/name)!=expected:
            raise RuntimeError(f"SHA256 mismatch: {name}")
    return {"base_id_alignment":"full_identity_proved", "X_query_equality":"verified_all_values",
            "sample_manifest_sha256":fn_sha(source_dir/"manifest.json"),
            "gold_sha256":fn_sha(source_dir/"gold.npy")}


def graph_info(path, n=1_000_000):
    size=path.stat().st_size
    with path.open("rb") as f:
        ngraph,cap=struct.unpack("<II",f.read(8))
        if ngraph!=n:raise RuntimeError(f"graph vertex count mismatch: {path} {ngraph}!={n}")
        if size<8+4*n or (size-8-4*n)%4:raise RuntimeError(f"bad graph size: {path}")
        degrees=np.fromfile(f,dtype="<u4",count=n)
    ne=int(degrees.sum(dtype=np.uint64))
    if 8+4*n+ne*4!=size or cap!=int(degrees.max()):
        raise RuntimeError(f"bad CSR graph header or edge count: {path}")
    return {"path":str(path),"bytes":size,"directed_edges":ne,"mean_degree":ne/n,
            "max_degree":cap,"sha256":fn_sha(path)}


def cmd_graft(fg, sample, out_graph, m):
    return [str(fg),"--data",str(sample/"X.npy"),"--queries",str(sample/"Q.npy"),
        "--gold",str(sample/"gold.npy"),"--metric","l2",
        "--dense","1200","--dense-m",str(m),"--dense-C","200",
        "--dense-prune","1","--dense-spine","3","--dense-spine-s","0",
        "--dense-spine-cap","16","--dense-spine-repair","1","--dense-kmeans","10",
        "--harvest-cap","64","--harvest-alpha","1.0",
        "--threads","4","--search-threads","1","--seed","42",
        "--k","10","--entry","hub","--ef","60","--dump-graph",str(out_graph)]


def parse_results(log, name, starts):
    lines=log.read_text(errors="replace")
    rows=[]
    for m in RESULT_RE.finditer(lines):
        parsed={}
        for token in m.group(1).split():
            if "=" not in token:continue
            k,v=token.split("=",1)
            try:parsed[k]=float(v) if "." in v else int(v)
            except ValueError:parsed[k]=v
        rows.append(parsed)
    if len(rows)!=len(EFS)*2:raise RuntimeError(f"missing eval rows in {log}: {len(rows)} vs {len(EFS)*2}")
    byef={}
    for ef in EFS:
        rs=[x for x in rows if x["ef"]==ef]
        if len(rs)!=2:raise RuntimeError("bad repetition count")
        if any(x["tag"]!=name for x in rs):raise RuntimeError("bad tag")
        if any(x["recall10"]!=rs[0]["recall10"] or x["distances"]!=rs[0]["distances"] for x in rs):
            raise RuntimeError(f"non-deterministic result at ef {ef} in {log}")
        byef[str(ef)]={"recall10":rs[0]["recall10"],"dist_per_query":rs[0]["dist_per_query"],
                      "qps_median":round(median(x["qps"] for x in rs),2),
                      "qps_repetitions":[x["qps"] for x in rs]}
    return byef


def make_report(out, pipnn):
    runs={};graphstats={};matches={}
    for arm in ARMS:
        gp=pipnn if arm=="pipnn" else out/f"{arm}.graph"
        graphstats[arm]=graph_info(gp)
        for label in ("entry1","entry8"):
            log=out/f"search_{arm}_{label}.log"
            if not log.exists():raise RuntimeError(f"missing shared search log: {log}")
            runs[f"{arm}_{label}"]=parse_results(log,arm,label)
    for regime in ("entry1","entry8"):
        matches[regime]={}
        for t in GOALS:
            arm_summary={}
            for arm in ARMS:
                choices=[{"ef":int(ef),**d} for ef,d in runs[f"{arm}_{regime}"].items() if d["recall10"]>=t]
                if not choices:arm_summary[arm]=None;continue
                arm_summary[arm]=max(choices,key=lambda x:x["qps_median"])
            matches[regime][str(t)]=arm_summary
    previous={"pipnn_sift1m_H17_BUILD_s":49.76,"dense_low_H24_R0e_BUILD_s":91.39,"dense_high_H24_R0e_BUILD_s":151.53,
        "note":"BUILD timings historical; Dense was rebuilt in this gate for graph dump; compare quality with same search only. PiPNN H17 tuning/index cap differs."}
    rep={"status":"H24_R0f_SHARED_SEARCH_FINISHED_NOT_STH","n":1_000_000,"nq":1000,"k":10,
      "shared_search":"standalone fixed-entry single-thread classical best-first HNSW layer-0 beam; squared L2; 2 repeats/ef; query+GT identical",
      "same_original_vertex_ids":True,"graph":graphstats,"search":runs,"threshold_matched_grid":matches,
      "historic_build_seconds":previous,
      "limitations":["Dense graph CSR export required 2 rebuilds; logged times in new export logs, not historical H24-build repeat equivalent",
          "PiPNN graph selected from existing H17 artifact; must confirm its provenance and BUILD config",
          "PiPNN R32 vs Dense R64 plus spine: graph size and topology are not matched degree/bytes",
          "One common independent search protocol controls implementation but need not reproduce native ParlayANN or GRAFT tuned search performance",
          "Selected thresholds compare different achieved recall within ef grid; no curve interpolation, no statistical CI",
          "STH not implemented; results assess competitive baseline only"]}
    (out/"comparison.json").write_text(json.dumps(rep,indent=2,ensure_ascii=False))
    print("=== H24 R0f summary: QPS at minimum Recall (discrete ef grid) ===")
    for reg,v in matches.items():
        print("\nProtocol:",reg)
        for target,vals in v.items():
            print(f"Recall>={target}")
            for arm in ARMS:
                x=vals[arm]
                print(f"  {arm:6s}: "+("NOT REACHED" if x is None else f"ef={x['ef']}, recall={x['recall10']:.4%}, median QPS={x['qps_median']:.1f}"))
    print("\nSaved:",out/"comparison.json")
    return rep


def run_cmd(cmd,log,env):
    log.parent.mkdir(parents=True,exist_ok=True)
    with log.open("w") as f:
        f.write("# COMMAND: "+shlex.join([str(x) for x in cmd])+"\n");f.flush()
        p=subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT,env=env)
    if p.returncode:raise RuntimeError(f"command failed with {p.returncode}; see {log}")


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--mode",choices=("plan","run","inspect","selftest"),default="plan")
    p.add_argument("--project",type=Path,default=PROJECT)
    p.add_argument("--source",type=Path,default=Path(__file__).parent/"h24_r0f_common_search.cpp")
    p.add_argument("--pipnn-graph",type=Path,default=None,help="existing PiPNN SIFT1M graph, original IDs")
    p.add_argument("--out",type=Path)
    a=p.parse_args()
    if a.mode=="selftest":
        print("SELFTEST: Python parser loaded, native executable selftest is part of kit distribution test")
        assert len(EFS)==6 and len(ARMS)==3
        return
    proj=a.project.expanduser().resolve()
    out=(a.out or proj/"experiments/H24/r0f_common_search_sift1m_seed42").expanduser().resolve()
    data=proj/"data"
    sample=proj/"experiments/H24/datasets/sift_subset_1000000_q1000_seed42_l2"
    graft=proj/"experiments/H24/vendor/graft-ann"
    fg=graft/"src/fg"
    pipnn=(a.pipnn_graph or proj/"results/pipnn_sift1m_4t.graph").expanduser().resolve()
    env=os.environ.copy()
    env.update(OMP_NUM_THREADS="4",OPENBLAS_NUM_THREADS="4",MKL_NUM_THREADS="4",OMP_DYNAMIC="FALSE")
    print("H24-R0f common-search; mode:",a.mode)
    for label,path in (("H24 dataset",sample),("PiPNN graph",pipnn),("GRAFT fg",fg),("Results",out)):
        print(f"{label:14s} {path}")
    if a.mode=="plan":
        print("No changes. Run mode will validate all original IDs, BUILD Dense twice only to dump graphs, then evaluate all three graphs.")
        print("New ANN BUILD outputs will not overwrite historical H24 R0e logs.")
        return
    if a.mode=="inspect":
        saved=out/"comparison.json"
        if saved.exists():
            print(saved.read_text())
        else:
            make_report(out,pipnn)
        return
    for pp in (sample/"manifest.json",sample/"X.npy",sample/"Q.npy",sample/"gold.npy",sample/"base_source_ids.npy",
               data/"sift1m.fbin",data/"sift1m_queries.fbin",pipnn,fg):
        if not pp.is_file():raise RuntimeError(f"missing input: {pp}")
    if not a.source.exists():raise RuntimeError("missing C++ evaluator source")
    gitrev=subprocess.check_output(["git","-C",str(graft),"rev-parse","HEAD"],text=True).strip()
    if gitrev!=EXPECTED_REV:raise RuntimeError(f"unexpected GRAFT commit {gitrev}; expected {EXPECTED_REV}")
    if shutil.disk_usage(proj).free<750*1024*1024:
        raise RuntimeError("need >=750 MiB disk free for two exported CSR graphs")
    with Path("/proc/meminfo").open() as f: info=f.read()
    mm=re.search(r"^MemAvailable:\s+(\d+) kB",info,re.M)
    if mm and int(mm.group(1))<5*1024*1024:raise RuntimeError("need >=5GiB available RAM before Dense export BUILD")
    proof=check_identity(sample,data/"sift1m.fbin",data/"sift1m_queries.fbin")
    print("Full base ID/vector and query alignment verified. Exact gold hashes/provenance verified.")
    graph_info(pipnn)
    out.mkdir(parents=True,exist_ok=True)
    golden=out/"gold10.rawi32"
    expectedgold=np.asarray(np.load(sample/"gold.npy",mmap_mode="r",allow_pickle=False),dtype="<i4")
    if golden.exists():
        existing=np.fromfile(golden,dtype="<i4").reshape(1000,10)
        if not np.array_equal(existing,expectedgold):raise RuntimeError("existing golden ids differ; refusing overwrite")
    else:expectedgold.tofile(golden)
    ent=out/"entries_1.rawu32"; ent8=out/"entries_8.rawu32"
    for path,ids in ((ent,[0]),(ent8,[0,12345,234567,345678,456789,567890,678901,789012])):
        if path.exists():
            if list(np.fromfile(path,dtype="<u4"))!=ids:raise RuntimeError(f"entry file changed; refuse overwrite: {path}")
        else:np.asarray(ids,dtype="<u4").tofile(path)
    meta=out/"provenance.json"
    if not meta.exists():meta.write_text(json.dumps({"baseline_revision":gitrev,"input":proof,
        "piPNN":graph_info(pipnn),"sample_dir":str(sample),"shared_ef":EFS,
        "entry1":[0],"entry8":[0,12345,234567,345678,456789,567890,678901,789012]},indent=2))
    expected_edges={"low":24213437, "high":25551006}
    for arm,m in (("low",3),("high",5)):
        graph=out/f"{arm}.graph"; log=out/f"export_{arm}_m{m}.log"
        if graph.exists():
            print("Existing Dense graph export found, validating:",graph)
            gi=graph_info(graph)
            if gi["directed_edges"]!=expected_edges[arm]:
                raise RuntimeError(f"export edge count changed for {arm}: {gi['directed_edges']} != {expected_edges[arm]} in H24-R0e")
            if not log.exists():raise RuntimeError(f"graph export log missing for {graph}")
            continue
        if log.exists():raise RuntimeError(f"build log already exists but graph is absent: {log}; inspect before retry")
        command=cmd_graft(fg,sample,graph,m)
        print("Native Dense re-BUILD for CSR export:",arm, flush=True)
        run_cmd(command,log,env)
        gi=graph_info(graph)
        if gi["directed_edges"]!=expected_edges[arm]:
            raise RuntimeError(f"export edge count changed for {arm}: {gi['directed_edges']} != {expected_edges[arm]} in H24-R0e")
    binary=out/"h24_r0f_common_search"
    if binary.exists() and binary.stat().st_mtime < a.source.stat().st_mtime:
        raise RuntimeError("C++ source is newer than existing binary. STOP; inspect/update binary explicitly.")
    if not binary.exists():
        print("Compiling independent common searcher",flush=True)
        subprocess.run(["g++","-O3","-std=c++17","-march=native","-ffp-contract=off",str(a.source),"-o",str(binary)],check=True)
    for label,entries in (("entry1",ent),("entry8",ent8)):
        for arm in ARMS:
            log=out/f"search_{arm}_{label}.log"
            if log.exists():
                print("Existing eval log (no overwrite):",log)
                continue
            graph=pipnn if arm=="pipnn" else out/f"{arm}.graph"
            command=[str(binary),"--graph",str(graph),"--base",str(data/"sift1m.fbin"),
                "--queries",str(data/"sift1m_queries.fbin"),"--gold",str(golden),
                "--entries",str(entries),"--tag",arm,"--nq","1000","--k","10","--repeats","2",
                "--efs",*[str(e) for e in EFS]]
            print("Common single-thread eval:",arm,label, flush=True)
            run_cmd(command,log,env)
    make_report(out,pipnn)


if __name__=="__main__":
    try:main()
    except Exception as e:
        print(f"H24-R0f STOP: {e}",file=sys.stderr)
        sys.exit(2)
