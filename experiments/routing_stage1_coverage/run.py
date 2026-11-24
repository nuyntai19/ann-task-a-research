"""Stage 1: compare ways to select 32 vertices out of the fixed root pool."""
import argparse
from pathlib import Path
from statistics import median
import time
from common import *


def medoid_swaps(dist, start, rounds=4):
    selected=list(start)
    for _ in range(rounds):
        best=None
        current=dist[:,selected].min(axis=1).mean()
        for position in range(len(selected)):
            others=selected[:position]+selected[position+1:]
            available=sorted(set(range(dist.shape[1]))-set(selected))
            costs=np.minimum(dist[:,others].min(axis=1)[:,None],dist[:,available]).mean(axis=0)
            opt=int(np.argmin(costs))
            if costs[opt]<current-1e-5 and (best is None or costs[opt]<best[0]):
                best=(costs[opt],position,available[opt])
        if best is None:
            break
        selected[best[1]]=best[2]
    return selected


def main(name):
    run=Run(HERE,name)
    sample=base_vectors()[np.loadtxt(run.data/"selection.ids",dtype=int)]
    methods=("uniform32","farthest32","facility32","medoids32")
    config_stats=[]
    cases=[]
    for seed in SEEDS:
        pool=root_ids(seed)
        centers=base_vectors()[pool]
        start=time.perf_counter()
        dist=l2(sample,centers)
        matrix_s=time.perf_counter()-start
        stats={}
        start=time.perf_counter()
        initial=greedy(dist,32)
        stats["facility32"]=(initial,matrix_s+time.perf_counter()-start)
        start=time.perf_counter()
        swaps=medoid_swaps(dist,initial)
        stats["medoids32"]=(swaps,stats["facility32"][1]+time.perf_counter()-start)
        start=time.perf_counter()
        spread=l2(centers,centers)
        farthest=[int(np.argmin(dist.mean(axis=0)))]
        for _ in range(31):
            near=spread[:,farthest].min(axis=1)
            near[farthest]=-1
            farthest.append(int(np.argmax(near)))
        stats["farthest32"]=(farthest,matrix_s+time.perf_counter()-start)
        stats["uniform32"]=([i*100//32 for i in range(32)],0)
        for arm in methods:
            ids,seconds=stats[arm]
            dst=flat(run.configs/f"{arm}_{seed}.txt",pool[ids])
            near=dist[:,ids].min(axis=1)
            config_stats.append(dict(arm=arm,seed=seed,selection_s=seconds,id_bytes=128,
                                     peak_distance_matrix_bytes=dist.nbytes,
                                     sample_mean_l2=float(near.mean()),sample_p95_l2=float(np.percentile(near,95))))
            cases.extend(Case(arm,g,seed,dst,graph(g,seed)) for g in GRAPHS)
        node0=flat(run.configs/f"node0_{seed}.txt",[])
        cases.extend(Case("node0",g,seed,node0,graph(g,seed)) for g in GRAPHS)
    csv_write(run.out/"selection.csv",config_stats)
    # Select the downstream method on calibration before opening either test set.
    score={}
    for arm in methods:
        selected=[]
        for case in cases:
            if case.arm==arm:
                data=run.eval(case,"cal","tune",CAL_GRID)
                selected.append(next((r["distance"] for r in data if r["recall"]>=.99),float("inf")))
        score[arm]=median(selected)
    winner=min(methods,key=score.get)
    save(run.out/"choice.json",dict(winner=winner,calibration_distance_at_99={
        k:v if np.isfinite(v) else None for k,v in score.items()}))
    run.benchmark(cases)


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--name",default="sift1m_r1")
    main(p.parse_args().name)
