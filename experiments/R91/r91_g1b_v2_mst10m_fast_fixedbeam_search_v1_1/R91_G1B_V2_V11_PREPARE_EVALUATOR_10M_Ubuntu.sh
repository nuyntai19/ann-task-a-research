#!/usr/bin/env bash
set -uo pipefail
TAG="R91_G1B_V2"
PY="$HOME/Downloads/r91_g1b_v2_mst10m_native_search_v1_1.py"
EXPECTED="3577ec1248696b4e1e7b427f0092b23ea2e01ecab80c39e1d0a1cc3cbd01f0c2"
EVAL="$HOME/ann-task-a/experiments/R91/r91_g1b_v2_native_eval_mst10m_exactguard_v1_1"
PREF="$HOME/ann-task-a/experiments/R91/r91_g1b_v2_mst10m_fast_preflight_v1_1"
OUT="$HOME/ann-task-a/experiments/R91/r91_g1b_v2_mst10m_fast_fixedbeam_search_v1_1"
LOG="$HOME/R91_G1B_V2_V11_PREPARE_EVALUATOR_10M.log"
echo "===== R91 G1B V2 PREPARE H85 ORIGINAL_R86_GUARD_10M, NO GRAPH BUILD ====="
if [[ "$HOME" != "/home/tai" ]]; then
 echo "R91_G1B_V2_HOLD_EXPECT_HOME_TAI"; rc=2
elif [[ ! -f "$PY" || -L "$PY" || "$(sha256sum "$PY" | awk '{print $1}')" != "$EXPECTED" ]]; then
 echo "R91_G1B_V2_HOLD_SCRIPT_SHA_OR_SYMLINK"; rc=2
elif ! command -v python3 >/dev/null || ! command -v sha256sum >/dev/null; then
 echo "R91_G1B_V2_HOLD_DEPENDENCY"; rc=2
elif [[ -e "$LOG" || -L "$LOG" || -e "$EVAL" || -L "$EVAL" || -e "$PREF" || -L "$PREF" || -e "$OUT" || -L "$OUT" ]]; then
 echo "R91_G1B_V2_HOLD_EXISTING_OUTPUT_OR_MISSING_INPUT_PRESERVE"; rc=2
elif ! command -v systemd-run >/dev/null; then
 echo "R91_G1B_V2_HOLD_SYSTEMD_RUN_MISSING"; rc=2
else
 (
  set -euo pipefail
  python3 "$PY" selftest
  python3 "$PY" prepare
  echo "R91_G1B_V2_PREPARE_NEW_10M_EVALUATOR_PASS_NO_GRAPH_BUILD_NO_SEARCH"
 ) 2>&1 | tee "$LOG"
 rc=${PIPESTATUS[0]}
fi
echo "R91_G1B_V2_PREPARE_NATIVE_EXIT_CODE=$rc"
echo "TERMINAL_SAFE_END"
exit "$rc"
