#!/usr/bin/env bash
# Only read historical SHA-verified logs and discover existing local 10M dataset files.
# NO BUILD; NO SEARCH; NO source/graph modification.
set -uo pipefail
F="$HOME/Downloads/r90_1m_evidence_10m_readonly_preflight_v1.py"
EXPECTED="ace19fa79729e4309531a44d96371c93b83feda8fe177fc8a47d411e2939208b"
OUT="$HOME/ann-task-a/experiments/R90/r90_1m_evidence_10m_readonly_preflight_v1"
LOG="$HOME/R90_1M_10M_READONLY_PREFLIGHT_v1.log"
echo '===== R90 1M LOG INVENTORY + MS-TURING 10M DATA DISCOVERY (NO BUILD) ====='
if [ ! -f "$F" ] || [ -L "$F" ] || [ "$(sha256sum "$F" | awk '{print $1}')" != "$EXPECTED" ]; then
    echo 'R90_INVENTORY_SCRIPT_SHA_HOLD'
elif [ -e "$OUT" ] || [ -L "$OUT" ] || [ -e "$LOG" ] || [ -L "$LOG" ]; then
    echo 'R90_INVENTORY_OUTPUT_EXISTS_HOLD'
else
    ( set -euo pipefail
      python3 "$F" selftest
      python3 "$F" preflight
      echo 'R90_1M_10M_READONLY_PREFLIGHT_SEQUENCE_COMPLETE'
    ) 2>&1 | tee "$LOG"
    RC=${PIPESTATUS[0]}
    echo "R90_INVENTORY_EXIT_CODE=$RC"
fi
echo 'TERMINAL_SAFE_END'
