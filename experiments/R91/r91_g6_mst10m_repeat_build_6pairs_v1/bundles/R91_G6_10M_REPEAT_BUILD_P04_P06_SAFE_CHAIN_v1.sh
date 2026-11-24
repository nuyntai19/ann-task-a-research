#!/usr/bin/env bash
set -Eeuo pipefail

# R91 G6 10M remaining fixed-SEED555 paired BUILDs.
# Explicit --check-only or --run. NO compile, NO Search, NO auto-retry.
# Existing output files/graphs are immutable. Each native BUILD is isolated
# in the original 24GiB-zero-swap systemd user scope. Each full pair audit
# is performed and read back before the next pair starts.
finish() {
    local rc=$?
    echo "R91_G6_P04_P06_CHAIN_EXIT_CODE=$rc"
    echo "TERMINAL_SAFE_END"
}
trap finish EXIT

if [[ $# -ne 1 || ( "$1" != "--check-only" && "$1" != "--run" ) ]]; then
    echo "USAGE: bash R91_G6_10M_REPEAT_BUILD_P04_P06_SAFE_CHAIN_v1.sh --check-only|--run" >&2
    exit 2
fi
MODE="$1"
D="$HOME/Downloads/R91_G6_10M_REPEAT_BUILD_P02_P06_V1_ISOLATED/R91_G6_10M_REPEAT_BUILD_P02_P06_v1"
R="$HOME/ann-task-a/experiments/R91/r91_g6_mst10m_repeat_build_6pairs_v1"

READ="$D/R91_G6_REPEAT_P02_P06_AUDIT_READONLY_v1_Ubuntu.sh"
RUN="$D/R91_G6_REPEAT_P02_P06_RUN_PAIR_v1_Ubuntu.sh"
AUD="$D/R91_G6_REPEAT_P02_P06_AUDIT_PAIR_v1_Ubuntu.sh"
PY="$D/r91_g6_10m_repeat_build_p02_p06_v1.py"
MANIFEST="$D/R91_G6_REPEAT_P02_P06_SHA256SUMS_v1.txt"
PRE="$R/extension_p02_p06_preflight_v1.json"
P03="$R/pairs/p03/pair_audit.json"

hold() { echo "R91_G6_P04_P06_HOLD: $*" >&2; exit 2; }
check_sha() {
    local p="$1" wanted="$2" label="$3" actual
    [[ -f "$p" && ! -L "$p" ]] || hold "${label}_NOT_REGULAR_OR_SYMLINK"
    actual="$(sha256sum -- "$p" | awk '{print $1}')" || hold "${label}_HASH_FAILED"
    [[ "$actual" == "$wanted" ]] || hold "${label}_SHA_MISMATCH"
}

[[ -d "$D" && ! -L "$D" && -d "$R" && ! -L "$R" ]] || hold "DIRECTORY_INVALID"
check_sha "$MANIFEST" '4a5e2604db1213140cd531b8e90f0cafcd4a21f4cc299490564db2fe4a495dd5' 'MANIFEST'
check_sha "$READ" '0dcb8cb5ed519ffd8c2cac938a9b84bfab490cf0b447c4606cc9c3bf9ccfbdee' 'READONLY_WRAPPER'
check_sha "$RUN" 'a7bb31a9b49de755592102dc07af4c1d5def377e1e65f6ec9ab780434913a01a' 'RUN_WRAPPER'
check_sha "$AUD" '61dac6bc8cb49ac13bd7654061704e2926d82a97892b5f39f003a12bbb86dc3d' 'AUDIT_WRAPPER'
check_sha "$PY" 'b3c1fbb8e22344ec296b672ca8e36a57fefc980be6356ae05dbdf66db1204d62' 'RUNNER'
check_sha "$PRE" '2d20ea7bb341067d162d7dbba1cf29fb8bc9606f4e7246e768a1c5629ea5ead2' 'EXTENSION_PREFLIGHT'
check_sha "$P03" 'fc0e7edf1edeae0e04d71406ee875c2b9a43357504641a0800adb0729beda88a' 'P03_AUDIT'

(
  cd -- "$D"
  sha256sum -c R91_G6_REPEAT_P02_P06_SHA256SUMS_v1.txt
) || hold 'BUNDLE_SHA_MANIFEST_FAILURE'

for pair in p04 p05 p06; do
    [[ ! -e "$R/pairs/$pair" && ! -L "$R/pairs/$pair" ]] || hold "${pair}_OUTPUT_ALREADY_EXISTS"
done
[[ ! -e "$R/repeat_6pair_summary.json" && ! -L "$R/repeat_6pair_summary.json" ]] || hold 'AGGREGATE_ALREADY_EXISTS'

echo 'R91_G6_P04_P06_CHAIN_STATIC_PREFLIGHT_PASS_NO_BUILD'
if [[ "$MODE" == '--check-only' ]]; then
    echo 'R91_G6_P04_P06_CHECK_ONLY_PASS_NO_BUILD'
    exit 0
fi

# Each loop iteration performs a FULL GRAPH READ-ONLY audit of the previous
# pair, then exactly two sequential BUILDs, an independent full pair audit,
# and a second full graph readback of the just-created pair. Any HOLD exits
# the entire process. There are no retries and no manual edits of receipts.
prev=p03
for pair in p04 p05 p06; do
    echo "===== R91 G6 10M $pair PREDECESSOR $prev FULL READONLY AUDIT ====="
    bash "$READ" "$prev"
    echo "===== R91 G6 10M $pair NATIVE TWO BUILD SLOTS ====="
    bash "$RUN" "$pair"
    echo "===== R91 G6 10M $pair NATIVE FULL PAIR AUDIT ====="
    bash "$AUD" "$pair"
    echo "===== R91 G6 10M $pair FULL READONLY AUDIT ====="
    bash "$READ" "$pair"
    echo "R91_G6_P04_P06_REAL_PAIR_AUDITED_PASS_${pair}"
    prev="$pair"
done

echo 'R91_G6_P04_P06_ALL_THREE_REAL_PAIRS_COMPLETED_AUDITED_PASS_AGGREGATE_NOT_RUN'
