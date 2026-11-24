#!/usr/bin/env bash
set -Eeuo pipefail
HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
PY="$HERE/r91_g6_10m_repeat_build_p02_p06_v1.py"
echo '===== R91 G6 10M REPEATED BUILD P02-P06 PREFLIGHT NO BUILD ====='
python3 "$PY" selftest
python3 "$HERE/r91_g6_repeat_p02_p06_fixture_tests_v1.py"
systemd-run --user --scope --collect \
  -p MemoryMax=25769803776 -p MemorySwapMax=0 \
  -- python3 "$PY" scopecheck
systemd-run --user --scope --collect \
  -p MemoryMax=25769803776 -p MemorySwapMax=0 \
  -- python3 "$PY" preflight
echo 'R91_G6_REPEAT_P02_P06_V1_PREFLIGHT_CHAIN_PASS_NO_BUILD'
