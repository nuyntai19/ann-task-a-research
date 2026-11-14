#!/usr/bin/env bash
# Compiles and runs a C++ synthetic differential test in THIS directory only.
# No Git source, PiPNN graph, dataset, or old binary is modified.
set -euo pipefail
cd "$(dirname "$0")"
echo '========== R78 STANDALONE =========='
g++ -std=c++17 -O2 -Wall -Wextra -pthread -o ./r78_standalone_test ./r78_s1_tests.cc
./r78_standalone_test correctness
echo 'R78_STANDALONE_SCRIPT_COMPLETE'
