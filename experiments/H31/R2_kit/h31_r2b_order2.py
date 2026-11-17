#!/usr/bin/env python3
"""H31-R2 common-searcher audit: RUN SEARCH only; NEVER build or modify graph inputs.

Source contract: ParlayANN a48c6a3 algorithms/bench/neighborsTime.C,
algorithms/utils/check_nn_recall.h and algorithms/vamana/neighbors.h.
"""
import argparse
import datetime as dt
import hashlib
import json
import math
import os
import re
import shutil
import statistics
import struct
import subprocess
import sys
from pathlib import Path

N = 1_000_000
D = 128
NQ = 10_000
ROLES = ('VAMANA', 'STOCK', 'TOP2')
EXPECTED_COMMIT_PREFIX = 'a48c6a3'
FIELD = r'([-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)'
SEARCH_RE = re.compile(
    r'search:\s*Q=(\d+),\s*k=(\d+),\s*limit=(\d+),\s*recall=' + FIELD +
    r',\s*visited=' + FIELD + r',\s*comparisons=' + FIELD +
    r',\s*QPS=' + FIELD + r'(?:,\s*ctime=' + FIELD + r')?', re.I,
)


def sha256(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda: f.read(4 * 1024 * 1024), b''):
            h.update(b)
    return h.hexdigest()


def load_inventory(path):
    inv = json.loads(path.read_text(encoding='utf8'))
    if not isinstance(inv.get('graph_roles'), dict):
        raise ValueError('Missing inventory.graph_roles')
    return inv


def hdr_check(path, expected_n, expected_k, element_bytes, payload_count=1):
    if not path.is_file():
        raise ValueError(f'Missing input {path}')
    with path.open('rb') as f:
        hdr = f.read(8)
    if len(hdr) != 8:
        raise ValueError(f'Short header {path}')
    n, k = struct.unpack('<II', hdr)
    expected = 8 + expected_n * expected_k * element_bytes * payload_count
    if n != expected_n or k != expected_k or path.stat().st_size != expected:
        raise ValueError(f'Header/size invalid {path}: got n={n},k={k},bytes={path.stat().st_size}, wanted {expected_n},{expected_k},{expected}')
    return {'n': n, 'k_or_d': k, 'bytes': expected, 'path': str(path)}


def preflight(args):
    root = args.root.expanduser().resolve()
    invpath = args.inventory.expanduser().resolve(strict=True)
    inv = load_inventory(invpath)
    binary = args.binary.expanduser().resolve(strict=True)
    if not binary.is_file() or not os.access(binary, os.X_OK):
        raise ValueError('ParlayANN executable unavailable or non-executable: ' + str(binary))
    if not shutil.which('taskset'):
        raise ValueError('taskset not found; refusing unpinned cross-graph benchmark')
    cpus = os.sched_getaffinity(0) if hasattr(os, 'sched_getaffinity') else {0}
    if args.cpu not in cpus:
        raise ValueError(f'CPU {args.cpu} unavailable in affinity={sorted(cpus)}; choose --cpu inside this set')
    dataset = {
        'base': hdr_check(root / 'data/sift1m.fbin', N, D, 4),
        'queries': hdr_check(root / 'data/sift1m_queries.fbin', NQ, D, 4),
        # ParlayANN groundTruth<uint>: contiguous uint32 IDs + float32 distances.
        'gt': hdr_check(root / 'data/sift1m_gt.ibin', NQ, 100, 4, payload_count=2),
    }
    graphs = {}
    for role in ROLES:
        item = inv['graph_roles'].get(role)
        if not isinstance(item, dict):
            raise ValueError(f'Missing graph inventory role {role}')
        path = Path(item['path']).expanduser().resolve(strict=True)
        if not path.is_file():
            raise ValueError(f'Graph path is not file {role}: {path}')
        digest = sha256(path)
        if digest != item.get('sha256'):
            raise ValueError(f'SHA256 mismatch {role}: H31-R0={item.get("sha256")}, actual={digest}')
        if path.stat().st_size != item.get('bytes'):
            raise ValueError(f'Graph size changed {role}')
        graphs[role] = {'path': str(path), 'sha256': digest, 'bytes': path.stat().st_size,
                        'edges': item.get('directed_edges'), 'max_degree': item.get('max_degree')}
    if len({x['path'] for x in graphs.values()}) != 3:
        raise ValueError('Graph paths must be unique')
    git = subprocess.run(['git', '-C', str(root / 'src/ParlayANN'), 'rev-parse', 'HEAD'],
                         stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, check=False)
    actual_commit = git.stdout.strip() if git.returncode == 0 else 'UNKNOWN'
    if actual_commit != 'UNKNOWN' and not actual_commit.startswith(EXPECTED_COMMIT_PREFIX):
        print('WARNING: ParlayANN source HEAD is not a48c6a3; binary could differ from pinned source.', file=sys.stderr)
    return {'inventory': str(invpath), 'graphs': graphs, 'data': dataset,
            'binary': str(binary), 'binary_sha256': sha256(binary),
            'parlayann_git_head': actual_commit,
            'host_cpu_affinity_available': sorted(cpus), 'cpu_selected': args.cpu,
            'gt_semantic_exactness': 'NOT_RECOMPUTED; H31-R0b checked finite ID/distance and nondecreasing rows'}


