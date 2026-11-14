#!/usr/bin/env bash
# H24-R0e | Real SIFT1M Dense LOW/HIGH scaling test.
# Does not implement STH. Does not edit H17--H23 or source code.
# Requires prior H24-R0d kit + fgraft checkout + fbin reader patch.
set -euo pipefail

PROJECT="${HOME}/ann-task-a"
KIT="${PROJECT}/experiments/H24/kit"
GRAFT="${PROJECT}/experiments/H24/vendor/graft-ann"
BASE="${PROJECT}/data/sift1m.fbin"
QUERY="${PROJECT}/data/sift1m_queries.fbin"
SEED=42
L=1200
NQUERY=1000
MODE=plan
EXPECTED_REV='a032c2d6cfb2c087d3b8abca028c745186501976'

usage() {
  cat <<'HELP'
SIFT1M Dense pair, isolated H24-R0e experiment (4 BUILD workers, 1 SEARCH worker).
Usage:
  bash h24_r0e_run_sift1m.sh --mode plan
  bash h24_r0e_run_sift1m.sh --mode run
Optional: --seed 42 --L 1200 --nquery 1000

LOW m=3 / HIGH m=5, C=200, degree R=64, alpha=1, spine HSP3.
This is a Dense baseline scaling test, not an STH/rescue test.
Source SIFT1M full base is 1,000,000 x 128 float32 (.fbin).
HELP
}
while (($#)); do
  case "$1" in
    --mode) MODE="${2:?}"; shift 2;;
    --seed) SEED="${2:?}"; shift 2;;
    --L) L="${2:?}"; shift 2;;
    --nquery) NQUERY="${2:?}"; shift 2;;
    --help|-h) usage; exit 0;;
    *) echo "Unknown parameter: $1" >&2; usage; exit 2;;
  esac
done
[[ "$MODE" == plan || "$MODE" == run ]] || { echo 'Need --mode plan|run' >&2; exit 2; }
for value in "$SEED" "$L" "$NQUERY"; do
  [[ "$value" =~ ^[0-9]+$ ]] || { echo "Invalid positive integer: $value" >&2; exit 2; }
done
(( L >= 5 && NQUERY >= 100 && NQUERY <= 10000 )) || { echo 'Invalid L or nquery' >&2; exit 2; }

NBASE=1000000
SAMPLE="${PROJECT}/experiments/H24/datasets/sift_subset_${NBASE}_q${NQUERY}_seed${SEED}_l2"
OUT="${PROJECT}/experiments/H24/dense_pair_n${NBASE}_q${NQUERY}_seed${SEED}_L${L}_m3v5_HSP3"

echo '=== H24 R0e | SIFT1M FULL BASE, no STH ==='
printf 'Mode=%s\nInput base=%s\nInput queries=%s\nDataset cache=%s\nResults=%s\n' \
  "$MODE" "$BASE" "$QUERY" "$SAMPLE" "$OUT"
printf 'Controls: seed=%s, L=%s, m=(3,5), C=200, R=64, HSP3, 4 BUILD workers, 1 SEARCH worker\n' "$SEED" "$L"
if [[ "$MODE" == plan ]]; then
  echo 'PLAN ONLY: no data preparation, no ANN BUILD, no changes to any files.'
  echo 'Note: exact top-10 against the full 1M base will be recomputed for external queries.'
  exit 0
fi

[[ -f "$BASE" && -f "$QUERY" ]] || { echo 'Missing SIFT .fbin inputs' >&2; exit 2; }
for src in h24_prepare_real_subset.py h24_r0d_dense_pair_gate.py; do
  [[ -f "$KIT/$src" ]] || { echo "Missing H24 kit file: $KIT/$src" >&2; exit 2; }
done
[[ -x "$GRAFT/src/fg" ]] || { echo "Missing compiled fgraft binary: $GRAFT/src/fg" >&2; exit 2; }
[[ -d "$GRAFT/.git" ]] || { echo "Missing git checkout: $GRAFT" >&2; exit 2; }
REV=$(git -C "$GRAFT" rev-parse HEAD)
[[ "$REV" == "$EXPECTED_REV" ]] || {
  echo "STOP: fgraft revision $REV differs from the H24 200k reference $EXPECTED_REV" >&2
  echo 'Do not compare unmatched source revisions.' >&2; exit 2;
}
echo "Verified fgraft commit: $REV"

