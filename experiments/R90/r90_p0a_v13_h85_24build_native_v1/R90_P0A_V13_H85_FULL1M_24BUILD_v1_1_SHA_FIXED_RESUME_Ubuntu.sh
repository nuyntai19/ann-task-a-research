#!/usr/bin/env bash
set -uo pipefail
PY="$HOME/Downloads/r90_p0a_v13_h85_24build_native_v1_1_SHA_FIXED.py"
STAGEAB="$HOME/Downloads/r90_p0a_v13_historical_highway_controlled_v1.py"
EXPECTED_PY="68bab029e4bd65a7179372ee67389c1272a5ce3bb6030b3f9be83318945fb140"
EXPECTED_STAGEAB="52805e517a8534732f0cbb6aeac374afc71dcbb88afc53aae0d7a4d624d9e5dc"
ROOT="$HOME/ann-task-a/experiments/R90/r90_p0a_v13_h85_24build_native_v1"
LOG="$HOME/R90_P0A_V13_H85_FULL1M_24BUILD_v1_1_SHA_FIXED_RESUME.log"
echo '===== R90 P0A V1.3 H85: FIX11 RESUME ONLY VERIFIED COMPLETE RECEIPTS ====='
if [[ ! -f "$PY" || -L "$PY" || "$(sha256sum "$PY" | awk '{print $1}')" != "$EXPECTED_PY" ]]; then
 echo 'R90_V13_FIX11_RESUME_HOLD_RUNNER_SHA'; rc=2
elif [[ ! -f "$STAGEAB" || -L "$STAGEAB" || "$(sha256sum "$STAGEAB" | awk '{print $1}')" != "$EXPECTED_STAGEAB" ]]; then
 echo 'R90_V13_FIX11_RESUME_HOLD_ORIGINAL_STAGEAB_SHA'; rc=2
elif [[ ! -f "$ROOT/preregister.json" || -L "$ROOT/preregister.json" ]]; then
 echo 'R90_V13_FIX11_RESUME_HOLD_NO_PREREGISTER'; rc=2
elif [[ -e "$LOG" || -L "$LOG" ]]; then
 echo 'R90_V13_FIX11_RESUME_HOLD_EXISTING_LOG_PRESERVE'; rc=2
else
 (
  set -euo pipefail
  python3 "$PY" selftest
  if [[ ! -f "$ROOT/full1m_manifest.json" ]]; then python3 "$PY" run; fi
  python3 "$PY" audit
  echo 'R90_P0A_V13_H85_24BUILD_FIX11_RESUME_COMPLETE__SEARCH_PENDING'
 ) 2>&1 | tee "$LOG"
 rc=${PIPESTATUS[0]}
fi
echo "R90_P0A_V13_H85_24BUILD_FIX11_RESUME_EXIT_CODE=$rc"
echo 'TERMINAL_SAFE_END'
exit "$rc"
