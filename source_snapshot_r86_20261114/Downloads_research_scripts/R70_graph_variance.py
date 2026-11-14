#!/usr/bin/env python3
"""R70: compare within-arm and cross-arm PiPNN graph variability (no writes to graphs)."""
import argparse
from array import array
from itertools import combinations
import json
from pathlib import Path
from statistics import median
import sys


def read_graph(path):
    raw = path.read_bytes()
    if len(raw) < 8 or len(raw) % 4:
        raise ValueError(f"Bad 32-bit graph file size: {path}")
    words = array('I')
    if words.itemsize != 4:
        raise RuntimeError("Requires 32-bit unsigned int")
    words.frombytes(raw)
    if sys.byteorder != 'little':
        words.byteswap()
    n, max_degree = words[0], words[1]
    if n != 100000:
        raise ValueError(f"Expected 100000 nodes, found {n}: {path}")
    if not (1 <= max_degree <= 4096):
        raise ValueError(f"Unreasonable maximum degree {max_degree}: {path}")
    if len(words) < 2 + n:
        raise ValueError(f"Truncated degree table: {path}")
    degrees = words[2:2+n]
    if max(degrees) > max_degree:
        raise ValueError(f"Degree exceeds maximum: {path}")
    total_arcs = sum(degrees)
    if len(words) != 2+n+total_arcs:
        raise ValueError(f"Degree sum disagrees with file length: {path}")
    offsets = [2+n]
    invalid = duplicate = selfloop = 0
    for i, deg in enumerate(degrees):
        end = offsets[-1] + deg
        row = words[offsets[-1]:end]
        invalid += sum(v >= n for v in row)
        duplicate += len(row) - len(set(row))
        selfloop += sum(v == i for v in row)
        offsets.append(end)
    if invalid or duplicate or selfloop:
        raise ValueError(f"Invalid graph {path}: invalid_ids={invalid}, duplicates={duplicate}, selfloops={selfloop}")
    print(f"R70_GRAPH_VALID name={path.name} n={n} maxdeg={max_degree} arcs={total_arcs}", flush=True)
    return dict(path=path, words=words, offsets=offsets, arcs=total_arcs, n=n, max_degree=max_degree)


def compare(a, b):
    wa, oa = a['words'], a['offsets']
    wb, ob = b['words'], b['offsets']
    diff_nodes = only_a = only_b = order_only = 0
    for i in range(a['n']):
        ra = wa[oa[i]:oa[i+1]]
        rb = wb[ob[i]:ob[i+1]]
        if ra == rb:
            continue
        sa, sb = set(ra), set(rb)
        if sa == sb:
            order_only += 1
        else:
            diff_nodes += 1
            only_a += len(sa-sb)
            only_b += len(sb-sa)
    return dict(different_adjacency_nodes=diff_nodes,
                different_order_only_nodes=order_only,
                only_first_arcs=only_a, only_second_arcs=only_b,
                symmetric_difference_over_sum_pct=round(100*(only_a+only_b)/(a['arcs']+b['arcs']), 4))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--pilot', type=Path, required=True)
    parser.add_argument('--repeats', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    names = {
        'stock': [args.pilot/'stock.graph', args.repeats/'02_stock.graph', args.repeats/'03_stock.graph'],
        'tier': [args.pilot/'tier.graph', args.repeats/'01_tier.graph', args.repeats/'04_tier.graph'],
    }
    for paths in names.values():
        for p in paths:
            if not p.is_file():
                parser.error(f"Missing graph: {p}")
    graphs = {}
    for group, paths in names.items():
        for j, p in enumerate(paths):
            graphs[(group, j)] = read_graph(p)
    groups = {'stock-stock': [], 'tier-tier': [], 'stock-tier': []}
    print('R70_GRAPH_VARIANCE_COMPARE_BEGIN', flush=True)
    for (ka, a), (kb, b) in combinations(graphs.items(), 2):
        grp = f'{ka[0]}-{kb[0]}'
        d = compare(a, b)
        entry = dict(group=grp, first=str(a['path']), second=str(b['path']), **d)
        groups[grp].append(entry)
        print(f"R70_GRAPH_VARIANCE_PAIR group={grp} first={a['path'].name} second={b['path'].name} "
              f"diff_nodes={d['different_adjacency_nodes']} only_first={d['only_first_arcs']} "
              f"only_second={d['only_second_arcs']} symmetric_diff_pct={d['symmetric_difference_over_sum_pct']:.4f}", flush=True)
    summary = {}
    for grp, items in groups.items():
        values = [e['symmetric_difference_over_sum_pct'] for e in items]
        nodevalues = [e['different_adjacency_nodes'] for e in items]
        summary[grp] = dict(pair_count=len(items), median_symdiff_pct=median(values),
                            min_symdiff_pct=min(values), max_symdiff_pct=max(values),
                            median_different_nodes=median(nodevalues))
        print(f"R70_GRAPH_VARIANCE_GROUP group={grp} pairs={len(items)} "
              f"median_symdiff_pct={median(values):.4f} range=[{min(values):.4f},{max(values):.4f}] "
              f"median_diff_nodes={median(nodevalues)}", flush=True)
    result = dict(description='PiPNN SIFT100K, 4-thread within-arm vs cross-arm graph comparisons',
                  groups=summary, pairs=groups,
                  caveat='Descriptive only: concurrency and repeated runs may change graph; no Recall or causal attribution.')
    args.out.parent.mkdir(parents=True, exist_ok=True)
    if args.out.exists():
        parser.error(f"Output already exists, preserving it: {args.out}")
    args.out.write_text(json.dumps(result, indent=2, ensure_ascii=False)+'\n', encoding='utf-8')
    print(f'R70_GRAPH_VARIANCE_ANALYSIS_PASS output={args.out}', flush=True)


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print(f'R70_GRAPH_VARIANCE_ANALYSIS_FAIL {type(exc).__name__}: {exc}', file=sys.stderr)
        sys.exit(1)
