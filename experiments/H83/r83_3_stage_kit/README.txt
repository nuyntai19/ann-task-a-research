R83.3: Source-only isolated prototype stage for Compact Fanout Assignment.

Input: H70/pipnn-clean-443a328 (read only), pinned exact two source SHA256.
Output: H83/r83_3_source_stage (exclusive create; no overwrite), with
  algorithms/PipNN/pipnn.h, pipnn_utils.h, CMakeLists.txt
  r83_3_compact_source.diff and r83_3_manifest.json.

No graph BUILD, no compiler, no Git mutation, no changes to H70/H80.
No ANN novelty or speedup claims. The source stage does NOT itself constitute
an installable standalone PiPNN tree; later isolated compilation must stage
all required dependencies and compile a true Flat/D0/E matched evaluation.

Run: python3 r83_3_stage.py --root "$HOME/ann-task-a"

Design: same assign_leaders GEMM, VQPartialSort, selected leader order,
only writes 16-bit leader index and reconstructs original (leader, point ID)
pairs through delayed_tabulate for the exact grouping call.
No alter of graph reservoir, leaf Top2, final pruning.

Acceptance to proceed: inspect diff, syntax compile both arms in an isolated
source tree, one-thread byte-identical graph/ordered buckets, multi-thread
technical graph checks, then SIFT100K counterbalanced time/RSS/Recall.
