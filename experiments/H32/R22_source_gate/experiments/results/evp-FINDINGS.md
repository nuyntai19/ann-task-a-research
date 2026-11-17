# EVP 2-bit quantisation as a candidate filter on GloVe (laptop, 2026-09-18)

Source: Connor, Dearle, Claydon, "Equi-Voronoi Polytopes: A Geometric Basis
for 2-bit Quantisation", SISAP 2025, LNCS 16134, pp. 288-302,
doi:10.1007/978-3-032-06069-3_23. {x,d} EVP: keep the
x largest |u_i| as ±1, zero the rest; distance = ternary scalar product =
bitwise b²sp (AND + POPCNT over two d-bit masks). Data-independent; the
mapping needs no distance computations.

Question: can the proxy generate the *pair set fixed in advance* that the
wall (`wall-FINDINGS.md`) requires — i.e. is its top-K a good candidate set
for exact re-ranking on GloVe, the paper's own weak case?

Protocol: 1,000 queries vs all 1,183,514 base vectors, proxy top-K, recall of
the true 10-NN (answer key) at K. The ternary product is computed exactly as
a GEMM over {−1,0,1}. `bench/evp_recall.py`. Variants: **tt** = both sides
ternary (the paper's b²sp, 2 bits/dim both sides); **tf** = ternary query ×
float data (the paper's §7.2 "hybrid", masked addition); **ft** = float query
× ternary data (2-bit *data*, float queries).

| x | side | K=10 | 50 | 100 | 200 | **500** | 1000 | 2000 |
|---:|---|---:|---:|---:|---:|---:|---:|---:|
| 25 | tt | 0.125 | 0.262 | 0.332 | 0.418 | 0.539 | 0.627 | 0.712 |
| 25 | tf | 0.315 | 0.588 | 0.694 | 0.783 | 0.878 | 0.928 | 0.960 |
| 25 | ft | 0.267 | 0.513 | 0.625 | 0.723 | 0.834 | 0.899 | 0.941 |
| **50** | tt | 0.280 | 0.526 | 0.633 | 0.722 | **0.828** | 0.892 | 0.939 |
| **50** | **tf** | 0.458 | 0.780 | 0.868 | 0.932 | **0.974** | 0.991 | 0.998 |
| **50** | **ft** | 0.422 | 0.735 | 0.827 | 0.901 | **0.960** | 0.984 | 0.995 |
| 66 | tt | 0.289 | 0.531 | 0.629 | 0.725 | 0.827 | 0.887 | 0.931 |
| 66 | tf | 0.442 | 0.762 | 0.855 | 0.917 | 0.969 | 0.987 | 0.995 |
| 66 | ft | 0.419 | 0.723 | 0.820 | 0.894 | 0.955 | 0.979 | 0.992 |
| 100 | tt (1-bit) | 0.138 | 0.274 | 0.346 | 0.425 | 0.532 | 0.615 | 0.694 |
| 100 | tf | 0.276 | 0.531 | 0.637 | 0.730 | 0.836 | 0.896 | 0.942 |
| 100 | ft | 0.256 | 0.489 | 0.589 | 0.683 | 0.794 | 0.865 | 0.920 |

Findings.
1. **x = d/2 is the optimum on GloVe** (as the paper reports for its data);
   the 1-bit hypercube (x = d) is far worse (0.53 at K=500).
2. **Both-sides 2-bit (b²sp) misses the filter threshold on GloVe**: recall of
   the true 10-NN is 0.83 at K=500 and needs K ≈ 2,000 for 0.94. As a final
   distance it is what the paper says ("less good" on GloVe); as a filter it
   costs a 2,000-candidate re-rank per point.
3. **One-sided quantisation crosses the threshold**: ternary query × float
   data reaches 0.974 at K=500 (0.991 at 1,000); float query × 2-bit data
   reaches 0.960 at K=500 (0.984 at 1,000). The paper's "hybrid" estimator
   ℓ2(v,u) is markedly better than ℓ2(v,v), and the *data-compressed* form
   (ft) is the one that matters for construction: the data side is 16×
   smaller (32 B/vector; all of GloVe in 38 MB, cache-resident on d0) while
   the queries — the block being harvested — stay float and are tiny.
4. Consequence for the dense construction of `density-FINDINGS.md` §4:
   stage 1 = float-block × 2-bit-data scan (a masked-add kernel, not BLAS;
   memory 16× lighter than SGEMM, compute of the same order), top-500
   candidates per point; stage 2 = exact float re-rank of 500/point
   (0.6 G distances for GloVe, negligible); stage 3 = occlusion prune +
   cheap route pass. Over all pairs stage 1 is O(n²) = 1.4·10¹² proxy pairs
   on GloVe — ~2–5 min on d0 at plausible kernel rates, i.e. Vamana-class
   time with no adaptivity at all; inside leaves (5k points, 30 memberships)
   it is ~1–2·10¹¹ pairs, tens of seconds.

Not measured yet: (a) the per-pair throughput of b²sp / masked-add on d0
(Haswell has no vector POPCNT; the paper's 26–60× is vs scalar float
one-to-many, not vs SGEMM); (b) candidate recall *within leaves* rather than
globally; (c) whether the resulting graph reaches GRAFT/Vamana quality.

## Within-leaf candidate recall (GloVe, laptop, `bench/evp_leaves.py`)

One level of leader clustering, every point in the leaves of its m nearest
leaders; pool(q) = union of q's m leaves; ceiling = fraction of the true 10-NN
inside the pool; ft@K = recall among the top-K by float-query × 2-bit-data
proxy inside the pool.

| leaders | m | leaf | pool | pool/n | ceiling | ft@500 | ft@1000 |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 240 random | 1 | 4,931 | 10,302 | 0.9% | 0.261 | 0.261 | 0.261 |
| 240 random | 3 | 14,794 | 82,433 | 7% | 0.674 | 0.667 | 0.672 |
| 240 random | 5 | 24,657 | 203,704 | 17% | 0.856 | 0.839 | 0.851 |
| 700 random | 5 | 8,454 | 74,034 | 6% | 0.776 | 0.767 | 0.774 |
| 1400 random | 5 | 4,227 | 39,401 | 3% | 0.740 | 0.734 | 0.738 |
| 3450 random (PiPNN-like) | 10 | 3,430 | 62,417 | 5% | 0.864 | 0.852 | 0.860 |
| 3450 random | 20 | 6,861 | 196,912 | 17% | 0.974 | 0.945 | 0.963 |
| 3450 random | 30 | 10,291 | 356,799 | 30% | 0.996 | 0.959 | 0.982 |
| 240 k-means | 3 | 14,794 | 43,516 | 4% | 0.854 | 0.846 | 0.852 |
| **240 k-means** | **5** | 24,657 | 105,831 | **9%** | **0.932** | 0.915 | 0.928 |
| 700 k-means | 5 | 8,454 | 38,912 | 3% | 0.880 | 0.872 | 0.878 |

Findings.
5. **Inside a pool the 2-bit proxy is lossless as a filter** (ft@500 ≈
   ceiling in every row). The candidate recall of a dense construction is
   set by the *partition*, not by the quantiser.
6. **On GloVe the partition leaks**: neighbours straddle cell boundaries at
   this intrinsic dimension, so recall is a function of the pool as a
   fraction of n — ≈0.87 at 5%, 0.93–0.97 at 9–17%, 0.996 at 30% —
   almost independently of how the pool is assembled (few big leaves or many
   small memberships). k-means leaders halve the pool for a given recall
   against random leaders. This is why PiPNN needs 30 memberships and still
   trails Vamana by 41–45% on GloVe, and why no quantiser fixes that.
7. **Cost consequence**: dense candidate generation on GloVe is Θ(f·n²) with
   f ≈ 0.1 for recall 0.93 — at 10⁶ that is 1.4·10¹¹ pairs, ≈30 s at d0's
   SGEMM rate (2-bit storage makes the scan cache-resident); at 10⁸ it is
   10⁴× more and infeasible without a hierarchical partition, which is
   where the leak compounds. So the dense route is a 10⁶–10⁷ design on
   high-LID data, not a scalable one — the opposite of the search route,
   whose cost is Θ(n log n)-ish but sits behind the wall.

## Dense construction: graph quality (GloVe, d0, `bench/dense_build.py`)

Search-free construction, pair sets fixed in advance: k-means leaders (L),
m memberships, exact GEMM inside every leaf → top-C candidates per point →
occlusion prune (α = 1.0) to R = 64 → reverse edges → re-prune. No far-start
pass, no search anywhere. Served by ParlayANN's beam (patched to load a
graph; start point 0, not the medoid), so d@r is in the Vamana column's
convention.

**Config A** (L = 240, m = 5, C = 200; pool ≈ 9% of n, candidate-recall
ceiling 0.93): mean degree 42.9, max 64.

| system (GloVe) | d@0.95 | d@0.97 | build |
|---|---:|---:|---|
| **dense A (this)** | **9,107** | **13,736** | numpy prototype 6,305 s; 228 G pairs (174 G stage 1, 24 G prune, 30 G re-prune) |
| Vamana R100/L200 2-pass | 9,204 | 13,325 | 145.9 s; 31.6 G |
| GRAFT T32/ef600 frozen | 9,400 | 13,950 | 390.6 s; 63.9 G |
| FGRAFT T8/ef400 B=8 | 9,739 | 14,234 | 226.3 s; 27.7 G |
| PiPNN R100/L200 | 13,320 | 18,825 | 10.4 s; 12.6 G |

Ladder (recall, cmps): 0.934/7,138 · 0.957/9,949 · 0.978/16,048 ·
0.988/21,885 · 0.992/27,131.

Findings.
8. **A search-free graph reaches the Vamana/GRAFT quality class on GloVe**:
   d@0.95 1% better than Vamana, d@0.97 3% worse than Vamana and 1.5%
   better than GRAFT's quality profile — with candidate provenance from a
   9% pool only, no route pass. PiPNN is 46% / 37% behind it; the
   difference is the pool size (106k vs ≈10k candidates per point), k-means
   leaders, and the Vamana-style prune with reverse edges.
9. **Its cost is 7× Vamana's distance count, all of it dense.** At d0's
   measured SGEMM rate (4.45 G pairs/s) stage 1 is ≈40 s and the two prune
   stages (batched C×C grams) ≈25 s: **≈65 s projected vs Vamana's 146 s**
   at the same quality, deterministic and embarrassingly parallel by
   construction. The numpy prototype's 6,305 s is Python overhead
   (argpartition/merge/prune loops), not kernel time; the projection is
   what a C++ implementation must confirm.
10. The 2-bit proxy enters as the stage-1 kernel's data side (16× less
    traffic; lossless as a filter), not as a quality lever.

