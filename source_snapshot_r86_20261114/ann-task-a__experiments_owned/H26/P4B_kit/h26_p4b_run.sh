#!/usr/bin/env bash
# P4b: 3-arm control (P0 / P4b OFF / P4b ON) + 1-thread sampled diagnostic.
set -Eeuo pipefail
ROOT="$HOME/ann-task-a"
P0="${H26P4B_P0_SOURCE:-$ROOT/experiments/H26/PiPNN-H26-src}"
SRC="${H26P4B_SOURCE:-$ROOT/experiments/H26/PiPNN-H26-P4B-src}"
BIN_P0="$P0/build/algorithms/PipNN/neighbors-pipnn_FLOAT_T_EUCLIDEAN"
BIN_B="$SRC/build/algorithms/PipNN/neighbors-pipnn_FLOAT_T_EUCLIDEAN"
BASE="${SIFT_BASE:-$ROOT/data/sift1m.fbin}"
OUTROOT="${H26P4B_OUTROOT:-$ROOT/experiments/H26}"
SAMPLE_MOD="${H26P4B_SAMPLE_MOD:-1024}"
[[ "$SAMPLE_MOD" =~ ^[0-9]+$ ]] || { echo 'H26P4B_FAIL_CLOSED: invalid sample mod' >&2;exit 2; }
[[ -x "$BIN_P0" && -x "$BIN_B" && -s "$BASE" ]] || { echo 'H26P4B_FAIL_CLOSED: binary/data missing' >&2; exit 2; }
command -v taskset >/dev/null
[[ -x /usr/bin/time ]] || { echo 'H26P4B_FAIL_CLOSED: GNU time not found' >&2;exit 2; }
mkdir -p "$OUTROOT"
OUT="$(mktemp -d "$OUTROOT/H26_P4B_$(date +%Y%m%d_%H%M%S)_XXXXXX")"
{
  date -Is
  echo 'study=H26-P4b lock acquisition/hold sampling, not CPU time or critical path'
  echo "P0_source=$P0"
  echo "P4B_source=$SRC"
  echo "p0_git=$(git -C "$P0" rev-parse HEAD)"
  echo "p4b_git=$(git -C "$SRC" rev-parse HEAD)"
  sha256sum "$BIN_P0" "$BIN_B" "$BASE"
  echo "sample_mod=$SAMPLE_MOD"
  echo 'graph_output=disabled, selector=top2, same SIFT1M, num_clusters=1, 4T CPU0,2,4,6'
} > "$OUT/manifest.txt"
echo "H26P4B_OUTPUT=$OUT"
run() {
  local label="$1" source="$2" nth="$3" cores="$4" mode="$5"
  local bin="$BIN_B" log="$OUT/$label.log" csv="$OUT/$label.csv"
  [[ "$source" == p0 ]] && bin="$BIN_P0"
  [[ ! -e "$log" && ! -e "$csv" ]] || { echo 'H26P4B_FAIL_CLOSED: output collision' >&2;exit 3; }
  echo "BEGIN $label ($source, ${nth}t, $mode)"
  (
    cd "$SRC"
    env PARLAY_NUM_THREADS="$nth" H26_SELECTOR=top2 H26_CHECK_TOP2=0 \
      H26P4B_LOCK_ENABLE="$mode" H26P4B_SAMPLE_MOD="$SAMPLE_MOD" \
      H26P4B_LOCK_TRACE_FILE="$csv" \
      taskset -c "$cores" /usr/bin/time -v "$bin" \
        -base_path "$BASE" -num_clusters 1 -fanout 30 \
        -fanout_scheme 10,3 -cluster_size 1024 -mst_deg 2 \
        -alpha 1.2 -prune 1 -prune_all 1 -prune_degree 32 \
        -top_level_leaders 1000 -fraction_leaders 0.005 -hash_bits 12
  ) >"$log" 2>&1 || { echo "H26P4B_FAIL_CLOSED: runner $label failed. Log tail:" >&2;tail -n 50 "$log" >&2;exit 4; }
  grep -q '^H26_PROFILE,leaf_count,85529$' "$log" || { echo "H26P4B_FAIL_CLOSED: leaf count wrong $label" >&2;exit 4; }
  grep -q '^H26_PROFILE,proposals,59990170$' "$log" || { echo "H26P4B_FAIL_CLOSED: proposal count wrong $label" >&2;exit 4; }
  if [[ "$source" == p4b ]];then
    grep -q "^H26P4B_LOCK,enabled,$mode$" "$log" || { echo "H26P4B_FAIL_CLOSED: recorder state wrong $label" >&2;exit 4; }
    if [[ "$mode" == 1 ]];then
      [[ -s "$csv" ]] || { echo "H26P4B_FAIL_CLOSED: missing CSV $label" >&2; exit 4; }
    fi
  fi
  echo "DONE $label"
}
run r1_p0      p0  4 '0,2,4,6' 0
run r1_off     p4b 4 '0,2,4,6' 0
run r1_on      p4b 4 '0,2,4,6' 1
run r1_1t_on   p4b 1 '0'       1
run r2_on      p4b 4 '0,2,4,6' 1
run r2_off     p4b 4 '0,2,4,6' 0
run r2_p0      p0  4 '0,2,4,6' 0
python3 "$(dirname "${BASH_SOURCE[0]}")/h26_p4b_analyze.py" --dir "$OUT"
echo "H26P4B_DONE=$OUT"
