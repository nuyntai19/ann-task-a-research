#!/usr/bin/env bash
# 2026-10-02: the open items of DensePaper/FRAMING.md §4.
#  D   determinism of the composed build end to end: PiPNN with GRAFT-DET
#      (PIPNN_SEED, PIPNN_DETERMINISTIC: fixed partition seed, sorted merged
#      buckets, sequential hash-vector draw, order-free reservoir) + fg; the
#      graph must be byte-identical at 64 and 32 threads.
#  K   k=100 (and k=10) on the same searcher for Vamana, PiPNN (deterministic),
#      the composed build at its best alpha, and hnswlib M16 (level-0 graph,
#      flat from point 0; native hnswlib ladder alongside): GloVe, SIFT, GIST,
#      Deep-10M; then Vamana + hnswlib on Wikipedia and Deep-100M.
#  A   HSP spine with automatic sample size (--dense-spine-s 0: double from
#      max(1024, sqrt n) until every vertex is reachable from the entry).
#  G   GloVe: 90 and 120 leaves per point, and alpha 1.2 on 60.
# QPS: every ParlayANN log carries QPS per beam; tabulated offline.
# Launch on d0: tmux new -d -s fgopen 'bash run_open_items.sh > results/open_items_chain.log 2>&1'
set -u
W=/mnt/claude/graft-work/fgraft; O=/mnt/raid/fgraft-campaign-2026-09-22/open; D=$W/data; R=/mnt/raid/fgraft-campaign-2026-09-22
FG=$W/graft-ann/src/fg; VAM=$W/PiPNN/build/algorithms/vamana/neighbors-vamana_FLOAT_T_EUCLIDEAN
PIP=$W/PiPNN/build/algorithms/PipNN/neighbors-pipnn_FLOAT_T_EUCLIDEAN
PY=/mnt/claude/graft-work/misifu/.venv/bin/python
export PIPNN_SEED=1 PIPNN_DETERMINISTIC=1
mkdir -p $O; cd $W; rm -f OPEN_DONE
md5sum graft-ann/src/build.cpp PiPNN/algorithms/PipNN/pipnn.h PiPNN/algorithms/utils/graph.h PiPNN/algorithms/utils/hash.h bench/hnsw_export.py

