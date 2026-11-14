#!/usr/bin/env bash
# Attribution arm: the existing count-ranked pools (k_b 32, C 1000 and 4000)
# pruned at alpha 1.2 (Vamana's) instead of the paper's 1.0. Waits for the
# E1b chain's marker first. Same grader as everything else.
set -u
W=/mnt/claude/graft-work/fgraft; O=/mnt/raid/fgraft-campaign-2026-09-22/solo; D=$W/data
FG=$W/graft-ann/src/fg
VAM=$W/PiPNN/build/algorithms/vamana/neighbors-vamana_FLOAT_T_EUCLIDEAN
cd $W; rm -f SOLOA_DONE
while [ ! -f SOLO2_DONE ]; do sleep 60; done
for C in 1000 4000; do
  tag=a0.02_kb32_C${C}_alpha1.2
  echo "[solo] === prune alpha 1.2 from cands $tag ==="; date
  /usr/bin/time -v $FG --data $D/gist_X.npy --queries $D/gist_Q.npy --gold $D/gist_gold.npy \
    --metric l2 --T 1 --harvest 400 --harvest-cap 64 --harvest-alpha 1.2 \
    --dense 700 --dense-m 5 --dense-C $C --dense-cands $O/gist_a0.02_kb32_C$C.i32 --dense-prune 1 --dense-spine 1 \
    --threads 64 --seed 1 --ef 60 80 120 200 300 400 600 \
    --dump-graph $O/gist_$tag.graph > $O/gist_$tag.log 2>&1
  echo "[solo] build rc=$?"; date
  $VAM -base_path $D/gist_base.fbin -query_path $D/gist_query.fbin -gt_path $D/gist_gt100 \
    -graph_path $O/gist_$tag.graph -file_type bin -data_type float -dist_func Euclidian \
    -R 64 -L 128 -alpha 1.2 -two_pass 1 -k 10 > $O/gist_${tag}_parlay.log 2>&1
  echo "[solo] grade rc=$?"; date
  grep -h "local completeness\|edges:" $O/gist_$tag.log | cut -c1-120
done
touch SOLOA_DONE; echo "[solo] alpha arms done"; date
