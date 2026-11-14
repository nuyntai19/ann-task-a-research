#!/usr/bin/env bash
# Radius prune (--dense-radius rho, --dense-radius-k k): can a signature-selected
# pool be used by discarding its far tail before the alpha-prune? GIST-960, d0.
# Gate: the paper's L700/m5 build must reproduce exactly with the flag off
# (26,377.7 M candidates, completeness 0.328, 18,335,567 edges).
# Arms: the uncut pair pool (j2 k10 C8000, d@0.95 6,860 without radius), the
# best count pool (k_b32 C4000, 5,510), and the cell pool itself as control.
#
# Launch on d0:  tmux new -d -s fgradius 'bash run_radius.sh > results/radius_chain.log 2>&1'
set -u
W=/mnt/claude/graft-work/fgraft; R=/mnt/raid/fgraft-campaign-2026-09-22; O=$R/radius; D=$W/data
FG=$W/graft-ann/src/fg
VAM=$W/PiPNN/build/algorithms/vamana/neighbors-vamana_FLOAT_T_EUCLIDEAN
mkdir -p $O; cd $W; rm -f RADIUS_DONE RADIUS_FAIL
run() {  # tag  fg-args...
  local tag=$1; shift
  echo "[radius] === $tag ==="; date
  /usr/bin/time -v $FG --data $D/gist_X.npy --queries $D/gist_Q.npy --gold $D/gist_gold.npy \
    --metric l2 --T 1 --harvest 400 --harvest-cap 64 --harvest-alpha 1.0 \
    --dense-prune 1 --dense-spine 1 --threads 64 --seed 1 --ef 60 80 120 200 300 400 600 \
    --dump-graph $O/gist_$tag.graph "$@" > $O/gist_$tag.log 2>&1
  echo "[radius] build rc=$?"; date
  $VAM -base_path $D/gist_base.fbin -query_path $D/gist_query.fbin -gt_path $D/gist_gt100 \
    -graph_path $O/gist_$tag.graph -file_type bin -data_type float -dist_func Euclidian \
    -R 64 -L 128 -alpha 1.2 -two_pass 1 -k 10 > $O/gist_${tag}_parlay.log 2>&1
  echo "[radius] grade rc=$?"; date
  grep -h "radius prune\|local completeness\|edges:" $O/gist_$tag.log | cut -c1-120
}
run gate_L700_m5 --dense 700 --dense-m 5 --dense-C 200
grep -q "edges: 18335567 directed" $O/gist_gate_L700_m5.log && grep -q "completeness (k=10, sample): 0.328" $O/gist_gate_L700_m5.log \
  || { echo "[radius] GATE FAILED: the paper's build did not reproduce with the new binary"; touch RADIUS_FAIL; exit 1; }
echo "[radius] gate passed"
PAIR=$R/hash/gist_j2_k10_C8000_C8000.i32; CNT=$R/solo/gist_a0.02_kb32_C4000.i32
run pair_k10_r1.3 --dense 700 --dense-m 5 --dense-C 8000 --dense-cands $PAIR --dense-radius 1.3 --dense-radius-k 10
run pair_k10_r1.6 --dense 700 --dense-m 5 --dense-C 8000 --dense-cands $PAIR --dense-radius 1.6 --dense-radius-k 10
run pair_k10_r2.0 --dense 700 --dense-m 5 --dense-C 8000 --dense-cands $PAIR --dense-radius 2.0 --dense-radius-k 10
run count_kb32_r1.6 --dense 700 --dense-m 5 --dense-C 4000 --dense-cands $CNT --dense-radius 1.6 --dense-radius-k 10
run cell_L700_m5_r1.6 --dense 700 --dense-m 5 --dense-C 200 --dense-radius 1.6 --dense-radius-k 10
touch RADIUS_DONE; echo "[radius] chain done"; date
