#!/usr/bin/env bash
set -euo pipefail
SRC="${1:?Usage: build_four.sh /absolute/path/to/isolated/R86-source /absolute/path/to/R86-build-root}"
ROOT="${2:?Missing unique build root}"
[[ -f "$SRC/R86_STAGING_PROVENANCE.json" ]] || { echo 'FAIL: source must come from stage_r86_isolated.py' >&2; exit 2; }
[[ ! -e "$ROOT" ]] || { echo 'FAIL: do not overwrite existing build root' >&2;exit 2; }
mkdir -p "$ROOT"
for ARM in stock h17; do
  for MODE in off on; do
    ON=OFF;H17=OFF
    [[ "$MODE" == on ]] && ON=ON
    [[ "$ARM" == h17 ]] && H17=ON
    BUILD="$ROOT/${ARM}_${MODE}"
    echo "===== CONFIGURE $ARM $MODE ====="
    cmake -S "$SRC" -B "$BUILD" -DCMAKE_BUILD_TYPE=Release \
      -DR70_USE_TIER=OFF -DR71_USE_H17="$H17" -DR86_USE_COUNTERS="$ON"
    cmake --build "$BUILD" -j 4 --target neighbors-pipnn_FLOAT_T_EUCLIDEAN
    BINARY="$BUILD/algorithms/PipNN/neighbors-pipnn_FLOAT_T_EUCLIDEAN"
    test -x "$BINARY"
    sha256sum "$BINARY" | tee "$BUILD/R86_EXECUTABLE_SHA256.txt"
    grep -E '^(R70_USE_TIER|R71_USE_H17|R86_USE_COUNTERS):' "$BUILD/CMakeCache.txt"
  done
done
echo R86_FOUR_BUILD_COMMANDS_COMPLETED_NATIVE_GATES_STILL_REQUIRED
