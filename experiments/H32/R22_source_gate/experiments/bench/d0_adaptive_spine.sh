#!/usr/bin/env bash
# 2026-09-30: the two steps after results/transitivity-FINDINGS.md.
# (1) HSP spine: --dense-spine 3 (HSP over a random sample S, point 0 = entry)
#     vs none vs SAT, |S| in {1e3, 1e4, 3e4}, GloVe config A and GIST.
# (2) Adaptive memberships: bench/adaptive_m_prep.py picks two-level m(p)
#     policies from three hardness scores (oracle cc, pilot-pass cc, leader
#     margin); fg --dense-m 10 --dense-m-file builds them end to end.
# ParlayANN grading with each corpus's recipe.
# Launch on d0: tmux new -d -s fgadsp 'bash run_adaptive_spine.sh > results/adaptive_spine_chain.log 2>&1'
set -u
W=/mnt/claude/graft-work/fgraft; O=/mnt/raid/fgraft-campaign-2026-09-22/adaptive; D=$W/data
FG=$W/graft-ann/src/fg; VAM=$W/PiPNN/build/algorithms/vamana/neighbors-vamana_FLOAT_T_EUCLIDEAN
PY=/mnt/claude/graft-work/misifu/.venv/bin/python
mkdir -p $O; cd $W; rm -f ADSP_DONE
md5sum graft-ann/src/build.cpp graft-ann/src/fg.hpp graft-ann/src/main.cpp bench/adaptive_m_prep.py
build() {  # corpus tag L Rg Lg alpha  extra...
  local c=$1 tag=$2 L=$3 Rg=$4 Lg=$5 al=$6; shift 6
  local X Q G met
  if [ $c = glove ]; then X=$D/glove_norm_X.npy; Q=$D/glove_norm_Q.npy; G=$D/glove_gold.npy; met=cosine
  else X=$D/${c}_X.npy; Q=$D/${c}_Q.npy; G=$D/${c}_gold.npy; met=l2; fi
  echo "[adsp] === $c $tag ($*) ==="; date
  /usr/bin/time -v $FG --data $X --queries $Q --gold $G --metric $met --T 1 --harvest 400 --harvest-cap 64 --harvest-alpha 1.0 \
    --dense $L --dense-C 200 --dense-prune 1 --threads 64 --seed 1 --ef 60 80 120 200 300 400 600 \
    --dump-graph $O/${c}_$tag.graph "$@" > $O/${c}_$tag.log 2>&1
  echo "[adsp] build rc=$?"; date
  $VAM -base_path $D/${c}_base.fbin -query_path $D/${c}_query.fbin -gt_path $D/${c}_gt100 -graph_path $O/${c}_$tag.graph \
    -file_type bin -data_type float -dist_func Euclidian -R $Rg -L $Lg -alpha $al -two_pass 1 -k 10 > $O/${c}_${tag}_parlay.log 2>&1
  echo "[adsp] grade rc=$?"; date
  grep -h "per-point\|spine:\|dense: L=\|candidates:\|local completeness\|Maximum resident" $O/${c}_$tag.log | cut -c1-240
  rm -f $O/${c}_$tag.graph
}
GL="glove 240 100 200 1.0"; GI="gist 700 64 128 1.2"

# ---- (1) spine -------------------------------------------------------------
for cfg in "$GL" "$GI"; do
  set -- $cfg; c=$1; shift
  build $c sp1    "$@" --dense-m 5 --dense-spine 1
  build $c sp0    "$@" --dense-m 5 --dense-spine 0
  for s in 1000 10000 30000; do build $c hsp$s "$@" --dense-m 5 --dense-spine 3 --dense-spine-s $s; done
done
grep -q "edges: 18335567 directed" $O/gist_sp1.log && echo "[adsp] GIST gate OK" || echo "[adsp] GIST GATE MISMATCH (see gist_sp1.log)"

# ---- (2) adaptive memberships ------------------------------------------------
$PY $W/bench/adaptive_m_prep.py $D/glove_norm_X.npy 240 $O/glove 64 > $O/glove_prep.log 2>&1; cat $O/glove_prep.log
$PY $W/bench/adaptive_m_prep.py $D/gist_X.npy 700 $O/gist 64 > $O/gist_prep.log 2>&1; cat $O/gist_prep.log
for cfg in "$GL" "$GI"; do
  set -- $cfg; c=$1; shift
  for f in $O/${c}_{oracle,pilot,margin}_{A,B}.u8; do
    [ -f $f ] || continue
    t=$(basename $f .u8); build $c am_${t#${c}_} "$@" --dense-m 10 --dense-m-file $f --dense-spine 1
  done
done
touch ADSP_DONE; echo "[adsp] all done"; date
