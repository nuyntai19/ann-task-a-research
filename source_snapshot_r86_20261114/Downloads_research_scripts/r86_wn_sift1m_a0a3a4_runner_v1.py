#!/usr/bin/env python3
"""R86 SIFT1M prefix W(n), provenance-pinned, counters-ON; isolated output.

Modes: --preflight-only (no build), --pilot (A0/10K only), --campaign (A0,A3,A4 x
10K/30K/100K/300K/1M, needs previously verified pilot), with resume-safe receipts.

Never edits source, input fbin, archived 100K benchmarks, or pre-existing graph.
ON wall-time is diagnostic only; never use as OFF BUILD time. This campaign is
an experimental scaling sweep, not a replay of the historical BIGANN1M G1 gate.
"""
from __future__ import annotations

import argparse
import collections
import csv
import hashlib
import json
import os
import re
import shutil
import struct
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT_DEFAULT = Path.home() / 'ann-task-a'
EXPECTED_SHA = {
    'base_100k': 'e50ff1bc34bcc6d1c97dd001023c09a666971cde64605cc06671ed8a8ff1ed12',
    'base_1m': '8c7b3d999ba3133f865af72df078f77c2d248fdb80571d7ea1f1bb8e1750658e',
    'stock_on': '396ef852992428cd3f935bcb33eeeeacc1bae565fbc4a441c1fa9d19720122ff',
    'h17_on': 'ef707479be221cb7a3c6257298d22f614678878f0a7bfc724dc8b28fabdd21c4',
}
ARM_SPEC = {
    'A0': {'kind': 'stock_on', 'C': 160, 'K': 1024, 'N': 2},
    'A3': {'kind': 'h17_on', 'C': 64, 'K': 512, 'N': 2},
    'A4': {'kind': 'h17_on', 'C': 64, 'K': 512, 'N': 1},
}
SIZES = (10_000, 30_000, 100_000, 300_000, 1_000_000)
CPUS = (0, 2, 4, 6)
REQUIRED_CMAKE = {'R70_USE_TIER': 'OFF', 'R86_USE_COUNTERS': 'ON'}
FLAG_SPEC = [
    ('-top_level_leaders', '100'), ('-fanout_scheme', '10,3,1'),
    ('-mst_deg', '2'), ('-prune', '1'), ('-prune_all', '1'),
    ('-prune_degree', '64'), ('-hash_bits', '12'),
    ('-alpha', '1.1'), ('-k', '0'),
]
SCRIPT_VERSION = 'R86_WN_SIFT1M_A0_A3_A4_ON_v1_0'


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for data in iter(lambda: f.read(4 * 1024 * 1024), b''):
            h.update(data)
    return h.hexdigest()


def check_fbin(path: Path, n: int) -> None:
    if not path.is_file():
        raise RuntimeError('FBIN_MISSING: ' + str(path))
    with path.open('rb') as f:
        raw = f.read(8)
    if len(raw) != 8 or struct.unpack('<II', raw) != (n, 128):
        raise RuntimeError('FBIN_SHAPE_HOLD: ' + str(path))
    expected = 8 + n * 128 * 4
    if path.stat().st_size != expected:
        raise RuntimeError(f'FBIN_BYTES_HOLD: {path} {path.stat().st_size} != {expected}')


def check_prefix(path: Path, source: Path, n: int) -> None:
    with path.open('rb') as a, source.open('rb') as b:
        a.seek(8)
        b.seek(8)
        left = n * 128 * 4
        while left:
            k = min(left, 4 * 1024 * 1024)
            if a.read(k) != b.read(k):
                raise RuntimeError('PREFIX_BYTES_HOLD: ' + str(path))
            left -= k


def read_cmake(path: Path) -> dict[str, str]:
    if not path.is_file():
        raise RuntimeError('CMAKE_CACHE_MISSING: ' + str(path))
    output = {}
    for line in path.read_text(errors='replace').splitlines():
        if ':' not in line or '=' not in line or line.startswith('//'):
            continue
        k = line.split(':', 1)[0]
        output[k] = line.split('=', 1)[1]
    return output


