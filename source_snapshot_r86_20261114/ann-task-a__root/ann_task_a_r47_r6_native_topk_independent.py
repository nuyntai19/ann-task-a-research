#!/usr/bin/env python3
"""H32-R47-R6 independent native Top-10 ID check, Q80/120/160.

Run the INDEPENDENT R45 native trace binary (not the R47 instrumented binary),
on pinned graph/data for three beam widths. Compare SEARCH records against R47-R5
reconstructed top-10 for 17 preselected queries; require 5 identical repeats.
No graph build, data mutation or rewrite of preexisting H47 outputs.

Usage:
  python3 ann_task_a_r47_r6_native_topk_independent.py selftest
  python3 -u ann_task_a_r47_r6_native_topk_independent.py run
  python3 -u ann_task_a_r47_r6_native_topk_independent.py audit
"""
import argparse
from collections import defaultdict
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path('experiments/H47')
PIN_GRAPH_SHA = 'd497f6d19fff4b7db6436f960d036755e375be92483c03ec0b9ed61968d17bef'
GRAPH = Path('experiments/H32/H32_R26a_pool_20261029_172452_132314/dump.graph')
NATIVE_R45 = Path('experiments/H45/ParlayANN-native-trace/algorithms/vamana/neighbors')
BASELINE = Path('src/ParlayANN/algorithms/vamana/neighbors')
BASE = Path('data/sift1m.fbin')
QUERIES = Path('data/sift1m_queries.fbin')
GT = Path('data/sift1m_gt.ibin')
QS = (80, 120, 160)
METRIC = re.compile(r'search: Q=(\d+), k=(\d+), limit=(\d+), recall=([^,]+), visited=([^,]+), comparisons=([^,]+), QPS=')


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(4 << 20), b''):
            h.update(block)
    return h.hexdigest()


def paths(q):
    stem = ROOT / ('r47_r6_q%d_r45_independent' % q)
    return Path(str(stem) + '.stdout'), Path(str(stem) + '.stderr')


def required_inputs():
    for p in (ROOT/'r47_target_manifest.json', ROOT/'r47_r5_q_sensitivity.json', GRAPH, BASE, QUERIES, GT):
        if not p.is_file():
            raise ValueError('Required input is missing: ' + str(p))
    for p in (NATIVE_R45, BASELINE):
        if not p.is_file() or not os.access(p, os.X_OK):
            raise ValueError('Executable missing: ' + str(p) + '. Use existing R45 native trace binary; do not rebuild graph.')
    m = json.loads((ROOT/'r47_target_manifest.json').read_text())
    r5 = json.loads((ROOT/'r47_r5_q_sensitivity.json').read_text())
    if m['protocol']['graph_sha256'] != PIN_GRAPH_SHA or r5['graph_sha256'] != PIN_GRAPH_SHA:
        raise ValueError('Manifest/report graph pin mismatch')
    if digest(GRAPH) != PIN_GRAPH_SHA:
        raise ValueError('Actual graph SHA differs from pinned R26a')
    qids = sorted(set(map(int, m['native_fail_query_ids'])))
    if len(qids) != 17 or r5.get('queries') != 17 or r5.get('audit') != 'R47_R5_FIXED_GRAPH_Q_SENSITIVITY_PASS':
        raise ValueError('Unexpected R47-R0/R5 records')
    by_id = {int(rec['query_id']): rec for rec in r5['per_query']}
    if set(by_id) != set(qids):
        raise ValueError('R5 query ID set mismatch')
    return qids, by_id


def parse_metrics(path, q):
    rows = []
    with path.open('r', errors='replace') as f:
        for line in f:
            m = METRIC.search(line)
            if m:
                rq, k, limit = map(int, m.group(1,2,3))
                if (rq, k, limit) != (q, 10, 1_000_000):
                    raise ValueError(f'Wrong evaluation Q/k/limit in {path}: {(rq,k,limit)}')
                rows.append(tuple(float(v) for v in m.group(4,5,6)))
    if len(rows) != 5 or len(set(rows)) != 1:
        raise ValueError(f'Expected 5 identical aggregate metric records in {path}, got {rows}')
    return rows[0]


