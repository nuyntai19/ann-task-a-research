#!/usr/bin/env bash
# PLAN-SPLIT.md stages A (fixed-P split sweep), B (leader choice) and D
# (PiPNN at equal pool) on GIST-960, d0, 64 threads. One build per arm.
# Every dense arm dumps its graph and is graded on ParlayANN's searcher
# with the flags of run_r5.sh; fg's own ladder is in the build log.
# Gate G0: the first arm must reproduce the paper's GIST row
# (completeness 0.328, 18,335,567 directed edges, candidates 26,377.7 M).
#
# Launch on d0:  tmux new -d -s fgsplit 'STAGES=A bash run_split.sh > results/split_chain.log 2>&1'
# Markers SPLIT_A_DONE / SPLIT_B_DONE / SPLIT_D_DONE / SPLIT_DONE in $W.
set -u
W=/mnt/claude/graft-work/fgraft; O=/mnt/raid/fgraft-campaign-2026-09-22/split; D=$W/data
FG=$W/graft-ann/src/fg
VAM=$W/PiPNN/build/algorithms/vamana/neighbors-vamana_FLOAT_T_EUCLIDEAN
PIP=$W/PiPNN/build/algorithms/PipNN/neighbors-pipnn_FLOAT_T_EUCLIDEAN
mkdir -p $O; cd $W; rm -f SPLIT_DONE SPLIT_A_DONE SPLIT_B_DONE SPLIT_D_DONE
dense() {  # tag L m [extra fg flags...]
  local tag=$1 L=$2 m=$3; shift 3
  echo "[split] === dense $tag L=$L m=$m $* ==="; date
  /usr/bin/time -v $FG --data $D/gist_X.npy --queries $D/gist_Q.npy --gold $D/gist_gold.npy \
    --metric l2 --T 1 --harvest 400 --harvest-cap 64 --harvest-alpha 1.0 \
    --dense $L --dense-m $m --dense-C 200 --dense-prune 1 --dense-spine 1 \
    --threads 64 --seed 1 --ef 60 80 120 200 300 400 600 \
    --dump-graph $O/gist_$tag.graph "$@" > $O/gist_$tag.log 2>&1
  echo "[split] build rc=$?"; date
  $VAM -base_path $D/gist_base.fbin -query_path $D/gist_query.fbin -gt_path $D/gist_gt100 \
    -graph_path $O/gist_$tag.graph -file_type bin -data_type float -dist_func Euclidian \
    -R 64 -L 128 -alpha 1.2 -two_pass 1 -k 10 > $O/gist_${tag}_parlay.log 2>&1
  echo "[split] grade rc=$?"; date
  grep -h "local completeness\|edges:\|dense: L=" $O/gist_$tag.log | cut -c1-160
}
pipnn() {  # tag [extra pipnn flags...]
  local tag=$1; shift
  echo "[split] === pipnn $tag $* ==="; date
  /usr/bin/time -v $PIP -base_path $D/gist_base.fbin -query_path $D/gist_query.fbin \
    -gt_path $D/gist_gt100 -graph_outfile $O/pipnn_gist_$tag.graph \
    -file_type bin -data_type float -dist_func Euclidian \
    -alpha 1.2 -prune_degree 64 -R 64 -L 128 -two_pass 0 -k 10 \
    -num_clusters 1 -cluster_size 1024 -mst_deg 2 -fanout_scheme 10,3,1 \
    -top_level_leaders 1000 -fraction_leaders 0.005 -hash_bits 12 "$@" \
    > $O/pipnn_gist_$tag.log 2>&1
  echo "[split] pipnn rc=$?"; date
}
STAGES=${STAGES:-A}   # any of A B D, e.g. STAGES=ABD
case $STAGES in *A*)  # --- Stage A: fixed P = 35,714, L = 28 m^2 ---
dense m5_L700      700   5           # G0 gate
dense m10_L2800    2800  10
dense m20_L11200   11200 20
dense m30_L25200   25200 30
touch SPLIT_A_DONE;; esac
case $STAGES in *B*)  # --- Stage B: leader choice at m = 30 ---
dense m30_L25200_k0 25200 30 --dense-kmeans 0
dense m30_L25200_k3 25200 30 --dense-kmeans 3
touch SPLIT_B_DONE;; esac
case $STAGES in *D*)  # --- Stage D: PiPNN at our pool ---
pipnn f100  -fanout_scheme 10,10,1
pipnn c4096 -cluster_size 4096
touch SPLIT_D_DONE;; esac
touch SPLIT_DONE; echo "[split] chain done ($STAGES)"; date
