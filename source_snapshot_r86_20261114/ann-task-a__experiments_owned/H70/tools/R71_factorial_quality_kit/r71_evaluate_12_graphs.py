#!/usr/bin/env python3
"""R71: audit and search-evaluate 12 existing saved SIFT100K PiPNN graphs.
Read-only to source/graphs; outputs a new run directory and JSON report.
"""
from __future__ import annotations

import argparse
from array import array
from collections import defaultdict
from datetime import datetime
import hashlib
import json
import math
import os
from pathlib import Path
import re
from statistics import median
import subprocess
import sys

VARIANTS = ('A_stock', 'B_h17', 'C_tier', 'D_h17_tier')
BEAMS = (10, 20, 40, 80, 160)
EXPECTED_LABELS = {
    'A_stock': ('STOCK_FLAT_C160', 'STOCK_HIGHWAY'),
    'B_h17': ('STOCK_FLAT_C160', 'H17_PACKED_TOP2'),
    'C_tier': ('TIER_B64_C160', 'STOCK_HIGHWAY'),
    'D_h17_tier': ('TIER_B64_C160', 'H17_PACKED_TOP2'),
}
PATTERN = re.compile(
    r'R70_RECALL_ROW beam=(\d+) recall=([\d.eE+-]+) qps=([\d.eE+-]+) '
    r'avg_cmps=([\d.eE+-]+) avg_visited=([\d.eE+-]+)'
)


