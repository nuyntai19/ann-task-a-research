#!/usr/bin/env bash
# R86 G1: isolated R86 Stock OFF against R85's Highway checkout.
# Diagnostics ONLY. This script never edits H70, R85, original R86 source/build, or G1 artifacts.
set -Eeuo pipefail

ROOT="$HOME/ann-task-a/experiments"
GATES="$ROOT/R86/gates"
SCRIPT_PATH="${BASH_SOURCE[0]}"

if [[ "${1:-}" != "--worker" ]]; then
  mkdir -p "$GATES"
  SESSION="$(mktemp -d "$GATES/highway_r85_stock_control_XXXXXX")"
  echo "SESSION=$SESSION"
  echo "TIMEBOX_SECONDS=3600"
  echo "SCRIPT=$SCRIPT_PATH"
  echo "NOTE=Only one new R86 Stock OFF binary; six SIFT100K builds; no original artifacts modified."
  set +e
  timeout --signal=TERM --kill-after=15s 3600 \
    bash "$SCRIPT_PATH" --worker "$SESSION" 2>&1 | tee "$SESSION/console.log"
  RC=${PIPESTATUS[0]}
  set -e
  if [[ "$RC" -eq 124 || "$RC" -eq 137 ]]; then
    echo "TIMEBOX_STOP_1_HOUR; result remains INCOMPLETE, not PASS"
  elif [[ "$RC" -ne 0 ]]; then
    echo "DIAGNOSTIC_FAILED_EXIT=$RC; inspect $SESSION/console.log"
  fi
  echo "RESULT_DIR=$SESSION"
  echo "experiment_exit_code=$RC"
  exit "$RC"
fi

OUT="${2:?Worker session missing}"
[[ -d "$OUT" ]] || { echo "ERROR: session directory missing"; exit 3; }
trap 'rc=$?; echo "FAIL_AT_LINE=${LINENO} EXIT_CODE=$rc"; exit "$rc"' ERR

SRC="$ROOT/R86/r86_v1_2_source"
BASE="$HOME/ann-task-a/data/sift100k.fbin"
ORIG_BUILD="$ROOT/R86/r86_v1_2_builds/stock_off"
ORIG_BIN="$ORIG_BUILD/algorithms/PipNN/neighbors-pipnn_FLOAT_T_EUCLIDEAN"
R85_HW="$ROOT/H85/r85_0_matched_baseline/build_stock/_deps/highway-src"
R86_HW="$ORIG_BUILD/_deps/highway-src"
R86_DEPS="$ORIG_BUILD/_deps"
H70_CWD="$ROOT/H70/pipnn-clean-443a328"
BUILD="$OUT/build"
BIN="$BUILD/algorithms/PipNN/neighbors-pipnn_FLOAT_T_EUCLIDEAN"

EXPECT_BASE=e50ff1bc34bcc6d1c97dd001023c09a666971cde64605cc06671ed8a8ff1ed12
EXPECT_R86_BIN=ba8e621fdcbf1649f101b2a0f63d13791061847e14608907ecbe601c4269b681
EXPECT_HW85=6bc2d47793bae9c521fb4150936669647700765d
EXPECT_HW86=0e0a01dac5321dafec478d781487d1323492359e
EXPECT_PARLAY=51017699dcc421f80479cdb238d3092233ad0d26
EXPECT_EIGEN=3147391d946bb4b6c68edd901f2add6ac1f31f8c
EXPECT_ABSEIL=bc257a88f7c1939f24e0379f14a3589e926c950c

require_cmd() { command -v "$1" >/dev/null || { echo "ERROR missing command: $1"; exit 3; }; }
check_sha() {
  local f="$1" want="$2" label="$3" actual
  [[ -f "$f" ]] || { echo "ERROR missing $label: $f"; exit 3; }
  actual="$(sha256sum "$f" | awk '{print $1}')"
  [[ "$actual" == "$want" ]] || { echo "ERROR ${label}_SHA_MISMATCH: $actual != $want"; exit 3; }
  echo "${label}_SHA_PASS=$actual"
}
check_repo() {
  local dir="$1" want="$2" label="$3" actual status
  [[ -d "$dir/.git" || -f "$dir/.git" ]] || { echo "ERROR no git checkout for $label: $dir"; exit 3; }
  actual="$(git -C "$dir" rev-parse HEAD)"
  [[ "$actual" == "$want" ]] || { echo "ERROR ${label}_COMMIT_MISMATCH: $actual != $want"; exit 3; }
  status="$(git -C "$dir" status --porcelain --untracked-files=no)"
  [[ -z "$status" ]] || { echo "ERROR ${label}_DIRTY_TRACKED_FILES: $status"; exit 3; }
  echo "${label}_COMMIT_PASS=$actual"
}

