# Requested independent review before native BUILD

**Source:** actual H70 source snapshot uploaded by the user, not hypothesized source line numbers.

## Review checklist

- [ ] Is `multiple_clustertrees()`'s per-pass blocking/join contract sufficient for process-global `active_pass`? Check whether nested Parlay tasks can escape before return.
- [ ] Does `SelectAndAssignLeaders()`'s `num_leaders` equal the actual GEMM width for every valid input size? Does `W_A=|ids|*fanout` include all emitted memberships?
- [ ] Does `RunLeaf` execute exactly for size>1 on every bucket? Is leaf-depth `null` the correct metadata given post-merge bucket representation?
- [ ] Is `r86::emit_leaf_sizes()` independent enough to audit `W_L`, `W_pairs`, leaf_count and size sum? It iterates buckets separately before RunLeaf. Verify no leaf is later skipped or changed.
- [ ] Can `eigen_knn()` propose edges through other paths than its `directed_edges` vector? Are proposal and two-direction merge counts as stated?
- [ ] For `LSHGraph::merge_neighbors()`, confirm early-break is counted once, collision ID compared only after hash collision, and accept/reject/replace metric meanings are consistent with the existing logic.
- [ ] Is `robustPrune()` always the code path from `ExportToGraph()` for these arms when prune_all is ON? We count exact `Points[...].distance` calls here, not VQSort compare operations.
- [ ] Check whether `no_reservoir` path should remain disabled on ON; current patch throws for this path to avoid misleading zero hash counters.
- [ ] Check that output-file safety and uniqueness are reasonable (`R86_COUNTER_OUT`, `R86_LEAF_SIZE_OUT`). Do not reuse paths across runs.
- [ ] Validate OFF build behavioral neutrality: timing/quality comparison with historical runs under the same setup, with variance noted.
- [ ] Confirm kit logger `import-leaf-sizes` accepts `depth:null` and scopes match C++ ON output.
- [ ] Do not require byte-identical ON/OFF outputs due instrumentation/scheduling; verify invariants and quality rather than assuming exact graph equality.

**Review response requested:** specific location/line, severity (BLOCKER / WARN / INFO), and minimal edit for each issue. No BUILD until blockers are addressed.