def check_file(p: Path, role: str):
    if not p.is_file() or not p.stat().st_size:
        raise ValueError(f'{role} not present/nonempty: {p}')


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open('rb') as f:
        for block in iter(lambda: f.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


def header(p: Path) -> tuple[int, int, int]:
    import struct
    check_file(p, 'dataset')
    with p.open('rb') as f:
        b = f.read(8)
    if len(b) != 8:
        raise ValueError(f'short dataset header: {p}')
    n, dim = struct.unpack('<II', b)
    return n, dim, p.stat().st_size


def manifest_ok(manifest: Path):
    check_file(manifest, 'inputs manifest')
    entries = []
    for line in manifest.read_text().splitlines():
        m = re.match(r'^([0-9a-f]{64})\s+\*?(.+)$', line)
        if not m:
            raise ValueError(f'malformed sha256 manifest: {line}')
        expected, name = m.groups()
        p = Path(name)
        check_file(p, 'manifest file')
        actual = sha256(p)
        if actual != expected:
            raise ValueError(f'INPUT_MUTATED {p}: {actual} != {expected}')
        entries.append({'path': str(p.resolve()), 'sha256': actual})
    if len(entries) != 5:
        raise ValueError('expected exactly 5 manifest entries (dataset + 4 binaries)')
    print('R71_INPUT_MANIFEST_SHA256_PASS entries=5', flush=True)
    return entries


def inspect_graph(p: Path):
    check_file(p, 'graph')
    b = p.read_bytes()
    if len(b) < 8 or len(b) % 4:
        raise ValueError(f'invalid graph size: {p}')
    words = array('I')
    if words.itemsize != 4:
        raise ValueError('host unsigned int is not 32 bit')
    words.frombytes(b)
    if sys.byteorder != 'little':
        words.byteswap()
    n, maxdegree = words[:2]
    if n != 100000 or maxdegree != 64:
        raise ValueError(f'bad graph header {p}: {n}, {maxdegree}')
    if len(words) < 2 + n:
        raise ValueError(f'truncated graph degree table: {p}')
    degs = words[2:2+n]
    arcs = sum(degs)
    if any(x > maxdegree for x in degs):
        raise ValueError(f'degree > max degree: {p}')
    if len(words) != 2 + n + arcs:
        raise ValueError(f'degree sum disagrees with file bytes: {p}')
    offset = 2 + n
    dup = selfloop = invalid_id = 0
    for i, d in enumerate(degs):
        row = words[offset:offset+d]
        offset += d
        if row:
            invalid_id += sum(x >= n for x in row)
            selfloop += sum(x == i for x in row)
            dup += len(row) - len(set(row))
    if dup or selfloop or invalid_id:
        raise ValueError(f'graph invalid {p}: duplicates={dup} selfloops={selfloop} invalid_id={invalid_id}')
    return {'size_bytes': len(b), 'n': n, 'max_degree': maxdegree, 'arcs': arcs,
            'average_degree': arcs / n, 'sha256': hashlib.sha256(b).hexdigest(),
            'invalid_ids': invalid_id, 'duplicates': dup, 'selfloops': selfloop}


def parse_time(t: Path):
    check_file(t, 'time')
    vals = dict(x.split('=', 1) for x in t.read_text().split() if '=' in x)
    if vals.get('EXIT') != '0':
        raise ValueError(f'nonzero measured exit: {t}')
    wall = float(vals['WALL_SEC'])
    rss = int(vals['MAX_RSS_KiB'])
    if not 0 < wall < 600 or not 0 < rss:
        raise ValueError(f'invalid wall/RSS: {t}')
    return wall, rss


def parse_recall(text: str):
    if 'R70_RECALL_INPUT_PASS' not in text or 'R70_RECALL_EVAL_PASS' not in text:
        raise ValueError('native evaluator did not print input / eval PASS')
    rows = {}
    for m in PATTERN.finditer(text):
        beam = int(m.group(1))
        if beam in rows or beam not in BEAMS:
            raise ValueError('duplicate/unexpected beam from native evaluator')
        recall, qps, cmps, visited = map(float, m.groups()[1:])
        if not (0 <= recall <= 1 and math.isfinite(recall) and
                0 < qps and math.isfinite(qps) and cmps >= 0 and visited >= 0):
            raise ValueError(f'invalid recall / QPS: beam={beam}')
        rows[beam] = {'recall': recall, 'qps': qps,
                      'avg_cmps': cmps, 'avg_visited': visited}
    if set(rows) != set(BEAMS):
        raise ValueError(f'wrong beam set from native evaluator: {sorted(rows)}')
    return rows


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run', type=Path, required=True, help='existing r71-factorial-4t-* folder')
    p.add_argument('--binary', type=Path, required=True, help='existing r70_graph_recall binary')
    p.add_argument('--base', type=Path, required=True)
    p.add_argument('--queries', type=Path, required=True)
    p.add_argument('--gt', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True, help='new non-existing output folder')
    a = p.parse_args()
    for attr in ('run','binary','base','queries','gt','out'):
        setattr(a, attr, getattr(a, attr).expanduser().resolve())
    if a.out.exists():
        raise ValueError(f'R71_OUTPUT_EXISTS_PRESERVED {a.out}')
    check_file(a.binary, 'native evaluator')
    if not os.access(a.binary, os.X_OK):
        raise ValueError(f'native evaluator not executable: {a.binary}')
    expected_headers = ((a.base, (100000, 128, 51200008)),
                        (a.queries, (300, 128, 153608)),
                        (a.gt, (300, 100, 240008)))
    for path, expected in expected_headers:
        h = header(path)
        if h != expected:
            raise ValueError(f'R71_BAD_DATASET_SHAPE {path} actual={h} expected={expected}')
    print('R71_DATA_SHAPES_PASS base=100000x128 queries=300x128 gt=300x100', flush=True)
    manifest = manifest_ok(a.run / 'inputs.sha256')
    expected_manifest_paths = {a.base.resolve()} | {a.run.parent / 'r71-bin' / v for v in VARIANTS}
    manifest_paths = {Path(e['path']) for e in manifest}
    if manifest_paths != expected_manifest_paths:
        raise ValueError('R71_MANIFEST_PATHS_NOT_MATCHING_EXPECTED_DATA_AND_BINARIES')
    specs = [(f'r{roundno}_{name}', name, roundno)
             for roundno in (1,2,3) for name in VARIANTS]
    all_runs = []
    for tag, variant, roundno in specs:
        graph = a.run / f'{tag}.graph'
        log = a.run / f'{tag}.log'
        time = a.run / f'{tag}.time'
        check_file(log, 'build log')
        build_text = log.read_text(errors='replace')
        reservoir, selection = EXPECTED_LABELS[variant]
        if f'R70_RESERVOIR_VARIANT={reservoir}' not in build_text:
            raise ValueError(f'R71_BAD_RESERVOIR_LABEL {tag}')
        if f'R71_SELECTION_VARIANT={selection}' not in build_text:
            raise ValueError(f'R71_BAD_SELECTION_LABEL {tag}')
        wall, rss = parse_time(time)
        stats = inspect_graph(graph)
        info = {'tag': tag, 'variant': variant, 'round': roundno,
                'graph': str(graph), 'build_wall_sec': wall, 'build_peak_rss_KiB': rss,
                'graph_stats': stats}
        all_runs.append(info)
        print(f'R71_GRAPH_VALID {tag} arcs={stats["arcs"]} bytes={stats["size_bytes"]} '
              f'wall_s={wall:.2f} rss_KiB={rss}', flush=True)
    print('R71_ALL_12_GRAPHS_VALID_PASS', flush=True)

    a.out.mkdir(parents=True)
    (a.out / 'run_manifest.json').write_text(json.dumps(
        {'timestamp': datetime.now().astimezone().isoformat(), 'input_manifest': manifest,
         'source_run': str(a.run), 'recalled_binary': str(a.binary),
         'recalled_binary_sha256': sha256(a.binary),
         'base': str(a.base), 'queries': str(a.queries), 'gt': str(a.gt),
         'runs': all_runs}, indent=2) + '\n')

    # Rotate variants across rounds to reduce systematic evaluation order bias.
    tags_by_round = {
        1: ['A_stock', 'B_h17', 'C_tier', 'D_h17_tier'],
        2: ['D_h17_tier', 'C_tier', 'B_h17', 'A_stock'],
        3: ['B_h17', 'D_h17_tier', 'A_stock', 'C_tier'],
    }
    by_tag = {r['tag']: r for r in all_runs}
    env = os.environ.copy()
    env['PARLAY_NUM_THREADS'] = '1'
    for roundno, variants in tags_by_round.items():
        for variant in variants:
            tag = f'r{roundno}_{variant}'
            entry = by_tag[tag]
            print(f'R71_RECALL_START {tag}', flush=True)
            cmd = [str(a.binary), entry['graph'], str(a.base), str(a.queries), str(a.gt)]
            try:
                proc = subprocess.run(cmd, env=env, stdout=subprocess.PIPE,
                                      stderr=subprocess.STDOUT, text=True, timeout=600)
            except subprocess.TimeoutExpired as e:
                raise ValueError(f'R71_RECALL_TIMEOUT {tag}') from e
            logfile = a.out / f'{tag}.recall.log'
            logfile.write_text(proc.stdout)
            if proc.returncode != 0:
                raise ValueError(f'R71_RECALL_FAILED {tag} rc={proc.returncode} see={logfile}')
            try:
                rows = parse_recall(proc.stdout)
            except ValueError as e:
                raise ValueError(f'R71_RECALL_PARSE_FAILED {tag} see={logfile}: {e}') from e
            entry['search'] = {str(k): v for k,v in rows.items()}
            print(f'R71_RECALL_RUN_PASS {tag} beams=5', flush=True)

    grouped = defaultdict(list)
    for r in all_runs:
        grouped[r['variant']].append(r)
    summary = {}
    for variant in VARIANTS:
        runs = grouped[variant]
        ss = {}
        for beam in BEAMS:
            recs = [r['search'][str(beam)]['recall'] for r in runs]
            qpss = [r['search'][str(beam)]['qps'] for r in runs]
            ss[str(beam)] = {
                'recall': recs, 'recall_median': median(recs),
                'recall_min': min(recs), 'recall_max': max(recs),
                'qps': qpss, 'qps_median': median(qpss),
                'qps_min': min(qpss), 'qps_max': max(qpss)
            }
        summary[variant] = {
            'wall_median_sec': median(r['build_wall_sec'] for r in runs),
            'rss_median_KiB': median(r['build_peak_rss_KiB'] for r in runs),
            'arcs_median': median(r['graph_stats']['arcs'] for r in runs),
            'search': ss}
    A = summary['A_stock']
    for variant in VARIANTS:
        v = summary[variant]
        print(f'R71_QUALITY_BUILD variant={variant} wall_median={v["wall_median_sec"]:.3f}s '
              f'rss_median={v["rss_median_KiB"]:.0f}KiB '
              f'wall_delta_pct={(v["wall_median_sec"]/A["wall_median_sec"]-1)*100:+.2f} '
              f'rss_delta_pct={(v["rss_median_KiB"]/A["rss_median_KiB"]-1)*100:+.2f}',
              flush=True)
    for beam in BEAMS:
        aa = A['search'][str(beam)]
        d = summary['D_h17_tier']['search'][str(beam)]
        print(f'R71_RECALL_COMPARE beam={beam} '
              f'A={aa["recall_median"]:.6f} '
              f'B={summary["B_h17"]["search"][str(beam)]["recall_median"]:.6f} '
              f'C={summary["C_tier"]["search"][str(beam)]["recall_median"]:.6f} '
              f'D={d["recall_median"]:.6f} '
              f'D_minus_A_pp={(d["recall_median"]-aa["recall_median"])*100:+.4f} '
              f'A_QPS={aa["qps_median"]:.2f} D_QPS={d["qps_median"]:.2f} '
              f'D_QPS_delta_pct={(d["qps_median"]/aa["qps_median"]-1)*100:+.2f}',
              flush=True)
    report = {
        'kind': 'R71_FACTORIAL_2x2_EXISTING_SIFT100K_GRAPH_RECALL_AUDIT',
        'created_at': datetime.now().astimezone().isoformat(),
        'source_run': str(a.run), 'build_threads':4, 'search_threads':1,
        'query_count':300, 'k':10, 'beams':list(BEAMS), 'cut':1.35,
        'limitations': [
            'The ground truth was externally sample-validated for 2 queries; not independently exact-validated for all 300.',
            'Three build repetitions per arm; descriptive medians, not a statistical equivalence test.',
            'Search QPS is timing-sensitive; one SEARCH pass per graph, may need repetition/warmup.',
            'Graph graph-outfile saved after BUILD; wall/RSS include graph serialization and process lifetime.',
            'Different graph SHA in multi-threaded PiPNN builds does not establish correctness or its absence.',
            'No SIFT1M result and no claim of algorithmic novelty.'
        ], 'summary': summary, 'runs': all_runs}
    json_path = a.out / 'r71_quality_summary.json'
    json_path.write_text(json.dumps(report, indent=2) + '\n')
    print(f'R71_RECALL_12_GRAPHS_PASS output={json_path}', flush=True)
    print('R71_INTERPRETATION_RECALL_PARITY_TO_BE_REVIEWED', flush=True)


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print(f'R71_QUALITY_FAIL {type(exc).__name__}: {exc}', file=sys.stderr, flush=True)
        sys.exit(1)
