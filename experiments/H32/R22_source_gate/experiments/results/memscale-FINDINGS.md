# Memberships at scale: the last regimes of the dense stage close (2026-10-03, d0)

Chain `bench/d0_membership_scale.sh` (05:29-~15:30, all steps rc=0), logs
`results/memscale/`. Composed build = deterministic PiPNN (GRAFT-DET with the
cached-maximum merge) at 60 / 120 leaves per point (fanout 20,3,1 / 40,3,1,
mst 10; table 400, Wikipedia-120 table 800) + our ending (alpha 1.0, 200-heap,
HSP spine s 10k cap 16, no orphan repair). One run each. d@0.95 / d@0.99 on
ParlayANN's searcher; composed time = PiPNN build - its final prune + fg prune
(incl. spine).

| corpus | build | k=10 d@0.95 | d@0.99 | k=100 d@0.95 | time |
|---|---|---|---|---|---|
| Wikipedia | dense + HSP (T5) | 3,840 | --- | 8,030 | 2,161 s |
| | composed, 30 leaves (T1) | 3,750 | --- | 8,713 | 413 s |
| | composed, 60 leaves | 3,218 | 20,034 | 7,681 | 830 s |
| | composed, 120 leaves | **2,888** | 14,822 | **7,185** | 1,669 s |
| | PiPNN own ending, 120 leaves | 4,028 | 19,707 | 8,295 | --- |
| Deep-100M | dense + HSP (T5) | 3,677 | 8,883 | 7,198 | 13,189 s |
| | Vamana | 4,047 | 10,547 | 7,369 | 9,816 s |
| | composed, 30 leaves rich (T1) | 4,108 | 9,516 | 7,795 | 1,785 s |
| | composed, 60 leaves | 3,591 | 8,077 | 7,033 | **6,880 s** |
| | composed, 120 leaves | **3,449** | **7,741** | **6,772** | 16,363 s |
| | PiPNN own ending, 60 / 120 | 4,437 / 4,511 | 12,396 / 12,575 | 8,020 / 8,045 | --- |

Reading:
1. **Both remaining regimes close.** Wikipedia k=100: 120 leaves give 7,185
   against dense 8,030 (-11%) at 0.77x the dense time; k=10 -25%. Deep-100M:
   60 leaves already beat the dense build at every point measured (-2% at
   0.95, -9% at 0.99, -2% at k=100) at 0.52x its time; 120 leaves -6% / -13% /
   -6%, but 1.24x its time, because the deterministic merge's evictions make
   PiPNN's leaf stage 12.0 ks (4.3 ks at 60 leaves).
2. PiPNN's own ending on the same rich pools does not improve (Deep-100M
   4,437-4,511, worse than its default pool's 4,289): the gain is our ending
   on a richer pool, not the pool alone.
3. With C2: Deep's zero-clustering tail grows to 8.1% at 10^8 and Wikipedia's
   is 2.4%; both close at 60-120 leaves per point; GloVe (12.6%) needed 120.
   The memberships needed track the tail, as the cover analysis predicts.
4. Orphans at 10^8 without repair: ~23k (0.023%) of 10^8 vertices unreachable
   from the entry; Wikipedia none.
5. Memory: deterministic PiPNN at 120 leaves, table 400, peaked at 679 GB
   (reservoir 320 GB + dump buffer 160 GB + base).

Consequence for C5: the dense candidate stage has no regime left among the six
corpora and both k measured; a partitioner with enough memberships plus our
ending matches or beats it, in less time where the membership count is the
smallest that closes the gap.

## Follow-up (2026-10-03 evening, `bench/d0_membership_scale2.sh`, logs `results/memscale2/`)

PiPNN GRAFT-DET merge "det4" (cached maximum kept across calls; byte-identical
to the earlier merge on the SIFT/GloVe gates, overhead gone). Composed build,
our ending alpha 1.0, k=10 d@0.95 / d@0.99 / k=100 d@0.95, time as before.

| corpus | leaves | composed | dense + HSP | time (composed / dense) |
|---|---|---|---|---|
| GIST | 60 | **4,172 / 8,682 / 7,111** | 4,268 / 11,098 / 7,509 | 114 / 194 s (0.59x) |
| GIST | 120 | 4,386 / 9,377 / 7,353 | | 190 s |
| Deep-10M | 60 | 2,157 / 4,586 / 4,194 | 2,133 / 4,553 / 4,084 | 349 / 689 s (0.51x) |
| Deep-10M | 120 | **2,093 / 4,345** / 4,090 | | 577 s (0.84x) |
| GloVe | 120 (det) | 9,290 / **23,911 / 19,690** | 9,172 / 24,833 / 20,228 | 74 / 86 s (0.86x) |
| Deep-100M | 120 (det4 rerun) | **3,449 / 7,741 / 6,772** | 3,677 / 8,883 / 7,198 | 7,885 / 13,189 s (0.60x) |

- GIST closes at 60 leaves (-2% / -22% / -5%); 120 is worse. Deep-10M at 120
  is ahead at k=10 and ties at k=100; at 60 within 1-3% at half the time.
  GloVe (det) is +1.3% at 0.95 but ahead at 0.99 and k=100; the original
  merge's single run at 120 was 8,956 (-2.4%).
- Deep-100M 120 rerun: PiPNN build 7,431 s (15,940 s with the per-offer
  rescan); composed 7,885 s, 0.60x the dense build.
- **Determinism at 10^8, residual:** the rerun reproduces quality to the
  digit (3,449 / 7,741 / 6,772; PiPNN's own 4,511 / 12,575) but not bytes:
  candidates 38,110,229,537 vs ...499 (38 of 3.8e10) and edges 4,127,345,658
  vs ...6,186. The two runs used det3 and det4, which are byte-identical on
  the 10^6 gates; the source at 10^8 is not identified. Gated determinism
  holds at 10^6; at 10^8 a ~1e-9 residual remains.

Consequence: with enough leaves per point (60 for GIST, Wikipedia-k10 and
Deep-100M; 120 for GloVe, Wikipedia-k100, Deep-10M) the composed build matches
or beats the dense build on all six corpora at both k, in 0.51-0.86x its time.
