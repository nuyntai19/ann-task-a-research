#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$HOME/ann-task-a/experiments/H26"
KIT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC="$ROOT/PiPNN-H26-P3B-src"
BIN="$SRC/build/algorithms/PipNN/neighbors-pipnn_FLOAT_T_EUCLIDEAN"
BASE="$HOME/ann-task-a/data/sift1m.fbin"
[[ -x "$BIN" && -s "$BASE" ]] || { echo 'H26P3B_FAIL_CLOSED: binary or SIFT1M not found' >&2;exit 2;}
ROUNDS="${H26P3B_ROUNDS:-3}"
[[ "$ROUNDS" =~ ^[0-9]+$ ]] && ((ROUNDS>=2)) || { echo 'H26P3B_FAIL_CLOSED: ROUNDS>=2 required' >&2;exit 2;}
OUT="$(mktemp -d "$ROOT/H26_P3B_$(date +%Y%m%d_%H%M%S)_XXXXXX")"
{
 echo "created=$(date --iso-8601=seconds)"
 echo "commit=$(git -C "$SRC" rev-parse HEAD)"
 echo "binary_sha256=$(sha256sum "$BIN")"
 echo 'one binary; H26_SELECTOR=top2 or fused; same build options; no graph output'
 echo 'worker elapsed sums and process wall; neither is novel contribution'
} > "$OUT/manifest.txt"
echo "H26P3B_OUTPUT=$OUT"
for ((r=1;r<=ROUNDS;r++)); do
  if ((r%2==1));then modes=(top2 fused);else modes=(fused top2);fi
  for mode in "${modes[@]}"; do
    echo "BEGIN round=$r mode=$mode"
    LOG="$OUT/r${r}_${mode}.log"
    env PARLAY_NUM_THREADS=4 H26_SELECTOR="$mode" H26_CHECK_TOP2=0 H26P3B_CHECK=0 \
      taskset -c 0,2,4,6 /usr/bin/time -v "$BIN" \
      -base_path "$BASE" -num_clusters 1 -fanout 30 -fanout_scheme 10,3 \
      -cluster_size 1024 -mst_deg 2 -alpha 1.2 -prune 1 -prune_all 1 -prune_degree 32 \
      -top_level_leaders 1000 -fraction_leaders 0.005 -hash_bits 12 \
      > "$LOG" 2>&1 || { echo "H26P3B_FAIL_CLOSED: failed round=$r mode=$mode" >&2; tail -n 60 "$LOG";exit 3; }
    grep -q "^H26_PROFILE,selector,$mode$" "$LOG" || { echo 'H26P3B_FAIL_CLOSED: wrong selector in log' >&2; exit 3; }
    if [[ "$mode" == "fused" ]]; then
      grep -q '^H26P3B,version,H26_P3B_v1$' "$LOG" || { echo 'H26P3B_FAIL_CLOSED: no fused stats' >&2; exit 3; }
      grep -q '^H26P3B,fused_rows,29995085$' "$LOG" || { echo 'H26P3B_FAIL_CLOSED: unexpected fused rows' >&2; exit 3; }
    fi
    echo "DONE round=$r mode=$mode"
  done
done
python3 "$KIT/h26_p3b_analyze.py" --out "$OUT"
echo "H26P3B_DONE=$OUT"
