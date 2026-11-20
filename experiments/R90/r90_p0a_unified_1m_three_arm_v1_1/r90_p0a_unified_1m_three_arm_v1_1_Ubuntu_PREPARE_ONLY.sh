#!/usr/bin/env bash
# v1.1 PREPARE ONLY: no CMake, no BUILD, no Search, never modifies v1 receipts.
set -o pipefail
F="$HOME/Downloads/r90_p0a_unified_1m_three_arm_v1_1.py"
SHA="fa9cdc09b3f447161f5c1f65382b15a0bc9645f425a679b73ca26f5ce8abecf0"
OUT="$HOME/ann-task-a/experiments/R90/r90_p0a_unified_1m_three_arm_v1_1"
LOG="$HOME/R90_P0A_UNIFIED_SOURCE_PREPARE_ONLY_v1_1.log"
echo '===== R90 P0A V1.1 ONE-SNAPSHOT SOURCE PREPARE (NO BUILD) ====='
if [[ ! -f "$F" || -L "$F" || "$(sha256sum "$F" | awk '{print $1}')" != "$SHA" ]]; then
  echo R90_P0A_V11_SOURCE_RUNNER_SHA_HOLD
elif [[ -e "$OUT" || -L "$OUT" || -e "$LOG" || -L "$LOG" ]]; then
  echo R90_P0A_V11_OUTPUT_OR_LOG_EXISTS_HOLD
else
 (
  set -euo pipefail
  python3 "$F" selftest
  python3 "$F" preflight
  python3 "$F" prepare
  echo R90_P0A_V11_PREPARE_ONLY_SEQUENCE_COMPLETE
 ) 2>&1 | tee "$LOG"
 RC=${PIPESTATUS[0]}
 echo "R90_P0A_V11_PREPARE_ONLY_EXIT_CODE=$RC"
fi
echo TERMINAL_SAFE_END
