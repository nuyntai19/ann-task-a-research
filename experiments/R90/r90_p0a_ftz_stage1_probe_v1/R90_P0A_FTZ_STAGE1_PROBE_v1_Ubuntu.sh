#!/usr/bin/env bash
# R90-P0A FTZ/DAZ vs original Highway archive + repeated SIFT10K Stage1 diagnostic.
# Does NOT edit original six ELF, original graphs/logs, or any 1M/10M dataset.
set -uo pipefail
P="$HOME/Downloads/r90_p0a_ftz_stage1_probe_v1.py"
CPP="$HOME/Downloads/r90_p0a_ftz_highway_native_probe_v1.cpp"
OLD="$HOME/Downloads/r90_p0a_unified_1m_three_arm_v1_1.py"
ROOT="$HOME/ann-task-a/experiments/R90"
O="$ROOT/r90_p0a_unified_1m_three_arm_v1_1"
D="$ROOT/r90_p0a_v11_pilot_hold_diagnostic_v1/diagnostic_report.json"
OUT="$ROOT/r90_p0a_ftz_stage1_probe_v1"
LOG="$HOME/R90_P0A_FTZ_STAGE1_NATIVE_PROBE_v1.log"

echo '===== R90 P0A CONTROLLED ORIGINAL HIGHWAY FTZ/DAZ + SIFT10K STAGE1 THREE REPS (NO 1M) ====='
verify() {
  local path="$1" expected="$2"
  [[ -f "$path" && ! -L "$path" ]] || return 1
  [[ "$(sha256sum "$path" | awk '{print $1}')" == "$expected" ]]
}
if ! verify "$P" '369340042caba43efd3c8a98be4af4c9bcde84e5977573ed98ff235d379ebd60'; then
  echo 'R90_P0A_FTZ_STAGE1_PYTHON_SHA_HOLD';RC=2
elif ! verify "$CPP" '93275ee4d3d273caf2864b523986097b7631b5bdd1c9f710a1f3563ed17caebb'; then
  echo 'R90_P0A_FTZ_STAGE1_CPP_SHA_HOLD';RC=2
elif ! verify "$OLD" 'fa9cdc09b3f447161f5c1f65382b15a0bc9645f425a679b73ca26f5ce8abecf0'; then
  echo 'R90_P0A_FTZ_STAGE1_ORIGINAL_RUNNER_SHA_HOLD';RC=2
elif ! verify "$O/source_manifest.json" '6e5d82c4ca331476240950afedfad970d8358fc7252d0d2b8b9ac441e1afb298'; then
  echo 'R90_P0A_FTZ_STAGE1_SOURCE_MANIFEST_SHA_HOLD';RC=2
elif ! verify "$O/pilot_manifest.json" 'b45ab2841b6f8ade980735d9b5414b921366eeab65d48dd52e770b8aef5947c9'; then
  echo 'R90_P0A_FTZ_STAGE1_PILOT_MANIFEST_SHA_HOLD';RC=2
elif ! verify "$D" 'cffe7fb508b3d5550e9ea7a41a11fa41f101b23a0034cd6b4c051a15fec9e519'; then
  echo 'R90_P0A_FTZ_STAGE1_PREVIOUS_DIAGNOSTIC_SHA_HOLD';RC=2
elif [[ -e "$LOG" || -L "$LOG" || -e "$OUT" || -L "$OUT" ]]; then
  echo 'R90_P0A_FTZ_STAGE1_EXISTING_NEW_OUTPUT_OR_LOG_HOLD__PRESERVE';RC=2
else
  (
    set -euo pipefail
    python3 "$P" selftest
    python3 "$P" preflight
    python3 "$P" run
    python3 "$P" audit
    echo 'R90_P0A_FTZ_STAGE1_ONE_BUNDLE_SEQUENCE_COMPLETE'
  ) 2>&1 | tee "$LOG"
  RC=${PIPESTATUS[0]}
fi
printf 'R90_P0A_FTZ_STAGE1_NATIVE_EXIT_CODE=%s\n' "$RC"
printf '%s\n' 'TERMINAL_SAFE_END'
exit "$RC"