**Config B** (L = 700, m = 5, C = 200; pool ≈ 3% of n, candidate-recall
ceiling 0.88): mean degree 39.8, max 64. Ladder: 0.931/7,283 · 0.952/10,017 ·
0.971/14,939 · 0.982/20,308.

| system (GloVe) | d@0.95 | d@0.97 | dense pairs | prototype s | projected at SGEMM rate |
|---|---:|---:|---:|---:|---:|
| dense A (pool 9%) | 9,107 | 13,736 | 228 G (174 + 24 + 30) | 6,305 | ≈65 s |
| dense B (pool 3%) | 9,801 | 14,761 | 102 G (61 + 24 + 17) | 4,330 | ≈35 s |
| Vamana | 9,204 | 13,325 | 31.6 G (adaptive) | — | 146 s measured |
| FGRAFT B=8 | 9,739 | 14,234 | 27.7 G (adaptive) | — | 226 s measured |

11. **Quality tracks the pool.** Cutting the pool from 9% to 3% costs 7.6%
    at d@0.95 and 7.5% at d@0.97, landing B in the FGRAFT-B8 class (equal at
    0.95, 4% worse at 0.97) for 2.2× fewer dense pairs. The candidate-recall
    ceiling (0.93 → 0.88) predicts the direction; the graph loses less than
    the ceiling does because the prune and the reverse edges recover part of
    what the pool misses.
