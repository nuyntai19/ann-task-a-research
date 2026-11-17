# R80.3 — Compile-only integration gate for H17 + Two-Tier + Move-Heap

**Current evidence:** R80.1 native PiPNN/Parlay `MergeBuckets` parity 21/21; R80.2 independent-process native synthetic-function microbench 18/18 signatures matched, 16/18 paired timings favored Move-Heap. This DOES NOT measure BUILD wall time or RSS.

## Purpose

Verify that the **entire templated BUILD path** of H17+Two-Tier still compiles with the R80-A move-heap implementation integrated **inside an isolated H80 copy** of `pipnn.h`. This is one step before any small SIFT100K pilot. It is not itself a graph BUILD or query.

## Safety and source integrity

- Runs only under `~/ann-task-a/experiments/H80/r80_3_compile_gate` and checks pinned H70 HEAD and four SHA256 hashes.
- Stages copies of `PipNN/pipnn.h` and `pipnn_utils.h` under `H80`, symlinking `utils` and `bench` to H70 **for reading only**. Never writes a source file in H70.
- Replaces only `cluster::MergeBuckets` in the H80 header with the size-heap move implementation previously tested at the R80.1 native function level. Original cluster membership/order and tie rules must remain unchanged.
- Uses H70 `build-r70/compile_commands.json` flags to run `g++ -fsyntax-only` on an explicit function that instantiates `build_index_impl` with the original `TwoTierLSHGraph`, and compile definitions `R70_TWO_TIER=1`, `R71_H17_TOP2=1`.
- No CMake, no object/binary, no dataset access, no ANN BUILD, no graph write, no Recall, no cleanup/reset; refuses overwriting modified H80 test source.

## Ubuntu command

Download `r80_3_compile_gate.tar.gz` into `~/Downloads` and verify its SHA256 against the assistant message. Then:

```bash
cd "$HOME/ann-task-a/experiments/H80"
tar -xzf "$HOME/Downloads/r80_3_compile_gate.tar.gz"
python3 ./r80_3_compile_gate/run_r80_3_compile_gate.py
```

Success markers, **expected only** until the user runs it:

```text
R80_3_H70_SOURCE_PINS_PASS
R80_3_SHADOW_SOURCE_PATCH_PASS
R80_3_FULL_BUILDPATH_TEMPLATE_PASS
R80_3_NO_FULL_BUILD_NO_RSS_NO_RECALL
R80_3_COMPILE_GATE_COMPLETE
```

If blocked, send the exact output. Only after this passes should a new independent binary be built in H80 and measured against the historical D baseline on SIFT100K under a matched, predeclared protocol. Do not claim algorithmic novelty from an STL ownership optimization.
