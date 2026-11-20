#!/usr/bin/env python3
"""R86 MS-Turing 1M six-arm *pilot*, fail-closed, one arm at a time.

--preflight: read-only SHA, shape, resource checks; writes nothing.
--build --arm A0: one native OFF graph, isolated immutable run directory.
--search --arm A0 --beams 64: evaluate on 100K public queries, functional smoke;
  only graph already produced by this script is accepted.

Neither one build nor one fixed beam constitutes quality-matched evidence.
R86 C/K/N/cluster parameters transcribed from archived native_command.json
of R86_WN_SIFT1M_A0_A3_A4_ON_v1_0; only dataset and binary changed.
No old graph, benchmark result, binary, or dataset is overwritten.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

ROOT = Path.home() / 'ann-task-a'
DATA = ROOT / 'data/MSTuring_1M_v1'
CAMPAIGN = ROOT / 'experiments/R86/msturing_1m_sixarm/pilot_mst1m_v1'
TARGET = 'algorithms/PipNN/neighbors-pipnn_FLOAT_T_EUCLIDEAN'
GATES = ROOT / 'experiments/R86/gates/highway_r85_four_binary_jvYREW'
STOCK = GATES / 'build_stock_off' / TARGET
H17 = GATES / 'build_h17_off' / TARGET
D0 = ROOT / 'experiments/R86/msturing_1m_sixarm/build_d0_h17_tier_off_v2' / TARGET
EVAL = ROOT / 'experiments/R86/msturing_1m_eval/r86_msturing1m_graph_recall_v3'
PINS = {
    'base': (DATA / 'base.1M.fbin', '44e83e1dd4c65999b75873101adc5ac06ca900d259a2befd05c2c3aa28ff4042', 400000008, (1000000, 100)),
    'query': (DATA / 'query.public.100K.fbin', '48d087a17bec15a5ec9ea526fe9bd14ac31bbbb5cd200817b341adbb77695644', 40000008, (100000, 100)),
    'gt': (DATA / 'groundtruth.public.100K.ibin', 'fa5acf5ab262b42355296e99f920e6aa863f48820ca6f70fa37ca7966634c344', 80000008, (100000, 100)),
    'stock': (STOCK, 'aa2d174ed063070045f1fbbc8051b1d97b851168b2f3bf53ee32215a867583be', None, None),
    'h17': (H17, '5f673586210f93b424fc81791ec7873cb74600843b5004c0a4aaaf32bf936297', None, None),
    'd0': (D0, '7c2aad71a97f9c2b2e6de6026085be43954a7dd0845feffb672f6782c84575ab', None, None),
    'eval': (EVAL, 'ea6c757b47b1267b7009ff0a1a80a3fdeaaf59740c4c2036712accf9ba0d0af5', None, None),
}
ARMS = {
    'A0': ('stock', 160, 1024, 2),
    'A1': ('h17', 160, 1024, 2),
    'A2': ('h17', 64, 1024, 2),
    'A3': ('h17', 64, 512, 2),
    'A4': ('h17', 64, 512, 1),
    'D0': ('d0', 160, 1024, 2),
}
CPUS_BUILD = [0, 2, 4, 6]
CPU_SEARCH = 0


def hold(msg):
    raise RuntimeError('R86_MST1M_SIXARM_PILOT_HOLD ' + msg)


def sha256(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for part in iter(lambda: f.read(1024 * 1024), b''):
            h.update(part)
    return h.hexdigest()


def atomic_json(path, data):
    with path.open('x', encoding='utf-8') as f:
        json.dump(data, f, indent=2, sort_keys=True)
        f.write('\n')


def preflight(need_resource=True):
    for name, (path, wanted, size, shape) in PINS.items():
        if not path.is_file():
            hold('PIN_MISSING ' + name + ' ' + str(path))
        if size is not None and path.stat().st_size != size:
            hold('PIN_SIZE_MISMATCH ' + name)
        if shape is not None:
            with path.open('rb') as f:
                import struct
                header = struct.unpack('<II', f.read(8))
            if header != shape:
                hold('PIN_SHAPE_MISMATCH ' + name + ' ' + str(header))
        got = sha256(path)
        if got != wanted:
            hold('PIN_SHA_MISMATCH ' + name + ' got=' + got + ' want=' + wanted)
        if name in ('stock', 'h17', 'd0', 'eval') and not os.access(path, os.X_OK):
            hold('PIN_NOT_EXECUTABLE ' + name)
        print('R86_MST1M_PIN_PASS ' + name + ' sha256=' + got, flush=True)
    for exe in ('taskset', '/usr/bin/time'):
        if not shutil.which(exe):
            hold('EXECUTABLE_MISSING ' + exe)
    if hasattr(os, 'sched_getaffinity'):
        allowed = os.sched_getaffinity(0)
        requested = set(CPUS_BUILD) | {CPU_SEARCH}
        if not requested.issubset(allowed):
            hold('CPU_AFFINITY_NOT_ALLOWED requested=' + str(sorted(requested)) + ' allowed=' + str(sorted(allowed)))
    free_gib = shutil.disk_usage(ROOT).free / 1024**3
    if need_resource and free_gib < 8:
        hold('FREE_DISK_LT_8_GIB actual=' + str(round(free_gib,2)))
    print('R86_MST1M_PREFLIGHT_DISK_FREE_GIB %.2f' % free_gib, flush=True)
    if Path('/proc/meminfo').is_file():
        for line in Path('/proc/meminfo').read_text().splitlines():
            if line.startswith('MemAvailable:'):
                print('R86_MST1M_MEM_AVAILABLE_KIB ' + line.split()[1], flush=True)
                break
    print('R86_MST1M_SIXARM_PILOT_INPUT_AND_BINARY_PINS_PASS_NO_WRITES', flush=True)


def native_build_command(arm, graph):
    key, C, K, N = ARMS[arm]
    binfile = PINS[key][0]
    native = [str(binfile), '-base_path', str(PINS['base'][0]), '-graph_outfile', str(graph),
              '-num_clusters', str(N), '-cluster_size', str(K),
              '-top_level_leaders', '100', '-fanout_scheme', '10,3,1',
              '-mst_deg', '2', '-prune', '1', '-prune_all', '1',
              '-prune_degree', '64', '-table_size', str(C),
              '-hash_bits', '12', '-alpha', '1.1', '-k', '0']
    return ['taskset', '-c', ','.join(map(str, CPUS_BUILD)), '/usr/bin/time',
            '-f', 'R86_MST1M_PILOT_TIME wall_s=%e peak_rss_kib=%M', *native]


def run_and_log(cmd, log, env):
    with log.open('x', encoding='utf-8') as f:
        p = subprocess.run(cmd, stdout=f, stderr=subprocess.STDOUT, env=env, check=False)
    print('RUN_EXIT_CODE=%s log=%s' % (p.returncode, log), flush=True)
    if p.returncode:
        tail = log.read_text(errors='replace').splitlines()[-35:]
        print('LOG_TAIL_BEGIN\n' + '\n'.join(tail) + '\nLOG_TAIL_END', flush=True)
        hold('NATIVE_COMMAND_FAILED_EXIT_' + str(p.returncode))


def build(arm):
    preflight()
    run_dir = CAMPAIGN / arm
    if run_dir.exists():
        hold('RUN_ALREADY_EXISTS_PRESERVE_EVIDENCE ' + str(run_dir))
    run_dir.parent.mkdir(parents=True, exist_ok=True)
    run_dir.mkdir() # exclusive, never overwrite prior build
    graph = run_dir / 'index.graph'
    cmd = native_build_command(arm, graph)
    receipt = {'dataset': 'MS-Turing-1M public', 'arm': arm, 'configuration': ARMS[arm],
               'pin_sha256': {n: x[1] for n,x in PINS.items()}, 'command': cmd,
               'environment': {'PARLAY_NUM_THREADS':'4'},
               'protocol': 'R86 native_command.json copy; separate dataset MS-Turing1M; pilot ONLY; one OFF build'}
    atomic_json(run_dir / 'build_command.json', receipt)
    print('R86_MST1M_BUILD_START arm=' + arm, flush=True)
    env = dict(os.environ, PARLAY_NUM_THREADS='4')
    run_and_log(cmd, run_dir / 'native.build.log', env)
    if not graph.is_file() or graph.stat().st_size < 1024:
        hold('GRAPH_NOT_CREATED_OR_TOO_SMALL ' + str(graph))
    result = {'arm':arm, 'build_exit_code':0, 'graph_path':str(graph),
              'graph_sha256':sha256(graph), 'graph_bytes':graph.stat().st_size,
              'build_log': str(run_dir/'native.build.log'),
              'input_sha256':PINS['base'][1], 'native_binary_sha256':PINS[ARMS[arm][0]][1],
              'status':'BUILD_OFF_GRAPH_EXISTS_SEARCH_NOT_YET_APPROVED'}
    atomic_json(run_dir / 'build_result.json', result)
    print('R86_MST1M_BUILD_GRAPH_WRITTEN_NOT_EVALUATED arm='+arm+' sha256='+result['graph_sha256']+' bytes='+str(result['graph_bytes']), flush=True)


def search(arm, beams_text):
    preflight()
    try:
        beams = [int(x) for x in beams_text.split(',')]
    except ValueError:
        hold('INVALID_BEAMS_CSV')
    if not beams or len(set(beams)) != len(beams) or any(b<10 or b>512 for b in beams):
        hold('INVALID_BEAMS_RANGE_OR_DUPLICATE')
    beam_csv = ','.join(map(str,beams))
    run_dir = CAMPAIGN / arm
    graph = run_dir/'index.graph'
    result_path = run_dir/'build_result.json'
    if not result_path.is_file() or not graph.is_file():
        hold('BUILD_GRAPH_AND_RECEIPT_REQUIRED_FOR_SEARCH')
    receipt = json.loads(result_path.read_text())
    if receipt.get('arm') != arm or receipt.get('input_sha256') != PINS['base'][1] or receipt.get('native_binary_sha256') != PINS[ARMS[arm][0]][1]:
        hold('BUILD_RECEIPT_MISMATCH')
    if sha256(graph) != receipt.get('graph_sha256') or graph.stat().st_size != receipt.get('graph_bytes'):
        hold('GRAPH_SHA_OR_SIZE_CHANGED')
    log = run_dir / ('search_beams_' + beam_csv.replace(',','_') + '.log')
    cmd = ['taskset','-c',str(CPU_SEARCH), '/usr/bin/time', '-f',
           'R86_MST1M_SEARCH_TIME wall_s=%e peak_rss_kib=%M', str(EVAL),
           str(graph),str(PINS['base'][0]),str(PINS['query'][0]),str(PINS['gt'][0]),beam_csv]
    command_path = run_dir / ('search_beams_' + beam_csv.replace(',','_') + '_command.json')
    if log.exists() or command_path.exists():
        hold('SEARCH_ALREADY_EXISTS_PRESERVE_EVIDENCE')
    atomic_json(command_path, {'arm':arm,'beams':beams,'command':cmd,'graph_sha256':receipt['graph_sha256'],
                               'evaluator_sha256':PINS['eval'][1],'status':'FUNCTIONAL_SMOKE_ONLY_UNTIL_REPEATED_MATCHED_RECALL'})
    env=dict(os.environ,PARLAY_NUM_THREADS='1')
    print('R86_MST1M_SEARCH_START arm='+arm+' beams='+beam_csv+' queries=100000',flush=True)
    run_and_log(cmd,log,env)
    txt=log.read_text(errors='replace')
    if 'R72_RECALL_INPUT_PASS' not in txt or 'R72_RECALL_EVAL_PASS' not in txt:
        hold('EVALUATOR_OUTPUT_PASS_MARKERS_MISSING ' + str(log))
    matches=re.findall(r'R72_RECALL_ROW\s+beam=(\d+)\s+recall=([^\s]+)\s+qps=([^\s]+)',txt)
    if len(matches)!=len(beams) or [int(b) for b,_,_ in matches] != beams:
        hold('SEARCH_ROW_COUNT_OR_BEAM_ORDER_MISMATCH')
    for beam,recall,qps in matches:
        print('R86_MST1M_SEARCH_FUNCTIONAL_ROW arm=%s beam=%s recall=%s qps=%s' % (arm,beam,recall,qps),flush=True)
    print('R86_MST1M_PILOT_SEARCH_FUNCTIONAL_SMOKE_PASS_NOT_MATCHED_RECALL arm='+arm,flush=True)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    x=p.add_mutually_exclusive_group(required=True)
    x.add_argument('--preflight',action='store_true')
    x.add_argument('--build',action='store_true')
    x.add_argument('--search',action='store_true')
    p.add_argument('--arm',choices=tuple(ARMS))
    p.add_argument('--beams',default='64',help='CSV 10..512; first smoke 64')
    args=p.parse_args()
    if (args.build or args.search) and not args.arm:
        p.error('--arm is required for --build and --search')
    try:
        if args.preflight: preflight()
        elif args.build: build(args.arm)
        else: search(args.arm,args.beams)
        return 0
    except Exception as e:
        print(str(e),flush=True)
        return 2

if __name__=='__main__':
    sys.exit(main())