echo "========== PREFLIGHT ========== "
for c in bash cmake git python3 sha256sum taskset timeout tee awk; do require_cmd "$c"; done
[[ -x /usr/bin/time ]] || { echo "ERROR: /usr/bin/time missing"; exit 3; }
[[ -d "$SRC" && -f "$SRC/CMakeLists.txt" ]] || { echo "ERROR R86 isolated source missing: $SRC"; exit 3; }
[[ -d "$H70_CWD" ]] || { echo "ERROR H70 working directory missing"; exit 3; }
[[ -x "$ORIG_BIN" ]] || { echo "ERROR R86 Stock OFF binary missing"; exit 3; }
check_sha "$ORIG_BIN" "$EXPECT_R86_BIN" R86_ORIGINAL_STOCK_OFF
check_sha "$BASE" "$EXPECT_BASE" SIFT100K_BASE
check_repo "$R85_HW" "$EXPECT_HW85" R85_HIGHWAY
check_repo "$R86_HW" "$EXPECT_HW86" R86_HIGHWAY
check_repo "$R86_DEPS/parlaylib-src" "$EXPECT_PARLAY" R86_PARLAY
check_repo "$R86_DEPS/eigen-src" "$EXPECT_EIGEN" R86_EIGEN
check_repo "$R86_DEPS/abseil-cpp-src" "$EXPECT_ABSEIL" R86_ABSEIL

# Only explicitly pinned/local FetchContent sources may be used. A missing optional
# googlebenchmark tree is allowed only if the configuration does not require it;
# FULLY_DISCONNECTED causes configure to fail closed rather than fetch it.
python3 - "$SRC/CMakeLists.txt" <<'PY'
import pathlib,re,sys
s=pathlib.Path(sys.argv[1]).read_text()
names=set(re.findall(r'FetchContent_Declare\s*\(\s*([A-Za-z][A-Za-z0-9_-]*)',s,re.I))
allowed={'parlaylib','eigen','abseil-cpp','highway','googlebenchmark'}
unknown={x for x in names if x.lower() not in allowed}
print('FETCHCONTENT_DECLARATIONS='+','.join(sorted(names)))
if unknown:raise SystemExit('UNKNOWN_FETCHCONTENT_DECLARATIONS='+','.join(sorted(unknown)))
PY

for c in 0 '0,2,4,6'; do
  taskset -c "$c" true || { echo "ERROR CPU_AFFINITY_NOT_AVAILABLE=$c"; exit 3; }
done

{
 echo "DATE_UTC=$(date -u +'%Y-%m-%dT%H:%M:%SZ')"
 echo "SOURCE=$SRC"
 echo "R85_HIGHWAY=$R85_HW"
 echo "R86_ORIGINAL_BUILD=$ORIG_BUILD"
 echo "DATA=$BASE"
 echo "BUILD=$BUILD"
 cmake --version | head -1
 /usr/bin/c++ --version | head -1
 echo "CPU_AFFINITY_1=0 CPU_AFFINITY_4=0,2,4,6"
 echo "HISTORICAL_R85_SIFT100K_B1=8367 B2=8297 P1_WP=89859812 P2_WP_CUM=177341343"
} > "$OUT/provenance.txt"
for file in "$SRC/CMakeLists.txt" "$SRC/algorithms/PipNN/CMakeLists.txt" "$SRC/algorithms/PipNN/pipnn.h" "$SRC/algorithms/PipNN/pipnn_utils.h"; do
  [[ -f "$file" ]] && sha256sum "$file" >> "$OUT/source_sha256.txt"
done
sha256sum "$SCRIPT_PATH" > "$OUT/script_sha256.txt"

