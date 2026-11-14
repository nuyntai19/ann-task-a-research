#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$HOME/ann-task-a/experiments/H26"
SRC="$ROOT/PiPNN-H26-P1A-src"
KIT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN="$SRC/build/algorithms/PipNN/neighbors-pipnn_FLOAT_T_EUCLIDEAN"
BASE="$HOME/ann-task-a/data/sift1m.fbin"
[[ -x "$BIN" && -s "$BASE" ]] || { echo 'H26P1A_FAIL_CLOSED binary or SIFT1M missing' >&2;exit 2; }
COUNT="${H26P1A_ROUNDS:-2}"
[[ "$COUNT" =~ ^[0-9]+$ ]] && (( COUNT >= 2 )) || { echo 'H26P1A_FAIL_CLOSED: use at least two runs' >&2;exit 2; }
DEST="$(mktemp -d "$ROOT/H26_P1A_$(date +%Y%m%d_%H%M%S)_XXXXXX")"
echo "H26P1A_OUTPUT=$DEST"
{
 date --iso-8601=seconds
 echo "source_git=$(git -C "$SRC" rev-parse HEAD)"
 echo "binary_sha256=$(sha256sum "$BIN")"
 echo 'No graph output. P1a wall not directly comparable to H26-P0, which wrote graph.'
} > "$DEST/manifest.txt"
for ((j=1;j<=COUNT;j++)); do
 echo "BEGIN H26P1A run=$j"
 logfile="$DEST/p1a_r${j}_top2.log"
 env PARLAY_NUM_THREADS=4 H26_SELECTOR=top2 H26_CHECK_TOP2=0 \
 taskset -c 0,2,4,6 /usr/bin/time -v "$BIN" \
  -base_path "$BASE" \
  -num_clusters 1 -fanout 30 -fanout_scheme 10,3 -cluster_size 1024 \
  -mst_deg 2 -alpha 1.2 -prune 1 -prune_all 1 -prune_degree 32 \
  -top_level_leaders 1000 -fraction_leaders 0.005 -hash_bits 12 \
  > "$logfile" 2>&1 || { echo "H26P1A_FAIL_CLOSED: run=$j failed";tail -n 60 "$logfile";exit 3; }
 grep -q '^H26P1A,version,H26_P1A_v1$' "$logfile" || { echo "H26P1A_FAIL_CLOSED: no counters in $logfile";exit 3; }
 echo "DONE H26P1A run=$j"
done
python3 "$KIT/h26_p1a_analyze.py" --out "$DEST"
echo "H26P1A_DONE=$DEST"
