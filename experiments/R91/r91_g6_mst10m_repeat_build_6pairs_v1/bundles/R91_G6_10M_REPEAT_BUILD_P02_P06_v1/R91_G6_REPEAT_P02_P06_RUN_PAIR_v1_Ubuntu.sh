#!/usr/bin/env bash
set -Eeuo pipefail
if [[ $# -ne 1 || ! "$1" =~ ^p0[2-6]$ ]]; then
  echo 'USAGE: bash R91_G6_REPEAT_P02_P06_RUN_PAIR_v1_Ubuntu.sh p02|p03|p04|p05|p06' >&2
  exit 2
fi
PID="$1"
HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
PY="$HERE/r91_g6_10m_repeat_build_p02_p06_v1.py"
case "$PID" in
  p02|p03|p06) FIRST=C64; SECOND=C512;;
  p04|p05) FIRST=C512; SECOND=C64;;
  *) echo 'PAIR_INVALID_HOLD' >&2; exit 2;;
esac
echo "===== R91 G6 10M REPEAT BUILD $PID $FIRST THEN $SECOND ====="
for ARM in "$FIRST" "$SECOND"; do
  echo "R91_G6_REPEAT_P02_P06_NATIVE_START_${PID}_${ARM}"
  systemd-run --user --scope --collect \
    -p MemoryMax=25769803776 -p MemorySwapMax=0 \
    -- python3 "$PY" build-arm --pair "$PID" --arm "$ARM"
done
echo "R91_G6_REPEAT_P02_P06_V1_TWO_ARMS_DONE_FULL_AUDIT_REQUIRED_${PID}"
