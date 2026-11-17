#!/usr/bin/env python3
"""Safely adds a read-only graph evaluator to isolated pinned R70 worktree."""
import argparse
from pathlib import Path
import shutil
import subprocess

COMMIT = '443a328dc71a3b7be753d52ca2b3c9a4ba77f3fd'
GRAPH_BLOB = '7c5b8c1196a3ad741dfd22fe8f35b72acae2b19f'
MARKER = '# R70_RECALL_EVALUATOR_TARGET'
INSERT = '''\n# R70_RECALL_EVALUATOR_TARGET: reads saved graphs, does not build PiPNN graph\nadd_executable(r70_graph_recall r70_graph_recall.cc)\ntarget_link_libraries(r70_graph_recall PRIVATE\n  parlay ParlayANN Eigen3::Eigen absl::synchronization\n  absl::flat_hash_set absl::span hwy hwy_contrib)\ntarget_include_directories(r70_graph_recall PRIVATE\n  ../bench ../../external/Parallel-KMeans/seeding)\ntarget_compile_features(r70_graph_recall PRIVATE cxx_std_17)\n'''

def git(work, *args):
    return subprocess.check_output(['git', '-C', str(work), *args], text=True).strip()


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--worktree', required=True)
    a = p.parse_args()
    work = Path(a.worktree).resolve()
    if 'pipnn-clean-443a328' != work.name:
        raise SystemExit('R70_RECALL_SETUP_BLOCKED: not named isolated worktree')
    if git(work, 'rev-parse', 'HEAD') != COMMIT:
        raise SystemExit('R70_RECALL_SETUP_BLOCKED: unexpected git commit')
    if git(work, 'hash-object', 'algorithms/utils/graph.h') != GRAPH_BLOB:
        raise SystemExit('R70_RECALL_SETUP_BLOCKED: stock graph.h changed')
    dst = work / 'algorithms/PipNN/r70_graph_recall.cc'
    src = Path(__file__).with_name('r70_graph_recall.cc')
    cmake = work / 'algorithms/PipNN/CMakeLists.txt'
    if not cmake.is_file() or not src.is_file():
        raise SystemExit('R70_RECALL_SETUP_BLOCKED: missing files')
    orig = cmake.read_text()
    if MARKER in orig and INSERT.strip() not in orig:
        raise SystemExit('R70_RECALL_SETUP_BLOCKED: inconsistent previous setup')
    if dst.exists() and dst.read_bytes() != src.read_bytes():
        raise SystemExit('R70_RECALL_SETUP_BLOCKED: evaluator differs; preserve manual edits')
    if not dst.exists():
        shutil.copy2(src, dst)
    if MARKER not in orig:
        cmake.write_text(orig + INSERT)
        print('R70_RECALL_CMAKE_TARGET_ADDED')
    else:
        print('R70_RECALL_CMAKE_TARGET_EXISTS')
    print('R70_RECALL_SETUP_PASS')
    print('R70_STOCK_GRAPH_H_UNCHANGED', GRAPH_BLOB)
    print('R70_ONLY_ISOLATED_WORKTREE_MODIFIED')

if __name__ == '__main__':
    main()