echo "========== CMAKE CONFIGURE: NEW ISOLATED DIRECTORY ========== "
args=(
  -DCMAKE_BUILD_TYPE=Release
  -DCMAKE_CXX_COMPILER=/usr/bin/c++
  -DR70_USE_TIER=OFF
  -DR71_USE_H17=OFF
  -DR86_USE_COUNTERS=OFF
  -DFETCHCONTENT_FULLY_DISCONNECTED=ON
  "-DFETCHCONTENT_SOURCE_DIR_PARLAYLIB=$R86_DEPS/parlaylib-src"
  "-DFETCHCONTENT_SOURCE_DIR_EIGEN=$R86_DEPS/eigen-src"
  "-DFETCHCONTENT_SOURCE_DIR_ABSEIL-CPP=$R86_DEPS/abseil-cpp-src"
  "-DFETCHCONTENT_SOURCE_DIR_HIGHWAY=$R85_HW"
)
if [[ -d "$R86_DEPS/googlebenchmark-src" ]]; then
  args+=("-DFETCHCONTENT_SOURCE_DIR_GOOGLEBENCHMARK=$R86_DEPS/googlebenchmark-src")
  echo "GOOGLEBENCHMARK=R86_EXISTING_CHECKOUT"
else
  echo "GOOGLEBENCHMARK=NOT_PRESENT_IF_REQUIRED_FAIL_CLOSED"
fi
cmake -S "$SRC" -B "$BUILD" "${args[@]}" 2>&1 | tee "$OUT/configure.log"

python3 - "$BUILD/CMakeCache.txt" "$SRC" "$R85_HW" <<'PY'
from pathlib import Path
import sys
p=Path(sys.argv[1]); src=sys.argv[2]; hw=sys.argv[3]
if not p.is_file(): raise SystemExit('CMAKE_CACHE_MISSING')
cache={}
for l in p.read_text(errors='replace').splitlines():
 if ':' in l and '=' in l and not l.startswith(('#','//')):
  k,other=l.split(':',1); cache[k]=other.split('=',1)[1]
for k,v in {'CMAKE_HOME_DIRECTORY':src,'CMAKE_BUILD_TYPE':'Release','CMAKE_CXX_COMPILER':'/usr/bin/c++','R70_USE_TIER':'OFF','R71_USE_H17':'OFF','R86_USE_COUNTERS':'OFF','FETCHCONTENT_SOURCE_DIR_HIGHWAY':hw}.items():
 got=cache.get(k)
 if got!=v: raise SystemExit(f'CACHE_FAIL {k}={got!r}, expected={v!r}')
print('R86_SOURCE_AND_HIGHWAY_OVERRIDE_CACHE_PASS')
PY

echo "========== CMAKE BUILD: ONE STOCK OFF TARGET ONLY ========== "
cmake --build "$BUILD" --target neighbors-pipnn_FLOAT_T_EUCLIDEAN --parallel 4 2>&1 | tee "$OUT/compile.log"
[[ -x "$BIN" ]] || { echo "ERROR compiled binary missing: $BIN"; exit 3; }
sha256sum "$BIN" > "$OUT/new_binary_sha256.txt"
cat "$OUT/new_binary_sha256.txt"

# Fail closed if build flags or defines are not comparable to the original R86.
python3 - "$ORIG_BUILD" "$BUILD" "$R85_HW" <<'PY'
from pathlib import Path
import sys
old,new,hw=map(Path,sys.argv[1:])
rel='algorithms/PipNN/CMakeFiles/neighbors-pipnn_FLOAT_T_EUCLIDEAN.dir/flags.make'
def extract(p):
 if not p.is_file(): raise SystemExit(f'MISSING_FLAGS {p}')
 vals={}
 for line in p.read_text().splitlines():
  if '=' in line:
   key,value=line.split('=',1)
   key=key.strip()
   if key in {'CXX_FLAGS','CXX_DEFINES','CXX_INCLUDES'}: vals[key]=value.strip()
 return vals
l=extract(old/rel); r=extract(new/rel)
for k in ('CXX_FLAGS','CXX_DEFINES'):
 if l.get(k)!=r.get(k):
  raise SystemExit(f'{k}_MISMATCH\nold={l.get(k)}\nnew={r.get(k)}')
if str(hw) not in r.get('CXX_INCLUDES',''):
 raise SystemExit('R85_HIGHWAY_PATH_NOT_IN_COMPILER_INCLUDES')
print('COMPILER_DEFINES_FLAGS_MATCH_ORIGINAL_R86')
print('HIGHWAY_R85_INCLUDE_PATH_CONFIRMED')
PY

