#!/usr/bin/env bash
# R86 HW85 G2 10K - resume after missing R86_COUNTER_OUT in collector v1.0.
# Never modifies old source, binaries, old stock_off graph, or failed stock_on logs.
# Does NOT assert G2 PASS; only collects evidence.
set -Eeuo pipefail

ROOT="$HOME/ann-task-a/experiments/R86/gates"
RUN="$ROOT/g2_hw85_native10k_JWuLB9"
BUILD="$ROOT/highway_r85_four_binary_jvYREW"
MANIFEST="$BUILD/four_binary_manifest.json"
SOURCE_SHA="$BUILD/source_sha256.txt"
TARGET="algorithms/PipNN/neighbors-pipnn_FLOAT_T_EUCLIDEAN"
PREFIX="$RUN/sift10k_prefix.fbin"
EXPECT_PREFIX="94320c4336a35f046de768a24ada57aa8998f511df9aa2a7c72fe9ed8c67c1f5"
EXPECT_STOCK_OFF_GRAPH="59dd18da46ebb88604de4aa0d253df36b65ca5965de80af2f616d5f119a637a9"

for tool in python3 sha256sum awk grep env taskset timeout date; do
  command -v "$tool" >/dev/null || { echo "PREFLIGHT_MISSING_TOOL=$tool"; exit 3; }
done
[[ -x /usr/bin/time ]] || { echo 'PREFLIGHT_MISSING_/usr/bin/time'; exit 3; }
[[ -s "$PREFIX" && -s "$MANIFEST" && -s "$SOURCE_SHA" ]] || {
  echo "PREFLIGHT_MISSING_PREVIOUS_SESSION_OR_MANIFEST"; exit 3;
}
[[ -s "$RUN/stock_off/stock_off.graph" && -s "$RUN/stock_off/stock_off.build.log" ]] || {
  echo 'PREFLIGHT_STOCK_OFF_EVIDENCE_MISSING'; exit 3;
}
[[ -s "$RUN/stock_on/stock_on.build.log" ]] || {
  echo 'PREFLIGHT_FAILED_STOCK_ON_LOG_MISSING'; exit 3;
}

sha_gate() {
  local path="$1" sha="$2" label="$3" actual
  [[ -f "$path" ]] || { echo "PREFLIGHT_MISSING_$label=$path"; exit 3; }
  actual="$(sha256sum "$path" | awk '{print $1}')"
  [[ "$actual" == "$sha" ]] || { echo "PREFLIGHT_SHA_MISMATCH_$label expected=$sha actual=$actual"; exit 3; }
  echo "SHA_PASS_$label=$actual"
}

echo '===== PINNED PREFLIGHT / READ-ONLY VERIFICATION ====='
sha_gate "$PREFIX" "$EXPECT_PREFIX" SIFT10K_PREFIX
sha_gate "$RUN/stock_off/stock_off.graph" "$EXPECT_STOCK_OFF_GRAPH" PREVIOUS_STOCK_OFF_GRAPH
( cd / && sha256sum -c "$SOURCE_SHA" ) || { echo 'PREFLIGHT_SOURCE_DRIFT'; exit 3; }

python3 - "$MANIFEST" "$BUILD" <<'PY'
import hashlib,json,sys
from pathlib import Path
p,root=Path(sys.argv[1]),Path(sys.argv[2])
m=json.loads(p.read_text())
assert m.get('status')=='FOUR_BINARIES_BUILT_NOT_VALIDATED'
assert m.get('highway_rev')=='6bc2d47793bae9c521fb4150936669647700765d'
assert m.get('control_decision')=='CONTROL_PASS_MATCH_STABLE'
assert set(m['binaries'])=={'stock_off','stock_on','h17_off','h17_on'}
expected={
 'stock_off':'aa2d174ed063070045f1fbbc8051b1d97b851168b2f3bf53ee32215a867583be',
 'stock_on':'396ef852992428cd3f935bcb33eeeeacc1bae565fbc4a441c1fa9d19720122ff',
 'h17_off':'5f673586210f93b424fc81791ec7873cb74600843b5004c0a4aaaf32bf936297',
 'h17_on':'ef707479be221cb7a3c6257298d22f614678878f0a7bfc724dc8b28fabdd21c4'
}
for arm,sha in expected.items():
 item=m['binaries'][arm]
 assert item['sha256']==sha and bool(item['COUNTERS_ON'])==(arm.endswith('_on'))
 assert bool(item['H17'])==(arm.startswith('h17'))
 path=Path(item['path']).resolve(strict=True)
 assert path==root.resolve()/f'build_{arm}/algorithms/PipNN/neighbors-pipnn_FLOAT_T_EUCLIDEAN'
 assert hashlib.sha256(path.read_bytes()).hexdigest()==sha
 print('BINARY_PIN_PASS',arm,sha)
