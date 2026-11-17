# R90 · A5 selective second-pass leaf gate — source pilot v0

**Status: SOURCE ONLY — C++ native BUILD and ANN correctness NOT YET VERIFIED.**

This directory contains four full files from original ParAlg/PiPNN (commit `443a328dc71a3b7be753d52ca2b3c9a4ba77f3fd`), with **changes in only two**: `algorithms/PipNN/pipnn.h` and `algorithms/PipNN/CMakeLists.txt`. The other two files are identical to upstream. The project repository's historical `src/PiPNN/` has non-stock H25 edits and must not be treated as pristine PiPNN.

## Working on Ubuntu (copy once; never overwrite)

From a fresh checkout of the research branch, run:

```bash
bash experiments/R90/a5_stock_443a328_v0/bootstrap.sh
```

This creates separate `~/ann-task-a/experiments/R90/a5_stock_443a328_v0/stock` and `.../a5` trees. Both start from the official upstream git commit, then only the two patched files are copied into `a5`. The script checks the commit, stock cleanliness, `git diff --check`, and that only those two files have changed. It refuses an existing destination. Do not modify prior R86/H17 source, data, graphs or results.

## Exact code intervention

PiPNN `multiple_clustertrees()` allocates `G` **before** the loop over `num_clusters`. Each `recursively_sketch_wrapper()` creates buckets and executes `RunLeaf` to merge bidirectional candidate edges into the **same** `G`. Final `ExportToGraph` and `robustPrune` occur after all passes. **N=2 means two build passes; it is NOT stage 2 of the four-stage PiPNN paper.**

The R90 patch ranks nodes after Pass 1 by **ascending reservoir degree**, breaking ties by global point ID, and selects the lowest `R90_A5_FRACTION` (default 0.25). The Pass-2 RBC partition **still runs in full**. A Pass-2 bucket is eligible when it contains at least one selected global node. A5 skips `RunLeaf` only for ineligible buckets; eligible buckets still run original full symmetric GEMM/Top-k and bidirectional HashPrune merges. Final RobustPrune is unchanged. This is **not** rectangular-GEMM RADAR or a proven high-quality selector.

CMake option `-DR90_A5_GATE=OFF` (default) compiles original code path. With `ON`, environment variable `R90_A5_MODE` can be:

| Mode | Behavior |
| --- | --- |
| `off` | original full N2; extra optional code compiled but no gate |
| `dryrun` | rank after P1, count Pass-2 bucket coverage, run **all** Pass-2 leaves unchanged |
| `all` | select all nodes and run all Pass-2 leaves |
| `none` | skip all Pass-2 `RunLeaf`, but still compute Pass-2 buckets (for N1 graph parity) |
| `gate` | lowest-occupancy nodes selected, omit Pass-2 leaves without any selected node |

Only `off` works with N=1. All non-off modes require N=2. `R90_A5_FRACTION` is accepted only for dryrun and gate, with `0 < fraction <= 1`. Selection uses no ground truth, query trace or online recall.

Outputs `R90_A5_PASS1 selected=... sort_comparisons=...` and `R90_A5_LEAF_SCREEN total=... eligible=... WL_total=... WL_eligible=... gate=...`. The `WL` statistic is a **potential O(|bucket|²) work proxy** and does not count hardware FLOPs or total Build cost; full second-pass RBC leader work continues.

## Hard gates before a pilot

1. On Ubuntu, build **separate** stock and a5 trees with identical compiler/flags/third-party dependencies. Build macro OFF, ON and run one CPU thread first. Log source+ELF+flags SHA. **This GitHub push is not proof of C++ compilation.**
2. On identical data and seeds, compare graph SHA/adjacency (or canonical adjacency if scheduling changes) for stock N2 vs A5 OFF, then `off`, `dryrun`, `all`; separately check A5 `none` vs stock N1. Any unexpected difference -> HOLD; never quietly rename a mismatch to PASS.
3. Dryrun to screen fraction 0.10/0.25/0.40 and compute eligible leaves and `WL` fraction; include **selector O(n log n) sort comparisons and memory**; P2 partition cost is *not* eliminated. Stop if most leaves remain.
4. Only then run `gate` small-data 10K/100K, compare original N1/full N2, quality/candidate-coverage and actual work counters. Maintain C160 stock comparator; H17 is a separate later arm, not included in this source-only v0.
5. A5 is a **proposal**. No native graph was built and no Search timing, Recall improvement or QPS has been established. Never call it a new algorithmic win based only on GitHub source review.

### Source provenance

- Upstream full commit `443a328dc71a3b7be753d52ca2b3c9a4ba77f3fd`.
- New branch `research/r90-a5-stock-gated-v0` in `nuyntai19/ann-task-a-research`.
- Distinct `stock/` and `a5/` local directories in the bootstrap contract.
- This repo's `main` remains untouched.
