#!/usr/bin/env bash
# FGRAFT Phase 1 — paired repeated-build wall-clock on d0 (64 threads).
# Block = pairing unit; every system built once per block in a seeded random
# order; ratios by Hodges-Lehmann + exact Wilcoxon (bench/paired_stats.py).
#
#   FG=<graft-ann>/src/fg DATA=<dir> BLOCKS=10 bash d0_phase1_paired.sh glove
set -euo pipefail
DS="${1:-glove}"
FG="${FG:?set FG to the fg binary}"
DATA="${DATA:-data}"
BLOCKS="${BLOCKS:-10}"
OUT="results/phase1_${DS}.log"
mkdir -p results; : > "$OUT"

case "$DS" in
  glove) X=$DATA/glove_norm_X.npy; Q=$DATA/glove_norm_Q.npy; G=$DATA/glove_gold.npy; M=cos
         ARMS=("frozen_T32_ef600:--T 32 --harvest 600"
               "frozen_T16_ef400:--T 16 --harvest 400"
               "mut_T8_ef400_B8:--T 8 --harvest 400 --harvest-blocks 8"
               "mut_T8_ef400_B32:--T 8 --harvest 400 --harvest-blocks 32") ;;
  sift)  X=$DATA/sift_X.npy; Q=$DATA/sift_Q.npy; G=$DATA/sift_gold.npy; M=l2
         ARMS=("frozen_T4_ef400:--T 4 --harvest 400"
               "frozen_T16_ef400:--T 16 --harvest 400"
               "mut_T4_ef400_B8:--T 4 --harvest 400 --harvest-blocks 8"
               "mut_T2_ef400_B8:--T 2 --harvest 400 --harvest-blocks 8") ;;
  *) echo "unknown dataset $DS" >&2; exit 2 ;;
esac

for b in $(seq 0 $((BLOCKS-1))); do
  # seeded random order within the block: deterministic given the block index
  for arm in $(printf '%s\n' "${ARMS[@]}" | awk -v s="$b" 'BEGIN{srand(s+1)} {print rand()"\t"$0}' | sort -k1,1 | cut -f2-); do
    label="${arm%%:*}"; flags="${arm#*:}"
    echo "### BLOCK $b ARM $label" >> "$OUT"
    # shellcheck disable=SC2086
    "$FG" --data "$X" --queries "$Q" --gold "$G" --metric "$M" \
          --harvest-cap 64 --threads 64 --seed 1 \
          --ef 60 80 120 200 300 400 600 $flags >> "$OUT" 2>&1
    echo "### END" >> "$OUT"
  done
done
echo "PHASE1 $DS DONE"
