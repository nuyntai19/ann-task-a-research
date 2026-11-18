#!/usr/bin/env bash
set -Eeuo pipefail
HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
mkdir -p "$HERE/logs"
LOG="$(mktemp "$HERE/logs/setup-XXXXXXXX.log")"
exec > >(tee "$LOG") 2>&1
echo "SETUP_LOG=$LOG"
python3 "$HERE/../../local_setup/khoa-linux/fetch_deps.py" --offline
cmake -S "$HERE" -B "$HERE/build" -DCMAKE_BUILD_TYPE=Release \
  -DR70_USE_TIER=OFF -DR71_USE_H17=ON -DR86_USE_COUNTERS=OFF
cmake --build "$HERE/build" --target neighbors-pipnn_FLOAT_T_EUCLIDEAN local_graph_recall --parallel "${BUILD_JOBS:-2}"
