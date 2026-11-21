#!/usr/bin/env bash
set -uo pipefail
PY="$HOME/Downloads/r91_g06_twotier_readonly_v1.py"
LOG="$HOME/R91_G06_TWOTIER_READONLY_v1.log"
EXPECTED="9a2d57bacb6b65392e62c17cbcdff2d2de968694bed2752d24b0f5c8fe546421"
echo '===== R91 G0.6 HISTORICAL H85 TWO-TIER SOURCE+PREPRUNE DEGREES READONLY AUDIT ====='
if [[ ! -f "$PY" || -L "$PY" || "$(sha256sum "$PY" | awk '{print $1}')" != "$EXPECTED" ]]; then
 echo 'R91_G06_HOLD_SCRIPT_SHA_OR_MISSING'; rc=2
elif [[ -e "$LOG" || -L "$LOG" ]]; then
 echo 'R91_G06_HOLD_LOG_EXISTS_PRESERVE'; rc=2
else
 (
  set -euo pipefail
  python3 "$PY" selftest
  python3 "$PY" audit
  echo 'R91_G06_SOURCE_HISTOGRAM_AUDIT_SEQUENCE_COMPLETE__NO_10M_BUILD'
 ) 2>&1 | tee "$LOG"
 rc=${PIPESTATUS[0]}
fi
echo "R91_G06_EXIT_CODE=$rc"
echo 'TERMINAL_SAFE_END'
exit "$rc"
