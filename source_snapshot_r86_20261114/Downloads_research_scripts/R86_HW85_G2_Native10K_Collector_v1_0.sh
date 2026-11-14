#!/usr/bin/env bash
# R86 Highway R85 / G2: native 10K ON/OFF evidence collector.
# This DOES NOT certify G2. Safe: no old source/build modification, no graph overwrite.
set -Eeuo pipefail

ROOT="$HOME/ann-task-a/experiments"
GATES="$ROOT/R86/gates"
BUILD_SESSION="$GATES/highway_r85_four_binary_jvYREW"
MANIFEST="$BUILD_SESSION/four_binary_manifest.json"
SOURCE_SHA="$BUILD_SESSION/source_sha256.txt"
BASE100="$HOME/ann-task-a/data/sift100k.fbin"
BASE100_SHA=e50ff1bc34bcc6d1c97dd001023c09a666971cde64605cc06671ed8a8ff1ed12
HW85_COMMIT=6bc2d47793bae9c521fb4150936669647700765d
TARGET=neighbors-pipnn_FLOAT_T_EUCLIDEAN

need() { command -v "$1" >/dev/null || { echo "FAIL_MISSING_TOOL=$1"; exit 3; }; }
for cmd in python3 sha256sum awk grep tee mktemp taskset timeout env git; do need "$cmd"; done
[[ -x /usr/bin/time ]] || { echo "FAIL_MISSING_/usr/bin/time"; exit 3; }
[[ -f "$MANIFEST" && -f "$SOURCE_SHA" && -f "$BASE100" ]] || {
  echo 'FAIL_MISSING_MANIFEST_OR_SOURCE_MANIFEST_OR_BASE'; exit 3;
}

printf '===== PINNED PREFLIGHT =====\n'
actual_base_sha="$(sha256sum "$BASE100" | awk '{print $1}')"
[[ "$actual_base_sha" == "$BASE100_SHA" ]] || {
  echo "FAIL_BASE_SHA expected=$BASE100_SHA actual=$actual_base_sha"; exit 3;
}
sha256sum -c "$SOURCE_SHA" || { echo 'FAIL_R86_SOURCE_CHANGED'; exit 3; }
python3 - "$MANIFEST" "$BUILD_SESSION" "$HW85_COMMIT" <<'PY'
import hashlib,json,sys
from pathlib import Path
manifest, session, hw = Path(sys.argv[1]), Path(sys.argv[2]).resolve(), sys.argv[3]
doc = json.loads(manifest.read_text())
assert doc.get('status')=='FOUR_BINARIES_BUILT_NOT_VALIDATED', 'MANIFEST_BAD_STATUS'
assert doc.get('highway_rev')==hw, 'HIGHWAY_MISMATCH'
assert doc.get('control_decision')=='CONTROL_PASS_MATCH_STABLE', 'CONTROL_PRECONDITION_FAIL'
arms=['stock_off','stock_on','h17_off','h17_on']
assert set(doc.get('binaries',{}))==set(arms), 'MANIFEST_ARMS_MISMATCH'
expected={
 'stock_off':'aa2d174ed063070045f1fbbc8051b1d97b851168b2f3bf53ee32215a867583be',
 'stock_on':'396ef852992428cd3f935bcb33eeeeacc1bae565fbc4a441c1fa9d19720122ff',
 'h17_off':'5f673586210f93b424fc81791ec7873cb74600843b5004c0a4aaaf32bf936297',
 'h17_on':'ef707479be221cb7a3c6257298d22f614678878f0a7bfc724dc8b28fabdd21c4',
}
for arm in arms:
 entry=doc['binaries'][arm]
 path=Path(entry['path']).resolve(strict=True)
 assert path==session/f'build_{arm}/algorithms/PipNN/neighbors-pipnn_FLOAT_T_EUCLIDEAN',f'BIN_PATH_MISMATCH:{arm}'
 assert entry['sha256']==expected[arm],f'MANIFEST_SHA_MISMATCH:{arm}'
 assert hashlib.sha256(path.read_bytes()).hexdigest()==expected[arm],f'ACTUAL_BIN_SHA_MISMATCH:{arm}'
 assert bool(entry.get('H17')) == arm.startswith('h17'), f'H17_FLAG_MISMATCH:{arm}'
 assert bool(entry.get('COUNTERS_ON')) == arm.endswith('on'), f'COUNTER_FLAG_MISMATCH:{arm}'
 print('PIN_PASS',arm,expected[arm])
