#!/usr/bin/env python3
"""Run isolated-process stock/tier reservoir microbenchmarks.

No real ANN graph build, no Recall, no claim of algorithmic novelty.
"""
import argparse
import csv
import json
import os
import pathlib
import re
import subprocess
import sys
import time

PAT = re.compile(r'R70_SYNTHETIC_BENCH variant=(stock|tier) nodes=(\d+) high_per_mille=(\d+) elapsed_ms=(\d+) VmHWM_KiB=(-?\d+) checksum=(\d+)')

ap=argparse.ArgumentParser()
ap.add_argument('--binary', type=pathlib.Path, required=True)
ap.add_argument('--out', type=pathlib.Path, required=True)
ap.add_argument('--nodes', type=int, default=100000)
ap.add_argument('--high-per-mille', type=int, default=46)
ap.add_argument('--repeats', type=int, default=3)
ap.add_argument('--timeout', type=int, default=300)
args=ap.parse_args()
if not args.binary.is_file() or args.nodes<100 or args.repeats<1 or args.repeats>10 or not (0<=args.high_per_mille<=1000):
    raise SystemExit('R70_BENCH_INVALID_ARGS_OR_MISSING_BINARY')
out=args.out.expanduser().resolve();out.mkdir(parents=True, exist_ok=True)
env=os.environ.copy()
env['PARLAY_NUM_THREADS']='1'
env['OMP_NUM_THREADS']='1'
env['OPENBLAS_NUM_THREADS']='1'
rows=[]
# Alternating AB/BA avoids systematic run-order advantage.
order=[]
for r in range(args.repeats):
    order += [(r, v) for v in (('stock','tier') if r%2==0 else ('tier','stock'))]
print('R70_SYNTHETIC_MICROBENCH_BEGIN', 'nodes='+str(args.nodes), 'high_per_mille='+str(args.high_per_mille), flush=True)
for k,(rep,variant) in enumerate(order,1):
    command=[str(args.binary.resolve()),variant,str(args.nodes),str(args.high_per_mille)]
    start=time.perf_counter()
    try:
        p=subprocess.run(command,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,
                         timeout=args.timeout,env=env)
    except subprocess.TimeoutExpired:
        raise SystemExit(f'R70_BENCH_TIMEOUT run={k} variant={variant}; full BUILD not started')
    elapsed_sec=time.perf_counter()-start
    (out/f'run_{k:02d}_{variant}.stdout.txt').write_text(p.stdout)
    (out/f'run_{k:02d}_{variant}.stderr.txt').write_text(p.stderr)
    if p.returncode!=0:
        raise SystemExit(f'R70_BENCH_FAIL run={k} variant={variant} exit={p.returncode}; inspect run logs')
    m=PAT.search(p.stdout)
    if not m or m.group(1)!=variant or int(m.group(2))!=args.nodes or int(m.group(3))!=args.high_per_mille:
        raise SystemExit(f'R70_BENCH_OUTPUT_INVALID run={k} variant={variant}')
    row={'run':k,'repeat':rep+1,'variant':variant,'nodes':args.nodes,
         'high_per_mille':args.high_per_mille,'elapsed_ms':int(m.group(4)),
         'VmHWM_KiB':int(m.group(5)),'checksum':int(m.group(6)),
         'process_elapsed_sec':round(elapsed_sec,4)}
    rows.append(row)
    print(f'R70_RUN {k}/{len(order)} variant={variant} elapsed_ms={row["elapsed_ms"]} VmHWM_KiB={row["VmHWM_KiB"]} checksum={row["checksum"]}',flush=True)
byvariant={v:[r for r in rows if r['variant']==v] for v in ('stock','tier')}
if len({x['checksum'] for x in rows})!=1:
    raise SystemExit('R70_BENCH_CHECKSUM_MISMATCH; not proof of equivalence, but mismatch blocks comparison')
import statistics
summary={'kind':'SYNTHETIC_RESERVOIR_MICROBENCH_NOT_NATIVE_PIPNN_BUILD',
         'nodes':args.nodes,'high_per_mille':args.high_per_mille,
         'repeats_per_arm':args.repeats,
         'stock':{'median_elapsed_ms':statistics.median(r['elapsed_ms'] for r in byvariant['stock']),
                  'median_VmHWM_KiB':statistics.median(r['VmHWM_KiB'] for r in byvariant['stock'])},
         'tier':{'median_elapsed_ms':statistics.median(r['elapsed_ms'] for r in byvariant['tier']),
                  'median_VmHWM_KiB':statistics.median(r['VmHWM_KiB'] for r in byvariant['tier'])},
         'checksum_all_equal':True,
         'limitations':['synthetic per-row ordered input; not replay of R60 distribution',
                        'VmHWM is total-process high-water RSS, not allocation size',
                        'elapsed time includes constructor and sequential merges, but excludes object destruction; does not include real PiPNN BUILD or SEARCH',
                        'three repeats are preliminary and do not demonstrate end-to-end two-metric benefit']}
summary['time_delta_percent'] = round(100*(summary['tier']['median_elapsed_ms']/summary['stock']['median_elapsed_ms'] -1),2) if summary['stock']['median_elapsed_ms'] else None
summary['VmHWM_delta_percent'] = round(100*(summary['tier']['median_VmHWM_KiB']/summary['stock']['median_VmHWM_KiB'] -1),2) if summary['stock']['median_VmHWM_KiB'] else None
(out/'runs.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2)+'\n')
with (out/'runs.csv').open('w',newline='') as f:
    w=csv.DictWriter(f,fieldnames=rows[0].keys()); w.writeheader();w.writerows(rows)
(out/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
print('R70_BENCH_CHECKSUM_PASS')
print('R70_SYNTHETIC_SUMMARY', json.dumps(summary,ensure_ascii=False))
print('R70_FILES',out)