def bins_check(hist, n, C, occupied, full, scope):
    if not isinstance(hist, dict):
        raise RuntimeError('OCC_HIST_NOT_OBJECT ' + scope)
    if set(hist) != set(str(i) for i in range(C + 1)):
        raise RuntimeError('OCC_HIST_MISSING_BINS ' + scope)
    vals = [hist[str(i)] for i in range(C + 1)]
    if any(type(v) is not int or v < 0 for v in vals):
        raise RuntimeError('OCC_HIST_BAD_COUNT ' + scope)
    if sum(vals) != n or sum(i * v for i, v in enumerate(vals)) != occupied:
        raise RuntimeError('OCC_HIST_INVARIANT ' + scope)
    if vals[C] != full:
        raise RuntimeError('OCC_FULL_NODES_INVARIANT ' + scope)
    return vals


def paths_for(root: Path):
    bs = root / 'experiments/R86/gates/highway_r85_four_binary_jvYREW'
    name = 'algorithms/PipNN/neighbors-pipnn_FLOAT_T_EUCLIDEAN'
    binaries = {'stock_on': bs / 'build_stock_on' / name,
                'h17_on': bs / 'build_h17_on' / name}
    prefix = root / 'experiments/R86/scaling_wn_sift1m_prefixes_v1_0'
    inputs = {
        10_000: prefix / 'sift1m_prefix_10000.fbin',
        30_000: prefix / 'sift1m_prefix_30000.fbin',
        100_000: root / 'data/sift100k.fbin',
        300_000: prefix / 'sift1m_prefix_300000.fbin',
        1_000_000: root / 'data/sift1m.fbin',
    }
    out = root / '00_PROJECT_HOME/05_RESULTS_AND_COUNTERS' / SCRIPT_VERSION
    return binaries, inputs, prefix, out


