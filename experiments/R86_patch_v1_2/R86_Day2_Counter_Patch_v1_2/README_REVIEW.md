# R86 Day 2 Counter Patch v1.2 — ready for isolated native BUILD gates, NOT yet native validated

**Date**: 12 Nov 2026. **Baseline**: H70 local snapshot, Git HEAD `443a328dc71a3b7be753d52ca2b3c9a4ba77f3fd` plus the exact local source modifications validated by `EXPECTED_SOURCE_SHA256.txt`. This is **not** a patch against the pristine upstream commit or the already-instrumented B1 `isolation_v4/pipnn.h`.

Claude reviewed v1.1 and approved proceeding to native builds. This v1.2 incorporates three follow-up review items: 

1. **Strong G0**: the original comments, indentation, and executable lines in `graph.h` are preserved. All additions to the three algorithm headers are ON-only. Removing R86-controlled branches from the patched source recreates the H70 baseline **byte for byte**, demonstrated by `scripts/verify_g0.py`. The output does not claim binary reproducibility; native OFF equivalence must still be tested.
2. **Occupancy cannot silently go missing**: when built with R86 ON, calling occupancy on a graph without `degree()`/`kMaxDegree` throws a runtime error rather than silently doing nothing; the OFF build has a no-op stub. The mandatory output path is validated at startup.
3. **Per-pass evidence**: append one JSONL occupancy record **after P1, after P2, ...**, and a separate `pass_id=0` record before final pruning. Optional `R86_DEGREES_PREFIX=/absolute/path/to/prefix` records `prefix_pass1.u32le`, `prefix_pass2.u32le` etc., one unsigned 32-bit little-endian degree per node (n×4 bytes per pass), for matched-node P1/P2 study. G2/G3 verifier can check these arrays against the histogram.

## Status

- G0 source OFF-projection byte identity: PASS on uploaded H70 snapshot.
- Patch applied **only on temp directory**: dry-run PASS.
- Standalone C++ counter header ON/OFF and 305-event synthetic `merge_neighbors` parity/invariants: PASS.
- Missing-capacity graph path: **throws as expected**, test PASS.
- P1/pre-prune JSONL histogram and optional per-node array: synthetic PASS.
- **Native PiPNN OFF/ON CMake build, 10K/1M counters, graph recall, and phase timings: NOT RUN here.**

## Step 0 — extract safely on Ubuntu

Download ZIP into `~/Downloads`. All commands below refer only to the extracted patch folder and a **new R86 destination**. Do not apply any patch to `experiments/H70` or `experiments/H85`.

```bash
unzip -n "$HOME/Downloads/R86_Day2_Counter_Patch_ClaudeReview_v1_2.zip" \
  -d "$HOME/ann-task-a/experiments/R86_patch_v1_2"
P="$HOME/ann-task-a/experiments/R86_patch_v1_2/R86_Day2_Counter_Patch_v1_2"
H70="$HOME/ann-task-a/experiments/H70/pipnn-clean-443a328"
KIT="$HOME/ann-task-a/experiments/R86_logging_kit/ANN_R86_Logging_Kit_v1_2"
bash "$P/scripts/check_and_dry_run.sh" "$H70" "$KIT"
bash "$P/tests/run_static_tests.sh"
```

## G0 — isolated staging (writes only into a NEW R86 directory)

```bash
SRC="$HOME/ann-task-a/experiments/R86/r86_v1_2_source"
python3 "$P/scripts/stage_r86_isolated.py" --source "$H70" --dest "$SRC"
# Inspect dry-run output, then explicitly stage:
python3 "$P/scripts/stage_r86_isolated.py" --source "$H70" --dest "$SRC" --apply
```

Staging copies the original source with a B1-like policy of skipping broken symlinks, checks SHA against the historical H70 snapshot, applies the patch **only** inside the new R86 directory, and runs byte-identity G0 again. Review `R86_STAGING_PROVENANCE.json`, especially omitted symlinks. This script is new and cannot fully guarantee that local dependencies match B1's previous CMake environment; investigate any CMake dependency problems rather than altering H70.

Optional external `unifdef` check (if Ubuntu has unifdef): `unifdef -UR86_COUNTERS <new-file> > off-file`, then diff against H70; the included Python G0 checker is an exact-text fallback that handles only the `R86_COUNTERS` branches.

