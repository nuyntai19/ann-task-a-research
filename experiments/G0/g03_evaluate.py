#!/usr/bin/env python3
"""Run native ParlayANN Vamana on G0.3 variants, report fixed-Q Recall/QPS."""
import argparse
import csv
import json
import os
import re
import statistics
import subprocess
from pathlib import Path

SEARCH_RE = re.compile(r'^search:\s*Q=(\d+),.*?\brecall=([\d.eE+-]+),.*?\bcomparisons=(\d+),.*?\bQPS=([\d.eE+-]+)', re.MULTILINE)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--root', type=Path, default=Path.cwd())
    p.add_argument('--budget', type=int, default=100000)
    p.add_argument('--seed', type=int, default=20261023)
    p.add_argument('--q', type=int, nargs='+', default=[120,135,160])
    args = p.parse_args()
    root = args.root.resolve()
    outdir = root/'experiments/G0/results/g03'
    manifest_file = outdir/f'manifest_b{args.budget}_s{args.seed}.json'
    manifest = json.loads(manifest_file.read_text(encoding='utf-8'))
    binary = root/'src/ParlayANN/algorithms/vamana/neighbors'
    if not binary.is_file() or not os.access(binary, os.X_OK):
        raise FileNotFoundError(f'Missing executable: {binary}')
    paths = [root/'data/sift1m.fbin', root/'data/sift1m_queries.fbin', root/'data/sift1m_gt.ibin']
    for path in paths:
        if not path.is_file() or path.stat().st_size < 8:
            raise FileNotFoundError(path)
    logs = root/'experiments/G0/logs/g03'
    logs.mkdir(parents=True, exist_ok=True)
    rows = []
    for name, graph_s in manifest['graphs'].items():
        graph = Path(graph_s)
        if not graph.is_file():
            raise FileNotFoundError(graph)
        if name != 'f60' and graph.stat().st_size != manifest['expected_graph_bytes']:
            raise ValueError(f'Graph bytes mismatch: {graph}')
        for q in args.q:
            log = logs/f'{name}_b{args.budget}_s{args.seed}_Q{q}.log'
            argv = [str(binary), '-R','32','-L','64','-alpha','1.2',
                    '-data_type','float','-dist_func','Euclidian',
                    '-base_path',str(paths[0]), '-graph_path',str(graph),
                    '-query_path',str(paths[1]), '-gt_path',str(paths[2]),
                    '-k','10','-Q',str(q),'-verbose']
            env = os.environ.copy()
            env['PARLAY_NUM_THREADS']='1'
            print(f'===== {name} Q={q} =====', flush=True)
            with log.open('w', encoding='utf-8') as f:
                outcome = subprocess.run(argv, env=env, cwd=root, stdout=f, stderr=subprocess.STDOUT, check=False)
            if outcome.returncode != 0:
                print(f'FAILED exit={outcome.returncode}; log={log}', flush=True)
                raise SystemExit(outcome.returncode)
            content = log.read_text(errors='replace')
            records = [(float(rec), int(cmp), float(qps)) for qq,rec,cmp,qps in SEARCH_RE.findall(content) if int(qq)==q]
            if len(records) < 3:
                print(f'FAILED expected >=3 native search records, got {len(records)}: {log}', flush=True)
                raise SystemExit(3)
            recalls = [z[0] for z in records]
            if max(recalls)-min(recalls) > 1e-7:
                print('WARNING: Native recall varied across repetitions; investigate', flush=True)
            result = dict(policy=name, Q=q, recall=statistics.median(recalls),
                          median_qps=statistics.median(z[2] for z in records),
                          comparisons=statistics.median(z[1] for z in records),
                          samples=len(records), graph_bytes=graph.stat().st_size)
            rows.append(result)
            print(f'  Recall={result["recall"]:.6f} QPS={result["median_qps"]:.2f} comparisons={result["comparisons"]:.0f} samples={len(records)}', flush=True)
    csv_file=outdir/f'search_b{args.budget}_s{args.seed}.csv'
    json_file=outdir/f'search_b{args.budget}_s{args.seed}.json'
    with csv_file.open('w', newline='', encoding='utf-8') as fh:
        writer=csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(rows)
    json_file.write_text(json.dumps(rows, indent=2), encoding='utf-8')
    print('\n===== FIXED-Q COMPARISON AGAINST f30 =====')
    for q in args.q:
        baseline=next(row for row in rows if row['policy']=='f30' and row['Q']==q)
        print(f'Q={q}: baseline Recall={baseline["recall"]:.6f}, QPS={baseline["median_qps"]:.2f}')
        for row in rows:
            if row['Q']==q and row['policy'] not in ('f30','f60'):
                dr=(row['recall']-baseline['recall'])*100
                dq=(row['median_qps']/baseline['median_qps']-1)*100
                print(f'  {row["policy"]:19} delta_Recall={dr:+.4f} percentage-points, delta_QPS={dq:+.2f}%')
    print(f'G0.3 EVALUATION PASS: {csv_file}',flush=True)
    print('CAUTION: oracle methods already paid the full f60 construction cost. These are feasibility diagnostics, not build-time speedups.',flush=True)


if __name__=='__main__':
    main()