def preflight(root: Path, out_override: Path | None):
    binary, inputs, pfx, out_default = paths_for(root)
    out = out_override.resolve() if out_override else out_default
    root_resolved = root.resolve()
    unsafe = [root_resolved / 'data', root_resolved / 'experiments/R86',
              root_resolved / 'experiments/R86/benchmarks']
    if any(out == p or p in out.parents for p in unsafe):
        raise RuntimeError('UNSAFE_OUTPUT_INSIDE_INPUT_SOURCE_OR_BENCHMARK')
    if out == root_resolved or root_resolved not in out.parents:
        raise RuntimeError('OUTPUT_MUST_BE_INSIDE_PROJECT_ROOT')

    if not shutil.which('taskset') or not Path('/usr/bin/time').is_file():
        raise RuntimeError('TASKSET_OR_GNU_TIME_UNAVAILABLE')
    affinity = os.sched_getaffinity(0) if hasattr(os, 'sched_getaffinity') else set()
    if not set(CPUS).issubset(affinity):
        raise RuntimeError(f'CPU_AFFINITY_HOLD wants={CPUS} available={sorted(affinity)}')
    if shutil.disk_usage(root).free < 2 * 1024**3:
        raise RuntimeError('FREE_DISK_LT_2_GIB_HOLD')
    memkb = None
    try:
        for line in Path('/proc/meminfo').read_text().splitlines():
            if line.startswith('MemAvailable:'):
                memkb = int(line.split()[1]); break
    except OSError:
        pass
    if memkb is not None and memkb < 4 * 1024 * 1024:
        raise RuntimeError('MEM_AVAILABLE_LT_4_GIB_HOLD')

    source = inputs[1_000_000]
    for n, path in inputs.items():
        check_fbin(path, n)
    if digest(source) != EXPECTED_SHA['base_1m']:
        raise RuntimeError('SIFT1M_PINNED_SHA_HOLD')
    if digest(inputs[100_000]) != EXPECTED_SHA['base_100k']:
        raise RuntimeError('SIFT100K_PINNED_SHA_HOLD')
    for n in SIZES[:-1]:
        check_prefix(inputs[n], source, n)
    manifest_file = pfx / 'prefix_manifest.json'
    if not manifest_file.is_file():
        raise RuntimeError('PREFIX_MANIFEST_MISSING')
    pre = json.loads(manifest_file.read_text())
    if pre.get('source_sha256') != EXPECTED_SHA['base_1m']:
        raise RuntimeError('PREFIX_MANIFEST_SOURCE_SHA_HOLD')
    input_hash = {}
    for n, f in inputs.items():
        h = digest(f)
        expect = pre.get('datasets', {}).get(str(n), {}).get('sha256')
        if h != expect or str(f) != pre['datasets'][str(n)].get('path'):
            raise RuntimeError(f'PREFIX_MANIFEST_INPUT_HOLD n={n}')
        input_hash[str(n)] = h

    binary_hash = {}
    for name, f in binary.items():
        if not f.is_file() or not os.access(f, os.X_OK):
            raise RuntimeError('BINARY_MISSING_OR_NOT_EXECUTABLE ' + str(f))
        h = digest(f)
        if h != EXPECTED_SHA[name]:
            raise RuntimeError(f'BINARY_SHA_MISMATCH {name}: {h}')
        cache = read_cmake(f.parent.parent.parent / 'CMakeCache.txt')
        want = {**REQUIRED_CMAKE, 'R71_USE_H17': 'OFF' if name == 'stock_on' else 'ON'}
        for key, v in want.items():
            if cache.get(key) != v:
                raise RuntimeError(f'CMAKE_FLAG_HOLD {name} {key}={cache.get(key)} want={v}')
        if cache.get('CMAKE_BUILD_TYPE') != 'Release':
            raise RuntimeError('CMAKE_RELEASE_FLAG_HOLD ' + name)
        binary_hash[name] = h

    ref_source = root / 'experiments/R86/r86_v1_2_source/algorithms/PipNN/r86_counters.hpp'
    if not ref_source.is_file():
        raise RuntimeError('COUNTER_SOURCE_HEADER_MISSING')
    text = ref_source.read_text(errors='replace')
    for flag in ('R86_COUNTER_OUT', 'R86_LEAF_SIZE_OUT', 'R86_OCCUPANCY_OUT',
                 'R86_DEGREES_PREFIX', 'require_output_paths', 'dump_jsonl_from_env'):
        if flag not in text:
            raise RuntimeError('COUNTER_INTERFACE_MISMATCH ' + flag)

    conf = dict(script_version=SCRIPT_VERSION, purpose='SIFT1M prefix W(n) ON logical work, not build OFF time',
                cpus=list(CPUS), threads=4, sizes=list(SIZES), arms=ARM_SPEC,
                input_sha256=input_hash, inputs={str(n):str(p) for n,p in inputs.items()},
                binary_sha256=binary_hash, binary_paths={k:str(v) for k,v in binary.items()},
                on_source_header=str(ref_source), base_source_sha=EXPECTED_SHA['base_1m'],
                flag_spec=[list(p) for p in FLAG_SPEC], source_note='G1 OFF original CLI reconstructed; R86 100K protocol C/K/N confirmed; ON instrumentation captured with env vars',
                gate_note='Separate scaling experiment; does not supersede historical 1M G1 HOLD')
    print('R86_WN_PINNED_PREFLIGHT_PASS', 'sizes', list(SIZES), 'arms', list(ARM_SPEC),
          'cpu', ','.join(map(str, CPUS)), 'output', out, flush=True)
    return out, conf, binary, inputs


def persist_manifest(out: Path, conf: dict):
    if out.exists() and not out.is_dir():
        raise RuntimeError('OUTPUT_PATH_NOT_DIRECTORY')
    out.mkdir(parents=True, exist_ok=True)
    dest = out / 'manifest.json'
    if dest.exists():
        if json.loads(dest.read_text()) != conf:
            raise RuntimeError('EXISTING_MANIFEST_DIFFERS_NO_OVERWRITE')
    else:
        dest.write_text(json.dumps(conf, sort_keys=True, indent=2) + '\n')
    return dest


