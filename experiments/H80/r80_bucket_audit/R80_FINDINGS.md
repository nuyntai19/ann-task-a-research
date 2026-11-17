# R80 — Source-derived build-work audit (2026-11-05)

## Evidence carried from R75.1

On SIFT1M with D=H17+Two-Tier and four threads, the archived median
BUILD wall is 106.020 s, Buckets 35.293 s, Build Leaf 63.711 s and Final
Prune 6.187 s. Phase medians cannot be summed into wall. On eight SMT
threads, Buckets rises to 39.059 s; this does not identify the cause.

## R80-A: avoid unnecessary bucket copies at ownership transfer

In the pinned `pipnn.h`, `MergeBuckets` constructs a priority queue of
Buckets and copies `pq.top()` when removing small and remaining buckets:
lines approximately 118, 124 and 159-160. `top()` returns `const&`, so
`std::move(pq.top())` is NOT a correct optimization.

One candidate is the same size-comparator heap stored in an owned vector:
`pop_heap` moves the top to the vector end, after which the bucket may be
moved into its destination. Its exact bucket ordering and duplication
behavior must be checked with the actual Parlay container, including size
ties, `remove_duplicates`, and the full recursion path before use.

Standalone STL model `r80_heap_drain_probe.cc` tests the *final-drain-only*
case. Four synthetic seeds, 12,000 bucket arrays, exact output ID/order
parity PASS. Baseline copies 9.217–9.245 million bytes of IDs at the final
drain; alternative copies 0 bucket-element bytes there. A standalone
ASan+UBSan run also passed. This is not a PiPNN BUILD benchmark and the
numbers cannot be extrapolated to wall time or peak RSS.

## R80-B: avoid whole temporary leader/point pair arrays (hold)

`SelectAndAssignLeaders` in `pipnn.h:50-89` allocates a
`parlay::sequence<std::pair<uint32_t,uint32_t>> flat(ids.size()*fanout)`.
The nominal storage for this intermediate is `8*N*fanout` bytes, e.g.
80 MB at `N=1m, fanout=10` just for that one array. But the real fanout
and concurrent cluster sizes vary; this is not measured peak memory.
A compact assignment plus counts/prefix-scatter could avoid some storage
but may incur extra passes and alter per-bucket point order. This is a
standard grouping/CSR technique with no established novelty and requires
careful source-level semantics and real phase memory evidence first.

PiPNN already implements overlapping randomized ball carving, leader
assignment and GEMM/Top-K, while newer PiPNN II/GPiPNN advances fused
Top-K and GPU flattened segmented partitioning. Neither R80-A nor R80-B
should be described as a novel ANN construction algorithm without new
mechanism and evidence.

## Evidence that is still missing

The 20 archived BUILD logs report final bucket size/count/point-memberships,
not intermediate priority queue copy bytes or allocation lifetimes. The
read-only parser in this kit can gather those existing summaries on the
user's Ubuntu machine without modifying H70. Gate R80-A on real amount
of work before a complete native `MergeBuckets` differential test. H17+
Two-Tier D stays benchmark baseline. No new SIFT BUILD authorized.

## Source/provenance

- GitHub R77 snapshot commit `d1b5b1a44122a6ce667ece548ea95a3b12df2d19`
- `https://github.com/nuyntai19/ann-task-a-research/tree/research/h17-two-tier-r77/r77_h17_two_tier/source`
- PiPNN: https://arxiv.org/html/2602.21247
- PiPNN II/GPiPNN abstract: https://papers.cool/arxiv/2611.05690

## Data disclosure

The assistant has NOT run the H70 historical-log scan, since those files
are on the user's Ubuntu host. The C++ model only tested STL behavior.