## Build four isolated binaries (G1/G2/G3 are later)

```bash
BUILD_ROOT="$HOME/ann-task-a/experiments/R86/r86_v1_2_builds"
bash "$P/scripts/build_four.sh" "$SRC" "$BUILD_ROOT" 2>&1 \
  | tee "$HOME/R86_v1_2_four_builds.log"
```

Builds `stock_off`, `stock_on`, `h17_off`, `h17_on` using the pinned `CMakeLists.txt` and `neighbors-pipnn_FLOAT_T_EUCLIDEAN` target, TwoTier OFF. Distinct binary SHA and CMakeCache flags are reported. **CMake might need existing local dependencies; this is the first real PiPNN build gate.**

## Run gates (read native runner flags from the pinned R85 manifests; do NOT invent CLI options)

**G1 OFF equivalence**: Compare Stock OFF / H17 OFF against a matching R85 dataset, query/GT, seed, input format, pruning configuration, CPU affinity, and 4-thread protocol. Use 100K for graph validity and same-beam recall and 1M for the historical partition identity. For Stock BIGANN1M K1024 N2, expected per-pass buckets 85,028 / 86,507 and cumulative `COMPARISONS` 4,728,316,379 / 9,478,487,005. For H17 C64 K512 N2, expect buckets 133,819 / 134,385 and cumulative 4,774,626,648 / 9,569,579,308, **under the same configuration**. Unexpected mismatches are an investigation gate, not proof that clustering is universally deterministic.

**G2 ON 10K, 1 thread**: Run with *new, unique, absolute* paths:

```bash
export R86_COUNTER_OUT="$OUT/counters.jsonl"
export R86_LEAF_SIZE_OUT="$OUT/leaf_sizes.jsonl"
export R86_OCCUPANCY_OUT="$OUT/occupancy.jsonl"
# Optional for N2 and future adaptive analysis:
export R86_DEGREES_PREFIX="$OUT/node_degrees"
```

`$OUT` must point to a newly-created, empty run directory. `R86_OCCUPANCY_OUT` is **JSONL** now (one record per pass plus pass 0), not the former single JSON object. The verifier supports this format:

```bash
python3 "$P/tests/verify_event_stream.py" \
  --events "$OUT/counters.jsonl" --leaves "$OUT/leaf_sizes.jsonl" \
  --occupancy "$OUT/occupancy.jsonl" \
  --degrees-prefix "$OUT/node_degrees" \
  --build-log "$OUT/build.log" --top2 h17
```

Use `--top2 stock` for Stock. The verifier tests exact per-pass logical counters, source cumulative comparisons, and occupancy/per-node histogram consistency. Validate graph structure independently. ON build elapsed times are **not** performance claims.

**G3 ON BIGANN1M**: Only after G1 + G2 PASS, run Stock and H17 C64 K512 N2 at 1M with matched R85 command lines, verify historical `W_P`, bucket count, and floor of final occupancy mean (55 for Stock and 56 for C64 K512 N2). Check P1/P2 snapshots and per-node arrays; compare the R85 historical predictions registered in the `R86_PREREG` tab of the Google Sheet.

## Interpretation safeguards

- `hash_moves` means moved **8-byte candidate slots**, not memory-bus bytes or assignments compiled to machine code.
- `top2_q_writes = Σs(s−1)` holds for executed Stock fallback leaves; H17 Q staging should be zero when the H17 Top-2 branch is taken, but this is **not a complete Top-2 instruction count**.
- `proposals ≤ 2×executed leaf membership` is only a source-derived bound for MST_DEG=2; the ~60M per pass is an approximate scale, **not an equality requirement**.
- `hash_moves/insert ≈ degree/2` is exploratory; it is not a gate (there are full-reservoir replacements, nonuniform insertion ranks and early breaks).
- R85 `Average table size` is integer truncated and is not a substitute for a per-pass occupancy histogram.
- A1 (H17 Flat C160) should be measured in BIGANN1M if comparing it to Stock and C64 variants; do not splice its SIFT1M historical timings into the SCALE1 BIGANN1M study.
- No automated Google Sheet sync exists. Data are entered only after validating A–E run files and E provenance.