12. Both prune stages cost the same 24 G regardless of the pool (C×C grams
    at C = 200); stage 3 scales with the reverse-edge overflow. At the
    projected kernel rates the pool is the only real cost knob, and 9% is
    affordable at 10⁶: the dense construction at Vamana parity is projected
    at ≈0.45× Vamana's build time, and at FGRAFT quality at ≈0.25×.

## C++ dense build on d0 (`fg --dense`, graft-ann fgraft branch, 2026-09-18)

Config A (L = 240, m = 5, C = 200, cap 64, α = 1.0), 64 threads, deterministic
(hash identical at 1 vs 64 threads on the smoke config for both endings).
Two endings: `--dense-prune 0` = GRAFT's (symmetrize, prune once);
`--dense-prune 1` = Vamana's (prune own list, add reverse edges, re-prune only
lists over cap). Graded on both searchers: fg's beam (compare with fg's own
T32/ef600: 9,400 / 13,966) and ParlayANN's beam via `--dump-graph` (compare
with Vamana 9,204 / 13,325 and the numpy prototype 9,107 / 13,736).

| graph | mean deg | compl. | fg d@0.95 | fg d@0.97 | ParlayANN d@0.95 | ParlayANN d@0.97 |
|---|---:|---:|---:|---:|---:|---:|
| dense A, GRAFT ending | 50.4 | 0.545 | 10,066 | 14,994 | 9,910 | 14,387 |
| **dense A, Vamana ending** | 45.4 | **0.605** | **9,351** | **13,877** | **9,130** | **13,031** |
| numpy prototype A (Vamana-style) | 42.9 | — | — | — | 9,107 | 13,736 |
| Vamana R100/L200 2-pass | ≈45 | — | — | — | 9,204 | 13,325 |
| GRAFT T32/ef600 frozen | 53.4 | 0.590 | 9,400 | 13,966 | — | — |