def command_for(binary: Path, base: Path, graph: Path, spec: dict):
    src = [str(binary), '-base_path', str(base), '-graph_outfile', str(graph),
           '-num_clusters', str(spec['N']), '-cluster_size', str(spec['K'])]
    for flag, value in FLAG_SPEC:
        if flag == '-hash_bits':
            src.extend(['-table_size', str(spec['C'])])
        src.extend([flag, value])
    return ['taskset', '-c', ','.join(map(str, CPUS)), '/usr/bin/time',
            '-f', 'R86_WN_ON_TIME wall_s=%e peak_rss_kib=%M'] + src


def rows_jsonl(path: Path):
    with path.open(encoding='utf-8', errors='strict') as f:
        for ln, line in enumerate(f, 1):
            if not line.strip():
                continue
            try:
                data = json.loads(line)
            except Exception as e:
                raise RuntimeError(f'JSONL_BAD {path} line={ln}: {e}')
            if not isinstance(data, dict):
                raise RuntimeError(f'JSONL_ROW_NOT_OBJECT {path} line={ln}')
            yield data


def verify_run(run_dir: Path, n: int, arm: str, conf: dict):
    spec = ARM_SPEC[arm]
    graph = run_dir / 'index.graph'
    ctr = run_dir / 'work.counters.jsonl'
    leaf = run_dir / 'leaf.sizes.jsonl'
    occ = run_dir / 'reservoir.occupancy.jsonl'
    log = run_dir / 'native.build.log'
    degpre = run_dir / 'node_degree'
    must = [graph, ctr, leaf, occ, log]
    for p in must:
        if not p.is_file() or p.stat().st_size == 0:
            raise RuntimeError('MISSING_OR_EMPTY_RUN_OUTPUT ' + str(p))

    with graph.open('rb') as f:
        head = f.read(8)
    if head != struct.pack('<II', n, 64):
        raise RuntimeError('INDEX_GRAPH_HEADER_MISMATCH')
    counters = collections.Counter()
    perpass = collections.defaultdict(collections.Counter)
    num_ctr = 0
    metric_keys = set()
    for item in rows_jsonl(ctr):
        pid = item.get('pass_id')
        metric = item.get('metric_code')
        v = item.get('observed')
        if type(pid) is not int or type(v) is not int or v < 0 or not isinstance(metric, str):
            raise RuntimeError('COUNTER_ROW_SHAPE_HOLD')
        num_ctr += 1
        counters[metric] += v
        perpass[pid][metric] += v
        metric_keys.add(metric)
    for metric in ('W_P','W_A','W_L','leaf_count','proposals','merge_attempts'):
        if metric not in metric_keys or counters[metric] <= 0:
            raise RuntimeError('COUNTER_REQUIRED_POSITIVE_HOLD ' + metric)
    if num_ctr < 30:
        raise RuntimeError('COUNTER_TOO_FEW_ROWS')

    leaves = collections.defaultdict(list)
    leaf_rows = 0
    for item in rows_jsonl(leaf):
        pid, size = item.get('pass_id'), item.get('size')
        if type(pid) is not int or pid < 1 or pid > spec['N'] or type(size) is not int or size < 2 or size > spec['K']:
            raise RuntimeError('LEAF_ROW_SHAPE_HOLD')
        leaf_rows += 1
        leaves[pid].append(size)
    if leaf_rows == 0 or any(not leaves[pid] for pid in range(1, spec['N'] + 1)):
        raise RuntimeError('LEAF_ROWS_MISSING_PASS')
    for pid in range(1, spec['N'] + 1):
        wl = sum(s*s for s in leaves[pid])
        wp = sum(s*(s-1)//2 for s in leaves[pid])
        native_wl = perpass[pid]['W_L']
        native_pairs = perpass[pid]['W_pairs']
        if native_wl and wl > native_wl:
            raise RuntimeError(f'LEAF_WL_EXCEEDS_COUNTER pass={pid} from_leaf={wl} native={native_wl}')
        if native_pairs and wp > native_pairs:
            raise RuntimeError(f'LEAF_PAIRS_EXCEEDS_COUNTER pass={pid}')

    occs = list(rows_jsonl(occ))
    if len(occs) != spec['N'] + 1:
        raise RuntimeError(f'OCC_SNAPSHOT_COUNT_HOLD {len(occs)} instead of {spec["N"]+1}')
    bins_by_pass = {}
    for row in occs:
        pass_id = row.get('pass_id')
        if pass_id in bins_by_pass or type(pass_id) is not int or pass_id not in list(range(1, spec['N']+1)) + [0]:
            raise RuntimeError('OCC_PASS_IDS_HOLD')
        if row.get('n') != n or row.get('capacity') != spec['C']:
            raise RuntimeError('OCC_N_CAP_MISMATCH')
        stage = 'after_pass' if pass_id > 0 else 'pre_prune'
        if row.get('stage') != stage:
            raise RuntimeError('OCC_STAGE_MISMATCH')
        bins = bins_check(row.get('histogram'), n, spec['C'], row.get('occupied_slots'), row.get('full_nodes'), f'{arm}/{n}/pass{pass_id}')
        bins_by_pass[pass_id] = bins
    if bins_by_pass[0] != bins_by_pass[spec['N']]:
        raise RuntimeError('OCC_FINAL_SNAPSHOT_DIFFERS_LAST_PASS')
    for pid in range(1, spec['N'] + 1):
        degree = Path(str(degpre) + f'_pass{pid}.u32le')
        if not degree.is_file() or degree.stat().st_size != n * 4:
            raise RuntimeError('NODE_DEGREE_FILE_MISSING_OR_SHAPE_HOLD')
        hist = collections.Counter(x[0] for x in struct.iter_unpack('<I', degree.read_bytes()))
        if any(d > spec['C'] for d in hist) or [hist.get(j,0) for j in range(spec['C'] + 1)] != bins_by_pass[pid]:
            raise RuntimeError('NODE_DEGREE_HIST_MISMATCH')

    logtext = log.read_text(errors='replace')
    if ('Final prune time' not in logtext and 'final prune time' not in logtext) or 'build leaf time' not in logtext.lower():
        raise RuntimeError('NATIVE_STDOUT_EXPECTED_TIMERS_MISSING')
    summary = {
        'status': 'R86_WN_NATIVE_ON_PILOT_OR_RUN_AUDIT_PASS',
        'script_version': SCRIPT_VERSION,
        'arm': arm, 'n': n, 'C': spec['C'], 'K': spec['K'], 'N': spec['N'],
        'dataset_sha256': conf['input_sha256'][str(n)],
        'binary_sha256': conf['binary_sha256'][spec['kind']],
        'graph_sha256': digest(graph), 'graph_bytes': graph.stat().st_size,
        'counters_sha256': digest(ctr), 'leaf_sha256': digest(leaf),
        'occupancy_sha256': digest(occ), 'log_sha256': digest(log),
        'counter_rows': num_ctr, 'leaf_rows': leaf_rows,
        'W_P_total': counters['W_P'], 'W_A_total': counters['W_A'], 'W_L_total': counters['W_L'],
        'W_pairs_total': counters['W_pairs'], 'merge_attempts_total': counters['merge_attempts'],
        'proposals_total': counters['proposals'],
        'top2_q_writes_total': counters['top2_q_writes'],
        'collision_same_id_total': counters['collision_same_id'],
        'hash_moves_total': counters['hash_moves'],
        'prune_distance_calls_total': counters['prune_distance_calls'],
        'per_pass': {str(pid): dict(ctr) for pid, ctr in perpass.items() if pid <= spec['N']},
        'occupancy': {str(pid): {'occupied_slots': sum(d*c for d,c in enumerate(bins)),
                                 'full_nodes': bins[spec['C']]}
                       for pid,bins in bins_by_pass.items()},
        'caveat': 'ON timing not OFF BUILD. W(n) work models empirical; historical 1M G1 HOLD not replaced.',
    }
    return summary


def verify_existing(run_dir: Path, n: int, arm: str, conf: dict):
    receipt = run_dir / 'verified_receipt.json'
    if not receipt.is_file():
        raise RuntimeError('RUN_DIR_EXISTS_WITHOUT_VERIFIED_RECEIPT_NO_OVERWRITE: '+str(run_dir))
    result = verify_run(run_dir, n, arm, conf)
    command_manifest = run_dir / 'native_command.json'
    if not command_manifest.is_file():
        raise RuntimeError('NATIVE_COMMAND_RECORD_MISSING_NO_OVERWRITE')
    result['input_command_json_sha256'] = digest(command_manifest)
    old = json.loads(receipt.read_text())
    if old != result:
        raise RuntimeError('EXISTING_RECEIPT_DIFFERS_STOP: ' + str(run_dir))
    print('SKIP_VERIFIED_RECEIPT', arm, n, flush=True)
    return result


def run_one(out: Path, conf: dict, binaries, inputs, arm: str, n: int):
    run_dir = out / f'{arm}_n{n}'
    if run_dir.exists():
        return verify_existing(run_dir, n, arm, conf)
    run_dir.mkdir(parents=True, exist_ok=False)
    spec = ARM_SPEC[arm]
    cmd = command_for(binaries[spec['kind']], inputs[n], run_dir / 'index.graph', spec)
    env = os.environ.copy()
    env.update({'PARLAY_NUM_THREADS':'4',
                'R86_COUNTER_OUT': str(run_dir / 'work.counters.jsonl'),
                'R86_LEAF_SIZE_OUT': str(run_dir / 'leaf.sizes.jsonl'),
                'R86_OCCUPANCY_OUT': str(run_dir / 'reservoir.occupancy.jsonl'),
                'R86_DEGREES_PREFIX': str(run_dir / 'node_degree')})
    (run_dir / 'native_command.json').write_text(json.dumps({
        'cmd': cmd, 'environment': {k:env[k] for k in (
            'PARLAY_NUM_THREADS','R86_COUNTER_OUT','R86_LEAF_SIZE_OUT',
            'R86_OCCUPANCY_OUT','R86_DEGREES_PREFIX')},
        'input_sha256': conf['input_sha256'][str(n)],
        'binary_sha256': conf['binary_sha256'][spec['kind']]},indent=2) + '\n')
    print('RUN_NATIVE_ON', arm, 'n', n, 'cmd_path', run_dir / 'native_command.json',flush=True)
    with (run_dir / 'native.build.log').open('x') as log:
        proc = subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT,env=env, check=False)
    if proc.returncode != 0:
        raise RuntimeError(f'BUILD_EXIT_NONZERO arm={arm} n={n} exit={proc.returncode}; inspect {run_dir / "native.build.log"}; no overwrite')
    receipt = verify_run(run_dir,n,arm,conf)
    receipt['input_command_json_sha256'] = digest(run_dir / 'native_command.json')
    # Compute a separate build-run digest; verification uses it as an audit trail.
    (run_dir/'verified_receipt.json').write_text(json.dumps(receipt,sort_keys=True,indent=2)+'\n')
    print('R86_WN_RUN_AUDIT_PASS',arm,n,'W_P',receipt['W_P_total'],'W_L',receipt['W_L_total'],
          'merge_attempts',receipt['merge_attempts_total'],flush=True)
    return receipt


