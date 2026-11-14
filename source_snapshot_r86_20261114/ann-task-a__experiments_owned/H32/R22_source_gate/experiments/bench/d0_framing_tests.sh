#!/usr/bin/env bash
# 2026-10-01: the tests that round off DensePaper/FRAMING.md, in decision order.
#  T1  composed build (PiPNN pool + our ending) at 10^8 and on Wikipedia:
#      does the dense candidate stage keep a scale regime?            [C5]
#  T2  alpha sweep of our ending on thin (mst 2) and rich (mst 10) pools,
#      GIST / GloVe / SIFT / Deep-10M: one recipe "alpha by pool size"? [C3]
#  T3  GloVe: does keeping more of PiPNN's leaves (mst 20/50, 2048-point
#      leaves, 60 leaves per point) close the gap to the dense build?   [C5, C2]
#  T5  the HSP spine (s 10k, cap 16) in every dense table, k=10 and k=100;
#      Deep-100M last (4 h).                                            [C4]
#  T4  kNN-graph clustering on Deep-10M at n = 200k / 1M / 10M (membership
#      growth law) and graph stats on Deep-100M and full Wikipedia.     [C2]
# Our ending = fg --dense-cands, 200-nearest heap, symmetrize + prune (cap 64,
# alpha as given), HSP spine s=10k cap 16. PiPNN = ParAlg 443a328 + counters +
# GRAFT-DUMP (read-only reservoir export). ParlayANN grading, k=10 always,
# k=100 on T1 and T5 graphs (gt100). PiPNN is nondeterministic (+-3%).
# Launch on d0: tmux new -d -s fgframe 'bash run_framing_tests.sh > results/framing_tests_chain.log 2>&1'
set -u
W=/mnt/claude/graft-work/fgraft; O=/mnt/raid/fgraft-campaign-2026-09-22/framing; D=$W/data; R=/mnt/raid/fgraft-campaign-2026-09-22
FG=$W/graft-ann/src/fg; VAM=$W/PiPNN/build/algorithms/vamana/neighbors-vamana_FLOAT_T_EUCLIDEAN
PIP=$W/PiPNN/build/algorithms/PipNN/neighbors-pipnn_FLOAT_T_EUCLIDEAN
PY=/mnt/claude/graft-work/misifu/.venv/bin/python
mkdir -p $O; cd $W; rm -f FRAME_DONE
md5sum graft-ann/src/build.cpp graft-ann/src/fg.hpp graft-ann/src/main.cpp PiPNN/algorithms/PipNN/pipnn.h bench/knn_transitivity_diag.py

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
  echo "[frame] grade k=$4 rc=$? $(basename $3)"
}
# composed: PiPNN pool (dumped) -> our ending at each alpha
composed() {  # test corpus tag k100(0/1) "alphas" pipnn-extra...
  local T=$1 c=$2 tag=$3 k100=$4 alphas=$5; shift 5
  cfg $c; local base=$O/${T}_${c}_${tag}
  echo "[frame] === $T $c $tag (pipnn: $*) ==="; date
  local keep=""; [ $k100 = 1 ] && keep="-graph_outfile $base.pipnn.graph"
  local tab=160 prev=""; for x in "$@"; do [ "$prev" = "-table_size" ] && tab=$x; prev=$x; done
  PIPNN_DUMP=$base.cands PIPNN_DUMP_C=$tab /usr/bin/time -v $PIP -base_path $FB/${c}_base.fbin -query_path $FB/${c}_query.fbin \
    -gt_path $FB/${c}_gt100 -file_type bin -data_type float -dist_func Euclidian \
    -alpha $AL -prune_degree 64 -R 64 -L 128 -two_pass 0 -k 10 -num_clusters 1 \
    -top_level_leaders 1000 -fraction_leaders 0.005 -hash_bits 12 $keep "$@" > $base.pipnn.log 2>&1
  echo "[frame] pipnn rc=$?"; date
  grep -h "GRAFT-DUMP\|BUILD_DISTANCES_PIPNN\|Final prune time\|Graph built in\|Maximum resident" $base.pipnn.log | cut -c1-200
  [ $k100 = 1 ] && { grade $c $base.pipnn.graph $base.pipnn_k100.log 100; rm -f $base.pipnn.graph; }
  local C=$(grep -o "GRAFT-DUMP [^ ]* C=[0-9]*" $base.pipnn.log | sed 's/.*C=//')
  for a in $alphas; do
    /usr/bin/time -v $FG --data $X --queries $Q --gold $G --metric $MET --T 1 --harvest 400 --harvest-cap 64 --harvest-alpha $a \
      --harvest-cand 200 --dense 1 --dense-C $C --dense-cands $base.cands --dense-prune 1 \
      --dense-spine 3 --dense-spine-s 10000 --dense-spine-cap 16 --threads 64 --seed 1 --ef 60 120 200 400 \
      --dump-graph $base.a$a.graph > $base.a$a.log 2>&1
    echo "[frame] fg alpha=$a rc=$?"; date
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
  echo "[frame] === T5 $c dense L$DL + HSP spine ==="; date
  /usr/bin/time -v $FG --data $X --queries $Q --gold $G --metric $MET --T 1 --harvest 400 --harvest-cap 64 --harvest-alpha 1.0 \
    --dense $DL --dense-m 5 --dense-C 200 --dense-prune 1 --dense-spine 3 --dense-spine-s 10000 --dense-spine-cap 16 \
    --threads 64 --seed 1 --ef 60 120 200 400 --dump-graph $base.graph > $base.log 2>&1
  echo "[frame] dense rc=$?"; date
  grep -h "spine:\|dense: L=\|candidates:\|Maximum resident\|Elapsed" $base.log | cut -c1-240
  grade $c $base.graph ${base}_parlay.log 10
  grade $c $base.graph ${base}_k100.log 100
  rm -f $base.graph
}
DEF="-cluster_size 1024 -fanout_scheme 10,3,1"
if [ -n "${SMOKE:-}" ]; then composed SMOKE sift m5_t250 1 "1.1" $DEF -mst_deg 5 -table_size 250; exit; fi