# Check .fbin header and exact file sizes. No vector data is copied during this check.
python3 - "$BASE" "$QUERY" "$NQUERY" <<'PY'
import pathlib, struct, sys
base,query=(pathlib.Path(s) for s in sys.argv[1:3])
nquery=int(sys.argv[3])
for p, expected in [(base,1000000),(query,None)]:
    with p.open('rb') as f: buf=f.read(8)
    if len(buf)!=8: raise SystemExit(f'Invalid fbin header: {p}')
    n,d=struct.unpack('<ii',buf)
    if (expected and n!=expected) or d!=128 or p.stat().st_size != 8+n*d*4:
        raise SystemExit(f'Invalid SIFT fbin: path={p} n={n} d={d} size={p.stat().st_size}')
    if p==query and n < nquery:
        raise SystemExit(f'Too few queries: {n} < {nquery}')
    print(f'Input verified: {p.name}: {n} x {d}')
PY
python3 -c 'import numpy' || { echo 'NumPy missing; activate ~/ann-task-a/.venv' >&2; exit 2; }

# This builder has a large temporary n*C heap; refuse when RAM/disk are scarce.
AVAIL_KB=$(awk '/^MemAvailable:/ {print $2}' /proc/meminfo)
FREE_KB=$(df -Pk "${PROJECT}" | awk 'END{print $4}')
if (( AVAIL_KB < 5*1024*1024 )); then
  echo "STOP: available RAM <5 GiB (MemAvailable=${AVAIL_KB} KiB). Close apps first." >&2; exit 2
fi
if (( FREE_KB < 3*1024*1024 )); then
  echo "STOP: free disk <3 GiB (${FREE_KB} KiB)." >&2; exit 2
fi
echo "Resources: available RAM ~$((AVAIL_KB/1024)) MiB; disk free ~$((FREE_KB/1024)) MiB"

export OMP_NUM_THREADS=4 OPENBLAS_NUM_THREADS=4 MKL_NUM_THREADS=4 OMP_DYNAMIC=FALSE
if [[ -f "$SAMPLE/manifest.json" ]]; then
  python3 - "$SAMPLE" "$BASE" "$QUERY" "$NQUERY" "$SEED" <<'PY'
import json,pathlib,sys
folder,base,query,nquery,seed=sys.argv[1:]
p=pathlib.Path(folder)
man=json.loads((p/'manifest.json').read_text())
expect={'n':1000000,'nq':int(nquery),'d':128,'seed':int(seed),'metric':'l2',
        'base_source':str(pathlib.Path(base).resolve()),'query_source':str(pathlib.Path(query).resolve())}
for k,v in expect.items():
    if man.get(k)!=v: raise SystemExit(f'Unsafe cached-subset mismatch for {k}: {man.get(k)} vs {v}')
for fn in ('X.npy','Q.npy','gold.npy'):
    if not (p/fn).is_file(): raise SystemExit(f'Missing cached subset file: {p/fn}')
print('Reusing matching dataset manifest:',p/'manifest.json')
PY
else
  echo 'Preparing full 1M NPY with fresh exact GT (non-BUILD preprocessing).'
  python3 "$KIT/h24_prepare_real_subset.py" \
    --base "$BASE" --query "$QUERY" --out "$SAMPLE" \
    --nbase "$NBASE" --nquery "$NQUERY" --seed "$SEED" --metric l2
fi

if [[ -e "$OUT/gate_results.json" || -e "$OUT/dense_low_m3_seed${SEED}.log" || -e "$OUT/dense_high_m5_seed${SEED}.log" ]]; then
  echo "STOP: logs/results already exist at $OUT; inspect rather than overwrite." >&2; exit 2
fi

echo 'Starting full SIFT1M native Dense baseline pair.'
python3 "$KIT/h24_r0d_dense_pair_gate.py" --mode run \
  --binary "$GRAFT/src/fg" \
  --data "$SAMPLE/X.npy" --queries "$SAMPLE/Q.npy" --gold "$SAMPLE/gold.npy" \
  --metric l2 --out "$OUT" --seeds "$SEED" --threads 4 \
  --L "$L" --m-low 3 --m-high 5 --C 200 --R 64 --alpha 1.0 \
  --spine 3 --spine-s 0 --spine-cap 16 --spine-repair 1

echo
printf 'DONE: %s\n' "$OUT/gate_results.json"
echo 'Read result with:'
printf 'cat %q\n' "$OUT/gate_results.json"
