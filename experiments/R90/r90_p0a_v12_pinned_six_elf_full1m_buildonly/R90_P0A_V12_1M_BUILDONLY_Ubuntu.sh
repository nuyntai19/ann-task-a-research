#!/usr/bin/env bash
# Strict first-run, new-output namespace, original six binaries reused only.
set -uo pipefail

PY="$HOME/Downloads/r90_p0a_v12_pinned_six_elf_full1m_buildonly.py"
EXPECTED="cd696087b03135699b4272357964f840f6148d9fe818b65c31a37064d122fabc"
OUT="$HOME/ann-task-a/experiments/R90/r90_p0a_v12_pinned_six_elf_full1m_buildonly"
LOG="$HOME/R90_P0A_V12_PINNED_SIX_ELF_BUILDONLY.log"

if [ ! -f "$PY" ] || [ -L "$PY" ] || \
   [ "$(sha256sum "$PY" 2>/dev/null | awk '{print $1}')" != "$EXPECTED" ]; then
  echo "R90_P0A_V12_SCRIPT_SHA_HOLD"
  echo "TERMINAL_SAFE_END"
  exit 2
fi
if [ -e "$OUT" ] || [ -L "$OUT" ] || [ -e "$LOG" ] || [ -L "$LOG" ]; then
  echo "R90_P0A_V12_OLD_OUTPUT_OR_LOG_EXISTS_HOLD_NO_OVERWRITE"
  echo "If interrupted, inspect original logs. Resume via the immutable python script's run and audit phases (see README)."
  echo "TERMINAL_SAFE_END"
  exit 2
fi

{
  echo '===== R90 P0A V1.2 SOURCE-PINNED SIX-ELF EXPLORATORY 1M BUILD-ONLY ====='
  echo 'Original P0A v1.1 source, binaries, graph and logs remain READ ONLY. No Search. No 10M.'
  python3 "$PY" selftest && \
  python3 "$PY" preflight && \
  python3 "$PY" prepare && \
  python3 "$PY" run && \
  python3 "$PY" audit
} 2>&1 | tee "$LOG"
RC=${PIPESTATUS[0]}
{
  echo "R90_P0A_V12_NATIVE_EXIT_CODE=$RC"
  echo 'TERMINAL_SAFE_END'
} | tee -a "$LOG"
exit "$RC"
