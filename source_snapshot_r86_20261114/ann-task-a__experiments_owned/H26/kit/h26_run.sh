#!/usr/bin/env bash
# Matched Build profiling, no modifications to existing H17/H25 source or graphs.
set -Eeuo pipefail
SOURCE="${H26_SOURCE:-$HOME/ann-task-a/experiments/H26/PiPNN-H26-src}"
OUTROOT="${H26_OUTROOT:-$HOME/ann-task-a/experiments/H26}"
BASE="${SIFT_BASE:-$HOME/ann-task-a/data/sift1m.fbin}"
CPUSET="${H26_CPUSET:-0,2,4,6}"
THREADS="${H26_THREADS:-4}"
ROUNDS="${H26_ROUNDS:-2}"
MODELS="${H26_MODELS:-stock top2}"
BIN="$SOURCE/build/algorithms/PipNN/neighbors-pipnn_FLOAT_T_EUCLIDEAN"
[[ -x "$BIN" ]] || { echo "H26_FAIL_CLOSED: no instrumented binary: $BIN" >&2; exit 2; }
[[ -s "$BASE" ]] || { echo "H26_FAIL_CLOSED: missing base data: $BASE" >&2; exit 2; }
[[ "$ROUNDS" =~ ^[1-9][0-9]*$ ]] || { echo "H26_FAIL_CLOSED: ROUNDS must be positive" >&2; exit 2; }
command -v taskset >/dev/null
command -v /usr/bin/time >/dev/null
# Avoid reusing or clobbering an experiment, including same-second collisions.
mkdir -p "$OUTROOT"
DEST="$(mktemp -d "$OUTROOT/H26_profile_$(date +%Y%m%d_%H%M%S)_XXXXXX")"
{
 echo "H26_PROFILE_RUN $(date --iso-8601=seconds)"
 echo "source=$SOURCE"
 echo "source_git=$(git -C "$SOURCE" rev-parse HEAD)"
 echo "binary_sha256=$(sha256sum "$BIN")"
 echo "base=$BASE";echo "base_sha256=$(sha256sum "$BASE")"
 echo "cpuset=$CPUSET threads=$THREADS rounds=$ROUNDS modes=$MODELS"
 echo "Validation H26_CHECK_TOP2 disabled during timed profiling; optional separate check."
} > "$DEST/manifest.txt"
echo "H26_OUTPUT=$DEST"
for (( r=1; r<=ROUNDS; r++ )); do
  # Alternating order across rounds minimizes simple warm-order effects.
  if ((r%2==0)); then order="top2 stock"; else order="$MODELS"; fi
  for mode in $order; do
    [[ "$mode" == "stock" || "$mode" == "top2" ]] || { echo "H26_FAIL_CLOSED: mode=$mode" >&2;exit 2; }
    log="$DEST/r${r}_${mode}.log"; graph="$DEST/r${r}_${mode}.graph"
    [[ ! -e "$log" && ! -e "$graph" ]] || { echo "H26_FAIL_CLOSED: output exists" >&2;exit 2; }
    echo "BEGIN round=$r mode=$mode"
    (
      cd "$SOURCE"
      env PARLAY_NUM_THREADS="$THREADS" H26_SELECTOR="$mode" H26_CHECK_TOP2=0 \
        taskset -c "$CPUSET" /usr/bin/time -v "$BIN" \
        -base_path "$BASE" \
        -num_clusters 1 -fanout 30 -fanout_scheme 10,3 -cluster_size 1024 \
        -mst_deg 2 -alpha 1.2 -prune 1 -prune_all 1 -prune_degree 32 \
        -top_level_leaders 1000 -fraction_leaders 0.005 -hash_bits 12 \
        -graph_outfile "$graph"
    ) >"$log" 2>&1 || { echo "H26_FAIL_CLOSED: BUILD error at $log" >&2;tail -n 60 "$log";exit 3; }
    grep -q '^H26_PROFILE,leaf_count,' "$log" || { echo "H26_FAIL_CLOSED: instrumentation missing: $log" >&2; exit 4; }
    [[ -s "$graph" ]] || { echo "H26_FAIL_CLOSED: graph missing" >&2;exit 5; }
    sha256sum "$graph" >> "$DEST/graph_sha256.txt"
    echo "DONE round=$r mode=$mode"
  done
done
python3 "$(dirname "${BASH_SOURCE[0]}")/h26_analyze.py" --dir "$DEST"
echo "H26_DONE=$DEST"
