#!/usr/bin/env bash
# Run ORIGINAL PiPNN candidate merge + HashPrune + final RobustPrune with sampled modifications.
# Fails if H18 selected leaf controls do not match actual native leaves.
set -Eeuo pipefail
KIT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="${PIPNN_REPO:-$HOME/ann-task-a/src/PiPNN}"
PLAN="${H25_R1_PLAN:-$HOME/ann-task-a/experiments/H25/r1_graph_gate_sift1m_seed42}"
OUT="${H25_R1_RUN_OUT:-$HOME/ann-task-a/experiments/H25/r1_native_build_sift1m_seed42}"
BASE="${SIFT_BASE:-$HOME/ann-task-a/data/sift1m.fbin}"
QUERIES="${SIFT_QUERIES:-$HOME/ann-task-a/data/sift1m_queries.fbin}"
GT="${SIFT_GT:-$HOME/ann-task-a/data/sift1m_gt.ibin}"
CPUSET="${H25_CPUSET:-0,2,4,6}"
THREADS="${H25_THREADS:-4}"
NQ="${H25_NQ:-1000}"
REPEATS="${H25_SEARCH_REPEATS:-3}"
EFS="${H25_EFS:-100,120,140,160,180,200,240,300}"
BIN="$REPO/build/algorithms/PipNN/neighbors-pipnn_FLOAT_T_EUCLIDEAN"
SEARCH_BIN="$KIT/h25_r1_common_search"
[[ -f "$PLAN/expected_rows.bin" ]] || { echo "Missing plan: $PLAN/expected_rows.bin" >&2;exit 2; }
[[ -x "$BIN" ]] || { echo "Missing PiPNN binary: $BIN; run cmake --build first" >&2;exit 2; }
[[ -x "$SEARCH_BIN" ]] || { echo "Missing evaluator: run python3 h25_r1_test.py" >&2;exit 2; }
[[ -f "$BASE" && -f "$QUERIES" && -f "$GT" ]] || { echo "SIFT files missing" >&2;exit 2; }
[[ ! -e "$OUT" ]] || { echo "Refusing to overwrite output directory: $OUT" >&2;exit 2; }
command -v taskset >/dev/null || { echo "taskset missing" >&2;exit 2; }
command -v /usr/bin/time >/dev/null || { echo "/usr/bin/time missing" >&2;exit 2; }
mkdir -p "$OUT"
{
 echo "H25 native R1 pilot. OFFLINE patch-generation time EXCLUDED from BUILD."
 echo "Repo=$REPO"; echo "Plan=$PLAN"; echo "Out=$OUT";
 echo "CPUSET=$CPUSET THREADS=$THREADS NQ=$NQ REPEATS=$REPEATS EFS=$EFS"
 echo "GitCommit=$(git -C "$REPO" rev-parse HEAD 2>/dev/null || echo UNKNOWN)"
 echo "ExecutableSHA256=$(sha256sum "$BIN")"
 echo "SearcherSHA256=$(sha256sum "$SEARCH_BIN")"
 echo "Graph examples: 3 one-run builds; NOT repeated BUILD, NOT a Pareto claim."
} | tee "$OUT/run_manifest.txt"
for policy in baseline nearest random; do
  graph="$OUT/${policy}.graph"; log="$OUT/${policy}_build.log";csv="$OUT/${policy}_eval.csv"
  echo "=== NATIVE BUILD: $policy ==="
  export H25_R1_ROWS="$PLAN/expected_rows.bin"
  export H25_R1_PATCH="$PLAN/patch_${policy}.bin"
  (
    cd "$REPO"
    env PARLAY_NUM_THREADS="$THREADS" H25_R1_ROWS="$H25_R1_ROWS" H25_R1_PATCH="$H25_R1_PATCH" \
      taskset -c "$CPUSET" /usr/bin/time -v "$BIN" \
      -base_path "$BASE" \
      -num_clusters 1 -fanout 30 -fanout_scheme 10,3 -cluster_size 1024 \
      -mst_deg 2 -alpha 1.2 -prune 1 -prune_all 1 -prune_degree 32 \
      -top_level_leaders 1000 -fraction_leaders 0.005 -hash_bits 12 \
      -graph_outfile "$graph"
  ) >"$log" 2>&1 || { echo "BUILD FAILED ($policy), log $log" >&2;tail -80 "$log";exit 3; }
  grep -q 'H25_R1_VERIFY_PASS' "$log" || { echo "MISSING H25 verifier PASS in $log" >&2;exit 3; }
  [[ -s "$graph" ]] || { echo "Graph missing/empty $graph" >&2;exit 3; }
  echo "=== COMMON EVALUATION: $policy ==="
  taskset -c "$CPUSET" "$SEARCH_BIN" \
    --graph "$graph" --base "$BASE" --queries "$QUERIES" --gt "$GT" \
    --efs "$EFS" --nq "$NQ" --repeats "$REPEATS" --csv "$csv" \
    >"$OUT/${policy}_search.log" 2>&1 || { echo "SEARCH FAILED ($policy)" >&2;tail -80 "$OUT/${policy}_search.log";exit 4; }
  sha256sum "$graph" >> "$OUT/graph_sha256.txt"
done
python3 "$KIT/h25_r1_summarize.py" --runs "$OUT" --out "$OUT/summary.json"
python3 "$KIT/h25_r1_edge_survival.py" --runs "$OUT" --plan "$PLAN" --out "$OUT/final_edge_presence.json"
echo "DONE. Send $OUT/summary.json plus native build logs if anything fails."
