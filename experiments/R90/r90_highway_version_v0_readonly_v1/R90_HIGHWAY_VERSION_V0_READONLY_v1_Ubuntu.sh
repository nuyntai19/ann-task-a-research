#!/usr/bin/env bash
# R90: read-only root-cause evidence; does NOT run BUILD, Search, or modify source.
set -o pipefail
F="$HOME/Downloads/r90_highway_version_v0_readonly_v1.py"
EXPECTED="9471b11784a223dcfd273a4d2a4bfe7e9ce21982e02528f46b4cb6e9e9e87cb1"
OUT="$HOME/R90_HIGHWAY_VERSION_V0_READONLY_v1_report.json"
LOG="$HOME/R90_HIGHWAY_VERSION_V0_READONLY_v1.log"
echo '===== R90 HIGHWAY OLD/NEW SOURCE AND SIFT1M V0 READONLY AUDIT ====='
if [[ ! -f "$F" || -L "$F" || "$(sha256sum "$F" | awk '{print $1}')" != "$EXPECTED" ]]; then
  echo R90_HIGHWAY_V0_PY_SHA_HOLD
elif [[ -e "$OUT" || -L "$OUT" || -e "$LOG" || -L "$LOG" ]]; then
  echo R90_HIGHWAY_V0_OUTPUT_OR_LOG_EXISTS_HOLD
else
  (set -euo pipefail
    python3 "$F" --selftest
    python3 "$F" --audit
    echo R90_HIGHWAY_V0_READONLY_SEQUENCE_COMPLETE
  ) 2>&1 | tee "$LOG"
  RC=${PIPESTATUS[0]}
  echo "R90_HIGHWAY_V0_READONLY_EXIT_CODE=$RC"
fi
echo TERMINAL_SAFE_END