# The measured old baseline is historical and not rebuilt here.
# Decision fields were predeclared before execution: P1/P2 buckets,
# P1/P2 total occurrences, P1/P2 cumulative clustering comparisons.
cd "$H70_CWD"
echo "========== SIX INDEPENDENT SIFT100K BUILDS ========== "
for THREADS in 1 4; do
  if [[ "$THREADS" -eq 1 ]]; then AFFINITY=0; else AFFINITY='0,2,4,6'; fi
  for REP in 1 2 3; do
    RUN="r85hw_r86stock_t${THREADS}_r${REP}"
    LOG="$OUT/$RUN.log"
    GRAPH="$OUT/$RUN.graph"
    echo "===== START $RUN ====="
    env \
      PARLAY_NUM_THREADS="$THREADS" \
      OMP_NUM_THREADS=1 \
      OPENBLAS_NUM_THREADS=1 \
      MKL_NUM_THREADS=1 \
      VECLIB_MAXIMUM_THREADS=1 \
      taskset -c "$AFFINITY" \
      /usr/bin/time -f 'WALL_S=%e PEAK_RSS_KiB=%M' \
      "$BIN" \
      -base_path "$BASE" \
      -graph_outfile "$GRAPH" \
      -num_clusters 2 \
      -cluster_size 1024 \
      -top_level_leaders 100 \
      -fanout_scheme 10,3,1 \
      -mst_deg 2 \
      -prune 1 \
      -prune_all 1 \
      -prune_degree 64 \
      -table_size 160 \
      -hash_bits 12 \
      -alpha 1.1 \
      -k 0 \
      > "$LOG" 2>&1
    [[ -s "$GRAPH" ]] || { echo "ERROR graph empty $RUN"; exit 4; }
    sha256sum "$GRAPH" > "$GRAPH.sha256"
    python3 - "$LOG" "$GRAPH" "$OUT/$RUN.json" "$THREADS" "$REP" <<'PY'
import hashlib,json,re,sys
from pathlib import Path
log,graph,out=map(Path,sys.argv[1:4]); threads=int(sys.argv[4]); rep=int(sys.argv[5]); s=log.read_text(errors='replace')
def nums(p): return [int(x) for x in re.findall(p,s,re.M)]
b=nums(r'^Total buckets:\s*(\d+)\s*$')
p=nums(r'^Total points:\s*(\d+)\s*$')
w=nums(r'^# of comparisons during clustering:\s*(\d+)\s*$')
if len(b)!=2 or len(p)!=2 or len(w)!=2:raise SystemExit(f'INVALID_PARTITION_LOG {log.name}, bucket={b}, points={p}, wp={w}')
if not re.search(r'Data: detected 100000 points with dimension 128',s):raise SystemExit('WRONG_INPUT')
if 'R70_RESERVOIR_VARIANT=STOCK_FLAT_C160' not in s:raise SystemExit('WRONG_RESERVOIR_ARM')
if 'R71_SELECTION_VARIANT=STOCK_HIGHWAY' not in s:raise SystemExit('WRONG_SORT_ARM')
if not re.search(r'Writing graph with 100000 points and max degree 64',s):raise SystemExit('GRAPH_WRITER_N_OR_DEG_INVALID')
if not re.search(r'Graph built in ',s):raise SystemExit('BUILD_COMPLETION_MARKER_MISSING')
wall=re.search(r'^WALL_S=([0-9.]+) PEAK_RSS_KiB=(\d+)$',s,re.M)
if wall is None:raise SystemExit('TIME_OR_RSS_MARKER_MISSING')
occupancy=re.findall(r'^Average table size:\s*(\d+)\s*$',s,re.M)
bucket_phases=[float(x) for x in re.findall(r'^Parlay time: buckets time:\s*([0-9.]+)',s,re.M)]
leaf_phases=[float(x) for x in re.findall(r'^Parlay time: build leaf time:\s*([0-9.]+)',s,re.M)]
prune_phase=re.findall(r'^Parlay time: Final prune time:\s*([0-9.]+)',s,re.M)
record={'run_id':log.stem,'threads':threads,'rep':rep,'P1_buckets':b[0],'P2_buckets':b[1],
'P1_total_points':p[0],'P2_total_points':p[1],
'P1_WP_cumulative':w[0],'P2_WP_cumulative':w[1],
'P2_WP_increment':w[1]-w[0],
'printed_avg_table_size':int(occupancy[-1]) if occupancy else None,
'P1_bucket_wall_s':bucket_phases[0] if len(bucket_phases)==2 else None,
'P2_bucket_wall_s':bucket_phases[1] if len(bucket_phases)==2 else None,
'P1_leaf_wall_s':leaf_phases[0] if len(leaf_phases)==2 else None,
'P2_leaf_wall_s':leaf_phases[1] if len(leaf_phases)==2 else None,
'final_prune_wall_s':float(prune_phase[-1]) if prune_phase else None,
'wall_s':float(wall.group(1)),'peak_rss_KiB':int(wall.group(2)),
'graph_bytes':graph.stat().st_size,
'graph_sha256':hashlib.sha256(graph.read_bytes()).hexdigest(),
'graph_path':str(graph),'log_path':str(log), 'graph_validation':'NONEMPTY_AND_WRITER_LOG_ONLY'}
out.write_text(json.dumps(record,indent=2)+'\n')
print('BUCKETS_P1_P2='+str(b)+' POINTS_P1_P2='+str(p)+' WP_CUM_P1_P2='+str(w))
PY
    echo "RUN_PASS $RUN (diagnostic build only; not G1 gate PASS)"
  done