def parse_output(output, q, k=10, repeats=5):
    rows = []
    for m in SEARCH_RE.finditer(output):
        r = {'q': int(m[1]), 'k': int(m[2]), 'limit': int(m[3]), 'recall': float(m[4]),
             'visited': float(m[5]), 'comparisons': float(m[6]), 'qps': float(m[7])}
        if r['q'] != q or r['k'] != k:
            raise ValueError(f'Unexpected verbose search Q/k: {r}')
        if not (0 <= r['recall'] <= 1 and 0 < r['qps'] and
                r['visited'] >= 0 and r['comparisons'] >= 0 and
                all(math.isfinite(v) for v in (r['recall'], r['qps'],r['visited'],r['comparisons']))):
            raise ValueError(f'Invalid search metric: {r}')
        rows.append(r)
    if len(rows) != repeats:
        raise ValueError(f'Expected {repeats} `search:` lines for -Q {q}; found {len(rows)}. Check log / binary version.')
    return rows


def summary_row(role, q, rows):
    return {'role': role, 'Q': q, 'repeats': len(rows),
            'recall_min': min(x['recall'] for x in rows),
            'recall_max': max(x['recall'] for x in rows),
            'recall_median': statistics.median(x['recall'] for x in rows),
            'qps_median': statistics.median(x['qps'] for x in rows),
            'qps_min': min(x['qps'] for x in rows), 'qps_max': max(x['qps'] for x in rows),
            'visited_median': statistics.median(x['visited'] for x in rows),
            'comparisons_median': statistics.median(x['comparisons'] for x in rows)}


