#!/usr/bin/env python3
"""H31-R1, read-only directed BFS from common ParlayANN search entry 0.
No BUILD or SEARCH, no graph mutation; BFS hops != ANN beam-search hops.
Uses only Python standard library, checks each graph against SHA in H31-R0 inventory.
"""
from __future__ import annotations
import argparse
from array import array
import datetime as dt
import hashlib
import json
import mmap
from pathlib import Path
import struct
import sys
import tempfile

ROLES = ('VAMANA', 'STOCK', 'TOP2')
DEFAULT_ROOT = Path.home() / 'ann-task-a'


def file_sha256(path: Path) -> str:
    dig = hashlib.sha256()
    with path.open('rb') as f:
        for ch in iter(lambda: f.read(4 * 1024 * 1024), b''):
            dig.update(ch)
    return dig.hexdigest()


def percentile_hops(level_counts: list[int], share: float) -> int:
    if not level_counts or sum(level_counts) == 0:
        raise ValueError('No BFS levels')
    total = sum(level_counts)
    target = int((total * share) + (1 - 1e-12))  # ceil for positive fractions
    cum = 0
    for hop, count in enumerate(level_counts):
        cum += count
        if cum >= target:
            return hop
    raise AssertionError('Bad level counts')


def audit_one(path: Path, expected: dict, entry: int, expected_n: int = 1_000_000) -> dict:
    path = path.expanduser().resolve(strict=True)
    if not path.is_file():
        raise ValueError(f'Graph path is not a regular file: {path}')
    exp_path = Path(expected.get('path', '')).expanduser().resolve(strict=True)
    if path != exp_path:
        raise ValueError(f'Inventory/selected graph path mismatch: {path} != {exp_path}')
    actual_sha = file_sha256(path)
    want_sha = expected.get('sha256', '')
    if not want_sha or want_sha.lower() != actual_sha:
        raise ValueError(f'GRAPH_SHA_MISMATCH for {path}: {actual_sha} != {want_sha}')
    size = path.stat().st_size
    if size < 12 or size % 4:
        raise ValueError(f'Invalid size/alignment: {size} for {path}')
    if sys.byteorder != 'little':
        raise RuntimeError('This reader requires little-endian host; stop without proceeding')

    with path.open('rb') as f, mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mm:
        n, max_degree = struct.unpack_from('<II', mm, 0)
        if n != expected_n or n != expected.get('n'):
            raise ValueError(f'N mismatch, got {n}, expected {expected_n} and inventory {expected.get("n")}')
        if not (1 <= max_degree <= 4096):
            raise ValueError(f'Bad maxdegree: {max_degree}')
        if n <= entry or entry < 0:
            raise ValueError(f'Entry {entry} outside 0..{n-1}')
        neighbor_base = 8 + 4 * n
        if size < neighbor_base:
            raise ValueError('Truncated graph degrees')
        deg = array('I')
        deg.frombytes(mm[8:neighbor_base])
        offsets = array('Q')
        offsets.append(neighbor_base)
        e = 0
        for d in deg:
            if d > max_degree:
                raise ValueError(f'Degree {d} exceeds max degree {max_degree}')
            e += d
            offsets.append(neighbor_base + e * 4)
        if offsets[-1] != size:
            raise ValueError(f'Graph length {size} inconsistent with degree prefix {offsets[-1]}')
        if e != expected.get('directed_edge_occurrences'):
            raise ValueError(f'Edge count {e} differs from inventory {expected.get("directed_edge_occurrences")}')

        # Validate BFS over neighbor IDs; each reachable node scanned exactly once.
        seen = bytearray(n)
        queue = array('I', [entry])
        seen[entry] = 1
        head = 0
        scanned_edges = 0
        levels: list[int] = []
        while head < len(queue):
            end_of_level = len(queue)
            levels.append(end_of_level - head)
            while head < end_of_level:
                u = queue[head]
                head += 1
                k = deg[u]
                scanned_edges += k
                at = offsets[u]
                # k<=4096, pack small neighbors at a time; avoid materializing all M edges.
                if k:
                    nbrs = struct.unpack_from('<' + str(k) + 'I', mm, at)
                    for v in nbrs:
                        if v >= n:
                            raise ValueError(f'Invalid target ID {v} in row {u}')
                        if not seen[v]:
                            seen[v] = 1
                            queue.append(v)
        reachable = len(queue)
        unreachable = n - reachable
        unseen_ids = [i for i, val in enumerate(seen) if not val][:32]
        if sum(levels) != reachable:
            raise AssertionError('BFS level counts do not sum to reachable')
        return {
            'file': str(path), 'sha256_verified_against_h31_r0': actual_sha,
            'n': n, 'edges': e, 'max_degree': max_degree, 'entry': entry,
            'reachable': reachable, 'unreachable': unreachable,
            'reachable_fraction': round(reachable / n, 8),
            'max_shortest_hops_from_entry': len(levels) - 1,
            'p50_shortest_hops_reachable': percentile_hops(levels, 0.5),
            'p95_shortest_hops_reachable': percentile_hops(levels, 0.95),
            'p99_shortest_hops_reachable': percentile_hops(levels, 0.99),
            'bfs_frontier_counts_by_hop': levels,
            'edges_scanned_from_reachable_sources': scanned_edges,
            'unreachable_node_ids_first_32': unseen_ids,
            'warning': 'Directed BFS from entry=0, not strongly connected components, greedy ANN path lengths, Recall, QPS or graph quality proof.'
        }


