# R70 native Two-Tier PiPNN research kit

Only for the **isolated clean worktree** at `~/ann-task-a/experiments/H70/pipnn-clean-443a328` verified by the user. The installer asserts the exact full commit and `graph.h` blob before doing anything. It never changes the user's original `~/ann-task-a/src/PiPNN` source and never writes to the original `graph.h`.

## Run

Unzip `R70_native_kit.zip` into `~/ann-task-a/experiments/H70/tools`, then:

```bash
cd ~/ann-task-a
python3 experiments/H70/tools/R70_native_kit/r70_generate.py \
 --worktree "$PWD/experiments/H70/pipnn-clean-443a328"
```

This generates **only** `algorithms/utils/r70_two_tier_lshgraph.h`, `algorithms/PipNN/r70_native_tests.cc` and appends an `r70_native_tests` target to the isolated worktree's `algorithms/PipNN/CMakeLists.txt`.

Before compiling, check whether the original build has cached dependencies; a fresh `cmake` may attempt external FetchContent and fail on a disconnected Ubuntu environment.

```bash
WORK="$PWD/experiments/H70/pipnn-clean-443a328"
cmake -S "$WORK" -B "$PWD/experiments/H70/build-r70" -DCMAKE_BUILD_TYPE=Release
cmake --build "$PWD/experiments/H70/build-r70" --target r70_native_tests -j2
"$PWD/experiments/H70/build-r70/algorithms/PipNN/r70_native_tests" correctness
```

If dependency configuration fails, *do not modify the original sources or download random substitute headers*. Send the first CMake error. The compilation step is unverified until your machine reports its result.

## Scope and scientific guardrails

The test includes the actual *source-extracted* PiPNN `merge_neighbors` method from commit `443a328`, changing only row pointer access and a 64→65 promotion gate. It compares the original `LSHGraph` and `TwoTierLSHGraph` byte-for-byte for sentinel and occupied slots on matching **ordered** per-node input streams, including collision, full capacity, bf16 rounding, and parallel **independent** source rows.

This test does not establish full native PiPNN BUILD parity, linked end-to-end query Recall, or safe concurrent readers during same-node migration. A concurrent same-node input stream can change ordering and results; that requires later capture/replay and concurrency testing.

The optional `stock` and `tier` modes are SYNTHETIC microbenchmarks, **not** PiPNN full BUILD times. They must be run as separate processes to compare Linux VmHWM. The original `LSHGraph` has an empty destructor and can leak its allocation until the process exits, another reason to use isolated subprocesses. Memory model R69 estimates nominal allocated bytes; do not conflate with measured RSS.

Known limitations: no sanitizer integration yet; no ASAN or TSAN results; graph and final search not run; native compilation not tested in the assistant container because its Eigen/Abseil/Parlay dependencies are absent.
