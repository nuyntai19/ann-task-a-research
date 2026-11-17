#!/usr/bin/env bash
# Resume H25-R1 AFTER the first baseline native BUILD completed but the old
# common-search evaluator rejected SIFT1M ibin IDs+distances layout.
# Never repeats or overwrites baseline native BUILD/graph.
set -Eeuo pipefail
KIT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="${PIPNN_REPO:-$HOME/ann-task-a/src/PiPNN}"
PLAN="${H25_R1_PLAN:-$HOME/ann-task-a/experiments/H25/r1_graph_gate_sift1m_seed42}"
OUT="${H25_R1_RUN_OUT:-$HOME/ann-task-a/experiments/H25/r1_native_build_sift1m_seed42}"
BASE="${SIFT_BASE:-$HOME/ann-task-a/data/sift1m.fbin}"
QUERIES="${SIFT_QUERIES:-$HOME/ann-task-a/data/sift1m_queries.fbin}"
GT="${SIFT_GT:-$HOME/ann-task-a/data/sift1m_gt.ibin}"
CPUSET="${H25_CPUSET:-0,2,4,6}"
THREADS="${H25_THREADS:-4}"
NQ="${H25_NQ:-1000}"
REPEATS="${H25_SEARCH_REPEATS:-3}"
EFS="${H25_EFS:-100,120,140,160,180,200,240,300}"
BIN="$REPO/build/algorithms/PipNN/neighbors-pipnn_FLOAT_T_EUCLIDEAN"
SEARCH_BIN="$KIT/h25_r1_common_search"
fail(){ echo "H25_R1_RESUME_FAIL_CLOSED: $*" >&2;exit 2; }
[[ -d "$OUT" && -s "$OUT/baseline.graph" && -s "$OUT/baseline_build.log" && -s "$OUT/run_manifest.txt" ]] || fail 'Baseline native BUILD artifacts missing; cannot resume.'
[[ -x "$SEARCH_BIN" && -x "$BIN" ]] || fail 'One of the compiled binaries is absent. Recompile the fixed common search first.'
[[ -f "$PLAN/expected_rows.bin" && -f "$PLAN/patch_baseline.bin" && -f "$PLAN/patch_nearest.bin" && -f "$PLAN/patch_random.bin" ]] || fail 'Frozen H25-R1 plan missing.'
[[ -f "$BASE" && -f "$QUERIES" && -f "$GT" ]] || fail 'Dataset/GT files missing.'
[[ ! -e "$OUT/summary.json" && ! -e "$OUT/final_edge_presence.json" ]] || fail 'Summary already exists; refuse to overwrite.'
[[ ! -e "$OUT/baseline_eval.csv" && ! -e "$OUT/baseline_search_v4.log" ]] || fail 'Baseline evaluation/GT-fix log already exists; refuse to overwrite.'
for policy in nearest random; do
  for file in "$OUT/${policy}.graph" "$OUT/${policy}_build.log" "$OUT/${policy}_eval.csv" "$OUT/${policy}_search.log"; do
    [[ ! -e "$file" ]] || fail "Partial run already exists; inspect manually: $file"
  done
done
# Ensure same binary/configuration as the already-built baseline.
grep -Fx "Repo=$REPO" "$OUT/run_manifest.txt" >/dev/null || fail 'Repo changed since baseline BUILD.'
grep -Fx "Plan=$PLAN" "$OUT/run_manifest.txt" >/dev/null || fail 'Plan changed since baseline BUILD.'
grep -Fx "CPUSET=$CPUSET THREADS=$THREADS NQ=$NQ REPEATS=$REPEATS EFS=$EFS" "$OUT/run_manifest.txt" >/dev/null || fail 'Build/evaluation parameters changed since baseline BUILD.'
grep -Fx "ExecutableSHA256=$(sha256sum "$BIN")" "$OUT/run_manifest.txt" >/dev/null || fail 'PiPNN executable SHA changed; do not compare BUILD graphs.'
# Do NOT trust an existing baseline.graph if native capture controls did not pass.
grep -Fq 'H25_R1_VERIFY_PASS' "$OUT/baseline_build.log" || fail 'Baseline graph did not pass native leaf-control verification.'
checked="$(python3 - "$PLAN/expected_rows.bin" <<'PY'
import struct,sys
with open(sys.argv[1],'rb') as f: mg,count,n,leaves=struct.unpack('<8sQQQ',f.read(32))
assert mg==b'H25R1C01' and n==1_000_000 and leaves==85529 and count==20784,(mg,count,n,leaves)
print(count)
PY
)"
grep -Fq "H25_R1_VERIFY: checked_rows=$checked/$checked applied_patches=0/0" "$OUT/baseline_build.log" || fail 'Baseline native verification counters do not match plan.'
# Hard-check expected file headers so an invalid GT does not start another BUILD.
python3 - "$GT" "$BASE" "$QUERIES" <<'PY'
import sys,struct,os
for p in sys.argv[1:]:
 with open(p,'rb') as f: h=f.read(8)
 if len(h)!=8:raise SystemExit('Short header: '+p)
 n,k=struct.unpack('<II',h);size=os.stat(p).st_size
 if p.endswith('.ibin'):
  assert n==10000 and k>=10 and size in (8+4*n*k,8+8*n*k),(p,n,k,size)
  print('GT_PREFLIGHT_PASS n=',n,'k=',k,'bytes=',size,'layout=', 'ids+dist' if size==8+8*n*k else 'ids-only')
 else:
  assert size==8+4*n*k,(p,n,k,size)
  print('FBIN_PREFLIGHT_PASS n=',n,'d=',k,'file=',p)
