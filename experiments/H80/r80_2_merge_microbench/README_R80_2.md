# R80.2 — original PiPNN MergeBuckets microbenchmark (research only)

This is a **bounded, synthetic, function-level measurement**. It does **not** build an ANN graph, run SIFT, evaluate Recall@10, or modify H70 source or existing R80.1 test files.

After native R80.1 returned 21/21 source-level parity PASS on the user's Ubuntu, this kit performs three independent **process-per-variant** measurements on six distributions of 20,000 buckets each. It alternates the stock/move order, uses the **real, pinned Parlay/PiPNN MergeBuckets** for Stock and exactly the same move-heap implementation as R80.1, and compares output checksums on each paired fixture. It records per-process Linux `ru_maxrss` (KiB) and timed `MergeBuckets` call (ms); fixture preparation is outside the timed section.

## Strict scope and caveats

- The reported `avoided_copy_ID_bytes` counts the bytes that would have been copied by `pq.top()` extraction in the original **for this synthetic fixture**. It is not measured allocator traffic nor actual peak RSS saved.
- `ru_maxrss` is the **whole process** high-water mark including input fixture materialization, not an isolated function's temporary-memory peak. A flat VmHWM is not proof of no allocator savings.
- The benchmark uses synthetic distributions, not real cluster sizes from the historical SIFT1M build. The R80 read-only log captured final buckets but no per-call internal MergeBuckets inputs. It does not measure the actual 35-second BUILD Buckets phase.
- Do not claim algorithm novelty or graph improvement: this is a generic C++ ownership/memory-copy optimization with a source-equivalent operator.
- Does not alter `$HOME/ann-task-a/experiments/H70`, its object files, or previous A/B/C/D binaries. It does create the R80.2 C++ source, object and executable in **H80 only**.
- If the pinned original R80.1 source or H70 file hashes differ, the runner **fails closed**. It never repairs sources automatically.

## Run on Ubuntu

Place `r80_2_merge_microbench.tar.gz` in `~/Downloads`; then:

```bash
OUT="$HOME/ann-task-a/experiments/H80"
FILE="$HOME/Downloads/r80_2_merge_microbench.tar.gz"
EXPECTED="<sha256 of archive from accompanying message>"

if printf '%s  %s\n' "$EXPECTED" "$FILE" | sha256sum -c -; then
  tar -xzf "$FILE" -C "$OUT" && \
  python3 "$OUT/r80_2_merge_microbench/run_r80_2_microbench.py" \
    --buckets 20000 --reps 3 --kinds 0,1,2,3,4,5
fi
```

Expected status markers (only after actual successful execution):

```text
R80_1_SOURCE_PIN_GATE_PASS
R80_2_COMPILE_LINK_PASS
R80_2_PAIR_CHECKSUM_PARITY_PASS ...
R80_2_MEDIANS_BEGIN
R80_2_KIND_SUMMARY ...
R80_2_BOUNDED_NATIVE_GATE_COMPLETE
```

If native compile/link or checksum fails, **stop** and share the complete error. Do not run a full ANN BUILD. No `set -e`, `git reset`, `git clean`, or source patches are involved in the user command.

## Interpreting results

A consistent reduction in the isolated `MergeBuckets` call with no material VmHWM regression would justify discussing a *separate* H80 small BUILD integration gate. But function-level speed alone does not guarantee full BUILD wall improvements, nor does a smaller function allocation imply a smaller process RSS peak. H17 + Two-Tier D remains the validated SIFT1M comparator.
