#!/usr/bin/env bash
# PiPNN quality baseline for paper 2 (DensePaper), every corpus in the paper.
# Closes the handoff's one open hole: PiPNN appeared only on GloVe, carried
# from Phase 1b and unlabelled as to provenance.
#
# Recipe: PiPNN's own defaults (README: "sane defaults which always perform
# well"): num_clusters 1, cluster_size 1024, mst_deg 2, fanout_scheme 10,3,1
# (30 leaves per point), top_level_leaders 1000, fraction_leaders 0.005,
# hash_bits 12, prune + prune_all. alpha = the Vamana alpha of the same
# table (README: "We always use the same alpha parameter as Vamana uses").
# prune_degree 64 = Vamana's R on every corpus but GloVe, where Vamana is
# R100; GloVe therefore gets both 64 (reproduces Phase 1b) and 100
# (degree-matched). -R/-L are parsed by the ParlayANN driver but unused by
# PiPNN's build; -R is set to prune_degree for hygiene.
# Quality is graded by the same ParlayANN searcher and Q ladder as every
# other row, in the same process; a single build per arm (quality, not
# timing, is what is missing). Peak RSS and wall from /usr/bin/time -v.
#
# Launch on d0:  tmux new -d -s fgpipnn 'bash run_pipnn.sh > results/pipnn_chain.log 2>&1'
# Markers: PIPNN_DONE in $W. Logs and graphs in $O (safe to delete, see README.txt).
set -u
W=/mnt/claude/graft-work/fgraft; O=/mnt/raid/fgraft-campaign-2026-09-22; D=$W/data
PIP=$W/PiPNN/build/algorithms/PipNN/neighbors-pipnn_FLOAT_T_EUCLIDEAN
cd $W; rm -f PIPNN_DONE
run() {  # corpus dir alpha prune_degree
  local ds=$1 dir=$2 alpha=$3 pd=$4; local tag=${1}_d$4
  echo "[pipnn] === $tag alpha=$alpha ==="; date
  /usr/bin/time -v $PIP -base_path $dir/${ds}_base.fbin -query_path $dir/${ds}_query.fbin \
    -gt_path $dir/${ds}_gt100 -graph_outfile $O/pipnn_$tag.graph \
    -file_type bin -data_type float -dist_func Euclidian \
    -alpha $alpha -prune_degree $pd -R $pd -L 128 -two_pass 0 -k 10 \
    -num_clusters 1 -cluster_size 1024 -mst_deg 2 -fanout_scheme 10,3,1 \
    -top_level_leaders 1000 -fraction_leaders 0.005 -hash_bits 12 \
    > $O/pipnn_$tag.log 2>&1
  echo "[pipnn] $tag rc=$?"; date
}
run glove    $D 1.0  64
run glove    $D 1.0  100
run sift     $D 1.15 64
run gist     $D 1.2  64
run deep10m  $D 1.2  64
run wiki     $O 1.2  64
run deep100m $O 1.2  64
touch PIPNN_DONE; echo "[pipnn] chain done"; date
