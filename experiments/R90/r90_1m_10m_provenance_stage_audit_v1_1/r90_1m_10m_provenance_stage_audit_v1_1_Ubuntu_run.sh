#!/usr/bin/env bash
# R90 v1.1: isolated, SHA-gated read-only P4 9-stdout stage + 10M GT provenance audit.
# No BUILD, no SEARCH, no source/data/graph modification; writes ONLY a fresh audit report.
set -uo pipefail
F="$HOME/Downloads/r90_1m_10m_provenance_stage_audit_v1_1.py"
SHA="0b7f835919f2825a9aee1250a174f92e53120db731a0d1d93afa0e5691ba320b"
OUT="$HOME/ann-task-a/experiments/R90/r90_1m_10m_provenance_stage_audit_v1_1"
LOG="$HOME/R90_1M_10M_PROVENANCE_STAGE_AUDIT_v1_1.log"
echo '===== R90 9-P4 SHA STAGES + 10M GT/PROVENANCE (READ ONLY, NO BUILD/SEARCH) ====='
if [ ! -f "$F" ] || [ -L "$F" ] || [ "$(sha256sum "$F" | awk '{print $1}')" != "$SHA" ]; then
  echo 'R90_V1_1_SCRIPT_SHA_HOLD'
elif [ -e "$OUT" ] || [ -L "$OUT" ] || [ -e "$LOG" ] || [ -L "$LOG" ]; then
  echo 'R90_V1_1_OUTPUT_EXISTS_HOLD'
else
  ( set -euo pipefail
    python3 "$F" selftest
    python3 "$F" audit --hash-files
    echo 'R90_V1_1_READONLY_SEQUENCE_COMPLETE'
  ) 2>&1 | tee "$LOG"
  RC=${PIPESTATUS[0]}
  echo "R90_V1_1_NATIVE_EXIT_CODE=$RC"
fi
echo 'TERMINAL_SAFE_END'
