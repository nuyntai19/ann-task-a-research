#!/usr/bin/env python3
"""H32-R47-R5 v2: fixed-graph native/traced Q sensitivity audit.

Q80/Q120/Q160 were already run. Use `audit` to analyze their saved traces;
do NOT rerun SEARCH. The v2 correction reads ParlayANN groundTruth .ibin files
as an ID block followed by a separate float32 distance block.

Requires two existing scripts in ~/ann-task-a:
  ann_task_a_r47_r3_witness_audit.py
  ann_task_a_r47_r4_topk_parity_v2.py
"""
import argparse
import json
import os
from pathlib import Path
import re
import struct
import subprocess
import sys

from ann_task_a_r47_r3_witness_audit import read_events
from ann_task_a_r47_r4_topk_parity_v2 import (
    Fbin, exact_integer_l2, reconstruct_r47, hash_file
)

PIN = 'd497f6d19fff4b7db6436f960d036755e375be92483c03ec0b9ed61968d17bef'
ROOT = Path('experiments/H47')
GRAPH = Path('experiments/H32/H32_R26a_pool_20261029_172452_132314/dump.graph')
NATIVE = Path('src/ParlayANN/algorithms/vamana/neighbors')
TRACE = Path('experiments/H47/ParlayANN-native-decision-trace/algorithms/vamana/neighbors')
BASE = Path('data/sift1m.fbin')
QUERIES = Path('data/sift1m_queries.fbin')
GT = Path('data/sift1m_gt.ibin')
QS = (80, 100, 120, 160)
NEW_QS = (80, 120, 160)
METRICS = re.compile(
    r'search: Q=(\d+), k=(\d+), limit=(\d+), recall=([^,]+), '
    r'visited=([^,]+), comparisons=([^,]+), QPS='
)


class Ibin:
    """Read ParlayANN's groundTruth<>::save binary layout.

    Bytes: [uint32 n][uint32 dim]
           [uint32 IDs of shape n x dim]
           [float32 distances of shape n x dim].
    Only the IDs block is needed for the analysis.
    """
    def __init__(self, path):
        self.fd = path.open('rb')
        header = self.fd.read(8)
        if len(header) != 8:
            raise ValueError('Truncated GT ibin')
        self.n, self.dim = struct.unpack('<II', header)
        if self.n != 10000 or self.dim < 10 or self.dim > 1000:
            raise ValueError(f'GT ibin shape mismatch: {self.n} x {self.dim}')
        # v2 FIX: native file contains BOTH IDs and float32 distances.
        expected_bytes = 8 + self.n * self.dim * (4 + 4)
        actual_bytes = path.stat().st_size
        if actual_bytes != expected_bytes:
            raise ValueError(
                f'GT ibin file size mismatch: actual={actual_bytes} bytes, '
                f'expected={expected_bytes} bytes for ParlayANN '
                f'{self.n}x{self.dim} IDs plus float32 distances'
            )

    def row(self, query_id):
        self.fd.seek(8 + query_id * self.dim * 4)
        raw = self.fd.read(self.dim * 4)
        if len(raw) != self.dim * 4:
            raise ValueError('Truncated GT row')
        ids = struct.unpack(f'<{self.dim}I', raw)
        if any(id_ >= 1000000 for id_ in ids):
            raise ValueError('Bad GT id')
        return ids

    def close(self):
        self.fd.close()


def checked_inputs(manifest):
    if not GRAPH.is_file():
        raise ValueError(f'Missing pinned graph: {GRAPH}')
    actual_sha = hash_file(GRAPH)
    if actual_sha != PIN or manifest['protocol']['graph_sha256'] != PIN:
        raise ValueError(f'Graph SHA mismatch: {actual_sha}')
    if sorted(set(manifest['native_fail_query_ids'])) != sorted(manifest['native_fail_query_ids']):
        raise ValueError('Query IDs should be unique and sorted in manifest')
    if len(manifest['native_fail_query_ids']) != 17:
        raise ValueError('Expected 17 pre-selected native-failing queries')
    for path in (BASE, QUERIES, GT):
        if not path.is_file():
            raise ValueError(f'Missing data input: {path}')
    for path in (NATIVE, TRACE):
        if not path.is_file() or not os.access(path, os.X_OK):
            raise ValueError(f'Missing executable: {path}')


