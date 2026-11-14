#!/usr/bin/env bash
# Warm-started leaders on GIST (results/kmeans-init-FINDINGS.md): gate (no file,
# must reproduce 26,377.7 M / 0.328 / 18,335,567), random-file control (10 it.),
# HSP-smoothed 1 hop at 10 and 3 iterations. ParlayANN grading.
# Launch on d0:  tmux new -d -s fgwarm 'bash run_warm.sh > results/warm_chain.log 2>&1'
set -u
W=/mnt/claude/graft-work/fgraft; O=/mnt/raid/fgraft-campaign-2026-09-22/warm; D=$W/data
FG=$W/graft-ann/src/fg
VAM=$W/PiPNN/build/algorithms/vamana/neighbors-vamana_FLOAT_T_EUCLIDEAN
mkdir -p $O; cd $W; rm -f WARM_DONE
run() {  # tag fg-args...
  local tag=$1; shift
  echo "[warm] === $tag ==="; date
  /usr/bin/time -v $FG --data $D/gist_X.npy --queries $D/gist_Q.npy --gold $D/gist_gold.npy \
    --metric l2 --T 1 --harvest 400 --harvest-cap 64 --harvest-alpha 1.0 \
    --dense 700 --dense-m 5 --dense-C 200 --dense-prune 1 --dense-spine 1 \
    --threads 64 --seed 1 --ef 60 80 120 200 300 400 600 \
    --dump-graph $O/gist_$tag.graph "$@" > $O/gist_$tag.log 2>&1
  echo "[warm] build rc=$?"; date
  $VAM -base_path $D/gist_base.fbin -query_path $D/gist_query.fbin -gt_path $D/gist_gt100 \
    -graph_path $O/gist_$tag.graph -file_type bin -data_type float -dist_func Euclidian \
    -R 64 -L 128 -alpha 1.2 -two_pass 1 -k 10 > $O/gist_${tag}_parlay.log 2>&1
  echo "[warm] grade rc=$?"; date
  grep -h "leaders: initial\|dense: L=\|local completeness\|edges:" $O/gist_$tag.log | cut -c1-230
}
run gate
grep -q "edges: 18335567 directed" $O/gist_gate.log || { echo "[warm] GATE FAILED"; touch WARM_FAIL; exit 1; }
run random_it10 --dense-leaders-file $O/gist_leaders_random_L700.f32
run hsp1_it10   --dense-leaders-file $O/gist_leaders_hsp1_L700.f32
run hsp1_it3    --dense-leaders-file $O/gist_leaders_hsp1_L700.f32 --dense-kmeans 3
run random_it3  --dense-leaders-file $O/gist_leaders_random_L700.f32 --dense-kmeans 3
touch WARM_DONE; echo "[warm] chain done"; date
