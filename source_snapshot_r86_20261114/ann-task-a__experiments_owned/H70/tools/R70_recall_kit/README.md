# R70 Recall Kit — pinned PiPNN saved graph evaluation

- `r70_validate_gt.py`: verify 100K base, 300 queries, 300x100 GT file lengths, all IDs in range and full-scan exact top-10 for 2 queries. No numpy required; might take some seconds.
- `r70_setup_recall.py`: add only `algorithms/PipNN/r70_graph_recall.cc` and a small target in CMakeLists of the **isolated** git worktree pinned at 443a328; preserves `algorithms/utils/graph.h`.
- `r70_graph_recall.cc`: native PiPNN graph file reader, native PiPNN beam search + checkRecall, five fixed beams, no graph building.
- `r70_run_recall.py`: run six existing 4-thread BUILD graph files (3 stock, 3 tier) through one-thread native search; raw stdout logs and JSON summaries in a **new** output directory.

This is not tested against the Ubuntu dependency tree here; compiler errors must be reviewed before trusting a result. It only runs graph-based search and does not measure BUILD performance again.
