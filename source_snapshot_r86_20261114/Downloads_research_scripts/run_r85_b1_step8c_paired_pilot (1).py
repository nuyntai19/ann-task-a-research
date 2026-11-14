#!/usr/bin/env python3
"""R85-B1 Step8C: safe same-process paired P1/P2 export, SIFT100K pilot.

Reuses the SHA-pinned Step5/A4 command derivation. Only changes the pinned
native binary and adds R85_B1_P1_GRAPH_OUTFILE to export P1 from the N2 run.
No snapshot TSV serialization, dataset BUILD benchmark, source edit, or SEARCH.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import time

HOME = Path.home()
BASE = HOME / 'ann-task-a/experiments/H85/r85_b1_controlled'
SRC = BASE / 'isolation_v4/source/algorithms/PipNN/pipnn.h'
BINARY = BASE / 'isolation_v4/cmake-build/algorithms/PipNN/neighbors-pipnn_FLOAT_T_EUCLIDEAN'
STEP5 = HOME / 'Downloads/run_r85_b1_step5_pilot.py'
DATA = HOME / 'ann-task-a/data/sift100k.fbin'
OUTROOT = BASE / 'paired_p1p2_sift100k'

PIN_BINARY = '59f8597d7f5e22db86f65b7327a50dcfed241adf9b0085728bb0bd6ee1eccfd5'
PIN_SOURCE = '1857b1acd8e4af1a6afdec3d8b777ad7faf6b277b53acf2ac6513876b2abe923'
PIN_STEP5 = 'b7ffd832c1e4b2088fa8a690b82dcaf5ff4eb78983c034435594b491ef286949'
PIN_DATA = 'e50ff1bc34bcc6d1c97dd001023c09a666971cde64605cc06671ed8a8ff1ed12'
PIN_A4 = 'b9db158b022d9df9633817031282d68e45f7c0ee9236d2b7059aa184d73e3106'
PIN_H70 = 'f4391ad8712d7757423dca872f9042c3271660dffde384a85b93854b9692f288'
ARM = 'C64_K512_N2'


def die(msg):
    raise RuntimeError(msg)


def sha(path):
    hasher = hashlib.sha256()
    with path.open('rb') as f:
        for data in iter(lambda: f.read(1024 * 1024), b''):
            hasher.update(data)
    return hasher.hexdigest()


def require_file(path, expected, label):
    if path.is_symlink() or not path.is_file():
        die(f'MISSING_OR_SYMLINK_{label} {path}')
    got = sha(path)
    if got != expected:
        die(f'SHA_DRIFT_{label} expected={expected} got={got}')


def load_step5():
    spec = importlib.util.spec_from_file_location('r85_b1_step5_pinned_for_pair', STEP5)
    if not spec or not spec.loader:
        die('CANNOT_IMPORT_STEP5')
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def validate_command(cmd, graph, data):
    cmd = [str(x) for x in cmd]
    expected = {
        '-num_clusters': '2', '-cluster_size': '512',
        '-table_size': '64', '-top_level_leaders': '100',
        '-fanout_scheme': '10,3,1', '-mst_deg': '2',
        '-prune': '1', '-prune_all': '1', '-prune_degree': '64',
        '-hash_bits': '12', '-alpha': '1.1', '-k': '0',
        '-base_path': str(data), '-graph_outfile': str(graph),
    }
    if not cmd or cmd[0] != str(BINARY):
        die('WRONG_BINARY_IN_DERIVED_COMMAND')
    if cmd.count(str(graph)) != 1 or cmd.count(str(data)) != 1:
        die('WRONG_DATA_OR_OUTPUT_IN_DERIVED_COMMAND')
    for flag, value in expected.items():
        if cmd.count(flag) != 1 or cmd[cmd.index(flag) + 1] != value:
            die(f'CLI_PROTOCOL_DRIFT {flag} expected={value}')
    return cmd


def derive(step5, graph):
    # Step5 imported only after hash checking. Its derivation validates the pinned
    # A4 native command and the unchanged A4 source/data dependencies.
    original = step5.NEW_BINARY
    try:
        step5.NEW_BINARY = BINARY
        commands = step5.derive_commands({
            'C64_K512_N1': graph.parent / 'NO_RUN_N1.graph',
            'C64_K512_N2': graph,
        })
    finally:
        step5.NEW_BINARY = original
    return validate_command(commands[ARM], graph, DATA)


def preflight():
    require_file(BINARY, PIN_BINARY, 'B1_PAIRED_BINARY')
    require_file(SRC, PIN_SOURCE, 'B1_PAIRED_HEADER')
    require_file(STEP5, PIN_STEP5, 'B1_STEP5_RUNNER')
    m = load_step5()
    require_file(m.A4, PIN_A4, 'A4_RUNNER')
    require_file(m.H70_HEADER, PIN_H70, 'H70_HEADER')
    require_file(DATA, PIN_DATA, 'SIFT100K')
    info = m.fbin(DATA)
    if info['n'] != 100_000 or info['dim'] != 128:
        die('SIFT100K_DIMENSIONS_DRIFT')
    if not BASE.is_dir() or BASE.is_symlink():
        die('INVALID_B1_BASE_DIRECTORY')
    if OUTROOT.is_symlink():
        die('OUTPUT_ROOT_IS_SYMLINK')
    if not shutil.which('taskset'):
        die('TASKSET_UNAVAILABLE')
    if 0 not in os.sched_getaffinity(0):
        die('CPU0_NOT_ALLOWED')
    if shutil.disk_usage(BASE).free < 3 * 1024**3:
        die('INSUFFICIENT_DISK_SPACE_LT_3_GIB')
    cmd = derive(m, Path('/NO_WRITE_B1_PREFLIGHT/P2.graph'))
    print('R85_B1_STEP8C_BINARY_SHA256 ' + PIN_BINARY, flush=True)
    print('R85_B1_STEP8C_HEADER_SHA256 ' + PIN_SOURCE, flush=True)
    print('R85_B1_STEP8C_INPUT ' + json.dumps(info, sort_keys=True), flush=True)
    print('R85_B1_STEP8C_DRY_CMD ' + shlex.join(['taskset', '-c', '0'] + cmd), flush=True)
    print('R85_B1_STEP8C_PREFLIGHT_PASS_NO_BUILD', flush=True)
    return m, info


def validate_native_log(log_text, p1, p2):
    markers = (
        'R70_RESERVOIR_VARIANT=STOCK_FLAT_C64',
        'R71_SELECTION_VARIANT=H17_PACKED_TOP2',
        'R85_B1_PAIRED_RESERVOIR_UNCHANGED_PASS',
        'R85_B1_PAIRED_P1_EXPORT_PASS file=' + str(p1),
        'Built cluster 0 of 2',
        'Built cluster 1 of 2',
        'Writing graph to ' + str(p2),
    )
    for marker in markers:
        if marker not in log_text:
            die('NATIVE_REQUIRED_MARKER_MISSING ' + marker)
    if log_text.count('R85_B1_PAIRED_P1_EXPORT_PASS') != 1 or log_text.count('R85_B1_PAIRED_RESERVOIR_UNCHANGED_PASS') != 1:
        die('PAIRED_MARKERS_NOT_UNIQUE')
    if 'R85_B1_PAIRED_RESERVOIR_MUTATED_BY_P1_EXPORT' in log_text:
        die('RESERVOIR_MUTATED')
    # Guard order: first round finishes, P1 guard/export, second round finishes.
    i1 = log_text.index('R85_B1_PAIRED_RESERVOIR_UNCHANGED_PASS')
    i2 = log_text.index('R85_B1_PAIRED_P1_EXPORT_PASS')
    i3 = log_text.index('Built cluster 0 of 2')
    i4 = log_text.index('Built cluster 1 of 2')
    if not i1 < i2 < i3 < i4:
        die('PAIRED_NATIVE_EVENT_ORDER_INVALID')


def new_session():
    if OUTROOT.exists() and not OUTROOT.is_dir():
        die('OUTPUT_ROOT_NOT_DIRECTORY')
    OUTROOT.mkdir(parents=True, exist_ok=True)
    if OUTROOT.is_symlink():
        die('OUTPUT_ROOT_BECAME_SYMLINK')
    p = OUTROOT / ('pair_' + datetime.now().strftime('%Y%m%d-%H%M%S') + '_' + str(os.getpid()))
    p.mkdir(exist_ok=False)
    return p


def write_json_exclusive(path, data):
    with path.open('x', encoding='utf8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write('\n')


def run_pair(m, input_info):
    session = new_session()
    p1, p2 = session / 'P1.graph', session / 'P2.graph'
    if p1.exists() or p2.exists():
        die('OUTPUT_GRAPH_ALREADY_EXISTS')
    cmd = derive(m, p2)
    cwd = Path(m.load_a4_module().ROOT).resolve(strict=True)
    env = dict(os.environ)
    env.pop('R85_B1_SNAPSHOT_DIR', None)
    env['R85_B1_P1_GRAPH_OUTFILE'] = str(p1)
    for name in ('PARLAY_NUM_THREADS', 'OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS',
                 'MKL_NUM_THREADS', 'VECLIB_MAXIMUM_THREADS', 'NUMEXPR_NUM_THREADS'):
        env[name] = '1'
    native = ['taskset', '-c', '0'] + cmd
    manifest = {
        'scope': 'B1 same-process P1/P2 paired export, SIFT100K, not BUILD benchmark',
        'binary_sha256': PIN_BINARY, 'instrumented_header_sha256': PIN_SOURCE,
        'input': str(DATA), 'input_info': input_info, 'threads': 1, 'cpus': [0],
        'arm': ARM, 'cwd': str(cwd), 'command': native,
        'p1_export_env': 'R85_B1_P1_GRAPH_OUTFILE',
        'p1': str(p1), 'p2': str(p2),
        'snapshot_tsv_disabled': True,
        'created_utc': datetime.now(timezone.utc).isoformat(),
    }
    write_json_exclusive(session / 'manifest.json', manifest)
    print('R85_B1_STEP8C_SESSION ' + str(session), flush=True)
    print('R85_B1_STEP8C_BUILD_START ' + shlex.join(native), flush=True)
    start = time.monotonic()
    with (session / 'native.log').open('x', encoding='utf8') as f:
        with subprocess.Popen(native, cwd=str(cwd), env=env, stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT, text=True, errors='replace',
                              bufsize=1) as proc:
            for line in proc.stdout:
                f.write(line)
                if ('R85_B1_PAIRED_' in line or 'Built cluster ' in line or
                    'R71_SELECTION_VARIANT=' in line or 'R70_RESERVOIR_VARIANT=' in line or
                    'Writing graph to ' in line):
                    print(line.rstrip(), flush=True)
            returncode = proc.wait()
    elapsed = round(time.monotonic() - start, 3)
    if returncode:
        die(f'NATIVE_FAILED rc={returncode} log={session / "native.log"}')
    validate_native_log((session / 'native.log').read_text(errors='replace'), p1, p2)
    result = {'scope': 'P1/P2 native file existence and provenance; STRUCTURE/RECALL NOT YET CHECKED',
              'wall_with_export_overhead_s': elapsed, 'exit_code': returncode,
              'files': {}}
    for label, path in [('P1', p1), ('P2', p2)]:
        if path.is_symlink() or not path.is_file() or path.stat().st_size <= 100_000:
            die(f'{label}_GRAPH_MISSING_OR_IMPLAUSIBLY_SMALL {path}')
        result['files'][label] = {'path': str(path), 'bytes': path.stat().st_size,
                                  'sha256': sha(path)}
    if result['files']['P1']['sha256'] == result['files']['P2']['sha256']:
        die('P1_P2_GRAPH_SHA_EQUAL_UNEXPECTED')
    write_json_exclusive(session / 'result.json', result)
    print('R85_B1_STEP8C_PAIRED_OUTPUTS ' + json.dumps(result, sort_keys=True), flush=True)
    print('R85_B1_STEP8C_EXPORT_PILOT_PASS_GRAPH_QUALITY_PENDING ' + str(session), flush=True)


def selftest():
    sample = [str(BINARY), '-base_path', str(DATA), '-graph_outfile', '/tmp/p2.graph',
              '-num_clusters', '2', '-cluster_size', '512', '-table_size', '64',
              '-top_level_leaders', '100', '-fanout_scheme', '10,3,1',
              '-mst_deg', '2', '-prune', '1', '-prune_all', '1',
              '-prune_degree', '64', '-hash_bits', '12', '-alpha', '1.1', '-k', '0']
    validate_command(sample, Path('/tmp/p2.graph'), DATA)
    log = ('R70_RESERVOIR_VARIANT=STOCK_FLAT_C64\n'
           'R71_SELECTION_VARIANT=H17_PACKED_TOP2\n'
           'R85_B1_PAIRED_RESERVOIR_UNCHANGED_PASS values=400\n'
           'R85_B1_PAIRED_P1_EXPORT_PASS file=/tmp/p1.graph\n'
           'Built cluster 0 of 2\n'
           'Built cluster 1 of 2\n'
           'Writing graph to /tmp/p2.graph\n')
    validate_native_log(log, Path('/tmp/p1.graph'), Path('/tmp/p2.graph'))
    try:
        validate_command(sample[:-2] + ['-k', '10'], Path('/tmp/p2.graph'), DATA)
    except RuntimeError:
        pass
    else:
        die('SELFTEST_INVALID_CLI_ACCEPTED')
    try:
        validate_native_log(log.replace('RESERVOIR_UNCHANGED_PASS', 'RESERVOIR_MUTATED_BY_P1_EXPORT'),
                            Path('/tmp/p1.graph'), Path('/tmp/p2.graph'))
    except RuntimeError:
        pass
    else:
        die('SELFTEST_BAD_LOG_ACCEPTED')
    print('R85_B1_STEP8C_SELFTEST_PASS_NO_BUILD')


def main():
    p = argparse.ArgumentParser()
    x = p.add_mutually_exclusive_group(required=True)
    x.add_argument('--selftest', action='store_true')
    x.add_argument('--preflight', action='store_true')
    x.add_argument('--run', action='store_true')
    p.add_argument('--confirm-pair', action='store_true')
    a = p.parse_args()
    if a.selftest:
        selftest()
        return
    if a.run and not a.confirm_pair:
        die('MISSING_--confirm-pair')
    m, info = preflight()
    if a.run:
        run_pair(m, info)


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print('R85_B1_STEP8C_FAIL_CLOSED ' + repr(e), file=sys.stderr, flush=True)
        sys.exit(2)