def filepaths(q):
    prefix = ROOT / f'r47_r5_q{q:03d}'
    return (Path(str(prefix) + '_baseline.stdout'),
            Path(str(prefix) + '_baseline.stderr'),
            Path(str(prefix) + '_traced.stdout'),
            Path(str(prefix) + '_events.stderr'))


def metrics(path, q):
    if not path.is_file():
        raise ValueError(f'Missing search metrics: {path}')
    result = METRICS.findall(path.read_text())
    if len(result) != 5:
        raise ValueError(f'{path}: expected 5 search metrics; got {len(result)}')
    parsed = []
    for got_q, k, limit, recall, visited, comparisons in result:
        if int(got_q) != q or int(k) != 10 or int(limit) != 1_000_000:
            raise ValueError(
                f'{path}: bad search protocol Q={got_q},k={k},limit={limit}'
            )
        parsed.append((int(got_q), int(k), int(limit),
                       float(recall), float(visited), float(comparisons)))
    if len(set(parsed)) != 1:
        raise ValueError(f'{path}: 5 repeats have different aggregate metrics')
    return parsed


def run_cmd(binary, args, out, err):
    env = dict(os.environ)
    env.update(PARLAY_NUM_THREADS='1', OMP_NUM_THREADS='1',
               OPENBLAS_NUM_THREADS='1')
    with out.open('w', encoding='utf-8') as o, err.open('w', encoding='utf-8') as e:
        subprocess.run([str(binary.resolve()), *args], stdout=o, stderr=e,
                       env=env, check=True)


def run():
    # Retained only for compatibility; not needed when Q80/Q120/Q160 exist.
    manifest = json.loads((ROOT / 'r47_target_manifest.json').read_text())
    checked_inputs(manifest)
    ROOT.mkdir(parents=True, exist_ok=True)
    output_paths = [p for q in NEW_QS for p in filepaths(q)]
    already = [str(p) for p in output_paths if p.exists()]
    if already:
        raise ValueError('Refusing to overwrite existing outputs: ' + ', '.join(already))
    print('R47_R5_RUN_START; graph SHA and 17-query manifest PASS', flush=True)
    for q in NEW_QS:
        baseout, baseerr, traceout, traceerr = filepaths(q)
        flags = ['-data_type', 'float', '-dist_func', 'Euclidian',
                 '-base_path', str(BASE.resolve()),
                 '-query_path', str(QUERIES.resolve()),
                 '-gt_path', str(GT.resolve()),
                 '-graph_path', str(GRAPH.resolve()),
                 '-Q', str(q), '-k', '10', '-verbose']
        print(f'RUNNING Q{q} native baseline (10k heldout x 5)', flush=True)
        run_cmd(NATIVE, flags, baseout, baseerr)
        print(f'RUNNING Q{q} instrumented trace', flush=True)
        run_cmd(TRACE, flags, traceout, traceerr)
        if metrics(baseout, q) != metrics(traceout, q):
            raise ValueError(f'Q{q}: aggregate parity failed; do not accept trace')
        print(f'R47_R5_Q{q}_AGGREGATE_PARITY_PASS', flush=True)
    print('R47_R5_ALL_RUNS_COMPLETED', flush=True)


def reconstruct_one(events, qid, q, base, queries):
    rec = reconstruct_r47(events, qid, beam_size=q)
    qv = queries.vector(qid)
    values = []
    for id_, printed in rec['beam_distances_printed'].items():
        true = exact_integer_l2(qv, base.vector(id_))
        if abs(true - printed) > max(.51, abs(true) * 1.e-5):
            raise ValueError(f'q={qid} Q{q} distance mismatch on vertex {id_}')
        values.append((true, id_))
    return tuple(idx for _, idx in sorted(values)), rec


