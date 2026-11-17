#!/usr/bin/env bash
# H32-R26b search metrics recovery ONLY: no BUILD, no source edits.
# Run as: bash h32_r26b_search_recovery.sh
set -Eeuo pipefail
ROOT="$HOME/ann-task-a"
OUT="$ROOT/experiments/H32/H32_R26b_sift1m_20261029_173518_137022"
KIT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PY="$ROOT/experiments/H32/.venv-r25/bin/python"
SCRIPT="$KIT/h32_r26b_search_recovery.py"
SEARCH="$ROOT/src/ParlayANN/algorithms/vamana/neighbors"
PI="$ROOT/experiments/H32/H32_R26a_pool_20261029_172452_132314/dump.graph"
FG="$OUT/fg_vamana_style_nospine.graph"
DATA="$ROOT/data"
trap 'status=$?; echo "R26B_SEARCH_RECOVERY_STOP code=$status inspect=$OUT" >&2' ERR
printf 'R26B_RECOVERY_ORIGINAL_OUTPUT=%s\n' "$OUT"
[[ -x "$SEARCH" && -x "$PY" && -s "$SCRIPT" ]]
[[ -s "$OUT/r26b_graph_report.json" ]]
[[ "$(git -C "$ROOT/src/ParlayANN" rev-parse HEAD)" == a48c6a34e5f959190992aa531cc18454cfcc3dd3 ]]
check_hash() { local x="$1" expected="$2" got; got="$(sha256sum "$x" | awk '{print $1}')"; if [[ "$got" != "$expected" ]]; then echo "SOURCE_SHA_MISMATCH: $x $got" >&2; return 2; fi; }
check_hash "$SEARCH" ee6b9c0bec2f32fe00607f3facc73691d2dca2d5158e84e69c226b3cd219c9a8
check_hash "$PI" d497f6d19fff4b7db6436f960d036755e375be92483c03ec0b9ed61968d17bef
check_hash "$FG" e0842613d7fc24e4b3b1f3ec60aff2ce4f5e054b3bcc51812a06c83355b64389
for x in sift1m.fbin sift1m_queries.fbin sift1m_gt.ibin; do [[ -s "$DATA/$x" ]]; done
[[ $(taskset -pc $$ | sed 's/.*: //') != '' ]]
"$PY" "$SCRIPT" selftest
printf '%s\n' 'R26B_RECOVERY_PREFLIGHT=PASS' 'R26B_ORIGINAL_NO_VERBOSE_LOGS=PRESERVED'
# New log names; never overwrite original 8 R26b search logs.
for q in 80 100 120 160; do
  for arm in pipnn fg; do
    if [[ "$arm" == 'pipnn' ]]; then g="$PI"; else g="$FG"; fi
    log="$OUT/search_${arm}_q${q}.verbose.log"
    tlog="$OUT/search_${arm}_q${q}.verbose.time.log"
    if [[ -e "$log" || -e "$tlog" ]]; then
      echo "R26B_STOP_REPLAY_FILE_ALREADY_EXISTS log=$log" >&2
      exit 3
    fi
    echo "R26B_REPLAY_SEARCH_START arm=$arm Q=$q"
    env PARLAY_NUM_THREADS=1 taskset -c 0 \
      /usr/bin/time -v -o "$tlog" \
      "$SEARCH" \
        -base_path "$DATA/sift1m.fbin" \
        -query_path "$DATA/sift1m_queries.fbin" \
        -gt_path "$DATA/sift1m_gt.ibin" \
        -graph_path "$g" \
        -data_type float -dist_func Euclidian \
        -R 32 -L 64 -alpha 1.2 -k 10 -Q "$q" -verbose \
      >"$log" 2>&1
    "$PY" "$SCRIPT" parse-one --log "$log" --q "$q"
    echo "R26B_REPLAY_SEARCH_DONE arm=$arm Q=$q"
  done
done
"$PY" "$SCRIPT" report --out "$OUT" | tee "$OUT/r26b_search_recovered.stdout.txt"
