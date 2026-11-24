#!/usr/bin/env bash
set -Eeuo pipefail
trap 'rc=$?; echo "R91_STOCK_FINAL_10M_EXIT_CODE=$rc"; echo TERMINAL_SAFE_END' EXIT
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
sha256sum -c SHA256SUMS.txt
R="$HOME/ann-task-a/experiments/R91/r91_stock_final_c64_10m_report_v1"
scope() { systemd-run --user --scope --collect -p MemoryMax=25769803776 -p MemorySwapMax=0 -- python3 -B stock_final.py "$@"; }
hold() { echo "R91_STOCK_FINAL_HOLD $*" >&2; exit 2; }
absent() { [[ ! -e "$1" && ! -L "$1" ]] || hold "OUTPUT_EXISTS $1"; }
if [[ ${1:-} == --preflight && $# == 1 ]]; then
    absent "$R"
    python3 -B stock_final.py selftest
    scope preflight
    exit 0
fi
[[ $# == 2 && $2 =~ ^[0-9a-f]{64}$ ]] || hold PRE_SHA_REQUIRED
[[ -d "$R" && ! -L "$R" && -f "$R/preflight.json" && ! -L "$R/preflight.json" ]] || hold PREFLIGHT_MISSING
[[ $(sha256sum "$R/preflight.json" | awk '{print $1}') == "$2" ]] || hold PREFLIGHT_SHA
exec 9<"$R"; flock -n 9 || hold LOCKED
case "$1" in
 --run) absent "$R/runs"; absent "$R/summary.json"; scope run --pre "$2" --arm STOCK; scope run --pre "$2" --arm FINAL_C64; scope audit --pre "$2"; scope readonly --pre "$2"; echo R91_STOCK_FINAL_10M_FULL_CHAIN_PASS;;
 --readonly) scope readonly --pre "$2";;
 *) hold INVALID_MODE;;
esac
