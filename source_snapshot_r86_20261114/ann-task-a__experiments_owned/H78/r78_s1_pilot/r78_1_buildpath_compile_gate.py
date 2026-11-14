#!/usr/bin/env python3
"""R78.1 -- isolated C++ syntax-only instantiation of PiPNN build_index_impl
with the experimental S1 segmented reservoir. No ANN graph is built.

Write scope: only r78_1_buildpath_probe.cc alongside the existing R78 pilot.
Inputs: pinned H70 source and existing H70/build-r70/compile_commands.json.
This script does NOT modify H70 sources, binaries, build products, CMake, graphs,
datasets, or R78's validated native-test source/binary.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys

BASE = Path.home() / 'ann-task-a' / 'experiments'
WORK = BASE / 'H70' / 'pipnn-clean-443a328'
BUILD = BASE / 'H70' / 'build-r70'
HERE = BASE / 'H78' / 'r78_s1_pilot'
PROBE = HERE / 'r78_1_buildpath_probe.cc'

PINNED_HEAD = '443a328dc71a3b7be753d52ca2b3c9a4ba77f3fd'
PINS = {
    WORK / 'algorithms' / 'utils' / 'graph.h': '17e51779f32db56c9c50b6d514a8ff68539fd19b734804df3abdb63f88dd443e',
    WORK / 'algorithms' / 'PipNN' / 'pipnn.h': 'f4391ad8712d7757423dca872f9042c3271660dffde384a85b93854b9692f288',
    WORK / 'algorithms' / 'PipNN' / 'pipnn_utils.h': '7083e8183554a1cb586b70cdb4c57920f49ec5a50680096aecf6b873f596595d',
    HERE / 'r78_segmented_lshgraph.h': '8e2d16feda61644eab4fe730d1f78c43130f2a1d466523ed7712e68e423e41b7',
}

PROBE_SOURCE = r'''// R78.1 -- compile-only instantiation. NO main, NO execution, NO graph BUILD.
#include <cstdint>
#include <string>
#include "utils/euclidian_point.h"
#include "utils/point_range.h"
#include "PipNN/pipnn.h"
#include "r78_segmented_lshgraph.h"

namespace r78_compile_gate {
using Id = std::uint32_t;
using Point = parlayANN::Euclidian_Point<float>;
using PR = parlayANN::PointRange<Point>;
using Hash = ::SketchHash<Point, PR, Id>;
using S1 = parlayANN::R78SegmentedLSHGraph<Id, float, Hash>;

// This is an ordinary (non-template) function. Its body forces the compiler
// to instantiate the real PiPNN BUILD leaf / Final Prune path with S1's
// segmented NeighborView. It is never called or linked.
void force_build_path_template_check(parlayANN::Graph<Id>& output,
                                     ::commandLine& cli,
                                     PR& points,
                                     S1& candidates) {
  parlayANN::pipnn_index<Point, PR, Id> index;
  index.build_index_impl(
      output, cli, points,
      2L, 1024L, 2L,
      true, true, 1.1,
      64L, 100L, 1, 0, 0.005,
      std::string("10,3,1"), 12, 160L,
      candidates, 0UL);
}
}  // namespace r78_compile_gate
'''


def stop(reason: str) -> None:
    print('R78_1_BUILD_PATH_BLOCKED:', reason, flush=True)
    raise SystemExit(2)


def checksum(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def pinned_sources() -> None:
    if not HERE.is_dir():
        stop(f'R78 pilot folder missing: {HERE}')
    head = subprocess.run(
        ['git', '-C', str(WORK), 'rev-parse', 'HEAD'],
        capture_output=True, text=True, check=False,
    )
    if head.returncode != 0 or head.stdout.strip() != PINNED_HEAD:
        stop('H70 worktree HEAD differs from pinned source')
    for file, wanted in PINS.items():
        if not file.is_file():
            stop(f'missing pinned source: {file}')
        actual = checksum(file)
        if actual != wanted:
            stop(f'checksum mismatch: {file.name}: {actual} != {wanted}')
    print('R78_1_SOURCE_SHA256_GATE_PASS', flush=True)


def prior_compile_spec() -> tuple[list[str], Path]:
    db = BUILD / 'compile_commands.json'
    if not db.is_file():
        stop(f'missing existing CMake compile database: {db}')
    try:
        rows = json.loads(db.read_text())
    except (OSError, ValueError) as e:
        stop(f'cannot parse compile commands: {e}')
    matches = [
        entry for entry in rows
        if Path(entry.get('file', '')).resolve()
        == (WORK / 'algorithms' / 'PipNN' / 'r70_native_tests.cc').resolve()
    ]
    if len(matches) != 1:
        stop(f'expected exactly one existing R70 native compile entry; got {len(matches)}')
    entry = matches[0]
    command = (entry['arguments'][:] if 'arguments' in entry
               else shlex.split(entry['command']))
    if '-o' not in command or '-c' not in command:
        stop('unexpected original compile spec; expected -o <object> and -c <source>')
    # Remove all writing flags; -fsyntax-only must never write to H70/build-r70.
    for opt in ('-o', '-c', '-MF', '-MT', '-MQ'):
        if opt in command:
            pos = command.index(opt)
            if pos + 1 >= len(command):
                stop(f'malformed compiler args for {opt}')
            del command[pos:pos + 2]
    for opt in ('-MD', '-MMD', '-MP', '-save-temps'):
        command = [arg for arg in command if arg != opt]
    # Verify that no old source/object path remains as a bare compiler input.
    for arg in command:
        if arg.endswith('r70_native_tests.cc') or arg.endswith('r70_native_tests.cc.o'):
            stop(f'residual source/object in compile command: {arg}')
    command += [
        '-I' + str(HERE),
        '-DR71_H17_TOP2=1',
        '-fsyntax-only',
        str(PROBE),
    ]
    return command, Path(entry['directory'])


def main() -> None:
    print('========== R78.1 BUILD-PATH COMPILE-ONLY GATE ==========', flush=True)
    pinned_sources()
    if PROBE.exists():
        if PROBE.read_text() != PROBE_SOURCE:
            stop(f'existing probe differs; refusing overwrite: {PROBE}')
    else:
        # Exclusive creation: never overwrite existing user research files.
        with PROBE.open('x') as f:
            f.write(PROBE_SOURCE)
    command, cwd = prior_compile_spec()
    print('[R78.1] probe:', PROBE, flush=True)
    print('[R78.1] syntax-only argv:', shlex.join(command), flush=True)
    print('[R78.1] NO CMake, NO object/binary, NO ANN BUILD', flush=True)
    result = subprocess.run(command, cwd=cwd, check=False)
    if result.returncode:
        stop(f'compiler returned {result.returncode}; consult diagnostics above')
    print('R78_1_BUILD_PATH_TEMPLATE_PASS', flush=True)
    print('R78_1_NO_FULL_BUILD_NO_RECALL_NO_RSS', flush=True)
    print('R78_1_COMPILE_GATE_COMPLETE', flush=True)


if __name__ == '__main__':
    main()
