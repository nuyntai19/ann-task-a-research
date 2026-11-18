#!/usr/bin/env bash
set -Eeuo pipefail
HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
OFFLINE=()
case "${1:-}" in
  "") ;;
  --offline) OFFLINE=(--offline) ;;
  *) echo "Usage: bash $0 [--offline]" >&2; exit 2 ;;
esac
for cmd in git cmake g++ make python3; do
  command -v "$cmd" >/dev/null || { echo "Missing required command: $cmd" >&2; exit 1; }
done
JOBS="${BUILD_JOBS:-2}"
[[ "$JOBS" =~ ^[1-9][0-9]*$ ]] || { echo 'BUILD_JOBS must be a positive integer' >&2; exit 2; }
mkdir -p "$HERE/logs"
LOG="$(mktemp "$HERE/logs/setup-XXXXXXXX.log")"
exec > >(tee "$LOG") 2>&1
echo "Setup log: $LOG"
python3 -c 'import numpy' || {
  echo 'Missing NumPy. Install python3-numpy for your Python interpreter, then retry.' >&2
  exit 1
}
python3 "$HERE/fetch_deps.py" "${OFFLINE[@]}"

TARGET=neighbors-pipnn_FLOAT_T_EUCLIDEAN
for VARIANT in stock_off h17_on; do
  H17=OFF; COUNTERS=OFF
  if [[ "$VARIANT" == h17_on ]]; then H17=ON; COUNTERS=ON; fi
  BUILD="$HERE/build/$VARIANT"
  cmake -S "$HERE" -B "$BUILD" -G 'Unix Makefiles' \
    -DCMAKE_BUILD_TYPE=Release -DR70_USE_TIER=OFF \
    "-DR71_USE_H17=$H17" "-DR86_USE_COUNTERS=$COUNTERS"
  cmake --build "$BUILD" --target "$TARGET" local_graph_recall r70_native_tests --parallel "$JOBS"
  PARLAY_NUM_THREADS=2 "$BUILD/algorithms/PipNN/r70_native_tests" correctness
done
python3 "$HERE/run.py" --dataset synthetic --variant stock_off
python3 "$HERE/run.py" --dataset synthetic --variant h17_on
echo 'LOCAL_SETUP_AND_SMOKE_PASS'