# ---- T1: composed at 10^8 and Wikipedia (decisive for C5) --------------------
composed T1 deep100m m2_t160  1 "1.0 1.2" $DEF -mst_deg 2  -table_size 160
composed T1 wiki     m2_t160  1 "1.0 1.2" $DEF -mst_deg 2  -table_size 160
composed T1 wiki     m10_t400 1 "1.0 1.2" $DEF -mst_deg 10 -table_size 400

# ---- T2: alpha sweep, thin and rich pools ------------------------------------
for c in gist glove sift deep10m; do
  composed T2 $c m2_t160  0 "1.0 1.1 1.2" $DEF -mst_deg 2  -table_size 160
  composed T2 $c m10_t400 0 "1.0 1.1 1.2" $DEF -mst_deg 10 -table_size 400
done

# ---- T3: GloVe, more of PiPNN's leaves ---------------------------------------
composed T3 glove m20_t400        0 "1.0" $DEF -mst_deg 20 -table_size 400
composed T3 glove m50_t800        0 "1.0" $DEF -mst_deg 50 -table_size 800
composed T3 glove cs2048_m10_t400 0 "1.0" -cluster_size 2048 -fanout_scheme 10,3,1 -mst_deg 10 -table_size 400
composed T3 glove cs2048_m20_t800 0 "1.0" -cluster_size 2048 -fanout_scheme 10,3,1 -mst_deg 20 -table_size 800
composed T3 glove fan60_m10_t400  0 "1.0" -cluster_size 1024 -fanout_scheme 20,3,1 -mst_deg 10 -table_size 400

# ---- T5: HSP spine in the dense tables (10^6-10^7) ---------------------------
for c in glove sift gist deep10m wiki; do dense_hsp $c; done

# ---- T4: clustering diagnostic --------------------------------------------------
$PY bench/knn_transitivity_diag.py 200000  /mnt/claude/data/deep-10M.X.npy > $O/T4_deep10m_n200k.log 2>&1;  echo "[frame] T4 deep10m 200k rc=$?"
$PY bench/knn_transitivity_diag.py 1000000 /mnt/claude/data/deep-10M.X.npy > $O/T4_deep10m_n1m.log 2>&1;   echo "[frame] T4 deep10m 1M rc=$?"
$PY bench/knn_transitivity_diag.py         /mnt/claude/data/deep-10M.X.npy > $O/T4_deep10m_n10m.log 2>&1;  echo "[frame] T4 deep10m 10M rc=$?"
TRANS_NOCOST=1 $PY bench/knn_transitivity_diag.py /mnt/claude/data/deep-100M.X.npy > $O/T4_deep100m_stats.log 2>&1; echo "[frame] T4 deep100m rc=$?"
TRANS_NOCOST=1 $PY bench/knn_transitivity_diag.py /mnt/raid/wikifull_X.npy        > $O/T4_wiki_stats.log 2>&1;     echo "[frame] T4 wiki rc=$?"
grep -h "^==\|LID\|local clustering\|memberships needed" $O/T4_*.log

# ---- T5 at 10^8 (4 h) and the rich pool at 10^8 --------------------------------
dense_hsp deep100m
composed T1 deep100m m10_t400 1 "1.0 1.2" $DEF -mst_deg 10 -table_size 400
touch FRAME_DONE; echo "[frame] all done"; date
