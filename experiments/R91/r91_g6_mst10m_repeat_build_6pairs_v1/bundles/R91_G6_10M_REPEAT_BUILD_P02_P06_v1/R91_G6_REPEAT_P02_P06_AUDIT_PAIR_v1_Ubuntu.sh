#!/usr/bin/env bash
set -Eeuo pipefail
if [[ $# -ne 1 || ! "$1" =~ ^p0[2-6]$ ]]; then
  echo 'USAGE: bash R91_G6_REPEAT_P02_P06_AUDIT_PAIR_v1_Ubuntu.sh p02|p03|p04|p05|p06' >&2
  exit 2
fi
HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
PY="$HERE/r91_g6_10m_repeat_build_p02_p06_v1.py"
PID="$1"
echo "===== R91 G6 10M REPEAT BUILD $PID FULL PAIR AUDIT ====="
systemd-run --user --scope --collect \
  -p MemoryMax=25769803776 -p MemorySwapMax=0 \
  -- python3 "$PY" audit-pair --pair "$PID"
echo "R91_G6_REPEAT_P02_P06_V1_FULL_PAIR_AUDIT_CHAIN_PASS_${PID}"
