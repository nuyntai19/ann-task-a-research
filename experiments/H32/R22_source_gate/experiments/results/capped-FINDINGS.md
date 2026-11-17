# The heap was the confound: signature pools with the nearest-200 cap, and the exact ceiling — 2026-09-29, d0

**Supersedes the conclusions of `solo-FINDINGS.md` and `hash-FINDINGS.md`.**
Every signature-pool arm in those notes handed fg's prune the whole
candidate row (500-8,000 ids ranked by count or bucket size), whereas the
leaf build prunes only each point's 200 nearest by distance (the stage-3
heap). `--harvest-cand 200` caps the prune at the 200 nearest candidates,
which is the heap. Chain `bench/d0_capped.sh`, logs `results/capped/`,
ParlayANN grading as always.

## GIST-960, count pool (MISIFU, α 2%, k_b 32, top-4000 by shared count)

| pool → prune | cands / point | compl. | deg | prune evals | d@0.90 | d@0.95 | d@0.97 |
|---|---:|---:|---:|---:|---:|---:|---:|
| leaf k-means L700/m5 → heap 200 (paper) | 53k eff. → 200 | 0.328 | 18.3 | 0.75 G | 2,898 | 4,485 | 6,055 |
| random L90000/m30 → heap 200 | 46k eff. → 200 | 0.336 | 18.7 | 0.75 G | 2,925 | 4,419 | 6,010 |
| count k_b32 C4000 → prune all 4,000 (old) | 4,000 | 0.403 | 49.5 | 12.4 G | 3,730 | 5,510 | 6,974 |
| **count k_b32 C4000 → nearest 200 → prune** | 4,000 → 200 | 0.330 | 19.7 | 4.6 G | 2,929 | **4,518** | **5,971** |
| PiPNN | 14k eff. | 0.456 | 33.7 | — | 2,970 | 4,548 | 6,069 |

Same graph family as the leaf build (degree 19.7, completeness 0.330,
d@0.95 within 0.7%, d@0.97 1.4% better) from a pool thirteen times
smaller. The "region vs. signature" mechanism of the earlier notes was an
artefact of pruning an unheaped row: the far members a count ranking
admits are far *by distance*, and a distance heap removes them before the
prune ever sees them. What the prune needs is the 200 nearest of *any* pool
that contains them; it does not care how the pool was assembled.

Cost accounting for this arm: the 4,000 candidate distances per point are
random gathers (4.6 G in 377 s, 12 M/s) against the leaf build's 26 G GEMM
pairs in 160 s. The pool is 13x smaller and costs 2.4x more wall on the
present kernels; a block-shaped version of the same pool (the pair-bucket
partition, next arm) is what would make it GEMM-able.

## GloVe, the exact-kNN ceiling with the identical ending

`--dense 1 --dense-m 1`: one leaf of all 1,183,514 points, every pair
evaluated (700 G pairs, 420 s at 1.67 G pairs/s, 4.7 GB resident), 200
nearest per point → the paper's ending and spine.

| pool | deg | compl. | d@0.95 | d@0.97 |
|---|---:|---:|---:|---:|
| **exact 200-NN (ceiling)** | 50.7 | 0.652 | **8,652** | **12,330** |
| k-means L240/m5, 9% pool (paper) | 18.7 | 0.613 | 9,069 | 13,322 |
| Vamana R100/L200 | 51.1 | — | 9,204 | 13,325 |

The whole pool question on GloVe is worth 4.6% at 0.95 and 7.4% at 0.97:
the 9% k-means pool is 95% of the way to the exact pool, and Vamana is 6%
above the ceiling. (Note for the paper: fg's "completeness" is the fraction
of a point's true 10-NN among its *final out-edges*; with an exact pool it
is 0.652, so it is an ending statistic, not a pool recall.)

## Edge diagnostic of the capped count graph (`results/capped/edge_diag_capped.log`)

| graph | deg | edges rank ≤ 10 | ≤ 100 | ≤ 1k | > 10k | > 100k | true-10 covered |
|---|---:|---:|---:|---:|---:|---:|---:|
| leaf k-means L700/m5 (on record) | 18.9 | 0.176 | 0.506 | 0.845 | 0.038 | 0.005 | 0.332 |
| count k_b32 C4000, unheaped (on record) | 49.5 | ~0.08 | ~0.27 | ~0.57 | ~0.17 | ~0.03 | 0.40 |
| **count k_b32 C4000 → nearest 200** | 20.2 | 0.164 | 0.472 | 0.854 | 0.034 | 0.004 | 0.333 |

The leaf profile, to the point. The far tail (17% of edges beyond rank
10⁴) was the unheaped prune's doing; the heap removes it and the same pool
yields the same kind of graph as a geometric cell.

## GIST-960, pair-bucket pool (j 2, k 10, union of 45 buckets, ~2,611 candidates/point) with the cap

