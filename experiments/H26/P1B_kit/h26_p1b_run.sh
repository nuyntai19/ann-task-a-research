#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$HOME/ann-task-a/experiments/H26"
SRC="$ROOT/PiPNN-H26-P1B-src"
BIN="$SRC/build/algorithms/PipNN/neighbors-pipnn_FLOAT_T_EUCLIDEAN"
KIT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE="$HOME/ann-task-a/data/sift1m.fbin"
[[ -x "$BIN" && -s "$BASE" ]] || { echo 'H26P1B_FAIL_CLOSED: binary or SIFT1M missing' >&2;exit 2; }
COUNT="${H26P1B_ROUNDS:-2}"
[[ "$COUNT" =~ ^[0-9]+$ ]] && (( COUNT >= 2 )) || { echo 'H26P1B_FAIL_CLOSED: need two runs' >&2;exit 2; }
DEST="$(mktemp -d "$ROOT/H26_P1B_$(date +%Y%m%d_%H%M%S)_XXXXXX")"
echo "H26P1B_OUTPUT=$DEST"
{
  date --iso-8601=seconds
  echo "source_git=$(git -C "$SRC" rev-parse HEAD)"
  echo "binary_sha256=$(sha256sum "$BIN")"
  echo 'No graph output; elapsed worker sum not BUILD wall.'
} > "$DEST/manifest.txt"
for ((j=1;j<=COUNT;j++)); do
  echo "BEGIN H26P1B run=$j"
  LOG="$DEST/p1b_r${j}_top2.log"
  env PARLAY_NUM_THREADS=4 H26_SELECTOR=top2 H26_CHECK_TOP2=0 \
    taskset -c 0,2,4,6 /usr/bin/time -v "$BIN" \
      -base_path "$BASE" \
      -num_clusters 1 -fanout 30 -fanout_scheme 10,3 -cluster_size 1024 \
      -mst_deg 2 -alpha 1.2 -prune 1 -prune_all 1 -prune_degree 32 \
      -top_level_leaders 1000 -fraction_leaders 0.005 -hash_bits 12 \
      > "$LOG" 2>&1 || { echo "H26P1B_FAIL_CLOSED: run $j";tail -n 50 "$LOG";exit 3; }
  grep -q '^H26P1B,version,H26_P1B_v1$' "$LOG" || { echo "H26P1B_FAIL_CLOSED: no histogram: $LOG";exit 3; }
  echo "DONE H26P1B run=$j"
done
python3 "$KIT/h26_p1b_analyze.py" --out "$DEST"
echo "H26P1B_DONE=$DEST"