done

echo "========== PRE-REGISTERED DECISION (EXACT R85 STOCK REFERENCE) ========== "
python3 - "$OUT" <<'PY'
import csv,json,sys
from pathlib import Path
out=Path(sys.argv[1]); records=[]
for t in (1,4):
 for rep in (1,2,3):
  p=out/f'r85hw_r86stock_t{t}_r{rep}.json'
  records.append(json.loads(p.read_text()))
expected={
 'P1_buckets':8367,'P1_total_points':2999666,'P1_WP_cumulative':89859812,
 'P2_buckets':8297,'P2_total_points':2999577,'P2_WP_cumulative':177341343
}
fields=list(expected)
for x in records:
 x['exact_match_R85_reference']=all(x[f]==v for f,v in expected.items())
 x['core_match_bucket_and_WP']=all(x[f]==expected[f] for f in ('P1_buckets','P2_buckets','P1_WP_cumulative','P2_WP_cumulative'))
by_thread={str(t):len({tuple(r[f] for f in fields) for r in records if r['threads']==t})==1 for t in (1,4)}
stable_all=len({tuple(r[f] for f in fields) for r in records})==1
match_all=all(r['exact_match_R85_reference'] for r in records)
core_match_all=all(r['core_match_bucket_and_WP'] for r in records)
decision='CONTROL_PASS_MATCH_STABLE' if match_all and stable_all else 'CONTROL_HOLD_MOVE_TO_INTERNAL_R86_PROTOCOL'
result={'decision':decision,'pass_is_not_G1_PASS':True,'R85_reference':expected,
 'predeclared_core_fields':['P1_buckets','P2_buckets','P1_WP_cumulative','P2_WP_cumulative'],
 'extra_invariant_fields':['P1_total_points','P2_total_points'],
 'all_six_match_R85_reference':match_all,'all_six_match_buckets_and_WP':core_match_all,
 'within_thread_stability':by_thread,'all_six_stable':stable_all,
 'n_repetitions':len(records),'dataset':'SIFT100K','C':160,'K':1024,'N':2,
 'interpretation':('Eligible to construct four binaries separately and run 10K ON/OFF counters; does not prove Recall or G1' if match_all and stable_all else 'Stop this Highway investigation as preregistered; keep old G1 HOLD and use pinned internally calibrated R86, after ON/OFF 10K validation')}
(out/'decision.json').write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n')
with (out/'summary.csv').open('w',newline='') as f:
 columns=['run_id','threads','rep',*fields,'P2_WP_increment','printed_avg_table_size','P1_bucket_wall_s','P2_bucket_wall_s','P1_leaf_wall_s','P2_leaf_wall_s','final_prune_wall_s','wall_s','peak_rss_KiB','graph_bytes','graph_sha256','exact_match_R85_reference','core_match_bucket_and_WP']
 w=csv.DictWriter(f,fieldnames=columns);w.writeheader();w.writerows({k:r.get(k) for k in columns} for r in records)
for r in records:
 print(f"{r['run_id']}: P1b={r['P1_buckets']} P2b={r['P2_buckets']} P1WP={r['P1_WP_cumulative']} P2WPcum={r['P2_WP_cumulative']} R85_MATCH={r['exact_match_R85_reference']}")
print('R86_HIGHWAY_R85_CONTROL_DECISION='+decision)
print('ALL_SIX_STABLE='+str(stable_all))
print('ALL_SIX_MATCH_BUCKET_WP='+str(core_match_all))
print('ALL_SIX_MATCH_FULL_REFERENCE='+str(match_all))
print('DECISION_JSON='+str(out/'decision.json'))
print('SUMMARY_CSV='+str(out/'summary.csv'))
print('IMPORTANT: No G1 PASS and no 4-binary rebuild performed automatically.')
PY

echo "R86_G1_HIGHWAY_R85_ONE_BINARY_CONTROL_DONE"
