# R80.4 — Matched SIFT100K BUILD pilot for R80 Move-Heap

**Status on release:** Python static/selftest PASS. Original PiPNN full C++ compiler, linker, SIFT100K BUILD and Recall on Ubuntu **NOT YET RUN**. R80.3 compiler gate previously passed on the user's Ubuntu, but this does not mean R80.4 binaries have compiled.

## Scientific question

Compared with D = H17 Packed Top-2 + Two-Tier B64→C160, does removing `std::priority_queue::top()` deep copies inside `MergeBuckets` improve end-to-end PiPNN BUILD wall time on SIFT100K, **without a material peak-RSS increase** and without observable graph-quality regression?

R80.1 original native differential test: exact full `MergeBuckets` order/contents parity 21/21 fixtures (source-equivalent alternative). R80.2 original native 20,000-bucket independent-process test: 18/18 checksum parity, 16/18 paired timings favor Move-Heap, no measurable synthetic VmHWM improvement. These results are *not* end-to-end BUILD evidence or formal graph equivalence.

## Source protection

This package runs only inside `~/ann-task-a/experiments/H80/r80_4_matched_build`, verifies four H70 source SHA256 pins, pinned `git HEAD`, and R80.3's isolated patched source checksum. It does **not** modify H70, the protected A/B/C/D binaries or prior H80/R80.3 source. It constructs a **fresh independent H80 shadow** with original `neighbors.h`, source-equivalent `pipnn_utils.h`, patched `pipnn.h`, and read-only symlinks to H70's `utils` and `bench` folders.

The compiler input is a wrapper with two includes, the appropriate `PipNN/neighbors.h` and `bench/neighborsTime.C`. Both binaries are compiled with the **same original H70 FLOAT_T/EUCLIDEAN C++ and linker flags** but without the old CMake precompiled header, as follows:

- `D0`: original H70 PiPNN `pipnn.h`, H17+Two-Tier.
- `E`: isolated H80 R80.3-patched `pipnn.h`, H17+Two-Tier+Move-Heap.

A C++ preprocessor `-MM` dependency audit explicitly confirms that `D0` includes H70's original `neighbors.h`, `pipnn.h`, `pipnn_utils.h`, while `E` includes its H80 shadow equivalents. The compiler must NOT accidentally pick H70's old PCH for E. CMake is never run. Compile/link output only in the R80.4 folder.

A new `r80_4_binaries.json` stores source SHA and binary SHA/commands. Previously compiled binaries are accepted on subsequent runs only if the manifest and all checksums match.

## Step 1 — stage and compile ONLY

Download the archive into `~/Downloads`; verify SHA256 using the expected value in the chat. Extract into H80:

```bash
mkdir -p "$HOME/ann-task-a/experiments/H80"
tar -xzf "$HOME/Downloads/r80_4_matched_build.tar.gz" -C "$HOME/ann-task-a/experiments/H80"
python3 "$HOME/ann-task-a/experiments/H80/r80_4_matched_build/run_r80_4.py" --phase selftest
python3 "$HOME/ann-task-a/experiments/H80/r80_4_matched_build/run_r80_4.py" --phase compile
python3 "$HOME/ann-task-a/experiments/H80/r80_4_matched_build/run_r80_4.py" --phase locate
```

The `locate` phase scans only a handful of common data directories, reads 8-byte file headers, and prints native float32 SIFT100K (100000×128) candidates. If the base file isn't listed, supply its absolute path explicitly in the later `--base` parameter. No graph BUILD happens in this first step.

Expected **only if the user's native compile succeeds**:

```text
R80_4_PINNED_SOURCE_GATE_PASS
R80_4_OWN_SHADOW_SOURCE_READY
R80_4_HEADER_PROVENANCE_GATE_PASS arm=D0
R80_4_BINARY_D0_COMPILE_LINK_PASS ...
R80_4_HEADER_PROVENANCE_GATE_PASS arm=E
R80_4_BINARY_E_COMPILE_LINK_PASS ...
R80_4_PAIRED_BINARIES_VERIFIED_PASS
R80_4_COMPILE_ONLY_NO_ANN_BUILD
```

## Step 2 — BUILD pilot (run only after compiled binary checks)

For valid SIFT100K float32 base dataset:

```bash
python3 "$HOME/ann-task-a/experiments/H80/r80_4_matched_build/run_r80_4.py" \
  --phase pilot --base "/absolute/path/to/sift100k.fbin" --reps 3
```

If there is exactly one dataset candidate in the common directories, `--base` may be omitted. If there are zero or multiple, runner fails closed and requests the path.

The pilot executes 4-thread **BUILD-only** in counterbalanced order `D0 E / E D0 / D0 E`, with identical parameters `-num_clusters 2 -cluster_size 1024 -top_level_leaders 100 -fanout_scheme 10,3,1 -mst_deg 2 -prune_degree 64 -table_size 160 -hash_bits 12 -alpha 1.1`. Uses `/usr/bin/time` elapsed wall (%e) and peak RSS (%M, KiB); logs `.graph` per arm/rep and validates graph header, degree upper bound, exact expected graph bytes and SHA256. Writes all artifacts into a **fresh, timestamped** `H80/r80_4_matched_build/runs` folder with no overwrites. Outputs `R80_4_BUILD_RESULT` and per-arm `R80_4_BUILD_MEDIAN`.

Important: Original PiPNN `recursively_sketch_wrapper` seeds RNG with `std::random_device`. Seeds are not guaranteed identical between D0/E or independent processes; exact graph byte equality is **not expected or required**. Graph quality must be assessed separately and in comparison with natural D0-vs-D0 variability. No query/GT used during BUILD to avoid contaminating BUILD wall. No SIFT1M BUILD is supported.

## Step 3 — Search/Recall only (optional; requires existing native 100K evaluator)

After the pilot and with the native 300×128 queries and 300×100 GT, execute:

```bash
python3 "$HOME/ann-task-a/experiments/H80/r80_4_matched_build/run_r80_4.py" \
  --phase quality \
  --run-dir "/absolute/path/to/H80/r80_4_matched_build/runs/r80_4_sift100k_..." \
  --query "/absolute/path/to/sift100k_queries.fbin" \
  --gt "/absolute/path/to/sift100k_gt.ibin"
```

This uses **existing H70** `build-r70/algorithms/PipNN/r70_graph_recall` search-only evaluator. It checks every H80 graph checksum, runs fixed beams 10,20,40,80,160, stores only H80 quality logs, and does not BUILD graphs or change H70. The GT filename is illustrative; use the verified local 300×100 GT. Evaluation supports a scoped quality observation, not a formal non-inferiority test.

## Decision rule

A GO to any larger experiment requires: native compiler+header provenance PASS; all D0/E BUILD graphs valid; full BUILD wall medians E less than D0 in controlled repeats, no material peak-RSS regression, and technical Recall@10 parity across beams. The quantitative margin, confidence and external novelty remain open. Do not promise graph byte identity, universal parallel-schedule equality, or a new ANN algorithm. If the improvement is weak, stop R80-A instead of escalating to SIFT1M.
