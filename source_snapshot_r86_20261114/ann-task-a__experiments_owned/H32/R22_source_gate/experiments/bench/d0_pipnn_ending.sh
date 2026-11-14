#!/usr/bin/env bash
# 2026-10-01: our ending on PiPNN's pool. PiPNN (ParAlg 443a328 + counters +
# GRAFT-DUMP, a read-only export of the HashPrune reservoir before its final
# prune, sorted by exact distance) at (mst_deg, table_size) in
# {(2,160) = defaults, (5,400), (10,400)}: each leaf already computes its full
# N x N matrix; mst_deg is how many nearest per point it keeps. Per arm:
#   PiPNN's own ending (robustPrune, prune_all, degree 64) graded in-process;
#   our ending on the dumped pool: fg --dense-cands, 200-nearest heap,
#   symmetrize + alpha 1 prune cap 64, HSP spine s=10k cap 16; ParlayANN grade.
# Gate: the (2,160) arm's PiPNN grade must reproduce results/pipnn (dump is read-only).
# Launch on d0: tmux new -d -s fgpend 'bash run_pipnn_ending.sh > results/pipnn_ending_chain.log 2>&1'
set -u
W=/mnt/claude/graft-work/fgraft; O=/mnt/raid/fgraft-campaign-2026-09-22/pipnn_ending; D=$W/data
FG=$W/graft-ann/src/fg; VAM=$W/PiPNN/build/algorithms/vamana/neighbors-vamana_FLOAT_T_EUCLIDEAN
PIP=$W/PiPNN/build/algorithms/PipNN/neighbors-pipnn_FLOAT_T_EUCLIDEAN
mkdir -p $O; cd $W; rm -f PEND_DONE
md5sum graft-ann/src/build.cpp PiPNN/algorithms/PipNN/pipnn.h
arm() {  # corpus alpha mst table  Rg Lg  fgX fgQ fgG metric
  local c=$1 al=$2 mst=$3 tab=$4 Rg=$5 Lg=$6 X=$7 Q=$8 G=$9 met=${10}; local tag=${c}_m${mst}_t${tab}
  echo "[pend] === $tag ==="; date
  PIPNN_DUMP=$O/$tag.cands PIPNN_DUMP_C=$tab /usr/bin/time -v $PIP -base_path $D/${c}_base.fbin -query_path $D/${c}_query.fbin \
    -gt_path $D/${c}_gt100 -file_type bin -data_type float -dist_func Euclidian \
    -alpha $al -prune_degree 64 -R 64 -L 128 -two_pass 0 -k 10 \
    -num_clusters 1 -cluster_size 1024 -mst_deg $mst -fanout_scheme 10,3,1 \
    -top_level_leaders 1000 -fraction_leaders 0.005 -hash_bits 12 -table_size $tab > $O/${tag}_pipnn.log 2>&1
  echo "[pend] pipnn rc=$?"; date
  /usr/bin/time -v $FG --data $X --queries $Q --gold $G --metric $met --T 1 --harvest 400 --harvest-cap 64 --harvest-alpha 1.0 \
    --harvest-cand 200 --dense 1 --dense-C $tab --dense-cands $O/$tag.cands --dense-prune 1 \
    --dense-spine 3 --dense-spine-s 10000 --dense-spine-cap 16 --threads 64 --seed 1 --ef 60 80 120 200 300 400 600 \
    --dump-graph $O/${tag}_ours.graph > $O/${tag}_ours.log 2>&1
  echo "[pend] fg rc=$?"; date
  $VAM -base_path $D/${c}_base.fbin -query_path $D/${c}_query.fbin -gt_path $D/${c}_gt100 -graph_path $O/${tag}_ours.graph \
    -file_type bin -data_type float -dist_func Euclidian -R $Rg -L $Lg -alpha $al -two_pass 1 -k 10 > $O/${tag}_ours_parlay.log 2>&1
  echo "[pend] grade rc=$?"; date
  grep -h "GRAFT-DUMP\|Average table size\|BUILD_DISTANCES_PIPNN\|Final prune time\|Elapsed (wall" $O/${tag}_pipnn.log | cut -c1-200
  grep -h "spine:\|dense: L=\|candidates:\|Elapsed (wall" $O/${tag}_ours.log | cut -c1-240
  rm -f $O/$tag.cands $O/${tag}_ours.graph
}
corpus() {  # c alpha Rg Lg X Q G metric
  for mt in "2 160" "5 400" "10 400"; do set -- $mt; arm "$C" "$AL" $1 $2 "$RG" "$LG" "$X" "$Q" "$G" "$MET"; done
}
C=gist;    AL=1.2;  RG=64;  LG=128; X=$D/gist_X.npy;       Q=$D/gist_Q.npy;       G=$D/gist_gold.npy;  MET=l2;     corpus
C=glove;   AL=1.0;  RG=100; LG=200; X=$D/glove_norm_X.npy; Q=$D/glove_norm_Q.npy; G=$D/glove_gold.npy; MET=cosine; corpus
C=sift;    AL=1.15; RG=64;  LG=128; X=$D/sift_X.npy;       Q=$D/sift_Q.npy;       G=$D/sift_gold.npy;  MET=l2;     corpus
C=deep10m; AL=1.2;  RG=64;  LG=128; X=/mnt/claude/data/deep-10M.X.npy; Q=/mnt/claude/data/deep-10M.Q.npy; G=/mnt/claude/data/deep-10M.gold.npy; MET=l2; corpus
touch PEND_DONE; echo "[pend] all done"; date
