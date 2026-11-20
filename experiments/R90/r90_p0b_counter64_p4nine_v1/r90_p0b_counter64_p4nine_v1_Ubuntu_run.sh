#!/usr/bin/env bash
# Diagnostic Counter64 only. No BUILD, no changes to 9 P4 frozen graphs.
set -o pipefail
F="$HOME/Downloads/r90_p0b_counter64_p4nine_v1.py"
SHA="cbe3aa223ca0e57e6cda2f04ddd2292dafb6af43dfbccd6848bd81cd27324f72"
OUT="$HOME/ann-task-a/experiments/R90/r90_p0b_counter64_p4nine_v1"
LOG="$HOME/R90_P0B_COUNTER64_9GRAPH_100KQ_v1.log"
echo '===== R90 P0B 9 GRAPH COUNTER64 SEARCH (NO BUILD) ====='
if [[ ! -f "$F" || -L "$F" || "$(sha256sum "$F" | awk '{print $1}')" != "$SHA" ]]; then
  echo R90_P0B_SCRIPT_SHA_HOLD
elif [[ -e "$OUT" || -L "$OUT" || -e "$LOG" || -L "$LOG" ]]; then
  echo R90_P0B_OUTPUT_OR_LOG_EXISTS_HOLD
else
 (
  set -euo pipefail
  python3 "$F" selftest
  python3 "$F" preflight
  python3 "$F" run
  python3 "$F" audit
  echo R90_P0B_NATIVE_SEQUENCE_COMPLETE
 ) 2>&1 | tee "$LOG"
 RC=${PIPESTATUS[0]}
 echo "R90_P0B_NATIVE_EXIT_CODE=$RC"
fi
echo TERMINAL_SAFE_END
