#!/usr/bin/env bash
set -uo pipefail
PY="$HOME/Downloads/r90_p0a_v13_h85_24build_native_v1.py"
EXPECTED="60b3497a301022fc599e83411ce246d8f70099b878eaab5620c9c73a7ead21b2"
ROOT="$HOME/ann-task-a/experiments/R90/r90_p0a_v13_h85_24build_native_v1"
LOG="$HOME/R90_P0A_V13_H85_FULL1M_24BUILD_v1_RESUME.log"
echo '===== V1.3 H85 24 1M BUILDS: RESUME ONLY COMPLETE SHA-VERIFIED RECORDS ====='
if [[ ! -f "$PY" || -L "$PY" ]] || [[ "$(sha256sum "$PY" | awk '{print $1}')" != "$EXPECTED" ]]; then
 echo 'R90_V13_RESUME_HOLD_RUNNER_SHA'; rc=2
elif [[ ! -f "$ROOT/preregister.json" || -L "$ROOT/preregister.json" ]]; then
 echo 'R90_V13_RESUME_HOLD_NO_PREREGISTER'; rc=2
elif [[ -e "$LOG" || -L "$LOG" ]]; then
 echo 'R90_V13_RESUME_HOLD_EXISTING_LOG'; rc=2
else
 (
  set -euo pipefail
  python3 "$PY" selftest
  if [[ ! -f "$ROOT/full1m_manifest.json" ]]; then
   python3 "$PY" run
  fi
  python3 "$PY" audit
  echo 'R90_P0A_V13_H85_FULL1M_RESUME_COMPLETE__SEARCH_QUALITY_PENDING'
 ) 2>&1 | tee "$LOG"
 rc=${PIPESTATUS[0]}
fi
echo "R90_P0A_V13_H85_24BUILD_RESUME_EXIT_CODE=$rc"
echo 'TERMINAL_SAFE_END'
exit "$rc"
