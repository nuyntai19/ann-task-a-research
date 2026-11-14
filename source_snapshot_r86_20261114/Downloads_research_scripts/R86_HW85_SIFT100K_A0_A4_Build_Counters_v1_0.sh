#!/usr/bin/env bash
# R86 HW85 SIFT100K A0-A4 controlled BUILD + work campaign.
# OFF: 3 independent graph BUILDs per arm for timing/RSS.
# ON: 1 independent graph BUILD per arm for work counters.
# Only build/operation diagnostics. SEARCH+GT, graph validity and matched Recall
# require separately pinned evaluator; this script DOES NOT claim final benchmark PASS.
# Source, old graphs, old binaries remain read-only. New session for every --run.
set -Eeuo pipefail
umask 077

MODE="${1:---preflight}"
case "$MODE" in --preflight|--run) ;; *) echo 'USAGE: bash SCRIPT [--preflight|--run]'; exit 2;; esac

ROOT="$HOME/ann-task-a/experiments/R86"
BUILD="$ROOT/gates/highway_r85_four_binary_jvYREW"
SRC="$ROOT/r86_v1_2_source"
SRC_SHA="$BUILD/source_sha256.txt"
MANIFEST="$BUILD/four_binary_manifest.json"
TARGET="algorithms/PipNN/neighbors-pipnn_FLOAT_T_EUCLIDEAN"
BASE="$HOME/ann-task-a/data/sift100k.fbin"
BASE_SHA="e50ff1bc34bcc6d1c97dd001023c09a666971cde64605cc06671ed8a8ff1ed12"
HW_COMMIT="6bc2d47793bae9c521fb4150936669647700765d"
CPUSET="${CPUSET:-0,2,4,6}"
THREADS=4

echo "=== R86 HW85 SIFT100K A0-A4 MODE=$MODE ==="
for c in python3 sha256sum taskset timeout env date stat awk grep mktemp df; do
  command -v "$c" >/dev/null || { echo "PREFLIGHT_MISSING_COMMAND=$c"; exit 3; }
done
[[ -x /usr/bin/time ]] || { echo 'PREFLIGHT_MISSING_TIME'; exit 3; }
[[ -s "$SRC_SHA" && -s "$MANIFEST" && -s "$BASE" ]] || { echo 'PREFLIGHT_MISSING_SOURCE_BINARY_MANIFEST_OR_DATA'; exit 3; }
ACTUAL="$(sha256sum "$BASE" | awk '{print $1}')"
[[ "$ACTUAL" == "$BASE_SHA" ]] || { echo "PREFLIGHT_DATA_SHA_MISMATCH=$ACTUAL"; exit 3; }
( cd / && sha256sum -c "$SRC_SHA" ) || { echo 'PREFLIGHT_PINNED_SOURCE_DRIFT'; exit 3; }

python3 - "$MANIFEST" "$BUILD" "$HW_COMMIT" "$CPUSET" <<'PY'
import hashlib,json,os,sys
from pathlib import Path
manifest,build,highway,cpuset=Path(sys.argv[1]),Path(sys.argv[2]).resolve(),sys.argv[3],sys.argv[4]
want={
 'stock_off':'aa2d174ed063070045f1fbbc8051b1d97b851168b2f3bf53ee32215a867583be',
 'stock_on':'396ef852992428cd3f935bcb33eeeeacc1bae565fbc4a441c1fa9d19720122ff',
 'h17_off':'5f673586210f93b424fc81791ec7873cb74600843b5004c0a4aaaf32bf936297',
 'h17_on':'ef707479be221cb7a3c6257298d22f614678878f0a7bfc724dc8b28fabdd21c4'}
m=json.loads(manifest.read_text()); assert m['highway_rev']==highway and m['control_decision']=='CONTROL_PASS_MATCH_STABLE', 'MANIFEST_PIN'
assert set(m['binaries'])==set(want)
for arm,sha in want.items():
 d=m['binaries'][arm]; p=Path(d['path']).resolve(strict=True)
 assert p==build/f'build_{arm}/algorithms/PipNN/neighbors-pipnn_FLOAT_T_EUCLIDEAN'
 assert hashlib.sha256(p.read_bytes()).hexdigest()==d['sha256']==sha
 assert bool(d['COUNTERS_ON'])==arm.endswith('_on')
 assert bool(d['H17'])==arm.startswith('h17')
 print('BINARY_SHA_PASS',arm,sha)
