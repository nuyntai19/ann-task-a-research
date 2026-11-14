#!/usr/bin/env python3
"""R85-B1 Step5: fail-closed SIFT100K N1/N2 candidate-snapshot pilot.

Reuse *exact* old A4 native CLI generator, replace only the pinned base dataset,
output graph and verified binary. No modifications to H70, A4 or A4c. Snapshot
serialization is observational and included in elapsed time.
"""
from __future__ import annotations
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import importlib.util
import itertools
import json
import os
from pathlib import Path
import shlex
import shutil
import struct
import subprocess
import sys
import time

HOME = Path.home()
BASE = HOME / 'ann-task-a/experiments/H85/r85_b1_controlled'
ROOT = BASE / 'isolation_v3'
A4 = HOME / 'Downloads/run_r85_a4_paired_sift1m.py'
NEW_BINARY = ROOT / 'cmake-build/algorithms/PipNN/neighbors-pipnn_FLOAT_T_EUCLIDEAN'
NEW_HEADER = ROOT / 'source/algorithms/PipNN/pipnn.h'
H70_HEADER = HOME / 'ann-task-a/experiments/H70/pipnn-clean-443a328/algorithms/PipNN/pipnn.h'
DATA = HOME / 'ann-task-a/data/sift100k.fbin'
OUTROOT = BASE / 'pilot_sift100k'
PIN_A4 = 'b9db158b022d9df9633817031282d68e45f7c0ee9236d2b7059aa184d73e3106'
PIN_BIN = '1edb96e4a2ec8dd0609154bce51dbf020ca27b74e1b9d8bb9cf22bff0e1854e6'
PIN_H = 'b9eb57a956fcbabcc58a9705fe6fc8e986bda8a5f1a8bdf57bd0c32dab718387'
PIN_H70 = 'f4391ad8712d7757423dca872f9042c3271660dffde384a85b93854b9692f288'
ARMS = ('C64_K512_N1', 'C64_K512_N2')
CPUS = (0,)
REQUIRED_PARAMS = {'-table_size': ('64', '64'), '-cluster_size': ('512', '512'),
                   '-num_clusters': ('1', '2'), '-prune_degree': ('64', '64'),
                   '-alpha': ('1.1', '1.1'), '-mst_deg': ('2', '2'),
                   '-hash_bits': ('12', '12'), '-prune': ('1', '1'),
                   '-prune_all': ('1', '1')}


def fail(s):
    raise RuntimeError(s)


