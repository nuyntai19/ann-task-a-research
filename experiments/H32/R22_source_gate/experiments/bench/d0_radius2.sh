#!/usr/bin/env bash
# Tight-radius arms on the pair pool (rho 1.1, 1.15): the distance-ratio end
# where the rank-10^4 tail (1.2-1.5 d10) and the mid-range (1.05-1.16 d10) start
# to overlap. Waits for the first radius chain.
set -u
W=/mnt/claude/graft-work/fgraft; R=/mnt/raid/fgraft-campaign-2026-09-22; O=$R/radius; D=$W/data
FG=$W/graft-ann/src/fg
VAM=$W/PiPNN/build/algorithms/vamana/neighbors-vamana_FLOAT_T_EUCLIDEAN
cd $W; rm -f RADIUS2_DONE
while [ ! -f RADIUS_DONE ]; do sleep 30; done
PAIR=$R/hash/gist_j2_k10_C8000_C8000.i32
for rho in 1.1 1.15; do
  tag=pair_k10_r$rho
  echo "[radius] === $tag ==="; date
  /usr/bin/time -v $FG --data $D/gist_X.npy --queries $D/gist_Q.npy --gold $D/gist_gold.npy \
    --metric l2 --T 1 --harvest 400 --harvest-cap 64 --harvest-alpha 1.0 \
    --dense 700 --dense-m 5 --dense-C 8000 --dense-cands $PAIR --dense-radius $rho --dense-radius-k 10 \
    --dense-prune 1 --dense-spine 1 --threads 64 --seed 1 --ef 60 80 120 200 300 400 600 \
    --dump-graph $O/gist_$tag.graph > $O/gist_$tag.log 2>&1
  echo "[radius] build rc=$?"; date
  $VAM -base_path $D/gist_base.fbin -query_path $D/gist_query.fbin -gt_path $D/gist_gt100 \
    -graph_path $O/gist_$tag.graph -file_type bin -data_type float -dist_func Euclidian \
    -R 64 -L 128 -alpha 1.2 -two_pass 1 -k 10 > $O/gist_${tag}_parlay.log 2>&1
  echo "[radius] grade rc=$?"; date
  grep -h "local completeness\|edges:" $O/gist_$tag.log | cut -c1-120
done
touch RADIUS2_DONE; echo "[radius] tight arms done"; date
