# The permutation-prefix trie partition — GIST-960, d0, 2026-09-29

**Scheme (author):** every object's k-permutation over a random permutant
set; a prefix trie cut where a subtree has at most B objects (hub cells
split by the next permutant; children under B_min merged into a residual
block); the cut subtrees are the blocks; memberships = the object's own
block plus the blocks reached by the adjacent-swap variants of its prefix
(PP-Index's footrule neighbours). Candidate rows = union of block members,
through `fg --dense-cands --harvest-cand 200` (the heap), ParlayANN
grading. `bench/perm_cands.py`, chain `bench/d0_perm.sh`, logs `results/perm/`.

## The partition (|S| 1,000 permutants, k 8, B 1,000, B_min 100, l_max 4)

2,554 blocks (729 at depth 1, 1,787 at depth 2, 38 at depth 3); size mean
392, median 194, p99 2,640, max 4,492; **all pairs inside every block =
0.55 G** (the leaf stage: 26 G). The cut does what it was meant to: hub
cells are held down and the blocks are GEMM-sized.

## Results, with the 200-nearest heap

| memberships | cands / point | compl. | deg | d@0.90 | d@0.95 | d@0.97 |
|---|---:|---:|---:|---:|---:|---:|
| own block only | 1,088 | 0.106 | 14.6 | 14,049 | — (max recall 0.94) | — |
| own + 3 swap variants (2.5 found) | 2,459 | 0.175 | 19.1 | 6,886 | 11,083 | 13,644 |
| own + 6 swap variants | stopped: found 1.48 of 6 variants, identical memberships to the 3-swap arm | | | | | |
| *reference:* leaf k-means L700/m5 | 53k → 200 | 0.328 | 18.3 | 2,898 | 4,485 | 6,055 |
| *reference:* count k_b32 top-4000 → 200 | 4,000 | 0.330 | 19.7 | 2,929 | 4,518 | 5,971 |
| *reference:* exact ceiling | 10⁶ → 200 | 0.336 | 17.9 | 3,065 | 4,601 | 6,025 |

**Refuted at the criterion (completeness < 0.25).** A single prefix block
holds a tenth of a point's true neighbours (0.106) and the swap variants
raise it to 0.175: the footrule-nearest prefixes are not where the missing
neighbours are. The pool has the right *shape* for a GEMM (0.55 G pairs in
blocks of hundreds) and the wrong *content* — it is the m = 1-2.5 nearest-
leader pool of Table 2 (0.261 ceiling at m = 1 on GloVe), and nothing about
the ordering repairs the boundary loss. What repairs it, measured twice
now, is *many* memberships — 30 nearest leaders (random L90000/m30:
0.336, 4,419) or the count top-4,000 over 32 witnesses (0.330, 4,518) —
i.e. robustness to boundaries, which is exactly what discarding the order
buys. The permutation's extra information is useful for ranking two
objects, not for deciding which few blocks to put an object in.

## Cost note

Permutations 27 s (1 G pairs, numpy GEMM); the trie cut is instantaneous;
the union expansion in numpy is slow (1,566-4,711 s) and irrelevant to the
verdict.

## Why more inversions cannot help, and what would (2026-09-29, after the arms)

The 6-swap arm found the same 1.48 variant blocks per object as the 3-swap
arm (swaps beyond the cut depth land in the object's own block; swapped
prefixes that no object has do not exist as blocks), so it was stopped
before grading. The mechanism is distance concentration: every neighbour
edge sits at 1.05-1.4x the tenth-neighbour distance while the permutants
are rank-500,000 objects, so the distances from a point to its nearest
permutants are nearly equal and their order is fragile — a nearest
neighbour can rank the first permutant fourth. A prefix commits to the side
of every bisector among the leading permutants; a witness *set* does not,
which is why MISI's loss of order is the right choice for blocking, and why
the order should be kept only for ranking (rank-weighted scoring) and for
deciding where to split a large cell.

The repair that follows is independence, not inversions: L independent
permutant sets, one size-capped trie partition each, one block per table
per object — Wang et al. 2012 / LSH-forest with a balanced cut. If tables
were independent, 0.106 per block gives 0.29 at L = 3, 0.43 at L = 5; the
pool is ~L x 1,000 candidates in GEMM-shaped blocks at L x 0.55 G pairs
(2.75 G at L = 5, against the leaf stage's 26 G and PiPNN's 7.2 G). A
weighted (soft) membership — every cell within a (1+ε) distance margin of
the nearest — is the Voronoi form of a spill tree's overlap buffer and an
adaptive version of the paper's m nearest leaders. Both are known
mechanisms; the measurable claim would be the design point (ceiling-class
quality at a third of PiPNN's pairs), if it holds. Not run.

## The fragility diagnostic (2026-09-29, `results/perm/gist_perm_diag.log`)

1,000 sampled points, their exact 10-NN over the whole base, 1,000 random
permutants, 8-permutations; ten independent permutant sets, each cut into
a trie partition (B 1,000, B_min 100).

| quantity | value |
|---|---:|
| P(true-neighbour pair shares its first permutant) | 0.222 |
| P(shares its first two, in order) | 0.054 |
| Spearman footrule between their 8-permutations (max 64) | 26.3 |
| permutants shared among the 8 | 3.31 |
| same trie block, one table | 0.108 |
| covered by the best of L tables: L = 2 / 3 / 5 / 10 | 0.191 / 0.257 / 0.366 / 0.547 |
| if tables were independent: L = 5 / 10 | 0.434 / 0.680 |

The order is as fragile as the argument said: a nearest neighbour shares
your first permutant one time in five, your first two one time in twenty,
and only 3.3 of your 8 permutants at all. Independent tables help but are
correlated (0.366 at five against 0.434 if independent); ten tables cover
55% of neighbour pairs for 5.5 G pairs, which is already most of PiPNN's
7.2 G. The curve says the design converges on PiPNN's cost at PiPNN's
pool, not below it: coverage buys pairs at the same rate any partition
does, because coverage *is* measure. The one construction that escaped the
measure law was the count ranking, and it did so by an integer
pre-selection whose cost sits in the merge and the random-access
verification, not in the GEMM.

## The L = 5 table arm — stopped (2026-09-29, 18:30)

Stopped in its candidate expansion after 2.7 h at the author's suggestion:
its result is fixed by the diagnostic (coverage 0.366 of true-neighbour
pairs at 2.79 G pairs, five memberships per point), which predicts an
edge completeness near 0.27 and a graph short of the 4,485 bar, and the
enlarged-cell diagnostic (`cell-adjacency-FINDINGS.md`) then closed the
whole partition question under the measure law. Nothing further in this
direction is planned.
