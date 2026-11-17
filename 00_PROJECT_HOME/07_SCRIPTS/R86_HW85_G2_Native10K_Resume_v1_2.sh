#!/usr/bin/env bash
# R86 HW85 G2 SIFT10K native collector: safe resume v1.2
# Fixes v1.0 / v1.1 collectors: discover ALL literal R86_*_OUT variables
# in pinned source and provide an absolute output file for each *_on run.
# No rebuild. No changes to source, binaries, prior graph/results/logs.
# No graph audit, work-counter validation or G2 PASS is claimed.
set -Eeuo pipefail
umask 077

GATES="$HOME/ann-task-a/experiments/R86/gates"
RUN="$GATES/g2_hw85_native10k_JWuLB9"
BUILD="$GATES/highway_r85_four_binary_jvYREW"
MANIFEST="$BUILD/four_binary_manifest.json"
SOURCE_SHA="$BUILD/source_sha256.txt"
SRC="$HOME/ann-task-a/experiments/R86/r86_v1_2_source"
TARGET="algorithms/PipNN/neighbors-pipnn_FLOAT_T_EUCLIDEAN"
PREFIX="$RUN/sift10k_prefix.fbin"
EXPECT_PREFIX='94320c4336a35f046de768a24ada57aa8998f511df9aa2a7c72fe9ed8c67c1f5'
EXPECT_STOCK_OFF_GRAPH='59dd18da46ebb88604de4aa0d253df36b65ca5965de80af2f616d5f119a637a9'

for cmd in python3 sha256sum awk grep env taskset timeout date stat; do
  command -v "$cmd" >/dev/null || { echo "PREFLIGHT_MISSING_COMMAND=$cmd"; exit 3; }
done
[[ -x /usr/bin/time ]] || { echo 'PREFLIGHT_MISSING_TIME'; exit 3; }
[[ -s "$MANIFEST" && -s "$SOURCE_SHA" && -s "$PREFIX" ]] || {
  echo 'PREFLIGHT_MISSING_MANIFEST_SOURCE_SHA_OR_PREFIX'; exit 3;
}
[[ -s "$RUN/stock_off/stock_off.graph" && -s "$RUN/stock_off/stock_off.build.log" ]] || {
  echo 'PREFLIGHT_MISSING_ORIGINAL_STOCK_OFF'; exit 3;
}
[[ -s "$RUN/resume_v1_1/stock_on/stock_on.build.log" ]] || {
  echo 'PREFLIGHT_MISSING_V1_1_FAILURE_EVIDENCE'; exit 3;
}
grep -Fq 'R86 requires absolute path env R86_LEAF_SIZE_OUT' \
  "$RUN/resume_v1_1/stock_on/stock_on.build.log" || {
    echo 'PREFLIGHT_V1_1_FAILURE_NOT_AS_EXPECTED'; exit 3;
  }

sha_gate() {
  local f="$1" want="$2" tag="$3" actual
  actual="$(sha256sum "$f" | awk '{print $1}')"
  [[ "$actual" == "$want" ]] || { echo "SHA_FAIL_${tag} expected=$want actual=$actual"; exit 3; }
  echo "SHA_PASS_${tag}=$actual"
}

echo '===== V1.2 PINNED PREFLIGHT ====='
sha_gate "$PREFIX" "$EXPECT_PREFIX" SIFT10K_PREFIX
sha_gate "$RUN/stock_off/stock_off.graph" "$EXPECT_STOCK_OFF_GRAPH" ORIGINAL_STOCK_OFF_GRAPH
( cd / && sha256sum -c "$SOURCE_SHA" ) || { echo 'PREFLIGHT_SOURCE_DRIFT'; exit 3; }

