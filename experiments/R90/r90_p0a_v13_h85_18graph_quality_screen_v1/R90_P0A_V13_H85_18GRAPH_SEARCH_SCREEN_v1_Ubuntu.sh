#!/usr/bin/env bash
set -uo pipefail
umask 077
F="$HOME/Downloads/r90_p0a_v13_h85_18graph_search_screen_v1.py"
EXPECTED="dcfe8d6f856b37ca149ee4a00b257f2af11d7ef757a24d99859634633c2191a6"
OUT="$HOME/ann-task-a/experiments/R90/r90_p0a_v13_h85_18graph_quality_screen_v1"
LOG="$HOME/R90_P0A_V13_H85_18GRAPH_SEARCH_SCREEN_v1.log"
echo '===== R90 P0A V13 H85 OLD HIGHWAY FIXED BEAM SEARCH: 18 ORIGINAL 4CPU OFF GRAPHS, NO BUILD ====='
if [[ ! "$EXPECTED" =~ ^[a-f0-9]{64}$ ]] || [[ ! -f "$F" || -L "$F" ]] || [[ "$(sha256sum "$F" | awk '{print $1}')" != "$EXPECTED" ]]; then
 echo 'R90_P0A_V13_H85_SEARCH_SCREEN_V1_PYTHON_SHA_HOLD';echo TERMINAL_SAFE_END;exit 2
fi
if [[ -e "$OUT" || -L "$OUT" || -e "$LOG" || -L "$LOG" ]]; then
 echo 'R90_P0A_V13_H85_SEARCH_SCREEN_V1_EXISTING_OUTPUT_OR_LOG_HOLD';echo 'Preserve original data; use RESUME script only for complete verified receipts.';echo TERMINAL_SAFE_END;exit 2
fi
(
 set -euo pipefail
 python3 "$F" selftest
 python3 "$F" preflight
 python3 "$F" run
 python3 "$F" audit
 echo 'R90_P0A_V13_H85_SEARCH_SCREEN_V1_SEQUENCE_COMPLETE_18_ORIGINAL_OFF_GRAPHS_NO_BUILD'
) 2>&1 | tee "$LOG"
RC=${PIPESTATUS[0]}
echo "R90_P0A_V13_H85_SEARCH_SCREEN_V1_NATIVE_EXIT_CODE=$RC"
echo TERMINAL_SAFE_END
exit "$RC"
