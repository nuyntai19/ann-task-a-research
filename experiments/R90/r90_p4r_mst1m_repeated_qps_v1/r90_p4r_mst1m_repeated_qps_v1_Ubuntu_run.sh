#!/usr/bin/env bash
# R90-P4R v1: SHA-pinned, first-run only. Does not BUILD or modify frozen graphs.
set -o pipefail
F="$HOME/Downloads/r90_p4r_mst1m_repeated_qps_v1.py"
EXPECTED="581cb423039b44e414ffeee6240a93d27aa00b12a834ad7402f29727e1043b5c"
OUT="$HOME/ann-task-a/experiments/R90/r90_p4r_mst1m_repeated_qps_v1"
LOG="$HOME/R90_P4R_MST1M_REPEATED_QPS_v1.log"
echo "===== R90 P4R REPEATED NATIVE 100KQ, NO BUILD ====="
if [ ! -f "$F" ] || [ -L "$F" ] || \
   [ "$(sha256sum "$F" | awk '{print $1}')" != "$EXPECTED" ]; then
    echo "R90_P4R_SCRIPT_SHA_HOLD"
elif [ -e "$OUT" ] || [ -L "$OUT" ] || [ -e "$LOG" ] || [ -L "$LOG" ]; then
    echo "R90_P4R_PRIOR_OUTPUT_OR_LOG_EXISTS_HOLD"
    echo "Do not delete old files. For safe resume after interruption use Python phase 'run' with same SHA-pinned script."
else
    (
        set -euo pipefail
        python3 "$F" selftest
        python3 "$F" preflight
        python3 "$F" run
        python3 "$F" audit
        echo "R90_P4R_NATIVE_SEQUENCE_COMPLETE"
    ) 2>&1 | tee "$LOG"
    RC=${PIPESTATUS[0]}
    echo "R90_P4R_NATIVE_EXIT_CODE=$RC"
fi
echo "TERMINAL_SAFE_END"
