#!/usr/bin/env python3
"""Add a separate SIFT1M-only SEARCH evaluator to the pinned *isolated* PiPNN worktree.
Never edits previous R70 evaluator, original repository, or BUILDs.
"""
from pathlib import Path
import argparse
import hashlib
import subprocess
import sys

PINNED_COMMIT = '443a328dc71a3b7be753d52ca2b3c9a4ba77f3fd'
PINNED_GRAPH = '7c5b8c1196a3ad741dfd22fe8f35b72acae2b19f'
R70_SOURCE_SHA256 = '31e34e9bbde76467e675b8ede0f756de05750545b028cf482699cd66935d8b93'
TARGET = 'r72_graph_recall'
MARKER = '# R72_SIFT1M_RECALL_EVALUATOR_TARGET'
CMAKE_APPEND = '''
# R72_SIFT1M_RECALL_EVALUATOR_TARGET: SIFT1M search-only; does NOT BUILD graph
add_executable(r72_graph_recall r72_graph_recall.cc)
target_link_libraries(r72_graph_recall PRIVATE
  parlay ParlayANN Eigen3::Eigen absl::synchronization
  absl::flat_hash_set absl::span hwy hwy_contrib)
target_include_directories(r72_graph_recall PRIVATE
  ../bench ../../external/Parallel-KMeans/seeding)
target_compile_features(r72_graph_recall PRIVATE cxx_std_17)
'''

def require(cond, message):
    if not cond:
        raise RuntimeError(message)

def git(work, *cmd):
    return subprocess.check_output(['git','-C',str(work),*cmd], text=True).strip()

def sha256(blob):
    return hashlib.sha256(blob).hexdigest()

def make_source(base):
    require(sha256(base) == R70_SOURCE_SHA256,
            'R72_BLOCKED existing R70 evaluator source is not the audited pinned version')
    src = base.decode('utf-8')
    old = 'base.size() != 100000 || base.dimension() != 128 ||'
    new = 'base.size() != 1000000 || base.dimension() != 128 ||'
    require(src.count(old) == 1, 'R72_BLOCKED unexpected base size gate')
    src = src.replace(old, new)
    old = 'queries.size() != 300 || queries.dimension() != 128 ||'
    new = 'queries.size() != 10000 || queries.dimension() != 128 ||'
    require(src.count(old) == 1, 'R72_BLOCKED unexpected query size gate')
    src = src.replace(old, new)
    src = src.replace('R70_RECALL_', 'R72_RECALL_')
    src = src.replace('r70_graph_recall GRAPH', 'r72_graph_recall GRAPH')
    require('base.size() != 1000000' in src and 'queries.size() != 10000' in src,
            'R72_BLOCKED SIFT1M gate not applied')
    return src.encode('utf-8')

def main():
    a = argparse.ArgumentParser(description=__doc__)
    a.add_argument('--worktree', type=Path, required=True)
    args = a.parse_args()
    work = args.worktree.resolve()
    require(work.name == 'pipnn-clean-443a328', 'R72_BLOCKED unexpected worktree name')
    require(git(work, 'rev-parse', 'HEAD') == PINNED_COMMIT,
            'R72_BLOCKED unexpected git HEAD')
    require(git(work, 'hash-object', 'algorithms/utils/graph.h') == PINNED_GRAPH,
            'R72_BLOCKED stock graph.h modified')
    source = work / 'algorithms/PipNN/r70_graph_recall.cc'
    dest = work / 'algorithms/PipNN/r72_graph_recall.cc'
    cmake = work / 'algorithms/PipNN/CMakeLists.txt'
    require(source.is_file() and cmake.is_file(), 'R72_BLOCKED R70 evaluator or CMake missing')
    patched = make_source(source.read_bytes())
    text = cmake.read_text()
    if dest.exists():
        require(dest.read_bytes() == patched, 'R72_BLOCKED existing R72 evaluator differs; preserved')
        print('R72_EVALUATOR_SOURCE_ALREADY_PRESENT')
    else:
        # Exclusive creation: prevents accidental overwrites.
        with dest.open('xb') as f:
            f.write(patched)
        print('R72_EVALUATOR_SOURCE_CREATED')
    if MARKER in text:
        require(text.count(MARKER) == 1 and CMAKE_APPEND.strip() in text,
                'R72_BLOCKED existing CMake R72 target differs; preserved')
        print('R72_CMAKE_TARGET_ALREADY_PRESENT')
    else:
        # CMake change limited to the isolated H70 worktree, not src/PiPNN.
        with cmake.open('a', encoding='utf-8') as f:
            f.write(CMAKE_APPEND)
        print('R72_CMAKE_TARGET_ADDED')
    print(f'R72_EVALUATOR_SHA256 {sha256(patched)}')
    print('R72_STOCK_GRAPH_H_UNCHANGED', PINNED_GRAPH)
    print('R72_EVALUATOR_SETUP_PASS NOT_COMPILED_NOT_EVALUATED')

if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print(f'R72_EVALUATOR_SETUP_FAIL {type(e).__name__}: {e}', file=sys.stderr)
        sys.exit(1)
