#!/usr/bin/env python3
"""H32-R54: R26a archived BUILD wall/RSS log gate (read-only).

This is a provenance/availability audit, NOT a new benchmark or PiPNN II comparison.
It audits two original PiPNN SIFT1M R26a BUILD runs (candidate dump on/off),
never pools them into repeated-trial medians, and does not alter any input.

Usage on Ubuntu:
  python3 ann_task_a_r54_archival_build_gate.py selftest
  python3 ann_task_a_r54_archival_build_gate.py audit \
      --root ~/ann-task-a --output experiments/H54/r54_archival_build_gate.json
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import re
import statistics
import struct
import sys
import tempfile

REL = Path('experiments/H32/H32_R26a_pool_20261029_172452_132314')
GRAPH_SHA = 'd497f6d19fff4b7db6436f960d036755e375be92483c03ec0b9ed61968d17bef'
POOL_SIZE = 640_000_000
GRAPH_SIZE = 95_190_528
N = 1_000_000
CAP = 32
ARCS = 22_797_630
MAX_LOG = 8 * 1024 * 1024
WALL = re.compile(r'^\s*Elapsed \(wall clock\) time(?:\s+\([^)]*\))?:\s*(.*?)\s*$', re.I)
RSS = re.compile(r'^\s*Maximum resident set size \(kbytes\):\s*([0-9]+)\s*$', re.I)
EXIT = re.compile(r'^\s*Exit status:\s*(\d+)\s*$', re.I)


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda: f.read(8 * 1024 * 1024), b''):
            h.update(b)
    return h.hexdigest()


def seconds(s: str) -> float:
    parts = s.strip().replace(',', '.').split(':')
    if not 1 <= len(parts) <= 3:
        raise ValueError('unrecognized elapsed time: ' + repr(s))
    vals = [float(x) for x in parts]
    if any(x < 0 for x in vals):
        raise ValueError('negative elapsed time')
    if len(parts) >= 2 and not 0 <= vals[-1] < 60:
        raise ValueError('seconds field out of range')
    if len(parts) == 3 and not 0 <= vals[1] < 60:
        raise ValueError('minutes field out of range')
    return sum(v * (60**(len(vals) - 1 - i)) for i, v in enumerate(vals))


def parse_log(path: Path) -> dict:
    if not path.is_file() or path.stat().st_size > MAX_LOG:
        raise ValueError(f'not a regular bounded log: {path}')
    raw = path.read_text(encoding='utf-8', errors='replace')
    walls, peaks, statuses = [], [], []
    for no, line in enumerate(raw.splitlines(), 1):
        if (m := WALL.match(line)):
            walls.append((no, seconds(m.group(1))))
        if (m := RSS.match(line)):
            peaks.append((no, int(m.group(1))))
        if (m := EXIT.match(line)):
            statuses.append((no, int(m.group(1))))
    reasons = []
    if len(walls) != 1: reasons.append(f'wall cardinality {len(walls)} !=1')
    if len(peaks) != 1: reasons.append(f'RSS cardinality {len(peaks)} !=1')
    if len(statuses) != 1: reasons.append(f'exit-status cardinality {len(statuses)} !=1')
    if len(statuses) == 1 and statuses[0][1] != 0: reasons.append('nonzero exit status')
    return {
        'file': str(path), 'size_bytes': path.stat().st_size, 'sha256': digest(path),
        'status': 'STRICT_GNU_TIME_V_PASS' if not reasons else 'UNVERIFIED',
        'reasons': reasons,
        'wall_seconds': walls[0][1] if len(walls) == 1 else None,
        'wall_source_line': walls[0][0] if len(walls) == 1 else None,
        'max_rss_kib': peaks[0][1] if len(peaks) == 1 else None,
        'max_rss_source_line': peaks[0][0] if len(peaks) == 1 else None,
        'exit_status': statuses[0][1] if len(statuses) == 1 else None,
    }


def classify(path: Path) -> str:
    name = path.name.lower()
    if 'nodump' in name or 'no_dump' in name or 'no-dump' in name:
        return 'NODUMP'
    if 'dump' in name:
        return 'DUMP'
    return 'UNKNOWN'


def graph_header(path: Path) -> dict:
    with path.open('rb') as f:
        head = f.read(8)
    if len(head) != 8: raise ValueError('truncated graph header')
    n, cap = struct.unpack('<II', head)
    return {'n': n, 'max_degree': cap, 'bytes': path.stat().st_size, 'sha256': digest(path)}


def audit(root: Path) -> dict:
    dr = root / REL
    if not dr.is_dir():
        return {'status': 'BLOCKED_NO_R26A_DIR', 'expected_dir': str(dr)}
    graphs = {}
    for label in ('dump', 'nodump'):
        path = dr / f'{label}.graph'
        if not path.is_file():
            return {'status': 'BLOCKED_MISSING_GRAPH', 'path': str(path)}
        graphs[label] = graph_header(path)
        v = graphs[label]
        if (v['sha256'] != GRAPH_SHA or v['bytes'] != GRAPH_SIZE or
                v['n'] != N or v['max_degree'] != CAP):
            return {'status': 'FAIL_GRAPH_PIN', 'graphs': graphs, 'failed': label}
    pool = dr / 'dump.candidates.i32'
    pool_info = {'file': str(pool), 'exists': pool.is_file(),
                 'bytes': pool.stat().st_size if pool.is_file() else None,
                 'sha256': 'NOT_REHASHED_IN_R54; R51_ALREADY_PINNED_PASS'}
    if not pool.is_file() or pool.stat().st_size != POOL_SIZE:
        return {'status': 'FAIL_POOL_SIZE', 'graphs': graphs, 'pool': pool_info}

    # These are the BUILD time logs in a single pinned run directory;
    # an unknown name is not silently assigned to a BUILD arm.
    candidates = sorted(p for p in dr.glob('*.time.log') if p.is_file())
    if len(candidates) > 24:
        return {'status': 'BLOCKED_TOO_MANY_TOP_LEVEL_TIME_LOGS', 'count': len(candidates)}
    records = []
    for path in candidates:
        try:
            rec = parse_log(path)
        except Exception as exc:
            rec = {'file': str(path), 'status': 'UNVERIFIED', 'reasons': [str(exc)]}
        rec['arm_inferred_from_filename'] = classify(path)
        records.append(rec)
    arms = {a: [r for r in records if r['arm_inferred_from_filename'] == a] for a in ('NODUMP', 'DUMP')}
    errors = []
    for a in ('NODUMP', 'DUMP'):
        if len(arms[a]) != 1: errors.append(f'{a}: found {len(arms[a])}, expected 1')
        elif arms[a][0]['status'] != 'STRICT_GNU_TIME_V_PASS':
            errors.append(f'{a}: no unambiguous successful GNU time -v metrics')
    if not records: errors.append('No top-level *.time.log found; inspect filenames and provide exact paths')
    result = {
        'status': 'R54_R26A_ARCHIVED_BUILD_WALL_RSS_GATE_PASS' if not errors else 'R54_R26A_ARCHIVED_BUILD_WALL_RSS_GATE_BLOCKED',
        'kind': 'READ_ONLY_SINGLE_DUMP_NODUMP_PROVENANCE_NOT_SPEED_BENCHMARK',
        'root': str(root), 'graph_pin': GRAPH_SHA, 'graphs': graphs,
        'pool': pool_info,
        'original_top_level_time_log_count': len(records),
        'logs': records, 'errors': errors,
        'interpretation': 'Two sequential original PiPNN builds; dump has extra I/O. Do not use as a paired multi-repetition speed test or equate to H17 Top-2.',
        'historical_search_context_NOT_REMEASURED': {
            'graph': 'R26a original PiPNN pinned graph', 'k': 10, 'queries': 10000,
            'Q100_recall': 0.99096, 'Q100_mean_comparisons': 2068,
            'Q160_recall': 0.99667, 'Q160_mean_comparisons': 2975
        },
    }
    for a in ('NODUMP', 'DUMP'):
        if len(arms[a]) == 1:
            r = arms[a][0]
            if r.get('status') == 'STRICT_GNU_TIME_V_PASS':
                result[f'{a.lower()}_build_point'] = {
                    'wall_seconds': r['wall_seconds'],
                    'max_rss_kib': r['max_rss_kib'],
                    'max_rss_gib': round(r['max_rss_kib']/1048576, 6),
                    'log_file': r['file'], 'log_sha256': r['sha256'],
                    'is_valid_repeat_benchmark': False
                }
    return result


def selftest():
    assert seconds('0:44.95') == 44.95
    assert seconds('1:00:00.50') == 3600.5
    with tempfile.TemporaryDirectory() as td:
        r = Path(td); dr = r / REL; dr.mkdir(parents=True)
        content='\n'.join([
            'Command being timed: "build"',
            'Elapsed (wall clock) time (h:mm:ss or m:ss): 0:44.95',
            'Maximum resident set size (kbytes): 1849076',
            'Exit status: 0', ''])
        p = dr / 'build_nodump.time.log'; p.write_text(content)
        v = parse_log(p)
        assert v['status'] == 'STRICT_GNU_TIME_V_PASS'
        assert v['wall_seconds'] == 44.95 and v['max_rss_kib'] == 1849076
        assert classify(p) == 'NODUMP'
        assert classify(dr/'build_dump.time.log') == 'DUMP'
        p.write_text(content + 'Maximum resident set size (kbytes): 1849076\n')
        assert parse_log(p)['status'] == 'UNVERIFIED'
        p.write_text(content.replace('Exit status: 0', 'Exit status: 1'))
        assert parse_log(p)['status'] == 'UNVERIFIED'
    print('R54_SELFTEST_PASS: strict time-v wall/rss/exit, ambiguity, arm classification')


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    sp=ap.add_subparsers(dest='command',required=True)
    sp.add_parser('selftest')
    a=sp.add_parser('audit')
    a.add_argument('--root',type=Path,default=Path('.'))
    a.add_argument('--output',type=Path,default=Path('experiments/H54/r54_archival_build_gate.json'))
    args=ap.parse_args()
    if args.command=='selftest': selftest(); return 0
    root=args.root.expanduser().resolve()
    report=audit(root)
    out=args.output.expanduser()
    if not out.is_absolute(): out=root/out
    if not out.parent.is_dir():
        print(f'R54_FAIL missing output directory: {out.parent}',file=sys.stderr);return 2
    # Keep prior reports immutable; no override flag.
    try:
        with out.open('x',encoding='utf8') as f:
            json.dump(report,f,ensure_ascii=False,indent=2)
            f.write('\n')
    except FileExistsError:
        print(f'R54_FAIL already exists (preserved): {out}',file=sys.stderr);return 2
    print(report['status'])
    print('R54_REPORT',out)
    print('R54_TIME_LOG_COUNT',report.get('original_top_level_time_log_count','?'))
    for r in report.get('logs',[]):
        print('R54_LOG', Path(r['file']).name, r['arm_inferred_from_filename'],r['status'],
              'wall_s',r.get('wall_seconds'),'maxrss_kib',r.get('max_rss_kib'))
    for arm in ('nodump','dump'):
        if arm+'_build_point' in report:
            print('R54_BUILD_POINT',arm,report[arm+'_build_point'])
    for e in report.get('errors',[]): print('R54_BLOCKER',e)
    return 0 if report['status'].endswith('_PASS') else 2


if __name__=='__main__':
    sys.exit(main())
