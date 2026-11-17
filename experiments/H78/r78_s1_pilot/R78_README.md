# R78 — Exact segmented-delta candidate reservoir (research-only)

**Scope:** A small C++ prototype for PiPNN HashPrune's C160 candidate reservoir. It preserves H17 and the two-tier D binary without modification. It is NOT a new ANN graph algorithm, a full native BUILD, or a peer-reviewed novelty claim.

## Files

- `r78_segmented_lshgraph.h`: one S1 implementation. Physical storage is 32 + 32 + 96 candidate slots per node; the base 32 has a degree/worst sentinel. A read-only `Neighbors()` range iterates in **global hash order** so PiPNN's `robustPrune` can consume it without flattening the entire n×C storage.
- `r78_standalone_compat.h`: *test-only* stand-in for Eigen BF16, Parlay `parallel_for`, and Abseil locks; finite Float32 BF16 round-nearest-even. Not the original libraries.
- `r78_s1_tests.cc`: synthetic differential test against a source-derived copy of PiPNN Stock merge logic. Tests capacity boundaries 32/64/160, collisions, duplicate hashes, full eviction, multiple candidate batches, BF16 ties, randomized arrival order, disjoint-row multithreading and same-row structural stress. **Not** proof of full concurrency equivalence.
- `r78_native_pipnn_tests.cc`: the same test logic using the **real** Stock `LSHGraph` from the pinned PiPNN `graph.h`, to compile on the user's Ubuntu.
- `run_standalone.sh`: builds + runs standalone in this folder. It writes only a standalone binary in the current folder.
- `run_real_pipnn_native.py`: compiles and links the native test against the user's preexisting H70 `build-r70` compile/link configuration, **without editing original source, CMake, executables, logs, datasets or graph files**. Writes its own object/binary in this folder. Requires `H70/build-r70/compile_commands.json` and a Makefiles-style `link.txt`.

## Ubuntu workflow

Download `r78_s1_pilot.tar.gz` and put it under `~/Downloads`. Do not unpack into `~/ann-task-a/experiments/H70`.

```bash
mkdir -p ~/ann-task-a/experiments/H78

tar -xzf ~/Downloads/r78_s1_pilot.tar.gz -C ~/ann-task-a/experiments/H78
cd ~/ann-task-a/experiments/H78/r78_s1_pilot

bash ./run_standalone.sh
python3 ./run_real_pipnn_native.py
```

If the native script says `R78_NATIVE_BLOCKED`, send the output. Do not rebuild or modify the existing H70 worktree to satisfy it. The native script checks original PiPNN HEAD and `graph.h` SHA256 before compiling. If native compile success is uncertain, never interpret standalone synthetic PASS as native PASS.

## Source constraints and scientific status

The current header is **not wired into** PiPNN `build_index`. It is a standalone class for testing. Before opening any SIFT100K pilot it must pass the real native stock differential test and a separate compile test of a copied **H78-only** PiPNN tree using segmented `Neighbors()` inside `ExportToGraph`. Existing A/B/C/D binaries and H70 worktree must remain unchanged.

The model from a different archived SIFT1M pool (R59, not R72) predicts roughly 118 MiB less nominal reservoir allocation than B64→full C160, **after** accounting for two 8-byte segment pointers per node and 1024-row chunks. That is not an RSS or BUILD speedup measurement. Allocator, cache and branch overhead could outweigh storage savings. No second-dataset or formal noninferiority claim.

Stop the branch if native parity fails, sorted hash order changes, the API requires contiguous storage, the S1 overhead is too costly, or the direct prior-art papers overlap the proposed claim. In particular, `Polytopes, Bits and Hashes` full text still needs exact mechanism comparison.
