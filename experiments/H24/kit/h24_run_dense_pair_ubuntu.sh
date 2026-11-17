#!/usr/bin/env bash
# H24-R0d. Only runs when explicitly invoked with --base and --query.
# Creates a NEW isolated experiment folder; no writes into H17--H23.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT="${HOME}/ann-task-a"
BASE=''; QUERY=''; METRIC=l2; NBASE=50000; NQUERY=200; SEED=42
GRAFT_DIR=''; MODE=run
usage(){
  cat <<EOF
Usage: bash h24_run_dense_pair_ubuntu.sh --base /path/sift_base.fvecs --query /path/sift_query.fvecs [options]
Options:
  --project-dir DIR  (default ~/ann-task-a)
  --graft-dir DIR    (existing Graft fgraft clone; default project/experiments/H24/vendor/graft-ann)
  --metric l2|cos   (default l2, SIFT= l2)
  --nbase N         (default 50000, triage only)
  --nquery N        (default 200)
  --seed N          (default 42)
  --mode plan|run   (default run: prepares exact-GT subset and runs 2 native BUILDs)

No original SIFT1M gold file is reused: top-10 ground truth is regenerated for the subset.
If Graft is not present, run mode clones PUBLIC graft-ann fgraft into the H24 vendor folder.
EOF
}
while (($#)); do
  case "$1" in
    --base) BASE="${2:?}"; shift 2;;
    --query) QUERY="${2:?}"; shift 2;;
    --metric) METRIC="${2:?}"; shift 2;;
    --nbase) NBASE="${2:?}"; shift 2;;
    --nquery) NQUERY="${2:?}"; shift 2;;
    --seed) SEED="${2:?}"; shift 2;;
    --project-dir) PROJECT="${2:?}"; shift 2;;
    --graft-dir) GRAFT_DIR="${2:?}"; shift 2;;
    --mode) MODE="${2:?}"; shift 2;;
    --help|-h) usage; exit 0;;
    *) echo "Unknown argument $1" >&2; usage; exit 2;;
  esac
done
[[ -n "$BASE" && -n "$QUERY" ]] || { usage; exit 2; }
[[ "$METRIC" == l2 || "$METRIC" == cos ]] || { echo 'Invalid --metric' >&2; exit 2; }
[[ "$MODE" == run || "$MODE" == plan ]] || { echo 'Invalid --mode' >&2; exit 2; }
for f in "$BASE" "$QUERY"; do [[ -f "$f" ]] || { echo "Missing input $f" >&2; exit 2; }; done
[[ -f "$HERE/h24_prepare_real_subset.py" && -f "$HERE/h24_r0d_dense_pair_gate.py" ]] || {
  echo 'Put shell, h24_prepare_real_subset.py and h24_r0d_dense_pair_gate.py in the same directory.' >&2; exit 2;
}
PROJECT="$(realpath -m "$PROJECT")"
if [[ -z "$GRAFT_DIR" ]]; then GRAFT_DIR="$PROJECT/experiments/H24/vendor/graft-ann"; fi
GRAFT_DIR="$(realpath -m "$GRAFT_DIR")"
SAMPLE="$PROJECT/experiments/H24/datasets/sift_subset_${NBASE}_q${NQUERY}_seed${SEED}_${METRIC}"
OUT="$PROJECT/experiments/H24/dense_pair_n${NBASE}_q${NQUERY}_seed${SEED}_L240_m3v5_HSP3"
echo '=== H24 R0d reproducible paired Dense test ==='
printf 'Mode=%s\nProject=%s\nGraft=%s\nInput base=%s\nInput queries=%s\nOutput=%s\n' "$MODE" "$PROJECT" "$GRAFT_DIR" "$BASE" "$QUERY" "$OUT"
if [[ "$MODE" == plan ]]; then
  echo 'PLAN ONLY: no clone, compile, subset, or ANN BUILD.'
  exit 0
fi
python3 -c 'import numpy' || { echo 'Need NumPy: python3 -m pip install numpy' >&2; exit 2; }
if [[ ! -d "$GRAFT_DIR/.git" ]]; then
  [[ ! -e "$GRAFT_DIR" ]] || { echo "Refuse to overwrite non-git $GRAFT_DIR" >&2; exit 2; }
  mkdir -p "$(dirname "$GRAFT_DIR")"
  git clone --depth 1 --branch fgraft https://github.com/zevahcle/graft-ann.git "$GRAFT_DIR"
fi
[[ -f "$GRAFT_DIR/src/build.cpp" ]] || { echo 'graft source missing' >&2; exit 2; }
[[ "$(git -C "$GRAFT_DIR" branch --show-current)" == fgraft ]] || { echo 'Expected fgraft branch' >&2; exit 2; }
echo "Verified revision $(git -C "$GRAFT_DIR" rev-parse HEAD)"
if [[ ! -x "$GRAFT_DIR/src/fg" ]]; then
  echo 'Compiling ONLY the official fg graph builder, not HNSW.'
  make -C "$GRAFT_DIR/src" fg -j2
fi
if [[ ! -f "$SAMPLE/manifest.json" ]]; then
  python3 "$HERE/h24_prepare_real_subset.py" --base "$BASE" --query "$QUERY" \
    --out "$SAMPLE" --nbase "$NBASE" --nquery "$NQUERY" --seed "$SEED" --metric "$METRIC"
else
  echo "Reusing existing subset manifest at $SAMPLE/manifest.json"
fi
python3 "$HERE/h24_r0d_dense_pair_gate.py" --mode run \
  --binary "$GRAFT_DIR/src/fg" \
  --data "$SAMPLE/X.npy" --queries "$SAMPLE/Q.npy" --gold "$SAMPLE/gold.npy" \
  --metric "$METRIC" --out "$OUT" --seeds "$SEED" --threads 4 \
  --L 240 --m-low 3 --m-high 5 --C 200 --R 64 --alpha 1.0 \
  --spine 3 --spine-s 0 --spine-cap 16 --spine-repair 1
printf '\nDONE. Upload/review the report at:\n%s\n' "$OUT/gate_results.json"
