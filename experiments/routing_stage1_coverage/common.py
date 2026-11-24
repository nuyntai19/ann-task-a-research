"""Shared experiment harness. Each stage stores its own configs, commands and results."""
import csv
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import random
import shlex
from statistics import median
import subprocess
import time

for key in ("OPENBLAS_NUM_THREADS","OMP_NUM_THREADS","MKL_NUM_THREADS"):
    os.environ[key] = "4" if key=="OPENBLAS_NUM_THREADS" else "1"
import numpy as np

HERE=Path(__file__).resolve().parent
EXP=HERE.parent
FOLLOW=EXP/"adaptive_fanout_followup"
SIFT=EXP/"adaptive_fanout_v1/data/sift_n1000000_q10000"
REFERENCE=EXP/"beam_rescue/runs/sift1m_rescue_r1"
BIN=FOLLOW/"build/routing_stages/staged_route_eval"
SEEDS=(555,556,557)
GRAPHS=("fixed","v2a")
GRID=(40,64,80,86,90,92,94,96,98,100,104,112,120,126,132,140,152,168,192,240,320)
CAL_GRID=(80,92,96,104,120,140,168,240)
FOLLOW_GRID=(80,90,94,96,98,104,112,120,126,132,140,152,192,240)
TARGETS=(.99,.995)
REPEATS=3


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream,"sha256").hexdigest()


def save(path,obj):
    path.write_text(json.dumps(obj,indent=2,allow_nan=False)+"\n")


def rows(path):
    with path.open() as f:
        return list(csv.DictReader(f))


def csv_write(path,data):
    if not data:
        raise ValueError(f"Refusing an empty summary: {path}")
    with path.open("w",newline="") as f:
        writer=csv.DictWriter(f,fieldnames=list(data[0]))
        writer.writeheader()
        writer.writerows(data)


def graph(arm,seed):
    return FOLLOW/"runs"/f"sift1m_fanout_{arm}_s{seed}"/"index.graph"


def root_ids(seed):
    ids=np.loadtxt(REFERENCE/f"v2a_{seed}/root_leaders.txt",dtype=np.int64)
    if len(set(ids))!=100:
        raise ValueError("Missing saved root leaders")
    return ids


def base_vectors():
    return np.memmap(SIFT/"base.fbin",dtype="<f4",mode="r",offset=8,shape=(1_000_000,128))


def l2(a,b):
    out=a@b.T
    out*=-2
    out+=np.einsum("ij,ij->i",a,a)[:,None]
    out+=np.einsum("ij,ij->i",b,b)
    return np.sqrt(np.maximum(out,0))


def greedy(dist,k):
    """Add the candidate giving the largest improvement in mean sample L2."""
    available=set(range(dist.shape[1]))
    near=np.full(len(dist),np.inf)
    chosen=[]
    for _ in range(k):
        subset=sorted(available)
        entry=subset[int(np.argmin(np.minimum(near[:,None],dist[:,subset]).mean(axis=0)))]
        chosen.append(entry)
        near=np.minimum(near,dist[:,entry])
        available.remove(entry)
    return chosen


def flat(path, ids, ratio=0):
    path.write_text(f"flat {len(ids)} {ratio}\n"+" ".join(map(str,ids))+"\n")
    return path


def from_flat(path):
    tokens=path.read_text().split()
    if tokens[0]!="flat" or int(tokens[1])!=len(tokens[3:]):
        raise ValueError("Invalid flat config")
    return [int(i) for i in tokens[3:]],float(tokens[2])


@dataclass(frozen=True)
class Case:
    arm: str
    base_graph: str
    seed: int
    route: Path
    index: Path