print('FOUR_BINARIES_MANIFEST_AND_SHA_PASS')
PY

mkdir -p "$GATES"
OUT="$(mktemp -d "$GATES/g2_hw85_native10k_XXXXXX")"
echo "SESSION=$OUT"
# All runs use a read-only prefix of the exact already-pinned SIFT100K dataset.
# For fbin: little-endian uint32 [N, D], followed by 100000 x 128 float32.
python3 - "$BASE100" "$OUT/sift10k_prefix.fbin" "$BASE100_SHA" <<'PY'
from pathlib import Path
import hashlib,struct,sys
src,dst,sha=Path(sys.argv[1]),Path(sys.argv[2]),sys.argv[3]
assert hashlib.sha256(src.read_bytes()).hexdigest()==sha, 'SOURCE_DATA_SHA_CHANGED'
with src.open('rb') as f:
 header=f.read(8)
 assert len(header)==8, 'FBIN_HEADER_TOO_SHORT'
 n,d=struct.unpack('<II',header)
 assert (n,d)==(100000,128), f'UNEXPECTED_FBIN_HEADER={(n,d)}'
 assert src.stat().st_size == 8+n*d*4, 'FBIN_SIZE_MISMATCH'
 with dst.open('xb') as g:
  g.write(struct.pack('<II',10000,d))
  to_copy=10000*d*4
  while to_copy:
   chunk=f.read(min(to_copy,1024*1024))
   assert chunk, 'UNEXPECTED_EOF'
   g.write(chunk)
   to_copy-=len(chunk)
assert dst.stat().st_size==8+10000*128*4, 'PREFIX_FILE_SIZE_BAD'
print('SIFT10K_PREFIX_CREATED',dst)
print('PREFIX_SHA256='+hashlib.sha256(dst.read_bytes()).hexdigest())
PY
sha256sum "$OUT/sift10k_prefix.fbin" > "$OUT/sift10k_prefix.fbin.sha256"
cp "$MANIFEST" "$OUT/input_four_binary_manifest.json"
sha256sum "${BASH_SOURCE[0]}" > "$OUT/script_sha256.txt"
{
 printf 'START_UTC=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
 printf 'SOURCE_BASE100=%s\nSOURCE_SHA256=%s\n' "$BASE100" "$BASE100_SHA"
 printf 'PREFIX10K=%s\n' "$OUT/sift10k_prefix.fbin"
 printf 'BUILD_SESSION=%s\n' "$BUILD_SESSION"
 printf '%s\n' 'PROTOCOL=Stock/H17, C160 K1024 N2, 1 thread pinned to CPU0, identical CLI'
 printf '%s\n' 'OFF=for basic wall/RSS diagnostic only; ON=for instrumented counter audit'
 printf '%s\n' 'NO_G1_OR_G2_PASS_CLAIMED'
} > "$OUT/protocol.txt"

# Runs are independent and never write into the source or earlier build dirs.
for ARM in stock_off stock_on h17_off h17_on; do
  BIN="$BUILD_SESSION/build_$ARM/algorithms/PipNN/$TARGET"
  WORK="$OUT/$ARM"
  mkdir -p "$WORK"
  GRAPH="$WORK/$ARM.graph"
  LOG="$WORK/$ARM.build.log"
  TIMES="$WORK/$ARM.time.txt"
  echo "===== G2_NATIVE_10K_START arm=$ARM ====="
  (
    cd "$WORK"
    /usr/bin/time -o "$TIMES" -f 'WALL_S=%e PEAK_RSS_KiB=%M EXIT_CODE=%x' \
      timeout --signal=TERM --kill-after=5s 900s \
      env PARLAY_NUM_THREADS=1 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 \
          MKL_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 \
      taskset -c 0 "$BIN" \
        -base_path "$OUT/sift10k_prefix.fbin" \
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
  ) || { echo "NATIVE_10K_BUILD_FAILED=$ARM LOG=$LOG"; exit 5; }
  [[ -s "$GRAPH" ]] || { echo "FAIL_EMPTY_GRAPH=$ARM"; exit 5; }
  sha256sum "$GRAPH" > "$GRAPH.sha256"
  sha256sum "$LOG" > "$LOG.sha256"
  echo "G2_NATIVE_10K_RUN_COMPLETED=$ARM GRAPH_SHA=$(awk '{print $1}' "$GRAPH.sha256")"
  echo "----- diagnostic markers $ARM -----"
  grep -E 'R86_|Total buckets:|Total points:|comparisons during clustering:|Average table size:|graph with|Graph has|Graph built in|WALL_S|PEAK_RSS' "$LOG" "$TIMES" | tail -n 45 || true
