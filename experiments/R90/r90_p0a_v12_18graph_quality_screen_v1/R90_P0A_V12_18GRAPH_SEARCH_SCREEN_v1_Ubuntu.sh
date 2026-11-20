#!/usr/bin/env bash
set -uo pipefail
F="$HOME/Downloads/r90_p0a_v12_18graph_native_quality_screen_v1.py"
EXPECTED="23505630f0a3e9d38cf1f8d6ab98bf64fc140bad294cc7a6855583a82120680a"
OUT="$HOME/ann-task-a/experiments/R90/r90_p0a_v12_18graph_quality_screen_v1"
LOG="$HOME/R90_P0A_V12_18GRAPH_SEARCH_SCREEN_v1.log"
echo '===== R90 P0A V1.2 SEARCH ONLY: 18 ORIGINAL OFF 1M GRAPHS (NO BUILD) ====='
if [[ ! -f "$F" || -L "$F" || "$(sha256sum "$F" | awk '{print $1}')" != "$EXPECTED" ]]; then
  echo 'R90_P0A_V12_SEARCH_SCRIPT_SHA_HOLD'
  echo 'TERMINAL_SAFE_END'
  exit 2
fi
if [[ -e "$OUT" || -L "$OUT" || -e "$LOG" || -L "$LOG" ]]; then
  echo 'R90_P0A_V12_SEARCH_OUTPUT_OR_LOG_EXISTS_HOLD'
  echo 'No files deleted or overwritten. For a partial run, use the runner resume protocol after audit.'
  echo 'TERMINAL_SAFE_END'
  exit 2
fi
(
  python3 "$F" selftest &&
  python3 "$F" run &&
  python3 "$F" audit
) 2>&1 | tee "$LOG"
RC=${PIPESTATUS[0]}
echo "R90_P0A_V12_SEARCH_NATIVE_EXIT_CODE=$RC"
echo 'TERMINAL_SAFE_END'
exit "$RC"
