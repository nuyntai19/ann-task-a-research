#!/usr/bin/env bash
set -Eeuo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
sha256sum -c R91_G6_CROSS_GRAPH_P01_SHA256SUMS_v1.txt
PY=./r91_g6_10m_cross_graph_p01_v1.py
for ARM in C512 C64; do
    systemd-run --user --scope --collect -p MemoryMax=25769803776 -p MemorySwapMax=0 -- python3 -B "$PY" run-arm --arm "$ARM"
done
echo R91_G6_CROSS_GRAPH_P01_V1_TWO_SLOTS_DONE_AUDIT_REQUIRED
