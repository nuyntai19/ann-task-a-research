#!/usr/bin/env bash
set -euo pipefail
P="$HOME/Downloads/r91_g1stock_mst10m_24g_v1.py"
EXPECTED="84d1d7b5409f215667dbd7b92176ff8c3383cf17a4742bdbb42efebe98b95b63"
L="$HOME/R91_G1STOCK_NATIVE_PREFLIGHT_v1.log"
if [[ ! -f "$P" || -L "$P" || $(sha256sum "$P" | awk '{print $1}') != "$EXPECTED" ]]; then echo 'R91_G1STOCK_SCRIPT_SHA_HOLD'; exit 2; fi
if [[ -e "$L" || -L "$L" ]]; then echo 'R91_G1STOCK_LOG_EXISTS_HOLD'; exit 2; fi
set +e
( python3 "$P" selftest && python3 "$P" preflight ) 2>&1 | tee "$L"
RC=${PIPESTATUS[0]}
echo 'R91_G1STOCK_PREFLIGHT_NATIVE_EXIT_CODE='"$RC"
echo 'TERMINAL_SAFE_END'
exit "$RC"