python3 - "$MANIFEST" "$BUILD" <<'PY'
import hashlib,json,sys
from pathlib import Path
m=json.loads(Path(sys.argv[1]).read_text()); root=Path(sys.argv[2]).resolve()
expected={
 'stock_off':'aa2d174ed063070045f1fbbc8051b1d97b851168b2f3bf53ee32215a867583be',
 'stock_on':'396ef852992428cd3f935bcb33eeeeacc1bae565fbc4a441c1fa9d19720122ff',
 'h17_off':'5f673586210f93b424fc81791ec7873cb74600843b5004c0a4aaaf32bf936297',
 'h17_on':'ef707479be221cb7a3c6257298d22f614678878f0a7bfc724dc8b28fabdd21c4'
}
assert m.get('status')=='FOUR_BINARIES_BUILT_NOT_VALIDATED'
assert m.get('highway_rev')=='6bc2d47793bae9c521fb4150936669647700765d'
assert m.get('control_decision')=='CONTROL_PASS_MATCH_STABLE'
assert set(m['binaries'])==set(expected)
for arm,sha in expected.items():
  a=m['binaries'][arm]
  assert a['sha256']==sha and bool(a['COUNTERS_ON'])==arm.endswith('_on')
  assert bool(a['H17'])==arm.startswith('h17')
  p=Path(a['path']).resolve(strict=True)
  assert p==root/f'build_{arm}/algorithms/PipNN/neighbors-pipnn_FLOAT_T_EUCLIDEAN'
  assert hashlib.sha256(p.read_bytes()).hexdigest()==sha
  print(f'BINARY_PIN_PASS={arm} {sha}')
PY

