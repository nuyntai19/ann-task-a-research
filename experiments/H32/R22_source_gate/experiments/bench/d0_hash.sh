#!/usr/bin/env bash
# Subset-hashed localizer arms on GIST-960 (bench/hash_cands.py -> fg --dense-cands
# -> ParlayANN). Signatures reused from the stats run (k 16, alpha 2%, seed 1).
# Baselines on the grader: k-means L700/m5 4,485; random L90000/m30 4,419; PiPNN 4,548.
#
# Launch on d0:  tmux new -d -s fghash 'bash run_hash.sh > results/hash_chain.log 2>&1'
set -u
W=/mnt/claude/graft-work/fgraft; O=/mnt/raid/fgraft-campaign-2026-09-22/hash; D=$W/data
FG=$W/graft-ann/src/fg
VAM=$W/PiPNN/build/algorithms/vamana/neighbors-vamana_FLOAT_T_EUCLIDEAN
PY=/mnt/claude/graft-work/misifu/.venv/bin/python
SIG=$O/gist_a0.02_sig_k16.npy
cd $W; rm -f HASH_DONE
arm() {  # k j C
  local k=$1 j=$2 C=$3 tag=j${2}_k${1}_C$3
  echo "[hash] === cands $tag ==="; date
  /usr/bin/time -v $PY $W/bench/hash_cands.py --data $D/gist_X.npy --alpha 0.02 --k $k --j $j --C $C \
    --seed 1 --sig $SIG --out $O/gist_$tag > $O/gist_${tag}_cands.log 2>&1
  echo "[hash] cands rc=$?"; date; grep "buckets:\|union bound\|done:" $O/gist_${tag}_cands.log | cut -c1-200
  echo "[hash] === dense prune from cands $tag ==="; date
  /usr/bin/time -v $FG --data $D/gist_X.npy --queries $D/gist_Q.npy --gold $D/gist_gold.npy \
    --metric l2 --T 1 --harvest 400 --harvest-cap 64 --harvest-alpha 1.0 \
    --dense 700 --dense-m 5 --dense-C $C --dense-cands $O/gist_${tag}_C$C.i32 --dense-prune 1 --dense-spine 1 \
    --threads 64 --seed 1 --ef 60 80 120 200 300 400 600 \
    --dump-graph $O/gist_$tag.graph > $O/gist_$tag.log 2>&1
  echo "[hash] build rc=$?"; date
  $VAM -base_path $D/gist_base.fbin -query_path $D/gist_query.fbin -gt_path $D/gist_gt100 \
    -graph_path $O/gist_$tag.graph -file_type bin -data_type float -dist_func Euclidian \
    -R 64 -L 128 -alpha 1.2 -two_pass 1 -k 10 > $O/gist_${tag}_parlay.log 2>&1
  echo "[hash] grade rc=$?"; date
  grep -h "local completeness\|edges:" $O/gist_$tag.log | cut -c1-120
}
# pure form: C at the p90 of the per-object union bound, so only hub objects
# lose anything (and they lose their least specific buckets). The truncated
# C=2000 arm (j2_k16) is the earlier negative: truncation = ranking.
arm 10 2 8000
arm 12 3 6000
arm 16 2 16000
arm 16 3 16000
touch HASH_DONE; echo "[hash] chain done"; date