def sha(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def pinned(path, expect, label):
    if not path.is_file() or path.is_symlink():
        fail('MISSING_OR_SYMLINK_' + label + ': ' + str(path))
    got = sha(path)
    if got != expect:
        fail('SHA_DRIFT_' + label + ': ' + got)


def fbin(path):
    if not path.is_file() or path.is_symlink():
        fail('MISSING_ORDINARY_FBIN ' + str(path))
    with path.open('rb') as f:
        header = f.read(8)
    if len(header) != 8:
        fail('FBIN_SHORT_HEADER')
    n, d = struct.unpack('<II', header)
    if (n, d) != (100_000, 128):
        fail(f'EXPECTED_SIFT100K_FLOAT32_128D got={n}x{d}')
    if path.stat().st_size != 8 + n * d * 4:
        fail('FBIN_SIZE_INCONSISTENT')
    return {'n': n, 'dim': d, 'bytes': path.stat().st_size, 'sha256': sha(path)}


def load_a4_module():
    # Importing a pinned Python module does not execute its if-__main__ runner.
    spec = importlib.util.spec_from_file_location('r85_a4_step5_pinned_module', A4)
    if spec is None or spec.loader is None:
        fail('CANNOT_IMPORT_PINNED_A4')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if not callable(getattr(module, 'dep', None)) or not callable(getattr(module, 'cmd_build', None)):
        fail('A4_API_MISSING')
    return module


def get_flag(cmd, name):
    if cmd.count(name) != 1:
        fail('CLI_FLAG_NOT_UNIQUE ' + name)
    i = cmd.index(name)
    if i + 1 == len(cmd):
        fail('CLI_FLAG_MISSING_VALUE ' + name)
    return cmd[i+1]


def derive_commands(graphs):
    m = load_a4_module()
    # This verifies A4 pinned source/binaries and dataset dependencies.
    old, a1, _a1c, _base, _b, _ev = m.dep(require_eval=False)
    original_base = str(old.DATA_FILES['base'][0])
    if not Path(original_base).is_file():
        fail('A4_BASE_NOT_FOUND')
    commands = {}
    for ix, arm in enumerate(ARMS):
        graph = graphs[arm]
        raw = [str(x) for x in m.cmd_build(old, a1, arm, graph)]
        if len(raw) < 8 or not Path(raw[0]).is_file():
            fail('A4_DERIVED_COMMAND_UNKNOWN_NATIVE_BINARY: ' + repr(raw[:4]))
        if 'pipnn' not in Path(raw[0]).name.lower():
            fail('A4_NATIVE_NOT_PIPNN: ' + raw[0])
        if raw.count(str(graph)) != 1:
            fail('GRAPH_DEST_NOT_EXACTLY_ONCE ' + arm)
        if raw.count(original_base) != 1:
            fail('ORIGINAL_BASE_NOT_EXACTLY_ONCE ' + arm + ' orig=' + original_base)
        for label, val in old.DATA_FILES.items():
            if label == 'base':
                continue
            other_path = str(val[0])
            if other_path in raw:
                fail('A4_CLI_REFERENCES_OTHER_SIFT1M_DATASET ' + label + ' ' + other_path)
        for name, pair in REQUIRED_PARAMS.items():
            if get_flag(raw, name) != pair[ix]:
                fail(f'CLI_PROTOCOL_DRIFT {arm} {name}={get_flag(raw,name)}')
        cmd = [str(NEW_BINARY) if x == raw[0] else str(DATA) if x == original_base else x for x in raw]
        if str(original_base) in cmd or cmd.count(str(DATA)) != 1:
            fail('DATASET_SUBSTITUTION_FAILED ' + arm)
        if cmd[0] != str(NEW_BINARY):
            fail('NEW_BINARY_SUBSTITUTION_FAILED')
        commands[arm] = cmd
    return commands


def preflight(show=True):
    for p, h, name in [(A4, PIN_A4, 'A4_RUNNER'),
                       (NEW_BINARY, PIN_BIN, 'B1_BINARY'),
                       (NEW_HEADER, PIN_H, 'B1_HEADER'),
                       (H70_HEADER, PIN_H70, 'H70_HEADER')]:
        pinned(p, h, name)
    if not shutil.which('taskset'):
        fail('TASKSET_UNAVAILABLE')
    affinity = set(os.sched_getaffinity(0))
    if not set(CPUS).issubset(affinity):
        fail('CPU0_NOT_AVAILABLE')
    data = fbin(DATA)
    disk = shutil.disk_usage(BASE)
    if disk.free < 10 * 1024**3:
        fail('LESS_THAN_10_GIB_FREE_FOR_SNAPSHOTS')
    fakegraphs = {arm: Path('/NO_WRITE_B1_PREFLIGHT') / f'{arm}.graph' for arm in ARMS}
    cmds = derive_commands(fakegraphs)
    if show:
        print('R85_B1_STEP5_SIFT100K_INPUT ' + json.dumps(data, sort_keys=True), flush=True)
        print('R85_B1_STEP5_FREE_GIB ' + str(round(disk.free/1024**3, 2)), flush=True)
        for arm, cmd in cmds.items():
            print('R85_B1_STEP5_DERIVED_CMD_' + arm + ' ' + shlex.join(['taskset','-c','0'] + cmd), flush=True)
        print('R85_B1_STEP5_PREFLIGHT_PASS_NO_DATASET_BUILD', flush=True)
    return data


def write_json(path, value):
    with path.open('x') as f:
        json.dump(value, f, ensure_ascii=False, indent=2)
        f.write('\n')


def run_pilot():
    data = preflight(show=True)
    session = OUTROOT / ('pilot_' + datetime.now().strftime('%Y%m%d-%H%M%S') + '_' + str(os.getpid()))
    session.mkdir(parents=True, exist_ok=False)
    graphs = {a: session / (a + '.graph') for a in ARMS}
    cmds = derive_commands(graphs)
    native_cwd = Path(load_a4_module().ROOT).resolve(strict=True)
    if not native_cwd.is_dir():
        fail('A4_NATIVE_CWD_NOT_DIRECTORY')
    manifest = {'scope': 'controlled candidate snapshot pilot, NOT native BUILD benchmark',
                'input': str(DATA), 'input_info': data,
                'binary': str(NEW_BINARY), 'binary_sha256': PIN_BIN,
                'header_sha256': PIN_H, 'a4_runner_sha256': PIN_A4,
                'thread_count': 1, 'cpus': list(CPUS), 'native_cwd': str(native_cwd),
                'expected_snapshots': {'C64_K512_N1': ['pass1.tsv'],
                                       'C64_K512_N2': ['pass1.tsv','pass2.tsv']},
                'commands': {a:cmds[a] for a in ARMS},
                'created_utc': datetime.now(timezone.utc).isoformat()}
    write_json(session / 'manifest.json', manifest)
    print('R85_B1_STEP5_SESSION ' + str(session), flush=True)
    env = dict(os.environ,
               PARLAY_NUM_THREADS='1', OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1',
               MKL_NUM_THREADS='1', VECLIB_MAXIMUM_THREADS='1', NUMEXPR_NUM_THREADS='1')
    for arm in ARMS:
        snaps = session / arm
        snaps.mkdir(exist_ok=False)
        if graphs[arm].exists():
            fail('GRAPH_ALREADY_EXISTS ' + str(graphs[arm]))
        curenv = dict(env, R85_B1_SNAPSHOT_DIR=str(snaps))
        cmd = ['taskset','-c','0'] + cmds[arm]
        print('R85_B1_STEP5_BUILD_START ' + arm + ' ' + shlex.join(cmd), flush=True)
        stamp = time.monotonic()
        log = session / (arm+'.log')
        rc = 1
        with log.open('x') as f:
            proc = subprocess.Popen(cmd, cwd=str(native_cwd), env=curenv, stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT, text=True, errors='replace', bufsize=1)
            assert proc.stdout is not None
            for line in proc.stdout:
                f.write(line)
                if ('R85_B1_SNAPSHOT_' in line or 'Built cluster ' in line or
                    'R71_SELECTION_VARIANT=' in line or 'R70_RESERVOIR_VARIANT=' in line):
                    print(line.rstrip(), flush=True)
            rc = proc.wait()
        elapsed = time.monotonic() - stamp
        if rc:
            fail(f'NATIVE_FAILED arm={arm} rc={rc} log={log}; read tail -80')
        textlog = log.read_text(errors='replace')
        for marker in ('R71_SELECTION_VARIANT=H17_PACKED_TOP2', 'R70_RESERVOIR_VARIANT=STOCK_FLAT_C64'):
            if marker not in textlog:
                fail(f'WRONG_NATIVE_VARIANT arm={arm} marker={marker}')
        count = 1 if arm.endswith('_N1') else 2
        if textlog.count('R85_B1_SNAPSHOT_PASS round=') != count:
            fail('WRONG_SNAPSHOT_MARKER_COUNT ' + arm)
        for r in range(1, count+1):
            p = snaps / f'pass{r}.tsv'
            if not p.is_file() or p.stat().st_size == 0:
                fail('MISSING_SNAPSHOT ' + str(p))
        if not graphs[arm].is_file() or not graphs[arm].stat().st_size:
            fail('NATIVE_GRAPH_NOT_CREATED ' + str(graphs[arm]))
        write_json(session / (arm+'.result.json'),
                   {'arm':arm, 'exit_code':rc,'wall_including_snapshots_s': round(elapsed, 4),
                    'graph_sha256':sha(graphs[arm]),'graph_bytes':graphs[arm].stat().st_size,
                    'snapshots':[{'path':str(snaps/f'pass{r}.tsv'),
                                  'size':(snaps/f'pass{r}.tsv').stat().st_size,
                                  'sha256':sha(snaps/f'pass{r}.tsv')}
                                 for r in range(1,count+1)]})
        print(f'R85_B1_STEP5_BUILD_PASS {arm} elapsed_with_snapshots_s={elapsed:.3f}', flush=True)
    analyze(session, emit=True)
    print('R85_B1_STEP5_PILOT_PASS ' + str(session), flush=True)


def read_row(line, expected_row):
    fields = line.rstrip('\n').split('\t')
    if len(fields) < 4:
        fail('BAD_SNAPSHOT_FORMAT row=' + str(expected_row))
    try:
        row, degree, worst, norm = [int(x) for x in fields[:4]]
        if row != expected_row or not 0 <= degree <= 64 or len(fields) != 4 + degree:
            fail('SNAPSHOT_ROW_DEGREE_INVALID row=' + str(expected_row))
        if degree and not 0 <= worst < degree:
            fail('SNAPSHOT_WORST_INDEX_INVALID row=' + str(expected_row))
        if not 0 <= norm < 2**32:
            fail('SNAPSHOT_SENTINEL_NORM_INVALID row=' + str(expected_row))
        entries = []
        for field in fields[4:]:
            pid, h, bits = (int(x) for x in field.split(','))
            if not (0 <= pid < 100000 and 0 <= h < 65536 and 0 <= bits < 2**32):
                fail('SNAPSHOT_CANDIDATE_INVALID row=' + str(expected_row))
            entries.append((pid, h, bits))
        return {'degree':degree, 'worst_index':worst, 'worst_bits':norm, 'entries':entries}
    except ValueError as e:
        fail(f'NON_INTEGER_SNAPSHOT row={expected_row} {e}')


def audit_pair(a, b, count):
    stats = {'rows':0,'rows_changed':0, 'edges_before':0,'edges_after':0,
             'candidates_removed':0,'candidates_added':0, 'identical_rows':0}
    with a.open('r') as fa, b.open('r') as fb:
        for i, (aa, bb) in enumerate(itertools.zip_longest(fa, fb)):
            if i >= count or aa is None or bb is None:
                fail('SNAPSHOT_ROW_COUNT_MISMATCH')
            x, y = read_row(aa, i), read_row(bb, i)
            stats['rows'] += 1
            stats['edges_before'] += x['degree']
            stats['edges_after'] += y['degree']
            if aa == bb:
                stats['identical_rows'] += 1
            else:
                stats['rows_changed'] += 1
            cx, cy = Counter(x['entries']), Counter(y['entries'])
            stats['candidates_removed'] += sum((cx-cy).values())
            stats['candidates_added'] += sum((cy-cx).values())
    if stats['rows'] != count:
        fail('SNAPSHOT_WRONG_NUMBER_NODES ' + str(stats['rows']))
    return stats


def analyze(session, emit=True):
    manifest = json.loads((session/'manifest.json').read_text())
    if manifest.get('binary_sha256') != PIN_BIN or manifest.get('input_info',{}).get('n') != 100000:
        fail('PILOT_MANIFEST_DRIFT')
    a = session / 'C64_K512_N1/pass1.tsv'
    b = session / 'C64_K512_N2/pass1.tsv'
    c = session / 'C64_K512_N2/pass2.tsv'
    if not all(p.is_file() for p in (a,b,c)):
        fail('MISSING_REQUIRED_3_SNAPSHOTS')
    # Validate *all* 100k rows and measure candidate-set changes, not only file SHA.
    firstpass = audit_pair(a, b, 100000)
    incremental = audit_pair(b, c, 100000)
    out = {'scope':'SIFT100K 1-thread B1 candidate snapshot comparison',
           'firstpass_N1_vs_N2':firstpass, 'secondpass_N2P1_vs_N2P2':incremental,
           'snapshot_sha256':{str(p.relative_to(session)):sha(p) for p in (a,b,c)},
           'strict_firstpass_identical': firstpass['rows_changed'] == 0,
           'NOTE':'Snapshot cost contaminates native wall times; candidate delta is not automatically Recall/latency gain.'}
    summary = session/'snapshot_comparison.json'
    if summary.exists():
        if json.loads(summary.read_text()) != out:
            fail('EXISTING_AUDIT_DIFFERENT_REFUSE_OVERWRITE')
    else:
        write_json(summary, out)
    if emit:
        print('R85_B1_STEP5_FIRSTPASS_EQUIVALENCE ' + json.dumps(firstpass, sort_keys=True), flush=True)
        print('R85_B1_STEP5_SECOND_PASS_DELTA ' + json.dumps(incremental, sort_keys=True), flush=True)
        print('R85_B1_STEP5_SNAPSHOT_HASHES ' + json.dumps(out['snapshot_sha256'],sort_keys=True), flush=True)
        print('R85_B1_STEP5_AUDIT_PASS_READ_ONLY_INPUTS ' + str(summary), flush=True)
    return out


def selftest():
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        p = Path(d)
        # Delta exercise including candidate replacement with equal degree, and sentinel change.
        def make(path, entries):
            path.write_text(''.join(f'{i}\t{len(e)}\t0\t0' + ''.join(f'\t{pid},{h},{bits}' for pid,h,bits in e) + '\n' for i,e in enumerate(entries)))
        a,b,c = p/'a', p/'b', p/'c'
        e1=[[(1,2,3)], []]
        e2=[[(1,2,3)], []]
        e3=[[(4,5,6)], [(1,1,1)]]
        make(a,e1);make(b,e2);make(c,e3)
        x=audit_pair(a,b,2); y=audit_pair(b,c,2)
        assert x['rows_changed']==0 and y['rows_changed']==2
        assert (y['candidates_added'],y['candidates_removed'])==(2,1)
        assert get_flag(['x','-table_size','64'],'-table_size')=='64'
        print('R85_B1_STEP5_SELFTEST_PASS_NO_DATASET_BUILD')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    group=p.add_mutually_exclusive_group(required=True)
    group.add_argument('--selftest', action='store_true')
    group.add_argument('--preflight', action='store_true')
    group.add_argument('--run', action='store_true')
    group.add_argument('--audit', type=Path, metavar='SESSION')
    p.add_argument('--confirm-pilot', action='store_true')
    a=p.parse_args()
    if a.selftest:
        selftest()
    elif a.preflight:
        preflight()
    elif a.run:
        if not a.confirm_pilot:
            fail('PASS_--confirm-pilot_TO_START_NATIVE_DATASET_BUILD')
        run_pilot()
    else:
        analyze(a.audit.expanduser().resolve(strict=True))

if __name__=='__main__':
    try:
        main()
    except Exception as exc:
        print('R85_B1_STEP5_FAIL_CLOSED ' + repr(exc), file=sys.stderr, flush=True)
        sys.exit(2)
