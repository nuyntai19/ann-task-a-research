#!/usr/bin/env bash
set -euo pipefail
F="$HOME/Downloads/r91_g1bc_fast10m_highbeam_only_v1.py"
EXPECTED="cdf8d779b5bc1a631d23759c7ee8ad0ea8b55f779ef81b72e7cca45b2f5de2f5"
[[ -f "$F" && ! -L "$F" && "$(sha256sum "$F" | awk '{print $1}')" == "$EXPECTED" ]] || { echo R91_G1BC_PYTHON_SHA_HOLD; exit 2; }
python3 "$F" selftest
python3 "$F" preflight
echo R91_G1BC_PREFLIGHT_NATIVE_EXIT_CODE=0
echo TERMINAL_SAFE_END
