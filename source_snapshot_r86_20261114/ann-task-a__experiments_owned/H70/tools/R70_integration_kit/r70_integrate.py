#!/usr/bin/env python3
"""R70: opt-in compile-time STOCK/TIER PiPNN integration in isolated pinned worktree.

No benchmark is launched. Source repo src/PiPNN is never modified.
"""
import argparse
import pathlib
import subprocess
import sys
import hashlib

COMMIT = '443a328dc71a3b7be753d52ca2b3c9a4ba77f3fd'
GRAPH_BLOB = '7c5b8c1196a3ad741dfd22fe8f35b72acae2b19f'
MARK = 'R70_COMPILE_TIME_RESERVOIR_SELECTION'


def git(path, *args):
    return subprocess.check_output(['git', '-C', str(path), *args], text=True).strip()


def block(reason):
    raise SystemExit('R70_INTEGRATION_BLOCKED ' + reason)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--worktree', required=True)
    a = p.parse_args()
    w = pathlib.Path(a.worktree).expanduser().resolve()
    if w.name != 'pipnn-clean-443a328' or not (w.parent.name == 'H70' and w.parent.parent.name == 'experiments'):
        block('worktree must be experiments/H70/pipnn-clean-443a328')
    if not w.is_dir() or git(w, 'rev-parse', 'HEAD') != COMMIT:
        block('incorrect pinned commit or directory')
    if git(w, 'hash-object', 'algorithms/utils/graph.h') != GRAPH_BLOB:
        block('stock graph.h differs from pinned original')
    native = w / 'algorithms/utils/r70_two_tier_lshgraph.h'
    if not native.is_file() or 'struct TwoTierLSHGraph' not in native.read_text():
        block('generated TwoTierLSHGraph header missing')
    ph = w / 'algorithms/PipNN/pipnn.h'
    cm = w / 'algorithms/PipNN/CMakeLists.txt'
    before = ph.read_text()
    cm_before = cm.read_text()
    if MARK in before or MARK in cm_before:
        if MARK in before and MARK in cm_before:
            print('R70_INTEGRATION_ALREADY_PRESENT')
            return
        block('partial prior integration; inspect manually')
    if git(w, 'hash-object', 'algorithms/PipNN/pipnn.h') != git(w, 'rev-parse', 'HEAD:algorithms/PipNN/pipnn.h'):
        block('pipnn.h already modified; do not overwrite unknown edits')

    include_key = '#include "../utils/graph.h"'
    if before.count(include_key) != 1:
        block('unexpected graph include')
    after = before.replace(include_key, include_key + '\n#ifdef R70_TWO_TIER\n#include "../utils/r70_two_tier_lshgraph.h"\n#endif // ' + MARK, 1)

    old_line = 'LSHGraph<indexType, float, SketchHash<Point, PointRange, indexType>> lsh_graph(Points.size(), (size_t)table_size, H, /*allocate=*/false);'
    if after.count(old_line) != 1:
        block('unexpected or multiple stock LSHGraph constructors')
    selected = '''// R70_COMPILE_TIME_RESERVOIR_SELECTION: keep all caller arguments and logical C unchanged.
#ifdef R70_TWO_TIER
        using R70GraphStorage = TwoTierLSHGraph<indexType, float, SketchHash<Point, PointRange, indexType>>;
        std::cout << "R70_RESERVOIR_VARIANT=TIER_B64_C" << table_size << std::endl;
#else
        using R70GraphStorage = LSHGraph<indexType, float, SketchHash<Point, PointRange, indexType>>;
        std::cout << "R70_RESERVOIR_VARIANT=STOCK_FLAT_C" << table_size << std::endl;
#endif
        R70GraphStorage lsh_graph(Points.size(), (size_t)table_size, H, /*allocate=*/false);'''
    after = after.replace(old_line, selected, 1)
    # The original template is used for both arms; no other PiPNN code changes.
    if cm_before.count('target_precompile_headers(${TARGET_NAME} PRIVATE neighbors.h)') != 1:
        block('unexpected PipNN target block')
    if 'R70_USE_TIER' in cm_before:
        block('R70_USE_TIER already configured in CMakeLists')
    option = '''# R70_COMPILE_TIME_RESERVOIR_SELECTION (research-only isolated worktree)
option(R70_USE_TIER "R70 Two-Tier physical reservoir; logical C unchanged" OFF)
'''
    cm_after = option + cm_before
    anchor = 'target_precompile_headers(${TARGET_NAME} PRIVATE neighbors.h)'
    cm_after = cm_after.replace(anchor, anchor + '''
        if(R70_USE_TIER)
            target_compile_definitions(${TARGET_NAME} PRIVATE R70_TWO_TIER=1)
        endif()''', 1)
    backups = w / 'r70_integration_backups'
    if backups.exists():
        block('backup directory already exists, avoiding overwrite')
    backups.mkdir()
    (backups / 'pipnn.h.original').write_text(before)
    (backups / 'CMakeLists.pipnn.original').write_text(cm_before)
    ph.write_text(after)
    cm.write_text(cm_after)
    # Guard that only expected files have been touched by this script.
    if before.count('build_index_impl') != after.count('build_index_impl'):
        block('unexpected template change')
    print('R70_INTEGRATION_PATCH_PASS')
    print('R70_STOCK_GRAPH_H_UNCHANGED', git(w,'hash-object','algorithms/utils/graph.h'))
    print('R70_PINNED_COMMIT', git(w,'rev-parse','HEAD'))
    print('R70_TWO_ARM_SELECT_USE -DR70_USE_TIER=OFF/ON')
    print('R70_ONLY_ISOLATED_WORKTREE_MODIFIED')
    print('R70_BENCHMARK_NOT_RUN')


if __name__ == '__main__':
    main()
