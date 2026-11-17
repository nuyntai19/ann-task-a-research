#!/usr/bin/env bash
# H26 P3b: disambiguate fused gains vs P3b top2 control regression.
set -Eeuo pipefail
ROOT="$HOME/ann-task-a/experiments/H26"
BASE="$HOME/ann-task-a/data/sift1m.fbin"
P0="$ROOT/PiPNN-H26-src/build/algorithms/PipNN/neighbors-pipnn_FLOAT_T_EUCLIDEAN"
P3B="$ROOT/PiPNN-H26-P3B-src/build/algorithms/PipNN/neighbors-pipnn_FLOAT_T_EUCLIDEAN"
KIT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CPUSET="${H26TRIAGE_CPUSET:-0,2,4,6}"
THREADS="${H26TRIAGE_THREADS:-4}"
for path in "$P0" "$P3B"; do [[ -x "$path" ]] || { echo "H26TRIAGE_FAIL_CLOSED missing binary: $path" >&2; exit 2; }; done
[[ -s "$BASE" ]] || { echo "H26TRIAGE_FAIL_CLOSED missing $BASE" >&2; exit 2; }
for program in python3 taskset sha256sum; do command -v "$program" >/dev/null || { echo "H26TRIAGE_FAIL_CLOSED missing $program" >&2; exit 2;}; done
[[ -x /usr/bin/time ]] || { echo "H26TRIAGE_FAIL_CLOSED missing /usr/bin/time" >&2; exit 2; }
OUT="$(mktemp -d "$ROOT/H26_P3B_TRIAGE_$(date +%Y%m%d_%H%M%S)_XXXXXX")"
ARGS=(-base_path "$BASE" -num_clusters 1 -fanout 30 -fanout_scheme 10,3 -cluster_size 1024 -mst_deg 2 -alpha 1.2 -prune 1 -prune_all 1 -prune_degree 32 -top_level_leaders 1000 -fraction_leaders 0.005 -hash_bits 12)
{
  date --iso-8601=seconds
  printf 'CPUSET=%s THREADS=%s\n' "$CPUSET" "$THREADS"
  sha256sum "$P0" "$P3B" "$BASE"
  echo 'P0: H26-P0 top2 baseline. P3B: v2 binary for top2 and fused. Both no graph output.'
  echo 'Three runs per arm, balanced order. No speedup/novelty claims from raw pilot.'
} > "$OUT/manifest.txt"
echo "H26TRIAGE_OUTPUT=$OUT"
echo '== SAMPLED NATIVE SEMANTICS PREFLIGHT (no timing) =='
PRE="$OUT/fused_preflight.log"
if ! env PARLAY_NUM_THREADS="$THREADS" H26_SELECTOR=fused H26_CHECK_TOP2=0 H26P3B_CHECK=1 \
    taskset -c "$CPUSET" "$P3B" "${ARGS[@]}" > "$PRE" 2>&1; then
    tail -n 60 "$PRE"; echo 'H26TRIAGE_FAIL_CLOSED preflight exit nonzero' >&2;exit 3
fi
checks="$(awk -F, '$1=="H26_PROFILE"&&$2=="top2_checks"{print $3}' "$PRE" | tail -n 1)"
leaves="$(awk -F, '$1=="H26P3B"&&$2=="fused_leaves"{print $3}' "$PRE" | tail -n 1)"
rows="$(awk -F, '$1=="H26P3B"&&$2=="fused_rows"{print $3}' "$PRE" | tail -n 1)"
if [[ ! "$checks" =~ ^[0-9]+$ ]] || ((checks < 1)) || [[ "$leaves" != '85529' || "$rows" != '29995085' ]] || grep -q 'H26P3B_FAIL_CLOSED' "$PRE"; then
  echo "H26TRIAGE_FAIL_CLOSED preflight checks=$checks leaves=$leaves rows=$rows" >&2
  tail -n 60 "$PRE"; exit 3
fi
echo "H26TRIAGE_SAMPLED_SEMANTICS_PASS checks=$checks fused_leaves=$leaves fused_rows=$rows"
# Three order positions, balanced, one of each variant each round.
for round in 1 2 3; do
  case "$round" in
   1) cases=(p0_top2 p3b_top2 p3b_fused);;
   2) cases=(p3b_top2 p3b_fused p0_top2);;
   3) cases=(p3b_fused p0_top2 p3b_top2);;
  esac
  for case_name in "${cases[@]}"; do
    case "$case_name" in
      p0_top2) binary="$P0"; selector=top2;;
      p3b_top2) binary="$P3B"; selector=top2;;
      p3b_fused) binary="$P3B"; selector=fused;;
    esac
    LOG="$OUT/r${round}_${case_name}.log"
    echo "BEGIN round=$round arm=$case_name"
    if ! env PARLAY_NUM_THREADS="$THREADS" H26_SELECTOR="$selector" H26_CHECK_TOP2=0 H26P3B_CHECK=0 \
      taskset -c "$CPUSET" /usr/bin/time -v "$binary" "${ARGS[@]}" > "$LOG" 2>&1; then
      tail -n 60 "$LOG";echo "H26TRIAGE_FAIL_CLOSED in $LOG" >&2;exit 4
    fi
    grep -q "^H26_PROFILE,selector,$selector$" "$LOG" || { echo "H26TRIAGE_FAIL_CLOSED selector in $LOG" >&2;exit 4; }
    echo "DONE round=$round arm=$case_name"
  done
done
python3 "$KIT/h26_p3b_triage_analyze.py" --out "$OUT"
echo "H26TRIAGE_DONE=$OUT"