# Collect output-variable contract from the SHA-pinned source AND the two
# pinned ON binaries. A binary contains runtime env-name string literals.
# Do not rely on the order of failures to discover required variables. Fail closed if the mandatory names are not present.
# Avoid hard-coding only one or two variables and repeatedly aborting later.
mapfile -t OUT_VARS < <(python3 - "$SRC" "$BUILD/build_stock_on/$TARGET" "$BUILD/build_h17_on/$TARGET" <<'PY'
from pathlib import Path
import re,sys
src=Path(sys.argv[1]); names=set()
for binary_arg in sys.argv[2:]:
    binary=Path(binary_arg)
    assert binary.is_file()
    names.update(x.decode("ascii") for x in re.findall(rb"\bR86_[A-Z][A-Z0-9_]*_OUT\b", binary.read_bytes()))
assert src.is_dir()
for base in [src/'algorithms'/'PipNN']:
    assert base.is_dir()
    for p in base.rglob('*'):
        if p.is_file() and p.suffix in {'.h','.hpp','.hh','.cc','.cpp','.cxx'} and p.stat().st_size < 3_000_000:
            txt=p.read_text(encoding='utf-8',errors='replace')
            names.update(re.findall(r'\bR86_[A-Z][A-Z0-9_]*_OUT\b',txt))
for n in sorted(names): print(n)
PY
)
[[ ${#OUT_VARS[@]} -ge 2 ]] || { echo 'FAIL_CANNOT_DISCOVER_R86_OUTPUT_CONTRACT'; exit 3; }
printf '%s\n' "${OUT_VARS[@]}" | grep -Fxq R86_COUNTER_OUT || { echo 'FAIL_NO_COUNTER_OUT_IN_SOURCE'; exit 3; }
printf '%s\n' "${OUT_VARS[@]}" | grep -Fxq R86_LEAF_SIZE_OUT || { echo 'FAIL_NO_LEAF_SIZE_OUT_IN_SOURCE'; exit 3; }
for n in "${OUT_VARS[@]}"; do [[ "$n" =~ ^R86_[A-Z0-9_]+_OUT$ ]] || exit 3; done
printf 'DISCOVERED_SOURCE_OUTPUT_VARS=%s\n' "${OUT_VARS[*]}"
echo "NUMBER_OUTPUT_VARS=${#OUT_VARS[@]}"

# New session every attempt; never overwrite v1.0 or v1.1 evidence.
RESUME="$(mktemp -d "$RUN/resume_v1_2_XXXXXX")"
sha256sum "${BASH_SOURCE[0]}" > "$RESUME/script_sha256.txt"
cp -- "$MANIFEST" "$RESUME/pinned_four_binary_manifest.json"
printf '%s\n' "${OUT_VARS[@]}" > "$RESUME/discovered_output_env_contract.txt"
{
  echo "V1_0_SESSION=$RUN"
  echo "V1_1_FAILURE_DIR=$RUN/resume_v1_1"
  echo 'REPAIR=SEND_ALL_R86_*_OUT_VALUES_AS_ABSOLUTE_PATHS_FROM_PINNED_SOURCE'
  echo "RESUME_DIR=$RESUME"
  echo 'SIFT10K_PREFIX_PINNED=TRUE'
  echo 'CONFIG=1 thread CPU 0 C160 K1024 N2'
  echo 'STOCK_OFF=EXISTING_V1_0_GRAPH_NOT_RERUN'
  echo 'G2_PASS=FALSE (collector only)'
  echo "START_UTC=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
} > "$RESUME/protocol.txt"
echo "RESUME_DIR=$RESUME"

run_arm() {
  local arm="$1" work="$RESUME/$1" bin="$BUILD/build_$1/$TARGET"
  local graph="$work/$arm.graph" log="$work/$arm.build.log" times="$work/$arm.time.txt" rc name filepath
  local -a output_env=() unset_env=()
  mkdir "$work"
  for name in "${OUT_VARS[@]}"; do
    unset_env+=( -u "$name" )
    if [[ "$arm" == *_on ]]; then
      case "$name" in
        R86_COUNTER_OUT) filepath="$work/$arm.counters.jsonl";;
        R86_LEAF_SIZE_OUT) filepath="$work/$arm.leaf_sizes.out";;
        *) filepath="$work/$arm.${name}.out";;
      esac
      output_env+=( "$name=$filepath" )
      echo "$name=$filepath" >> "$work/output_env_paths.txt"
    fi
  done
  echo "===== NATIVE_10K_START arm=$arm ====="
  if [[ "$arm" == *_on ]]; then
    cat "$work/output_env_paths.txt"
  else
    echo "COUNTERS_OFF_OUTPUT_ENV_CLEARED=${OUT_VARS[*]}"
  fi
  set +e
  (
    cd "$work" || exit 3
    /usr/bin/time -o "$times" -f 'WALL_S=%e PEAK_RSS_KiB=%M TIME_CHILD_STATUS=%x' \
      timeout --signal=TERM --kill-after=5s 900s \
      env "${unset_env[@]}" PARLAY_NUM_THREADS=1 OMP_NUM_THREADS=1 \
        OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 \
        "${output_env[@]}" \
      taskset -c 0 "$bin" \
        -base_path "$PREFIX" -graph_outfile "$graph" \
        -num_clusters 2 -cluster_size 1024 -top_level_leaders 100 \
        -fanout_scheme 10,3,1 -mst_deg 2 -prune 1 -prune_all 1 \
        -prune_degree 64 -table_size 160 -hash_bits 12 -alpha 1.1 -k 0 \
        > "$log" 2>&1
  )
  rc=$?
  set -e
  printf 'NATIVE_EXIT_STATUS=%d\n' "$rc" > "$work/run_status.txt"
  if (( rc != 0 )); then
    echo "NATIVE_10K_FAILED=$arm NATIVE_EXIT_STATUS=$rc LOG=$log"
    tail -n 30 "$log" || true
    exit 5
  fi
  [[ -s "$graph" ]] || { echo "FAIL_EMPTY_GRAPH=$arm"; exit 5; }
  sha256sum "$graph" > "$graph.sha256"
  sha256sum "$log" > "$log.sha256"
  if [[ "$arm" == *_on ]]; then
    for name in "${OUT_VARS[@]}"; do
      filepath="$(sed -n "s/^${name}=//p" "$work/output_env_paths.txt")"
      [[ -n "$filepath" && -s "$filepath" ]] || {
        echo "FAIL_MISSING_OR_EMPTY_OUTPUT=$arm/$name ($filepath)"; exit 5;
      }
      sha256sum "$filepath" >> "$work/output_files.sha256"
      printf 'OUTPUT_WRITTEN %s BYTES=%s\n' "$name" "$(stat -c %s "$filepath")"
    done
  fi
  echo "NATIVE_10K_COMPLETED=$arm GRAPH_SHA=$(awk '{print $1}' "$graph.sha256")"
  grep -E 'Total buckets:|Total points:|comparisons during clustering:|R86_' "$log" | tail -n 30 || true
}

