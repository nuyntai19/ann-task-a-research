#!/usr/bin/env bash
# Safe RESUME ONLY when all existing complete receipt SHA gates are valid.
set -uo pipefail
umask 077
F="$HOME/Downloads/r90_p0a_v13_h85_matched_threshold_repeated_qps_v1.py"
EXPECTED="aecf431e4768d868a74b7c0562de4d87cba4ef44c4619c8d88dec63e1414f959"
OUT="$HOME/ann-task-a/experiments/R90/r90_p0a_v13_h85_matched_threshold_repeat_1m_v1"
LOG="$HOME/R90_P0A_V13_H85_MATCHED_THRESHOLD_REPEAT_v1_RESUME.log"
echo '===== R90 P0A V13 H85 MATCHED QPS SAFE RESUME: NO BUILD, REHASH ALL COMPLETED RECEIPTS ====='
if [[ ! "$EXPECTED" =~ ^[a-f0-9]{64}$ ]] || [[ ! -f "$F" || -L "$F" ]] || [[ "$(sha256sum "$F" | awk '{print $1}')" != "$EXPECTED" ]]; then
 echo 'R90_P0A_V13_MATCHED_V1_RESUME_PYTHON_SHA_HOLD';echo TERMINAL_SAFE_END;exit 2
fi
if [[ ! -d "$OUT" || -L "$OUT" || ! -d "$OUT/logs" || ! -f "$OUT/preregister.json" || -e "$OUT/threshold_matched_qps_summary.json" || -e "$LOG" || -L "$LOG" ]]; then
 echo 'R90_P0A_V13_MATCHED_V1_RESUME_BAD_OR_COMPLETE_OUTPUT_STATE_HOLD';echo TERMINAL_SAFE_END;exit 2
fi
(
 set -euo pipefail
 python3 "$F" selftest
 python3 "$F" calibrate
 python3 "$F" auditcal
 python3 "$F" timing
 python3 "$F" audit
 echo 'R90_P0A_V13_MATCHED_V1_RESUME_SEQUENCE_COMPLETE_18_CALIB_54_TIMING_NO_BUILD'
) 2>&1 | tee "$LOG"
RC=${PIPESTATUS[0]}
echo "R90_P0A_V13_MATCHED_V1_RESUME_EXIT_CODE=$RC"
echo TERMINAL_SAFE_END
exit "$RC"
