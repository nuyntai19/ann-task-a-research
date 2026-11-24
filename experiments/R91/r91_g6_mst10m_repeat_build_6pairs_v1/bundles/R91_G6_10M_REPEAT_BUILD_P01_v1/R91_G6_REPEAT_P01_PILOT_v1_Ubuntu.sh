#!/usr/bin/env bash
set -Eeuo pipefail
HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
PY="$HERE/r91_g6_10m_repeat_build_p01_v1.py"
echo '===== R91 G6 10M REPEATED BUILD P01 C512 THEN C64 ====='
for ARM in C512 C64; do
 echo "R91_G6_REPEAT_P01_BUILD_START_$ARM"
 systemd-run --user --scope --collect \
   -p MemoryMax=25769803776 -p MemorySwapMax=0 \
   -- python3 "$PY" pilot --arm "$ARM"
done
echo 'R91_G6_REPEAT_BUILD_P01_V1_TWO_BUILDS_DONE_AUDIT_REQUIRED'
