# Framing tests T1-T5 (2026-10-01, d0, `bench/d0_framing_tests.sh`, 09:25-23:14)

Tests of `../DensePaper/FRAMING.md` §4. All steps rc=0. Logs `results/framing/`;
d@r by `bench/parse_parlay.py` (ParlayANN searcher; k=10 unless stated).
"Ours" = fg on PiPNN's dumped reservoir (`--dense-cands`), 200-nearest heap,
symmetrize + prune cap 64 at the stated alpha, HSP spine s=10k cap 16.
"thin" = PiPNN defaults (mst_deg 2, table 160); "rich" = mst_deg 10, table
400. PiPNN is nondeterministic: reruns differ by up to ±3%.

## T1 — composed build at 10^8 and on Wikipedia 6.35M

| corpus | arm | d@0.90 | d@0.95 | d@0.97 | d@0.99 | k=100 d@0.95 |
|---|---|---|---|---|---|---|
| Deep-100M | dense + HSP (L24000) | 2,307 | **3,677** | **4,933** | **8,883** | **7,198** |
| | dense + SAT (09-22) | — | 3,775 | 5,105 | 8,831 | — |
| | Vamana (09-22) | — | 4,047 | 5,650 | 10,547 | — |
| | PiPNN thin (own ending) | 2,647 | 4,289 | 5,736 | 10,365 | 8,403 |
| | ours, thin, alpha 1.0 | 2,586 | 4,146 | 5,493 | 9,900 | 8,213 |
| | ours, rich, alpha 1.0 | 2,630 | 4,108 | 5,546 | 9,516 | 7,795 |
| | ours, thin/rich, alpha 1.2 | | 4,284 / 5,941 | | 10,326 / 17,120 | 8,070 / 9,953 |
| Wikipedia | dense + HSP (L1600) | 2,047 | 3,840 | 6,619 | — | **8,030** |
| | dense + SAT (09-23) | — | 3,868 | 6,705 | — | — |
| | Vamana (09-23) | — | 4,246 | 6,942 | — | — |
| | PiPNN thin | 2,043 | 4,158 | 6,605 | 25,865 | 8,688 |
| | ours, thin, alpha 1.0 | **1,890** | **3,750** | **6,315** | — | 8,713 |
| | ours, rich, alpha 1.0 | 2,044 | 4,052 | 6,550 | 26,315 | 9,065 |

