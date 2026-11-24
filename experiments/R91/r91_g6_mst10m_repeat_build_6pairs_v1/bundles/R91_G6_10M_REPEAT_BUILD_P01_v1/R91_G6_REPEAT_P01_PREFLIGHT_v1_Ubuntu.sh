#!/usr/bin/env bash
set -Eeuo pipefail
HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
PY="$HERE/r91_g6_10m_repeat_build_p01_v1.py"
echo '===== R91 G6 10M REPEATED BUILD P01 PREFLIGHT NO BUILD ====='
python3 "$PY" selftest
systemd-run --user --scope --collect \
  -p MemoryMax=25769803776 -p MemorySwapMax=0 \
  -- python3 "$PY" scopecheck
python3 "$PY" preflight
echo 'R91_G6_REPEAT_BUILD_P01_V1_PREFLIGHT_CHAIN_PASS_NO_BUILD'
