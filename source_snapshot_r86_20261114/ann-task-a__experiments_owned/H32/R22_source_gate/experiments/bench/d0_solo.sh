#!/usr/bin/env bash
# E1 of the SOLO-candidates idea (results/split-FINDINGS.md, "what to test next"
# superseded): GIST-960, alpha 2%, k_b in {16, 32}, C in {500,1000,2000,4000}.
# Candidates from bench/solo_cands.py (misifu venv), then fg --dense-cands runs
# prune + spine + eval and dumps the graph; ParlayANN grades it with the flags
# of run_r5.sh. Baseline on the same grader: dense L700 d@0.95 = 4,485,
# PiPNN 4,548, Vamana 5,281 (results/split-FINDINGS.md).
#
# Launch on d0:  tmux new -d -s fgsolo 'bash run_solo.sh > results/solo_chain.log 2>&1'
# E1b (hub remedies): KBS=32 CS=1000,2000,4000 SCORING=idf CAP=3200 bash run_solo2.sh
set -u
W=/mnt/claude/graft-work/fgraft; O=/mnt/raid/fgraft-campaign-2026-09-22/solo; D=$W/data
FG=$W/graft-ann/src/fg
VAM=$W/PiPNN/build/algorithms/vamana/neighbors-vamana_FLOAT_T_EUCLIDEAN
PY=/mnt/claude/graft-work/misifu/.venv/bin/python
KBS=${KBS:-16 32}; CS=${CS:-500,1000,2000,4000}; ALPHA=${ALPHA:-0.02}; SCORING=${SCORING:-count}; CAP=${CAP:-0}
SFX=""; [ "$SCORING" != count ] && SFX="_$SCORING"; [ "$CAP" != 0 ] && SFX="${SFX}_cap$CAP"
mkdir -p $O; cd $W; rm -f SOLO_DONE
for kb in $KBS; do
  pre=$O/gist_a${ALPHA}_kb${kb}${SFX}
  echo "[solo] === candidates alpha=$ALPHA k_b=$kb C=$CS scoring=$SCORING cap=$CAP ==="; date
  /usr/bin/time -v $PY $W/bench/solo_cands.py --data $D/gist_X.npy --alpha $ALPHA --kb $kb --C $CS \
    --threads 64 --seed 1 --scoring $SCORING --cap $CAP --out $pre > ${pre}_cands.log 2>&1
  echo "[solo] cands rc=$?"; date; grep "fit:\|check\|descending\|done:" ${pre}_cands.log
  for C in ${CS//,/ }; do
    tag=a${ALPHA}_kb${kb}${SFX}_C$C
    echo "[solo] === dense prune from cands $tag ==="; date
    /usr/bin/time -v $FG --data $D/gist_X.npy --queries $D/gist_Q.npy --gold $D/gist_gold.npy \
      --metric l2 --T 1 --harvest 400 --harvest-cap 64 --harvest-alpha 1.0 \
      --dense 700 --dense-m 5 --dense-C $C --dense-cands ${pre}_C$C.i32 --dense-prune 1 --dense-spine 1 \
      --threads 64 --seed 1 --ef 60 80 120 200 300 400 600 \
      --dump-graph $O/gist_$tag.graph > $O/gist_$tag.log 2>&1
    echo "[solo] build rc=$?"; date
    $VAM -base_path $D/gist_base.fbin -query_path $D/gist_query.fbin -gt_path $D/gist_gt100 \
      -graph_path $O/gist_$tag.graph -file_type bin -data_type float -dist_func Euclidian \
      -R 64 -L 128 -alpha 1.2 -two_pass 1 -k 10 > $O/gist_${tag}_parlay.log 2>&1
    echo "[solo] grade rc=$?"; date
    grep -h "dense: L=\|local completeness\|edges:" $O/gist_$tag.log | cut -c1-200
  done
done
touch SOLO_DONE; echo "[solo] chain done"; date
