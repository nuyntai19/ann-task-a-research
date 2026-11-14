# R86 fast-track — MS-Turing 1M → 10M → 50M → 100M

Date: 2026-11-14. **Prepared, NOT executed on user's Ubuntu.**

## Deliverables and SHA256

- `r86_mst1m_fasttrack_formal_v1.py`: `3f6cde145120298411c0be94fd4d983b52aa7eabe1fe77dc410dd255f6ec797e`
- `r86_msturing10m_acquire_gate_v1.py`: `13dab194c812d242456de94a1d9359f412b1cd00007b69bc02b846b890813edc`

All commands operate under `~/ann-task-a` and expect the scripts in `~/Downloads`. Existing pilot files and earlier evidence are immutable. The formal graph root is `~/ann-task-a/experiments/R86/msturing_1m_sixarm/formal_mst1m_v1/`.

## A. Check scripts before running

```bash
F="$HOME/Downloads/r86_mst1m_fasttrack_formal_v1.py"
T="$HOME/Downloads/r86_msturing10m_acquire_gate_v1.py"
sha256sum "$F" "$T"
python3 "$F" --preflight
python3 "$F" --scale-plan
python3 "$T" --preflight
```

If any hash differs, HOLD. `--preflight` and `--scale-plan` are read-only. `--scale-plan` is not authorization for large builds.

## B. Last 1M refinement, no graph rebuild

```bash
python3 "$F" --refine
```

Measures: A0/A1/D0 832 (v4), A2 704/1920, A3 832/2112, A4 832/1920; and A0/A1/D0 beam 320 (v3). Searches use the existing six SHA-locked 1M pilot graphs, 100K public queries. A proven existing log is skipped; a conflicting/incomplete log causes HOLD.

## C. Fresh formal 1M graph builds (18 total)

```bash
python3 "$F" --build-all --max-new-builds 6
python3 "$F" --build-all --max-new-builds 6
python3 "$F" --build-all --max-new-builds 6
```

Each command performs up to six new native OFF graph builds, 4 threads pinned CPUs 0,2,4,6. Resume uses graph SHA and evidence receipts, never overwrites. Order balanced across build reps. The formal manifest freezes the smallest **actually measured** beam meeting each target on the pilot graph at the first build; subsequent new pilot refinements do not silently change the official protocol.

## D. Native 100K-query calibration and 5 Search repetitions per fresh graph

```bash
python3 "$F" --calibrate-all --max-new-graphs 6
# Repeat the preceding command until 18/18 fresh graphs calibrated.
python3 "$F" --measure-all --max-new-searches 10
# Repeat until all 180 measurements completed; existing valid receipts skipped.
python3 "$F" --summarize
```

Calibration chooses the pilot smallest measured quality-passing beam, checks it on each fresh graph and increases beam in controlled increments if needed. Each graph has two targets, Recall@10≥0.990 and ≥0.998; each target receives **five new Search process measurements**. Report hierarchical median of graph-level median QPS, not one pooled 90/180-query median. Recall quality floor is **not** exact interpolated matched-Recall; the script must not be cited as providing per-query latency p95/p99, NDC, or logical work counts. These require separate audit.

**Avoid running 10M downloads simultaneously with timed BUILD/Search**; IO/network background load compromises timing/QPS fairness.

## E. Prepare real 10M dataset and official 10M GT

```bash
python3 "$T" --preflight
python3 "$T" --download
```

Downloader uses official Microsoft Turing-ANNS range requests and **requires HTTP 206** with exact Content-Range, aborting on 200/full file transfer. It writes the first 10,000,000 `float32` vectors (100D), source `query100K.fbin` copied from immutable/pinned 1M query, and the **10M-specific** public top-100 GT. It validates dimensions, lengths, SHA, that the first 1M raw vector values match the existing dataset exactly, and all 10M GT IDs are in range. Download can resume from partial files; it does **not** verify exact GT top-100 against the full 10M, does **not** run 10M PiPNN, and does not prove memory feasibility. Store resulting SHA manifest under `~/ann-task-a/data/MSTuring_10M_v1/dataset_manifest.json`. Independent GT spotchecks are still required before reporting Recall.

## F. Resource gates for larger data

- **10M**: base 4,000,000,008 B (~3.73 GiB). Naive 1M-to-10M graph bytes ~1.47–2.01 GiB, but graph structure and memory are **not** known. Test actual 3M/5M first; available RAM ~27 GiB makes C160 10M questionable.
- **50M**: base ~18.63 GiB plus graph. The official standard subset list does **not** provide matching 50M ground truth; a custom exact GT or verified source is necessary before any Recall@10 claim.
- **100M**: base ~37.25 GiB plus estimated graph ~14.66–20.08 GiB, exceeding ~50 GiB free **even before** scratch, logs and repetitions. Requires more disk, likely more RAM, or a formally evaluated out-of-core/sharded protocol; no unsupported 100M native build.

Official dataset references: https://big-ann-benchmarks.com/neurips21.html ; https://github.com/harsha-simhadri/big-ann-benchmarks/blob/main/benchmark/datasets.py ; https://github.com/unum-cloud/usearch/blob/main/BENCHMARKS.md

## G. Teacher's algorithmic evidence still required

Timed OFF graphs and Search do not replace native ON work counters (W_P, W_A, W_L, assignments, comparisons, merge/proposals/hash/prune), coverage/leaf dumps, graph degree/SCC/WCC, per-query search comparisons/visited, and scaling W(n) on **one dataset family**. D0 TwoTier counters ON are not supported by the current pinned source: record `N/A`, not zero. No arm winner or formal complexity bound is established by this fast-track script.
