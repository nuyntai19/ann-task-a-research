#!/usr/bin/env bash
# R90 P0A V1.2 READ-ONLY evidence export. NO BUILD/SEARCH. No existing evidence overwritten.
set -u
set -o pipefail
F="$HOME/Downloads/r90_p0a_v12_evidence_export_readonly_v1.py"
EXPECTED="ece6e47a8e81d24b0c93eecb3d73044654608171743e5a494832573537594750"
LOG="$HOME/R90_P0A_V12_EVIDENCE_EXPORT_v1.log"
OUT="$HOME/R90_P0A_V12_NATIVE_EVIDENCE_EXPORT_v1.tar.gz"
printf '%s\n' '===== R90 P0A V1.2 READ-ONLY 24 GRAPH SHA REHASH + LOG COUNTER EVIDENCE EXPORT ====='
if [ ! -f "$F" ] || [ -L "$F" ] || [ "$(sha256sum "$F" | awk '{print $1}')" != "$EXPECTED" ]; then
  echo "R90_P0A_V12_EVIDENCE_SCRIPT_SHA_HOLD"
  RC=2
elif [ -e "$LOG" ] || [ -L "$LOG" ] || [ -e "$OUT" ] || [ -L "$OUT" ] || [ -e "$OUT.part" ] || [ -L "$OUT.part" ]; then
  echo "R90_P0A_V12_EVIDENCE_OUTPUT_OR_LOG_EXISTS_HOLD_NO_OVERWRITE"
  RC=2
else
  {
    python3 "$F" selftest &&
    python3 "$F" export
  } 2>&1 | tee "$LOG"
  RC=${PIPESTATUS[0]}
fi
printf 'R90_P0A_V12_EVIDENCE_EXPORT_NATIVE_EXIT_CODE=%d\n' "$RC"
printf '%s\n' 'TERMINAL_SAFE_END'
exit "$RC"
