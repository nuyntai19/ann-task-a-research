#!/usr/bin/env python3
"""Read-only search campaign on 15 prebuilt SIFT100K OFF graphs.

R70 native evaluator (from a validated A0 smoke); does NOT compile, build, or
modify any input. Measurements are five fixed-beam points, not matched-recall
interpolated latency, nor per-query P95/P99. Records raw repeated QPS separately
from independent graph-build repetitions.
"""
import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import statistics
import struct
import subprocess
import sys
import time

ARMS = [
    ("A0", "stock_C160_K1024_N2"),
    ("A1", "h17_C160_K1024_N2"),
    ("A2", "h17_C64_K1024_N2"),
    ("A3", "h17_C64_K512_N2"),
    ("A4", "h17_C64_K512_N1"),
]
SHA = {
    "base": "e50ff1bc34bcc6d1c97dd001023c09a666971cde64605cc06671ed8a8ff1ed12",
    "query": "9e9328e3f0488840d3f12efcc3b0f6af940dd398fb7b6d178d72bd1e1c0f9d74",
    "gt": "e038aff5970977d0ee925b4357295bd81817b99b35e11bbab783fd64e0715e7f",
    "evaluator": "f3999051c6cc96434ea26d2faedd3ac632ed8d20be342e15c92fd4b905a33fe9",
}
BEAMS = (10, 20, 40, 80, 160)
ROW = re.compile(r'^R70_RECALL_ROW beam=(\d+) recall=([0-9.]+) qps=([0-9.]+) avg_cmps=([0-9.]+) avg_visited=([0-9.]+)\s*$', re.M)
FIELDS = ["arm_id", "build_rep", "search_rep", "run_id", "graph_sha256",
          "beam", "recall_at10", "qps", "avg_cmps", "avg_visited", "qps_inverse_us",
          "evaluator_sha256", "base_sha256", "query_sha256", "gt_sha256", "log_path"]


