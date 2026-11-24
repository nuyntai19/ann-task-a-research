#!/usr/bin/env bash
set -Eeuo pipefail
trap 'rc=$?; echo "R91_G6_MATCHED_RECALL_12G_EXIT_CODE=$rc"; echo TERMINAL_SAFE_END' EXIT
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
sha256sum -c SHA256SUMS.txt
PY=./r91_g6_matched_recall_12g_v1.py
R="$HOME/ann-task-a/experiments/R91/r91_g6_mst10m_matched_recall_12g_v1"
scope() { systemd-run --user --scope --collect -p MemoryMax=25769803776 -p MemorySwapMax=0 -- python3 -B "$PY" "$@"; }
hold() { echo "R91_G6_MATCHED_RECALL_12G_HOLD: $*" >&2; exit 2; }
absent() { [[ ! -e "$1" && ! -L "$1" ]] || hold "OUTPUT_EXISTS $1"; }
check_sha() { [[ -f "$1" && ! -L "$1" && "$(sha256sum "$1" | awk '{print $1}')" == "$2" ]] || hold "SHA_MISMATCH $1"; }
mode="${1:-}"
if [[ "$mode" == --preflight && $# == 1 ]]; then
    absent "$R"
    python3 -B "$PY" selftest
    python3 -B fixture_tests.py
    scope scopecheck
    scope preflight
    echo R91_G6_MATCHED_RECALL_12G_PREFLIGHT_CHAIN_PASS_NO_SEARCH
    exit 0
fi
[[ $# -ge 2 && "$2" =~ ^[a-f0-9]{64}$ ]] || hold 'PREFLIGHT_SHA_REQUIRED'
[[ -d "$R" && ! -L "$R" ]] || hold OUTPUT_ROOT_MISSING
check_sha "$R/preflight.json" "$2"
exec 9<"$R"
flock -n 9 || hold EXPERIMENT_ALREADY_LOCKED
run_pair() {
    local pair="$1" arm
    local -a arms
    absent "$R/pairs/$pair"
    case "$pair" in p02|p03|p06) arms=(C64 C512);; p01|p04|p05) arms=(C512 C64);; *) hold INVALID_PAIR;; esac
    for arm in "${arms[@]}"; do scope run-arm --pair "$pair" --arm "$arm"; done
    scope audit --pair "$pair"
    scope readonly --pair "$pair"
    echo "R91_G6_MATCHED_RECALL_12G_REAL_PAIR_AUDITED_PASS_$pair"
}
case "$mode" in
    --pilot)
        [[ $# == 2 ]] || hold ARG_COUNT
        absent "$R/pairs"; absent "$R/matched_recall_12g_summary.json"
        run_pair p01
        echo R91_G6_MATCHED_RECALL_12G_PILOT_PASS_REMAINING_NOT_RUN
        ;;
    --run-chain)
        [[ $# == 3 && "$3" =~ ^[a-f0-9]{64}$ ]] || hold PILOT_SHA_REQUIRED
        check_sha "$R/pairs/p01/pair_search_summary.json" "$3"
        absent "$R/matched_recall_12g_summary.json"
        for pair in p02 p03 p04 p05 p06; do absent "$R/pairs/$pair"; done
        scope readonly --pair p01
        for pair in p02 p03 p04 p05 p06; do run_pair "$pair"; done
        echo R91_G6_MATCHED_RECALL_12G_ALL_PAIRS_AUDITED_AGGREGATE_NOT_RUN
        ;;
    --aggregate)
        [[ $# == 2 ]] || hold ARG_COUNT
        absent "$R/matched_recall_12g_summary.json"
        scope aggregate
        ;;
    --aggregate-readonly)
        [[ $# == 2 ]] || hold ARG_COUNT
        scope aggregate-readonly
        ;;
    *) hold INVALID_MODE;;
esac
