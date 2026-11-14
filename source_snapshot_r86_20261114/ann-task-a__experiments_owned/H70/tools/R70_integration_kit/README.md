# R70 isolated PiPNN integration for two-arm BUILD screening

**Purpose:** Compile PiPNN `neighbors-pipnn_FLOAT_T_EUCLIDEAN` in two physical-reservoir variants while keeping the logical table size and pruning implementation unchanged. It does not automatically apply H17, does not modify original `~/ann-task-a/src/PiPNN`, and does not run experiments. Only source-pinned `experiments/H70/pipnn-clean-443a328` is permitted.

Prerequisites: Original `graph.h` pin checked; R70 `TwoTierLSHGraph` native test previously passed; worktree CMake parlaylib/Mirage fixes already applied.

## Apply once

```bash
python3 ~/ann-task-a/experiments/H70/tools/R70_integration_kit/r70_integrate.py \
 --worktree ~/ann-task-a/experiments/H70/pipnn-clean-443a328
```

The patch alters only the isolated worktree's `algorithms/PipNN/pipnn.h` and `algorithms/PipNN/CMakeLists.txt`. It retains the same runtime `table_size` value; use 160 in paired runs. A variant identifier is printed at index construction time.

## Build variants, using ONE cached CMake build directory sequentially

Run stock first, then tier. The binary is copied to separately named paths immediately after each compilation; this avoids duplicate third-party dependency builds. **Do not execute the PiPNN builder before capturing its precise stock invocation, dataset/GT paths, flags, thread affinity, and seed from existing logs.**

```bash
cd ~/ann-task-a
OUT="$PWD/experiments/H70"
WORK="$OUT/pipnn-clean-443a328"
BUILD="$OUT/build-r70"
mkdir -p "$OUT/bin"
for PAIR in 'OFF stock' 'ON tier'; do
  set -- $PAIR
  OPT="$1"; LABEL="$2"
  cmake -S "$WORK" -B "$BUILD" -DCMAKE_BUILD_TYPE=Release -DR70_USE_TIER="$OPT" > "$OUT/r70_${LABEL}_configure.log" 2>&1 || { echo "R70_CONFIG_${LABEL}_FAIL"; tail -n 25 "$OUT/r70_${LABEL}_configure.log"; break; }
  cmake --build "$BUILD" --target neighbors-pipnn_FLOAT_T_EUCLIDEAN -j1 > "$OUT/r70_${LABEL}_compile.log" 2>&1 || { echo "R70_COMPILE_${LABEL}_FAIL"; tail -n 35 "$OUT/r70_${LABEL}_compile.log"; break; }
  BIN="$BUILD/algorithms/PipNN/neighbors-pipnn_FLOAT_T_EUCLIDEAN"
  test -x "$BIN" || { echo "R70_BINARY_${LABEL}_MISSING"; break; }
  cp "$BIN" "$OUT/bin/r70_${LABEL}_pipnn"
  sha256sum "$OUT/bin/r70_${LABEL}_pipnn"
  echo "R70_${LABEL}_BINARY_PASS"
done
```

## Scientific notes

- This only establishes the first two arms (clean stock and clean Two-Tier). H17 + flat and H17 + tier remain a future 2×2 ablation only after reproducing the H17 code modification from the original user build in isolation. The original user's modified `pipnn.h`/`pipnn_utils.h` are left untouched.
- The two binaries should be tested against **identical build-only input and flags**. Require a complete, valid generated graph, followed by the same native searcher with fixed dataset/queries/GT, Q sweep, degree/bytes, recall, distance comparisons, wall time, peak RSS and independent processes.
- The pinned original `LSHGraph` destructor does not release the flat allocation. This does not invalidate process-level peak RSS, but it matters for in-process repeated builds.
- Do not claim speed/RSS gains beyond the synthetic reservoir benchmark until native BUILD evidence exists. No SIFT1M run yet.
