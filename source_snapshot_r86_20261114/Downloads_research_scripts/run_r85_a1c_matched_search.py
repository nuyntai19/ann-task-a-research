#!/usr/bin/env python3
"""R85-A1c SEARCH-only: measured Recall-vs-comparisons on the 3 saved B64 graphs.

Reuses and SHA-pins the prior R85-0f and R85-A1 scripts. Builds an *isolated*
R72-derived evaluator whose sole substantive change is accepting an explicit
CSV beam list. Compiles it using the previously generated H70 evaluator's
compile_commands.json and link.txt, leaving H70-H84 untouched. Runs only 3
existing B64 graphs and compares against D0's 3 existing quality results.

Invocation:
  python3 run_r85_a1c_matched_search.py --selftest
  python3 run_r85_a1c_matched_search.py --prepare
  python3 run_r85_a1c_matched_search.py --dry-run
  python3 run_r85_a1c_matched_search.py --run-quality
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
from statistics import median

ROOT = Path.home() / 'ann-task-a'
A1_RUN = ROOT / 'experiments/H85/r85_a1_capacity_ablation/runs_20261109-215545'
NEW = ROOT / 'experiments/H85/r85_a1c_matched_search'
ORIG = ROOT / 'experiments/H70/pipnn-clean-443a328/algorithms/PipNN/r72_graph_recall.cc'
H70_BLD = ROOT / 'experiments/H70/build-r70'
CPP = NEW / 'r85_a1c_graph_recall.cc'
OBJECT = NEW / 'r85_a1c_graph_recall.o'
EVAL = NEW / 'r85_a1c_graph_recall'
MANIFEST = NEW / 'evaluator_manifest.json'
ORIG_EVAL = H70_BLD / 'algorithms/PipNN/r72_graph_recall'
A1_SCRIPT = Path.home() / 'Downloads/run_r85_a1_capacity_ablation.py'
A1_SCRIPT_SHA = '843cacaffb0c16d0ab8f86a32546ca74cc3b4c59d47ac3fd724e5fffc2accdb9'
EVAL_SHA = '3c2294efa1d7fb5d89c79ca5bf9c1eaca86247f7246e6d6d7c6c94549d08ed57'
BEAMS = (10, 11, 12, 20, 21, 22, 23, 24, 40, 44, 46, 48, 50, 80,
         96, 100, 104, 108, 112, 120, 160, 176, 192, 224, 256)
ANCHORS = (10, 20, 40, 80, 160)
CORE_IDS = (0, 2, 4, 6)
PATTERN = re.compile(r'R72_RECALL_ROW beam=(\d+) recall=([0-9.Ee+-]+) qps=([0-9.Ee+-]+) avg_cmps=([0-9.Ee+-]+) avg_visited=([0-9.Ee+-]+)')


def fail(msg):
    raise RuntimeError('R85_A1C_FAIL_CLOSED: ' + msg)


def sha(p):
    h = hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''):
            h.update(b)
    return h.hexdigest()


def json_atomic(path, data):
    tmp = path.with_name(path.name + '.tmp')
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + '\n', encoding='utf8')
    tmp.replace(path)


def module(path, name, expected):
    if not path.is_file() or sha(path) != expected:
        fail('Pinned runner absent or changed: ' + str(path))
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        fail('Cannot import pinned runner ' + name)
    obj = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(obj)
    return obj


def background_run(cmd, cwd, log):
    with log.open('w', encoding='utf8') as f:
        f.write('$ ' + shlex.join([str(x) for x in cmd]) + '\n')
        f.flush()
        result = subprocess.run([str(x) for x in cmd], cwd=str(cwd), stdout=f,
                                stderr=subprocess.STDOUT, check=False)
    if result.returncode:
        fail('Command returned ' + str(result.returncode) + ': see ' + str(log))


def preflight():
    a1 = module(A1_SCRIPT, 'r85_a1_pinned', A1_SCRIPT_SHA)
    old = a1.load_pinned_previous()
    old.check_inputs()
    a1.verify_b_manifest()
    if not ORIG.is_file() or sha(ORIG_EVAL) != EVAL_SHA:
        fail('Original R72 evaluator source/binary pin missing or changed')
    if not (A1_RUN / 'build_results.json').is_file() or not (A1_RUN / 'quality/quality_results.json').is_file():
        fail('R85-A1 BUILD or original SEARCH results missing')
    builds = json.loads((A1_RUN / 'build_results.json').read_text())
    qualities = json.loads((A1_RUN / 'quality/quality_results.json').read_text())
    if len(builds) != 9 or len(qualities) != 45:
        fail('Incorrect R85-A1 number of graphs/search rows')
    for row in builds:
        graph = Path(row['graph'])
        if not graph.is_file() or sha(graph) != row['graph_sha256']:
            fail('Graph SHA mismatch: ' + str(graph))
        if row['arm'] not in ('B64', 'B160', 'D0') or row['rep'] not in (1, 2, 3):
            fail('Unexpected R85-A1 graph')
    if sorted((r['rep'], r['arm']) for r in builds) != sorted((rep, arm) for rep in (1,2,3) for arm in ('B64','B160','D0')):
        fail('Missing arm/rep graph')
    for r in qualities:
        if r['arm'] not in ('B64', 'B160', 'D0') or r['beam'] not in ANCHORS:
            fail('Unexpected original quality row')
    if len({(r['arm'], r['rep'], r['beam']) for r in qualities}) != 45:
        fail('Original quality tuples not unique')
    return old, builds, qualities


def patch_source(original):
    # Exactly three narrow edits; the original R72 search and checkRecall() stay unchanged.
    edits = (
        ('#include <stdexcept>', '#include <stdexcept>\n#include <sstream>\n#include <string>\n#include <vector>\n#include <set>'),
        ('if (argc != 5)', 'if (argc != 6)'),
        ('for (long beam : {10L, 20L, 40L, 80L, 160L})', 'for (long beam : beams)'),
    )
    result = original
    for old, new in edits:
        if result.count(old) != 1:
            fail('Original R72 C++ source differs unexpectedly: ' + old)
        result = result.replace(old, new, 1)
    marker = '    // These are native PiPNN readers and native PiPNN search/recall routines.'
    if result.count(marker) != 1:
        fail('Original evaluator parser insertion marker changed')
    parser = '''    std::vector<long> beams;
    std::set<long> seen;
    std::stringstream ss(argv[5]);
    std::string piece;
    while (std::getline(ss, piece, ',')) {
      if (piece.empty()) throw std::invalid_argument("Empty beam");
      size_t consumed = 0;
      long beam = std::stol(piece, &consumed, 10);
      if (consumed != piece.size() || beam < 10 || beam > 512 || !seen.insert(beam).second)
        throw std::invalid_argument("Invalid or duplicated beam");
      beams.push_back(beam);
    }
    if (beams.empty()) throw std::invalid_argument("No beams supplied");
    std::cout << "R85_A1C_DYNAMIC_BEAMS count=" << beams.size() << "\\n";
'''
    result = result.replace(marker, parser + '\n' + marker, 1)
    # The copied source lives in H85. Point utility includes back to pinned H70.
    def rewrite(m):
        p = ORIG.parent.parent / 'utils' / m.group(1)
        if not p.is_file():
            fail('Missing pinned header ' + str(p))
        return '#include "' + str(p) + '"'
    result, count = re.subn(r'#include "\.\./utils/([^\"]+)"', rewrite, result)
    if count != 3:
        fail('Expected 3 R72 relative utility includes; got ' + str(count))
    return result.replace('GRAPH.fbin BASE.fbin QUERIES.fbin GT.ibin\\n',
                          'GRAPH.fbin BASE.fbin QUERIES.fbin GT.ibin BEAMS_CSV\\n')


def compile_eval():
    cdb = H70_BLD / 'compile_commands.json'
    link_file = H70_BLD / 'algorithms/PipNN/CMakeFiles/r72_graph_recall.dir/link.txt'
    if not cdb.is_file() or not link_file.is_file():
        fail('Missing preexisting R72 compile_commands.json or link.txt')
    entries = json.loads(cdb.read_text())
    matched = [e for e in entries if Path(e.get('file', '')).name == 'r72_graph_recall.cc']
    if len(matched) != 1:
        fail('Need exactly one original R72 evaluator compile command, found ' + str(len(matched)))
    entry = matched[0]
    argv = shlex.split(entry['command']) if 'command' in entry else entry['arguments'][:]
    if argv.count('-c') != 1 or argv.count('-o') != 1:
        fail('Unexpected R72 evaluator compiler invocation')
    argv[argv.index('-c') + 1] = str(CPP)
    argv[argv.index('-o') + 1] = str(OBJECT)
    background_run(argv, Path(entry['directory']), NEW / 'compile.log')
    # CMake link command includes many target dependencies. Reuse it unchanged
    # except for the SINGLE evaluator object and output binary.
    link = shlex.split(link_file.read_text().strip())
    originals = [i for i, token in enumerate(link)
                 if token.endswith('/r72_graph_recall.cc.o') or token == 'r72_graph_recall.cc.o']
    if len(originals) != 1 or link.count('-o') != 1:
        fail('Unexpected original evaluator linker command')
    link[originals[0]] = str(OBJECT)
    link[link.index('-o')+1] = str(EVAL)
    background_run(link, link_file.parent.parent.parent, NEW / 'link.log')
    if not EVAL.is_file() or not os.access(EVAL, os.X_OK):
        fail('Dynamic evaluator not produced')
    return {'compiler_command': argv, 'linker_command': link}


def prepare():
    old, _, _ = preflight()
    if MANIFEST.exists():
        manifest = check_evaluator()
        print('R85_A1C_ALREADY_PREPARED sha256=' + manifest['dynamic_evaluator_sha256'], flush=True)
        return
    NEW.mkdir(parents=True, exist_ok=True)
    cpp_text = patch_source(ORIG.read_text())
    if CPP.exists() or EVAL.exists():
        fail('Partial existing evaluator found. Do not overwrite it: ' + str(NEW))
    CPP.write_text(cpp_text, encoding='utf8')
    print('R85_A1C_COMPILE_START', flush=True)
    cmds = compile_eval()
    manifest = {
        'source_head': old.EXPECTED_GIT,
        'original_evaluator_source_sha256': sha(ORIG),
        'original_evaluator_binary_sha256': sha(ORIG_EVAL),
        'patched_evaluator_source_sha256': sha(CPP),
        'dynamic_evaluator_sha256': sha(EVAL),
        'beams': list(BEAMS),
        'compile_command': cmds['compiler_command'],
        'link_command': cmds['linker_command'],
        'purpose': 'Only compare recall/comparisons; same native checkRecall, different explicit beam list',
    }
    json_atomic(MANIFEST, manifest)
    print('R85_A1C_DYNAMIC_EVALUATOR_PREPARED sha256=' + manifest['dynamic_evaluator_sha256'], flush=True)
    print('R85_A1C_EVAL_MANIFEST ' + str(MANIFEST), flush=True)


def check_evaluator():
    if not MANIFEST.is_file() or not CPP.is_file() or not EVAL.is_file():
        fail('Dynamic evaluator not prepared; run --prepare')
    m = json.loads(MANIFEST.read_text())
    for key, p in [('original_evaluator_source_sha256', ORIG),
                   ('original_evaluator_binary_sha256', ORIG_EVAL),
                   ('patched_evaluator_source_sha256', CPP),
                   ('dynamic_evaluator_sha256', EVAL)]:
        if sha(p) != m[key]:
            fail('Evaluator provenance mismatch for ' + str(p))
    if m['beams'] != list(BEAMS):
        fail('Beam list differs from manifest')
    return m


def run_quality():
    old, builds, qualities = preflight()
    manifest = check_evaluator()
    out = A1_RUN / 'matched_quality'
    if out.exists():
        fail('Quality output already exists; refuse to overwrite ' + str(out))
    out.mkdir()
    rows = []
    b64 = sorted((r for r in builds if r['arm'] == 'B64'), key=lambda r: r['rep'])
    orig_index = {(r['arm'], r['rep'], r['beam']): r for r in qualities}
    for i, g in enumerate(b64, 1):
        cmd = ['taskset', '-c', ','.join(map(str, CORE_IDS)), str(EVAL),
               g['graph'], str(old.DATA_FILES['base'][0]),
               str(old.DATA_FILES['query'][0]), str(old.DATA_FILES['gt'][0]),
               ','.join(map(str, BEAMS))]
        env = dict(os.environ)
        env['PARLAY_NUM_THREADS'] = '4'
        log = out / f"{g['tag']}.log"
        print(f"R85_A1C_SEARCH_START {i}/3 graph={g['tag']} beams={len(BEAMS)}", flush=True)
        with log.open('w', encoding='utf8') as f:
            f.write('# COMMAND ' + shlex.join(cmd) + '\n')
            f.flush()
            result = subprocess.run(cmd, cwd=str(ROOT), env=env, stdout=f, stderr=subprocess.STDOUT)
        output = log.read_text(errors='replace')
        if result.returncode or 'R85_A1C_DYNAMIC_BEAMS count=' + str(len(BEAMS)) not in output or 'R72_RECALL_EVAL_PASS' not in output:
            fail('Native dynamic evaluator did not pass, see ' + str(log))
        found = PATTERN.findall(output)
        if len(found) != len(BEAMS) or {int(x[0]) for x in found} != set(BEAMS):
            fail('Missing or duplicated dynamic evaluator beam; see ' + str(log))
        for beam, recall, qps, cmps, visited in found:
            row = {'tag': g['tag'], 'arm': 'B64', 'rep': g['rep'],
                   'beam': int(beam), 'recall': float(recall),
                   'qps': float(qps), 'avg_cmps': float(cmps),
                   'avg_visited': float(visited)}
            if not (0 <= row['recall'] <= 1) or not all(math.isfinite(row[k]) and row[k] > 0 for k in ('qps','avg_cmps','avg_visited')):
                fail('Non-finite or invalid metric: ' + str(row))
            # Cross-evaluator semantic parity on one unchanged graph and fixed beam.
            if row['beam'] in ANCHORS:
                prev = orig_index['B64', row['rep'], row['beam']]
                if abs(row['recall'] - prev['recall']) > 0.00001 or abs(row['avg_cmps'] - prev['avg_cmps']) > 2.0:
                    fail(f"Dynamic/native evaluator result mismatch at {g['tag']} beam={row['beam']}; originals remain intact")
            rows.append(row)
        json_atomic(out / 'measured_B64_results.json', rows)
        print('R85_A1C_SEARCH_PASS ' + g['tag'], flush=True)
    # D0 metrics are the original/native 3x5 quality rows, same query set.
    table = []
    for b in BEAMS:
        cur = [r for r in rows if r['beam'] == b]
        if len(cur) != 3:
            fail('Missing all 3 B64 graphs at beam=' + str(b))
        table.append({'beam': b,
                      'B64_recall_median': median(r['recall'] for r in cur),
                      'B64_cmps_median': median(r['avg_cmps'] for r in cur),
                      'B64_recall_min': min(r['recall'] for r in cur),
                      'B64_recall_max': max(r['recall'] for r in cur)})
    targets = []
    for beam in ANCHORS:
        d = [r for r in qualities if r['arm']=='D0' and r['beam']==beam]
        if len(d) != 3:
            fail('Missing D0 target quality beam=' + str(beam))
        recall_t = median(x['recall'] for x in d)
        cmps_t = median(x['avg_cmps'] for x in d)
        passed = [r for r in table if r['B64_recall_median'] >= recall_t]
        if passed:
            chosen = min(passed, key=lambda r: (r['B64_cmps_median'], r['beam']))
            result = {'status': 'MEASURED_RECALL_AT_LEAST_TARGET',
                      'B64_beam': chosen['beam'],
                      'B64_recall': chosen['B64_recall_median'],
                      'B64_avg_cmps': chosen['B64_cmps_median'],
                      'B64_vs_D0_cmps_ratio': chosen['B64_cmps_median'] / cmps_t,
                      'B64_minus_D0_recall_pp': 100*(chosen['B64_recall_median'] - recall_t)}
        else:
            result = {'status': 'TARGET_NOT_REACHED_WITH_TESTED_BEAMS'}
        targets.append({'D0_beam': beam, 'D0_recall': recall_t,
                        'D0_avg_cmps': cmps_t, **result})
    json_atomic(out / 'B64_curve_medians.json', table)
    json_atomic(out / 'matched_recall_summary.json', targets)
    json_atomic(out / 'manifest.json', {'source_run_dir': str(A1_RUN),
                                       'dynamic_evaluator_sha256': manifest['dynamic_evaluator_sha256'],
                                       'original_evaluator_sha256': EVAL_SHA,
                                       'original_D0_quality_results': str(A1_RUN / 'quality/quality_results.json'),
                                       'B64_graph_shas': {x['tag']: x['graph_sha256'] for x in b64},
                                       'beams': list(BEAMS),
                                       'note': 'medians across 3 non-identical constructed graphs; comparison counts at first measured sufficient recall; no formal noninferiority'})
    print('R85_A1C_ALL_3_B64_SEARCHES_PASS', flush=True)
    for t in targets:
        print('R85_A1C_MATCHED_RECALL_ROW ' + json.dumps(t, ensure_ascii=False), flush=True)
    print('R85_A1C_MATCHED_RECALL_SUMMARY ' + str(out / 'matched_recall_summary.json'), flush=True)


def selftest():
    sample = '''#include <stdexcept>\n#include "../utils/euclidian_point.h"\n#include "../utils/point_range.h"\n#include "../utils/check_nn_recall.h"\nif (argc != 5) {\n  for (long beam : {10L, 20L, 40L, 80L, 160L}) {\n    // These are native PiPNN readers and native PiPNN search/recall routines.\n'''
    # Use patch_source on the real bundled user source only in full run; synthetic
    # assert tests beam config parsing and thresholds without accessing Ubuntu.
    assert BEAMS[0] == 10 and BEAMS[-1] == 256
    assert len(BEAMS) == len(set(BEAMS)) and BEAMS == tuple(sorted(BEAMS))
    assert (10, 20, 40, 80, 160) == ANCHORS
    assert not (NEW == A1_RUN or NEW == ORIG.parent)
    assert 'if (argc != 5)' in sample and 'for (long beam : {10L, 20L, 40L, 80L, 160L})' in sample
    print('R85_A1C_SELFTEST_PASS')


def main():
    arg = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    modes = arg.add_mutually_exclusive_group(required=True)
    modes.add_argument('--selftest', action='store_true')
    modes.add_argument('--prepare', action='store_true')
    modes.add_argument('--dry-run', action='store_true')
    modes.add_argument('--run-quality', action='store_true')
    a = arg.parse_args()
    if a.selftest:
        selftest()
        return
    if a.prepare:
        prepare()
        return
    old, builds, _ = preflight()
    check_evaluator()
    print('R85_A1C_SOURCE_BINARIES_9_GRAPHS_AND_NATIVE_EVALUATOR_PIN_PASS', flush=True)
    if a.dry_run:
        for r in sorted((r for r in builds if r['arm']=='B64'), key=lambda x:x['rep']):
            cmd = ['taskset', '-c', ','.join(map(str, CORE_IDS)), str(EVAL), r['graph'],
                   str(old.DATA_FILES['base'][0]), str(old.DATA_FILES['query'][0]),
                   str(old.DATA_FILES['gt'][0]), ','.join(map(str, BEAMS))]
            print('R85_A1C_DRY_RUN_COMMAND ' + shlex.join(cmd))
        print('R85_A1C_DRY_RUN_PASS_NO_SEARCH', flush=True)
    else:
        run_quality()


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