def audit():
    manifest = json.loads((ROOT / 'r47_target_manifest.json').read_text())
    checked_inputs(manifest)
    qids = sorted(manifest['native_fail_query_ids'])
    expected = set(qids)
    r46 = json.loads(Path(
        'experiments/H46/r46_native_miss_reclassified.json').read_text())
    old = json.loads((ROOT / 'r47_r4_topk_parity.json').read_text())
    if old['audit'] != 'R47_R4_NATIVE_TOPK_ID_PARITY_PASS' or old['queries'] != 17:
        raise ValueError('R47-R4 TOP10 parity proof missing')
    if r46['counts']['native_deficit'] != 20 or r46['counts']['queries_native_miss'] != 17:
        raise ValueError('R46 result mismatch')
    old_topk = {int(item['query_id']): tuple(item['top10'])
                for item in old['per_query']}
    if set(old_topk) != expected:
        raise ValueError('R47-R4 query IDs mismatch')
    targets = manifest['twohop_targets'] + manifest['non_twohop_targets']
    if len(targets) != 20:
        raise ValueError('Expected 20 pinned GT targets')
    rows_by_q = {q: {} for q in qids}
    base = Fbin(BASE)
    queries = Fbin(QUERIES)
    gt = Ibin(GT)
    try:
        if (base.n, base.dim, queries.n, queries.dim) != (1000000, 128, 10000, 128):
            raise ValueError('SIFT1M dataset shape mismatch')
        for q in QS:
            if q == 100:
                # Reuse existing Q100, already verified at ID level by R47-R4.
                events_file = ROOT / 'r47_events.stderr'
                native_metrics_file = ROOT / 'r47_baseline.stdout'
                trace_metrics_file = ROOT / 'r47_traced.stdout'
            else:
                native_metrics_file, _, trace_metrics_file, events_file = filepaths(q)
            native = metrics(native_metrics_file, q)
            traced = metrics(trace_metrics_file, q)
            if native != traced:
                raise ValueError(f'Aggregate parity failed at Q{q}')
            print(f'R47_R5_Q{q}_AGGREGATE_PARITY_PASS '
                  f'recall={native[0][3]} visited={native[0][4]} '
                  f'comparisons={native[0][5]}', flush=True)
            events = read_events(events_file, expected, expected_repeats=5)
            for query_id in qids:
                beam, reconstructed = reconstruct_one(
                    events[query_id], query_id, q, base, queries)
                top10 = beam[:10]
                if len(top10) != 10 or len(set(top10)) != 10:
                    raise ValueError(f'q={query_id} Q{q} top10 invalid')
                if q == 100 and top10 != old_topk[query_id]:
                    raise ValueError(f'Q100 R47-R4 Top10 mismatch query={query_id}')
                if q == 100:
                    expected_visits = {
                        int(item['query_id']): item['visited_count']
                        for item in r46['missed_query_details']
                        if item['native_deficit'] > 0
                    }[query_id]
                    if len(reconstructed['visited_ids']) != expected_visits:
                        raise ValueError('Q100 visited count mismatch R46')
                gt_ids = gt.row(query_id)
                true10 = set(gt_ids[:10])
                kth = exact_integer_l2(
                    queries.vector(query_id), base.vector(gt_ids[9]))
                tie_ok = set(gt_ids[:10])
                for id_ in gt_ids[10:]:
                    if exact_integer_l2(queries.vector(query_id), base.vector(id_)) == kth:
                        tie_ok.add(id_)
                strict_hit = len(set(top10) & true10)
                native_hit = len(set(top10) & tie_ok)
                if not 0 <= strict_hit <= native_hit <= 10:
                    raise ValueError('Bad strict vs native hit invariant')
                rows_by_q[query_id][q] = {
                    'top10': list(top10), 'strict_hits': strict_hit,
                    'native_tie_hits': native_hit,
                    'native_deficit': 10-native_hit,
                    'visited_count': len(reconstructed['visited_ids']),
                    'comparisons': reconstructed['comparisons']
                }
        deficit100 = sum(rows_by_q[id_][100]['native_deficit'] for id_ in qids)
        if deficit100 != 20:
            raise ValueError(f'Q100 native deficits {deficit100} != R46 20')
        print('R47_R5_Q100_NATIVE_DEFICIT_REPLICATION_PASS 20/170')
        for q in QS:
            total = sum(rows_by_q[id_][q]['native_deficit'] for id_ in qids)
            failed = sum(rows_by_q[id_][q]['native_deficit'] > 0 for id_ in qids)
            avgvis = sum(rows_by_q[id_][q]['visited_count'] for id_ in qids)/len(qids)
            avgcmp = sum(rows_by_q[id_][q]['comparisons'] for id_ in qids)/len(qids)
            recovered = sum(
                int(t['gt_id']) in rows_by_q[int(t['query_id'])][q]['top10']
                for t in targets
            )
            print(f'R47_R5_Q{q} failing_queries={failed}/17 '
                  f'native_missing_slots={total}/170 '
                  f'recovered_original_strict_targets={recovered}/20 '
                  f'mean_visited={avgvis:.1f} mean_comparisons={avgcmp:.1f}')
        print('R47_R5_TARGET_LEVEL_DETAIL')
        for t in sorted(targets, key=lambda x:(x['query_id'],x['gt_id'])):
            id_, gt_id = int(t['query_id']), int(t['gt_id'])
            bits = ''.join('1' if gt_id in rows_by_q[id_][q]['top10'] else '0'
                           for q in QS)
            print(f'query={id_} target={gt_id} '
                  f'twohop={int(t["graph_twohop"])} Q80,100,120,160={bits}')
        result = {
            'audit': 'R47_R5_FIXED_GRAPH_Q_SENSITIVITY_PASS',
            'graph_sha256': PIN,
            'query_selection': '17 Q100-native failing queries from R46; selection-conditioned',
            'q_values': list(QS), 'queries': len(qids),
            'old_missing_gt_targets': targets,
            'per_query': [{'query_id': id_, 'by_q': rows_by_q[id_]} for id_ in qids],
            'limits': [
                'Q80/120/160 Top10 recovered from trace; no independent per-query native ID parity at those Q',
                'Baseline vs trace aggregate metric parity at each Q only',
                'Increasing Q on same graph is search control, not evidence for a new graph builder',
                'Tie handling uses exact integer-coordinate SIFT L2 under 2^24'
            ]
        }
        path = ROOT / 'r47_r5_q_sensitivity.json'
        if path.exists():
            raise ValueError(f'Output exists; refusing overwrite: {path}')
        path.write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n')
        print('R47_R5_FIXED_GRAPH_Q_SENSITIVITY_PASS')
        print('OUTPUT', path)
    finally:
        gt.close()
        base.close()
        queries.close()