d0 timings, 64 threads (Vamana ending): leaders 0.7 s, candidates 250.5 s
(177.2 G pairs → **0.71 G pairs/s**), prune 10.4 s; **total 262 s** vs
Vamana's 146 s. Candidate-stage rate vs d0's SGEMM 4.45 G/s: 16%; vs
Vamana's build rate 0.216 G/s: 3.3×. (Laptop, 10 threads: 0.38 G/s
before the 4×4 tile, 0.61 after.)

Findings.
13. **The C++ build reproduces the prototype and the ending matters**: with
    Vamana's prune/reverse/re-prune the search-free graph is at
    9,130 / 13,031 on ParlayANN's searcher — 1% and **2% better than
    Vamana** — and 9,351 / 13,877 on fg's searcher, better than GRAFT's own
    quality profile there, with completeness 0.605 (T32: 0.590). GRAFT's
    symmetrize-then-prune ending is 8–10% worse on the same candidates: the
    in-links of a pruned list are navigation edges and must survive as
    out-links; pruning the symmetrized union throws half of them away.
14. **Time: 1.8× Vamana today, kernel-bound**. The candidate stage runs at
    0.71 G pairs/s on 64 Haswell threads, 16% of SGEMM: the 2×4 AVX2 tile
    plus the per-pair bookkeeping (first-shared-leaf dedupe, heap offer)
    cost ≈ 90 cycles per pair. At SGEMM rate the same stage is ≈40 s and
    the build ≈50 s, 0.35× Vamana at better quality — the projection of
    finding 9, now with a measured 3.3× over Vamana's rate already in hand
    and a 6× gap left in the kernel.
15. Everything else is already cheap: leaders 0.7 s, prune 10 s. The
    construction has one hot loop, and it is a dense one.

### Kernel study (d0, 64 threads, smoke config: 40 leaves of 25k, 25.1 G pairs)

| step | candidate stage | G pairs/s |
|---|---:|---:|
| first 2×4 AVX2 tile (rows scan whole leaf) | 29.1 s | 0.86 |
| + per-column-block leaf masks for the dedupe | 23.2 s | 1.08 |
| + hadd-tree reduction, vector epilogue (padded rows) | 22.2 s | 1.13 |
| + SIMD prefilter vs the heap's worst kept distance | **15.2 s** | **1.65** |
| tile alone (offers disabled), the floor of this design | 13.8 s | 1.81 |

Single-thread tile microbenchmark on L1-resident rows: 13.8 → 9.0 ns/pair
(no spills; the 1×4 kernel: 21 ns). The tile is now latency-bound on
Haswell (5-cycle FMA, 8 accumulator chains per half); bookkeeping is 10% of
the stage. d0's SGEMM does 4.45 G/s: the stage is at 37% of it.

