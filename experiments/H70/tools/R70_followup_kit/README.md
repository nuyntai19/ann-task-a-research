# R70 — Mixed correctness + synthetic reservoir microbenchmark

This package extends the *existing* generated R70 native correctness test from the exact pinned PiPNN `graph.h` 443a328 commit. It does not edit the user's original `src/PiPNN` checkout or the graph implementation. It modifies only the generated `r70_native_tests.cc` in the isolated worktree.

1. Run `r70_patch_mixed_correctness.py --worktree ~/ann-task-a/experiments/H70/pipnn-clean-443a328`. It rejects unexpected edits by checking the starter harness SHA256 and makes a copy in H70.
2. Recompile the existing `r70_native_tests` target with `cmake --build ... --target r70_native_tests -j1` and run `.../r70_native_tests correctness`. Check `R70_MIXED_FINAL_ROW_PARITY_PASS` with positive `promoted` and `unpromoted`.
3. If PASS, use `r70_run_synthetic_bench.py --binary .../r70_native_tests --out ~/ann-task-a/experiments/H70/microbench-100k --nodes 100000 --high-per-mille 46 --repeats 3`. It runs alternating stock/tier **separate subprocesses**, stores raw logs, and reports medians. Note this is not PiPNN ANN BUILD/search.

Safety: no `set -e`, no full SIFT1M BUILD, no deletions, no overwriting original checkout. The original stock class has an empty destructor; the OS reclaims memory at each process exit. Do not claim improvement if checksum differs or a process fails.
