# R78.3 — S1 FastShift: CPU-overhead gate

This kit is **research-only**, and targets only:
`~/ann-task-a/experiments/H78/r78_s1_pilot/r78_3_fastshift`.

## Why

User's R78.2 native PiPNN microbenchmark (3 OS processes/arm, 100k nodes):

| variant | median elapsed | median VmHWM |
|---|---:|---:|
| Stock | 0.084798s | 130408 KiB |
| Two-Tier | 0.068746s | 62028 KiB |
| S1 segmented | 0.090175s | 49904 KiB |

S1 saved ~19.55% peak memory against Two-Tier, but cost ~31.17% elapsed **in the synthetic reservoir microbenchmark only**. Full PiPNN build/Recall has not been measured for S1.

## Source-level change

`r78_fast_segmented_lshgraph.h` defines `R78SegmentedFastShiftLSHGraph`, a separate class. It retains the same 32+32+96 memory policy, all Stock/Two-Tier collision and BF16 rules, and the global hash-order iterable. It replaces per-element candidate shifts with segment-local `std::memmove` (requires trivially-copyable T) plus fixed seam moves at logical positions 31→32 and 63→64. No different candidate/edge decision rule is intended.

The header is **not** a patch to original `algorithms/utils/graph.h` or to the R78 S1 header. Never overwrite earlier sources. The first gates compile and compare against actual PiPNN on Ubuntu. A compilation error is a test failure, not permission to modify H70.

## Read-only target / new outputs

The Python runner reuses `H70/build-r70` compiler/link metadata but creates only new test objects and binaries under this R78.3 directory. It pins H70 git HEAD and SHA256 for existing H70 graph.h/pipnn.h/pipnn_utils.h, and the original R78 S1 header; it pins FastShift header SHA256 too. There is **no CMake regeneration, no ANN graph construction, no dataset consumption or new graph output**, and no Git push.

## Execute on Ubuntu

Download `r78_3_fastshift.tar.gz` into `~/Downloads`, then:

```bash
cd ~/ann-task-a/experiments/H78/r78_s1_pilot
sha256sum ~/Downloads/r78_3_fastshift.tar.gz
# Compare to the SHA256 provided in chat; DO NOT extract on mismatch.
tar -xzf ~/Downloads/r78_3_fastshift.tar.gz

cd r78_3_fastshift
bash ./run_r78_3_standalone.sh
python3 ./run_r78_3_fastshift.py --phase native && \
python3 ./run_r78_3_fastshift.py --phase export && \
python3 ./run_r78_3_fastshift.py --phase bench --nodes 500000 --reps 3
```

**Run native first.** Only run Export if native parity PASS; only run benchmark if Export parity PASS. If any phase stops/fails, submit the error output instead of running subsequent phases.

Bench compares 4 arms `stock`, `tier`, `s1`, `fast`, 3 reordered independent OS-process runs/arm. Predefined performance exploration criteria:
- GO *to a small SIFT100K feasibility review* only if FastShift median time is ≤ 1.10× Two-Tier time and median VmHWM is ≤ 1.05× original S1 VmHWM on the same run, with all checksum/parity gates PASS. This is a resource-selection heuristic, **not** a confidence interval or statistical-equivalence test.
- If it reduces S1's 31% CPU overhead but does not reach the target, HOLD for cost diagnosis; do not proceed automatically to full BUILD.
- Never describe microbench numbers as actual SIFT1M BUILD time or ANN Recall.

## Local assistant validation (not Ubuntu)

FastShift C++17 standalone ordered-stream parity test PASS, and standalone ASan/UBSan PASS. Actual PiPNN-native FastShift compile/runtime **PENDING user's Ubuntu terminal**. The assistant's separate 100k standalone timings were noisy and are NOT treated as CPU gains.
