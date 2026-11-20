#!/usr/bin/env bash
set -uo pipefail
PY="$HOME/Downloads/r90_p0a_v13_historical_highway_controlled_v1.py"
CPP="$HOME/Downloads/r90_p0a_v13_hwy_old_ftz_probe_v1.cpp"
WANTED_PY="52805e517a8534732f0cbb6aeac374afc71dcbb88afc53aae0d7a4d624d9e5dc"
WANTED_CPP="93275ee4d3d273caf2864b523986097b7631b5bdd1c9f710a1f3563ed17caebb"
LOG="$HOME/R90_P0A_V13_H85_HIGHWAY_STAGEB_STOCK_SIFT1M_QUALITY.log"
echo '===== R90 P0A V1.3 STAGE B: ONE PINNED STOCK SIFT1M BUILD + V0/DUPLICATE/RECALL QUALITY GATE ====='
if [[ ! -f "$PY" || -L "$PY" ]] || [[ "$(sha256sum "$PY" | awk '{print $1}')" != "$WANTED_PY" ]]; then
 echo 'R90_P0A_V13_STAGEB_HOLD_PY_SHA'; rc=2
elif [[ ! -f "$CPP" || -L "$CPP" ]] || [[ "$(sha256sum "$CPP" | awk '{print $1}')" != "$WANTED_CPP" ]]; then
 echo 'R90_P0A_V13_STAGEB_HOLD_CPP_SHA'; rc=2
elif [[ -e "$LOG" || -L "$LOG" ]]; then
 echo 'R90_P0A_V13_STAGEB_HOLD_EXISTING_LOG_PRESERVE'; rc=2
else
 (
  set -euo pipefail
  python3 "$PY" selftest
  python3 "$PY" preflightB
  python3 "$PY" stock1m
  echo 'R90_P0A_V13_STAGEB_ONE_STOCK_SIFT1M_SEQUENCE_COMPLETE__FULL_MATRIX_NOT_RUN'
 ) 2>&1 | tee "$LOG"
 rc=${PIPESTATUS[0]}
fi
echo "R90_P0A_V13_STAGEB_EXIT_CODE=$rc"
echo 'TERMINAL_SAFE_END'
exit "$rc"