def parse_search_stream(path, q, query_ids):
    """Native R45 emits SEARCH|query|Q|k|opaque|cmps|beamIDs|visitedIDs.

    Do NOT assume field[4] is a repeat index; R45 prints 0 five times.
    A single native R45 trace records all 10k queries or selected 256; only
    remember the 17 pinned IDs, avoiding excess memory.
    """
    found = defaultdict(list)
    with path.open('r', errors='replace') as f:
        for number, line in enumerate(f, 1):
            if not line.startswith('SEARCH|'):
                continue
            fields = line.rstrip('\r\n').split('|')
            if len(fields) < 8:
                raise ValueError(f'Incomplete SEARCH line {number} in {path}')
            try:
                qid, qq, k, opaque, comparisons = (int(f) for f in fields[1:6])
            except ValueError as e:
                raise ValueError(f'Bad SEARCH header at {path}:{number}: {e}')
            if qid not in query_ids:
                continue
            if qq != q or k != 10:
                raise ValueError(f'Wrong Q/k in SEARCH query={qid} Q{qq},k{k}')
            def parse_ids(s):
                return tuple(int(x) for x in s.split(',') if x.strip())
            beam, visited = parse_ids(fields[6]), parse_ids(fields[7])
            if len(beam) != q or len(set(beam)) != q:
                raise ValueError(f'Bad beam size/ID duplicates for qid={qid}, Q={q}: len={len(beam)}')
            if len(set(visited)) != len(visited):
                raise ValueError(f'Duplicate visited IDs for qid={qid}')
            found[qid].append({'top10': beam[:10], 'full_beam': beam,
                                'visited': visited, 'comparisons': comparisons,
                                'opaque_header_field': opaque})
    if set(found) != set(query_ids):
        raise ValueError(f'Missing selected SEARCH IDs in {path}: {sorted(set(query_ids)-set(found))}. '
                         'The R45 trace binary may be pinned to Q100 only; inspect its trace conditions.')
    result = {}
    for qid in sorted(query_ids):
        items = found[qid]
        if len(items) != 5:
            raise ValueError(f'qid={qid},Q={q}: expected 5 native SEARCH records, got {len(items)}')
        if any((i['top10'],i['full_beam'],i['visited'],i['comparisons']) !=
               (items[0]['top10'],items[0]['full_beam'],items[0]['visited'],items[0]['comparisons'])
               for i in items[1:]):
            raise ValueError(f'Native R45 not deterministic at qid={qid},Q={q}')
        result[qid] = items[0]
    return result


