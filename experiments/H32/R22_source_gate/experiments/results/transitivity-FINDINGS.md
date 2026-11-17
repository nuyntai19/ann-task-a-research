# kNN-graph transitivity vs the cost of a block cover (2026-09-30, M5, local)

Question: is the pair count a partition-then-brute-force build needs set by
the data, via how clique-like the exact kNN graph is? Script
`bench/knn_transitivity_diag.py [nsub] [corpus ...]`; logs
`results/transitivity/diag.log` (full n) and `diag-n200k.log` (every corpus
subsampled to 200k, seed 7). Sample P = 2,000 points (seed 0); exact 10-NN of
P and of every q in N(P). Cost side: symmetric k-means leaves (10 Lloyd on a
200k sample, mean cell 1,400 = L n/1400), m nearest leaders per point; a true
pair (p,q) is covered if p and q share a leaf. At fixed cell size pool(m) is
the same on every corpus (~1.6k/6.5k/15k/26k/41k for m=1..5), so the
portable cost is **m@rho, the memberships needed to cover a fraction rho**.

Sanity: GIST m=5 cover 0.906 at 52k pool (numpy replica of 09-29: 0.895 at 52k).

## n-matched (200k each)

| corpus | LID | recip. | clustering mean | cc q10 | frac cc=0 | m@0.85 | m@0.90 | m@0.95 |
|---|---|---|---|---|---|---|---|---|
| Wikipedia | 35.3 | 0.517 | 0.162 | 0.033 | 0.024 | 1.77 | 1.99 | 2.81 |
| SIFT | 19.7 | 0.332 | 0.137 | 0.044 | 0.007 | 2.01 | 2.48 | 2.95 |
| GIST | 49.9 | 0.074 | 0.076 | 0.011 | 0.043 | 2.95 | 3.53 | 4.38 |
| GloVe | 35.7 | 0.312 | 0.106 | 0.000 | 0.120 | 3.30 | 4.24 | 5.91 |

## Full n (Wikipedia is 200k locally)

| corpus | n | clustering | m@0.85 | m@0.90 | m@0.95 | cover @ m=12 |
|---|---|---|---|---|---|---|
| SIFT | 1.0M | 0.171 | 2.73 | 3.21 | 4.04 | 1.000 |
| GIST | 1.0M | 0.084 | 4.14 | 4.90 | 6.26 | 0.996 |
| GloVe | 1.18M | 0.123 | 4.64 | 6.46 | 9.91 | 0.967 |

## Within corpus (per point: its own cover vs its local clustering)

Cover rises monotonically across clustering quartiles in all 16 cases
(8 corpus/n settings x m in {2,4}). Spearman(cover, clustering) +0.09..+0.61,
larger than for reciprocity (+0.09..+0.34) and |LID| (0.08..0.41) in every
row. Strongest on GloVe: m=2 cover 0.32 in the bottom clustering quartile
vs 0.86 in the top (full n).

## Reading

1. No kNN graph is near clique-like (mean clustering 0.08-0.17, two-hop
   expansion 7.7-9.1 of a maximum 11): the overpay of any clique cover over
   n*k is structural.
2. Local clustering predicts which pairs a block cover misses, within every
   corpus: the mechanism holds point by point, not only across corpora.
3. Across corpora a scalar does not suffice. The mean orders the easy pair
   (Wikipedia, SIFT) from the hard pair but puts GIST below GloVe; the low
   tail (q10, fraction with cc=0: 12% of GloVe points have *no* edges among
   their neighbours) orders GloVe/GIST correctly, and m@0.95 follows it.
   The cost at high rho is set by the tail of the local-clustering
   distribution. Four corpora; do not fit a law yet.
4. **m@rho grows with n at fixed cell size**: 200k -> 1M raises m@0.85 by
   1.36x (SIFT), 1.40x (GIST), 1.41x (GloVe), close to log L (143 -> 714:
   1.32x). Pool ~ m^2 * cell, so at fixed cell size the pool per point grows
   ~ (log n)^2 if this holds. Two n points only; the 10^9 consequence needs a
   third (10^7, Deep-10M on d0).