# corpus table: name -> fbin dir, alpha, ParlayANN R/L, fg X/Q/gold/metric, dense L
cfg() {
  case $1 in
    gist)     FB=$D; AL=1.2;  RG=64;  LG=128; X=$D/gist_X.npy;       Q=$D/gist_Q.npy;       G=$D/gist_gold.npy;  MET=l2;     DL=700 ;;
    glove)    FB=$D; AL=1.0;  RG=100; LG=200; X=$D/glove_norm_X.npy; Q=$D/glove_norm_Q.npy; G=$D/glove_gold.npy; MET=cosine; DL=240 ;;
    sift)     FB=$D; AL=1.15; RG=64;  LG=128; X=$D/sift_X.npy;       Q=$D/sift_Q.npy;       G=$D/sift_gold.npy;  MET=l2;     DL=700 ;;
    deep10m)  FB=$D; AL=1.2;  RG=64;  LG=128; X=/mnt/claude/data/deep-10M.X.npy;  Q=/mnt/claude/data/deep-10M.Q.npy;  G=/mnt/claude/data/deep-10M.gold.npy;  MET=l2; DL=2400 ;;
    deep100m) FB=$R; AL=1.2;  RG=64;  LG=128; X=/mnt/claude/data/deep-100M.X.npy; Q=/mnt/claude/data/deep-100M.Q.npy; G=/mnt/claude/data/deep-100M.gold.npy; MET=l2; DL=24000 ;;
    wiki)     FB=$R; AL=1.2;  RG=64;  LG=128; X=/mnt/raid/wikifull_X.npy;  Q=$R/wiki_Q.npy;  G=$R/wiki_gold_full.npy;  MET=cosine; DL=1600 ;;
  esac
}
grade() {  # corpus graph out k
  cfg $1
  $VAM -base_path $FB/${1}_base.fbin -query_path $FB/${1}_query.fbin -gt_path $FB/${1}_gt100 -graph_path $2 \
    -file_type bin -data_type float -dist_func Euclidian -R $RG -L $LG -alpha $AL -two_pass 1 -k $4 > $3 2>&1
  echo "[open] grade k=$4 rc=$? $(basename $3)"
}
# composed: PiPNN pool (dumped) -> our ending at each alpha
composed() {  # test corpus tag k100(0/1) "alphas" pipnn-extra...
  local T=$1 c=$2 tag=$3 k100=$4 alphas=$5; shift 5
  cfg $c; local base=$O/${T}_${c}_${tag}
  echo "[open] === $T $c $tag (pipnn: $*) ==="; date
  local keep=""; [ $k100 = 1 ] && keep="-graph_outfile $base.pipnn.graph"
  local tab=160 prev=""; for x in "$@"; do [ "$prev" = "-table_size" ] && tab=$x; prev=$x; done
  PIPNN_DUMP=$base.cands PIPNN_DUMP_C=$tab /usr/bin/time -v $PIP -base_path $FB/${c}_base.fbin -query_path $FB/${c}_query.fbin \
    -gt_path $FB/${c}_gt100 -file_type bin -data_type float -dist_func Euclidian \
    -alpha $AL -prune_degree 64 -R 64 -L 128 -two_pass 0 -k 10 -num_clusters 1 \
    -top_level_leaders 1000 -fraction_leaders 0.005 -hash_bits 12 $keep "$@" > $base.pipnn.log 2>&1
  echo "[open] pipnn rc=$?"; date
  grep -h "GRAFT-DUMP\|BUILD_DISTANCES_PIPNN\|Final prune time\|Graph built in\|Maximum resident" $base.pipnn.log | cut -c1-200
  [ $k100 = 1 ] && { grade $c $base.pipnn.graph $base.pipnn_k100.log 100; rm -f $base.pipnn.graph; }
  local C=$(grep -o "GRAFT-DUMP [^ ]* C=[0-9]*" $base.pipnn.log | sed 's/.*C=//')
  for a in $alphas; do
    /usr/bin/time -v $FG --data $X --queries $Q --gold $G --metric $MET --T 1 --harvest 400 --harvest-cap 64 --harvest-alpha $a \
      --harvest-cand 200 --dense 1 --dense-C $C --dense-cands $base.cands --dense-prune 1 \
      --dense-spine 3 --dense-spine-s 10000 --dense-spine-cap 16 --threads 64 --seed 1 --ef 60 120 200 400 \
      --dump-graph $base.a$a.graph > $base.a$a.log 2>&1
    echo "[open] fg alpha=$a rc=$?"; date
    grep -h "dense: L=\|candidates:\|Maximum resident" $base.a$a.log | cut -c1-240
    grade $c $base.a$a.graph $base.a${a}_parlay.log 10
    [ $k100 = 1 ] && grade $c $base.a$a.graph $base.a${a}_k100.log 100
    rm -f $base.a$a.graph
  done
  rm -f $base.cands
}
# dense build with the HSP spine
dense_hsp() {  # corpus
  local c=$1; cfg $c; local base=$O/T5_${c}_dense_hsp
  echo "[open] === T5 $c dense L$DL + HSP spine ==="; date
  /usr/bin/time -v $FG --data $X --queries $Q --gold $G --metric $MET --T 1 --harvest 400 --harvest-cap 64 --harvest-alpha 1.0 \
    --dense $DL --dense-m 5 --dense-C 200 --dense-prune 1 --dense-spine 3 --dense-spine-s 10000 --dense-spine-cap 16 \
    --threads 64 --seed 1 --ef 60 120 200 400 --dump-graph $base.graph > $base.log 2>&1
  echo "[open] dense rc=$?"; date
  grep -h "spine:\|dense: L=\|candidates:\|Maximum resident\|Elapsed" $base.log | cut -c1-240
  grade $c $base.graph ${base}_parlay.log 10
  grade $c $base.graph ${base}_k100.log 100
  rm -f $base.graph
}

