#!/usr/bin/env python3
"""R83.8: search-only, paired 6-graph Recall/QPS audit of R83.7.

Reuses the existing PiPNN R70 evaluator without modifying H70/H80, building
indices, or requiring CUDA. Strict checks of dataset, graphs and manifests;
result directory is exclusive and is never overwritten. Individual logs and
incremental manifest are retained if an evaluator fails.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import platform
import re
import statistics
import struct
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

BASE_SHA = 'e50ff1bc34bcc6d1c97dd001023c09a666971cde64605cc06671ed8a8ff1ed12'
BINARY_SHA = {
    'D0': '254fe67c42a5568fc78062b51ee65ebcf13d03b6689c2470bc465423f9aad7e6',
    'E': 'd6ba7dcf7ed4fce1f40b646bc90bcd4cafa9fd668630d9b5a8922ad02e32615f'
}
STATUS = 'R83_7_TWO_METRIC_PILOT_SCREEN_GO_RECALL_PENDING'
PROTOCOL_BEAMS = (10, 20, 40, 80, 160)
PLAN = ('r1_D0', 'r1_E', 'r2_E', 'r2_D0', 'r3_D0', 'r3_E')


def require(ok: bool, msg: str):
    if not ok:
        raise RuntimeError(msg)


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def validate_matrix(path: Path, shape: tuple[int, int], payload_bytes_per_slot: int = 4):
    """Check the observed file layout; do not reinterpret or convert the payload.

    SIFT100K base/query .fbin files carry 4 bytes per float32 slot. The
    previously evaluated sift100k_gt300.ibin artifact has a 300x100 header and
    240008 bytes in total (8 payload bytes per advertised slot). This does NOT
    assert that the original evaluator reads the GT file as uint64: it only
    preserves the exact original artifact's byte layout.
    """
    require(payload_bytes_per_slot in (4, 8), 'R83_8_INVALID_PAYLOAD_WIDTH')
    require(path.is_file(), f'R83_8_MISSING_INPUT {path}')
    with path.open('rb') as f:
        header = f.read(8)
    require(len(header) == 8, f'R83_8_BAD_INPUT_HEADER {path}')
    n, d = struct.unpack('<II', header)
    expected_size = 8 + n * d * payload_bytes_per_slot
    require((n, d) == shape and path.stat().st_size == expected_size,
            f'R83_8_BAD_INPUT_SHAPE {path} got={(n,d)} size={path.stat().st_size} '
            f'expected_shape={shape} expected_bytes={expected_size} '
            f'bytes_per_slot={payload_bytes_per_slot}')


def check_graph(path: Path, recorded: dict):
    require(path.is_file(), f'R83_8_MISSING_GRAPH {path}')
    with path.open('rb') as f:
        header = f.read(8)
        require(len(header) == 8, f'R83_8_GRAPH_HEADER_SHORT {path}')
        n, degree = struct.unpack('<II', header)
        require((n, degree) == (100000, 64), f'R83_8_GRAPH_HEADER_CHANGED {path}')
        ds = f.read(4 * n)
        require(len(ds) == 4 * n, f'R83_8_GRAPH_DEGREES_SHORT {path}')
        degrees = struct.unpack('<' + str(n) + 'I', ds)
        require(max(degrees) <= degree, f'R83_8_GRAPH_BAD_DEGREE {path}')
        arcs = sum(degrees)
    require(path.stat().st_size == 8 + 4 * n + 4 * arcs,
            f'R83_8_GRAPH_SIZE_CHANGED {path}')
    require(arcs == recorded.get('arcs') and sha(path) == recorded.get('sha256'),
            f'R83_8_GRAPH_SHA_OR_ARC_CHANGED {path}')
    return arcs


def extract_rows(raw: str):
    rows = []
    for line in raw.splitlines():
        if line.startswith('R70_RECALL_ROW '):
            pairs = dict(re.findall(r'(\w+)=([0-9.eE+\-]+)', line))
            require(bool(pairs), 'R83_8_RECALL_ROW_PARSE_EMPTY')
            rows.append({k: float(v) for k, v in pairs.items()})
    require('R70_RECALL_EVAL_PASS' in raw, 'R83_8_RECALL_EVAL_PASS_MISSING')
    require(len(rows) == 5, f'R83_8_RECALL_EXPECTED_5_BEAMS got={len(rows)}')
    for expected, row in zip(PROTOCOL_BEAMS, rows):
        reported_beam = value(row, ('beam','beamsize','beam_size'))
        if reported_beam is not None:
            require(reported_beam == expected,
                    f'R83_8_RECALL_BEAM_ORDER_MISMATCH expected={expected} got={reported_beam}')
    return rows


def value(row, terms):
    keys = {k.lower(): k for k in row}
    for t in terms:
        if t in keys:
            return row[keys[t]]
    return None


def recall_val(row):
    v = value(row, ('recall_at_10','recall10','recall_at10','recall','recall_10','r10'))
    if v is None:
        for k, val in row.items():
            if 'recall' in k.lower():
                v = val
                break
    return v


def qps_val(row):
    v = value(row, ('qps','queries_per_second','throughput_qps'))
    if v is None:
        for k, val in row.items():
            if 'qps' in k.lower():
                return val
    return v


def metrics(rows: dict):
    """Structured exploratory medians. Only declare numeric quality if parsed."""
    raw = []
    for ix, beam in enumerate(PROTOCOL_BEAMS):
        by = {}
        for arm in ('D0', 'E'):
            rec = [recall_val(rows[f'r{rep}_{arm}']['beams'][ix]) for rep in (1,2,3)]
            qps = [qps_val(rows[f'r{rep}_{arm}']['beams'][ix]) for rep in (1,2,3)]
            by[arm] = {'recall': rec, 'qps': qps}
        result = {'beam_assumed_from_R70_evaluator_fixed_order': beam,
                  'D0': by['D0'], 'E': by['E']}
        if all(x is not None and 0 <= x <= 1 for arm in by for x in by[arm]['recall']):
            d = statistics.median(by['D0']['recall'])
            e = statistics.median(by['E']['recall'])
            result['median_recall_D0'] = d
            result['median_recall_E'] = e
            result['median_recall_E_minus_D0'] = e - d
            result['paired_recall_deltas_E_minus_D0'] = [e1-d1 for e1,d1 in zip(by['E']['recall'],by['D0']['recall'])]
        if all(x is not None and x > 0 for arm in by for x in by[arm]['qps']):
            d = statistics.median(by['D0']['qps'])
            e = statistics.median(by['E']['qps'])
            result['median_qps_D0'] = d
            result['median_qps_E'] = e
            result['median_qps_E_over_D0'] = e / d
        raw.append(result)
    all_recall = all('median_recall_E_minus_D0' in b for b in raw)
    all_qps = all('median_qps_E_over_D0' in b for b in raw)
    if not all_recall:
        verdict = 'R83_8_SCHEMA_REVIEW_REQUIRED_NO_RECALL_CLAIM'
    elif any(x['median_recall_E_minus_D0'] < -0.005 for x in raw):
        verdict = 'R83_8_RECALL_PILOT_REVIEW_HOLD'
    elif all_qps and sum(x['median_qps_E_over_D0'] < 0.90 for x in raw) >= 2:
        verdict = 'R83_8_QPS_PILOT_REVIEW_HOLD'
    else:
        verdict = 'R83_8_TECHNICAL_RECALL_SCREEN_PASS_NOT_STATISTICAL_PROOF'
    return {'beams': raw, 'numeric_recall_parsed': all_recall,
            'numeric_qps_parsed': all_qps,
            'exploratory_recall_median_abs_tolerance': 0.005,
            'exploratory_qps_ratio_review_threshold': 0.90,
            'verdict': verdict,
            'notes': ['Beam labels positional: R70 fixed beam protocol 10,20,40,80,160; verify against evaluator output',
                      'Three independent graph BUILDs per arm, not an equivalence/non-inferiority test',
                      'Native QPS can be sensitive to new CPU, affinity, clock, frequency and system load']}


def find_evaluator(root):
    h70 = root / 'experiments/H70/pipnn-clean-443a328'
    candidates = [h70/'build-r70/algorithms/PipNN/r70_graph_recall',
                  h70/'build-r70/r70_graph_recall']
    candidates.extend(sorted(h70.glob('build*/**/r70_graph_recall')))
    found = sorted({p.resolve() for p in candidates if p.is_file() and os.access(p, os.X_OK)})
    require(len(found) == 1, f'R83_8_EVALUATOR_NOT_UNIQUE expected 1 found={len(found)} paths={found}')
    return found[0]


def historic_quality(root):
    p = root/'experiments/H80/r80_4_matched_build/runs'
    reports = sorted(p.glob('*/quality/recall_summary.json')) if p.is_dir() else []
    return [(path, json.loads(path.read_text())) for path in reports]


def preflight(root):
    run_dir = root/'experiments/H83/r83_7_sift100k_paired'
    report = run_dir/'r83_7_summary.json'
    require(report.is_file(), f'R83_8_R83_7_REPORT_MISSING {report}')
    source = json.loads(report.read_text())
    require(source.get('status') == STATUS, 'R83_8_R83_7_SCREEN_NOT_GO')
    require(source.get('threads') == 4 and source.get('base_sha256') == BASE_SHA,
            'R83_8_R83_7_BASE_OR_THREADS_MISMATCH')
    require(source.get('binary_sha256') == BINARY_SHA,
            'R83_8_R83_7_BINARIES_MISMATCH')
    base = root/'data/sift100k.fbin'
    query = root/'data/sift100k_queries_300.fbin'
    gt = root/'data/sift100k_gt300.ibin'
    validate_matrix(base, (100000,128))
    validate_matrix(query, (300,128))
    validate_matrix(gt, (300,100), payload_bytes_per_slot=8)
    print('R83_8_GT300_OBSERVED_BYTE_LAYOUT_PASS rows=300 cols=100 bytes_per_slot=8 bytes=240008', flush=True)
    require(sha(base) == BASE_SHA, 'R83_8_BASE_SHA_MISMATCH')
    hashes = {'base': sha(base), 'query': sha(query), 'gt': sha(gt)}
    ev = find_evaluator(root)
    evaluator_sha = sha(ev)
    prev = historic_quality(root)
    for path, old in prev:
        for key, now in [('evaluator_sha256', evaluator_sha),
                         ('query_sha256', hashes['query']), ('gt_sha256', hashes['gt'])]:
            if key in old:
                require(old[key] == now,
                        f'R83_8_R80_EVALUATOR_OR_DATA_DRIFT key={key} historical={path}')
    print(f'R83_8_EVALUATOR path={ev} sha256={evaluator_sha}', flush=True)
    print(f'R83_8_INPUT_HASHES {json.dumps(hashes, sort_keys=True)}', flush=True)
    print(f'R83_8_H80_QUALITY_PROVENANCE_REPORTS count={len(prev)}', flush=True)
    for tag in PLAN:
        item = source.get('runs', {}).get(tag)
        require(item is not None and item['tag'] == tag and item['exit_code'] == 0,
                f'R83_8_INCOMPLETE_BUILD {tag}')
        p = run_dir/tag/'graph.bin'
        check_graph(p, item['graph'])
    print('R83_8_PINNED_SIX_GRAPHS_AND_SEARCH_INPUTS_PASS', flush=True)
    return run_dir, base, query, gt, ev, hashes, evaluator_sha


def selftest():
    sample = '''R70_RECALL_ROW beam=10 recall=0.79 qps=1234.5\nR70_RECALL_ROW beam=20 recall=0.9 qps=777\nR70_RECALL_ROW beam=40 recall=0.97 qps=678\nR70_RECALL_ROW beam=80 recall=0.99 qps=543\nR70_RECALL_ROW beam=160 recall=1.0 qps=321\nR70_RECALL_EVAL_PASS'''
    rows = extract_rows(sample)
    assert len(rows) == 5 and recall_val(rows[0]) == .79 and qps_val(rows[0]) == 1234.5
    records = {f'r{rep}_{arm}': {'beams': rows} for rep in (1,2,3) for arm in ('D0', 'E')}
    m = metrics(records)
    assert m['verdict'] == 'R83_8_TECHNICAL_RECALL_SCREEN_PASS_NOT_STATISTICAL_PROOF'
    assert len(m['beams']) == 5
    from tempfile import TemporaryDirectory
    with TemporaryDirectory() as td:
        gt_fixture = Path(td) / 'gt300.ibin'
        gt_fixture.write_bytes(struct.pack('<II', 300, 100) + b'\0' * (300*100*8))
        validate_matrix(gt_fixture, (300, 100), payload_bytes_per_slot=8)
        try:
            validate_matrix(gt_fixture, (300, 100), payload_bytes_per_slot=4)
        except RuntimeError as exc:
            assert 'R83_8_BAD_INPUT_SHAPE' in str(exc)
        else:
            raise AssertionError('GT payload width regression not detected')
        query_fixture = Path(td) / 'queries.fbin'
        query_fixture.write_bytes(struct.pack('<II', 300, 128) + b'\0' * (300*128*4))
        validate_matrix(query_fixture, (300, 128))
    print('R83_8_GT_LAYOUT_SELFTEST_PASS', flush=True)
    print('R83_8_RUNNER_SELFTEST_PASS', flush=True)


def run(root, dry_run=False):
    selftest()
    run_dir, base, query, gt, evaluator, hashes, eval_sha = preflight(root)
    out = run_dir/'quality'
    require(not out.exists(), f'R83_8_OUTPUT_EXISTS_FAIL_CLOSED {out}')
    if dry_run:
        print('R83_8_DRY_RUN_PASS_NO_SEARCH_PERFORMED', flush=True)
        return
    out.mkdir(exist_ok=False)
    report = out/'r83_8_quality_summary.json'
    results = {'status': 'STARTED', 'source_R83_7_report': str(run_dir/'r83_7_summary.json'),
               'base_sha256': hashes['base'], 'query_sha256': hashes['query'],
               'gt_sha256': hashes['gt'], 'evaluator_sha256': eval_sha,
               'search_host': {'node': platform.node(), 'machine': platform.machine(),
                               'processor': platform.processor(), 'kernel': platform.release(),
                               'allowed_cpus': sorted(os.sched_getaffinity(0)) if hasattr(os,'sched_getaffinity') else None},
               'created_at_utc': datetime.now(timezone.utc).isoformat(), 'rows': {}}
    report.write_text(json.dumps(results, indent=2)+'\n')
    try:
        for tag in PLAN:
            gp = run_dir/tag/'graph.bin'
            log = out/(tag+'.recall.log')
            args = [str(evaluator), str(gp), str(base), str(query), str(gt)]
            print(f'R83_8_SEARCH_START graph={tag}', flush=True)
            with log.open('x') as fp:
                try:
                    proc = subprocess.run(args, stdout=fp, stderr=subprocess.STDOUT,
                                          cwd=out, timeout=300, check=False)
                    code = proc.returncode
                except subprocess.TimeoutExpired:
                    code = 124
            require(code == 0, f'R83_8_SEARCH_EXIT_{code} graph={tag} log={log}')
            rec = extract_rows(log.read_text(errors='replace'))
            results['rows'][tag] = {'arm':tag.split('_')[1], 'rep':int(tag[1]),
                                   'beams':rec, 'log':str(log)}
            report.write_text(json.dumps(results, indent=2)+'\n')
            print('R83_8_SEARCH_PASS graph='+tag+' rows='+str(len(rec))+' '+json.dumps(rec), flush=True)
        m = metrics(results['rows'])
        results['assessment'] = m
        results['status'] = m['verdict']
        report.write_text(json.dumps(results, indent=2)+'\n')
        print('R83_8_MEDIANS '+json.dumps([{
            k:v for k,v in b.items() if k.startswith('median_') or k.startswith('beam_')}
            for b in m['beams']], sort_keys=True), flush=True)
        print(m['verdict'], flush=True)
        print('R83_8_NOT_SIFT1M_NOT_NEW_BUILD_NOT_STATISTICAL_EQUIVALENCE_NOT_PUSH', flush=True)
        print('R83_8_REPORT', report, flush=True)
    except Exception as exc:
        results['status'] = 'STOP_INCOMPLETE'
        results['error'] = str(exc)
        report.write_text(json.dumps(results, indent=2)+'\n')
        raise


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--root', type=Path, default=Path.home()/'ann-task-a')
    p.add_argument('--selftest', action='store_true')
    p.add_argument('--dry-run', action='store_true')
    a = p.parse_args()
    try:
        if a.selftest:
            selftest()
        else:
            run(a.root.expanduser().resolve(), a.dry_run)
    except Exception as exc:
        print('R83_8_STOP', exc, file=sys.stderr, flush=True)
        sys.exit(1)
