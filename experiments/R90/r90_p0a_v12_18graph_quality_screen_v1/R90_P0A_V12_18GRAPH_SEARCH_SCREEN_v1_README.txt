R90-P0A v1.2 18 NEW OFF GRAPH Search fixed-beam quality SCREEN v1.

This is a native read-only SEARCH screening campaign. It does not BUILD graph,
edit the original graphs, compile executables, change repository files, or run
MS-Turing10M. It requires the same 18 OFF graphs produced by R90-P0A v1.2.

SIFT1M: 10,000 held-out queries, GT100, native pinned R72 evaluator
    ~/ann-task-a/experiments/H70/build-r70/algorithms/PipNN/r72_graph_recall
    evaluator SHA 3c2294efa1d7fb5d89c79ca5bf9c1eaca86247f7246e6d6d7c6c94549d08ed57
    beams: 10,20,40,80,160.
MS-Turing1M: 100,000 public queries, GT100, native pinned R86 v4 evaluator
    ~/ann-task-a/experiments/R86/msturing_1m_eval/r86_msturing1m_graph_recall_v4_highbeam
    evaluator SHA bb6576ad3e1e0cc770535aa06355c664993ca70bd1170d6dd4d202ab5767e144
    beams: 384,896.

The program checks original v1.2 audit/full/preregister/native log file SHA,
checks every original graph's SHA and shape, checks query/GT exact SHA and
shapes, evaluator ELF exact SHA, and native CPU0 affinity. It runs one Search
per graph with taskset CPU0, PARLAY_NUM_THREADS=1, OMP_NUM_THREADS=1, collecting
full native stdout/stderr and per-graph JSON receipts. The fixed-beam quality
screen is NOT a matched-recall noninferiority proof, and legacy 32-bit avg_cmps
from high-beam R86 v4 is explicitly NOT valid. To assess MS Search work use a
separate Counter64 diagnostic; timing should come from the normal evaluator.

Outputs ONLY to NEW directory:
  ~/ann-task-a/experiments/R90/r90_p0a_v12_18graph_quality_screen_v1/
Original v1.2 BUILD source, graphs, binaries, logs and historical evidence are
read-only and never deleted/modified.

To run: download ZIP into ~/Downloads, then:
 unzip -n ~/Downloads/R90_P0A_V12_18GRAPH_SEARCH_SCREEN_v1_BUNDLE.zip -d ~/Downloads
 bash ~/Downloads/R90_P0A_V12_18GRAPH_SEARCH_SCREEN_v1_Ubuntu.sh

On success please upload:
 ~/ann-task-a/experiments/R90/r90_p0a_v12_18graph_quality_screen_v1/quality_screen_summary.json
 ~/ann-task-a/experiments/R90/r90_p0a_v12_18graph_quality_screen_v1/full_manifest.json
 ~/R90_P0A_V12_18GRAPH_SEARCH_SCREEN_v1.log

IMPORTANT: output cannot be reused if it already exists. If a job is interrupted,
keep every file. The Python runner supports reusing complete validated receipts
on phase 'run', but a half-written stdout/stderr with no receipt causes HOLD to
preserve evidence. Never manually delete old original research graph/logs.