def inventory_load(path: Path) -> dict:
    data = json.loads(path.read_text(encoding='utf-8'))
    if data.get('study') != 'H31_R0_EXISTING_GRAPH_AUDIT':
        raise ValueError('Not an H31-R0 audit inventory')
    roles = data.get('graph_roles')
    if not isinstance(roles, dict) or set(roles) != set(ROLES):
        raise ValueError('Inventory must have exactly VAMANA, STOCK, TOP2')
    if data.get('gates', {}).get('graph_file_schema') != 'PASS':
        raise ValueError('Inventory graph schema gate not PASS')
    for r in ROLES:
        if not (roles[r].get('sha256') and roles[r].get('path')):
            raise ValueError(f'Inventory missing required graph path/hash for {r}')
    return data


def synthetic_graph(path: Path, rows: list[list[int]], maxdeg: int) -> Path:
    if any(len(x) > maxdeg for x in rows):
        raise ValueError('Invalid synthetic rows')
    vals = [len(rows), maxdeg] + [len(x) for x in rows] + [x for row in rows for x in row]
    path.write_bytes(struct.pack('<' + 'I' * len(vals), *vals))
    return path


def selftest() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        # Two disconnected SCCs, no zero-indegree vertices. Shows indeg0 != unreachable.
        g = synthetic_graph(root / 'x.graph', [[1], [2], [0], [4], [3]], 2)
        expected = {'path': str(g), 'sha256': file_sha256(g), 'n': 5, 'directed_edge_occurrences': 5}
        z = audit_one(g, expected, 0, expected_n=5)
        assert (z['reachable'], z['unreachable'], z['max_shortest_hops_from_entry']) == (3, 2, 2), z
        assert z['bfs_frontier_counts_by_hop'] == [1, 1, 1]
        assert z['p50_shortest_hops_reachable'] == 1
        z2 = audit_one(g, expected, 3, expected_n=5)
        assert (z2['reachable'], z2['unreachable']) == (2, 3), z2
        # Positive 0-indegree orphan
        g2 = synthetic_graph(root / 'y.graph', [[1], [2], [], []], 2)
        e2 = {'path': str(g2), 'sha256': file_sha256(g2), 'n': 4, 'directed_edge_occurrences': 2}
        z3 = audit_one(g2, e2, 0, expected_n=4)
        assert (z3['reachable'], z3['unreachable']) == (3, 1), z3
        # No silent source modification: bad sha, truncated file, malformed destination must fail
        tampered = dict(expected, sha256='00' * 32)
        try:
            audit_one(g, tampered, 0, expected_n=5)
        except ValueError as ex:
            assert 'SHA_MISMATCH' in str(ex)
        else:
            raise AssertionError('Bad SHA should be rejected')
        old = g.read_bytes()
        g.write_bytes(old[:-4])
        e_truncated = dict(expected, sha256=file_sha256(g))
        try:
            audit_one(g, e_truncated, 0, expected_n=5)
        except ValueError as ex:
            assert 'inconsistent' in str(ex)
        else:
            raise AssertionError('Truncated graph should be rejected')
        bad = synthetic_graph(root / 'bad.graph', [[1], [5], []], 2)
        e_bad = {'path': str(bad), 'sha256': file_sha256(bad), 'n': 3, 'directed_edge_occurrences': 2}
        try:
            audit_one(bad, e_bad, 0, expected_n=3)
        except ValueError as ex:
            assert 'Invalid target ID' in str(ex)
        else:
            raise AssertionError('Invalid vertex ID should be rejected')
    print('H31R1_BFS_ENTRY_SCHEMA_HASH_SELFTEST_PASS')