vamana() {  # corpus
  local c=$1; cfg $c; local base=$O/K_${c}_vamana
  echo "[open] === vamana $c R$RG L$LG a$AL ==="; date
  /usr/bin/time -v $VAM -base_path $FB/${c}_base.fbin -query_path $FB/${c}_query.fbin -gt_path $FB/${c}_gt100 \
    -graph_outfile $base.graph -file_type bin -data_type float -dist_func Euclidian \
    -R $RG -L $LG -alpha $AL -two_pass 1 -k 10 > $base.log 2>&1
  echo "[open] vamana rc=$?"; date
  grade $c $base.graph ${base}_k100.log 100; rm -f $base.graph
}
hnsw() {  # corpus
  local c=$1; cfg $c; local base=$O/K_${c}_hnsw16
  echo "[open] === hnswlib M16 $c ==="; date
  /usr/bin/time -v $PY bench/hnsw_export.py $X $Q $G 16 $base 64 > $base.log 2>&1
  echo "[open] hnsw rc=$?"; date
  grade $c ${base}_level0.graph ${base}_k10.log 10
  grade $c ${base}_level0.graph ${base}_k100.log 100
  rm -f ${base}_level0.graph $base.hnsw
}
dense_auto() {  # corpus
  local c=$1; cfg $c; local base=$O/A_${c}_dense_auto
  echo "[open] === dense $c + HSP auto-s ==="; date
  /usr/bin/time -v $FG --data $X --queries $Q --gold $G --metric $MET --T 1 --harvest 400 --harvest-cap 64 --harvest-alpha 1.0 \
    --dense $DL --dense-m 5 --dense-C 200 --dense-prune 1 --dense-spine 3 --dense-spine-s 0 --dense-spine-cap 16 \
    --threads 64 --seed 1 --ef 60 120 200 400 --dump-graph $base.graph > $base.log 2>&1
  echo "[open] dense rc=$?"; date
  grep -h "spine:" $base.log | cut -c1-200
  grade $c $base.graph ${base}_parlay.log 10; rm -f $base.graph
}
DEF="-cluster_size 1024 -fanout_scheme 10,3,1"

# ---- D: end-to-end determinism of the composed build -------------------------
for t in 64 32; do
  cfg sift; base=$O/D_sift_t$t
  PARLAY_NUM_THREADS=$t PIPNN_DUMP=$base.cands PIPNN_DUMP_C=160 $PIP -base_path $FB/sift_base.fbin -query_path $FB/sift_query.fbin \
    -gt_path $FB/sift_gt100 -file_type bin -data_type float -dist_func Euclidian -alpha $AL -prune_degree 64 -R 64 -L 128 \
    -two_pass 0 -k 10 -num_clusters 1 $DEF -mst_deg 2 -top_level_leaders 1000 -fraction_leaders 0.005 -hash_bits 12 -table_size 160 > $base.pipnn.log 2>&1
  $FG --data $X --queries $Q --gold $G --metric $MET --T 1 --harvest 400 --harvest-cap 64 --harvest-alpha 1.0 --harvest-cand 200 \
    --dense 1 --dense-C 160 --dense-cands $base.cands --dense-prune 1 --dense-spine 3 --dense-spine-s 10000 --dense-spine-cap 16 \
    --threads $t --seed 1 --ef 60 --dump-graph $base.graph > $base.log 2>&1
  echo "[open] D threads=$t cands $(md5sum $base.cands | cut -c1-32) graph $(md5sum $base.graph | cut -c1-32)"
done
[ "$(md5sum $O/D_sift_t64.graph | cut -c1-32)" = "$(md5sum $O/D_sift_t32.graph | cut -c1-32)" ] && echo "[open] D: composed build DETERMINISTIC" || echo "[open] D: MISMATCH"
rm -f $O/D_*.cands $O/D_*.graph

# ---- K + A at 10^6-10^7 -----------------------------------------------------
best_alpha() { case $1 in gist) echo 1.1;; glove) echo 1.2;; *) echo 1.0;; esac; }
for c in glove sift gist deep10m; do
  composed K $c pipnn_det 1 "$(best_alpha $c)" $DEF -mst_deg 2 -table_size 160
  vamana $c
  hnsw $c
  dense_auto $c
done

# ---- G: GloVe, more leaves per point ------------------------------------------
composed G glove fan60_m10_t400 0 "1.2"     -cluster_size 1024 -fanout_scheme 20,3,1 -mst_deg 10 -table_size 400
composed G glove fan90_m10_t600 0 "1.0 1.2" -cluster_size 1024 -fanout_scheme 30,3,1 -mst_deg 10 -table_size 600
composed G glove fan120_m10_t800 0 "1.0 1.2" -cluster_size 1024 -fanout_scheme 40,3,1 -mst_deg 10 -table_size 800

# ---- K at 10^6.8 and 10^8 (long) ---------------------------------------------------
vamana wiki; hnsw wiki
vamana deep100m; hnsw deep100m
touch OPEN_DONE; echo "[open] all done"; date
