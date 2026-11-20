#!/usr/bin/env bash
set -uo pipefail
PY="$HOME/Downloads/r90_p0a_v13_h85_24build_native_v1.py"
EXPECTED="60b3497a301022fc599e83411ce246d8f70099b878eaab5620c9c73a7ead21b2"
LOG="$HOME/R90_P0A_V13_H85_FULL1M_24BUILD_v1.log"
ZIP="$HOME/Downloads/R90_P0A_V13_H85_FULL1M_24BUILD_v1_BUNDLE.zip"
echo '===== R90 P0A V1.3 H85 6BC2 HISTORICAL HIGHWAY: 18 OFF + 6 ON FRESH 1M BUILD-ONLY ====='
if [[ ! -f "$PY" || -L "$PY" ]] || [[ "$(sha256sum "$PY" | awk '{print $1}')" != "$EXPECTED" ]]; then
 echo 'R90_V13_FULL1M_HOLD_RUNNER_SHA'; rc=2
elif [[ -e "$LOG" || -L "$LOG" ]]; then
 echo 'R90_V13_FULL1M_HOLD_EXISTING_LOG_DO_NOT_OVERWRITE'; rc=2
else
 (
  set -euo pipefail
  python3 "$PY" selftest
  python3 "$PY" preflight
  python3 "$PY" prepare
  python3 "$PY" run
  python3 "$PY" audit
  echo 'R90_P0A_V13_H85_FULL1M_24_BUILD_ONLY_SEQUENCE_COMPLETE__SEARCH_QUALITY_PENDING'
 ) 2>&1 | tee "$LOG"
 rc=${PIPESTATUS[0]}
fi
echo "R90_P0A_V13_H85_24BUILD_NATIVE_EXIT_CODE=$rc"
echo 'TERMINAL_SAFE_END'
exit "$rc"
