#!/usr/bin/env bash
# Warm-started leaders on the other corpora (results/kmeans-init-FINDINGS.md):
# per corpus, the paper's build (gate), HSP-smoothed once + 3 Lloyd, and
# 2 enlarged-Lloyd rounds + 2 Lloyd. ParlayANN grading with each corpus's
# recipe. Launch: tmux new -d -s fgwarmall 'bash run_warm_all.sh > results/warm_all_chain.log 2>&1'
set -u
W=/mnt/claude/graft-work/fgraft; O=/mnt/raid/fgraft-campaign-2026-09-22/warm; D=$W/data; R=/mnt/raid/fgraft-campaign-2026-09-22
FG=$W/graft-ann/src/fg; VAM=$W/PiPNN/build/algorithms/vamana/neighbors-vamana_FLOAT_T_EUCLIDEAN
PY=/mnt/claude/graft-work/misifu/.venv/bin/python
mkdir -p $O; cd $W; rm -f WARMALL_DONE
build() {  # corpus tag X Q gold metric L base_fbin query_fbin gt R Lg alpha  extra...
  local c=$1 tag=$2 X=$3 Q=$4 G=$5 met=$6 L=$7 base=$8 qf=$9 gt=${10} Rg=${11} Lg=${12} al=${13}; shift 13
  echo "[warm] === $c $tag ==="; date
  /usr/bin/time -v $FG --data $X --queries $Q --gold $G --metric $met --T 1 --harvest 400 --harvest-cap 64 --harvest-alpha 1.0 \
    --dense $L --dense-m 5 --dense-C 200 --dense-prune 1 --dense-spine 1 --threads 64 --seed 1 --ef 60 80 120 200 300 400 600 \
    --dump-graph $O/${c}_$tag.graph "$@" > $O/${c}_$tag.log 2>&1
  echo "[warm] build rc=$?"; date
  $VAM -base_path $base -query_path $qf -gt_path $gt -graph_path $O/${c}_$tag.graph -file_type bin -data_type float \
    -dist_func Euclidian -R $Rg -L $Lg -alpha $al -two_pass 1 -k 10 > $O/${c}_${tag}_parlay.log 2>&1
  echo "[warm] grade rc=$?"; date
  grep -h "dense: L=\|local completeness" $O/${c}_$tag.log | cut -c1-200
}
corpus() {  # c X Q gold metric L base qf gt R Lg alpha
  local c=$1 X=$2 met=$5 L=$6
  echo "[warm] === leaders $c ==="; date
  $PY $W/bench/hsp_enl_leaders.py $X $L 2 $met $O/${c}_leaders 1 > $O/${c}_leaders.log 2>&1; cat $O/${c}_leaders.log
  build "$1" gate "${@:2}"
  build "$1" hsp1_it3 "${@:2}" --dense-leaders-file $O/${c}_leaders_hsp1_L$L.f32 --dense-kmeans 3
  build "$1" enl2_it2 "${@:2}" --dense-leaders-file $O/${c}_leaders_enl2_L$L.f32 --dense-kmeans 2
}
corpus glove   $D/glove_norm_X.npy $D/glove_norm_Q.npy $D/glove_gold.npy cosine 240  $D/glove_base.fbin $D/glove_query.fbin $D/glove_gt100 100 200 1.0
corpus sift    $D/sift_X.npy       $D/sift_Q.npy       $D/sift_gold.npy  l2     700  $D/sift_base.fbin  $D/sift_query.fbin  $D/sift_gt100  64 128 1.15
corpus deep10m /mnt/claude/data/deep-10M.X.npy /mnt/claude/data/deep-10M.Q.npy /mnt/claude/data/deep-10M.gold.npy l2 2400 $D/deep10m_base.fbin $D/deep10m_query.fbin $D/deep10m_gt100 64 128 1.2
corpus wiki    /mnt/raid/wikifull_X.npy $R/wiki_Q.npy $R/wiki_gold_full.npy cosine 1600 $R/wiki_base.fbin $R/wiki_query.fbin $R/wiki_gt100 64 128 1.2
touch WARMALL_DONE; echo "[warm] all done"; date