def run(args):
    gate = preflight(args)
    qs = [int(x) for x in args.qs.split(',')]
    if not qs or len(qs) != len(set(qs)) or any(x < 10 or x > 1000 for x in qs):
        raise ValueError('--qs must be unique comma-separated Q≥10 and ≤1000')
    if args.mode == 'preflight':
        print('H31R2_PREFLIGHT_PASS: all three graph hashes and all dataset headers match; source flags read-only')
        print('SEARCHER=' + gate['binary'])
        print('BINARY_SHA256=' + gate['binary_sha256'])
        print('PARLAYANN_HEAD=' + gate['parlayann_git_head'])
        print('QS=' + ','.join(map(str,qs)) + '  K=10  WORKERS=1  REPEATS_INTERNAL=5  CPU=' + str(args.cpu))
        return
    out_base = args.root.expanduser().resolve() / 'experiments/H31'
    out_base.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    out = out_base / ('H31_R2_' + stamp)
    out.mkdir(mode=0o755, exist_ok=False)
    env = os.environ.copy()
    env['PARLAY_NUM_THREADS'] = '1'
    env['OMP_NUM_THREADS'] = '1'
    env['OPENBLAS_NUM_THREADS'] = '1'
    env['MKL_NUM_THREADS'] = '1'
    rows = []
    runs = []
    (out / 'h31_r2_preflight.json').write_text(json.dumps(gate, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    for qi, q in enumerate(qs):
        roles = ('STOCK', 'TOP2', 'VAMANA')
        for role in roles:
            graph = gate['graphs'][role]['path']
            cmd = ['taskset', '-c', str(args.cpu), gate['binary'],
                   '-base_path', gate['data']['base']['path'],
                   '-query_path', gate['data']['queries']['path'],
                   '-gt_path', gate['data']['gt']['path'],
                   '-graph_path', graph,
                   '-data_type', 'float', '-dist_func', 'Euclidian', '-file_type', 'bin',
                   '-k', '10', '-Q', str(q), '-R', '32', '-L', '64', '-alpha', '1.2',
                   '-verbose']
            logfile = out / f'{role.lower()}_Q{q}.log'
            print(f'RUN: {role} Q={q} (5 internal query repetitions); log={logfile}', flush=True)
            rec = {'role': role, 'Q': q, 'cmd': cmd, 'log': str(logfile)}
            # Record before executing: partial results remain inspectable if a run fails.
            runs.append(rec)
            (out / 'h31_r2_runs.json').write_text(json.dumps(runs, indent=2) + '\n', encoding='utf8')
            try:
                p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                   text=True, errors='replace', timeout=args.timeout, env=env, check=False)
            except subprocess.TimeoutExpired as e:
                logfile.write_text(str(e.output) if e.output else 'TIMEOUT', encoding='utf8')
                raise RuntimeError(f'Timed out {role} Q{q}; see {logfile}')
            logfile.write_text(p.stdout, encoding='utf8')
            rec['returncode'] = p.returncode
            if p.returncode:
                raise RuntimeError(f'Search failed {role} Q{q}, exit={p.returncode}. Inspect {logfile}')
            rec['metrics'] = parse_output(p.stdout, q)
            rows.append(summary_row(role, q, rec['metrics']))
            (out / 'h31_r2_runs.json').write_text(json.dumps(runs, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    report = {'preflight': gate, 'parameters': {'qs': qs, 'k': 10, 'workers': 1, 'cpu': args.cpu,
              'repeats_per_graph_q': 5, 'search_binary_source': 'ParlayANN a48c6a3 expected',
              'search_mode': 'Parlay default non-quantized beam search',
              'graph_budget_matched': False,
              'note': 'Fixed Q != fixed recall; BFS != beam hops; intra-query parallelism NOT TESTED'},
              'rows': sorted(rows, key=lambda x: (x['Q'], ROLES.index(x['role'])))}
    (out / 'h31_r2_results.json').write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n', encoding='utf8')
    lines = ['H31-R2 SAME SEARCHER SIFT1M 10k queries, single worker, fixed Q=... (no BUILD)',
             'SOURCE_SHA256_MATCH_H31_R0=PASS for all graphs; SIFT1M n,d and GT header/length pass',
             'GRAPH BUDGETS DIFFER: Vamana ~114.57MB, PiPNN ~95.17MB; NOT MATCHED PARETO PROOF',
             'Q      ROLE      RECALL@10       QPS_MED5      VISITED_MED5     CMP_MED5      RECALL_RANGE']
    for r in report['rows']:
        lines.append(f"{r['Q']:<6} {r['role']:<8} {r['recall_median']:<15.6f} {r['qps_median']:<13.2f} "
                     f"{r['visited_median']:<16.2f} {r['comparisons_median']:<13.2f} "
                     f"{r['recall_min']:.6f}..{r['recall_max']:.6f}")
    lines += ['NOTE: matched Recall and graph bytes not enforced; no claims of algorithmic novelty.',
              'NO NEW BUILD, NO GRAPH MODIFICATION, NO INTRA-QUERY PARALLEL MEASUREMENT.',
              'H31R2_DONE=' + str(out)]
    (out / 'h31_r2_summary.txt').write_text('\n'.join(lines) + '\n', encoding='utf8')
    print('\n'.join(lines))


def selftest():
    good = ('some setup\n' + '\n'.join(
        f'search: Q=100, k=10, limit=0, recall=0.992, visited=140.0, comparisons=2010.5, QPS={2000 + i}, ctime=10.2'
        for i in range(5)) + '\n')
    parsed = parse_output(good, 100)
    assert len(parsed) == 5 and summary_row('VAMANA', 100, parsed)['qps_median'] == 2002
    for malformed in (good.replace('Q=100', 'Q=120', 1), good.replace('QPS=2000', 'QPS=-7'), good.replace('recall=0.992', 'recall=1.992', 1), good.rsplit('search:', 1)[0]):
        try:
            parse_output(malformed, 100)
        except ValueError:
            pass
        else:
            raise AssertionError('Malformed metric log unexpectedly accepted')
    # Synthetic Parlay GT includes consecutive uint32 IDs and float32 distances.
    import tempfile
    with tempfile.TemporaryDirectory(prefix='h31r2_selftest_') as t:
        p = Path(t) / 'tiny.ibin'
        p.write_bytes(struct.pack('<II', 2, 3) + struct.pack('<6I', *range(6)) + struct.pack('<6f', *range(6)))
        got = hdr_check(p, 2, 3, 4, 2)
        assert got['bytes'] == 56
        p.write_bytes(p.read_bytes()[:-4])
        try:
            hdr_check(p, 2, 3, 4, 2)
        except ValueError:
            pass
        else:
            raise AssertionError('Truncated GT unexpectedly accepted')
    print('H31R2_SEARCH_LOG_AND_GT_SCHEMA_SELFTEST_PASS (synthetic; real search NOT run)')


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--mode', choices=('selftest', 'preflight', 'run'), required=True)
    ap.add_argument('--root', type=Path, default=Path('~/ann-task-a'))
    ap.add_argument('--inventory', type=Path,
                    default=Path('~/ann-task-a/experiments/H31/H31_R0_20261028_003956/h31_r0_inventory.json'))
    ap.add_argument('--binary', type=Path,
                    default=Path('~/ann-task-a/src/ParlayANN/algorithms/vamana/neighbors'))
    ap.add_argument('--cpu', type=int, default=0)
    ap.add_argument('--qs', default='80,100,108,112,120,140,160,180,200')
    ap.add_argument('--timeout', type=int, default=480, help='Hard safety timeout per single external search process in seconds')
    args = ap.parse_args()
    try:
        if args.mode == 'selftest':
            selftest()
        else:
            run(args)
    except Exception as e:
        print(f'H31R2_FAIL_CLOSED: {type(e).__name__}: {e}', file=sys.stderr)
        sys.exit(2)

if __name__ == '__main__':
    main()
