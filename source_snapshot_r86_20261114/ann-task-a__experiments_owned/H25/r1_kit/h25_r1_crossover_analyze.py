#!/usr/bin/env python3
"""Analyze H25-R1 crossover. Only same fixed graphs; not a new BUILD claim."""
import csv
import json
import statistics
import sys
from pathlib import Path

EFS = (140, 160, 180, 200)
POLICIES = ('baseline', 'nearest', 'random')

def load(path):
    with path.open(newline='', encoding='utf-8') as f:
        rr = list(csv.DictReader(f))
    assert len(rr) == len(EFS), (str(path), len(rr))
    ret = {}
    for x in rr:
        ef = int(x['ef'])
        assert ef in EFS and ef not in ret, (str(path),ef)
        assert int(x['nq']) == 10000 and int(x['repeats']) == 3
        ret[ef] = {
            'qps': float(x['median_qps']),
            'recall10': float(x['recall10']),
            'edges': int(x['edges']),
            'graph_bytes': int(x['graph_bytes']),
            'reachable0': int(x['reachable0']),
            'n': int(x['n']),
        }
    assert sorted(ret) == list(EFS)
    return ret

def main():
    directory = Path(sys.argv[1]) if len(sys.argv) == 2 else None
    if directory is None or not directory.is_dir():
        raise SystemExit('Usage: python3 h25_r1_crossover_analyze.py OUTPUT_DIRECTORY')
    data = {(r, p): load(directory / f'r{r}_{p}.csv') for r in (1, 2, 3) for p in POLICIES}
    for p in POLICIES:
        ref = [data[(1,p)][ef]['recall10'] for ef in EFS]
        for r in (1, 2, 3):
            for i,ef in enumerate(EFS):
                x = data[(r,p)][ef]
                if x['recall10'] != ref[i]:
                    raise ValueError(f'Recall not identical on same graph: {r=} {p=} {ef=}')
                for name in ('edges', 'graph_bytes', 'reachable0', 'n'):
                    if x[name] != data[(1,p)][ef][name]:
                        raise ValueError(f'Graph metadata changed: {r=} {p=} {ef=} {name=}')

    output = {'study': 'H25_R1_CROSSOVER_SAME_GRAPHS_NOT_REPEATED_BUILD',
              'rounds':3,'ef_grid':list(EFS),'query_count':10000,
              'repeat_qps_per_call':3,'results':{}}
    print('H25-R1 crossover: each variant appears once in each order position.')
    print('Only SEARCH timing repeatability. Offline policy cost, BUILD repeatability and edge matching remain OPEN.')
    print()
    for ef in EFS:
        print(f'ef={ef} | recall B/N/R: '+ ' / '.join(f'{data[(1,p)][ef]["recall10"]:.5f}' for p in POLICIES))
        ratios = {}
        for policy in ('nearest', 'random'):
            per_round = [100 * (data[(r,policy)][ef]['qps'] / data[(r,'baseline')][ef]['qps'] - 1) for r in (1,2,3)]
            ratios[policy] = {'relative_qps_pct_by_round': per_round,
                              'median_gain_pct': statistics.median(per_round),
                              'min_gain_pct':min(per_round),'max_gain_pct':max(per_round)}
            print(f'  {policy:7s}: QPS gain by round = '+', '.join(f'{x:+.2f}%' for x in per_round) +
                  f' ; median = {statistics.median(per_round):+.2f}%')
        base_qps=[data[(r,'baseline')][ef]['qps'] for r in (1,2,3)]
        print('  baseline QPS by round: '+', '.join(f'{x:.2f}' for x in base_qps))
        output['results'][str(ef)]={'baseline_qps_by_round':base_qps,
                                    'recall10_by_policy': {p:data[(1,p)][ef]['recall10'] for p in POLICIES},
                                    'relative_to_baseline':ratios}
    print()
    for p in POLICIES:
        m=data[(1,p)][EFS[0]]
        print(f'graph {p}: edges={m["edges"]} bytes={m["graph_bytes"]} reachable0={m["reachable0"]}/{m["n"]}')
        if m['reachable0']!=m['n']:print(f'  WARNING: {p} graph not fully reachable.')
    path=directory/'crossover_summary.json'
    if path.exists(): raise FileExistsError(path)
    path.write_text(json.dumps(output,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    print('\nRESULT_FILE',path)

if __name__=='__main__':main()