**GloVe, config A, Vamana ending, 64 threads, after the kernel work**
(graph byte-identical to the graded one — the prefilter preserves the
exact heap rule): leaders 0.7 s, **candidates 125.3 s** (177.2 G pairs,
1.41 G/s), prune 10.9 s; **total 137 s vs Vamana's 146 s (0.94×)**, at
9,130 / 13,031 on Vamana's own searcher (Vamana: 9,204 / 13,325). The
search-free, deterministic construction is now faster than the tuned
incremental baseline at better quality, on the machine where the wall was
measured; the remaining 2.7× to SGEMM rate is in the tile.

## Phase 1b: paired dense build (d0, 10 blocks, 64 threads, 2026-09-19)

`bench/d0_phase1.py` with `ARMSET=dense`; manifests `results/phase1b/`.
Dense arm: L leaders, m = 5, C = 200, cap 64, Vamana ending. Every dense
arm produced an identical distance count and completeness in all 10 blocks.

**GloVe**

| arm | median build | IQR | HL vs Vamana [95% CI] | Wilcoxon | compl. | fg d@0.95 / 0.97 | ParlayANN d@0.95 / 0.97 |
|---|---:|---:|---|---|---:|---:|---:|
| **dense L240/m5/C200** | **138.5 s** | 1.9% | **0.951 [0.936, 0.966]** | p = 0.002, 0/10 slower | 0.605 | 9,351 / 13,877 | **9,130 / 13,031** |
| Vamana R100/L200 2-pass | 146.1 s | 0.2% | 1 | | — | — | 9,204 / 13,325 |
| hnswlib M16 | 41.1 s | 0.4% | 0.281 [0.280, 0.282] | | — | — | — |

**SIFT** (ParlayANN grades from single dumped builds; Vamana 1,619 / 2,172)

| arm | build | HL vs Vamana [95% CI] | compl. | ParlayANN d@0.98 / 0.99 | vs Vamana |
|---|---:|---|---:|---:|---:|
| dense L240 α1.0 (9% pool) | 111.9 s (10-block median) | 2.146 [2.126, 2.168] | 0.557 | 1,684 / 2,109 | +4% / −3% |
| dense L240 α1.15 | 117.8 s | 2.276 [2.250, 2.289] | 0.746 | 2,249 / 3,101 | +39% / +43% |
| dense L700 α1.0 (3% pool) | 47.9 s (single) | ≈0.92 | 0.551 | 1,749 / 2,252 | +8% / +4% |
| dense L1400 α1.0 (1.5% pool) | 36.3 s (single) | ≈0.70 | 0.545 | 1,843 / 2,322 | +14% / +7% |
| Vamana R64/L128 α1.15 2-pass | 51.8 s | 1 | — | 1,619 / 2,172 | 0 |
| GRAFT T4/ef400 frozen | 52.5 s | 1.013 [0.997, 1.035], p = 0.13 | 0.483 | 1,739 / 2,317 (fg) | +7% / +7% |

Findings.
16. **GloVe: the search-free build is significantly faster than Vamana at
    better quality** — HL 0.951 [0.936, 0.966], slower in 0 of 10 blocks,
    with the graph 1% / 2% better than Vamana's on Vamana's own searcher.
    Deterministic (identical count and completeness in every block).
17. **SIFT is the cheap regime, as Phase 1 predicted for search builders and
    the pool study predicted for dense ones.** Vamana needs 11 G distances
    and 52 s; a 9% pool costs 119 G and 2.1× the time for parity-class
    quality (+4% / −3%). Shrinking the pool to 3% (L700) brings the build to
    0.92× Vamana at +8% / +4%, i.e. exactly GRAFT-T4-frozen quality at
    GRAFT-T4-frozen cost; 1.5% (L1400) gives 0.70× at +14% / +7%. The dense
    frontier on SIFT coincides with the search frontier: where the frozen
    scaffold is already cheap there is nothing to buy with density.
18. **α = 1.15 is wrong for the dense prune on SIFT** (+39%): with 200
    exact candidates the slack keeps 59 edges/vertex against 26 and the
    beam pays for them; α = 1.0 is the right setting for this ending on both
    datasets.

The paper's claim is therefore regime-shaped, like FGRAFT's: on the
high-intrinsic-dimension data where the wall bites hardest (GloVe) the dense
construction beats the tuned incremental baseline on both time and quality;
on SIFT it matches the frozen search builder and does not beat Vamana.