Build (wall; composed = PiPNN build - its final prune + fg prune incl.
spine; excludes data loading and the dump's file I/O):

| corpus | dense + HSP | dense + SAT | composed thin | composed rich | PiPNN peak RSS thin / rich | dense RSS |
|---|---|---|---|---|---|---|
| Deep-100M | 13,723 s (3:48:43) | 15,186 s | ~984 s | ~1,785 s | 288 / 559 GB | 267 GB |
| Wikipedia | 2,422 s | 2,507 s | ~413 s | ~1,270 s | 43 / 60 GB | 51 GB |

Reading:
- **Deep-100M keeps a scale regime for the dense stage:** it is 11-12%
  better at 0.95 and 7-11% better at 0.99 than the best composed build,
  and 8% better at k=100. The composed build costs 1/8-1/14 of the dense
  build and still beats PiPNN (4-8%) and Vamana at 0.99 (-6 to -10%).
- **Wikipedia, k=10: the composed thin build beats dense** by 2-5%
  (3,750 vs 3,840 at 0.95) at 1/6 of the build. **At k=100 it reverses:**
  dense 8,030 vs composed 8,713 (+8.5%) and PiPNN 8,688. The thin pool
  holds the 10 nearest well and the 100 nearest poorly.
- alpha 1.0 is best at 10^8 and on Wikipedia in every arm at k=10; at k=100
  alpha 1.2 helps the thin pool on Deep-100M (8,070 vs 8,213).

## T2 — alpha of our ending on thin and rich pools (d@0.95 / d@0.99)

| corpus | PiPNN thin (own) | thin a1.0 | thin a1.1 | thin a1.2 | PiPNN rich (own) | rich a1.0 | rich a1.1 | rich a1.2 |
|---|---|---|---|---|---|---|---|---|
| GIST | 4,635 / 10,169 | 5,229 / 10,723 | **4,383 / 9,767** | 4,471 / 9,925 | 5,579 / 12,036 | 4,513 / 9,575 | 5,279 | 7,651 |
| GloVe | 13,316 | 12,284 | 11,539 / 30,721 | **11,402 / 30,809** | 13,072 / 32,479 | 11,963 / 30,533 | 11,894 | 13,468 |
| SIFT | 1,226 / 2,270 | **1,167 / 2,224** | 1,317 / 2,487 | 1,372 / 2,512 | 1,362 / 2,433 | 1,211 / 2,188 | 1,359 | 1,582 |
| Deep-10M | 2,462 / 5,268 | **2,278 / 4,876** | 2,416 / 5,141 | 2,406 / 5,272 | 2,399 / 5,579 | 2,328 / 4,893 | 2,331 / 5,453 | 3,059 / 7,233 |

Reading:
- **On every corpus some alpha on PiPNN's own (thin) pool beats PiPNN's own
  ending**: GIST -5% (alpha 1.1), GloVe -14% (1.2), SIFT -5% (1.0),
  Deep-10M -7% (1.0). The FRAMING T2 criterion is met: C3 does not need
  rich pools.
- **"alpha by pool size" is refuted as a single rule.** On rich pools
  alpha 1.0 is always best (alpha 1.2 is catastrophic: GIST 7,651). On thin
  pools the best alpha is corpus-dependent: 1.1-1.2 on GIST and GloVe, 1.0
  on SIFT, Deep-10M, Deep-100M and Wikipedia.
- At 10^6-10^7, thin pool + the right alpha matches or beats the rich pool
  in every corpus; the rich pool only pays at 10^8 (Deep-100M 0.99: 9,516
  vs 9,900).

## T3 — GloVe: what closes the gap to the dense build (ours, alpha 1.0)

| PiPNN variant | ours d@0.95 / d@0.99 | PiPNN own d@0.95 |
|---|---|---|
| thin (mst 2) | 12,284 | 13,316 |
| mst 10 / 20 / 50 | 11,963 / 11,638 / 11,239 | 13,072 / 13,149 / 13,789 |
| 2,048-point leaves, mst 10 / 20 | 11,428 / 10,893 | 12,122 / 12,468 |
| **60 leaves per point (fanout 20,3,1), mst 10** | **9,971 / 25,400** | 11,132 |
| dense + HSP / dense + SAT | 9,172 / 9,069 | — |

Reading: keeping more of each leaf matrix buys 5-9%; doubling the leaves
per point buys 19% and brings the composed build to 8.7% of dense+HSP
(9,971 vs 9,172). FRAMING's T3 criterion (<= 5%) is not met, so the GloVe
regime stands, but its mechanism is **memberships, not leaf retention**:
GloVe needs more coverage per point, as C2 predicts for a corpus with the
heaviest clustering tail. Untested: fanout 30-40 per point, and alpha 1.2
on the 60-leaf pool (alpha 1.2 gave GloVe's thin pool -7%).

## T5 — HSP spine (s 10k, cap 16) in every dense table

| corpus | SAT d@0.95 | **HSP d@0.95** | SAT d@0.99 | **HSP d@0.99** | HSP k=100 d@0.95 | spine cost HSP (SAT) | build HSP (SAT) |
|---|---|---|---|---|---|---|---|
| GloVe | 9,069 | 9,172 (+1.1%) | — | 24,833 | 20,228 | 100 M, 2.3 s (985 M, 10.4 s) | 96 s (95 s) |
| SIFT | — | 1,175 | 2,155 | 2,116 (-1.8%) | 2,422 | 100 M, 1.6 s | 58 s |
| GIST | 4,485 | 4,268 (-4.8%) | — | 11,098 | 7,509 | 100 M, 4.3 s (1,678 M, 30.9 s) | 241 s |
| Deep-10M | 2,180 | 2,133 (-2.2%) | 4,811 | 4,553 (-5.4%) | 4,084 | 100 M, 10.3 s | 739 s |
| Wikipedia | 3,868 | 3,840 (-0.7%) | — | — | 8,030 | 100 M, 10.1 s | 2,422 s (2,507 s) |
| Deep-100M | 3,775 | 3,677 (-2.6%) | 8,831 | 8,883 (+0.6%) | 7,198 | 100 M, 112 s (56,704 M, 599 s) | 13,723 s (15,186 s) |

Reading: never worse than SAT by more than 1.1%; better by 2-5% on four of
six corpora; the spine stage costs 100 M distances instead of up to 57 G,
and the Deep-100M build drops by 24 min (peak RSS 267 GB vs 327 GB).
FRAMING's T5 criterion (> 3% worse anywhere) is not met: C4 holds 10^6 -> 10^8.

## T4 — clustering of the kNN graph (see also transitivity-FINDINGS)

Deep at fixed cell size 1,400 (m@cover):

| n | L | mean cc | frac cc = 0 | m@0.85 | m@0.90 | m@0.95 | m@0.85 / ln L |
|---|---|---|---|---|---|---|---|
| 200k | 143 | 0.144 | 1.1% | 1.95 | 2.39 | 2.94 | 0.393 |
| 1M | 714 | 0.122 | 2.7% | 2.49 | 2.91 | 3.84 | 0.379 |
| 10M | 7,143 | 0.096 | 5.7% | 3.61 | 4.47 | 6.05 | 0.407 |
| 100M (stats only) | — | 0.090 | 8.1% | — | — | — | — |

Full Wikipedia 6.35M (stats only): mean cc 0.206, frac cc=0 2.4%, the most
clustered corpus measured. Within Deep-10M, Spearman(cover, clustering)
+0.43 to +0.50 at 10M, again above reciprocity and LID.

Reading: m@0.85 ~ 0.38-0.41 ln L over three decades of n (the log-L law
holds, slight upturn at 10M). **The clustering tail grows with n on the
same corpus** (frac cc=0 1.1% -> 8.1% from 2e5 to 1e8): scale makes a
corpus GloVe-like. Across the regimes measured, the corpora where the dense
stage pays (GloVe; Deep at 10^8) are those with the heaviest tails (12.6%;
8.1%), and the one where the composed build wins at k=10 (Wikipedia) has
the lightest (2.4%). Correlational, six corpora / settings.
