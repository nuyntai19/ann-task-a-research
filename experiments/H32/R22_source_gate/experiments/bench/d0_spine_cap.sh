#!/usr/bin/env bash
# 2026-09-30 (evening): HSP spine, capped degree vs capped sample size.
# Grid s in {1k,3k,10k,30k} x cap in {0,8,16,32} + s=100k uncapped (degree curve).
# s=1k cap 0 is the gate (edges must match results/adaptive/*_hsp1000.log).
# (header of the parent chain follows)
# (1) HSP spine: --dense-spine 3 (HSP over a random sample S, point 0 = entry)
#     vs none vs SAT, |S| in {1e3, 1e4, 3e4}, GloVe config A and GIST.
# (2) Adaptive memberships:  picks two-level m(p)
#     policies from three hardness scores (oracle cc, pilot-pass cc, leader
#     margin); fg --dense-m 10 --dense-m-file builds them end to end.
# ParlayANN grading with each corpus's recipe.
# Launch on d0: tmux new -d -s fgadsp 'bash run_adaptive_spine.sh > results/adaptive_spine_chain.log 2>&1'
set -u
W=/mnt/claude/graft-work/fgraft; O=/mnt/raid/fgraft-campaign-2026-09-22/spinecap; D=$W/data
FG=$W/graft-ann/src/fg; VAM=$W/PiPNN/build/algorithms/vamana/neighbors-vamana_FLOAT_T_EUCLIDEAN
PY=/mnt/claude/graft-work/misifu/.venv/bin/python
mkdir -p $O; cd $W; rm -f SPCAP_DONE
md5sum graft-ann/src/build.cpp graft-ann/src/fg.hpp graft-ann/src/main.cpp 
build() {  # corpus tag L Rg Lg alpha  extra...
  local c=$1 tag=$2 L=$3 Rg=$4 Lg=$5 al=$6; shift 6
  local X Q G met
  if [ $c = glove ]; then X=$D/glove_norm_X.npy; Q=$D/glove_norm_Q.npy; G=$D/glove_gold.npy; met=cosine
  else X=$D/${c}_X.npy; Q=$D/${c}_Q.npy; G=$D/${c}_gold.npy; met=l2; fi
  echo "[spcap] === $c $tag ($*) ==="; date
  /usr/bin/time -v $FG --data $X --queries $Q --gold $G --metric $met --T 1 --harvest 400 --harvest-cap 64 --harvest-alpha 1.0 \
    --dense $L --dense-C 200 --dense-prune 1 --threads 64 --seed 1 --ef 60 80 120 200 300 400 600 \
    --dump-graph $O/${c}_$tag.graph "$@" > $O/${c}_$tag.log 2>&1
  echo "[spcap] build rc=$?"; date
  $VAM -base_path $D/${c}_base.fbin -query_path $D/${c}_query.fbin -gt_path $D/${c}_gt100 -graph_path $O/${c}_$tag.graph \
    -file_type bin -data_type float -dist_func Euclidian -R $Rg -L $Lg -alpha $al -two_pass 1 -k 10 > $O/${c}_${tag}_parlay.log 2>&1
  echo "[spcap] grade rc=$?"; date
  grep -h "per-point\|spine:\|dense: L=\|candidates:\|local completeness\|Maximum resident" $O/${c}_$tag.log | cut -c1-240
  rm -f $O/${c}_$tag.graph
}
GL="glove 240 100 200 1.0"; GI="gist 700 64 128 1.2"

# ---- grid
for cfg in "$GL" "$GI"; do
  set -- $cfg; c=$1; shift
  for s in 1000 3000 10000 30000; do for cap in 0 8 16 32; do
    build $c hsp${s}_c$cap "$@" --dense-m 5 --dense-spine 3 --dense-spine-s $s --dense-spine-cap $cap
  done; done
  build $c hsp100000_c0 "$@" --dense-m 5 --dense-spine 3 --dense-spine-s 100000
done
grep -q "edges: 53704153 directed" $O/glove_hsp1000_c0.log && echo "[spcap] GloVe gate OK" || echo "[spcap] GloVe GATE MISMATCH"
grep -q "edges: 16778882 directed" $O/gist_hsp1000_c0.log && echo "[spcap] GIST gate OK" || echo "[spcap] GIST GATE MISMATCH"
touch SPCAP_DONE; echo "[spcap] all done"; date