PY

# The v1.0 collector failed because R86_COUNTER_OUT was not set.
# This resume explicitly sets an ABSOLUTE file path for *_on only.
[[ "$(grep -c 'R86 requires absolute path env R86_COUNTER_OUT' "$RUN/stock_on/stock_on.build.log")" -ge 1 ]] || {
  echo 'PREFLIGHT_UNEXPECTED_FAILURE_ORIGINAL_CAUSE'; exit 3;
}

RESUME="$RUN/resume_v1_1"
[[ ! -e "$RESUME" ]] || { echo "PREFLIGHT_RESUME_OUTPUT_ALREADY_EXISTS=$RESUME"; exit 3; }
mkdir "$RESUME"
sha256sum "${BASH_SOURCE[0]}" > "$RESUME/resume_script.sha256"
{
  echo "SOURCE_SESSION=$RUN"
  echo "PREVIOUS_STOCK_OFF_GRAPH_SHA=$EXPECT_STOCK_OFF_GRAPH"
  echo 'PREVIOUS_STOCK_ON_ABORT_REASON=MISSING_R86_COUNTER_OUT'
  echo 'REPAIR=SET_ABSOLUTE_R86_COUNTER_OUT_FOR_ON_ARMS'
  echo 'PROTOCOL=1 THREAD; CPU0; C160 K1024 N2; SIFT10K PREFIX PINNED'
  echo 'G2_PASS=FALSE (collector only)'
  echo "START_UTC=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
} > "$RESUME/protocol.txt"
echo "RESUME_DIR=$RESUME"

run_arm() {
  local arm="$1" bin work graph log times counter rc
  bin="$BUILD/build_$arm/$TARGET"
  work="$RESUME/$arm"
  mkdir "$work"
  graph="$work/$arm.graph"
  log="$work/$arm.build.log"
  times="$work/$arm.time.txt"
  counter="$work/$arm.counters.jsonl"
  echo "===== START_RESUME arm=$arm ====="
  echo "COUNTERS_ENV=$([[ "$arm" == *_on ]] && echo "$counter" || echo '<OFF_UNSET>')"
  set +e
  (
    cd "$work" || exit 3
    if [[ "$arm" == *_on ]]; then
      /usr/bin/time -o "$times" -f 'WALL_S=%e PEAK_RSS_KiB=%M EXIT_CODE=%x' \
        timeout --signal=TERM --kill-after=5s 900s \
        env PARLAY_NUM_THREADS=1 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 \
            MKL_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 \
            R86_COUNTER_OUT="$counter" \
        taskset -c 0 "$bin" \
          -base_path "$PREFIX" -graph_outfile "$graph" \
          -num_clusters 2 -cluster_size 1024 -top_level_leaders 100 \
          -fanout_scheme 10,3,1 -mst_deg 2 -prune 1 -prune_all 1 \
          -prune_degree 64 -table_size 160 -hash_bits 12 -alpha 1.1 -k 0 \
          > "$log" 2>&1
    else
      /usr/bin/time -o "$times" -f 'WALL_S=%e PEAK_RSS_KiB=%M EXIT_CODE=%x' \
        timeout --signal=TERM --kill-after=5s 900s \
        env -u R86_COUNTER_OUT PARLAY_NUM_THREADS=1 OMP_NUM_THREADS=1 \
            OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 \
        taskset -c 0 "$bin" \
          -base_path "$PREFIX" -graph_outfile "$graph" \
          -num_clusters 2 -cluster_size 1024 -top_level_leaders 100 \
          -fanout_scheme 10,3,1 -mst_deg 2 -prune 1 -prune_all 1 \
          -prune_degree 64 -table_size 160 -hash_bits 12 -alpha 1.1 -k 0 \
          > "$log" 2>&1
    fi
  )
  rc=$?
  set -e
  echo "NATIVE_EXIT_STATUS=$rc" > "$work/run_status.txt"
  if ((rc != 0)); then
    echo "RESUME_ARM_FAILED=$arm NATIVE_EXIT_STATUS=$rc LOG=$log"
    tail -n 40 "$log" || true
    exit 5
  fi
  [[ -s "$graph" ]] || { echo "RESUME_EMPTY_GRAPH=$arm"; exit 5; }
  sha256sum "$graph" > "$graph.sha256"
  sha256sum "$log" > "$log.sha256"
  if [[ "$arm" == *_on ]]; then
    [[ -s "$counter" ]] || { echo "RESUME_COUNTER_FILE_MISSING_OR_EMPTY=$counter"; exit 5; }
    sha256sum "$counter" > "$counter.sha256"
    echo "COUNTER_FILE_WRITTEN=$counter BYTES=$(stat -c %s "$counter")"
  fi
  echo "RESUME_ARM_COMPLETED=$arm GRAPH_SHA=$(awk '{print $1}' "$graph.sha256")"
  grep -E 'Total buckets:|Total points:|comparisons during clustering:|R86_' "$log" | tail -n 25 || true
}

