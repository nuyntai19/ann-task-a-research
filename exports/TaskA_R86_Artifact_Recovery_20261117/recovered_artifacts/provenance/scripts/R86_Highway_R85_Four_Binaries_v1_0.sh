#!/usr/bin/env bash
# R86: construct 4 isolated binaries using the EXACT R85 Highway checkout.
# Build-only. Does not execute G1/G2, does not change original R85/R86/H70 source/builds.
set -Eeuo pipefail

ROOT="$HOME/ann-task-a/experiments"
GATES="$ROOT/R86/gates"
SRC="$ROOT/R86/r86_v1_2_source"
ORIG_ROOT="$ROOT/R86/r86_v1_2_builds"
R85_HW="$ROOT/H85/r85_0_matched_baseline/build_stock/_deps/highway-src"
R86_DEPS="$ORIG_ROOT/stock_off/_deps"
TARGET=neighbors-pipnn_FLOAT_T_EUCLIDEAN
REL="algorithms/PipNN/CMakeFiles/${TARGET}.dir/flags.make"
BIN_REL="algorithms/PipNN/$TARGET"
PREV_CTL="$GATES/highway_r85_stock_control_MVzZH3"

EXP_R86_STOCK=ba8e621fdcbf1649f101b2a0f63d13791061847e14608907ecbe601c4269b681
EXP_CONTROL=aa2d174ed063070045f1fbbc8051b1d97b851168b2f3bf53ee32215a867583be
EXP_HW85=6bc2d47793bae9c521fb4150936669647700765d
EXP_PARLAY=51017699dcc421f80479cdb238d3092233ad0d26
EXP_EIGEN=3147391d946bb4b6c68edd901f2add6ac1f31f8c
EXP_ABSEIL=bc257a88f7c1939f24e0379f14a3589e926c950c

require() { command -v "$1" >/dev/null || { echo "FAIL_MISSING_COMMAND=$1"; exit 3; }; }
sha_gate() {
  local file="$1" expected="$2" tag="$3" found
  [[ -f "$file" ]] || { echo "FAIL_MISSING_${tag}=$file"; exit 3; }
  found="$(sha256sum "$file" | awk '{print $1}')"
  [[ "$found" == "$expected" ]] || { echo "FAIL_${tag}_SHA expected=$expected found=$found"; exit 3; }
  echo "${tag}_SHA_PASS=$found"
}
git_gate() {
  local directory="$1" commit="$2" tag="$3" got dirty
  [[ -d "$directory" ]] || { echo "FAIL_MISSING_${tag}=$directory"; exit 3; }
  got="$(git -C "$directory" rev-parse HEAD)"
  [[ "$got" == "$commit" ]] || { echo "FAIL_${tag}_COMMIT expected=$commit found=$got"; exit 3; }
  dirty="$(git -C "$directory" status --porcelain --untracked-files=no)"
  [[ -z "$dirty" ]] || { echo "FAIL_${tag}_DIRTY_TRACKED_FILES=$dirty"; exit 3; }
  echo "${tag}_COMMIT_PASS=$got"
}

for cmd in cmake c++ sha256sum git python3 awk tee mktemp date grep; do require "$cmd"; done
[[ -f "$SRC/CMakeLists.txt" ]] || { echo "FAIL_R86_SOURCE_NOT_FOUND=$SRC"; exit 3; }
sha_gate "$ORIG_ROOT/stock_off/$BIN_REL" "$EXP_R86_STOCK" ORIGINAL_R86_STOCK
sha_gate "$PREV_CTL/build/$BIN_REL" "$EXP_CONTROL" PREVIOUS_CONTROL_STOCK
[[ -f "$PREV_CTL/source_sha256.txt" ]] || { echo "FAIL_CONTROL_SOURCE_MANIFEST_MISSING"; exit 3; }
( cd / && sha256sum -c "$PREV_CTL/source_sha256.txt" ) || { echo "FAIL_R86_SOURCE_DRIFT_FROM_PASSED_CONTROL"; exit 3; }
echo "R86_SOURCE_MATCHES_PASSED_CONTROL"
[[ -f "$PREV_CTL/decision.json" ]] || { echo 'FAIL_CONTROL_DECISION_JSON_MISSING'; exit 3; }
python3 - "$PREV_CTL/decision.json" <<'PY'
import json,sys
j=json.load(open(sys.argv[1]))
assert j.get('decision')=='CONTROL_PASS_MATCH_STABLE', 'CONTROL_NOT_PASS'
assert j.get('all_six_match_R85_reference') is True, 'CONTROL_NOT_SIX_EXACT_MATCH'
assert j.get('all_six_stable') is True, 'CONTROL_NOT_STABLE'
print('CONTROL_PASS_DECISION_PIN_PASS')
PY

