#!/usr/bin/env bash
set -uo pipefail
PY="$HOME/Downloads/r91_g1b_mst10m_fastv2_search_screen_v1.py"
LOG="$HOME/R91_G1B_FASTV2_MST10M_SEARCH_PREFLIGHT_v1.log"
PREF="$HOME/ann-task-a/experiments/R91/r91_g1b_mst10m_fastv2_search_preflight_v1"
OUT="$HOME/ann-task-a/experiments/R91/r91_g1b_mst10m_fastv2_search_screen_v1"
EXPECTED="3566fc7e04d0b8833c3fed07fdd0a2612ecc7612223b7e43781f594a5e9223b5"
echo '===== R91 G1B MS-TURING10M FASTV2 EXISTING GRAPH SEARCH PREFLIGHT — NO BUILD / NO SEARCH ====='
if [[ ! -f "$PY" || -L "$PY" || "$(sha256sum "$PY" | awk '{print $1}')" != "$EXPECTED" ]]; then
 echo 'R91_G1B_PREFLIGHT_HOLD_SCRIPT_SHA'; rc=2
elif [[ -e "$LOG" || -L "$LOG" || -e "$PREF" || -L "$PREF" || -e "$OUT" || -L "$OUT" ]]; then
 echo 'R91_G1B_PREFLIGHT_HOLD_EXISTING_LOG_OR_OUTPUT_PRESERVE'; rc=2
elif ! command -v systemd-run >/dev/null || ! command -v python3 >/dev/null; then
 echo 'R91_G1B_PREFLIGHT_HOLD_DEPENDENCY'; rc=2
else
 (
  set -euo pipefail
  python3 "$PY" selftest
  systemd-run --user --scope --expand-environment=no \
   -p MemoryAccounting=yes -p MemoryMax=24G -p MemorySwapMax=0 \
   "$(command -v python3)" "$PY" scope-check
  python3 "$PY" preflight
  echo 'R91_G1B_SEARCH_PREFLIGHT_NO_BUILD_NO_SEARCH_PASS'
 ) 2>&1 | tee "$LOG"
 rc=${PIPESTATUS[0]}
fi
echo "R91_G1B_PREFLIGHT_NATIVE_EXIT_CODE=$rc"
echo 'TERMINAL_SAFE_END'
exit "$rc"
