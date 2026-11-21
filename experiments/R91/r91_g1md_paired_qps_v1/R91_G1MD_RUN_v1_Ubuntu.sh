#!/usr/bin/env bash
set -euo pipefail
P="$HOME/Downloads/r91_g1md_paired_qps_10m_v1.py"
EXPECTED="f25edb81d6c8dfbbaf90872d5fd184501e31df39cdc546d06f334d8d375bf397"
if [ ! -f "$P" ] || [ -L "$P" ] || [ "$(sha256sum "$P" | awk '{print $1}')" != "$EXPECTED" ]; then
    echo R91_G1MD_SCRIPT_SHA_HOLD
    exit 2
fi
rc=0
(python3 "$P" run && python3 "$P" audit) || rc=$?
echo "R91_G1MD_RUN_NATIVE_EXIT_CODE=$rc"
echo TERMINAL_SAFE_END
exit "$rc"