git_gate "$R85_HW" "$EXP_HW85" HIGHWAY_R85
git_gate "$R86_DEPS/parlaylib-src" "$EXP_PARLAY" PARLAY_R86
git_gate "$R86_DEPS/eigen-src" "$EXP_EIGEN" EIGEN_R86
git_gate "$R86_DEPS/abseil-cpp-src" "$EXP_ABSEIL" ABSEIL_R86

# Fail closed if FetchContent declares an unexpected dependency.
python3 - "$SRC/CMakeLists.txt" <<'PY'
import pathlib,re,sys
s=pathlib.Path(sys.argv[1]).read_text()
names=set(x.lower() for x in re.findall(r'FetchContent_Declare\s*\(\s*([A-Za-z][A-Za-z0-9_-]*)',s,re.I))
allow={'parlaylib','eigen','abseil-cpp','highway','googlebenchmark'}
assert not(names-allow),f'UNREVIEWED_FETCHCONTENT_DECLARATIONS={names-allow}'
print('FETCHCONTENT_DECLARATIONS_PASS='+','.join(sorted(names)))
PY

mkdir -p "$GATES"
OUT="$(mktemp -d "$GATES/highway_r85_four_binary_XXXXXX")"
echo "SESSION=$OUT"
echo 'NOTE=Four new isolated builds only. No graph BUILD, ON counter run, or G1/G2 PASS claimed.'
{
  printf 'DATE_UTC=%s\n' "$(date -u +'%Y-%m-%dT%H:%M:%SZ')"
  printf 'R86_SOURCE=%s\nR85_HIGHWAY=%s\nR86_OTHERS=%s\n' "$SRC" "$R85_HW" "$R86_DEPS"
  printf 'CONTROL_SESSION=%s\n' "$PREV_CTL"
  cmake --version | head -1
  /usr/bin/c++ --version | head -1
} > "$OUT/provenance.txt"
for f in "$SRC/CMakeLists.txt" "$SRC/algorithms/PipNN/CMakeLists.txt" "$SRC/algorithms/PipNN/pipnn.h" "$SRC/algorithms/PipNN/pipnn_utils.h"; do
  if [[ -f "$f" ]]; then sha256sum "$f" >> "$OUT/source_sha256.txt"; fi
done
sha256sum "${BASH_SOURCE[0]}" > "$OUT/script_sha256.txt"

# All 4 variants intentionally use identical frozen dependencies and R86 source.
# Each variant gets a completely new CMake build directory.
for ARM in stock_off stock_on h17_off h17_on; do
  case "$ARM" in
    stock_off) H17=OFF; COUNTERS=OFF ;;
    stock_on)  H17=OFF; COUNTERS=ON ;;
    h17_off)   H17=ON; COUNTERS=OFF ;;
    h17_on)    H17=ON; COUNTERS=ON ;;
  esac
  BUILD="$OUT/build_$ARM"
  ORIGINAL="$ORIG_ROOT/$ARM"
  echo "===== CONFIGURE $ARM H17=$H17 COUNTERS=$COUNTERS ====="
  cmake_args=(
    -DCMAKE_BUILD_TYPE=Release
    -DCMAKE_CXX_COMPILER=/usr/bin/c++
    -DR70_USE_TIER=OFF
    "-DR71_USE_H17=$H17"
    "-DR86_USE_COUNTERS=$COUNTERS"
    -DFETCHCONTENT_FULLY_DISCONNECTED=ON
    "-DFETCHCONTENT_SOURCE_DIR_PARLAYLIB=$R86_DEPS/parlaylib-src"
    "-DFETCHCONTENT_SOURCE_DIR_EIGEN=$R86_DEPS/eigen-src"
    "-DFETCHCONTENT_SOURCE_DIR_ABSEIL-CPP=$R86_DEPS/abseil-cpp-src"
    "-DFETCHCONTENT_SOURCE_DIR_HIGHWAY=$R85_HW"
  )
  if [[ -d "$R86_DEPS/googlebenchmark-src" ]]; then
    cmake_args+=("-DFETCHCONTENT_SOURCE_DIR_GOOGLEBENCHMARK=$R86_DEPS/googlebenchmark-src")
  fi
  cmake -S "$SRC" -B "$BUILD" "${cmake_args[@]}" > "$OUT/${ARM}.configure.log" 2>&1 || {
    echo "FAIL_CONFIGURE_ARM=$ARM; log=$OUT/${ARM}.configure.log"; exit 4;
  }
  python3 - "$BUILD/CMakeCache.txt" "$SRC" "$R85_HW" "$H17" "$COUNTERS" <<'PY'
