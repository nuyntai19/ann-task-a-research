#!/usr/bin/env bash
# H32-R26b -- one SIFT1M author-FGraft ending on the exact R26a PiPNN pool;
# read-only native ParlayANN search against PiPNN and FG graph.
# NOT a speed or quality superiority claim unless actual graph arcs/bytes are matched.
set -Eeuo pipefail
ROOT="$HOME/ann-task-a"
BASE="$ROOT/experiments/H32/R22_source_gate"
R26A="$ROOT/experiments/H32/H32_R26a_pool_20261029_172452_132314"
R25="$ROOT/experiments/H32/H32_R25_pool_ending_20261029_170450_123214"
FG="$R25/fg_src/fg"
SEARCH="$ROOT/src/ParlayANN/algorithms/vamana/neighbors"
PY="$ROOT/experiments/H32/.venv-r25/bin/python"
D="$ROOT/data"
POOL="$R26A/dump.candidates.i32"
PI_GRAPH="$R26A/dump.graph"
OUT="$ROOT/experiments/H32/H32_R26b_sift1m_$(date +%Y%m%d_%H%M%S)_$$"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
V="$HERE/h32_r26b_report.py"
mkdir -p "$OUT"
trap 'code=$?; echo "R26B_STOP code=$code; inspect=$OUT" >&2' ERR
printf 'R26B_OUTPUT=%s\n' "$OUT"

need_sha() {
  local file="$1" expected="$2"
  [[ -s "$file" ]] || { echo "R26B_MISSING=$file" >&2; return 2; }
  local actual
  actual=$(sha256sum "$file" | awk '{print $1}')
  [[ "$actual" == "$expected" ]] || {
    printf 'R26B_SHA_MISMATCH file=%s expected=%s actual=%s\n' "$file" "$expected" "$actual" >&2
    return 2
  }
}

# Fail closed: every baseline input and executable must match a verified run.
[[ -x "$FG" && -x "$SEARCH" && -x "$PY" && -s "$V" ]]
[[ "$(git -C "$BASE/fgraft" rev-parse HEAD)" == a032c2d6cfb2c087d3b8abca028c745186501976 ]]
[[ "$(git -C "$ROOT/src/ParlayANN" rev-parse HEAD)" == a48c6a34e5f959190992aa531cc18454cfcc3dd3 ]]
need_sha "$FG" 74f0094b6ebf58e2d7cafbb06d339eac766c1b3fd9f8b007efff942cb84c697d
need_sha "$SEARCH" ee6b9c0bec2f32fe00607f3facc73691d2dca2d5158e84e69c226b3cd219c9a8
need_sha "$POOL" 7e22a4ca2b71bd560560f7e4aa2a1f2dcad46b8f25ae48ca8ea014c17086f9e8
need_sha "$PI_GRAPH" d497f6d19fff4b7db6436f960d036755e375be92483c03ec0b9ed61968d17bef
[[ "$(stat -c %s "$POOL")" == 640000000 ]]
[[ "$(stat -c %s "$PI_GRAPH")" == 95190528 ]]
for x in sift1m.fbin sift1m_queries.fbin sift1m_gt.ibin; do [[ -s "$D/$x" ]]; done
[[ -x /usr/bin/time ]] && command -v taskset >/dev/null
"$PY" -c 'import numpy as np; print("R26B_NUMPY", np.__version__)'
"$PY" "$V" selftest
if [[ -s "$R26A/base_data.sha256" ]];then
  (cd "$R26A" && sha256sum -c base_data.sha256)
fi
printf 'R26B_PREFLIGHT=PASS\n'

{
 echo 'R26B: SIFT1M same-candidate-pool FGraft dense-prune=1, spine=0, cap32, alpha1.2.'
 echo 'R26B binary/source pinned; 1 FGraft build ONLY; PiPNN R26a graph is read-only.'
 echo 'R26B 4 physical build CPUs=0,2,4,6; 1 search CPU=0; 5 internal search repeats/Q.'
 echo 'CAVEAT: fg total process time includes 800-base-point exact local-completeness and query/search diagnostics, NOT pure BUILD timing.'
 echo 'CAVEAT: FG and PiPNN graph arc budgets may differ; no superiority claim until matching.'
 git -C "$BASE/fgraft" rev-parse HEAD
 git -C "$ROOT/src/ParlayANN" rev-parse HEAD
 sha256sum "$FG" "$SEARCH" "$POOL" "$PI_GRAPH" "$V" "$0"
 df -h "$ROOT"; free -h
} >"$OUT/provenance.txt" 2>&1