def validate_receipt(run_dir: Path,n: int,arm: str,conf:dict):
    r = verify_run(run_dir,n,arm,conf)
    r['input_command_json_sha256'] = digest(run_dir/'native_command.json')
    old = json.loads((run_dir/'verified_receipt.json').read_text())
    if r != old:
        raise RuntimeError(f'RECEIPT_REVALIDATION_MISMATCH {arm} {n}')
    return r


def write_campaign_summary(out: Path, conf: dict):
    results = []
    for n in SIZES:
        for arm in ARM_SPEC:
            p = out/f'{arm}_n{n}'
            results.append(validate_receipt(p,n,arm,conf))
    dest = out/'campaign_summary.csv'
    if dest.exists():
        existing = list(csv.DictReader(dest.open(newline='')))
        if len(existing) == 15 and all(
            str(x['graph_sha256']) == str(y['graph_sha256']) and
            str(x['W_P_total']) == str(y['W_P_total']) and
            str(x['W_L_total']) == str(y['W_L_total'])
            for x,y in zip(existing, results)
        ):
            print('SUMMARY_ALREADY_EXISTS_VERIFIED', dest)
            return
        raise RuntimeError('EXISTING_SUMMARY_DIFFERS_STOP_NO_OVERWRITE')
    with dest.open('x',newline='') as f:
        fieldnames = ['arm','n','C','K','N','W_P_total','W_A_total','W_L_total','W_pairs_total',
                      'merge_attempts_total','proposals_total','top2_q_writes_total',
                      'collision_same_id_total','hash_moves_total','prune_distance_calls_total',
                      'graph_bytes','graph_sha256','status']
        writer=csv.DictWriter(f,fieldnames=fieldnames,extrasaction='ignore')
        writer.writeheader()
        writer.writerows(results)
    print('R86_WN_15_RUNS_AUDITED_CSV_READY',dest)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument('--preflight-only',action='store_true')
    mode.add_argument('--pilot',action='store_true')
    mode.add_argument('--campaign',action='store_true')
    ap.add_argument('--root',type=Path,default=ROOT_DEFAULT)
    ap.add_argument('--out',type=Path,default=None,
                    help='Isolated output under ann-task-a; does not overwrite old experiment data.')
    ap.add_argument('--max-new-runs',type=int,default=None,
                    help='For campaign smoke test; newly built runs counted, verified receipts skipped.')
    args=ap.parse_args()
    if args.max_new_runs is not None and args.max_new_runs < 1:
        raise RuntimeError('MAX_NEW_RUNS_MUST_BE_POSITIVE')
    root=args.root.expanduser().resolve()
    out,conf,binaries,inputs=preflight(root,args.out)
    if args.preflight_only:
        print('R86_WN_PREFLIGHT_ONLY_NO_BUILD');return
    persist_manifest(out,conf)
    if args.pilot:
        run_one(out,conf,binaries,inputs,'A0',10_000)
        print('R86_WN_A0_N10000_PILOT_PASS_STOP_BEFORE_CAMPAIGN')
        return
    pilot = out/'A0_n10000'
    if not (pilot/'verified_receipt.json').is_file():
        raise RuntimeError('PILOT_NOT_VERIFIED_REFUSE_CAMPAIGN_RUN_--pilot_FIRST')
    validate_receipt(pilot,10_000,'A0',conf)
    print('R86_WN_PILOT_GATE_PASS',flush=True)
    count = 0
    for n in SIZES:
        for arm in ARM_SPEC:
            path=out/f'{arm}_n{n}'
            existed=path.exists()
            run_one(out,conf,binaries,inputs,arm,n)
            if not existed:
                count+=1
                if args.max_new_runs is not None and count>=args.max_new_runs:
                    print('R86_WN_PARTIAL_SAFE_STOP_AFTER_NEW_RUNS',count)
                    return
    write_campaign_summary(out,conf)
    print('R86_WN_CAMPAIGN_COMPLETE_15_ARMS_X_SIZES')

if __name__ == '__main__':
    try:main()
    except Exception as exc:
        print('R86_WN_HOLD',str(exc),file=sys.stderr,flush=True)
        sys.exit(1)
