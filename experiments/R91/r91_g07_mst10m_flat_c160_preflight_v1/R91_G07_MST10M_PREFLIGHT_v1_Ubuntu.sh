#!/usr/bin/env bash
set -uo pipefail
PY="$HOME/Downloads/r91_g07_g1_mst10m_hardcap_v1.py"
LOG="$HOME/R91_G07_MST10M_PREFLIGHT_v1.log"
EXPECTED="b216af7d3b49994f3ad9704d7354ebe3fac5dec57ec986c41deb02644d1957ed"
echo '===== R91 G0.7 PINNED H85 FASTV2 MST10M DATA/GT/CAP PREFLIGHT — NO BUILD ====='
if [[ ! -f "$PY" || -L "$PY" || "$(sha256sum "$PY" | awk '{print $1}')" != "$EXPECTED" ]]; then
 echo 'R91_G07_HOLD_SCRIPT_SHA_OR_MISSING'; rc=2
elif [[ -e "$LOG" || -L "$LOG" ]]; then
 echo 'R91_G07_HOLD_LOG_EXISTS_PRESERVE'; rc=2
elif ! command -v systemd-run >/dev/null || ! command -v python3 >/dev/null; then
 echo 'R91_G07_HOLD_REQUIRED_COMMAND_MISSING'; rc=2
else
 (
  set -euo pipefail
  python3 "$PY" selftest
  # This is a second, independent dry-run scope; it does NOT launch PiPNN.
  systemd-run --user --scope --expand-environment=no \
   -p MemoryAccounting=yes -p MemoryMax=24G -p MemorySwapMax=0 \
   "$(command -v python3)" "$PY" scope-check
  python3 "$PY" preflight
  echo 'R91_G07_ALL_NATIVE_SOURCE_DATA_GT_CGROUP_RESOURCE_PREFLIGHT_PASS__NO_BUILD'
 ) 2>&1 | tee "$LOG"
 rc=${PIPESTATUS[0]}
fi
echo "R91_G07_EXIT_CODE=$rc"
echo 'TERMINAL_SAFE_END'
exit "$rc"