PY
printf 'GT-FIX R1 RESUME: verified baseline graph retained (no rebuild).\n' | tee "$OUT/gt_fix_resume_manifest.txt"
sha256sum "$SEARCH_BIN" | tee -a "$OUT/gt_fix_resume_manifest.txt"
# Search baseline with the corrected evaluator.
taskset -c "$CPUSET" "$SEARCH_BIN" \
  --graph "$OUT/baseline.graph" --base "$BASE" --queries "$QUERIES" --gt "$GT" \
  --efs "$EFS" --nq "$NQ" --repeats "$REPEATS" --csv "$OUT/baseline_eval.csv" \
  >"$OUT/baseline_search_v4.log" 2>&1 || { tail -70 "$OUT/baseline_search_v4.log";fail 'Fixed baseline SEARCH failed; no more BUILDs executed.'; }
grep -q 'H25_R1_SEARCH_DONE' "$OUT/baseline_search_v4.log" || fail 'Baseline SEARCH did not complete.'
sha256sum "$OUT/baseline.graph" >> "$OUT/graph_sha256.txt"
for policy in nearest random; do
  graph="$OUT/${policy}.graph"; log="$OUT/${policy}_build.log";csv="$OUT/${policy}_eval.csv"
  echo "=== NATIVE BUILD: $policy ==="
  export H25_R1_ROWS="$PLAN/expected_rows.bin"
  export H25_R1_PATCH="$PLAN/patch_${policy}.bin"
  (
    cd "$REPO"
    env PARLAY_NUM_THREADS="$THREADS" H25_R1_ROWS="$H25_R1_ROWS" H25_R1_PATCH="$H25_R1_PATCH" \
      taskset -c "$CPUSET" /usr/bin/time -v "$BIN" \
      -base_path "$BASE" \
      -num_clusters 1 -fanout 30 -fanout_scheme 10,3 -cluster_size 1024 \
      -mst_deg 2 -alpha 1.2 -prune 1 -prune_all 1 -prune_degree 32 \
      -top_level_leaders 1000 -fraction_leaders 0.005 -hash_bits 12 \
      -graph_outfile "$graph"
  ) >"$log" 2>&1 || { echo "BUILD FAILED ($policy), log $log" >&2;tail -80 "$log";exit 3; }
  grep -Fq 'H25_R1_VERIFY_PASS' "$log" || { echo "MISSING H25 verifier PASS in $log" >&2;exit 3; }
  [[ -s "$graph" ]] || { echo "Graph missing/empty $graph" >&2;exit 3; }
  echo "=== COMMON EVALUATION: $policy ==="
  taskset -c "$CPUSET" "$SEARCH_BIN" \
    --graph "$graph" --base "$BASE" --queries "$QUERIES" --gt "$GT" \
    --efs "$EFS" --nq "$NQ" --repeats "$REPEATS" --csv "$csv" \
    >"$OUT/${policy}_search.log" 2>&1 || { echo "SEARCH FAILED ($policy)" >&2;tail -80 "$OUT/${policy}_search.log";exit 4; }
  sha256sum "$graph" >> "$OUT/graph_sha256.txt"
done
python3 "$KIT/h25_r1_summarize.py" --runs "$OUT" --out "$OUT/summary.json"
python3 "$KIT/h25_r1_edge_survival.py" --runs "$OUT" --plan "$PLAN" --out "$OUT/final_edge_presence.json"
echo "H25_R1_RESUME_DONE. Send: $OUT/summary.json and $OUT/final_edge_presence.json"
