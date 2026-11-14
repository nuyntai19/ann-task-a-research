#!/usr/bin/env bash
# H26-P4a: leaf execution envelopes only. Not an exact critical-path trace.
set -Eeuo pipefail
ROOT="$HOME/ann-task-a"
SOURCE="${H26P4A_SOURCE:-$ROOT/experiments/H26/PiPNN-H26-P4A-src}"
BASE="${SIFT_BASE:-$ROOT/data/sift1m.fbin}"
BIN="$SOURCE/build/algorithms/PipNN/neighbors-pipnn_FLOAT_T_EUCLIDEAN"
OUTROOT="${H26P4A_OUTROOT:-$ROOT/experiments/H26}"
SCOPE="${H26P4A_SCOPE:-full}"   # quick: four-thread controlled only; full: also 1t/2t
[[ "$SCOPE" == quick || "$SCOPE" == full ]] || { echo 'H26P4A_FAIL_CLOSED: scope must be quick/full' >&2;exit 2; }
[[ -x "$BIN" && -s "$BASE" ]] || { echo "H26P4A_FAIL_CLOSED: binary/base missing" >&2;exit 2; }
command -v taskset >/dev/null
[[ -x /usr/bin/time ]] || { echo 'H26P4A_FAIL_CLOSED: GNU time missing' >&2;exit 2; }
command -v python3 >/dev/null
mkdir -p "$OUTROOT"
OUT="$(mktemp -d "$OUTROOT/H26_P4A_$(date +%Y%m%d_%H%M%S)_XXXXXX")"
{
 echo "H26P4A_START $(date -Is)"
 echo "source=$SOURCE"
 echo "pin=$(git -C "$SOURCE" rev-parse HEAD)"
 echo "binary_sha=$(sha256sum "$BIN")"
 echo "base_sha=$(sha256sum "$BASE")"
 echo "scope=$SCOPE; selector=top2; graph_output=disabled; P0 and P4 sources are not the same binary"
 echo "TRACE_ENABLED causes CSV I/O at process end and changes measured process wall time"
} > "$OUT/manifest.txt"
echo "H26P4A_OUTPUT=$OUT"

run() {
  local label="$1" nth="$2" cores="$3" trace="$4"
  local log="$OUT/$label.log" csv="$OUT/$label.csv"
  [[ ! -e "$log" && ! -e "$csv" ]] || { echo 'H26P4A_FAIL_CLOSED: output exists' >&2;exit 3; }
  echo "BEGIN $label threads=$nth trace=$trace cpuset=$cores"
  (
    cd "$SOURCE"
    env PARLAY_NUM_THREADS="$nth" H26_SELECTOR=top2 H26_CHECK_TOP2=0 \
      H26P4_TRACE="$trace" H26P4_TRACE_FILE="$csv" \
      taskset -c "$cores" /usr/bin/time -v "$BIN" \
       -base_path "$BASE" -num_clusters 1 -fanout 30 \
       -fanout_scheme 10,3 -cluster_size 1024 -mst_deg 2 \
       -alpha 1.2 -prune 1 -prune_all 1 -prune_degree 32 \
       -top_level_leaders 1000 -fraction_leaders 0.005 -hash_bits 12
  ) > "$log" 2>&1 || { echo "H26P4A_FAIL_CLOSED: $label failed; see $log" >&2;tail -n 50 "$log";exit 3; }
  grep -q '^H26_PROFILE,leaf_count,85529$' "$log" || { echo "H26P4A_FAIL_CLOSED: unexpected leaf count: $log" >&2;exit 4; }
  grep -q "^H26P4_TRACE,enabled,$trace$" "$log" || { echo "H26P4A_FAIL_CLOSED: recorder status wrong" >&2;exit 4; }
  if [[ "$trace" == 1 ]]; then
    [[ -s "$csv" ]] || { echo "H26P4A_FAIL_CLOSED: CSV missing" >&2;exit 5; }
  fi
  echo "DONE $label"
}
# 4-thread trace-off/on comparisons intentionally alternate; 1t/2t are scaling diagnostics only.
run r1_4t_off 4 '0,2,4,6' 0
run r1_4t_on  4 '0,2,4,6' 1
if [[ "$SCOPE" == full ]]; then
  run r1_2t_on 2 '0,2' 1
  run r1_1t_on 1 '0' 1
fi
run r2_4t_on  4 '0,2,4,6' 1
run r2_4t_off 4 '0,2,4,6' 0
python3 "$(dirname "${BASH_SOURCE[0]}")/h26_p4a_analyze.py" --dir "$OUT"
echo "H26P4A_DONE=$OUT"
