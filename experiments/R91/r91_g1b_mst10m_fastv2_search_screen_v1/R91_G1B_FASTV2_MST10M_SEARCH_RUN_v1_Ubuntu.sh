#!/usr/bin/env bash
set -uo pipefail
PY="$HOME/Downloads/r91_g1b_mst10m_fastv2_search_screen_v1.py"
PREF="$HOME/ann-task-a/experiments/R91/r91_g1b_mst10m_fastv2_search_preflight_v1/r91_g1b_preflight.json"
OUT="$HOME/ann-task-a/experiments/R91/r91_g1b_mst10m_fastv2_search_screen_v1"
LOG="$HOME/R91_G1B_FASTV2_MST10M_SEARCH_RUN_v1.log"
EXPECTED="3566fc7e04d0b8833c3fed07fdd0a2612ecc7612223b7e43781f594a5e9223b5"
echo '===== R91 G1B MS-TURING10M FASTV2 GRAPH SEARCH 100KQ BEAMS384,896 1CPU 24GiB/NOSWAP NO BUILD ====='
if [[ ! -f "$PY" || -L "$PY" || "$(sha256sum "$PY" | awk '{print $1}')" != "$EXPECTED" ]]; then
 echo 'R91_G1B_RUN_HOLD_SCRIPT_SHA'; rc=2
elif [[ ! -f "$PREF" || -L "$PREF" ]]; then
 echo 'R91_G1B_RUN_HOLD_PREFLIGHT_MISSING'; rc=2
elif [[ -e "$LOG" || -L "$LOG" || -e "$OUT" || -L "$OUT" ]]; then
 echo 'R91_G1B_RUN_HOLD_PREVIOUS_OUTPUT_OR_LOG_PRESERVE'; rc=2
elif ! command -v systemd-run >/dev/null || ! command -v python3 >/dev/null; then
 echo 'R91_G1B_RUN_HOLD_DEPENDENCY'; rc=2
else
 (
  set -euo pipefail
  systemd-run --user --scope --expand-environment=no \
   -p MemoryAccounting=yes -p MemoryMax=24G -p MemorySwapMax=0 \
   "$(command -v python3)" "$PY" run
  python3 "$PY" audit
  echo 'R91_G1B_NATIVE_SINGLE10M_GRAPH_SEARCH_SCREEN_AUDIT_PASS_NO_BUILD'
 ) 2>&1 | tee "$LOG"
 rc=${PIPESTATUS[0]}
fi
echo "R91_G1B_RUN_NATIVE_EXIT_CODE=$rc"
echo "R91_G1B_SEARCH_SUMMARY=$OUT/quality_screen_summary.json"
echo 'TERMINAL_SAFE_END'
exit "$rc"
