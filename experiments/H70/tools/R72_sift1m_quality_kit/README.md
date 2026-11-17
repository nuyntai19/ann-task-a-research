# R72 — SIFT1M native graph/recall pilot

Only for isolated pinned PiPNN H70 worktree and existing R72 pilot four graph files. It never rebuilds the ANN graph, never touches the original `src/PiPNN`, and never overwrites prior run results. Unlike the R70 evaluator (hardcoded to 100,000 base points and 300 queries), the new `r72_graph_recall` is hardcoded to 1,000,000 points, 10,000 queries and graph degree 64. It reuses the native pinned PiPNN `checkRecall` implementation.

1. `python3 r72_preflight.py --base .../data/sift1m.fbin --queries .../data/sift1m_queries.fbin --gt .../data/sift1m_gt.ibin`. Requires NumPy, checks 2 exact top-10 queries by full streaming scan.
2. `python3 r72_setup_evaluator.py --worktree .../experiments/H70/pipnn-clean-443a328`. Appends a separate CMake target, without touching the previously compiled R71 four-arm binaries or source. Verifies pinned HEAD and graph.h as well as existing R70 evaluator source SHA256.
3. `cmake -S "$WORK" -B "$BUILD" -DCMAKE_BUILD_TYPE=Release && cmake --build "$BUILD" --target r72_graph_recall -j1`.
4. `python3 r72_quality_pilot.py --run .../experiments/H70/r72-sift1m-pilot-4t-v71Mv4cM --binary .../experiments/H70/build-r70/algorithms/PipNN/r72_graph_recall --base .../data/sift1m.fbin --queries .../data/sift1m_queries.fbin --gt .../data/sift1m_gt.ibin --out .../experiments/H70/r72-quality-<unique>`.

Failure means stop and inspect errors. `R72_SIFT1M_QUALITY_PILOT_PASS` is a **technical pass for validity and search execution**, not an assertion of Recall parity or statistical significance. One BUILD/arm only; if quality is acceptable, run more BUILD repetitions.
