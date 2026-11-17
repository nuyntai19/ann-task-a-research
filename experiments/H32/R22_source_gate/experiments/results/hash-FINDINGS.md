# The localizer construction, subset-hashed form — GIST-960, d0, 2026-09-26

> **SUPERSEDED 2026-09-29 (`capped-FINDINGS.md`):** every arm below pruned the
> whole candidate row without the stage-3 heap (200 nearest by distance).
> With `--harvest-cand 200` the count pool matches the leaf build (d@0.95
> 4,518 vs 4,485). The "region vs. signature" reading was the confound, not
> the pool.


**Scheme (author):** the k-group of sample neighbours is hashed by its
j-subsets; the objects colliding on a key are one local neighbourhood
(bucket); all pairs inside a bucket. `bench/hash_cands.py` builds the
buckets (exact signatures by GEMM, α 2%, |S| 20,000, k ≤ 16) and writes
each object's union of buckets as candidate rows for `fg --dense-cands`,
filled smallest-bucket-first up to C. Chain `bench/d0_hash.sh`.

## Bucket statistics (pairs and triples of sample ids)

| key | k | keys | bucket size median / p99 / max | singletons | union bound median / p90 / max | all-pairs bound |
|---|---:|---:|---:|---:|---:|---:|
| pairs | 8 | 5.0 M | 2 / 68 / 4,800 | 0.48 | 1,262 / 4,415 / 25,584 | 0.98 G |
| pairs | 10 | 6.6 M | 2 / 86 / 6,066 | 0.45 | 2,900 / 9,309 / 50,026 | 2.14 G |
| pairs | 16 | 11.5 M | 2 / 145 / 9,834 | 0.39 | 15,565 / 43,810 / 207,680 | 10.7 G |
| triples | 12 | 112 M | 1 / 15 / 2,173 | 0.73 | 1,186 / 6,985 / 156,467 | 1.58 G |
| triples | 16 | 245 M | 1 / 20 / 3,225 | 0.69 | 5,333 / 27,820 / 492,178 | 6.40 G |

The buckets are tiny (median 2) with a hub tail; the pool an object sees
is the union of 45-560 of them. The all-pairs cost bound is 1-11 G against
the paper's 26 G leaf stage, so on cost the form is attractive.

## Results

| arm | C | rows cut | mean cands / object | compl. | deg | prune s | d@0.90 | d@0.95 | d@0.97 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| cell-built k-means L700/m5 (paper) | — | — | 53k eff. | 0.328 | 18.3 | 50 | 2,898 | **4,485** | 6,055 |
| cell-built random L90000/m30 | — | — | 46k eff. | 0.336 | 18.7 | 50 | 2,925 | **4,419** | 6,010 |
| pairs k16, cut smallest-first | 2,000 | 94% | 1,968 | 0.363 | 48.5 | 307 | 4,971 | 7,287 | 9,459 |
| **pairs k10, uncut** | 8,000 | 3% | 2,611 | 0.353 | 43.0 | 380 | 4,592 | **6,860** | 8,814 |
| triples k12, uncut | 6,000 | 0.2% | 1,021 | 0.309 | 33.3 | 160 | 5,339 | 8,151 | 11,187 |

(pairs k16 and triples k16 at C 16000, the large-pool forms: running.)
Smaller signature pools are worse (triples 1k → 8,151; pairs 2.6k → 6,860),
and the count series showed the same direction with saturation, so the
large-pool arms are the last informative ones: they ask whether measure
alone rescues a signature pool.

Edge diagnostic (`results/hash/edge_diag_hash.log`):

| graph | deg | edges rank ≤ 10 | ≤ 100 | ≤ 1k | > 10k | > 100k | true-10 covered |
|---|---:|---:|---:|---:|---:|---:|---:|
| cell-built k-means L700/m5 | 18.9 | 0.176 | 0.506 | 0.845 | 0.038 | 0.005 | 0.332 |
| cell-built random L90000/m30 | 18.7 | 0.181 | 0.519 | 0.845 | 0.039 | 0.005 | 0.340 |
| pairs k16, cut to 2,000 | 49.2 | 0.074 | 0.253 | 0.544 | 0.196 | 0.042 | 0.364 |
| pairs k10, uncut | 43.8 | 0.079 | 0.273 | 0.576 | 0.167 | 0.028 | 0.347 |

## Reading

The uncut pair-bucket union is negative in exactly the way the
count-ranked pools were (`solo-FINDINGS.md`): more true neighbours in the
pool than the cell pool (0.35 vs 0.33), twice the pruned degree, half the
share of edges within rank 10, four times the share beyond rank 10⁴, and
50% more distance evaluations at 0.95. Truncation was not the cause; the
uncut form (3% of rows touched) reproduces it.

Why: an object's union of pair buckets is, by definition, the set of
objects sharing at least two of its k sample neighbours — the
shared-neighbour pool with a threshold in place of a rank. Its members
are selected by *signature agreement*, and signature agreement is a noisy
proxy for distance at the ranks that matter (10-1,000): a far object
sharing two hub sample points is in, a near object whose nearest sample
points happen to differ is out. The α-prune then keeps the unshadowed
far members as edges. A cell, by contrast, is a *region*: every object
whose nearest sample point is s, whatever else its signature says, and
its members are close to s in the metric, not similar to x in the hash.
Hashing the group localises objects with respect to each other's
signatures; the prune needs objects localised with respect to the space.
That is why the single-id form (a Voronoi cell per sample point) works
and every subset form does not: the single id *is* the region, the pair
is a signature.

## Cost, for the record

Signatures 401 s (numpy GEMM, 0.1 TFLOP/s), bucketing 12-150 s, the
per-object union expansion 30-60 min in numpy (not tuned; irrelevant if
the quality is not there), prune 300-380 s for 7.5 G random evaluations.
