"""Run the frozen SIFT1M Beam-Rescue comparison and preserve raw artifacts."""
import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import random
import re
import shlex
import subprocess
import sys
import time

import numpy as np

HERE = Path(__file__).resolve().parent
FOLLOW = HERE.parent / "adaptive_fanout_followup"
V1 = HERE.parent / "adaptive_fanout_v1"
DATA = V1 / "data/sift_n1000000_q10000"
BIN = FOLLOW / "build/beam_rescue"
SEEDS = (555,556,557)
ARMS = {
    "fixed": ("fixed",0), "v1": ("adaptive",0), "v2a": ("v2a",0),
    "v2b": ("v2b",0), "v3": ("v3",0), "rescue": ("rescue",0),
    "random": ("random",0), "fixed_r32": ("fixed",32),
    "v2a_r32": ("v2a",32), "v2a_r100": ("v2a",100), "rescue_r32": ("rescue",32),
}
GRID = [40,64,80,84,86,*range(88,101),112,120,125,128,131,136,140,160]
TARGETS = {"r99":0.99,"r995":0.995}
REPEATS = 3
WARMUP_BEAM = 112


def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1<<20), b""):
            h.update(chunk)
    return h.hexdigest()


def save(path,data):
    path.write_text(json.dumps(data,indent=2,allow_nan=False)+"\n")


def read_rows(path, delimiter=","):
    with path.open() as f:
        return list(csv.DictReader(f,delimiter=delimiter))


def original(seed,arm):
    return FOLLOW / "runs" / f"sift1m_fanout_{arm}_s{seed}"


