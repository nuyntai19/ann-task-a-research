#!/usr/bin/env bash
set -Eeuo pipefail
trap 'rc=$?; echo "R91_STOCK_FINAL_TOPOLOGY_EXIT_CODE=$rc"; echo TERMINAL_SAFE_END' EXIT
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
sha256sum -c SHA256SUMS.txt
R="$HOME/ann-task-a/experiments/R91/r91_stock_final_c64_10m_topology_v1"
scope() { systemd-run --user --scope --collect -p MemoryMax=25769803776 -p MemorySwapMax=0 -- python3 -B run_topology.py "$@"; }
absent() { [[ ! -e "$1" && ! -L "$1" ]] || { echo "OUTPUT_EXISTS_HOLD $1"; exit 2; }; }
if [[ $# == 1 && $1 == --preflight ]]; then absent "$R"; scope preflight; exit 0; fi
[[ $# == 2 && $2 =~ ^[0-9a-f]{64}$ && -d "$R" && ! -L "$R" && -f "$R/preflight.json" && ! -L "$R/preflight.json" ]] || exit 2
[[ $(sha256sum "$R/preflight.json" | awk '{print $1}') == "$2" ]] || exit 2
exec 9<"$R"; flock -n 9 || exit 2
case "$1" in
 --run) absent "$R/runs"; absent "$R/summary.json"; scope run --pre "$2" --arm STOCK; scope run --pre "$2" --arm FINAL_C64; scope audit --pre "$2"; scope readonly --pre "$2"; echo R91_STOCK_FINAL_TOPOLOGY_FULL_CHAIN_PASS;;
 --readonly) scope readonly --pre "$2";;
 *) exit 2;;
esac