# Do NOT re-run original stock_off; retain the successful v1.0 evidence.
run_arm stock_on
run_arm h17_off
run_arm h17_on

python3 - "$RUN" "$RESUME" <<'PY'
import csv,hashlib,json,re,sys
from pathlib import Path
run,resume=map(Path,sys.argv[1:3]); rows=[]
fields=['arm','source','P1_buckets','P2_buckets','P1_total_points','P2_total_points',
        'P1_WP_cumulative','P2_WP_cumulative','P2_WP_increment','graph_sha256',
        'wall_s','peak_rss_KiB','counter_file','counter_bytes']
for arm in ('stock_off','stock_on','h17_off','h17_on'):
    work=(run/'stock_off') if arm=='stock_off' else (resume/arm)
    log=(work/f'{arm}.build.log').read_text(errors='replace')
    def two(pattern):
        xs=[int(x) for x in re.findall(pattern,log)]
        assert len(xs)==2, (arm,pattern,xs)
        return xs
    b=two(r'Total buckets:\s*(\d+)')
    n=two(r'Total points:\s*(\d+)')
    w=two(r'# of comparisons during clustering:\s*(\d+)')
    t=(work/f'{arm}.time.txt').read_text()
    wall=re.search(r'WALL_S=([0-9.]+)',t)
    rss=re.search(r'PEAK_RSS_KiB=(\d+)',t)
    graph=work/f'{arm}.graph'
    sha=hashlib.sha256(graph.read_bytes()).hexdigest()
    counter=work/f'{arm}.counters.jsonl'
    rows.append(dict(arm=arm,source='v1_0_original_success' if arm=='stock_off' else 'v1_1_resume',
        P1_buckets=b[0],P2_buckets=b[1],P1_total_points=n[0],P2_total_points=n[1],
        P1_WP_cumulative=w[0],P2_WP_cumulative=w[1],P2_WP_increment=w[1]-w[0],
        graph_sha256=sha,wall_s=wall.group(1) if wall else '',
        peak_rss_KiB=rss.group(1) if rss else '',
        counter_file=str(counter) if counter.is_file() else '',
        counter_bytes=counter.stat().st_size if counter.is_file() else ''))
by={x['arm']:x for x in rows}
cf=['P1_buckets','P2_buckets','P1_total_points','P2_total_points','P1_WP_cumulative','P2_WP_cumulative']
comp={f'{a}_vs_{b}':{k:by[a][k]==by[b][k] for k in cf}
      for a,b in [('stock_off','stock_on'),('h17_off','h17_on')]}
summary=dict(status='G2_NATIVE_10K_RESUMED_AUDIT_REQUIRED',G2_pass=False,
    independently_audited_graph=False,validated_counter_invariants=False,
    runs=rows,off_on_partition_comparison=comp,
    note='Completed 4 arms using original stock_off and resumed three others; NOT G2 PASS.')
(resume/'summary.json').write_text(json.dumps(summary,indent=2,ensure_ascii=False)+'\n')
with (resume/'summary.csv').open('w',newline='') as f:
    writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader();writer.writerows(rows)
print('===== OFF/ON PARTITION COMPARISON =====')
print(json.dumps(comp,indent=2))
print('G2_NATIVE_10K_RESUME_COMPLETED_NOT_G2_PASS')
print('SUMMARY_JSON='+str(resume/'summary.json'))
print('SUMMARY_CSV='+str(resume/'summary.csv'))
PY
