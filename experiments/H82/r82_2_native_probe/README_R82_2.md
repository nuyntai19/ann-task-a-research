# R82.2 — SIFT1M H18 sampled source-relative Top-2 hash collision diagnostic

Purpose: estimate prevalence of same-source same-leaf Top-2 `relative_hash` collisions, NOT test S3 algorithm, ANN BUILD, Recall or improvement. Real PiPNN `Hash_Family` and Parlay RNG are compiled from pinned hash.h. Original H18 capture has IDs only, so sketches are recomputed (not original runtime trace). Only reads 128 sample leaves by Python random seed 20261106.

Source gates: HEAD 443a328dc71a3b7be753d52ca2b3c9a4ba77f3fd; hash.h Git blob 3d4a2c2f06b7d3eef3a637d8022a2e3ac14c6391; H18 capture SHA256 13e78697bb4e56b5013ee2df3b6c7cee4daa1cfad0185f56a576448d428ccc95; SIFT1M fbin 1,000,000 × 128 Float32.

Installation: extract in a **new** directory such as `~/ann-task-a/experiments/H82/r82_2_native_probe`. Then `python3 run_r82_2.py --root "$HOME/ann-task-a"`. The kit will compile `r82_2_hash_probe_native` and write exclusively `r82_2_summary.json` in this new directory; if summary exists it fails closed. Does not modify H70/H80, does not create graph or run queries.

Output: number of source rows with equal 12-bit relative hashes for two stored Top-2 proposals (nominal) and a heuristic float-boundary sensitivity interval (definite/possible), plus per-leaf counts. The boundary 1e-6 is NOT a mathematical forward-error bound, so the interval is a diagnostic sensitivity bracket only. The C++ floating-point accumulation may differ from original BUILD's flags; use this to screen a candidate, not claim original graph-runtime hash bit identity.

Caveats: Top-2 collisions are not full-reservoir collision rate, not wasted proposal rate, not real HashPrune reject probability, not evidence that replacement Top-3 is available; reverse proposals from other sources may survive. For real S3, require source-native exact correctness, fixed-budget Recall, cost / two metrics, and prior art. Never use heldout query GT to choose edges.