class Run:
    def __init__(self,folder,name):
        self.out=folder/"runs"/name
        self.data=HERE/"runs"/name/"data"
        self.raw=self.out/"raw"
        self.raw.mkdir(parents=True,exist_ok=True)
        self.configs=self.out/"configs"
        self.configs.mkdir(exist_ok=True)
        self.command_log=self.out/"commands.sh"

    def execute(self,cmd,log,extra=None):
        env={k:v for k,v in os.environ.items() if not k.startswith(("AF_","R86_","ROUTE_"))}
        custom={"PARLAY_NUM_THREADS":"4","OPENBLAS_NUM_THREADS":"4","OMP_NUM_THREADS":"1",**(extra or {})}
        env.update(custom)
        full=["taskset","-c","0,2,4,6",*map(str,cmd)]
        with self.command_log.open("a") as f:
            f.write(shlex.join(["env",*[f"{k}={v}" for k,v in custom.items()],*full])
                    +" > "+shlex.quote(str(log))+" 2>&1\n")
        start=time.perf_counter()
        with log.open("x") as f:
            subprocess.run(full,env=env,stdout=f,stderr=subprocess.STDOUT,check=True,timeout=3600)
        return time.perf_counter()-start

    def eval(self,case,dataset,label,beams,detail=False):
        keys=f"{dataset}_{label}_{case.arm}_{case.base_graph}_{case.seed}"
        target=self.raw/(keys+".csv")
        detail_path=self.raw/(keys+"_queries.csv") if detail else "-"
        if dataset=="official":
            query,gt=SIFT/"query.fbin",SIFT/"gt.ibin"
        elif dataset in ("cal","proxy"):
            query,gt="@"+str(self.data/(dataset+".ids")),self.data/(dataset+".ibin")
        else:
            raise ValueError(dataset)
        native_beams=[112,*sorted(set(beams))]
        print("RUN",keys,flush=True)
        log=self.raw/(keys+".log")
        time_log=self.raw/(keys+".time")
        self.execute(["/usr/bin/time","-f","%M","-o",time_log,BIN,SIFT/"base.fbin",case.index,query,gt,case.route,
                      ",".join(map(str,native_beams)),target,detail_path],log)
        peak_rss_mib=float(time_log.read_text().strip())/1024
        result=[{**{k:float(v) for k,v in r.items()},"peak_rss_mib":peak_rss_mib} for r in rows(target)]
        if [int(r["beam"]) for r in result]!=native_beams[1:] or "ROUTE_EVAL_PASS" not in log.read_text():
            raise ValueError(f"Incomplete benchmark {keys}")
        if any(not 0<=r["recall"]<=1 or r["qps"]<=0 or r["mean_us"]<=0 for r in result):
            raise ValueError(f"Invalid metrics {keys}")
        return result

    def provenance(self,cases,grid):
        required={str(c.index):sha(c.index) for c in {c.index:c for c in cases}.values()}
        config={str(c.route):sha(c.route) for c in {c.route:c for c in cases}.values()}
        inputs={str(SIFT/f):sha(SIFT/f) for f in ("base.fbin","query.fbin","gt.ibin")}
        expected=json.loads((SIFT/"manifest.json").read_text())["sha256"]
        if any(digest != expected[Path(path).name] for path,digest in inputs.items()):
            raise ValueError("Frozen SIFT1M input changed")
        for dataset in ("cal","proxy"):
            for ext in ("ids","ibin"):
                p=self.data/f"{dataset}.{ext}"
                inputs[str(p)]=sha(p)
        for c in cases:
            if c.index==graph(c.base_graph,c.seed):
                summary=json.loads(c.index.with_name("summary.json").read_text())
                if required[str(c.index)]!=summary["graph"]["sha256"]:
                    raise ValueError(f"Historical graph changed {c.index}")
        save(self.out/"manifest.json",dict(grid=grid,seeds=SEEDS,inputs_sha256=inputs,
             configs_sha256=config,graphs_sha256=required,evaluator_sha256=sha(BIN),timing_repeats=REPEATS,
             thresholds=TARGETS,threads=4,affinity=[0,2,4,6]))

    def benchmark(self,cases,reuse=None,grid=GRID):
        self.provenance(cases,grid)
        reuse=reuse or {}
        current=json.loads((self.out/"manifest.json").read_text())
        cached_root=HERE/"runs"/self.out.name
        cached=(json.loads((cached_root/"manifest.json").read_text()) if reuse else None)

        def survey_case(case,dataset):
            ref=reuse.get(case.arm)
            if ref and cached["evaluator_sha256"]==current["evaluator_sha256"] and cached["inputs_sha256"]==current["inputs_sha256"]:
                prev=cached_root/"configs"/f"{ref}_{case.seed}.txt"
                src=cached_root/"raw"/f"{dataset}_survey_{ref}_{case.base_graph}_{case.seed}.csv"
                if (from_flat(prev)==from_flat(case.route) and src.is_file() and
                    cached["graphs_sha256"].get(str(case.index))==current["graphs_sha256"][str(case.index)]):
                    data=[{k:float(v) for k,v in r.items()} for r in rows(src)]
                    data=[r for r in data if r["beam"] in grid]
                    if [r["beam"] for r in data]==list(grid):
                        return [{**r,"peak_rss_mib":None} for r in data],str(src)
            return self.eval(case,dataset,"survey",grid),"new"
        survey=[]
        picks={}
        for dataset in ("official","proxy"):
            order=list(cases)
            random.Random(79).shuffle(order)
            for case in order:
                res,origin=survey_case(case,dataset)
                survey.extend(dict(dataset=dataset,arm=case.arm,graph=case.base_graph,seed=case.seed,origin=origin,**r) for r in res)
                picks[dataset,case]={
                    target:next((int(r["beam"]) for r in res if r["recall"]>=target),None)
                    for target in TARGETS
                }
        csv_write(self.out/"survey.csv",survey)
        save(self.out/"operating_points.json",[
            dict(dataset=d,arm=c.arm,graph=c.base_graph,seed=c.seed,
                 beams={str(k):v for k,v in p.items()})
            for (d,c),p in picks.items()])
        details=[]
        for dataset in ("official","proxy"):
            order=list(cases)
            random.Random(33).shuffle(order)
            for repeat in range(REPEATS):
                if repeat==1:
                    order.reverse()
                if repeat==2:
                    order=order[len(order)//2:]+order[:len(order)//2]
                for case in order:
                    target_beams=picks[dataset,case]
                    beams=[beam for beam in target_beams.values() if beam is not None]
                    if not beams:
                        continue
                    out={r["beam"]:r for r in self.eval(case,dataset,f"r{repeat+1}",beams)}
                    for target,beam in target_beams.items():
                        if beam is not None:
                            r=out[beam]
                            if r["recall"]<target:
                                raise ValueError("Recall failed to reproduce")
                            details.append(dict(dataset=dataset,arm=case.arm,graph=case.base_graph,
                                                seed=case.seed,target=target,repeat=repeat+1,**r))
        csv_write(self.out/"timing.csv",details)
        summarize(self.out,details,picks)


METRICS=("beam","recall","qps","mean_us","p95_us","p99_us","visited","distance",
         "route_cmps","two_fraction","entry_l2","peak_rss_mib")


def summarize(out,details,picks):
    groups={}
    for row in details:
        key=tuple(row[k] for k in ("dataset","graph","arm","seed","target"))
        groups.setdefault(key,[]).append(row)
    per_seed=[]
    for key,group in sorted(groups.items()):
        if len(group)!=REPEATS:
            raise ValueError("Incomplete timing repeats")
        per_seed.append(dict(zip(("dataset","graph","arm","seed","target"),key),
                             **{k:median(r[k] for r in group) for k in METRICS}))
    folded={}
    for r in per_seed:
        folded.setdefault(tuple(r[k] for k in ("dataset","graph","arm","target")),[]).append(r)
    aggregate=[]
    for (dataset,g,arm,target),group in sorted(folded.items()):
        aggregate.append(dict(dataset=dataset,graph=g,arm=arm,target=target,seeds=len(group),
                              **{k:median(r[k] for r in group) for k in METRICS}))
    csv_write(out/"per_seed.csv",per_seed)
    csv_write(out/"matched_recall.csv",aggregate)
    table=["# SIFT1M routing results","",
           "Median of each seed's medians at the first beam on the survey grid reaching the target.",
           "Official queries were used historically. Proxy queries are held-out, self-excluded base vectors.",
           "Routing comparisons are included. p95 is query service time.","",
           "| Query set | Graph | Arm | Target | Seeds | Beam | Recall | QPS | Mean µs | P95 µs | Visited | Distance | Top-2 |",
           "|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for r in aggregate:
        table.append(f"| {r['dataset']} | {r['graph']} | {r['arm']} | {r['target']:.1%} | {r['seeds']}/3 | "
                     f"{r['beam']:g} | {r['recall']:.3%} | {r['qps']:,.0f} | {r['mean_us']:.1f} | "
                     f"{r['p95_us']:.1f} | {r['visited']:.1f} | {r['distance']:.1f} | {r['two_fraction']:.1%} |")
    missing=[(d,c.arm,c.base_graph,c.seed,t) for (d,c),p in picks.items() for t,b in p.items() if b is None]
    save(out/"validation.json",dict(status="PASS",cases=len(picks),timing_rows=len(details),missing_targets=missing))
    (out/"REPORT.md").write_text("\n".join(table)+"\n")
