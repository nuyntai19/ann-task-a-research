#!/usr/bin/env python3
"""Recover R26b metrics from NEW -verbose SEARCH ONLY logs. Never rebuild graph."""
import argparse
import hashlib
import json
import math
import re
import statistics
from pathlib import Path

NUMBER = r'[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?'
# ParlayANN cmuparlay/ParlayANN pinned a48c6a3, check_nn_recall.h:
#   search: Q=..., k=..., limit=..., recall=..., visited=..., comparisons=..., QPS=..., ctime=...
PAT = re.compile(
    rf'^\s*search:\s*Q\s*=\s*(\d+)\s*,\s*k\s*=\s*(\d+)\s*,\s*limit\s*=\s*(\d+)\s*,\s*'
    rf'recall\s*=\s*({NUMBER})\s*,\s*visited\s*=\s*(\d+)\s*,\s*'
    rf'comparisons\s*=\s*(\d+)\s*,\s*QPS\s*=\s*({NUMBER})\s*(?:,|$)',
    re.I | re.M,
)
EXPECTED_SEARCH_SHA = 'ee6b9c0bec2f32fe00607f3facc73691d2dca2d5158e84e69c226b3cd219c9a8'
EXPECTED_PIPNN_SHA = 'd497f6d19fff4b7db6436f960d036755e375be92483c03ec0b9ed61968d17bef'
EXPECTED_FG_SHA = 'e0842613d7fc24e4b3b1f3ec60aff2ce4f5e054b3bcc51812a06c83355b64389'


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(8 * 1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def parse(log, expected_q):
    text = Path(log).read_text(encoding='utf-8', errors='replace')
    matches = list(PAT.finditer(text))
    if len(matches) != 5:
        lines = [line.strip()[:350] for line in text.splitlines() if 'search:' in line or 'recall' in line.lower()]
        raise ValueError(f'EXPECTED_FIVE_SEARCH_SUMMARIES q={expected_q} actual={len(matches)} path={log} snippets={lines[:12]!r}')
    rows = []
    for m in matches:
        q, k, limit = (int(m.group(x)) for x in [1, 2, 3])
        recall = float(m.group(4))
        visited, comparisons = int(m.group(5)), int(m.group(6))
        qps = float(m.group(7))
        if q != expected_q or k != 10 or limit != 1_000_000 or not (0 <= recall <= 1) or not (math.isfinite(qps) and qps > 0):
            raise ValueError(f'BAD_SEARCH_RECORD path={log} record={m.group(0)!r}')
        rows.append({'recall_native_tie_aware': recall, 'qps': qps, 'visited': visited, 'comparisons': comparisons})
    return rows


def selftest():
    line = 'search: Q=100, k=10, limit=1000000, recall=0.990870, visited=143, comparisons=2070, QPS=2461.38, ctime=195.4'
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        f = Path(td) / 'test.log'
        f.write_text((line + '\n') * 5)
        vals = parse(f, 100)
        assert len(vals) == 5 and vals[0]['comparisons'] == 2070 and vals[0]['recall_native_tie_aware'] == .99087
    print('R26B_SEARCH_PARSER_SELFTEST_PASS')


def report(out):
    original = out / 'r26b_graph_report.json'
    gr = json.loads(original.read_text())
    p = gr['pipnn']; f = gr['fg']
    assert p['sha256'] == EXPECTED_PIPNN_SHA and f['sha256'] == EXPECTED_FG_SHA, 'GRAPH_REPORT_SHA_MISMATCH'
    assert p['arcs'] == 22_797_630 and f['arcs'] == 28_368_175, 'GRAPH_REPORT_ARCS_MISMATCH'
    records = {}
    simple = []
    for q in (80, 100, 120, 160):
        records[str(q)] = {}
        for arm in ('pipnn', 'fg'):
            path = out / f'search_{arm}_q{q}.verbose.log'
            rows = parse(path, q)
            fields = ('recall_native_tie_aware','qps','visited','comparisons')
            med = {key: statistics.median(row[key] for row in rows) for key in fields}
            records[str(q)][arm] = {'log_file': path.name, 'sha256': digest(path), 'five_internal_repeats': rows, 'median': med}
            simple.append(f'Q={q} ARM={arm} RECALL_NATIVE_TIE_AWARE_MEDIAN={med["recall_native_tie_aware"]:.6f} QPS_MEDIAN={med["qps"]:.2f} AVG_CMPS_MEDIAN={med["comparisons"]:.1f} AVG_VISITED_MEDIAN={med["visited"]:.1f}')
    meta = {
        'status': 'R26B_SEARCH_RECOVERY_PASS_SAME_NATIVE',
        'script_fix': 'Prior R26b omitted -verbose; old logs contain no search statistics; fixed-Q native prints search: ..., not For 10@10 ...',
        'native_search_sha256': EXPECTED_SEARCH_SHA,
        'graphs': {'pipnn': p, 'fg': f},
        'budget_delta_percent': round((f['arcs']/p['arcs']-1)*100,6),
        'graph_budget_matched': False,
        'measurements': records,
        'limits': [
            '8 native SEARCH configurations rerun only; NO index graph rebuilt or candidate pool regeneration',
            '5 repetitions are inside a single native process per graph/Q, not 5 independent processes',
            'Data is SIFT1M, same native ParlayANN searcher, single CPU 0, k=10, fixed Q 80/100/120/160',
            'FG graph has 24.435% more arcs than PiPNN. NO equal-budget superiority claim',
            'Same fixed Q is not same Recall; QPS alone does not isolate distance-work or imply exact latency distribution',
            'The reported Recall is native tie-aware Recall; strict top10 was not independently computed here',
            'No PiPNN II, no novelty claim, no independent BUILD repetitions',
        ]
    }
    (out/'r26b_search_recovered_report.json').write_text(json.dumps(meta,indent=2,ensure_ascii=False)+'\n')
    summary = [
        'R26B_SEARCH_RECOVERY=PASS_SAME_NATIVE',
        'R26B_FULL_BUILD_AGAIN=NO',
        f'R26B_BUDGET_DELTA_PERCENT={meta["budget_delta_percent"]:+.3f}',
        'R26B_BUDGET_MATCHED=NO',
        *simple,
        'R26B_SEARCH_RECOVERY_LIMIT=UNMATCHED_BUDGET_AND_UNMATCHED_RECALL',
        'R26B_PIPNN_II_RUN=NO',
        'R26B_ALGORITHM_NOVELTY_CLAIM=NO',
        'R26B_SEARCH_RECOVERY_DONE='+str(out),
    ]
    (out/'r26b_search_recovered_summary.txt').write_text('\n'.join(summary)+'\n')
    print('\n'.join(summary))


def main():
    arg = argparse.ArgumentParser()
    arg.add_argument('mode',choices=['selftest','parse-one','report'])
    arg.add_argument('--out',type=Path)
    arg.add_argument('--log',type=Path)
    arg.add_argument('--q',type=int)
    a=arg.parse_args()
    if a.mode == 'selftest':selftest()
    elif a.mode == 'parse-one':
        if not a.log or not a.q:raise ValueError('REQUIRE_LOG_AND_Q')
        rows=parse(a.log,a.q)
        print(f'R26B_VERIFIED_FIXED_Q_STATS q={a.q} five_repeats={len(rows)} median_recall={statistics.median(row["recall_native_tie_aware"] for row in rows):.6f}')
    elif a.mode == 'report':
        if not a.out:raise ValueError('REQUIRE_OUT')
        report(a.out)

if __name__=='__main__':main()