# Convert SIFT1M base/query/groundtruth to FGraft-required .npy format.
# Stream base by blocks with memory mapping, do NOT materialize 1m x128 in RAM.
printf 'R26B_CONVERT_NPY_START\n'
"$PY" "$V" convert --data "$D" --out "$OUT" \
  > "$OUT/convert.log" 2>&1 || { tail -n 70 "$OUT/convert.log"; exit 3; }
printf 'R26B_CONVERT_NPY_PASS\n'

# Pin exact external author's FGraft candidate-ending source and parameters.
# Recall/GT are passed for FGraft's built-in diagnostics, NEVER used to build its graph.
FG_GRAPH="$OUT/fg_vamana_style_nospine.graph"
FG_ARGS=(
 --data "$OUT/sift_X.npy" --queries "$OUT/sift_Q.npy" --gold "$OUT/sift_GT100.npy"
 --metric l2 --dense 1 --dense-C 160 --dense-cands "$POOL"
 --dense-prune 1 --dense-spine 0
 --harvest 400 --harvest-cand 200 --harvest-cap 32 --harvest-alpha 1.2
 --threads 4 --seed 1 --k 10 --ef 100
 --dump-graph "$FG_GRAPH"
)
printf 'R26B_FGRAFT_BUILD_START=YES\n'
{
  printf 'COMMAND='; printf '%q ' "$FG" "${FG_ARGS[@]}"; printf '\n'
} > "$OUT/fg_command.txt"
if ! taskset -c 0,2,4,6 /usr/bin/time -v -o "$OUT/fg_process.time.log" \
      "$FG" "${FG_ARGS[@]}" >"$OUT/fg_process.log" 2>&1; then
  echo 'R26B_FGRAFT_PROCESS_FAILED' >&2
  tail -n 85 "$OUT/fg_process.log" >&2
  exit 4
fi
[[ -s "$FG_GRAPH" ]]
printf 'R26B_FGRAFT_GRAPH_SAVED=YES\n'

# Check graph integrity and arc budget BEFORE evaluating heldout search Recall.
"$PY" "$V" graph --pipnn "$PI_GRAPH" --fg "$FG_GRAPH" --out "$OUT" \
    | tee "$OUT/graph_audit.stdout.txt"

# One native ParlayANN executable, identical CLI parameters and Q for both.
# -Q is a FIXED beam width and source runs exactly 5 query repetitions internally.
# Run all Q values for both without additional graph BUILD.
for q in 80 100 120 160; do
  for arm in pipnn fg; do
    if [[ "$arm" == pipnn ]]; then graph="$PI_GRAPH";else graph="$FG_GRAPH";fi
    echo "R26B_SEARCH_START arm=$arm Q=$q"
    if ! env PARLAY_NUM_THREADS=1 taskset -c 0 \
         /usr/bin/time -v -o "$OUT/search_${arm}_q${q}.time.log" \
         "$SEARCH" \
            -base_path "$D/sift1m.fbin" \
            -query_path "$D/sift1m_queries.fbin" \
            -gt_path "$D/sift1m_gt.ibin" \
            -graph_path "$graph" \
            -data_type float -dist_func Euclidian \
            -R 32 -L 64 -alpha 1.2 -k 10 -Q "$q" \
            >"$OUT/search_${arm}_q${q}.log" 2>&1; then
      echo "R26B_SEARCH_FAILED arm=$arm Q=$q" >&2
      tail -n 70 "$OUT/search_${arm}_q${q}.log" >&2
      exit 5
    fi
    printf 'R26B_SEARCH_DONE arm=%s Q=%s\n' "$arm" "$q"
  done
done

"$PY" "$V" search --out "$OUT" | tee "$OUT/search_summary.stdout.txt"
printf 'R26B_DONE=%s\n' "$OUT"
cat "$OUT/r26b_summary.txt"
