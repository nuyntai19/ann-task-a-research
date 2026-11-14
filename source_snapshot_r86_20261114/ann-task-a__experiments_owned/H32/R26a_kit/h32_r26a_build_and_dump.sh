#!/usr/bin/env bash
# H32-R26a SIFT1M: control/no-dump vs candidate-dump on one fixed seed.
# Runs TWO legitimate ANN GRAPH BUILDS; does not run ANN SEARCH, FGraft or PiPNN II.
# Run as: bash ~/Downloads/H32_R26a_sift1m_pool_gate_kit/h32_r26a_build_and_dump.sh
# An error exits this child bash only; it does not require `source` or `set -e` in terminal.
set -Eeuo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$HOME/ann-task-a"
BASE="$ROOT/experiments/H32/R22_source_gate"
DATA="$ROOT/data/sift1m.fbin"
BIN="$BASE/R23_build/algorithms/PipNN/neighbors-pipnn_FLOAT_T_EUCLIDEAN"
PY="$ROOT/experiments/H32/.venv-r25/bin/python"
V="$HERE/h32_r26a_validate.py"
EXPECTED_BIN="5bc2bb9fb1c41e8dcfc7f052b63afde8ff977fec8aa810e81a1cfe3e3e49a68c"
EXPECTED_HEAD="443a328dc71a3b7be753d52ca2b3c9a4ba77f3fd"
OUT="$ROOT/experiments/H32/H32_R26a_pool_$(date +%Y%m%d_%H%M%S)_$$"
mkdir -p "$OUT"
trap 'rc=$?; echo "R26A_STOP code=$rc; output=$OUT" >&2' ERR
printf 'R26A_OUTPUT=%s\n' "$OUT"
[[ -x "$BIN" && -x "$PY" && -s "$V" && -f "$DATA" ]]
[[ "$(sha256sum "$BIN" | cut -d' ' -f1)" == "$EXPECTED_BIN" ]]
[[ "$(git -C "$BASE/pipnn_r23_patched" rev-parse HEAD)" == "$EXPECTED_HEAD" ]]
"$PY" - "$DATA" <<'PY'
import os,struct,sys
p=sys.argv[1]
with open(p,'rb') as f: n,d=struct.unpack('<II',f.read(8))
assert (n,d)==(1_000_000,128),f'BAD_SIFT_HEADER={(n,d)}'
assert os.path.getsize(p)==512_000_008,'BAD_SIFT_BYTES'
assert hasattr(os,'sched_getaffinity') and {0,2,4,6}.issubset(os.sched_getaffinity(0)), 'CPU_0_2_4_6_AFFINITY_NOT_ALLOWED'
print('R26A_DATA_AND_CPUSET_PASS n=1000000 d=128; physical CPU IDs 0,2,4,6 allowed')
PY
"$PY" "$V" --mode selftest
if ! command -v taskset >/dev/null || [[ ! -x /usr/bin/time ]]; then
  echo 'R26A_STOP_MISSING_TASKSET_OR_TIME' >&2;exit 2
fi
# Keep all provenance and compiler/physical memory information; do not modify them.
{
 echo 'R26A_CONFIG: Original patched PiPNN; NOT PiPNN II and NOT H17.'
 echo 'R26A_BUILD_ARGS: -num_clusters 1 -fanout 30 -fanout_scheme 10,3 -cluster_size 1024 -mst_deg 2 -alpha 1.2 -prune_degree 32 -table_size 160 -hash_bits 12 -top_level_leaders 1000 -fraction_leaders 0.005 -prune 1 -prune_all 1 -k 10'
 echo 'R26A_THREADS=PARLAY_NUM_THREADS=4; taskset physical cpus=0,2,4,6'
 echo 'R26A_SEED=20261029; PIPNN_DETERMINISTIC=1; dump_C=160'
 echo "R26A_BINARY_SHA256=$EXPECTED_BIN"
 git -C "$BASE/pipnn_r23_patched" rev-parse HEAD
 git -C "$BASE/pipnn_r23_patched" status --short
 "$PY" -c 'import numpy; print("NUMPY_VERSION",numpy.__version__)'
 df -h "$ROOT"; free -h
 lscpu | grep -E 'Model name|CPU\(s\)|Core\(s\)|Thread\(s\)' || true
} > "$OUT/provenance.txt" 2>&1
sha256sum "$DATA" > "$OUT/base_data.sha256"
sha256sum "$BIN" > "$OUT/binary.sha256"
sha256sum "$V" "$HERE/h32_r26a_build_and_dump.sh" > "$OUT/kit_files.sha256"

a=(
 "$BIN" -base_path "$DATA"
 -num_clusters 1 -cluster_size 1024 -mst_deg 2
 -top_level_leaders 1000 -fraction_leaders 0.005
 -fanout 30 -fanout_scheme 10,3
 -prune 1 -prune_all 1 -prune_degree 32
 -table_size 160 -hash_bits 12 -alpha 1.2 -k 10
)
run_build() {
 local mode="$1" log="$OUT/$1.build.log" outgraph="$OUT/$1.graph" status=0
 echo "R26A_RUNNING_BUILD=$mode threads=4 seed=20261029"
 if [[ "$mode" == nodump ]]; then
    env -u PIPNN_DUMP -u PIPNN_DUMP_C PARLAY_NUM_THREADS=4 \
      PIPNN_SEED=20261029 PIPNN_DETERMINISTIC=1 \
      taskset -c 0,2,4,6 /usr/bin/time -v -o "$OUT/$mode.time.log" \
      "${a[@]}" -graph_outfile "$outgraph" > "$log" 2>&1 || status=$?
 else
    env PARLAY_NUM_THREADS=4 PIPNN_SEED=20261029 PIPNN_DETERMINISTIC=1 \
      PIPNN_DUMP="$OUT/dump.candidates.i32" PIPNN_DUMP_C=160 \
      taskset -c 0,2,4,6 /usr/bin/time -v -o "$OUT/$mode.time.log" \
      "${a[@]}" -graph_outfile "$outgraph" > "$log" 2>&1 || status=$?
 fi
 if ((status != 0));then
   echo "R26A_BUILD_FAIL=$mode code=$status (last 65 lines):" >&2
   tail -n 65 "$log" >&2
   return "$status"
 fi
 [[ -s "$outgraph" ]]
 if [[ "$mode" == dump ]];then [[ -s "$OUT/dump.candidates.i32" ]];fi
 echo "R26A_BUILD_COMPLETE=$mode graph_bytes=$(stat -c %s "$outgraph")"
}
run_build nodump
run_build dump
"$PY" "$V" --mode audit --out "$OUT" | tee "$OUT/audit_stdout.txt"
echo "R26A_DONE=$OUT"
cat "$OUT/r26a_summary.txt"
