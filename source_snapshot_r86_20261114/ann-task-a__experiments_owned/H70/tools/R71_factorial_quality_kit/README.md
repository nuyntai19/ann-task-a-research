# R71.6: Saved-graph correctness and Recall@10

This follow-up is read-only toward the original PiPNN source and the twelve R71 factorial graphs. It uses the previously compiled `r70_graph_recall` evaluator based on native PiPNN `checkRecall`, with the same 300-query SIFT100K GT and the same beams: 10, 20, 40, 80, 160.

Preconditions: successful `R71_FACTORIAL_12_BUILDS_PASS`, `R71_FACTORIAL_SUMMARY_PASS`, `R70_GT_VALIDATION_PASS`, and existing executable `experiments/H70/build-r70/algorithms/PipNN/r70_graph_recall`.

The script first checks SHA256 of the recorded input manifest, the exact 12 BUILD time files, runtime labels, graph serialization format, legal IDs, duplicate neighbors and self-loops. If preflight fails, it leaves graph files untouched and exits. Then it evaluates all 12 graphs, saving one native log per graph, and prints arm medians and Recall@10 differences D vs A.

The directory passed as `--out` must not already exist. To prevent accidental overwrites, use `$(date +%Y%m%d-%H%M%S)-$$` in its name. The output is `r71_quality_summary.json` and twelve `.recall.log` files.

This is *not* a statistical equivalence test, not a novelty claim, and not a BUILD rerun.
