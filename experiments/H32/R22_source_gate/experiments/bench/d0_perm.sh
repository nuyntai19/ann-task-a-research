#!/usr/bin/env bash
# Permutation-prefix trie partition arms on GIST-960 (bench/perm_cands.py ->
# fg --dense-cands --harvest-cand 200 -> ParlayANN). Baselines on the grader:
# leaf k-means 4,485; exact ceiling 4,601; count+heap 4,518; PiPNN 4,548.
# Launch on d0:  tmux new -d -s fgperm 'bash run_perm.sh > results/perm_chain.log 2>&1'
set -u
W=/mnt/claude/graft-work/fgraft; O=/mnt/raid/fgraft-campaign-2026-09-22/perm; D=$W/data
FG=$W/graft-ann/src/fg
VAM=$W/PiPNN/build/algorithms/vamana/neighbors-vamana_FLOAT_T_EUCLIDEAN
PY=/mnt/claude/graft-work/misifu/.venv/bin/python
SIG20K=/mnt/raid/fgraft-campaign-2026-09-22/capped/gist_a0.02_sig_k16.npy
mkdir -p $O; cd $W; rm -f PERM_DONE
arm() {  # tag C perm_cands-args...
  local tag=$1 C=$2; shift 2
  echo "[perm] === cands $tag ==="; date
  /usr/bin/time -v $PY $W/bench/perm_cands.py --data $D/gist_X.npy --C $C --seed 1 --out $O/gist_$tag "$@" > $O/gist_${tag}_cands.log 2>&1
  echo "[perm] cands rc=$?"; date; grep "trie cut\|memberships\|rows written" $O/gist_${tag}_cands.log | cut -c1-220
  echo "[perm] === prune (cap 200) $tag ==="; date
  /usr/bin/time -v $FG --data $D/gist_X.npy --queries $D/gist_Q.npy --gold $D/gist_gold.npy \
    --metric l2 --T 1 --harvest 400 --harvest-cap 64 --harvest-alpha 1.0 --harvest-cand 200 \
    --dense 700 --dense-m 5 --dense-C $C --dense-cands $O/gist_${tag}_C$C.i32 --dense-prune 1 --dense-spine 1 \
    --threads 64 --seed 1 --ef 60 80 120 200 300 400 600 \
    --dump-graph $O/gist_$tag.graph > $O/gist_$tag.log 2>&1
  echo "[perm] build rc=$?"; date
  $VAM -base_path $D/gist_base.fbin -query_path $D/gist_query.fbin -gt_path $D/gist_gt100 \
    -graph_path $O/gist_$tag.graph -file_type bin -data_type float -dist_func Euclidian \
    -R 64 -L 128 -alpha 1.2 -two_pass 1 -k 10 > $O/gist_${tag}_parlay.log 2>&1
  echo "[perm] grade rc=$?"; date
  grep -h "local completeness\|edges:" $O/gist_$tag.log | cut -c1-120
}
arm S1000_B1000_sw3 4000 --S 1000 --k 8 --B 1000 --lmax 4 --swaps 3
arm S1000_B1000_sw0 4000 --S 1000 --k 8 --B 1000 --lmax 4 --swaps 0 --sig $O/gist_S1000_B1000_sw3_perm_S1000_k8.npy
arm S1000_B1000_sw6 8000 --S 1000 --k 8 --B 1000 --lmax 4 --swaps 6 --sig $O/gist_S1000_B1000_sw3_perm_S1000_k8.npy
arm S1000_B2000_sw3 8000 --S 1000 --k 8 --B 2000 --lmax 4 --swaps 3 --sig $O/gist_S1000_B1000_sw3_perm_S1000_k8.npy
arm S20000_B1000_sw3 4000 --S 20000 --k 8 --B 1000 --lmax 4 --swaps 3 --sig $SIG20K
touch PERM_DONE; echo "[perm] chain done"; date
