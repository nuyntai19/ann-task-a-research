# The localizer construction, single-id form — GIST-960, d0, 2026-09-25/26

**Author's scheme (2026-09-25):** no k-means. A random sample S; the inner
index is only a *localizer* that returns each object's k nearest sample
points; the k-group is hashed and collisions define the local
neighbourhood; all pairs inside a neighbourhood go through the dense GEMM
tile. With single sample ids as the hash key this is exactly fg's
`--dense-kmeans 0 --dense L --dense-m k`: L random leaders, every object in
the cells of its k nearest, all pairs per cell. Chain `bench/d0_random.sh`,
logs `results/random/`, graded on ParlayANN like every other row.

Nominal pool P = n m²/L assumes equal cells. Random cells are not equal
(hub sample points), so the table also gives the **effective pool**, the
size-biased mean 2·(candidate pairs)/n, which is what an object actually
sees.

| arm | L | m | cell mean / max | pool nominal / effective | compl. | leaders s | cand. s | cand. G pairs | build | d@0.90 | d@0.95 | d@0.97 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| k-means L700/m5 (paper) | 700 | 5 | 7,143 / 28,204 | 36k / 53k | 0.328 | 13 | 160 | 26.4 | 4:31 | 2,898 | 4,485 | 6,055 |
| k-means L2500/m5 | 2,500 | 5 | 2,000 / 12,318 | 10k / 18k | 0.318 | 47 | 109 | 9.1 | 3:37 | 3,079 | 4,686 | 6,122 |
| random L2500/m5 | 2,500 | 5 | 2,000 / 26,851 | 10k / 35k | 0.312 | 15 | 149 | 17.7 | 3:45 | 3,200 | 4,776 | 6,252 |
| random L10000/m10 | 10,000 | 10 | 1,000 / 27,915 | 10k / 40k | 0.325 | 171 | 269 | 20.1 | 8:20 | 3,060 | 4,632 | 6,087 |
| random L25000/m30 | 25,000 | 30 | 1,200 / 42,450 | 36k / 149k | 0.337 | 435 | 821 | 74.7 | 22:26 | 3,046 | 4,450 | 6,006 |
| **random L90000/m30** | 90,000 | 30 | 333 / 25,217 | 10k / 46k | 0.336 | 1,576 | 1,364 | 23.2 | **50:37** | **2,925** | **4,419** | 6,010 |
| PiPNN (30 × ~330, size-capped, recursive) | — | 30 | ~330 / — | ~10k / 14k | 0.456 | — | — | 7.2 (leaf) | **0:35** | 2,970 | 4,548 | 6,069 |
| Vamana R64/L128 | — | — | — | — | — | — | — | 19.6 | 10:33 | 3,191 | 5,281 | 7,445 |

## What it says

1. **The single-id localizer form works, and it is PiPNN with exact
   assignment.** Random L 90,000 / m 30 — thirty memberships in 333-point
   cells — gives d@0.95 = 4,419, the best GIST number of the day (paper's
   k-means build 4,485, PiPNN 4,548), at a nominal pool 3.6x smaller than
   the paper's. On GIST, random leaders with many memberships match or
   beat Lloyd leaders with few, which is what the GloVe pool table already
   said (0.974 for 20 × 3,450 random against 0.856 for 5 × 240 at 17%)
   and what §4's text currently denies.
2. **But quality still tracks the effective pool, with a modest bonus for
   many memberships.** 18k → 4,686; 35-40k → 4,632-4,776; 46-53k →
   4,419-4,485; 149k → 4,450. The random/m30 point sits ~2% below the
   k-means/m5 point at equal effective pool; that is the whole quality
   gain of the split, on this corpus. PiPNN gets 4,548 from an effective
   pool of 14k — its recursive, size-capped cells are better shaped than
   a flat random Voronoi with hubs.
3. **The cost is entirely in things PiPNN engineered and fg has not:**
   * the membership scan is n·L: 90 G distances, 1,576 s, at the leader
     kernel's 0.057 G/s (it is a scalar loop; a GEMM would be ~10x faster,
     a localizer index ~1000x — PiPNN's recursive sketch assigns 30
     memberships in seconds);
   * **hub cells**: the largest random cell holds 25,217 objects against a
     mean of 333 (42,450 vs 1,200 at L 25,000), so the candidate stage runs
     23 G pairs where equal cells would cost 5 G, and the effective pool is
     4.6x the nominal. PiPNN caps cells at 1,024 by recursive splitting;
   * the tile on 333-point cells: 23.2 G pairs in 1,364 s = 0.017 G/s,
     ten times below its large-leaf rate. PiPNN's leaf stage is a plain
     GEMM (EigenKNN).
   Fixing all three is a build in the tens of seconds at this quality —
   which is PiPNN's number. The single-id form therefore converges on
   PiPNN's design; what it adds is exact assignment (worth ~3% at 0.95 on
   GIST) and the dense construction's ending and spine.
4. **The pool-size correction for tab:gist stands on its own:** k-means
   L 2,500 / m 5 is 4,686 at 9 G pairs and 217 s, 11% ahead of Vamana at
   a third of the paper's candidate work.

## What was not tested

The subset-hashed form (pairs or triples of sample ids as the key), which
is the part of the scheme with no existing flag. It is a finer partition
than any single-id cell and the natural way to split hub cells: a hub's
25k objects fall into many (hub, second-nearest) buckets. That is where
the idea stops being PiPNN. Prototype path: signatures (GEMM, exists in
`bench/solo_cands.py`) → bucket by C(k,2) keys → per-object union of
bucket members → `fg --dense-cands` for a quality answer; the bucketed
GEMM in fg only if quality holds.

## Edge diagnostic (`results/random/edge_diag_random.log`, 1,000 sources, exact ranks)

| graph | deg | edges rank ≤ 10 | ≤ 100 | ≤ 1k | > 10k | > 100k | true-10 covered |
|---|---:|---:|---:|---:|---:|---:|---:|
| k-means L700/m5 (paper) | 18.9 | 0.176 | 0.506 | 0.845 | 0.038 | 0.005 | 0.332 |
| k-means L2500/m5 | 19.3 | 0.167 | 0.477 | 0.850 | 0.037 | 0.005 | 0.321 |
| random L10000/m10 | 18.9 | 0.176 | 0.502 | 0.843 | 0.039 | 0.005 | 0.333 |
| random L25000/m30 | 18.4 | 0.185 | 0.530 | 0.845 | 0.040 | 0.005 | 0.341 |
| random L90000/m30 | 18.7 | 0.181 | 0.519 | 0.845 | 0.039 | 0.005 | 0.340 |
| PiPNN | 33.7 | 0.136 | 0.398 | 0.676 | 0.129 | 0.026 | 0.456 |

Every cell-built graph has the same edge profile to within a point,
whatever made the cells (Lloyd or random) and however many memberships:
85% of edges within rank 10³, 4% beyond 10⁴. The α-prune over a
geometric cell produces one kind of graph, and the two random/m30 arms
have slightly *more* near edges (0.18-0.19 at rank ≤ 10, 0.52-0.53 at
≤ 100) than the paper's build, matching their slightly better d@0.95.
Contrast the count-ranked pools of `solo-FINDINGS.md` (0.08-0.10 at
≤ 10, 12-18% beyond 10⁴) and PiPNN, whose graph is a different object:
twice the degree, more true neighbours, and 13% far edges.