def run():
    qids, by_id = required_inputs()
    expected = [p for q in QS for p in paths(q)]
    exists = [str(p) for p in expected if p.exists()]
    if exists:
        raise ValueError('Won\'t overwrite existing R6 output(s): ' + ', '.join(exists))
    flags = ['-data_type','float','-dist_func','Euclidian',
             '-base_path',str(BASE.resolve()), '-query_path',str(QUERIES.resolve()),
             '-gt_path',str(GT.resolve()), '-graph_path',str(GRAPH.resolve()),
             '-k','10','-verbose']
    env = dict(os.environ)
    env.update(PARLAY_NUM_THREADS='1', OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1')
    for q in QS:
        out,err = paths(q)
        print(f'R47_R6_START_INDEPENDENT_R45_NATIVE_SEARCH Q={q}', flush=True)
        with out.open('w') as fo, err.open('w') as fe:
            subprocess.run([str(NATIVE_R45.resolve()), *flags, '-Q', str(q)],
                           stdout=fo, stderr=fe, check=True, env=env)
        # Query-level results might be in either stream, validate at audit.
        m = parse_metrics(out, q)
        r5_baseline = ROOT / f'r47_r5_q{q:03d}_baseline.stdout'
        if m != parse_metrics(r5_baseline, q):
            raise ValueError(f'Q{q}: R45-independent aggregate metrics != R5 original baseline')
        print(f'R47_R6_Q{q}_NATIVE_AGGREGATE_PARITY_PASS', flush=True)
        # Fail early if the isolated R45 binary was hard-coded to trace Q100.
        # Avoid running Q120/Q160 without the needed SEARCH ID evidence.
        valid_sources = []
        for path in (out, err):
            try:
                records = parse_search_stream(path, q, set(qids))
                valid_sources.append(path)
            except ValueError as ex:
                if 'Missing selected SEARCH IDs' not in str(ex):
                    raise
        if len(valid_sources) != 1:
            raise ValueError(f'Q{q}: native R45 did not produce one valid 17-query SEARCH stream. '
                             'The R45 binary may limit trace emission to Q100; stop and inspect '
                             'check_nn_recall.h rather than modify the original source.')
        print(f'R47_R6_Q{q}_NATIVE_TRACE_17x5_PASS', flush=True)
    print('R47_R6_SEARCH_RUNS_DONE', flush=True)


def audit():
    qids, by_id = required_inputs()
    summary = []
    for q in QS:
        out,err = paths(q)
        if not (out.is_file() and err.is_file()):
            raise ValueError('Missing R6 outputs at Q' + str(q))
        metrics_r45 = parse_metrics(out, q)
        metrics_original = parse_metrics(ROOT/f'r47_r5_q{q:03d}_baseline.stdout',q)
        if metrics_r45 != metrics_original:
            raise ValueError(f'Q{q}: aggregate metrics mismatch')
        # Trace instrumentations may print SEARCH events to stderr OR stdout.
        # Exactly one stream must contain complete pinned records.
        got = []
        for path in (out,err):
            try:
                got.append((path, parse_search_stream(path, q, set(qids))))
            except ValueError as ex:
                if 'Missing selected SEARCH IDs' in str(ex):
                    continue
                raise
        if len(got) != 1:
            raise ValueError(f'Q{q}: expected one complete SEARCH stream, found {len(got)}; '
                             'check R45 binary trace emission and file layout')
        source, records = got[0]
        for qid in qids:
            expected = tuple(by_id[qid]['by_q'][str(q)]['top10'])
            native = records[qid]['top10']
            if expected != native:
                raise ValueError(f'Q{q}, query={qid}: INDEPENDENT_TOP10_MISMATCH '
                                 f'R5={expected} R45_native={native}')
            if by_id[qid]['by_q'][str(q)]['comparisons'] != records[qid]['comparisons']:
                raise ValueError(f'Q{q}, query={qid}: independent comparisons mismatch')
            if by_id[qid]['by_q'][str(q)]['visited_count'] != len(records[qid]['visited']):
                raise ValueError(f'Q{q}, query={qid}: independent visited count mismatch')
        print(f'R47_R6_Q{q}_NATIVE_TOP10_IDS_PASS 17/17 x 5 repeats; trace_source={source}', flush=True)
        summary.append({'Q':q,'aggregate_metrics':metrics_r45,'matched_queries':len(qids),
                        'native_trace_source':str(source),'query_details':[{'query_id':id_,
                        'top10':list(records[id_]['top10']), 'comparisons':records[id_]['comparisons'],
                        'visited_count':len(records[id_]['visited'])} for id_ in qids]})
    report = {'audit':'R47_R6_INDEPENDENT_NATIVE_TOP10_ID_PARITY_PASS',
              'graph_sha256':PIN_GRAPH_SHA, 'native_trace_executable':str(NATIVE_R45),
              'independent_source':'R45 separately instrumented native ParlayANN (not R47 beam-decision binary)',
              'Q':[80,120,160], 'query_ids':qids,'repeats':5,'by_q':summary,
              'limits':['Independent R45 source instrumentation may itself affect control flow; '
                        'compared aggregate metrics and all selected Top10/visited/comparisons.',
                        'Search-level evidence, not a graph construction improvement or novel algorithm.']}
    destination = ROOT/'r47_r6_independent_native_top10.json'
    if destination.exists():
        raise ValueError('Refusing to overwrite existing R6 audit: ' + str(destination))
    destination.write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n')
    print('R47_R6_INDEPENDENT_NATIVE_TOP10_ID_PARITY_PASS', flush=True)
    print('OUTPUT',destination)


def selftest():
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        p=Path(td)/'test.stderr'
        qids={4,7}
        b4=','.join(str(i) for i in range(80)) + ','
        visited='1,2,3,'
        lines=[]
        for i in range(5):
            for qid in qids:
                lines.append(f'SEARCH|{qid}|80|10|0|313|{b4}|{visited}')
        p.write_text('\n'.join(lines)+'\n')
        r=parse_search_stream(p,80,qids)
        assert set(r)==qids and len(r[7]['top10'])==10
        assert r[4]['comparisons']==313 and len(r[7]['visited'])==3
        p.write_text(p.read_text().replace('SEARCH|7|80|10|0|313','SEARCH|7|80|10|0|314',1))
        try:
            parse_search_stream(p,80,qids)
            raise AssertionError('repeat mismatch unreported')
        except ValueError as e:
            assert 'not deterministic' in str(e)
    print('R47_R6_SELFTEST_PASS: native SEARCH Q, IDs, 5 repeats, mismatch detection')


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('action',choices=['selftest','run','audit'])
    a=ap.parse_args()
    try:
        if a.action=='selftest':selftest()
        elif a.action=='run':run()
        else:audit()
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as e:
        print('R47_R6_FAIL:',e,file=sys.stderr)
        sys.exit(2)

if __name__=='__main__':main()
