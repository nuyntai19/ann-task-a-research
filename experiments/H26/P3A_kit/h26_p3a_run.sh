#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$HOME/ann-task-a/experiments/H26"
KIT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC="$ROOT/PiPNN-H26-P3A-src"
BIN="$SRC/build/algorithms/PipNN/neighbors-pipnn_FLOAT_T_EUCLIDEAN"
BASE="$HOME/ann-task-a/data/sift1m.fbin"
[[ -x "$BIN" && -s "$BASE" ]] || { echo 'H26P3A_FAIL_CLOSED: binary or SIFT1M not found' >&2; exit 2; }
ROUNDS="${H26P3A_ROUNDS:-2}"
MOD="${H26P3A_SAMPLE_MOD:-64}"
[[ "$ROUNDS" =~ ^[0-9]+$ ]] && (( ROUNDS>=2 )) || { echo 'H26P3A_FAIL_CLOSED: use >=2 rounds' >&2; exit 2; }
[[ "$MOD" =~ ^(16|32|64|128)$ ]] || { echo 'H26P3A_FAIL_CLOSED: sample_mod invalid' >&2; exit 2; }
OUT="$(mktemp -d "$ROOT/H26_P3A_$(date +%Y%m%d_%H%M%S)_XXXXXX")"
echo "H26P3A_OUTPUT=$OUT"
{
  echo "time=$(date --iso-8601=seconds)"
  echo "source_git=$(git -C "$SRC" rev-parse HEAD)"
  echo "binary_sha256=$(sha256sum "$BIN")"
  echo "sample_mod=$MOD"
  echo 'Selection subphase sample; no graph output; no speedup claim.'
} > "$OUT/manifest.txt"
for ((i=1;i<=ROUNDS;i++)); do
  echo "BEGIN H26P3A run=$i sample_mod=$MOD"
  LOG="$OUT/p3a_r${i}_top2.log"
  env PARLAY_NUM_THREADS=4 H26_SELECTOR=top2 H26_CHECK_TOP2=0 H26P3A_SAMPLE_MOD="$MOD" \
  taskset -c 0,2,4,6 /usr/bin/time -v "$BIN" \
    -base_path "$BASE" \
    -num_clusters 1 -fanout 30 -fanout_scheme 10,3 -cluster_size 1024 \
    -mst_deg 2 -alpha 1.2 -prune 1 -prune_all 1 -prune_degree 32 \
    -top_level_leaders 1000 -fraction_leaders 0.005 -hash_bits 12 \
    > "$LOG" 2>&1 || { echo "H26P3A_FAIL_CLOSED: run=$i failed" >&2;tail -n 60 "$LOG";exit 3; }
  grep -q '^H26P3A,version,H26_P3A_v1$' "$LOG" || { echo 'H26P3A_FAIL_CLOSED: missing P3A counters' >&2;exit 3; }
  echo "DONE H26P3A run=$i"
done
python3 "$KIT/h26_p3a_analyze.py" --out "$OUT"
echo "H26P3A_DONE=$OUT"
