#!/usr/bin/env python3
"""G0.3 exploratory: fixed-outdegree swaps, never modifies baseline files.

Oracle methods use a prebuilt f60 graph and must NOT be interpreted as a
construction algorithm with the reported f30 build time.
"""
import argparse
import json
import shutil
import struct
import time
from collections import deque
from pathlib import Path

import numpy as np


def load_graph(path):
    if not path.is_file():
        raise FileNotFoundError(path)
    with path.open('rb') as fh:
        head = fh.read(8)
    if len(head) != 8:
        raise ValueError(f'Invalid graph header: {path}')
    n, maxdeg = struct.unpack('<II', head)
    if not (0 < n <= 100_000_000 and 0 < maxdeg <= 100_000):
        raise ValueError(f'Unexpected graph shape: {n}, {maxdeg}')
    degree = np.memmap(path, dtype='<u4', mode='r', offset=8, shape=n)
    if np.any(degree > maxdeg):
        raise ValueError(f'Degree limit exceeded: {path}')
    offsets = np.empty(n + 1, dtype=np.int64)
    offsets[0] = 0
    np.cumsum(degree, dtype=np.int64, out=offsets[1:])
    m = int(offsets[-1])
    if path.stat().st_size != 8 + 4*n + 4*m:
        raise ValueError(f'Unexpected graph file size: {path}')
    edges = np.memmap(path, dtype='<u4', mode='r', offset=8 + 4*n, shape=m)
    if m and int(edges.max()) >= n:
        raise ValueError(f'Neighbor out of range: {path}')
    return dict(path=path, n=n, maxdeg=maxdeg, degree=degree, offsets=offsets, edges=edges, m=m)


def nbrs(g, v):
    return g['edges'][int(g['offsets'][v]):int(g['offsets'][v+1])]


def read_base(path, expected_n):
    with path.open('rb') as fh:
        head = fh.read(8)
    if len(head) != 8:
        raise ValueError('Invalid base data header')
    n, dim = struct.unpack('<II', head)
    if n != expected_n or not (0 < dim <= 100000):
        raise ValueError(f'Unexpected base shape {(n, dim)}')
    if path.stat().st_size != 8 + n * dim * 4:
        raise ValueError('Invalid .fbin size')
    return np.memmap(path, mode='r', dtype='<f4', offset=8, shape=(n, dim))


def reachability(g):
    n = g['n']
    marked = bytearray(n)
    marked[0] = 1
    queue = deque([0])
    count = 1
    offsets, edges = g['offsets'], g['edges']
    while queue:
        v = queue.popleft()
        for u0 in edges[int(offsets[v]):int(offsets[v+1])]:
            u = int(u0)
            if not marked[u]:
                marked[u] = 1
                count += 1
                queue.append(u)
    return count


def write_variant(dst, source, swaps, check_bfs):
    if dst.exists():
        raise FileExistsError(f'Output already exists (will not overwrite): {dst}')
    shutil.copyfile(source['path'], dst)
    actual = None
    try:
        out = np.memmap(dst, dtype='<u4', mode='r+', offset=8 + 4*source['n'], shape=source['m'])
        for v, old_position, new_neighbor in swaps:
            a = int(source['offsets'][v]) + old_position
            if int(out[a]) == new_neighbor:
                raise ValueError('No-op edge replacement')
            out[a] = new_neighbor
        out.flush()
        del out
        result = load_graph(dst)
        if not np.array_equal(result['degree'], source['degree']):
            raise ValueError('Outdegree changed')
        if result['m'] != source['m'] or dst.stat().st_size != source['path'].stat().st_size:
            raise ValueError('Graph bytes or directed edge count changed')
        changed = int(np.count_nonzero(result['edges'] != source['edges']))
        if changed != len(swaps):
            raise ValueError(f'Expected {len(swaps)} replacements; found {changed}')
        actual = reachability(result) if check_bfs else None
        return changed, actual
    except Exception:
        dst.unlink(missing_ok=True)
        raise


