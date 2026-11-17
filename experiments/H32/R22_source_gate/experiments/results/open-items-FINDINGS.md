# Open items of FRAMING §4 (2026-10-02, d0; `bench/d0_open_items.sh` + follow-ups)

Logs `results/open/`; d@r and QPS by `bench/parse_qps.py` (QPS = ParlayANN
batch throughput on d0's 64 threads, comparable only within this table).
All rows on ParlayANN's searcher. "Composed" = deterministic PiPNN pool
(defaults, mst 2, table 160) + our ending at the corpus's best alpha (T2:
GIST 1.1, GloVe 1.2, else 1.0), HSP spine s=10k cap 16.

## D. The composed build is deterministic end to end

PiPNN made deterministic under `PIPNN_SEED=1 PIPNN_DETERMINISTIC=1`
(GRAFT-DET patches on d0; default PiPNN untouched; originals saved as
`/mnt/raid/fgraft-campaign-2026-09-22/{pipnn.h,graph.h,hash.h}.before-*`).
Three sources had to be removed:
1. the partition seed came from `std::random_device` (the authors' own
   `// TODO: this is non-deterministic! wtf`);
2. `parlay::remove_duplicates` (hash-based) reorders merged buckets, and the
   next level samples leaders by position (`std::sample`);
3. the sketch-hash vectors were drawn by a parallel `tabulate` through one
   shared, stateful `std::normal_distribution` (Box-Muller caches every
   second draw), so the hash family depended on scheduling;
plus the reservoir merge, made order-free: total order (bfloat16 distance,
id), a bucket keeps its minimum, a full table evicts its maximum.
Gate: SIFT reservoir dump byte-identical at 64/32/64 threads
(a08dddd7...), and the composed graph byte-identical at 64 and 32 threads
(f2794a2b...). Quality unchanged within PiPNN's run-to-run noise (GIST
4,556 vs 4,548-4,672 nondeterministic). **Cost:** +1-3% build time on thin
pools; 1.8x on rich tables (GloVe 60 leaves, table 400: 72.6 s vs 39.5 s),
because the order-free merge rescans the table for its maximum on every
insert. An incremental max (heap) would remove this; not done.

## K. k=10 and k=100 on one searcher (d@0.95; QPS@0.95 in brackets)

| corpus | k | dense + HSP | Vamana | PiPNN (det) | composed | hnswlib M16 (level 0, flat) |
|---|---|---|---|---|---|---|
| GloVe | 10 | **9,172** (14.6k) | 9,204 (17.9k) | 13,330 (10.8k) | 11,444 (10.4k) | 12,919 (7.1k) |
| | 100 | **20,228** (6.6k) | 20,619 (6.7k) | 28,676 (4.1k) | 24,418 (5.5k) | — |
| SIFT | 10 | 1,175 (75k) | **1,106** (135k) | 1,230 (110k) | 1,165 (98k) | 1,184 (97k) |
| | 100 | 2,422 (49k) | 2,978 (44k) | 2,571 (45k) | **2,357** (49k) | 2,363 (48k) |
| GIST | 10 | **4,268** (2.1k) | 5,281 (3.3k) | 4,556 (3.2k) | 4,418 (3.0k) | 6,440 (1.7k) |
| | 100 | 7,509 (1.7k) | 8,318 (1.6k) | 7,603 (1.7k) | **7,218** (1.8k) | 11,153 (1.2k) |
| Deep-10M | 10 | **2,133** (65k) | 2,150 (81k) | 2,431 (63k) | 2,277 (59k) | 2,278 (50k) |
| | 100 | **4,084** (26k) | 4,807 (23k) | 4,761 (21k) | 4,596 (22k) | 4,580 (28k) |
| Wikipedia | 10 | 3,840 (4.1k) | 4,246 (4.1k) | — | **3,750** (T1) | 4,225 (3.4k) |
| | 100 | **8,030** | 8,666 (1.8k) | — | 8,713 (T1) | 9,629 (1.7k) |
| Deep-100M | 10 | **3,677** (38.6k) | 4,047 (37.8k) | — | 4,108 (T1, rich) | 4,133 (32.7k) |
| | 100 | **7,198** (17.6k) | 7,369 (17.2k) | — | 7,795 (T1, rich) | 8,790 (14.0k) |

Vamana on Deep-100M reproduces the published 4,047 / 10,547 to the digit.
hnswlib builds (M16, efC 200, 64 threads): GloVe 50 s, SIFT 30 s, GIST
182 s, Deep-10M 401 s, Wikipedia 1,642 s, Deep-100M 5,684 s; its native
recall/QPS ladders are in `K_*_hnsw16.log`. **The hnswlib column is a lower
bound on hnswlib**: ParlayANN searches its level-0 graph flat from point 0,
without the hierarchy; QPS comparisons with hnswlib must use the native
ladders.