def run(inventory_path: Path, outdir: Path | None, entry: int) -> None:
    inv = inventory_load(inventory_path.expanduser().resolve(strict=True))
    stats: dict = {}
    for role in ROLES:
        expected = inv['graph_roles'][role]
        stats[role] = audit_one(Path(expected['path']), expected, entry, expected_n=1_000_000)
    root = Path(inv['host_home_root']).expanduser().resolve(strict=True)
    if outdir is None:
        base = root / 'experiments' / 'H31'
        base.mkdir(parents=True, exist_ok=True)
        folder = Path(tempfile.mkdtemp(prefix='H31_R1_' + dt.datetime.now().strftime('%Y%m%d_%H%M%S') + '_', dir=base))
    else:
        folder = outdir.expanduser().resolve()
        folder.mkdir(parents=True, exist_ok=False)
    data = {
        'study': 'H31_R1_ENTRY0_DIRECTED_REACHABILITY_ONLY',
        'source_inventory': str(inventory_path.expanduser().resolve(strict=True)),
        'entry': entry, 'graph_roles': stats,
        'algorithm': 'unweighted directed BFS from common Vamana searcher entry=0',
        'warnings': [
            'This audit does not run native ANN SEARCH or compute QPS/Recall.',
            'BFS shortest hop count is not greedy-search hop count or distance evaluations.',
            'Cross-method graph budgets differ (R0 Vamana ~27.64M edges; PiPNN ~22.79M).',
            'Graph source hash matches R0 inventory; source/binary/flags/seed still require manifests.',
            'Zero indegree is not equal to unreachable count, nor evidence of a significant Recall difference.'
        ]
    }
    (folder / 'h31_r1_bfs.json').write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    lines = [
        'H31-R1 DIRECTED BFS FROM COMMON SEARCHER ENTRY 0 (READ ONLY, no BUILD/SEARCH)',
        'ROLE             N     EDGES(dir)   REACH0  UNREACH0  BFS_HOPS_MAX  P50_HOPS  P95_HOPS  P99_HOPS',
    ]
    for role in ROLES:
        a = stats[role]
        lines.append(f'{role:<8s} {a["n"]:>9,d} {a["edges"]:>14,d} {a["reachable"]:>9,d} {a["unreachable"]:>9,d} {a["max_shortest_hops_from_entry"]:>13,d} {a["p50_shortest_hops_reachable"]:>9,d} {a["p95_shortest_hops_reachable"]:>9,d} {a["p99_shortest_hops_reachable"]:>9,d}')
    lines.extend([
        'SOURCE_SHA256_MATCH_H31_R0_INVENTORY=PASS for all 3 graphs',
        'BFS from entry 0 only; other entries/SCCs not inferred. BFS hops are NOT greedy/beam ANN hops.',
        'Vamana and PiPNN graph bytes/outdegree differ. NOT an equal-budget Pareto comparison.',
        'NO RECALL, NO QPS, NO NOVELTY CLAIM, NO NEW BUILD.',
        f'H31R1_DONE={folder}'
    ])
    summary = '\n'.join(lines) + '\n'
    (folder / 'h31_r1_summary.txt').write_text(summary, encoding='utf-8')
    print(summary, end='')


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--mode', required=True, choices=['selftest', 'run'])
    ap.add_argument('--inventory', type=Path, help='Exact H31-R0 inventory JSON, mandatory for run')
    ap.add_argument('--entry', type=int, default=0, help='Common ParlayANN search entry. Default 0.')
    ap.add_argument('--outdir', type=Path, default=None, help='Optional new output folder; must not exist')
    ns = ap.parse_args()
    try:
        if ns.mode == 'selftest':
            selftest()
        else:
            if ns.inventory is None:
                raise ValueError('Provide --inventory /exact/H31_R0.../h31_r0_inventory.json')
            if ns.entry != 0:
                raise ValueError('H31-R1 comparison is pre-registered for entry=0; different entry requires separate study')
            run(ns.inventory, ns.outdir, ns.entry)
        return 0
    except (ValueError, OSError, KeyError, RuntimeError, AssertionError) as ex:
        print(f'H31R1_FAIL_CLOSED: {type(ex).__name__}: {ex}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
