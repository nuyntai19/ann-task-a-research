#!/usr/bin/env bash
# H25-R1: randomized-order crossover SEARCH audit; NO BUILD, NO graph writes.
# Three-block Latin-square ordering controls systematic run-order bias.
set -euo pipefail

KIT="${HOME}/ann-task-a/experiments/H25/r1_kit"
ROOT="${HOME}/ann-task-a/experiments/H25/r1_native_build_sift1m_seed42"
BASE="${HOME}/ann-task-a/data/sift1m.fbin"
QUERIES="${HOME}/ann-task-a/data/sift1m_queries.fbin"
GT="${HOME}/ann-task-a/data/sift1m_gt.ibin"
CPUSET="${CPUSET:-0,2,4,6}"
EFS="${EFS:-140,160,180,200}"
NQ="${NQ:-10000}"
REPEATS="${REPEATS:-3}"
DEST="${ROOT}/crossover_$(date +%Y%m%d_%H%M%S)"

for path in "$KIT/h25_r1_common_search" "$KIT/h25_r1_crossover_analyze.py" "$BASE" "$QUERIES" "$GT" \
            "$ROOT/baseline.graph" "$ROOT/nearest.graph" "$ROOT/random.graph"; do
  if [[ ! -f "$path" ]]; then echo "FAIL_CLOSED missing file: $path" >&2; exit 2; fi
done
[[ "$NQ" == 10000 && "$REPEATS" == 3 && "$EFS" == "140,160,180,200" ]] || {
  echo "FAIL_CLOSED: this gate is pre-registered for NQ=10000 REPEATS=3 EFS=140,160,180,200" >&2; exit 2;
}
mkdir -- "$DEST" || exit 2
printf 'DEST=%s\nCPUSET=%s\nEFS=%s\nNQ=%s\nREPEATS=%s\n' "$DEST" "$CPUSET" "$EFS" "$NQ" "$REPEATS" | tee "$DEST/protocol.txt"
sha256sum "$ROOT"/{baseline,nearest,random}.graph > "$DEST/graph_hashes_before.sha256"
sha256sum "$KIT/h25_r1_common_search" > "$DEST/searcher_sha256.txt"

for round in 1 2 3; do
  case "$round" in
    1) ORDER="baseline nearest random";;
    2) ORDER="nearest random baseline";;
    3) ORDER="random baseline nearest";;
  esac
  printf '\n===== ROUND %d: %s =====\n' "$round" "$ORDER" | tee -a "$DEST/protocol.txt"
  for policy in $ORDER; do
    CSV="$DEST/r${round}_${policy}.csv"
    LOG="$DEST/r${round}_${policy}.log"
    printf '\nRUN round=%s policy=%s output=%s\n' "$round" "$policy" "$CSV"
    taskset -c "$CPUSET" "$KIT/h25_r1_common_search" \
      --graph "$ROOT/${policy}.graph" --base "$BASE" \
      --queries "$QUERIES" --gt "$GT" \
      --efs "$EFS" --nq "$NQ" --repeats "$REPEATS" \
      --csv "$CSV" 2>&1 | tee "$LOG"
  done
done
sha256sum "$ROOT"/{baseline,nearest,random}.graph > "$DEST/graph_hashes_after.sha256"
diff -u "$DEST/graph_hashes_before.sha256" "$DEST/graph_hashes_after.sha256" >/dev/null || {
  echo "FAIL_CLOSED: graph content changed during crossover" >&2; exit 2;
}
python3 "$KIT/h25_r1_crossover_analyze.py" "$DEST" | tee "$DEST/summary.txt"
printf '\nCROSSOVER_DONE %s\n' "$DEST"