cs=[int(x) for x in cpuset.split(',')]
assert len(cs)==len(set(cs))==4 and all(x>=0 for x in cs), 'CPUSET_EXPECTS_FOUR_DISTINCT_CPU_IDS'
allowed=os.sched_getaffinity(0)
assert set(cs).issubset(allowed),f'CPUSET_NOT_ALLOWED allowed={sorted(allowed)}'
physical=[]
for cpu in cs:
 p=Path(f'/sys/devices/system/cpu/cpu{cpu}/topology')
 physical.append((int((p/'physical_package_id').read_text()),int((p/'core_id').read_text())))
assert len(set(physical))==4,f'CPUSET_SHARES_PHYSICAL_CORE cpus={cs} physical={physical}; choose four distinct physical cores'
print('CPUSET_DISTINCT_PHYSICAL_CORES_PASS',cpuset,physical)
PY

# 100K control A0 expects the EXACT pinned SIFT100K workload used to prove
# Highway compatibility earlier. Abort the rest if the protocol drifts.
echo "PREFLIGHT_PASS base_sha=$BASE_SHA cpu_list=$CPUSET parlay_threads=$THREADS"
echo 'NOTE=taskset bounds benchmark CPUs but does NOT block browser/OS tasks from these CPUs.'
echo 'NOTE=Search queries/ground truth/evaluator are not available in this collector and must be verified separately.'
if [[ "$MODE" == --preflight ]]; then
  echo 'PREFLIGHT_ONLY_NO_GRAPH_BUILD'
  exit 0
fi

OUTBASE="$ROOT/benchmarks"
mkdir -p "$OUTBASE"
OUT="$(mktemp -d "$OUTBASE/sift100k_a0a4_hw85_XXXXXX")"
echo "RESULT_DIR=$OUT"
sha256sum "${BASH_SOURCE[0]}" > "$OUT/script_sha256.txt"
cp "$MANIFEST" "$OUT/four_binary_manifest.json"
cp "$SRC_SHA" "$OUT/source_sha256.txt"
{
 echo 'BENCHMARK_SCOPE=100K_GRAPH_BUILD_AND_OPERATIONS_ONLY'
 echo 'BENCHMARK_STATUS=PROVISIONAL_G2_GRAPH_AUDIT_AND_SEARCH_GT_PENDING'
 echo 'BASE_DATASET=SIFT100K (NOT SIFT10K)'
 echo "BASE_SHA256=$BASE_SHA"
 echo "HIGHWAY_COMMIT=$HW_COMMIT"
 echo "THREADS=$THREADS CPUSET=$CPUSET"
 echo 'OFF=three independent builds per arm, counterbalanced blocks; ON=one counter build per arm'
 echo 'TOP_LEVEL_LEADERS=100 FANOUT=10,3,1 PRUNE=1 PRUNE_ALL=1 PRUNE_DEGREE=64 HASH_BITS=12 ALPHA=1.1 CLI_K=0'
 echo 'SEARCH_RECALL_NDC_LATENCY=NOT_MEASURED'
 echo "START_UTC=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
} > "$OUT/protocol.txt"

export OUT BUILD TARGET BASE CPUSET THREADS
python3 - "$OUT" <<'PY'
import csv,sys
from pathlib import Path
p=Path(sys.argv[1])/'runs.csv'
with p.open('w',newline='') as f:
 w=csv.writer(f);w.writerow(['run_id','arm','mode','C','K','N','threads','cpu_list','rep','wall_s','peak_rss_KiB','graph_bytes','graph_sha256','P1_buckets','P1_points','P1_WP_cumulative','P2_buckets','P2_points','P2_WP_cumulative','native_exit_status','log_path','counter_path','leaf_path','occupancy_path','status'])
PY