| pool → prune | cands / point | compl. | deg | d@0.90 | d@0.95 | d@0.97 |
|---|---:|---:|---:|---:|---:|---:|
| pair j2 k10 → prune all (old) | 2,611 | 0.353† | 43.0 | 4,592 | 6,860 | 8,814 |
| **pair j2 k10 → nearest 200 → prune** | 2,611 → 200 | 0.285 | 19.8 | 3,627 | **5,503** | 7,328 |
| count k_b32 C4000 → nearest 200 | 4,000 → 200 | 0.330 | 19.7 | 2,929 | 4,518 | 5,971 |
| leaf k-means L700/m5 → heap 200 | 53k → 200 | 0.328 | 18.3 | 2,898 | 4,485 | 6,055 |

† the unheaped run's completeness counts true neighbours among 43 edges;
not comparable.

The heap fixes the graph's shape (degree 19.8, the leaf family) but not
the pool's content: the pair-bucket union at k 10 holds fewer of the true
neighbours (0.285 among the final edges against 0.33) and lands 23% above
the leaf build at 0.95. The union of 45 pair-keyed buckets is a *more
selective* pool than the top-4,000 by count over the same signatures, not a
better one; at k 10 it is simply too small. The block-shaped form has a
second problem that no k fixes: pair-keyed buckets have median size 2 and
mean 7-10 (`hash-FINDINGS.md`), which is not a shape a GEMM can use.
Single-id keys (posting lists, mean 400-1,600) are the GEMM-shaped
partition, and that form is the random-leader build (4,419).

**Where this leaves the shared-neighbour idea.** As a *pool*: it works,
with the heap (count top-4,000 → 4,518). As a *partition for SGEMM*: the
pair keys are too fine; the single-id keys are the existing random-leader
form; nothing in between has been found. As a *cost story* on the CPU: the
count pool needs 13x fewer candidate distances (4 G vs 26 G) but they are
random gathers at 12 M/s against GEMM pairs at 165 M/s, so it costs 2.4x
more wall today (377 s vs 160 s); it wins only if verification gets
cheaper — SOLO's SQ4/2-bit screen (8x fewer bytes per candidate) is the
obvious lever and is not tested here.

## GIST-960, the exact-kNN ceiling with the identical ending

`--dense 1 --dense-m 1`: all 5·10¹¹ pairs (1,914 s at 0.26 G pairs/s on the
tile, 8.4 GB resident), 200 nearest per point → ending → spine.

| pool → 200 nearest → prune | cands / point | compl. | deg | d@0.90 | d@0.95 | d@0.97 |
|---|---:|---:|---:|---:|---:|---:|
| **exact 200-NN (ceiling)** | 10⁶ → 200 | 0.336 | 17.9 | 3,065 | **4,601** | 6,025 |
| leaf k-means L700/m5 (paper) | 53k → 200 | 0.328 | 18.3 | 2,898 | 4,485 | 6,055 |
| random L90000/m30 | 46k → 200 | 0.336 | 18.7 | 2,925 | 4,419 | 6,010 |
| count k_b32 C4000 → 200 | 4,000 → 200 | 0.330 | 19.7 | 2,929 | 4,518 | 5,971 |
| PiPNN (its own ending) | ~14k | 0.456 | 33.7 | 2,970 | 4,548 | 6,069 |
| Vamana R64/L128 α1.2 (its own) | search | — | 36.1 | 3,191 | 5,281 | 7,445 |

**On GIST the pool is not the lever at all.** The exact pool gives 4,601;
every pool we built lands within ±3% of it, two of them *below* it (a pool
that is not exactly the 200 nearest admits a few farther candidates that
the α = 1 prune turns into slightly better navigation edges). With the
200-nearest heap and this ending, a 3.6% k-means pool, a 4.6% random
30-membership pool and a shared-neighbour top-4,000 are all the same
graph, and the exact pool is no better. What separates the rows of this
table from Vamana (15%) is the candidate source plus the ending (exact-ish
candidates, α = 1, 200 nearest) against search-harvested candidates with
α = 1.2 — not the pool's measure. On GloVe the ceiling was 4.6% above the
9% k-means pool; on GIST there is nothing above it.

**Consequence for the family analysis.** The pool's *measure* buys quality
only where the cell pool falls short of the exact one (GloVe, 4.6%; the
Deep corpora at 10⁷-10⁸ presumably more, unmeasured); on GIST any pool
that contains the near neighbours is enough, and the heap makes any pool
do. The cost of the candidate stage — 500 G exact, 26 G leaf, 4 G count —
is then the only thing that differs between constructions of equal
quality, and on the CPU the 26 G GEMM (160 s) is the cheapest of the three
in wall time; the 4 G random gathers (377 s) would win only with a cheaper
per-candidate verification.