def ensure_graphs(reference, path, patches):
    a,b = [np.memmap(p,mode="r",dtype="<u4") for p in (reference,path)]
    n=int(a[0])
    if len(a) != len(b) or not np.array_equal(a[:n+2],b[:n+2]):
        raise ValueError("Reallocation changed graph size or per-node out-degree")
    offsets = np.cumsum(np.r_[n+2,a[2:n+1]],dtype=np.uint64)
    changed = np.flatnonzero(a[n+2:] != b[n+2:])+n+2
    expected = []
    for edit in patches:
        u,slot,old,new = map(int,(edit[k] for k in ("u","slot","old","new")))
        start = int(offsets[u])
        index = start+slot
        row = b[start:start+int(b[u+2])]
        if (a[index] != old or b[index] != new or len(set(row)) != len(row) or u in row):
            raise ValueError("Unexpected adjacency edit")
        expected.append(index)
    if list(changed) != sorted(expected):
        raise ValueError("Unaccounted graph mutation")
    return {"edits":len(changed),"edges":len(b)-n-2,"sha256":sha(path)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--name", default="sift1m_rescue_r1")
    parser.add_argument("--stage", choices=("refine","evaluate","all"), default="all")
    opts = parser.parse_args()
    if not re.fullmatch(r"[a-zA-Z0-9_-]+",opts.name):
        parser.error("Invalid name")
    root = HERE / "runs" / opts.name
    root.mkdir(parents=True,exist_ok=True)
    raw = root / "raw"
    raw.mkdir(exist_ok=True)
    expected_data = json.loads((DATA/"manifest.json").read_text())["sha256"]
    for name,digest in expected_data.items():
        if sha(DATA/name) != digest:
            raise ValueError(f"Changed input {name}")
    protocol = {"grid":GRID,"targets":TARGETS,"seeds":SEEDS,"arms":ARMS,"timing_repeats":REPEATS,
                "threads":4,"cores":"0,2,4,6","warmup_beam":WARMUP_BEAM,
                "holdout":"SIFT1M 10000 queries, never used for selecting edges; reused historical benchmark",
                "data_sha256":expected_data,"mine_sha256":sha(BIN/"beam_rescue_mine"),
                "eval_sha256":sha(BIN/"beam_rescue_eval")}
    baseline = {f"{arm}_{seed}":json.loads((original(seed,arm)/"summary.json").read_text())
                for seed in SEEDS for arm, route in set(ARMS.values()) if arm not in ("rescue","random")}
    protocol["original_graphs"] = {key:r["graph"]["sha256"] for key,r in baseline.items()}
    if not (root/"protocol.json").exists():
        save(root/"protocol.json",protocol)
    elif json.loads((root/"protocol.json").read_text()) != json.loads(json.dumps(protocol)):
        raise ValueError("Campaign protocol changed")

    def run(cmd, log, extra=None):
        log = root/log
        env = {key:value for key,value in os.environ.items() if not key.startswith("RESCUE_")}
        custom = {"PARLAY_NUM_THREADS":"4","OPENBLAS_NUM_THREADS":"4", **(extra or {})}
        env.update(custom)
        full = ["taskset","-c","0,2,4,6",*map(str,cmd)]
        with (root/"commands.sh").open("a") as script:
            script.write(shlex.join(["env",*[f"{k}={v}" for k,v in custom.items()],*full])
                         + " > "+shlex.quote(str(log))+" 2>&1\n")
        print("START",log.name,flush=True)
        start=time.perf_counter()
        with log.open("x") as f:
            subprocess.run(full,stdout=f,stderr=subprocess.STDOUT,env=env,check=True,timeout=1800)
        return time.perf_counter()-start

    for seed in SEEDS:
        for arm in ("fixed","adaptive","v2a","v2b","v3"):
            p = original(seed,arm)/"index.graph"
            if sha(p) != baseline[f"{arm}_{seed}"]["graph"]["sha256"]:
                raise ValueError(f"Historical graph changed {p}")

    cal = root/"calibration.tsv"
    if opts.stage in ("all","refine"):
        if not cal.exists():
            run([sys.executable,"-B",HERE/"prepare.py",DATA/"base.fbin",cal],"prepare.log")
        for seed in SEEDS:
            for arm in ("fixed","v2a"):
                out = root/f"{arm}_{seed}"
                duration = run([BIN/"beam_rescue_mine",DATA/"base.fbin",original(seed,arm)/"index.graph",
                                cal,out,seed,"audit" if arm=="fixed" else "refine"],f"{out.name}.log")
                save(out/"time.json",{"elapsed_s_includes_graph_load":duration})
        verified = {}
        for seed in SEEDS:
            out = root/f"v2a_{seed}"
            patches = read_rows(out/"patches.tsv","\t")
            for arm in ("rescue","random"):
                verified[f"{arm}_{seed}"] = ensure_graphs(
                    original(seed,"v2a")/"index.graph",out/(arm+".graph"),
                    [row for row in patches if row["arm"]==arm])
        save(root/"frozen_graphs.json", {"calibration_sha256":sha(cal),"graphs":verified})
    if opts.stage == "refine":
        return
    frozen = json.loads((root/"frozen_graphs.json").read_text())
    for key, meta in frozen["graphs"].items():
        arm,seed = key.split("_")
        if sha(root/f"v2a_{seed}"/f"{arm}.graph") != meta["sha256"]:
            raise ValueError(f"Changed refinement graph {key}")

    def eval_case(seed, arm, label, beams):
        graph, router = ARMS[arm]
        path = (root/f"v2a_{seed}"/f"{graph}.graph" if graph in ("rescue","random")
                else original(seed,graph)/"index.graph")
        log = raw/f"{label}.log"
        metrics = raw/f"{label}.csv"
        parsed = raw/f"{label}.json"
        if parsed.exists():
            return json.loads(parsed.read_text())
        route = {"RESCUE_ROUTE_COUNT":str(router),"RESCUE_ROUTE_SEED":str(seed)} if router else {}
        run([BIN/"beam_rescue_eval",path,DATA/"base.fbin",DATA/"query.fbin",DATA/"gt.ibin",
             metrics,",".join(map(str,beams))],log.relative_to(root),route)
        text=log.read_text()
        rows=re.findall(r"LOCAL_RECALL_ROW beam=(\d+) recall=([\d.eE+-]+) qps=([\d.eE+-]+) avg_cmps=([\d.eE+-]+) avg_visited=([\d.eE+-]+)",text)
        if [int(row[0]) for row in rows] != list(beams) or "LOCAL_RECALL_EVAL_PASS" not in text:
            raise ValueError(f"Incomplete eval {label}")
        values={beam:{} for beam in beams}
        for row in read_rows(metrics):
            qid,beam=int(row["query_id"]),int(row["beam"])
            if qid in values[beam] or not 0 <= qid < 10_000:
                raise ValueError("Duplicate or invalid query row")
            values[beam][qid] = float(row["latency_us"]),int(row["hits_at_10"])
        reach=int(re.search(r"AF_GRAPH_REACHABLE=(\d+)",text)[1])
        result=[]
        for b,recall,qps,cmps,visited in rows:
            b=int(b)
            if len(values[b]) != 10_000:
                raise ValueError("Incomplete per-query results")
            latency,hits=np.array(list(values[b].values())).T
            exact_recall=hits.sum()/100000
            if abs(float(recall)-exact_recall)>1e-6 or not np.all(np.isfinite(latency) & (latency > 0)):
                raise ValueError("Invalid search statistics")
            result.append(dict(arm=arm,seed=seed,beam=b,recall=exact_recall,qps=float(qps),
                               avg_cmps=int(cmps),avg_visited=int(visited),reach=reach,
                               mean_us=float(latency.mean()),p95_us=float(np.percentile(latency,95))))
        save(parsed,result)
        return result

    survey=[]
    for seed in SEEDS:
        order=list(ARMS)
        random.Random(seed).shuffle(order)
        for arm in order:
            # Warm up before the survey. Timing used for claims is measured separately.
            stats=eval_case(seed,arm,f"survey_{arm}_{seed}",[WARMUP_BEAM,*[b for b in GRID if b!=WARMUP_BEAM]])
            survey.extend(stats)
            if ARMS[arm][1] == 0 and ARMS[arm][0] not in ("rescue","random"):
                old={r["beam"]:r for r in baseline[f"{ARMS[arm][0]}_{seed}"]["search"]}
                for r in stats:
                    if r["beam"] in old:
                        row=old[r["beam"]]
                        if abs(row["recall_at_10"]-r["recall"])>1e-6 or any(
                            int(row[k])!=r[k] for k in ("avg_cmps","avg_visited")):
                            raise ValueError(f"Native evaluator parity failed for {arm} seed {seed}: {r}")
    save(root/"survey.json",survey)
    selected={}
    for seed in SEEDS:
        for arm in ARMS:
            group=sorted((r for r in survey if (r["seed"],r["arm"])==(seed,arm)),key=lambda r:r["beam"])
            selected[f"{arm}_{seed}"]={
                name: next((r["beam"] for r in group if r["recall"]>=target),None)
                for name,target in TARGETS.items()}
    save(root/"operating_points.json",selected)

    timing=[]
    for repeat in range(REPEATS):
        for seed in SEEDS:
            order=list(ARMS)
            random.Random(seed+100).shuffle(order)
            if repeat == 1:
                order.reverse()
            if repeat == 2:
                order=order[len(order)//2:]+order[:len(order)//2]
            for arm in order:
                target_beams=selected[f"{arm}_{seed}"]
                beams=sorted({b for b in target_beams.values() if b is not None})
                if not beams:
                    continue
                warmup=next(b for b in (112,110,114) if b not in beams)
                stats=eval_case(seed,arm,f"timing_{repeat}_{arm}_{seed}",[warmup,*beams])
                for target,beam in target_beams.items():
                    if beam is None:
                        continue
                    row=next(r for r in stats if r["beam"]==beam)
                    if row["recall"]<TARGETS[target]:
                        raise ValueError("Recall changed between discovery and timing")
                    timing.append(dict(repeat=repeat,target=target,**row))
    save(root/"timing.json",timing)
    print("SIFT1M_CAMPAIGN_PASS",root,flush=True)


if __name__=="__main__":
    main()
