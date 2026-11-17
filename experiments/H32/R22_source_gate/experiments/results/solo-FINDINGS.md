# SOLO candidates for the dense construction — E1 (2026-09-25, d0, GIST-960)

> **SUPERSEDED 2026-09-29 (`capped-FINDINGS.md`):** every arm below pruned the
> whole candidate row without the stage-3 heap (200 nearest by distance).
> With `--harvest-cand 200` the count pool matches the leaf build (d@0.95
> 4,518 vs 4,485). The "region vs. signature" reading was the confound, not
> the pool.


**Idea (author, 2026-09-25):** replace the dense construction's leaders +
leaf all-pairs by MISIFU's architecture: a random sample S (α = 2%), each
object's k_b nearest sample points (exact, by GEMM), an inverted index over
S, and for every object the count-ranked top-C objects sharing sample
neighbours with it. Only those C pairs get a distance (inside fg's prune);
the pool's ceiling (the union of k_b posting lists, 5-20% of n) decouples
from its cost (C). Everything already existed: `misifu.MISIFU.fit` +
`batch_merge` (`bench/solo_cands.py`) → n × C int32 → `fg --dense-cands`
(prune, spine, dump) → ParlayANN grader. Chain `bench/d0_solo.sh`.

Prediction (k_b 32, C 2000): completeness ≥ 0.7, degree ~30, d@0.95 < 4,000.
Refutation: d@0.95 ≥ 4,485 (the leaf build on the same grader) at C = 4000.

## Result: refuted under plain shared-count scoring, at both k_b

| pool | completeness | degree | prune evals | d@0.90 | d@0.95 | d@0.97 |
|---|---:|---:|---:|---:|---:|---:|
| leaf L700/m5 (P = 36k, all pairs) | 0.328 | 18.3 | 26.4 G (GEMM) | 2,898 | **4,485** | 6,055 |
| PiPNN (30 × ~330) | 0.456† | 33.7 | 7.2 G | 2,970 | 4,548 | 6,069 |
| Vamana R64/L128 | — | 36.1 | 19.6 G | 3,191 | 5,281 | 7,445 |
| count k_b16 C500 | 0.302 | 29.8 | 1.8 G | 4,900 | 7,504 | 9,753 |
| count k_b16 C1000 | 0.347 | 36.9 | 3.4 G | 4,587 | 6,996 | 9,276 |
| count k_b16 C2000 | 0.380 | 43.2 | 6.2 G | 4,411 | 6,615 | 8,714 |
| count k_b16 C4000 | 0.387 | 47.6 | 12.4 G | 3,997 | 6,270 | 8,000 |
| count k_b32 C500 | 0.344 | 31.5 | 1.8 G | 3,866 | 5,776 | 7,675 |
| count k_b32 C1000 | 0.382 | 38.9 | 3.4 G | 3,771 | 5,773 | 7,368 |
| count k_b32 C2000 | 0.401 | 45.3 | 6.2 G | 3,729 | 5,818 | 7,387 |
| count k_b32 C4000 | 0.403 | 49.5 | 12.4 G | 3,730 | 5,510 | 6,974 |

† from `bench/edge_diag.py` (1,000 sources, exact ranks), which reproduces
fg's completeness for the leaf graph (0.332 vs 0.328).

Signatures: 389 s (20 G sample pairs through numpy GEMM, 0.1 TFLOP/s — not
tuned), merge 164 s at k_b 16 / ~300 s at k_b 32, prune (the verification)
17 M random evals/s: 106 s at C 500, 548 s at C 4000.

Three facts:

1. **Completeness is not what buys navigability.** Count k_b16 C1000 has
   the leaf pool's completeness (0.347 vs 0.328) and twice its degree, and
   is 56% worse at 0.95. Completeness rises slowly with C (0.30 → 0.40) and
   d@0.95 saturates: k_b 32 is flat at 5,500-5,800 from C 500 to 4000.
2. **k_b is the lever that works, C is not.** Doubling k_b bought 23% at
   C 500 (7,504 → 5,776); octupling C bought 5% at k_b 32.
3. **The failure mode is precision, not reach.** The edge diagnostic
   (`results/solo/edge_diag_kb*.log`) shows the count-built graphs have
   *fewer* near edges and *more* far ones than the leaf graph:

| graph | deg | edges with rank ≤ 10 | ≤ 100 | ≤ 1k | > 10k | > 100k |
|---|---:|---:|---:|---:|---:|---:|
| leaf L700/m5 | 18.9 | 0.176 | 0.506 | 0.845 | 0.038 | 0.005 |
| PiPNN | 33.7 | 0.136 | 0.398 | 0.676 | 0.129 | 0.026 |
| count k_b16 C4000 | 48.7 | 0.079 | 0.265 | 0.565 | 0.177 | 0.036 |
| count k_b32 C1000 | 39.3 | 0.097 | 0.318 | 0.642 | 0.118 | 0.019 |
| count k_b32 C2000 | 46.0 | 0.090 | 0.295 | 0.615 | 0.136 | 0.023 |

   The count-ranked list is polluted by hub sample points: posting lengths
   have mean 800 / max 26,486 at k_b 16 and mean 1,600 / max 44,038 at
   k_b 32, so an object sharing two hubs with a far stranger outranks a
   true neighbour sharing one rare sample point. The α-prune then spends
   degree on far junk (17.7% of edges beyond rank 10⁴ against 3.8%), and
   half as many edges land within rank 10. PiPNN tolerates 12.9% far edges
   because it has the most true neighbours of all three (0.456).

This is the hub regime MISIFU's own log identified (2026-08-21): the fix
there was **idf** (discount votes from long lists, w = log(1 + n/|L(s)|);
capping was tried and removes true postings) and **rank agreement**
(w = 1/(1 + r_q + r_o)). E1b runs both at k_b 32, C ∈ {1000, 2000, 4000}
(`run_solo2.sh`, tmux `fgsolo2`, logs `results/solo2_{idf,rankidf}.log`).
Gate: d@0.95 < 4,485 **and** edge share within rank 100 ≥ 0.45.

## What stands regardless of E1b

* The idea's cost side held: the candidate stage's distance work became
  n·C random evals (1.8-12 G) instead of 26 G GEMM pairs, and the counting
  is linear integer work. But at 17 M random evals/s against 165 M GEMM
  pairs/s, C 4000 (548 s) already costs more wall than the leaf stage
  (160 s). Break-even needs C ≲ 1,500 *and* a ranking that is right at
  that C — or SOLO's screen in front of the verification.
* The scaling and dynamism arguments (no Lloyd, no n·L membership, insert
  = one sample search) are untouched by E1; they were never about quality.
* GIST's completeness ceiling is low for every method (0.33-0.46) and the
  graphs beat Vamana anyway. Whatever governs d@r here, it is the *edge
  precision at short rank*, which the leaf pool gets from geometry (a
  Lloyd cell is a ball around the object's region) and the count ranking
  does not.

## E1b (idf) and closure — 2026-09-25, 20:12

idf scoring at k_b 32 changed nothing: C 1000 → completeness 0.390, degree
41.5, **d@0.95 5,809** (count: 5,773); C 2000 → 0.406, 47.5, **5,874**
(count: 5,818). The idf C 4000 arm, the rank-idf leg and the α 1.2 prune
arm were stopped unfinished at the author's decision ("enough negative
results; drop the branch"). Hub discounting is therefore not the fix, and
the failure is not in the ranking's weights.

**Closing assessment.** The shared-neighbour ranking does what it was built
for — its pools hold *more* true neighbours than the leaf pool (0.40 vs
0.33) at a tenth of the candidates — and the graph built from them is
worse anyway. What the α-prune needs is not a high-recall list but a
geometrically faithful neighbourhood at several scales: a Lloyd cell is a
region around the object with density falling with distance, and the
prune's kept edges follow that geometry (85% within rank 10³, 4% beyond
10⁴). A count-ranked list is a single-scale ball plus a noise tail; the
prune shadows most of the ball and keeps the tail. No re-weighting of the
votes changes that shape. The idea's cost, scale and dynamism arguments
were never refuted, but without a quality path they have nothing to carry.

**Disk:** `/mnt/raid/fgraft-campaign-2026-09-22/solo/` is 84 GB — 11
candidate matrices (`*.i32`, regenerable in ~25 min) and 10 graphs — all
safe to delete; logs are in `results/solo/`.
