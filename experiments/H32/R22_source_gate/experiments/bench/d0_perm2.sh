#!/usr/bin/env bash
# Fragility diagnostic, then the L-table arm (independent permutant sets,
# one own-block membership per table) on GIST-960, heap 200, ParlayANN.
# Launch on d0:  tmux new -d -s fgperm2 'bash run_perm2.sh > results/perm2_chain.log 2>&1'
set -u
W=/mnt/claude/graft-work/fgraft; O=/mnt/raid/fgraft-campaign-2026-09-22/perm; D=$W/data
FG=$W/graft-ann/src/fg
VAM=$W/PiPNN/build/algorithms/vamana/neighbors-vamana_FLOAT_T_EUCLIDEAN
PY=/mnt/claude/graft-work/misifu/.venv/bin/python
cd $W; rm -f PERM2_DONE
echo "[perm2] === fragility diagnostic ==="; date
OMP_NUM_THREADS=32 OPENBLAS_NUM_THREADS=32 $PY $W/bench/perm_diag.py --data $D/gist_X.npy --S 1000 --k 8 --B 1000 --lmax 4 --tables 10 --sample 1000 > $O/gist_perm_diag.log 2>&1
echo "[perm2] diag rc=$?"; date; cat $O/gist_perm_diag.log
tag=S1000_B1000_T5; C=8000
echo "[perm2] === cands $tag ==="; date
/usr/bin/time -v $PY $W/bench/perm_cands.py --data $D/gist_X.npy --S 1000 --k 8 --B 1000 --lmax 4 --swaps 0 --tables 5 --C $C --seed 1 --out $O/gist_$tag > $O/gist_${tag}_cands.log 2>&1
echo "[perm2] cands rc=$?"; date; grep "table\|rows written" $O/gist_${tag}_cands.log | cut -c1-200
echo "[perm2] === prune (cap 200) $tag ==="; date
/usr/bin/time -v $FG --data $D/gist_X.npy --queries $D/gist_Q.npy --gold $D/gist_gold.npy \
  --metric l2 --T 1 --harvest 400 --harvest-cap 64 --harvest-alpha 1.0 --harvest-cand 200 \
  --dense 700 --dense-m 5 --dense-C $C --dense-cands $O/gist_${tag}_C$C.i32 --dense-prune 1 --dense-spine 1 \
  --threads 64 --seed 1 --ef 60 80 120 200 300 400 600 \
  --dump-graph $O/gist_$tag.graph > $O/gist_$tag.log 2>&1
echo "[perm2] build rc=$?"; date
$VAM -base_path $D/gist_base.fbin -query_path $D/gist_query.fbin -gt_path $D/gist_gt100 \
  -graph_path $O/gist_$tag.graph -file_type bin -data_type float -dist_func Euclidian \
  -R 64 -L 128 -alpha 1.2 -two_pass 1 -k 10 > $O/gist_${tag}_parlay.log 2>&1
echo "[perm2] grade rc=$?"; date
grep -h "local completeness\|edges:" $O/gist_$tag.log | cut -c1-120
touch PERM2_DONE; echo "[perm2] chain done"; date