run_one() {
  local arm="$1" mode="$2" C="$3" K="$4" N="$5" rep="$6" bin graph log times work rc sha
  local runid="${arm}_C${C}_K${K}_N${N}_${mode}_r${rep}"; work="$OUT/$runid"; mkdir "$work"
  bin="$BUILD/build_${arm}_${mode}/$TARGET"
  graph="$work/$runid.graph";log="$work/$runid.build.log";times="$work/$runid.time.txt"
  local -a counter_env=() unset_env=( -u R86_COUNTER_OUT -u R86_LEAF_SIZE_OUT -u R86_OCCUPANCY_OUT )
  if [[ "$mode" == on ]]; then
    counter_env=( "R86_COUNTER_OUT=$work/$runid.counters.jsonl"
                  "R86_LEAF_SIZE_OUT=$work/$runid.leaf_sizes.out"
                  "R86_OCCUPANCY_OUT=$work/$runid.occupancy.jsonl" )
  fi
  echo "START_RUN=$runid C=$C K=$K N=$N"
  set +e
  (
    cd "$work" || exit 4
    /usr/bin/time -o "$times" -f 'WALL_S=%e PEAK_RSS_KiB=%M TIME_CHILD_STATUS=%x' \
     timeout --signal=TERM --kill-after=10s 1800s \
     env "${unset_env[@]}" PARLAY_NUM_THREADS="$THREADS" OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 \
         MKL_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 "${counter_env[@]}" \
      taskset -c "$CPUSET" "$bin" \
       -base_path "$BASE" -graph_outfile "$graph" \
       -num_clusters "$N" -cluster_size "$K" -top_level_leaders 100 \
       -fanout_scheme 10,3,1 -mst_deg 2 -prune 1 -prune_all 1 -prune_degree 64 \
       -table_size "$C" -hash_bits 12 -alpha 1.1 -k 0 > "$log" 2>&1
  )
  rc=$?
  set -e
  echo "$rc" > "$work/native_exit_status.txt"
  if ((rc!=0));then
    echo "RUN_FAILED=$runid NATIVE_EXIT=$rc"; tail -n 40 "$log" || true; exit 5
  fi
  [[ -s "$graph" ]] || { echo "RUN_FAILED_EMPTY_GRAPH=$runid"; exit 5; }
  sha="$(sha256sum "$graph" | awk '{print $1}')"
  sha256sum "$graph" > "$graph.sha256"
  sha256sum "$log" > "$log.sha256"
  if [[ "$mode" == on ]]; then
    for suf in counters.jsonl leaf_sizes.out occupancy.jsonl;do
      [[ -s "$work/$runid.$suf" ]] || { echo "RUN_FAILED_MISSING_COUNTER_OUTPUT=$runid.$suf"; exit 5; }
      sha256sum "$work/$runid.$suf" >> "$work/counter_outputs.sha256"
    done
  fi
  python3 - "$OUT" "$work" "$runid" "$arm" "$mode" "$C" "$K" "$N" "$rep" "$sha" <<'PY'
import csv,json,re,sys,os
from pathlib import Path
out,work=map(Path,sys.argv[1:3]); runid,arm,mode=sys.argv[3:6]
C,K,N,rep=map(int,sys.argv[6:10]); sha=sys.argv[10]
raw=(work/f'{runid}.build.log').read_text(errors='replace')
get=lambda expr:[int(x) for x in re.findall(expr,raw)]
b=get(r'Total buckets:\s*(\d+)');points=get(r'Total points:\s*(\d+)');wp=get(r'# of comparisons during clustering:\s*(\d+)')
assert len(b)==len(points)==len(wp)==N, f'EXPECTED_{N}_PASSES actual={len(b)},{len(points)},{len(wp)}'
txt=(work/f'{runid}.time.txt').read_text(errors='replace');
wall=re.search(r'WALL_S=([0-9.]+)',txt);rss=re.search(r'PEAK_RSS_KiB=(\d+)',txt)
assert wall and rss
row=[runid,arm,mode,C,K,N,4,os.environ['CPUSET'],rep,float(wall.group(1)),int(rss.group(1)),
  (work/f'{runid}.graph').stat().st_size,sha,b[0],points[0],wp[0],
  b[1] if N==2 else '',points[1] if N==2 else '',wp[1] if N==2 else '',
  0,str(work/f'{runid}.build.log'),str(work/f'{runid}.counters.jsonl') if mode=='on' else '',
  str(work/f'{runid}.leaf_sizes.out') if mode=='on' else '',
  str(work/f'{runid}.occupancy.jsonl') if mode=='on' else '',
  'COLLECTED_NOT_SEARCH_VALIDATED']
with (out/'runs.csv').open('a',newline='') as f:csv.writer(f).writerow(row)
(work/f'{runid}.partition.json').write_text(json.dumps({'run_id':runid,'P1_buckets':b[0],'P1_points':points[0],
  'P1_wp_cumulative':wp[0],'P2_buckets':b[1] if N==2 else None,'P2_points':points[1] if N==2 else None,
  'P2_wp_cumulative':wp[1] if N==2 else None},indent=2)+'\n')
print('RUN_CAPTURED',runid,'P1_buckets',b[0],'P1_WP',wp[0],'sha',sha[:16])
PY
  echo "RUN_PASS=$runid GRAPH_SHA=$sha"
}

