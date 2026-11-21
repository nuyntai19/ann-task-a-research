#!/usr/bin/env bash
set -euo pipefail
P="$HOME/Downloads/r91_g1ma_10m_calibration_v1.py"
EXPECTED="2f64af73c6969ae9c7233fa57b586a0238fb004cea1d22a7d0727060d4c4d59e"
if [ ! -f "$P" ] || [ -L "$P" ] || [ "$(sha256sum "$P" | awk '{print $1}')" != "$EXPECTED" ]; then
  echo R91_G1MA_SCRIPT_SHA_HOLD
  exit 2
fi
rc=0
(python3 "$P" run && python3 "$P" audit) || rc=$?
echo "R91_G1MA_RUN_AUDIT_NATIVE_EXIT_CODE=$rc"
echo TERMINAL_SAFE_END
exit "$rc"
