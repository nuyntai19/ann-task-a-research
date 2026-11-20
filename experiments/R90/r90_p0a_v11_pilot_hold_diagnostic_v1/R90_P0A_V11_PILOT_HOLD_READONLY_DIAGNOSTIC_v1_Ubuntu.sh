#!/usr/bin/env bash
# SAFE: only reads old P0A source, manifests, six graph/log/binary records.
# Writes one NEW diagnostic directory and one NEW log; never rebuilds.
set -uo pipefail
F="$HOME/Downloads/r90_p0a_v11_pilot_hold_diagnostic_v1.py"
SHA="e2714a0e9ab66531c4e8c72a6c0fc457696062e189a4a6d04ad984b848e9acb2"
OUT="$HOME/ann-task-a/experiments/R90/r90_p0a_v11_pilot_hold_diagnostic_v1"
LOG="$HOME/R90_P0A_V11_PILOT_HOLD_DIAGNOSTIC_V1.log"
echo '===== R90-P0A V1.1 GRAPH PARITY HOLD READ-ONLY DIAGNOSTIC ====='
if [[ ! -f "$F" || -L "$F" || "$(sha256sum "$F" | awk '{print $1}')" != "$SHA" ]]; then
  echo 'R90_P0A_DIAG_V1_SCRIPT_SHA_HOLD'
elif [[ -e "$OUT" || -L "$OUT" || -e "$LOG" || -L "$LOG" ]]; then
  echo 'R90_P0A_DIAG_V1_OUTPUT_OR_LOG_EXISTS_HOLD'
else
  (
    set -euo pipefail
    python3 "$F" selftest
    python3 "$F" audit
    echo 'R90_P0A_DIAG_V1_NATIVE_SEQUENCE_COMPLETE'
  ) 2>&1 | tee "$LOG"
  RC=${PIPESTATUS[0]}
  echo "R90_P0A_DIAG_V1_NATIVE_EXIT_CODE=$RC"
fi
printf '%s\n' TERMINAL_SAFE_END