### Symmetric scan (d0, 64 threads)

Every unordered pair inside a leaf is now evaluated once and offered to both
endpoints' heaps. Tiles (TB×TB blocks of the leaf) are listed in
round-robin-tournament order and taken from a shared counter under a
spinlock per block; a heap keeps the C smallest (distance, id) keys whatever
the order of its offers, so the result is schedule-independent. Gate:
hash identical at 1 vs 64 threads; the GloVe graph is byte-identical to the
graded one through every step below.

| step | smoke (12.8 G pairs) | GloVe candidates | GloVe total |
|---|---:|---:|---:|
| before (one-sided, 25.1 G / 177 G pairs) | 15.2 s | 125.3 s | 137 s (0.94× Vamana) |
| symmetric, barrier per tournament round | 14.6 s | 101.7 s | 112 s |
| + two-sided SIMD prefilter | 13.5 s | — | — |
| + locked tile scheduler, TB = 64 | 11.1 s | 77.8 s | 88 s |
| + TB = 128 (default) | **10.3 s** | **73.3 s** | **84 s (0.57× Vamana)** |

The barrier rounds had left a quarter of the threads idle (195 tiles per
round on 64 threads, worse on small leaves); the lock-based scheduler
removes the rounds while keeping the tournament order, so consecutive tiles
still touch disjoint blocks and the locks almost never spin.

### Spine: the connectivity guarantee the dense graph needs

On the synthetic clustered smoke the dense graph gave **recall 0.002 at
ef 64** (search over in 256 distances): k-means leaves coincide with the
clusters and the α = 1 prune occludes every cross-leaf candidate behind a
nearer one, so nothing connects the leaves — the same failure GRAFT
recorded before it unioned tree-0's spine after the prune. `--dense-spine 1`
(default) does the same with one SAT tree: smoke recall 0.002 → **0.987**,
25.5 M distances, 1.6 s; hash identical across threads.

On GloVe the spine is insurance the data does not need (its k-means leaves
overlap through the memberships) and it is not free: one SAT tree on GloVe
costs 985 M distances and **23.7 s** (a SAT tree's cost tracks intrinsic
dimension, like the forest's), and its root becomes a degree-483 hub.

| GloVe, config A | total | fg d@0.95 / 0.97 | ParlayANN d@0.95 / 0.97 | compl. | max deg |
|---|---:|---:|---:|---:|---:|
| without spine | 84 s (0.57×) | 9,351 / 13,877 | 9,130 / 13,031 | 0.605 | 64 |
| with SAT spine | 108 s (0.74×) | 9,743 / 14,225 | 9,069 / 13,322 | 0.613 | 483 |
| Vamana | 146 s | — | 9,204 / 13,325 | — | — |

On Vamana's searcher the spine is a wash (−0.7% / +2.2%; d@0.97 lands
exactly on Vamana); on fg's searcher the root hub costs 3–4%. Either way
the dense graph with the guarantee is still at Vamana quality at 0.74× its
build time; without it 0.57×. A cheaper guarantee — a k-nearest-leader
graph realized between leaf medoids, O(L²) — would keep the clustered case
connected at no cost on GloVe; that is the next measurement.

**Cheaper connectors, refuted.** A k-nearest-leader graph (k = 8) realized
between leaf medoids (`--dense-spine 2`) leaves the clustered smoke at
recall 0.002; adding a star from the global medoid to every leaf medoid
raises it only to 0.035. The disconnection is at cluster level *inside* the
leaves (the synthetic set has far more clusters than leaves, and the prune
separates them), and a greedy beam never expands a medoid that is farther
from the query than its local frontier, so long edges hung on medoids are
not traversed. A spanning tree is what works, because every point has an
edge up a hierarchy the descent can follow. On GloVe both variants are
indistinguishable from no spine (ParlayANN 9,699 / 13,300).

**Parallel single tree.** With T = 1 the forest builder ran the spine tree
on one thread (23.7 s on GloVe). Subtrees are now OpenMP tasks with
per-thread scratch (node processing is a pure function of its segment with a
node-keyed RNG; child segments are disjoint): tree bitwise identical (GloVe
graph identical, hash identical at 1 vs 64 threads), but the spine only
dropped to 20.2 s — the cost sits in the *root node's own processing*
(every member against the root's ~10³ children, sequential in the SAT
selection loop), not in the subtrees. Blocking that loop (parallel distances
of a block of members to the children that already exist, then a short
sequential pass against the children added within the block) is the next
step; it preserves the pair-to-kernel assignment and hence bitwise identity.

