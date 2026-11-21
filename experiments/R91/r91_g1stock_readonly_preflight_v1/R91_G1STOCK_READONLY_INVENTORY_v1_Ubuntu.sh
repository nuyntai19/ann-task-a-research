#!/usr/bin/env bash
set -euo pipefail
F="$HOME/Downloads/r91_g1stock_readonly_inventory_v1.py"
EXPECTED="d27275f079c79ccb2f2a5ee879eb7f1a5c6184853b737a072ba8a2894c17df81"
echo "===== R91 STOCK10M READONLY SOURCE+RESOURCE INVENTORY — ABSOLUTELY NO ANN BUILD ====="
if [[ ! -f "$F" || -L "$F" ]]; then
  echo "R91_G1STOCK_SCRIPT_MISSING_OR_SYMLINK_HOLD"
  exit 2
fi
ACTUAL=$(sha256sum "$F" | awk '{print $1}')
if [[ "$ACTUAL" != "$EXPECTED" ]]; then
  echo "R91_G1STOCK_SCRIPT_SHA_HOLD expected=$EXPECTED actual=$ACTUAL"
  exit 2
fi
python3 "$F" --selftest
python3 "$F"
echo "R91_G1STOCK_READONLY_INVENTORY_V1_SEQUENCE_COMPLETE_NO_BUILD"
echo "TERMINAL_SAFE_END"
