#!/usr/bin/env bash
set -Eeuo pipefail
HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
PY="$HERE/r91_g6_10m_repeat_build_p02_p06_v1.py"
echo '===== R91 G6 10M FIXED SEED SIX PAIRED BUILD FINAL AGGREGATE ====='
systemd-run --user --scope --collect \
  -p MemoryMax=25769803776 -p MemorySwapMax=0 \
  -- python3 "$PY" aggregate
echo 'R91_G6_REPEAT_P02_P06_V1_AGGREGATE_CHAIN_PASS_SIX_PAIRS'
