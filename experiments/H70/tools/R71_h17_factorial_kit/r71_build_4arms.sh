#!/usr/bin/env bash
# Four-variant BUILD. Never touches src/PiPNN or existing R70 bin/ artifacts.
set -euo pipefail
if [[ "$#" -ne 1 ]]; then
  echo 'Usage: bash r71_build_4arms.sh /path/to/ann-task-a' >&2; exit 2
fi
ROOT="$(realpath "$1")"
OUT="$ROOT/experiments/H70"
WORK="$OUT/pipnn-clean-443a328"
BUILD="$OUT/build-r70"
DEST="$OUT/r71-bin"
TARGET=neighbors-pipnn_FLOAT_T_EUCLIDEAN
BINARY="$BUILD/algorithms/PipNN/$TARGET"
[[ -d "$WORK" && -d "$BUILD" ]] || { echo 'R71_BUILD_BLOCKED missing existing isolated worktree / build'; exit 2; }
[[ "$(git -C "$WORK" rev-parse HEAD)" == 443a328dc71a3b7be753d52ca2b3c9a4ba77f3fd ]] || { echo 'R71_BUILD_BLOCKED pinned commit mismatch'; exit 2; }
[[ "$(git -C "$WORK" hash-object algorithms/utils/graph.h)" == 7c5b8c1196a3ad741dfd22fe8f35b72acae2b19f ]] || { echo 'R71_BUILD_BLOCKED stock graph.h changed'; exit 2; }
for f in algorithms/PipNN/pipnn.h algorithms/PipNN/pipnn_utils.h algorithms/PipNN/CMakeLists.txt; do
  grep -q 'R71_H17_PACKED_TOP2_ISOLATED' "$WORK/$f" || { echo "R71_BUILD_BLOCKED no patch marker in $f"; exit 2; }
done
[[ ! -e "$DEST" ]] || { echo "R71_BUILD_BLOCKED old $DEST exists; preserve and investigate"; exit 2; }
mkdir "$DEST"
# First reconstruct A and C (H17 OFF), then B and D (H17 ON).
# Reusing one build directory reduces third-party compilation; each -D change
# invalidates precompiled headers and target objects as needed.
for SPEC in \
  'OFF OFF A_stock STOCK_FLAT STOCK_HIGHWAY' \
  'OFF ON C_tier TIER_B64 STOCK_HIGHWAY' \
  'ON OFF B_h17 STOCK_FLAT H17_PACKED_TOP2' \
  'ON ON D_h17_tier TIER_B64 H17_PACKED_TOP2'; do
  read -r H17 TIER LABEL RESMARK H17MARK <<< "$SPEC"
  echo "========== R71 BUILD $LABEL H17=$H17 TIER=$TIER =========="
  CL="$DEST/${LABEL}.configure.log"
  BL="$DEST/${LABEL}.compile.log"
  if ! cmake -S "$WORK" -B "$BUILD" -DCMAKE_BUILD_TYPE=Release \
        -DR70_USE_TIER="$TIER" -DR71_USE_H17="$H17" > "$CL" 2>&1; then
    echo "R71_${LABEL}_CMAKE_FAIL"; tail -n 45 "$CL"; exit 3
  fi
  grep -Fqx "R70_USE_TIER:BOOL=$TIER" "$BUILD/CMakeCache.txt" || { echo "R71_${LABEL}_TIER_FLAG_MISMATCH"; exit 3; }
  grep -Fqx "R71_USE_H17:BOOL=$H17" "$BUILD/CMakeCache.txt" || { echo "R71_${LABEL}_H17_FLAG_MISMATCH"; exit 3; }
  if ! cmake --build "$BUILD" --target "$TARGET" -j1 > "$BL" 2>&1; then
    echo "R71_${LABEL}_COMPILE_FAIL"; tail -n 45 "$BL"; exit 4
  fi
  [[ -x "$BINARY" ]] || { echo "R71_${LABEL}_BINARY_MISSING"; exit 5; }
  grep -aFq "R70_RESERVOIR_VARIANT=${RESMARK}_C" "$BINARY" || { echo "R71_${LABEL}_RESERVOIR_MARKER_MISSING"; exit 5; }
  grep -aFq "R71_SELECTION_VARIANT=${H17MARK}" "$BINARY" || { echo "R71_${LABEL}_H17_MARKER_MISSING"; exit 5; }
  cp "$BINARY" "$DEST/$LABEL"
  sha256sum "$DEST/$LABEL"
  echo "R71_${LABEL}_BINARY_CONFIRMED"
done
python3 - "$DEST" <<'PY'
from pathlib import Path
import hashlib, sys
p=Path(sys.argv[1]); names=('A_stock','B_h17','C_tier','D_h17_tier')
h={n:hashlib.sha256((p/n).read_bytes()).hexdigest() for n in names}
for n in names: print('R71_BINARY_SHA256', n, h[n])
if len(set(h.values())) != 4:
    raise SystemExit('R71_BINARY_DISTINCT_FAIL')
print('R71_FOUR_BINARY_VARIANTS_PASS')
print('R71_COMPILATION_ONLY_NOT_ALGORITHM_CORRECTNESS')
PY