Reading: at k=100 the dense build is first on GloVe, Deep-10M, Wikipedia
and Deep-100M, and within 3% of the composed build on SIFT; on GIST the
composed build leads by 4%. Vamana is never first at k=100. At equal
distance counts Vamana's graphs give more QPS (GloVe 17.9k vs 14.6k at
~9.2k distances); the cause (degree, memory layout) is not measured, so
the paper's cost metric stays distances, with QPS reported alongside.

## A. HSP spine with automatic sample size, and orphan repair

`--dense-spine-s 0`: start at max(1024, sqrt n), double |S| until every
vertex is reachable from the entry. First rule hung on GIST (killed after
4 h): the pruned graph leaves vertices with **no in-edge** ("orphans"); the
HSP spine adds edges among S only, so no sample size reaches them. Orphans:
GloVe 0, SIFT 0, Deep-10M 940 (0.009%), GIST ~1,980 (0.19%) plus ~60
vertices reachable only through orphans.

Fix (`--dense-spine-repair 1`, off by default so earlier graphs reproduce):
each orphan gets an in-edge from its own nearest kept out-neighbour (no
distance evaluations); and the doubling stops when a round adds fewer than
n/10^4 reachable vertices (cap 65,536).

| corpus | rule | final |S| | spine s | d@0.95 | d@0.99 | k=100 d@0.95 |
|---|---|---|---|---|---|---|
| GloVe | auto (no orphans) | 1,087 | 2.4 | 9,135 | 24,816 | — |
| SIFT | auto | 1,024 | 1.3 | 1,085 | 2,045 | — |
| Deep-10M | auto | 3,162 | 21.5 | 2,151 | 4,519 | — |
| Deep-10M | s=10k + repair (938) | 10,000 | 28.1 | 2,148 | 4,568 | 4,081 |
| GIST | auto, no repair (cap hit) | 65,536 | 210 | 4,321 | 11,249 | — |
| GIST | auto + repair (1,982) | 2,048 | 2.5 | 4,290 | 11,109 | 7,530 |
| GIST | s=10k + repair | 10,000 | 4.9 | 4,276 | 11,114 | 7,519 |
| GIST | s=10k, no repair (T5) | 10,000 | 4.3 | 4,268 | 11,098 | 7,509 |

Reading: the automatic rule picks ~sqrt(n) on real data (1,024-3,162) and
8,192 on the 800-cluster smoke set, at no-spine quality. **Orphan repair
does not change quality and does not lift GIST's recall ceiling**: max
recall on the ladder stays 0.9962 (SAT-spined: 0.9977). The hypothesis that
orphans caused the SAT gap at the top of the recall range is refuted; the
cause is open.

## G. GloVe: memberships close the gap to the dense build

Composed (deterministic PiPNN, mst 10, our ending):

| leaves per point | table | alpha | d@0.95 | d@0.99 | composed build (det merge) |
|---|---|---|---|---|---|
| 30 (default) | 160 | 1.0 | 12,284 | — | ~17 s |
| 60 | 400 | 1.0 / 1.2 | 9,971 / 12,525 | 25,400 / — | 81 s |
| 90 | 600 | 1.0 / 1.2 | 9,591 / 12,355 | 24,481 / — | 119 s |
| **120** | 800 | 1.0 / 1.2 | **9,290** / 12,250 | **23,911** / — | 166 s |
| dense + HSP | — | 1.0 | 9,172 | 24,833 | 96 s |

At 120 leaves per point the composed build is within 1.3% of dense at 0.95
and 3.7% better at 0.99. Alpha 1.2 is harmful on these rich pools (as T2).
The build times above use the deterministic merge (1.8x slower on large
tables). With PiPNN's original merge (`run_glove_timing.sh`, one run each;
composed time = PiPNN build - its final prune + fg prune incl. spine):

| leaves per point | PiPNN build | composed build | d@0.95 | d@0.99 | QPS@0.95 |
|---|---|---|---|---|---|
| 90 | 58.0 s | **59.8 s** | 9,539 | 24,306 | 11.1k |
| 120 | 75.6 s | **75.0 s** | **8,956** | **23,832** | 14.6k |
| dense + HSP | — | 96 s | 9,172 | 24,833 | 14.6k |

**At 120 leaves per point the composed build beats the dense build on
GloVe (-2.4% at 0.95, -4.0% at 0.99) in 0.78x its time.** The GloVe regime
of C5 is closed: it was a membership deficit of PiPNN's defaults (30 leaves
per point), not a property that requires the dense candidate stage. The
deterministic and original-merge runs at 120 leaves differ by 3.6% at 0.95
(9,290 vs 8,956), at the edge of PiPNN's ±3% run-to-run band; one run each.
