#!/usr/bin/env bash
# H26-P4c: Linux perf PMU, P0 binary only, no source modifications.
set -Eeuo pipefail
ROOT="${H26P4C_ROOT:-$HOME/ann-task-a}"
P0="${H26P4C_P0_SOURCE:-$ROOT/experiments/H26/PiPNN-H26-src}"
BIN="$P0/build/algorithms/PipNN/neighbors-pipnn_FLOAT_T_EUCLIDEAN"
BASE="${SIFT_BASE:-$ROOT/data/sift1m.fbin}"
OUTROOT="${H26P4C_OUTROOT:-$ROOT/experiments/H26}"
MODE="${1:-run}"
case "$MODE" in probe|run) ;; *) echo 'Usage: bash h26_p4c_run.sh [probe|run]' >&2; exit 2;; esac
for command in perf taskset python3 sha256sum; do
  command -v "$command" >/dev/null || { echo "H26P4C_BLOCKED: missing command: $command" >&2; exit 2; }
done
[[ -x /usr/bin/time ]] || { echo 'H26P4C_BLOCKED: /usr/bin/time missing' >&2; exit 2; }
[[ -x "$BIN" && -s "$BASE" ]] || { echo 'H26P4C_BLOCKED: P0 binary or SIFT1M data missing' >&2;exit 2; }
# Probe expected affinity without assuming logical IDs are physically distinct.
taskset -c 0,2,4,6 /bin/true 2>/dev/null || { echo 'H26P4C_BLOCKED: CPU affinity 0,2,4,6 unavailable' >&2;exit 2; }
mkdir -p "$OUTROOT"
OUT="$(mktemp -d "$OUTROOT/H26_P4C_$(date +%Y%m%d_%H%M%S)_XXXXXX")"
{
  echo 'H26-P4c pinned P0 Top2 only; no graph output; no source patch; not a critical-path trace'
  date -Is
  echo "root=$ROOT"; echo "source=$P0"
  echo "git_commit=$(git -C "$P0" rev-parse HEAD)"
  sha256sum "$BIN" "$BASE"
  echo "perf_version=$(perf --version 2>&1 || true)"
  echo "perf_event_paranoid=$(cat /proc/sys/kernel/perf_event_paranoid 2>/dev/null || echo unknown)"
  uname -a
  lscpu -e=CPU,CORE,SOCKET,NODE,ONLINE 2>/dev/null || true
} > "$OUT/manifest.txt"
printf 'H26P4C_OUTPUT=%s\n' "$OUT"
# Probe event availability and privilege; fail closed instead of requesting sudo/sysctl.
if ! perf stat -x ';' --no-big-num -e task-clock,cycles,instructions -o "$OUT/probe_core.csv" -- /bin/sleep 0.10 > "$OUT/probe.log" 2>&1; then
  echo "H26P4C_BLOCKED: perf counters unavailable (permission/kernel/VM). See $OUT/probe.log" | tee "$OUT/probe_status.txt"
  cat "$OUT/probe.log"; exit 0
fi
if grep -Eqi 'not (supported|counted)|Permission denied|No permission' "$OUT/probe_core.csv"; then
  echo "H26P4C_BLOCKED: core PMU events not counted. See $OUT/probe_core.csv" | tee "$OUT/probe_status.txt"
  cat "$OUT/probe_core.csv"; exit 0
fi
EVENTS='task-clock,cycles,instructions'
# Cache events optional. If unsupported, still run core IPC analysis only.
if perf stat -x ';' --no-big-num -e task-clock,cycles,instructions,cache-references,cache-misses,branches,branch-misses -o "$OUT/probe_cache.csv" -- /bin/sleep 0.10 > "$OUT/probe_cache.log" 2>&1 && ! grep -Eqi 'not (supported|counted)|Permission denied|No permission' "$OUT/probe_cache.csv"; then
  EVENTS='task-clock,cycles,instructions,cache-references,cache-misses,branches,branch-misses'
fi
printf 'events=%s\n' "$EVENTS" | tee "$OUT/probe_status.txt"
if [[ "$MODE" == probe ]];then
  echo "H26P4C_PROBE_DONE=$OUT"; exit 0
fi
run() {
 local label="$1" threads="$2" cores="$3" instrument="$4"
 local log="$OUT/$label.log"
 local perf_csv="$OUT/$label.perf.csv"
 [[ ! -e "$log" && ! -e "$perf_csv" ]] || { echo "H26P4C_FAIL_CLOSED: output exists $label" >&2;exit 3; }
 echo "BEGIN H26P4C $label threads=$threads PMU=$instrument"
 local -a cmd=(env PARLAY_NUM_THREADS="$threads" H26_SELECTOR=top2 H26_CHECK_TOP2=0 taskset -c "$cores" /usr/bin/time -v "$BIN"
   -base_path "$BASE" -num_clusters 1 -fanout 30 -fanout_scheme 10,3
   -cluster_size 1024 -mst_deg 2 -alpha 1.2 -prune 1 -prune_all 1
   -prune_degree 32 -top_level_leaders 1000 -fraction_leaders 0.005 -hash_bits 12)
 if [[ "$instrument" == perf ]];then
  (cd "$P0"; perf stat -x ';' --no-big-num -e "$EVENTS" -o "$perf_csv" -- "${cmd[@]}") > "$log" 2>&1 || { echo "H26P4C_FAIL_CLOSED: $label failed" >&2;tail -n 55 "$log" >&2;exit 4; }
  grep -Eqi 'cycles|instructions' "$perf_csv" || { echo "H26P4C_FAIL_CLOSED: missing PMU $label" >&2;exit 4; }
 else
  (cd "$P0"; "${cmd[@]}") > "$log" 2>&1 || { echo "H26P4C_FAIL_CLOSED: $label failed" >&2;tail -n 55 "$log" >&2;exit 4; }
 fi
 grep -qx 'H26_PROFILE,leaf_count,85529' "$log" || { echo "H26P4C_FAIL_CLOSED: leaf count wrong $label" >&2;exit 4; }
 grep -qx 'H26_PROFILE,rows,29995085' "$log" || { echo "H26P4C_FAIL_CLOSED: row count wrong $label" >&2;exit 4; }
 grep -qx 'H26_PROFILE,proposals,59990170' "$log" || { echo "H26P4C_FAIL_CLOSED: proposals wrong $label" >&2;exit 4; }
 echo "DONE H26P4C $label"
}
# Two near-paired P0 controls for probe overhead, single 1T/2T PMU pilot.
run r1_4t_off  4 '0,2,4,6' off
run r1_4t_perf 4 '0,2,4,6' perf
run r1_2t_perf 2 '0,2' perf
run r1_1t_perf 1 '0' perf
run r2_4t_perf 4 '0,2,4,6' perf
run r2_4t_off  4 '0,2,4,6' off
python3 "$(dirname "${BASH_SOURCE[0]}")/h26_p4c_analyze.py" --dir "$OUT"
echo "H26P4C_DONE=$OUT"