def selftest():
    from tempfile import TemporaryDirectory
    assert exact_integer_l2((1,2),(4,6)) == 25
    with TemporaryDirectory() as td:
        p = Path(td) / 'metrics.stdout'
        good = ('search: Q=80, k=10, limit=1000000, recall=0.982, '
                'visited=140, comparisons=2000, QPS=100\n')
        p.write_text(good * 5)
        assert len(metrics(p, 80)) == 5
        try:
            metrics(p, 160)
            raise AssertionError('Expected Q mismatch')
        except ValueError:
            pass
        p.write_text(good * 4)
        try:
            metrics(p, 80)
            raise AssertionError('Expected 5-repeat validation fail')
        except ValueError:
            pass
        gtpath = Path(td) / 'gt.ibin'
        ids_blob = struct.pack('<10I', *range(10)) * 10000
        dists_blob = struct.pack('<10f', *([0.0] * 10)) * 10000
        gtpath.write_bytes(struct.pack('<II', 10000, 10) + ids_blob + dists_blob)
        parsed = Ibin(gtpath)
        assert parsed.row(0) == tuple(range(10))
        assert parsed.row(7) == tuple(range(10))
        assert parsed.row(9999) == tuple(range(10))
        parsed.close()
        # Truncated file must be rejected.
        gtpath.write_bytes(struct.pack('<II', 10000, 10) + ids_blob)
        try:
            Ibin(gtpath)
            raise AssertionError('Missing distance block was accepted')
        except ValueError as e:
            assert 'file size mismatch' in str(e)
    print('R47_R5_V2_SELFTEST_PASS: 5 repeats, Q check, '
          'GT IDs+distances layout, integer L2')


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('action', choices=['selftest', 'run', 'audit'])
    args = ap.parse_args()
    try:
        if args.action == 'selftest':
            selftest()
        elif args.action == 'run':
            run()
        else:
            audit()
    except (OSError, ValueError, KeyError, AssertionError,
            subprocess.CalledProcessError) as e:
        print('R47_R5_FAIL:', e, file=sys.stderr)
        sys.exit(2)


if __name__ == '__main__':
    main()
