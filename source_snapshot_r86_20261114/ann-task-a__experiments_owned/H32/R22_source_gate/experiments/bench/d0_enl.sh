#!/usr/bin/env bash
set -u
W=/mnt/claude/graft-work/fgraft; O=/mnt/raid/fgraft-campaign-2026-09-22/warm; D=$W/data
FG=$W/graft-ann/src/fg; VAM=$W/PiPNN/build/algorithms/vamana/neighbors-vamana_FLOAT_T_EUCLIDEAN
cd $W; rm -f ENL_DONE
for arm in "enl5_k0:gist_leaders_enl5_L700.f32:0" "enl5_k2:gist_leaders_enl5_L700.f32:2" "enl2_k2:gist_leaders_enl2_L700.f32:2"; do
  IFS=: read tag file it <<< "$arm"
  echo "[enl] === $tag ==="; date
  /usr/bin/time -v $FG --data $D/gist_X.npy --queries $D/gist_Q.npy --gold $D/gist_gold.npy \
    --metric l2 --T 1 --harvest 400 --harvest-cap 64 --harvest-alpha 1.0 \
    --dense 700 --dense-m 5 --dense-C 200 --dense-prune 1 --dense-spine 1 --dense-kmeans $it \
    --dense-leaders-file $O/$file --threads 64 --seed 1 --ef 60 80 120 200 300 400 600 \
    --dump-graph $O/gist_$tag.graph > $O/gist_$tag.log 2>&1
  echo "[enl] build rc=$?"; date
  $VAM -base_path $D/gist_base.fbin -query_path $D/gist_query.fbin -gt_path $D/gist_gt100 \
    -graph_path $O/gist_$tag.graph -file_type bin -data_type float -dist_func Euclidian \
    -R 64 -L 128 -alpha 1.2 -two_pass 1 -k 10 > $O/gist_${tag}_parlay.log 2>&1
  echo "[enl] grade rc=$?"; date
done
touch ENL_DONE
