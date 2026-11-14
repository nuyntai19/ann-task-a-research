#!/usr/bin/env bash
# The faithful test of signature pools (2026-09-29): every earlier signature-
# pool arm handed fg's prune the whole candidate row (500-8,000 ids), while the
# leaf build prunes only each point's 200 nearest (the stage-3 heap). fg's
# --harvest-cand N caps the prune at the N NEAREST candidates by distance,
# which is the heap. Arms: count pool (k_b 32, C 4000) and pair-bucket pool
# (j 2, k 10, C 8000) with --harvest-cand 200; plus the exact-kNN ceiling with
# the identical ending: --dense 1 --dense-m 1 (one leaf = all points, n^2/2
# pairs) on GloVe and GIST. Graded on ParlayANN as everything else.
#
# Launch on d0:  tmux new -d -s fgcap 'bash run_capped.sh > results/capped_chain.log 2>&1'
set -u
W=/mnt/claude/graft-work/fgraft; O=/mnt/raid/fgraft-campaign-2026-09-22/capped; D=$W/data
FG=$W/graft-ann/src/fg
VAM=$W/PiPNN/build/algorithms/vamana/neighbors-vamana_FLOAT_T_EUCLIDEAN
PY=/mnt/claude/graft-work/misifu/.venv/bin/python
mkdir -p $O; cd $W; rm -f CAPPED_DONE
grade() {  # ds tag R L alpha
  local ds=$1 tag=$2
  $VAM -base_path $D/${ds}_base.fbin -query_path $D/${ds}_query.fbin -gt_path $D/${ds}_gt100 \
    -graph_path $O/${ds}_$tag.graph -file_type bin -data_type float -dist_func Euclidian \
    -R $3 -L $4 -alpha $5 -two_pass 1 -k 10 > $O/${ds}_${tag}_parlay.log 2>&1
  echo "[cap] grade rc=$?"; date
  grep -h "local completeness\|edges:\|dense: L=" $O/${ds}_$tag.log | cut -c1-200
}
echo "[cap] === GloVe ceiling: --dense 1 --dense-m 1 (all pairs) ==="; date
/usr/bin/time -v $FG --data $D/glove_norm_X.npy --queries $D/glove_norm_Q.npy --gold $D/glove_gold.npy \
  --metric cosine --T 1 --harvest 400 --harvest-cap 64 --harvest-alpha 1.0 \
  --dense 1 --dense-m 1 --dense-C 200 --dense-prune 1 --dense-spine 1 \
  --threads 64 --seed 1 --ef 60 80 120 200 300 400 600 \
  --dump-graph $O/glove_ceiling.graph > $O/glove_ceiling.log 2>&1
echo "[cap] build rc=$?"; date; grade glove ceiling 100 200 1.0

echo "[cap] === count pool k_b32 C4000 (regenerate) ==="; date
$PY $W/bench/solo_cands.py --data $D/gist_X.npy --alpha 0.02 --kb 32 --C 4000 --threads 64 --seed 1 --scoring count --out $O/gist_a0.02_kb32 > $O/gist_a0.02_kb32_cands.log 2>&1
echo "[cap] cands rc=$?"; date
echo "[cap] === GIST count kb32 C4000, prune capped at 200 nearest ==="; date
/usr/bin/time -v $FG --data $D/gist_X.npy --queries $D/gist_Q.npy --gold $D/gist_gold.npy \
  --metric l2 --T 1 --harvest 400 --harvest-cap 64 --harvest-alpha 1.0 --harvest-cand 200 \
  --dense 700 --dense-m 5 --dense-C 4000 --dense-cands $O/gist_a0.02_kb32_C4000.i32 --dense-prune 1 --dense-spine 1 \
  --threads 64 --seed 1 --ef 60 80 120 200 300 400 600 \
  --dump-graph $O/gist_count_kb32_cap200.graph > $O/gist_count_kb32_cap200.log 2>&1
echo "[cap] build rc=$?"; date; grade gist count_kb32_cap200 64 128 1.2

echo "[cap] === pair pool j2 k10 C8000 (regenerate; signatures k16) ==="; date
$PY $W/bench/hash_cands.py --data $D/gist_X.npy --alpha 0.02 --k 16 --j 2 --C 2000 --seed 1 --out $O/gist_a0.02 --stats-only > $O/gist_sig.log 2>&1
$PY $W/bench/hash_cands.py --data $D/gist_X.npy --alpha 0.02 --k 10 --j 2 --C 8000 --seed 1 --sig $O/gist_a0.02_sig_k16.npy --out $O/gist_j2_k10 > $O/gist_j2_k10_cands.log 2>&1
echo "[cap] cands rc=$?"; date
echo "[cap] === GIST pair j2 k10 C8000, prune capped at 200 nearest ==="; date
/usr/bin/time -v $FG --data $D/gist_X.npy --queries $D/gist_Q.npy --gold $D/gist_gold.npy \
  --metric l2 --T 1 --harvest 400 --harvest-cap 64 --harvest-alpha 1.0 --harvest-cand 200 \
  --dense 700 --dense-m 5 --dense-C 8000 --dense-cands $O/gist_j2_k10_C8000.i32 --dense-prune 1 --dense-spine 1 \
  --threads 64 --seed 1 --ef 60 80 120 200 300 400 600 \
  --dump-graph $O/gist_pair_k10_cap200.graph > $O/gist_pair_k10_cap200.log 2>&1
echo "[cap] build rc=$?"; date; grade gist pair_k10_cap200 64 128 1.2

echo "[cap] === GIST ceiling: --dense 1 --dense-m 1 (all pairs) ==="; date
/usr/bin/time -v $FG --data $D/gist_X.npy --queries $D/gist_Q.npy --gold $D/gist_gold.npy \
  --metric l2 --T 1 --harvest 400 --harvest-cap 64 --harvest-alpha 1.0 \
  --dense 1 --dense-m 1 --dense-C 200 --dense-prune 1 --dense-spine 1 \
  --threads 64 --seed 1 --ef 60 80 120 200 300 400 600 \
  --dump-graph $O/gist_ceiling.graph > $O/gist_ceiling.log 2>&1
echo "[cap] build rc=$?"; date; grade gist ceiling 64 128 1.2
touch CAPPED_DONE; echo "[cap] chain done"; date