def sha_file(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(4 * 1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def check(cond, message):
    if not cond:
        raise RuntimeError('PREFLIGHT_FAIL ' + message)


def parse_output(out):
    check(out.count('R70_RECALL_EVAL_PASS') == 1, 'missing/duplicate R70_RECALL_EVAL_PASS')
    found = ROW.findall(out)
    check(len(found) == len(BEAMS), f'got {len(found)} beam rows, expected {len(BEAMS)}')
    result = []
    for i, (b, recall, qps, cmps, visited) in enumerate(found):
        beam = int(b)
        r, q, c, v = map(float, (recall, qps, cmps, visited))
        check(beam == BEAMS[i], f'beam sequence mismatch: {b}')
        check(0 <= r <= 1 and q > 0 and c >= 0 and v >= 0, f'invalid metrics beam={b}')
        result.append(dict(beam=beam, recall_at10=r, qps=q,
                           avg_cmps=c, avg_visited=v, qps_inverse_us=1_000_000.0 / q))
    return result


def store_csv(path, rows, cols):
    tmp = path.with_suffix(path.suffix + '.part')
    with open(tmp, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
    tmp.replace(path)


def run_manifest(args):
    home = Path.home()
    repo = home / 'ann-task-a'
    hub = repo / '00_PROJECT_HOME'
    graph_root = hub / '04_RUNS_AND_GRAPHS' / 'SIFT100K_A0_A4_20_RUNS'
    files = {
        'base': repo / 'data' / 'sift100k.fbin',
        'query': repo / 'data' / 'sift100k_queries_300.fbin',
        'gt': repo / 'data' / 'sift100k_gt300.ibin',
        'evaluator': repo / 'experiments' / 'H70' / 'build-r70' / 'algorithms' / 'PipNN' / 'r70_graph_recall',
    }
    check(shutil.which('taskset') is not None, 'taskset command missing')
    for name, path in files.items():
        check(path.is_file(), f'{name} missing: {path}')
        found = sha_file(path)
        check(found == SHA[name], f'{name} SHA mismatch {found}')
        print(f'INPUT_SHA_PASS {name} {found}', flush=True)
    check(os.access(files['evaluator'], os.X_OK), 'evaluator not executable')
    check(graph_root.is_dir(), 'graph root missing: ' + str(graph_root))
    csv_path = graph_root / 'runs.csv'
    check(csv_path.is_file(), 'runs.csv missing')
    with csv_path.open(newline='', encoding='utf-8') as f:
        entries = list(csv.DictReader(f))
    check(len(entries) == 20, f'runs.csv has {len(entries)} rows; expected 20')
    all_names = {e.get('run_id') for e in entries}
    expected_all = {f'{prefix}_{mode}_r{r}' for _, prefix in ARMS
                    for mode in ('off', 'on') for r in ((1, 2, 3) if mode == 'off' else (1,))}
    check(all_names == expected_all, f'wrong run IDs: missing={expected_all-all_names}, extra={all_names-expected_all}')
    check('graph_sha256' in entries[0], 'runs.csv lacks graph_sha256 column')
    byname = {e['run_id']: e for e in entries}
    graph_rows = []
    for arm, prefix in ARMS:
        for rep in (1, 2, 3):
            name = f'{prefix}_off_r{rep}'
            graph = graph_root / name / (name + '.graph')
            check(graph.is_file() and graph.stat().st_size > 400008, 'missing/truncated graph: ' + str(graph))
            h = sha_file(graph)
            check(h == byname[name]['graph_sha256'], 'graph sha mismatch '+name)
            with graph.open('rb') as f:
                n, cap = struct.unpack('<II', f.read(8))
            check((n, cap) == (100000, 64), f'unexpected graph header for {name}: {n},{cap}')
            graph_rows.append(dict(arm_id=arm, build_rep=rep, run_id=name,
                                   graph_path=str(graph), graph_sha256=h))
    check(len(graph_rows) == 15, 'expected 15 OFF graphs')
    print('GRAPH_SHA_PASS_15_OFF', flush=True)
    print('PRECHECK_APPROVED_R70_STORED_GRAPH_EVALUATOR', flush=True)
    return repo, hub, graph_root, files, graph_rows


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument('--preflight', action='store_true')
    mode.add_argument('--run', action='store_true')
    p.add_argument('--search-reps', type=int, default=3, help='Repeated search executions for every graph (default 3)')
    p.add_argument('--output', type=Path, help='Optional fresh output path; defaults under 00_PROJECT_HOME/05_RESULTS_AND_COUNTERS')
    p.add_argument('--cpu', type=int, default=0, help='Pinned logical CPU for sequential single-thread native search (default 0)')
    p.add_argument('--timeout', type=int, default=600, help='Timeout seconds for each evaluator execution')
    args = p.parse_args()
    check(1 <= args.search_reps <= 15, 'search reps out of range 1..15')
    check(0 <= args.cpu < (os.cpu_count() or 1), 'CPU id out of range')
    repo, hub, graph_root, files, graph_rows = run_manifest(args)
    output = args.output or hub / '05_RESULTS_AND_COUNTERS' / 'R70_SIFT100K_A0_A4_15OFF_v1_0'
    check(not output.exists() and not output.is_symlink(), f'output exists, refusing overwrite: {output}')
    check(output.parent.is_dir(), f'output parent absent: {output.parent}')
    print(f'OUTPUT_DIR={output}')
    print(f'CAMPAIGN_PLAN={len(graph_rows)} graphs x {args.search_reps} repeated searches = {len(graph_rows)*args.search_reps} native calls')
    print(f'CPU_PIN={args.cpu}  SEARCH_THREADS=1  BEAMS={list(BEAMS)}  QUERIES=300 K=10')
    if args.preflight:
        print('PREFLIGHT_ONLY_NO_SEARCH')
        return

    output.mkdir(parents=False, exist_ok=False)
    logs = output / 'raw_logs'
    logs.mkdir()
    manifest = dict(
        campaign='R70_SIFT100K_A0_A4_15OFF',
        date_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        search_reps=args.search_reps, beams=list(BEAMS), k=10, queries=300,
        cpu=args.cpu, threads=1, input_sha256=SHA,
        graphs=graph_rows,
        evaluator=str(files['evaluator']),
        limitations=['single logical CPU; 300 queries each process',
                     'QPS inverse is throughput-equivalent time, not measured per-query P95/P99',
                     'five coarse beams; not an exactly matched-Recall latency sweep',
                     'ANN distance calculations measured at search differ from build W_P/W_L',
                     'build repetitions and repeated searches are distinct independent axes',
                     'not a full graph connectivity audit'],
    )
    (output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    by_key = {(e['arm_id'], e['build_rep']): e for e in graph_rows}
    records = []
    env = os.environ.copy()
    env.update({'PARLAY_NUM_THREADS':'1', 'OMP_NUM_THREADS':'1', 'OPENBLAS_NUM_THREADS':'1',
                'MKL_NUM_THREADS':'1', 'VECLIB_MAXIMUM_THREADS':'1'})
    for search_rep in range(1, args.search_reps + 1):
        for build_rep in (1, 2, 3):
            rotate = (search_rep + build_rep - 2) % len(ARMS)
            seq = ARMS[rotate:] + ARMS[:rotate]
            for arm_id, _ in seq:
                graph = by_key[(arm_id, build_rep)]
                run_name = graph['run_id']
                logfile = logs / f'{run_name}__s{search_rep}.log'
                cmd = ['taskset', '-c', str(args.cpu), str(files['evaluator']),
                       graph['graph_path'], str(files['base']), str(files['query']), str(files['gt'])]
                print('SEARCH_START', arm_id, run_name, 'search_rep', search_rep, flush=True)
                try:
                    r = subprocess.run(cmd, env=env, stdout=subprocess.PIPE,
                                       stderr=subprocess.STDOUT, text=True, timeout=args.timeout,
                                       check=False)
                except subprocess.TimeoutExpired as e:
                    logfile.write_text((e.stdout or b'').decode('utf8', errors='replace') if isinstance(e.stdout, bytes) else (e.stdout or ''), encoding='utf-8')
                    raise RuntimeError(f'SEARCH_TIMEOUT {run_name} search_rep={search_rep} log={logfile}')
                logfile.write_text(r.stdout, encoding='utf-8')
                check(r.returncode == 0, f'evaluator return code {r.returncode}; log={logfile}')
                vals = parse_output(r.stdout)
                for row in vals:
                    records.append(dict(arm_id=arm_id, build_rep=build_rep,
                                        search_rep=search_rep, run_id=run_name,
                                        graph_sha256=graph['graph_sha256'], **row,
                                        evaluator_sha256=SHA['evaluator'], base_sha256=SHA['base'],
                                        query_sha256=SHA['query'], gt_sha256=SHA['gt'],
                                        log_path=str(logfile)))
                store_csv(output / 'search_all_rows.csv', records, FIELDS)
                print('SEARCH_PASS', arm_id, run_name, 'search_rep', search_rep,
                      'rows', len(vals), flush=True)

    summaries=[]
    for arm_id, prefix in ARMS:
        for beam in BEAMS:
            graph_vals=[]
            for br in (1,2,3):
                select = [r for r in records if r['arm_id']==arm_id and r['build_rep']==br and r['beam']==beam]
                check(len(select)==args.search_reps, f'missing search repetitions {arm_id} {br} {beam}')
                graph_vals.append({col:statistics.median(float(r[col]) for r in select)
                                   for col in ('recall_at10','qps','avg_cmps','avg_visited','qps_inverse_us')})
            out = {'arm_id':arm_id,'beam':beam,'n_graphs':3,'search_reps_per_graph':args.search_reps}
            for col in ('recall_at10','qps','avg_cmps','avg_visited','qps_inverse_us'):
                v=[x[col] for x in graph_vals]
                out[f'{col}_median']=statistics.median(v)
                out[f'{col}_min']=min(v)
                out[f'{col}_max']=max(v)
            summaries.append(out)
    summary_cols=list(summaries[0])
    store_csv(output / 'arm_beam_summary.csv',summaries,summary_cols)
    (output/'arm_beam_summary.json').write_text(json.dumps({'manifest':manifest,'summary':summaries},indent=2)+'\n',encoding='utf-8')
    print('SEARCH_CAMPAIGN_COMPLETE_15_GRAPHS',flush=True)
    print('RAW_ROWS='+str(output/'search_all_rows.csv'),flush=True)
    print('ARM_SUMMARY='+str(output/'arm_beam_summary.csv'),flush=True)
    print('OUTPUT_DIR='+str(output),flush=True)
    print('MATCHED_RECALL_AND_P95_P99_NOT_MEASURED',flush=True)


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print(f'SEARCH_CAMPAIGN_HOLD {exc}',file=sys.stderr,flush=True)
        sys.exit(1)