import sys
from pathlib import Path
p=Path(sys.argv[1]); src,hw,h17,counters=sys.argv[2:]
cache={}
for l in p.read_text(errors='replace').splitlines():
 if not l.startswith(('#','//')) and ':' in l and '=' in l:
  k,extra=l.split(':',1);cache[k]=extra.split('=',1)[1]
expected={'CMAKE_HOME_DIRECTORY':src,'CMAKE_BUILD_TYPE':'Release',
'CMAKE_CXX_COMPILER':'/usr/bin/c++','R70_USE_TIER':'OFF','R71_USE_H17':h17,
'R86_USE_COUNTERS':counters,'FETCHCONTENT_SOURCE_DIR_HIGHWAY':hw,
'FETCHCONTENT_FULLY_DISCONNECTED':'ON'}
for k,v in expected.items():
 if cache.get(k)!=v:raise SystemExit(f'FAIL_CMAKE_CACHE: {k} {cache.get(k)} != {v}')
print('CMAKE_CACHE_PIN_PASS')
PY
  echo "===== COMPILE $ARM ====="
  if ! cmake --build "$BUILD" --target "$TARGET" --parallel 4 > "$OUT/${ARM}.compile.log" 2>&1; then
    echo "FAIL_COMPILE_ARM=$ARM; log=$OUT/${ARM}.compile.log"; exit 5
  fi
  BIN="$BUILD/$BIN_REL"
  [[ -x "$BIN" ]] || { echo "FAIL_BINARY_MISSING_ARM=$ARM"; exit 5; }
  sha256sum "$BIN" > "$OUT/${ARM}.binary.sha256"
  python3 - "$ORIGINAL/$REL" "$BUILD/$REL" "$R85_HW" "$ARM" <<'PY'
from pathlib import Path
import sys
old,new,hw=map(Path,sys.argv[1:4]);arm=sys.argv[4]
def get(p):
 if not p.is_file():raise SystemExit(f'FAIL_FLAGS_FILE_MISSING: {p}')
 vals={}
 for line in p.read_text(errors='replace').splitlines():
  if '=' in line:
   k,v=line.split('=',1); k=k.strip()
   if k in ('CXX_FLAGS','CXX_DEFINES','CXX_INCLUDES'):vals[k]=v.strip()
 return vals
r=get(new)
if str(hw) not in r.get('CXX_INCLUDES',''):
 raise SystemExit(f'FAIL_HIGHWAY_R85_NOT_IN_TARGET_INCLUDES={arm}')
if old.is_file():
 o=get(old)
 for k in ('CXX_FLAGS','CXX_DEFINES'):
  if o.get(k)!=r.get(k):
   raise SystemExit(f'FAIL_FLAGS_DIFFER_FROM_ORIGINAL_VARIANT={arm}:{k}\nold={o.get(k)}\nnew={r.get(k)}')
 print('ORIGINAL_TARGET_FLAGS_MATCH='+arm)
else:
 print('WARNING_ORIGINAL_TARGET_FLAGS_NOT_FOUND='+arm)
print('HIGHWAY_R85_TARGET_INCLUDE_PASS='+arm)
PY
  echo "BINARY_BUILD_PASS=$ARM $(cat "$OUT/${ARM}.binary.sha256")"
done

python3 - "$OUT" <<'PY'
import json,hashlib,sys
from pathlib import Path
out=Path(sys.argv[1]); names=['stock_off','stock_on','h17_off','h17_on']
records={}
for name in names:
 p=out/f'build_{name}/algorithms/PipNN/neighbors-pipnn_FLOAT_T_EUCLIDEAN'
 assert p.is_file() and p.stat().st_size>0,(name,str(p))
 records[name]={'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),
 'H17':name.startswith('h17'),'COUNTERS_ON':name.endswith('on')}
assert len(records)==4
(out/'four_binary_manifest.json').write_text(json.dumps({
 'status':'FOUR_BINARIES_BUILT_NOT_VALIDATED','highway_rev':'6bc2d47793bae9c521fb4150936669647700765d',
 'source':str(Path.home()/'ann-task-a/experiments/R86/r86_v1_2_source'),
 'control_decision':'CONTROL_PASS_MATCH_STABLE', 'binaries':records,
 'next':'Native 10K ON/OFF G2 counter invariant + graph audit + search protocol; this build is NOT G1/G2 PASS'},indent=2)+'\n')
print('FOUR_BINARY_MANIFEST='+str(out/'four_binary_manifest.json'))
PY

echo 'R86_HIGHWAY_R85_FOUR_BINARY_BUILD_DONE'
echo 'IMPORTANT=No original build overwritten; counters/graph/search NOT VALIDATED YET'
echo "RESULT_DIR=$OUT"
