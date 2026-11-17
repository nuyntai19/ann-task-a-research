# R80.1 — Native PiPNN `MergeBuckets` differential gate

## Why this gate was opened

The user's **read-only R80 log scan** checked 155 H70 files and found 58 matching
build logs. A SIFT1M log records two cluster rounds summing to 180,064 final
bucket rows and 59,999,552 point memberships; its source-reported bucket
bytes are `4 × 59,999,552 + 16 × 180,064 = 242,879,232` (231.63 MiB).
These are *final bucket snapshots summed across cluster rounds*, not an actual
`priority_queue` deep-copy trace, the same time peak memory, or unique points.

Source `algorithms/PipNN/pipnn.h:97–162`, pinned by SHA256, uses
`std::priority_queue<Bucket>` with copies of `pq.top()` for merged and remaining
buckets. `priority_queue::top()` is `const_reference` so simply writing
`std::move(pq.top())` is NOT a valid way to avoid the deep copy.

## What this pilot actually does

`r80_1_mergebuckets_native.cc` includes **the actual pinned PiPNN `pipnn.h`**
and instantiates/calls its unmodified `cluster::MergeBuckets` using real Parlay
`sequence`. An alternative local function reproduces the whole merge procedure
but uses a vector heap with **the same comparator and per-insertion
`std::push_heap` / `std::pop_heap` sequence**, moving the extracted last entry.
It compares **exact bucket order and all point IDs** in both `finished_buckets`
and `remaining_clusters`, for 21 deterministic cases: large, mixed, tied sizes,
duplicates, capacity constraints, and `NO_MERGE`. The `potential_copy_id_bytes`
count in its output counts the logical bucket-ID bytes copied by source-style
`pq.top()` extractions on that fixture (it is NOT a measured hardware copy
count or RSS savings). Micro timings are exploratory, not production BUILD.

The runner reuses compile_commands.json and link.txt from the existing H70
`build-r70` native tests, checks original Git HEAD and SHA256 for three source
files, and writes object/executable only in H80. Its run sets Parlay to one
thread for deterministic comparison. **It does not edit H70, execute
`build_index`, run SIFT, allocate the ANN index, or assess Recall.**

## Commands on Ubuntu

After downloading `r80_1_mergebuckets_native.tar.gz` into `~/Downloads`:

```bash
OUT="$HOME/ann-task-a/experiments/H80"
FILE="$HOME/Downloads/r80_1_mergebuckets_native.tar.gz"
EXPECTED="REPLACE_WITH_ARCHIVE_SHA256_FROM_CHAT"
mkdir -p "$OUT"
if printf '%s  %s\n' "$EXPECTED" "$FILE" | sha256sum -c -; then
    if tar -xzf "$FILE" -C "$OUT"; then
        if cd "$OUT/r80_1_mergebuckets_native"; then
            python3 ./run_r80_1_native.py --buckets 1600
        fi
    fi
fi
```

**Note:** This does not use shell `set -e`. If any native compile, link, pin
or parity check fails, the runner
prints `R80_1_BLOCKED` or `R80_1_NATIVE_MERGEBUCKETS_FAIL` and stops.

### Expected success markers (NOT YET observed on user's Ubuntu)

- `R80_1_SOURCE_PIN_GATE_PASS`
- 21 lines `R80_1_NATIVE_CASE_PARITY_PASS`
- `R80_1_REAL_PIPNN_MERGEBUCKETS_PARITY_PASS cases=21`
- `R80_1_NOT_FULL_BUILD_NOT_BUILD_WALL_NOT_PEAK_RSS_NOT_RECALL`
- `R80_1_NATIVE_GATE_COMPLETE`

## Evidence boundary

The assistant tested the differential algorithm against a **simplified local
C++-17 compatibility shim** (same source-level merge shape, but **NOT the
original Parlay/pipnn.h**) at 400 and 1600 buckets; 21/21 cases passed.
A 400-bucket shim fixture passed ASan+UBSan. The real PiPNN native test
provided here has **NOT** been compiled/run on Ubuntu as of kit creation.
The shim is NOT included in the research archive, to avoid confusion with
real PiPNN source. If native parity fails, inspect exact mismatch before
running anything larger. No full SIFT BUILD is approved at this gate.