# Reconcile dataset/CLI protocol against the successful independent Highway
# control BEFORE any H17/C/K/N claims. No modification of earlier artifacts.
run_one stock off 160 1024 2 1
python3 - "$OUT/stock_C160_K1024_N2_off_r1/stock_C160_K1024_N2_off_r1.partition.json" <<'PY'
import json,sys
r=json.load(open(sys.argv[1])); expect={'P1_buckets':8367,'P1_points':2999666,
'P1_wp_cumulative':89859812,'P2_buckets':8297,'P2_points':2999577,
'P2_wp_cumulative':177341343}
if any(r.get(k)!=v for k,v in expect.items()):
 print('CONTROL_WORKLOAD_MISMATCH_HOLD',r,expect);sys.exit(8)
print('A0_SIFT100K_BASELINE_PROTOCOL_MATCH_CONTROL_PASS')
PY
# Counterbalance run order across 3 OFF blocks to reduce thermal/time-order bias.
# A0 OFF rep1 was already executed above to verify the exact R85 control protocol.
run_ablation() {
  local a="$1" mode="$2" rep="$3" binary C K N
  case "$a" in
    A0) binary=stock; C=160; K=1024; N=2;;
    A1) binary=h17; C=160; K=1024; N=2;;
    A2) binary=h17; C=64;  K=1024; N=2;;
    A3) binary=h17; C=64;  K=512;  N=2;;
    A4) binary=h17; C=64;  K=512;  N=1;;
    *) echo "BAD_ARM=$a"; exit 4;;
  esac
  echo "===== ABLATION_ARM=$a MODE=$mode REP=$rep C=$C K=$K N=$N ====="
  run_one "$binary" "$mode" "$C" "$K" "$N" "$rep"
}
for a in A1 A2 A3 A4; do run_ablation "$a" off 1; done
for a in A4 A3 A2 A1 A0; do run_ablation "$a" off 2; done
for a in A2 A0 A4 A1 A3; do run_ablation "$a" off 3; done
for a in A0 A2 A4 A1 A3; do run_ablation "$a" on 1; done

# Validate per-arm graph hashes: ON must match all OFF reps within the arm.
# If not, preserve data but do not promote the result.
python3 - "$OUT" <<'PY'
from pathlib import Path
import csv,json,sys
out=Path(sys.argv[1]); rows=list(csv.DictReader((out/'runs.csv').open()))
assert len(rows)==20, f'EXPECTED_20_BUILDS_GOT_{len(rows)}'
# Must compare each ablation arm, not group A1-A4 together by identical h17 binary name.
arm_specs=[('A0','stock',160,1024,2),('A1','h17',160,1024,2),('A2','h17',64,1024,2),('A3','h17',64,512,2),('A4','h17',64,512,1)]
result={}
for name,b,C,K,N in arm_specs:
 these=[r for r in rows if r['arm']==b and (int(r['C']),int(r['K']),int(r['N']))==(C,K,N)]
 assert len(these)==4,(name,len(these))
 hashes={x['graph_sha256'] for x in these}
 result[name]={'C':C,'K':K,'N':N,'off_builds':3,'on_builds':1,
               'graph_SHA_equivalent_all_four':len(hashes)==1,
               'graph_shas':sorted(hashes),
               'OFF_wall_s':[float(x['wall_s']) for x in these if x['mode']=='off'],
               'OFF_peakRSS_KiB':[int(x['peak_rss_KiB']) for x in these if x['mode']=='off']}
all_stable=all(v['graph_SHA_equivalent_all_four'] for v in result.values())
(out/'build_only_summary.json').write_text(json.dumps({'status':'BUILD_COLLECTION_DONE_SEARCH_NOT_RUN' if all_stable else 'BUILD_COLLECTION_DONE_GRAPH_SHA_VARIANCE_HOLD',
 'metrics':result,'search':{'status':'GT_EVALUATOR_NOT_VERIFIED'},
 'warning':'G2 graph format audit pending; do not claim matched-Recall or causal speedup from raw build wall alone.'},indent=2)+'\n')
for key,v in result.items():print('ARM_SUMMARY',key,'OFF_wall',v['OFF_wall_s'],'OFF_RSS',v['OFF_peakRSS_KiB'],'SHA_STABLE',v['graph_SHA_equivalent_all_four'])
print('GRAPH_SHA_CONSISTENCY_PASS' if all_stable else 'GRAPH_SHA_CONSISTENCY_HOLD_CHECK_VARIANCE')
print('SIFT100K_A0_A4_BUILD_WORK_COLLECTION_COMPLETED_NOT_FULL_BENCHMARK')
PY
printf 'RESULT_DIR=%s\n' "$OUT"
