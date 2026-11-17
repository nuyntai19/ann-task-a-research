#!/usr/bin/env bash
# Executed in a child bash process; only writes new outputs inside this directory.
set -euo pipefail
cd "$(dirname "$0")"
echo '========== R78.3 STANDALONE FASTSHIFT =========='
g++ -std=c++17 -O2 -Wall -Wextra -Werror -pthread -o r78_3_standalone_test r78_3_s1_tests.cc
./r78_3_standalone_test correctness
echo R78_3_STANDALONE_SCRIPT_COMPLETE