def make_random_2hop(graph, vertices, budget, seed):
    rng = np.random.default_rng(seed)
    swaps = []
    total_attempts = 0
    for vid in vertices:
        v = int(vid)
        a = nbrs(graph, v)
        if len(a) == 0:
            continue
        old = set(map(int, a))
        target = None
        for _ in range(32):
            total_attempts += 1
            parent = int(a[int(rng.integers(len(a)))])
            b = nbrs(graph, parent)
            if not len(b):
                continue
            candidate = int(b[int(rng.integers(len(b)))])
            if candidate != v and candidate not in old:
                target = candidate
                break
        if target is None:
            continue
        pos = int(rng.integers(len(a)))
        swaps.append((v, pos, target))
        if len(swaps) == budget:
            break
    if len(swaps) < budget:
        raise RuntimeError(f'Only {len(swaps)} eligible 2-hop swaps; need {budget}')
    return swaps, dict(twohop_attempts=total_attempts, extra_distance_evals=0)


def eligible_oracle(f30, f60, vertices):
    eligible = []
    for vid in vertices:
        v = int(vid)
        a = nbrs(f30, v)
        b = nbrs(f60, v)
        aset = set(map(int, a))
        bset = set(map(int, b))
        old_positions = [i for i, x in enumerate(a) if int(x) not in bset]
        new_neighbors = [int(x) for x in b if int(x) not in aset and int(x) != v]
        if old_positions and new_neighbors:
            eligible.append((v, old_positions, new_neighbors))
    return eligible


def make_oracle_random(rows, budget, seed):
    rng = np.random.default_rng(seed)
    swaps = []
    for v, positions, candidates in rows[:budget]:
        i = int(rng.integers(len(positions)))
        j = int(rng.integers(len(candidates)))
        swaps.append((v, positions[i], candidates[j]))
    return swaps, dict(extra_distance_evals=0)


