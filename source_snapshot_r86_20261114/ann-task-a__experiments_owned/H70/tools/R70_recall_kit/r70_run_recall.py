#!/usr/bin/env python3
"""Evaluate six existing SIFT100K graphs with native PiPNN checkRecall, no rebuild."""
import argparse
from collections import defaultdict
from datetime import datetime
import json
import os
from pathlib import Path
import re
import statistics
import subprocess

ROW = re.compile(r'R70_RECALL_ROW beam=(\d+) recall=([\d.]+) qps=([\d.]+) avg_cmps=([\d.]+) avg_visited=([\d.]+)')

def main():
    p = argparse.ArgumentParser()
    for name in ['binary','base','queries','gt','pilot','repeats','out']:
        p.add_argument('--'+name, required=True)
    a = p.parse_args()
    binary = Path(a.binary).resolve()
    pilot = Path(a.pilot).resolve()
    repeats = Path(a.repeats).resolve()
    out = Path(a.out).resolve()
    if out.exists():
        raise SystemExit('R70_RECALL_RUN_BLOCKED_OUT_EXISTS ' + str(out))
    paths = [
      ('pilot_stock','stock',pilot/'stock.graph'),
      ('repeat_01_tier','tier',repeats/'01_tier.graph'),
      ('repeat_02_stock','stock',repeats/'02_stock.graph'),
      ('pilot_tier','tier',pilot/'tier.graph'),
      ('repeat_04_tier','tier',repeats/'04_tier.graph'),
      ('repeat_03_stock','stock',repeats/'03_stock.graph'),
    ]
    if not binary.is_file():
        raise SystemExit('R70_RECALL_RUN_BLOCKED_BINARY_MISSING')
    for _,_,graph in paths:
        if not graph.is_file():
            raise SystemExit('R70_RECALL_RUN_BLOCKED_GRAPH_MISSING '+str(graph))
    out.mkdir(parents=True)
    runs = []
    env = os.environ.copy()
    env['PARLAY_NUM_THREADS'] = '1'
    for tag,variant,graph in paths:
        print('R70_RECALL_START',tag,graph,flush=True)
        result = subprocess.run([str(binary), str(graph),a.base,a.queries,a.gt],
            stdout=subprocess.PIPE,stderr=subprocess.STDOUT,universal_newlines=True,
            env=env,timeout=600,check=False)
        (out/(tag+'.log')).write_text(result.stdout)
        parsed = []
        for m in ROW.finditer(result.stdout):
            beam,recall,qps,cmps,visited=m.groups()
            parsed.append(dict(beam=int(beam),recall=float(recall),qps=float(qps),avg_cmps=float(cmps),avg_visited=float(visited)))
        print('R70_RECALL_RUN',tag,'rc='+str(result.returncode),'beams='+str(len(parsed)),flush=True)
        if result.returncode != 0 or len(parsed) != 5 or 'R70_RECALL_EVAL_PASS' not in result.stdout:
            print('R70_RECALL_RUN_FAIL',tag,'see',out/(tag+'.log'))
            raise SystemExit(1)
        runs.append(dict(tag=tag,variant=variant,graph=str(graph),measurements=parsed))
    summary = {}
    for variant in ('stock','tier'):
        rows = [r for r in runs if r['variant']==variant]
        summary[variant] = {}
        for beam in [10,20,40,80,160]:
            samples=[next(z for z in r['measurements'] if z['beam']==beam) for r in rows]
            summary[variant][str(beam)]=dict(
                recall=[s['recall'] for s in samples],
                recall_median=statistics.median(s['recall'] for s in samples),
                qps=[s['qps'] for s in samples],
                qps_median=statistics.median(s['qps'] for s in samples))
    result=dict(kind='NATIVE_PIPNN_CHECKRECALL_SAVED_GRAPHS',
          threads=1,query_count=300,k=10,cut=1.35,beams=[10,20,40,80,160],
          graph_construction_threads=4,
          limitations=['3 graphs/arm, search 300 queries; exploratory, QPS subject to run order/cache',
                       'no end-to-end build/search benchmark; separate stages',
                       'GT is expected exact for 100K base; validate separately first'],
          summary=summary,runs=runs)
    (out/'recall_summary.json').write_text(json.dumps(result,indent=2)+'\n')
    for beam in [10,20,40,80,160]:
        s=summary['stock'][str(beam)]['recall_median'];t=summary['tier'][str(beam)]['recall_median']
        print(f'R70_RECALL_COMPARE beam={beam} stock_median={s:.6f} tier_median={t:.6f} delta_pp={(t-s)*100:+.4f}',flush=True)
    print('R70_RECALL_SUITE_PASS',out/'recall_summary.json',flush=True)

if __name__ == '__main__':
    try:
        main()
    except subprocess.TimeoutExpired as e:
        print('R70_RECALL_SUITE_TIMEOUT',str(e))
        raise SystemExit(1)
