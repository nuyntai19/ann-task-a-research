# Our ending on PiPNN's pool (2026-10-01, d0, `bench/d0_pipnn_ending.sh`)

PiPNN (ParAlg 443a328 + counters + GRAFT-DUMP: read-only export of the
HashPrune reservoir before its final prune, sorted by exact distance; patch
in `pipnn.h`, original saved as `/mnt/raid/.../pipnn.h.before-dump`).
Each PiPNN leaf computes its full N x N matrix but keeps only each point's
`mst_deg` nearest (default 2): the reservoir holds 37-66 candidates per point
on average. Arms (mst_deg, table_size) = (2,160) defaults, (5,400), (10,400).
Per arm: PiPNN's own ending (robustPrune alpha = corpus alpha, prune_all,
degree 64) graded in-process; ours on the dumped pool = fg `--dense-cands`,
200-nearest heap, symmetrize + alpha 1 prune cap 64, HSP spine s=10k cap 16
(`--dense-spine 3 --dense-spine-s 10000 --dense-spine-cap 16`), ParlayANN
grade. d@r by `bench/parse_parlay.py`; logs `results/pipnn_ending/`.

**Gate.** PiPNN is not deterministic (reservoir merges are lock-order
dependent; distance totals differ in the 4th digit). Defaults rerun:
GIST 4,672 / 6,087 vs 4,548 / 6,069 on 09-25, GloVe 13,228 vs 13,302,
Deep-10M 2,418 vs 2,463: run-to-run noise ~±3% for PiPNN rows.

## d@r (ParlayANN), and composed build time

Composed time = PiPNN build - its final prune + fg prune stage (incl.
spine); excludes the dump's file I/O.

| corpus | arm | pool/pt | PiPNN own d@0.95 | **ours d@0.95** | ours d@0.99 | PiPNN build | composed |
|---|---|---|---|---|---|---|---|
| GIST | m2 t160 | 57 | 4,672 | 5,271 | 10,576 | 40.1 s | 47.0 s |
| | m5 t400 | 128 | 4,575 | 5,068 | 10,400 | 53.0 s | 60.5 s |
| | m10 t400 | 210 | 5,497 | **4,485** | 9,664 | 63.8 s | 69.2 s |
| GloVe | m2 t160 | 66 | 13,228 | 12,372 | — | 12.5 s | 16.9 s |
| | m5 t400 | 145 | 13,093 | 12,303 | 31,157 | 18.3 s | 22.7 s |
| | m10 t400 | 247 | 13,033 | **12,024** | 30,549 | 23.0 s | 26.1 s |
| SIFT | m2 t160 | 37 | 1,235 | **1,146** | 2,204 | 10.4 s | 12.0 s |
| | m10 t400 | 160 | 1,365 | 1,218 | **2,196** | 18.1 s | 19.4 s |
| Deep-10M | m2 t160 | 53 | 2,418 | **2,278** | **4,822** | 109.4 s | 126.4 s |
| | m10 t400 | 213 | 2,397 | 2,308 | 4,882 | 189.7 s | 201.2 s |

(SIFT/Deep-10M m5 rows in the logs; they sit between m2 and m10.)

Against the full builds (09-25/26 tables, ParlayANN):

| corpus | Vamana | dense (build) | best ours-on-PiPNN (composed) |
|---|---|---|---|
| GIST d@0.95 | 5,281 (632 s) | 4,485 SAT / 4,268 HSP (~250 s) | 4,485 (69 s) |
| GloVe d@0.95 | 9,204 (146 s) | 9,069 (94.7 s) | 12,024 (26 s) |
| SIFT d@0.99 | 2,172 (51.5 s) | 2,155 (51.5 s) | 2,196 (19 s) / 2,204 (12 s) |
| Deep-10M d@0.99 | 5,159 (699 s) | 4,811 (734 s) | 4,822 (126 s) |
| Deep-10M d@0.95 | 2,150 | 2,180 | 2,278 |

## Reading

1. **The ending composes with PiPNN and is worth 4-9% over PiPNN's own**
   at the best pool per corpus (GIST -4%, GloVe -9%, SIFT -7% at 0.95,
   Deep-10M -6% at 0.95 / -8% at 0.99), for +8-16% over the same PiPNN
   arm's build time (GIST's best arm, m10, is 1.7x PiPNN's default build).
2. **Thin pools want a different ending than rich pools.** On PiPNN's
   default 57-candidate GIST pool our alpha-1 prune is 13% worse than
   PiPNN's alpha-1.2 robustPrune; on the 210-candidate pool ours is 18%
   better and PiPNN's own ending degrades (5,497). The heap + alpha-1
   ending needs a rich pool; robustPrune at alpha > 1 compensates for a thin
   one. On SIFT/Deep-10M ours wins already at the default pool.
3. **At 10^7 the composed build reaches the dense build's quality at a
   sixth of its time:** Deep-10M d@0.99 4,822 vs 4,811 (dense, 734 s) vs
   5,159 (Vamana, 699 s), in 126 s. SIFT is at parity with both in 12-19 s
   vs 51.5 s. GIST matches the SAT-spined dense build (4,485) in 69 s vs
   ~250 s; the HSP-spined dense build is still 5% better.
4. **GloVe is where the pool is the lever:** the best composed graph is
   12,024 vs dense 9,069 (+33%). Keeping more of each 1,024-leaf (mst 10)
   helps only 3%; the missing pairs are not in PiPNN's leaves at all
   (transitivity-FINDINGS: GloVe's low-clustering tail).
5. Consequence for paper 2: the contribution that survives on
   partition-friendly data is the ending (heap + alpha-1 prune + HSP spine),
   and it composes with the cheapest partitioner; the dense candidate stage
   is needed only where the kNN graph's clustering tail is heavy (GloVe).
   Untested: our ending with alpha 1.2 on thin pools; mst_deg 20-50 on
   GloVe; Deep-100M/Wikipedia composed.