def make_oracle_short(rows, budget, graph, base):
    swaps = []
    evaluations = 0
    for number, (v, positions, candidates) in enumerate(rows[:budget], 1):
        a = nbrs(graph, v)
        old_ids = np.asarray([int(a[i]) for i in positions], dtype=np.int64)
        new_ids = np.asarray(candidates, dtype=np.int64)
        center = base[v]
        old_diff = base[old_ids] - center
        new_diff = base[new_ids] - center
        old_dists = np.einsum('ij,ij->i', old_diff, old_diff, optimize=False)
        new_dists = np.einsum('ij,ij->i', new_diff, new_diff, optimize=False)
        # Geometric preference: remove the longest f30-only edge,
        # introduce the shortest f60-only edge. Not guaranteed to help ANN.
        old_pos = positions[int(np.argmax(old_dists))]
        new_neighbor = candidates[int(np.argmin(new_dists))]
        evaluations += len(old_ids) + len(new_ids)
        swaps.append((v, old_pos, new_neighbor))
        if number % 25000 == 0:
            print(f'  Oracle geometry: {number:,}/{budget:,}', flush=True)
    return swaps, dict(extra_distance_evals=int(evaluations))


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--root', type=Path, default=Path.cwd())
    p.add_argument('--budget', type=int, default=100000)
    p.add_argument('--pool-size', type=int, default=250000)
    p.add_argument('--seed', type=int, default=20261023)
    p.add_argument('--skip-bfs', action='store_true', help='Exploratory only; keep BFS enabled for validation')
    args = p.parse_args()
    root = args.root.resolve()
    if args.budget <= 0 or args.pool_size < args.budget:
        p.error('Require 0 < budget <= pool-size')
    f30p = root / 'results/pipnn_sift1m_4t.graph'
    f60p = root / 'results/pipnn_static_sift1m_f60_4t.graph'
    f30, f60 = load_graph(f30p), load_graph(f60p)
    if f30['n'] != f60['n'] or f30['maxdeg'] != f60['maxdeg']:
        raise ValueError('Graph vertices/maxdeg mismatch')
    if args.pool_size > f30['n']:
        p.error('pool-size exceeds graph vertex count')
    outdir = root / 'experiments/G0/results/g03'
    outdir.mkdir(parents=True, exist_ok=True)
    manifest_path = outdir / f'manifest_b{args.budget}_s{args.seed}.json'
    if manifest_path.exists():
        raise FileExistsError(f'Manifest already exists: {manifest_path}; change seed or budget')
    names = ('random_2hop', 'oracle_random', 'oracle_lowdegree', 'oracle_geometry')
    for name in names:
        out = outdir / f'{name}_b{args.budget}_s{args.seed}.graph'
        if out.exists():
            raise FileExistsError(f'Output exists: {out}')
    base = read_base(root / 'data/sift1m.fbin', f30['n'])
    pool = np.random.default_rng(args.seed).permutation(f30['n'])[:args.pool_size]
    print(f'G0.3: n={f30["n"]}, base_degree={f30["m"]/f30["n"]:.3f}, budget={args.budget:,}', flush=True)
    print('Finding f60-only candidates on sampled vertices...', flush=True)
    rows = eligible_oracle(f30, f60, pool)
    print(f'Oracle-eligible: {len(rows):,} / {len(pool):,}', flush=True)
    if len(rows) < args.budget:
        raise RuntimeError('Not enough oracle-eligible sources; increase --pool-size')
    original_rows = rows[:args.budget]
    low_degree_rows = sorted(rows, key=lambda r: int(f30['degree'][r[0]]))[:args.budget]
    methods = {
        'random_2hop': make_random_2hop(f30, pool, args.budget, args.seed + 29),
        'oracle_random': make_oracle_random(original_rows, args.budget, args.seed + 31),
        'oracle_lowdegree': make_oracle_random(low_degree_rows, args.budget, args.seed + 37),
        'oracle_geometry': make_oracle_short(original_rows, args.budget, f30, base),
    }
    manifest = {
        'experiment': 'G0.3 exploratory fixed-outdegree graph-edge swap',
        'warning': 'All oracle policies use FULL f60 graph built beforehand; NOT a cheap G build algorithm',
        'n': f30['n'], 'max_degree': f30['maxdeg'], 'budget': args.budget,
        'seed': args.seed, 'pool_size': args.pool_size,
        'baseline_directed_edges': f30['m'], 'expected_graph_bytes': f30p.stat().st_size,
        'oracle_eligible_pool_count': len(rows),
        'graphs': {'f30': str(f30p), 'f60': str(f60p)},
        'policies': {},
    }
    for name, (swaps, info) in methods.items():
        output = outdir / f'{name}_b{args.budget}_s{args.seed}.graph'
        if len(swaps) != args.budget or len(set(v for v, _, _ in swaps)) != args.budget:
            raise ValueError(f'Duplicate source or wrong budget for {name}')
        print(f'Writing {name}...', flush=True)
        t = time.perf_counter()
        changed, reachable = write_variant(output, f30, swaps, check_bfs=not args.skip_bfs)
        chosen_mean_degree = float(np.mean([int(f30['degree'][v]) for v,_,_ in swaps]))
        manifest['graphs'][name] = str(output)
        manifest['policies'][name] = {
            'directed_edge_replacements': changed,
            'fraction_baseline_edges_replaced': changed / f30['m'],
            'changed_source_vertices': changed,
            'mean_selected_outdegree': chosen_mean_degree,
            'reachable_from_vertex_0': reachable,
            'wall_seconds_including_file_copy_and_bfs': round(time.perf_counter()-t,3),
            'candidate_generation': 'two-hop from f30' if name=='random_2hop' else 'f60-only oracle',
            **info,
        }
        print(f'  PASS {name}: {changed:,} swaps; graph_bytes={output.stat().st_size}; reachable={reachable}', flush=True)
        if reachable is not None and reachable != f30['n']:
            print('  WARNING: reachability degraded; do not treat this as a valid topology improvement', flush=True)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'G0.3 CONSTRUCTION PASS; manifest: {manifest_path}', flush=True)


if __name__ == '__main__':
    main()