# Keep the successful original stock_off untouched; only resume the 3 missing arms.
run_arm stock_on
run_arm h17_off
run_arm h17_on

python3 - "$RUN" "$RESUME" <<'PY'
import csv,hashlib,json,re,sys
from pathlib import Path
run,resume=map(Path,sys.argv[1:3]); rows=[]
fields=['arm','source','P1_buckets','P2_buckets','P1_total_points','P2_total_points',
  'P1_WP_cumulative','P2_WP_cumulative','P2_WP_increment','graph_sha256',
  'wall_s','peak_rss_KiB','output_env_paths','output_file_sizes']
for arm in ('stock_off','stock_on','h17_off','h17_on'):
  work=run/'stock_off' if arm=='stock_off' else resume/arm
  raw=(work/f'{arm}.build.log').read_text(errors='replace')
  def two(p):
    hits=list(map(int,re.findall(p,raw)))
    if len(hits)!=2: raise ValueError((arm,p,hits))
    return hits
  b=two(r'Total buckets:\s*(\d+)'); p=two(r'Total points:\s*(\d+)')
  w=two(r'# of comparisons during clustering:\s*(\d+)')
  t=(work/f'{arm}.time.txt').read_text(errors='replace')
  wall=re.search(r'WALL_S=([\d.]+)',t); rss=re.search(r'PEAK_RSS_KiB=(\d+)',t)
  graph=work/f'{arm}.graph'; sha=hashlib.sha256(graph.read_bytes()).hexdigest()
  envs={}
  cfg=work/'output_env_paths.txt'
  if cfg.exists():
    for line in cfg.read_text().splitlines():
      name,path=line.split('=',1); envs[name]=path
  sizes={name:Path(path).stat().st_size for name,path in envs.items()}
  rows.append(dict(arm=arm,source='v1_0_existing' if arm=='stock_off' else 'v1_2_resume',
    P1_buckets=b[0],P2_buckets=b[1],P1_total_points=p[0],P2_total_points=p[1],
    P1_WP_cumulative=w[0],P2_WP_cumulative=w[1],P2_WP_increment=w[1]-w[0],
    graph_sha256=sha,wall_s=wall.group(1) if wall else '',
    peak_rss_KiB=rss.group(1) if rss else '',
    output_env_paths=json.dumps(envs),output_file_sizes=json.dumps(sizes)))
by={x['arm']:x for x in rows}
check_fields=['P1_buckets','P2_buckets','P1_total_points','P2_total_points','P1_WP_cumulative','P2_WP_cumulative']
comparisons={f'{a}_vs_{b}':{k:by[a][k]==by[b][k] for k in check_fields}
 for a,b in [('stock_off','stock_on'),('h17_off','h17_on')]}
summary=dict(status='COLLECTED_NOT_G2_PASS',g2_pass=False,independent_graph_audit=False,
  native_work_counter_invariants_verified=False,source='R86 HW85 G2 native SIFT10K',
  runs=rows,off_on_partition_comparison=comparisons,
  note='Collector completed. Inspect every output file and independent graph validity before G2 decision.')
(resume/'summary.json').write_text(json.dumps(summary,indent=2,ensure_ascii=False)+'\n')
with (resume/'summary.csv').open('w',newline='') as f:
  writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader();writer.writerows(rows)
print('===== ON/OFF PARTITION DIAGNOSTIC =====')
print(json.dumps(comparisons,indent=2))
print('G2_NATIVE_10K_V1_2_COMPLETED_NOT_G2_PASS')
print('SUMMARY_JSON='+str(resume/'summary.json'))
print('SUMMARY_CSV='+str(resume/'summary.csv'))
PY