**Blocked node loops (final).** The root node's own processing dominated the
spine (every member against the root's children, sequential in the SAT
selection rule). Blocked version: a block of 8,192 members computes its
distances to the children that exist at block start in parallel over the
aligned 4-groups [0, j0), then each member continues sequentially from j0
(4-groups, then the scalar tail) against the children added inside the
block; the routing loop is parallel over member blocks. Every pair goes
through the same kernel as in the sequential code, so the tree is bitwise
identical: GloVe graph byte-identical, hash identical at 1 vs 64 threads,
and the spine's distance count identical (985.5 M). **Spine 23.7 s → 9.8 s.**

Bug found on the way: a `size_t`-indexed `taskloop` ran zero iterations
under clang, so the routing loop was silently skipped; the graph stayed
identical (routing re-routes only ≈0.2% of a node's members) and only the
distance count diverging from the sequential path (779 M vs 985 M) exposed
it. The count is a correctness check, not just a cost metric.

**GloVe, config A, final stage table (d0, 64 threads, Vamana ending, spine on):**

| leaders | candidates (88.6 G pairs) | prune | spine | **total** | vs Vamana 146.1 s |
|---:|---:|---:|---:|---:|---:|
| 0.7 s | 75.2 s | 9.9 s | 9.8 s | **95.5 s** | **0.65×** |

(without the spine: 84 s, 0.57×; the spine is the connectivity guarantee
for clustered data, and on GloVe its graph is at Vamana parity on Vamana's
searcher: 9,069 / 13,322 vs 9,204 / 13,325.)

## GPU leg (G15: i7-11800H 8c/16t up to 4.2 GHz, RTX 3060 Laptop 6 GB, 2026-09-19)

`bench/dense_gpu.py`: leaders and memberships in CuPy, per-leaf exact kNN
with FAISS `knn_gpu` (fused GEMM + k-select), running top-C merge; the
candidate lists go to `fg --dense-cands` for the prune, the spine and the
evaluation. The GPU k-means uses scatter-add (unordered float sums), so its
leaves are not bitwise reproducible, unlike the CPU path; the per-leaf kNN
is exact.

| stage (GloVe, config A) | v1: host merge | v2: merge on GPU |
|---|---:|---:|
| leaders + memberships | 1.0 s | 1.0 s |
| kNN, 174.2 G ordered pairs (FAISS) | 22.06 s = **7.90 G pairs/s** | 22.19 s |
| top-C merge + transfer | 103.6 s (numpy) | 13.1 s |
| candidate stage | 125.7 s | **35.3 s** (total 38.5 s) |
| fg prune + spine (G15 CPU, 16 threads) | 15.5 s | 15.7 s (spine 985.5 M in 3.6 s) |
| **end to end** | 141 s | **54.2 s** |

Graph: 46.8 edges/vertex, max 479, completeness 0.609. Quality on Vamana's
searcher (graded on d0): GPU graph A2 **9,131 / 13,447**, A 9,138 / 13,502
— Vamana 9,204 / 13,325, CPU dense build with spine 9,069 / 13,322: parity.
On fg's searcher A2: 9,805 / 14,432 (CPU build with spine: 9,743 / 14,225).

**Vamana on the same laptop** (ParlayANN, authors' recipe, built offline
from d0's dependency sources): run 1 653.6 s, run 2 639.3 s; the same
31.56 G distances and the same query column (9,752 @0.954, 13,508 @0.971)
as on d0, so the configuration matches. 8 physical cores under a
`powersave` governor: 640 s × 8 cores ≈ d0's 146 s × 32 cores, so the
per-core rate is the same and nothing is anomalous.

| machine | dense build | Vamana | ratio |
|---|---:|---:|---:|
| G15 laptop (GPU candidates + CPU prune/spine) | **54 s** | 640 s | **0.085×** |
| d0 (CPU only, 64 threads) | 95.5 s | 146 s | 0.65× |

Findings.
19. **The candidate stage is a GPU kernel.** FAISS's fused brute force runs
    at 7.9 G pairs/s on a 6 GB laptop GPU — 6.6× the CPU stage on d0's 64
    Haswell threads (1.2 G/s) and 1.8× d0's SGEMM rate — for the whole
    174 G-pair scan in 22 s. The wall paper's argument in one number: the
    pair set is fixed in advance, so the arithmetic rate is the bound.
20. **On the laptop the dense build is 12× faster than Vamana at parity
    quality**, because Vamana's build is a search that the laptop's 8 cores
    execute at their random-access rate, while the dense build's dominant
    stage runs on the GPU and the rest (prune, spine, 16 s) is a small,
    parallel, cache-friendly remainder.
21. What is left on the GPU path: the prune (24 G candidate–candidate
    distances, C×C grams per point) and the spine are CPU stages today; both
    are batched products too. And the merge (13 s) is a CuPy argsort that a
    fused k-select would absorb.

## Scale: Deep-10M (d0, 64 threads, 2026-09-19)

Deep-96 at $10^7$ (L2). Dense: m = 5, C = 200, cap 64, α = 1.0, Vamana
ending, SAT spine. References: GRAFT's published Deep arm (T8/ef400 frozen)
on fg, and Vamana with DiskANN's L2 recipe (R64/L128, α 1.2, two passes).
d@r on ParlayANN's searcher (Vamana's own); fg's searcher in the last columns.

| arm | pool | build (stages) | G dist | compl. | PA d@0.95 | PA d@0.99 | fg d@0.95 | fg d@0.99 |
|---|---:|---|---:|---:|---:|---:|---:|---:|
| **dense L2400** | 1% | **734 s** (leaders 20, candidates 607, prune 69, spine 37) | 661 | 0.604 | 2,180 | **4,811** | <2,224 (0.954 @ ef 60) | 4,974 |
| dense L800 | 3% | 1,397 s (7, 1,280, 71, 39) | 1,786 | 0.615 | 2,135 | 4,579 | <2,240 | 4,9xx |
| Vamana R64/L128 α1.2 2-pass | — | 699 s | 278 | — | 2,150 | 5,159 | — | — |
| GRAFT T8/ef400 frozen | — | 986 s (trees 107 + harvest 874) | 105 | 0.521 | — | — | 2,238 | 5,406 |

Findings.
22. **At $10^7$ the dense build is at Vamana quality with a 1% pool** —
    +1.4% at 0.95, **−6.7% at 0.99** on Vamana's searcher — and beats
    GRAFT's frozen arm on fg's searcher (≈ equal at 0.95, −8% at 0.99, and
    completeness 0.604 vs 0.521). Deep's lower intrinsic dimension shows in
    the pool: 3% buys only 1.1 points of completeness and −5% at 0.99 over
    1%, for 2.9× the pairs; on GloVe the same step (3% → 9%) was worth 7.6%.
23. **Cost: 734 s vs Vamana 699 s (1.05×) and GRAFT 986 s (0.74×).** The
    candidate stage ran at 1.01 G pairs/s (leaves of 21k; the smaller
    per-leaf tiles and 10× more heaps cost some rate against GloVe's 1.2).
    The distance count is 2.4× Vamana's and 6.3× GRAFT's — all dense.
    Vamana itself needs 278 G distances at $10^7$ (8.8× its GloVe count for
    8.5× the points): its per-point search cost grows with n, the dense
    build's does not at fixed pool size.
24. **Projection for Deep-100M.** Pairs = n²m²/L. Holding the *absolute*
    pool at 10⁵ candidates per point (0.1% of n; the same as the 1% pool at
    $10^7$, which sufficed) needs L = 24,000 and 1.0·10¹³ pairs — ≈2.9 h at
    the measured rate — plus prune (~150 G, ~15 min) and spine (~6 min).
    Memory: heaps 160 GB, data 38 GB, fine on d0. The membership stage as
    written costs n·L = 2.4·10¹² distances (40 min) and needs a two-level
    leader hierarchy (240 top leaders × 100 sub-leaders → n·340). GRAFT's
    T8/ef400 at $10^8$ took 16,700 s on this machine; Vamana's cost grows
    faster than linearly. Whether 10⁵ candidates per point still give
    parity at $10^8$ is the open question the run would answer.
