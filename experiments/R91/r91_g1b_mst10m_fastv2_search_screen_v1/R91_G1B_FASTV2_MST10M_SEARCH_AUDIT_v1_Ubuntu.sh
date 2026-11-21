#!/usr/bin/env bash
set -uo pipefail
PY="$HOME/Downloads/r91_g1b_mst10m_fastv2_search_screen_v1.py"
EXPECTED="3566fc7e04d0b8833c3fed07fdd0a2612ecc7612223b7e43781f594a5e9223b5"
echo '===== R91 G1B INDEPENDENT READ-ONLY GRAPH SEARCH RECEIPT AUDIT — NO BUILD / NO SEARCH ====='
if [[ ! -f "$PY" || -L "$PY" || "$(sha256sum "$PY" | awk '{print $1}')" != "$EXPECTED" ]]; then
 echo 'R91_G1B_AUDIT_HOLD_SCRIPT_SHA'; exit 2
fi
python3 "$PY" audit
RC=$?
echo "R91_G1B_AUDIT_EXIT_CODE=$RC"
echo 'TERMINAL_SAFE_END'
exit "$RC"
