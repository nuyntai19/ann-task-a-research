#!/usr/bin/env bash
# R70: guarded PiPNN stock/tier binary generation after integration.
# Usage: bash r70_build_variants.sh ~/ann-task-a
set -euo pipefail

if [[ "$#" -ne 1 ]]; then
  echo 'Usage: bash r70_build_variants.sh /path/to/ann-task-a' >&2
  exit 2
fi
ROOT="$(realpath "$1")"
OUT="$ROOT/experiments/H70"
WORK="$OUT/pipnn-clean-443a328"
BUILD="$OUT/build-r70"
BIN="$BUILD/algorithms/PipNN/neighbors-pipnn_FLOAT_T_EUCLIDEAN"
DEST="$OUT/bin"

if [[ ! -d "$WORK" || ! -d "$BUILD" ]]; then
  echo 'R70_BUILD_BLOCKED missing worktree or CMake build directory' >&2; exit 2
fi
if [[ "$(git -C "$WORK" rev-parse HEAD)" != 443a328dc71a3b7be753d52ca2b3c9a4ba77f3fd ]] || \
   [[ "$(git -C "$WORK" hash-object algorithms/utils/graph.h)" != 7c5b8c1196a3ad741dfd22fe8f35b72acae2b19f ]]; then
  echo 'R70_BUILD_BLOCKED pinned PiPNN source mismatch' >&2; exit 2
fi
if ! grep -Fq 'R70_RESERVOIR_VARIANT=TIER_B64_C' "$WORK/algorithms/PipNN/pipnn.h" || \
   ! grep -Fq 'target_compile_definitions(${TARGET_NAME} PRIVATE R70_TWO_TIER=1)' "$WORK/algorithms/PipNN/CMakeLists.txt"; then
  echo 'R70_BUILD_BLOCKED integration missing (do not trust old identical binaries)' >&2; exit 2
fi
mkdir -p "$DEST"
for item in 'OFF stock STOCK_FLAT' 'ON tier TIER_B64'; do
  read -r MODE LABEL BANNER <<< "$item"
  echo "===== R70 BUILD ${LABEL} ====="
  CONF_LOG="$OUT/r70_${LABEL}_configure.log"
  COMPILE_LOG="$OUT/r70_${LABEL}_compile.log"
  if ! cmake -S "$WORK" -B "$BUILD" -DCMAKE_BUILD_TYPE=Release -DR70_USE_TIER="$MODE" \
        > "$CONF_LOG" 2>&1; then
     echo "R70_${LABEL}_CONFIG_FAIL"; tail -n 40 "$CONF_LOG"; exit 3
  fi
  if ! grep -Fqx "R70_USE_TIER:BOOL=${MODE}" "$BUILD/CMakeCache.txt"; then
     echo "R70_${LABEL}_CONFIG_FLAG_MISMATCH"; exit 4
  fi
  if ! cmake --build "$BUILD" --target neighbors-pipnn_FLOAT_T_EUCLIDEAN -j1 \
        > "$COMPILE_LOG" 2>&1; then
     echo "R70_${LABEL}_COMPILE_FAIL"; tail -n 50 "$COMPILE_LOG"; exit 5
  fi
  if [[ ! -x "$BIN" ]] || ! grep -aFq "R70_RESERVOIR_VARIANT=${BANNER}_C" "$BIN"; then
     echo "R70_${LABEL}_BINARY_VARIANT_MARKER_MISSING"; exit 6
  fi
  cp "$BIN" "$DEST/r70_${LABEL}_pipnn"
  sha256sum "$DEST/r70_${LABEL}_pipnn"
  echo "R70_${LABEL}_BINARY_CONFIRMED"
done
if cmp -s "$DEST/r70_stock_pipnn" "$DEST/r70_tier_pipnn"; then
   echo 'R70_STOCK_TIER_IDENTICAL_FAIL'; exit 7
fi
printf '\nR70_STOCK_TIER_DISTINCT_PASS\n'
printf 'R70_BINARY_VARIANTS_COMPILED_NOT_RUNTIME_VALIDATED\n'
