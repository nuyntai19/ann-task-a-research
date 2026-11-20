#!/usr/bin/env bash
# SOURCE GATE ONLY. DOES NOT COMPILE/BUILD/SEARCH 1M DATA.
set -o pipefail
F="$HOME/Downloads/r90_p0a_unified_1m_three_arm_v1.py"
SHA="055f36902c1ce6d3c5bdcc116c9e0703cd7dd7ff33ee2c32ed64bb3b345a8d44"
OUT="$HOME/ann-task-a/experiments/R90/r90_p0a_unified_1m_three_arm_v1"
LOG="$HOME/R90_P0A_UNIFIED_SOURCE_PREPARE_ONLY_v1.log"
echo '===== R90 P0A ONE-SNAPSHOT SOURCE PREPARE (NO BUILD) ====='
if [[ ! -f "$F" || -L "$F" || "$(sha256sum "$F" | awk '{print $1}')" != "$SHA" ]]; then
  echo R90_P0A_SOURCE_RUNNER_SHA_HOLD
elif [[ -e "$OUT" || -L "$OUT" || -e "$LOG" || -L "$LOG" ]]; then
  echo R90_P0A_OUTPUT_OR_LOG_EXISTS_HOLD
else
 (
  set -euo pipefail
  python3 "$F" selftest
  python3 "$F" preflight
  python3 "$F" prepare
  echo R90_P0A_PREPARE_ONLY_SEQUENCE_COMPLETE
 ) 2>&1 | tee "$LOG"
 RC=${PIPESTATUS[0]}
 echo "R90_P0A_PREPARE_ONLY_EXIT_CODE=$RC"
fi
echo TERMINAL_SAFE_END