done

# Read stdout evidence. Parsing only; does not certify native leaf-counter invariants.
python3 - "$OUT" <<'PY'
import csv,hashlib,json,re,sys
from pathlib import Path
out=Path(sys.argv[1]); rows=[]
keys=['arm','P1_buckets','P2_buckets','P1_total_points','P2_total_points',
      'P1_WP_cumulative','P2_WP_cumulative','P2_WP_increment',
      'graph_sha256','log_sha256','wall_s','peak_rss_KiB','counter_json_stdout_lines']
for arm in ('stock_off','stock_on','h17_off','h17_on'):
 work=out/arm; p=work/f'{arm}.build.log'; text=p.read_text(errors='replace')
 def matches(pat): return [int(x) for x in re.findall(pat,text)]
 b=matches(r'Total buckets:\s*(\d+)')
 n=matches(r'Total points:\s*(\d+)')
 w=matches(r'# of comparisons during clustering:\s*(\d+)')
 assert len(b)==len(n)==len(w)==2, f'FAIL_EXPECTED_TWO_PASSES:{arm}:{len(b)},{len(n)},{len(w)}'
 # Collect standalone JSON events if ON prints any; not a claim they are complete.
 valid=[]
 for line in text.splitlines():
  if line.lstrip().startswith('{'):
   try:
    payload=json.loads(line)
    if isinstance(payload,dict):valid.append(payload)
   except json.JSONDecodeError:pass
 with (work/f'{arm}.stdout_json_objects.jsonl').open('w') as f:
  for obj in valid:f.write(json.dumps(obj,ensure_ascii=False)+'\n')
 time_text=(work/f'{arm}.time.txt').read_text()
 wall=re.search(r'WALL_S=([0-9.]+)',time_text)
 rss=re.search(r'PEAK_RSS_KiB=(\d+)',time_text)
 def sha(x):return hashlib.sha256(x.read_bytes()).hexdigest()
 row=dict(arm=arm,P1_buckets=b[0],P2_buckets=b[1],P1_total_points=n[0],P2_total_points=n[1],
          P1_WP_cumulative=w[0],P2_WP_cumulative=w[1],P2_WP_increment=w[1]-w[0],
          graph_sha256=sha(work/f'{arm}.graph'),log_sha256=sha(p),
          wall_s=float(wall.group(1)) if wall else None,
          peak_rss_KiB=int(rss.group(1)) if rss else None,
          counter_json_stdout_lines=len(valid))
 rows.append(row)
with (out/'summary.csv').open('w',newline='') as f:
 writer=csv.DictWriter(f,fieldnames=keys);writer.writeheader();writer.writerows(rows)
by={r['arm']:r for r in rows}
compare_fields=['P1_buckets','P2_buckets','P1_total_points','P2_total_points','P1_WP_cumulative','P2_WP_cumulative']
comparisons={
 'stock_off_vs_on':{k:by['stock_off'][k]==by['stock_on'][k] for k in compare_fields},
 'h17_off_vs_on':{k:by['h17_off'][k]==by['h17_on'][k] for k in compare_fields}
}
summary={'status':'NATIVE_10K_COMPLETED_G2_AUDIT_PENDING',
 'G2_pass':False,'graph_validity_independently_audited':False,
 'leaf_counter_invariants_independently_audited':False,
 'matched_Recall_evaluated':False,
 'note':'4 native graph BUILDs completed, SHA captured, partition comparisons summarized; NOT G2 PASS.',
 'runs':rows,'off_on_partition_comparison':comparisons}
(out/'summary.json').write_text(json.dumps(summary,indent=2,ensure_ascii=False)+'\n')
print('===== 10K OFF/ON PARTITION COMPARISON =====')
print(json.dumps(comparisons,indent=2))
print('G2_NATIVE_10K_COLLECTOR_COMPLETED_NOT_G2_PASS')
print('RESULT_DIR='+str(out))
print('SUMMARY_JSON='+str(out/'summary.json'))
print('SUMMARY_CSV='+str(out/'summary.csv'))
PY
