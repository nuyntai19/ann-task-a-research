#!/usr/bin/env bash
set -uo pipefail
PY="$HOME/Downloads/r91_g07_g1_mst10m_hardcap_v1.py"
PREF="$HOME/ann-task-a/experiments/R91/r91_g07_mst10m_flat_c160_preflight_v1/r91_g07_preflight.json"
OUT="$HOME/ann-task-a/experiments/R91/r91_g1_one_fastv2_flat_c160_mst10m_24g_v1"
LOG="$HOME/R91_G1_ONE_FASTV2_MST10M_24G_NOSWAP_v1.log"
WATCH="$HOME/R91_G1_OUTSIDE_CGROUP_MONITOR_v1.tsv"
EXPECTED="b216af7d3b49994f3ad9704d7354ebe3fac5dec57ec986c41deb02644d1957ed"
echo '===== R91 G1 ONE NATIVE FASTV2 FLAT C160 MST10M OFF BUILD: 24GiB HARD CAP / ZERO SWAP ====='
if [[ ! -f "$PY" || -L "$PY" || "$(sha256sum "$PY" | awk '{print $1}')" != "$EXPECTED" ]]; then
 echo 'R91_G1_HOLD_RUNNER_SHA_OR_MISSING'; rc=2
elif [[ ! -f "$PREF" || -L "$PREF" ]]; then
 echo 'R91_G1_HOLD_G07_PREFLIGHT_NOT_COMPLETE'; rc=2
elif [[ -e "$OUT" || -L "$OUT" || -e "$LOG" || -L "$LOG" || -e "$WATCH" || -L "$WATCH" ]]; then
 echo 'R91_G1_HOLD_PRIOR_OUTPUT_LOG_OR_MONITOR_PRESERVE'; rc=2
elif ! command -v systemd-run >/dev/null || ! command -v python3 >/dev/null; then
 echo 'R91_G1_HOLD_REQUIRED_COMMAND_MISSING'; rc=2
else
  # Monitoring here runs OUTSIDE the 24GiB scope and survives a whole-scope OOM.
  printf 'epoch	memory_current	memory_peak	swap_current	oom_kill	disk_free_bytes
' > "$WATCH"
  (
    set +e
    SCOPE_FILE="$OUT/cgroup_scope_path.txt"
    while :; do
      if [[ -f "$SCOPE_FILE" && ! -L "$SCOPE_FILE" ]]; then
        CG=$(head -n1 "$SCOPE_FILE")
        if [[ "$CG" == /sys/fs/cgroup/user.slice/* && -d "$CG" ]]; then
          C=$(cat "$CG/memory.current" 2>/dev/null || echo NA)
          P=$(cat "$CG/memory.peak" 2>/dev/null || echo NA)
          S=$(cat "$CG/memory.swap.current" 2>/dev/null || echo NA)
          O=$(awk '$1=="oom_kill" {print $2}' "$CG/memory.events" 2>/dev/null || echo NA)
          D=$(df -B1 --output=avail "$HOME/ann-task-a" 2>/dev/null | tail -n1 | tr -d ' ')
          printf '%s	%s	%s	%s	%s	%s
' "$(date +%s)" "$C" "$P" "$S" "$O" "$D" >> "$WATCH"
        fi
      fi
      sleep 1
    done
  ) &
  WATCHER_PID=$!
  systemd-run --user --scope --expand-environment=no \
   -p MemoryAccounting=yes -p MemoryMax=24G -p MemorySwapMax=0 \
   "$(command -v python3)" "$PY" build-inscope 2>&1 | tee "$LOG"
  rc=${PIPESTATUS[0]}
  kill "$WATCHER_PID" >/dev/null 2>&1 || :
  wait "$WATCHER_PID" 2>/dev/null || :
fi
echo "R91_G1_NATIVE_EXIT_CODE=$rc"
echo "R91_G1_OUTSIDE_MONITOR=$WATCH"
echo "R91_G1_RESULT_MANIFEST=$OUT/r91_g1_single10m_result.json"
echo 'TERMINAL_SAFE_END'
exit "$rc"
