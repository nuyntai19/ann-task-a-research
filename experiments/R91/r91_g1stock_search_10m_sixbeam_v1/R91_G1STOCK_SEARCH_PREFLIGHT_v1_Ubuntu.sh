#!/usr/bin/env bash
set -euo pipefail
F="$HOME/Downloads/r91_g1stock_search_10m_sixbeam_v1.py"
EXPECTED="6fe8bdd5fb8ae59c6b48aeb429bf4dd2a2aae4086862460962f6f7248d9da717"
[[ -f "$F" && ! -L "$F" && "$(sha256sum "$F" | awk '{print $1}')" == "$EXPECTED" ]] || { echo R91_G1STOCK_SEARCH_PYTHON_SHA_HOLD; exit 2; }
python3 "$F" selftest
python3 "$F" preflight
echo R91_G1STOCK_SEARCH_PREFLIGHT_NATIVE_EXIT_CODE=0
echo TERMINAL_SAFE_END
