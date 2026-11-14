#!/usr/bin/env python3
"""H25-R1 hotfix for an already applied v2 PiPNN patch.

Only fixes RunLeaf -> EigenKNN call from 3 to 4 arguments.
Fails closed unless the existing instrumented code matches the expected state.
Usage:
  python3 h25_r1_fix_eigenknn_arity.py --mode check
  python3 h25_r1_fix_eigenknn_arity.py --mode apply
"""
import argparse
import shutil
import sys
from pathlib import Path

OLD = '''    leaf_count++;
    EigenKNN(G, Points, active_indices);
'''
NEW = '''    leaf_count++;
    EigenKNN(G, Points, active_indices, h25_leaf_id);
'''
EXPECTED_SIGNATURE = '''  void RunLeaf(GraphH &G, PR &Points,
               parlay::sequence<uint32_t> &active_indices, size_t h25_leaf_id) {'''
EXPECTED_EIGEN_SIGNATURE = '''  void EigenKNN(GraphH &G, PR &Points,
                     parlay::sequence<uint32_t> &active_indices, size_t h25_leaf_id) {'''
EXPECTED_EIGEN_TO_KNN = '''    eigen_knn(G, active_indices, Points, MST_DEG, h25_leaf_id);'''

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path,
                        default=Path.home() / 'ann-task-a/src/PiPNN')
    parser.add_argument('--mode', choices=['check', 'apply'], required=True)
    a = parser.parse_args()
    repo = a.repo.expanduser().resolve()
    srcdir = repo / 'algorithms/PipNN'
    filename = srcdir / 'pipnn.h'
    original_backup = srcdir / 'pipnn.h.h25r1_original'
    hook = srcdir / 'h25_r1_hook.h'
    if not filename.is_file() or not original_backup.is_file() or not hook.is_file():
        raise RuntimeError('Requires existing H25-R1 applied patch and original backup; files missing')
    content = filename.read_text(encoding='utf-8')
    if EXPECTED_SIGNATURE not in content:
        raise RuntimeError('RunLeaf does not have expected h25_leaf_id signature')
    if EXPECTED_EIGEN_SIGNATURE not in content:
        raise RuntimeError('EigenKNN does not have expected h25_leaf_id signature')
    if EXPECTED_EIGEN_TO_KNN not in content:
        raise RuntimeError('EigenKNN -> eigen_knn does not forward h25_leaf_id')
    if content.count(OLD) != 1:
        if content.count(NEW) == 1:
            print('ALREADY_FIXED: 4-argument EigenKNN call is present. No changes.')
            return
        raise RuntimeError(f'Expected exactly one 3-argument call, found {content.count(OLD)}')
    modified = content.replace(OLD, NEW, 1)
    assert modified.count(NEW) == 1
    if a.mode == 'check':
        print('HOTFIX_CHECK_PASS: only RunLeaf -> EigenKNN needs the fourth argument.')
        print('DRY RUN: no changes made.')
        return
    backup = srcdir / 'pipnn.h.h25r1_before_arity_hotfix'
    if backup.exists():
        raise RuntimeError(f'Backup already exists, refusing overwrite: {backup}')
    shutil.copy2(filename, backup)
    filename.write_text(modified, encoding='utf-8')
    print('HOTFIX_APPLIED: RunLeaf now passes h25_leaf_id into EigenKNN.')
    print(f'Previous instrumented header safely backed up: {backup}')
    print('Next: rerun cmake build. Do not rerun the old patch_source.py --mode apply.')

if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print('FAIL CLOSED:', exc, file=sys.stderr)
        sys.exit(2)
