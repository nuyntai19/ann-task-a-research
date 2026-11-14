#!/usr/bin/env python3
"""Compile a pinned MS-Turing-1M recall evaluator *outside* the R85 tree.

Safeguards: pin both old/new source, verify exactly 3 input-guard edits,
inspect includes, refuse overwrite, retain diagnostics, never run Search/BUILD.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys

HOME = Path.home()
ROOT = HOME / 'ann-task-a'
R85_SRC = ROOT / 'experiments/H85/r85_a1c_matched_search/r85_a1c_graph_recall.cc'
R85_BIN = ROOT / 'experiments/H85/r85_a1c_matched_search/r85_a1c_graph_recall'
NEW_SRC = ROOT / 'experiments/R86/msturing_1m_eval/r86_msturing1m_graph_recall.cc'
OUT = ROOT / 'experiments/R86/msturing_1m_eval/r86_msturing1m_graph_recall'
LOG = ROOT / 'experiments/R86/msturing_1m_eval/r86_msturing1m_eval_compile.log'
MANIFEST = ROOT / 'experiments/R86/msturing_1m_eval/r86_msturing1m_eval_compile.json'
H70 = ROOT / 'experiments/H70/pipnn-clean-443a328'
EXPECTED = {
    R85_SRC: 'a2b4f27e8dd9f7cd428c5568b1691eb6dc810d2cb7813a4e421ea238c13fb2c0',
    R85_BIN: '11587916ffd70143d6d5246bf8d2e26c1927b81bf8b3298fbc2014bfb6c64a4e',
    NEW_SRC: '91078479eb7fdb05a6070526797c4feaf01d6e994c13f699108e497ea0609b7e',
}
EDITS = (
    ('base.dimension() != 128', 'base.dimension() != 100'),
    ('queries.size() != 10000', 'queries.size() != 100000'),
    ('queries.dimension() != 128', 'queries.dimension() != 100'),
)

def fail(msg: str) -> None:
    raise RuntimeError('R86_MST_EVAL_COMPILE_HOLD: ' + msg)

def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1048576), b''):
            h.update(chunk)
    return h.hexdigest()

def preflight() -> tuple[str, list[str]]:
    for p, h in EXPECTED.items():
        if not p.is_file() or sha(p) != h:
            fail(f'SOURCE_OR_BINARY_PIN_MISMATCH path={p}')
        print(f'PIN_PASS sha256={h} path={p}')
    expected_text = R85_SRC.read_text(encoding='utf-8')
    for old, new in EDITS:
        if expected_text.count(old) != 1:
            fail('OLD_SOURCE_UNEXPECTED ' + old)
        expected_text = expected_text.replace(old, new, 1)
    if expected_text != NEW_SRC.read_text(encoding='utf-8'):
        fail('UNEXPECTED_SOURCE_DIFFERENCE_BEYOND_THREE_INPUT_GUARDS')
    if not (H70/'algorithms/utils/check_nn_recall.h').is_file():
        fail(f'PINNED_NATIVE_CHECK_RECALL_NOT_FOUND {H70}')
    candidates = [
        H70 / 'external/parlaylib/include',
        H70 / 'external/parlaylib',
        H70 / 'external/ParlayANN/include',
        H70 / 'external/ParlayANN',
        H70 / 'external/Parallel-KMeans',
        H70 / 'external/Parallel-KMeans/seeding',
        H70 / 'external/Highway',
        H70 / 'algorithms',
        H70 / 'algorithms/utils',
        H70,
        Path('/usr/include/eigen3'),
    ]
    includes = [str(p) for p in candidates if p.is_dir()]
    compiler = shutil.which('g++') or shutil.which('c++')
    if compiler is None:
        fail('CXX_COMPILER_NOT_FOUND')
    print(f'COMPILER={compiler}')
    print(f'INCLUDE_PATHS={len(includes)}')
    for inc in includes:
        print('INCLUDE ' + inc)
    print('R86_MST_EVAL_SOURCE_EQUIVALENCE_AND_BUILD_INPUT_PREFLIGHT_PASS')
    return compiler, includes

def compile_eval(compiler: str, includes: list[str]) -> None:
    if OUT.exists():
        fail(f'BINARY_DEST_ALREADY_EXISTS_NO_OVERWRITE {OUT}')
    if LOG.exists() or MANIFEST.exists():
        fail(f'RECEIPT_OR_LOG_ALREADY_EXISTS_NO_OVERWRITE {LOG} {MANIFEST}')
    OUT.parent.mkdir(parents=True, exist_ok=True)
    tmp = OUT.with_name(OUT.name + f'.part.{os.getpid()}')
    if tmp.exists():
        fail(f'TEMP_PATH_ALREADY_EXISTS {tmp}')
    cmd = [compiler, '-std=c++17', '-O3', '-DNDEBUG', '-pthread', '-fopenmp']
    for i in includes:
        cmd.extend(['-I', i])
    cmd += [str(NEW_SRC), '-o', str(tmp)]
    print('COMPILER_COMMAND ' + shlex.join(cmd), flush=True)
    with LOG.open('x', encoding='utf-8') as f:
        run = subprocess.run(cmd, stdout=f, stderr=subprocess.STDOUT, check=False)
    print(f'COMPILE_EXIT_CODE={run.returncode} log={LOG}')
    if run.returncode != 0:
        tmp.unlink(missing_ok=True)
        print('===== COMPILER LOG LAST 50 LINES =====')
        print('\n'.join(LOG.read_text(errors='replace').splitlines()[-50:]))
        fail('COMPILE_FAILED_SAVED_LOG_NO_BINARY')
    test = subprocess.run([str(tmp)], capture_output=True, text=True, timeout=15)
    if test.returncode != 2 or 'Usage:' not in test.stderr:
        tmp.unlink(missing_ok=True)
        fail(f'NO_ARG_USAGE_SMOKE_FAIL code={test.returncode} stderr={test.stderr[:200]}')
    if OUT.exists():
        tmp.unlink(missing_ok=True)
        fail('DEST_RACED_NO_OVERWRITE')
    # Atomic, no-overwrite hard-link within the same destination directory.
    os.link(tmp, OUT)
    tmp.unlink()
    manifest = {
        'status': 'COMPILE_AND_NO_ARG_SMOKE_PASS_NOT_SEARCH_VALIDATED',
        'source_sha256': sha(NEW_SRC),
        'binary_sha256': sha(OUT),
        'compiler': compiler,
        'command': cmd[:-1] + [str(OUT)],
        'log_sha256': sha(LOG),
        'native_search_semantics': 'R85 checkRecall unchanged; graph/GT on MS-Turing NOT tested',
    }
    with MANIFEST.open('x', encoding='utf-8') as f:
        json.dump(manifest, f, indent=2)
    print('NEW_EVAL_BINARY_SHA256=' + sha(OUT))
    print('NEW_EVAL_MANIFEST=' + str(MANIFEST))
    print('R86_MSTURING_EVAL_COMPILE_AND_USAGE_SMOKE_PASS_NOT_SEARCH_APPROVED')

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--preflight', action='store_true')
    mode.add_argument('--compile', action='store_true')
    args = parser.parse_args()
    try:
        c, inc = preflight()
        if args.compile:
            compile_eval(c, inc)
    except (OSError, RuntimeError, subprocess.TimeoutExpired) as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(2)
