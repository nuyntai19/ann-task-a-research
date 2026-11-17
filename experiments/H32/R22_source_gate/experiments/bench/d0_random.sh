#!/usr/bin/env bash
# Random leaders + many memberships = the "localizer hash" construction with
# single sample ids as keys (author, 2026-09-25): a random sample S, every
# object in the cells of its m nearest sample points, all pairs per cell
# through the dense tile. No Lloyd. Existing flags: --dense-kmeans 0.
# GIST-960, d0, 64 threads; graded on ParlayANN like everything else.
# Baselines on that grader: dense L700/m5 k-means 4,485; PiPNN 4,548; Vamana 5,281.
#
# Launch on d0:  tmux new -d -s fgrand 'bash run_random.sh > results/random_chain.log 2>&1'
set -u
W=/mnt/claude/graft-work/fgraft; O=/mnt/raid/fgraft-campaign-2026-09-22/random; D=$W/data
FG=$W/graft-ann/src/fg
VAM=$W/PiPNN/build/algorithms/vamana/neighbors-vamana_FLOAT_T_EUCLIDEAN
mkdir -p $O; cd $W; rm -f RANDOM_DONE
dense() {  # tag L m [extra fg flags...]
  local tag=$1 L=$2 m=$3; shift 3
  echo "[rand] === $tag L=$L m=$m $* ==="; date
  /usr/bin/time -v $FG --data $D/gist_X.npy --queries $D/gist_Q.npy --gold $D/gist_gold.npy \
    --metric l2 --T 1 --harvest 400 --harvest-cap 64 --harvest-alpha 1.0 \
    --dense $L --dense-m $m --dense-C 200 --dense-prune 1 --dense-spine 1 \
    --threads 64 --seed 1 --ef 60 80 120 200 300 400 600 \
    --dump-graph $O/gist_$tag.graph "$@" > $O/gist_$tag.log 2>&1
  echo "[rand] build rc=$?"; date
  $VAM -base_path $D/gist_base.fbin -query_path $D/gist_query.fbin -gt_path $D/gist_gt100 \
    -graph_path $O/gist_$tag.graph -file_type bin -data_type float -dist_func Euclidian \
    -R 64 -L 128 -alpha 1.2 -two_pass 1 -k 10 > $O/gist_${tag}_parlay.log 2>&1
  echo "[rand] grade rc=$?"; date
  grep -h "dense: L=\|local completeness\|edges:" $O/gist_$tag.log | cut -c1-200
}
dense r5_L2500    2500  5  --dense-kmeans 0     # pool 1e4, few memberships
dense k5_L2500    2500  5                       # control: k-means at pool 1e4
dense r10_L10000  10000 10 --dense-kmeans 0     # pool 1e4, split
dense r30_L25000  25000 30 --dense-kmeans 0     # pool 3.6e4, stage A's m30 with random leaders
dense r30_L90000  90000 30 --dense-kmeans 0     # pool 1e4, PiPNN's point, exact assignment
touch RANDOM_DONE; echo "[rand] chain done"; date
