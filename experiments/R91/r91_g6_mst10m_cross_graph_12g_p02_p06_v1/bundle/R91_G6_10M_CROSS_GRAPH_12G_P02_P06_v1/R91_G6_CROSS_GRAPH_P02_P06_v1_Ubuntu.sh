#!/usr/bin/env bash
set -Eeuo pipefail
trap 'rc=$?; echo "R91_G6_CROSS_GRAPH_P02_P06_EXIT_CODE=$rc"; echo TERMINAL_SAFE_END' EXIT
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
sha256sum -c R91_G6_CROSS_GRAPH_P02_P06_SHA256SUMS_v1.txt
PY=./r91_g6_10m_cross_graph_p02_p06_v1.py
R="$HOME/ann-task-a/experiments/R91/r91_g6_mst10m_cross_graph_12g_p02_p06_v1"
scope() { systemd-run --user --scope --collect -p MemoryMax=25769803776 -p MemorySwapMax=0 -- python3 -B "$PY" "$@"; }
hold() { echo "R91_G6_CROSS_GRAPH_P02_P06_HOLD: $*" >&2; exit 2; }
mode="${1:-}"
if [[ "$mode" == --preflight && $# == 1 ]]; then
    [[ ! -e "$R" && ! -L "$R" ]] || hold OUTPUT_EXISTS
    python3 -B "$PY" selftest
    python3 -B fixture_tests.py
    scope scopecheck
    scope preflight
    echo R91_G6_CROSS_GRAPH_P02_P06_PREFLIGHT_CHAIN_PASS_NO_SEARCH
    exit 0
fi
[[ $# == 2 && "$2" =~ ^[a-f0-9]{64}$ ]] || hold 'usage: --preflight OR --run-chain|--aggregate|--aggregate-readonly PREFLIGHT_SHA'
[[ -d "$R" && ! -L "$R" && -f "$R/preflight.json" && ! -L "$R/preflight.json" ]] || hold PREFLIGHT_MISSING
[[ "$(sha256sum "$R/preflight.json" | awk '{print $1}')" == "$2" ]] || hold PREFLIGHT_SHA
# Cooperative lock shared by all modes of this wrapper, including other copies of the bundle.
exec 9<"$R"
flock -n 9 || hold EXPERIMENT_ALREADY_LOCKED
if [[ "$mode" == --run-chain ]]; then
    [[ ! -e "$R/pairs" && ! -L "$R/pairs" && ! -e "$R/cross_graph_12g_summary.json" && ! -L "$R/cross_graph_12g_summary.json" ]] || hold EXISTING_RUNS_DO_NOT_RETRY
    for pair in p02 p03 p04 p05 p06; do
        case "$pair" in p02|p03|p06) arms=(C64 C512);; p04|p05) arms=(C512 C64);; esac
        echo "===== NATIVE SEARCH $pair ${arms[*]} ====="
        for arm in "${arms[@]}"; do scope run-arm --pair "$pair" --arm "$arm"; done
        scope audit --pair "$pair"
        scope readonly --pair "$pair"
        echo "R91_G6_CROSS_GRAPH_P02_P06_REAL_PAIR_AUDITED_PASS_$pair"
    done
    echo R91_G6_CROSS_GRAPH_P02_P06_TEN_GRAPHS_AUDITED_PASS_AGGREGATE_NOT_RUN
elif [[ "$mode" == --aggregate ]]; then
    [[ ! -e "$R/cross_graph_12g_summary.json" && ! -L "$R/cross_graph_12g_summary.json" ]] || hold AGGREGATE_EXISTS
    scope aggregate
elif [[ "$mode" == --aggregate-readonly ]]; then
    scope aggregate-readonly
else hold INVALID_MODE
fi
