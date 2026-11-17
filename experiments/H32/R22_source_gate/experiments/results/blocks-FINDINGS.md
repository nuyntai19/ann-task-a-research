# Block-synchronous mutation of the rootstock (GloVe, 2026-09-15)

Hypothesis (EC): an incremental builder's substrate improves as it goes,
so each insertion searches a better graph; GRAFT searches one frozen,
mediocre scaffold for all n points and must buy the missing routability
with trees (T=32 on GloVe costs 23.5 G, 75% of Vamana's entire build).
Letting the rootstock mutate should recover that.

Implementation: `--harvest-blocks B`. Points are harvested in B blocks
(block = p mod B); within a block the substrate is frozen and writes are
disjoint; between blocks the finished rows are UNIONED into the scaffold
(not replacing it -- a pruned graph is a poor substrate, cf. the S2x2
collapse). Determinism is preserved: hash identical at 1 vs 10 threads,
and `--harvest-blocks 0/1` reproduces the shipped hash exactly.

| arm | build Gdist | build s | compl | d@0.95 | d@0.97 |
|---|---:|---:|---:|---:|---:|
| T8/ef600 frozen | 23.0 | 260 | 0.525 | 10,970 | 17,267 |
| T8/ef600 B=8 | 38.9 | 581 | 0.583 | 9,619 | 14,149 |
| T8/ef600 B=32 | 40.8 | 675 | 0.587 | 9,569 | 14,015 |
| **T8/ef400 B=32** | **28.9** | **401** | **0.574** | **9,670** | **14,182** |
| T4/ef600 B=32 | 34.5 | 601 | 0.581 | 9,730 | 14,300 |
| T32/ef600 frozen (paper quality) | 63.9 | 654 | 0.590 | 9,400 | 13,966 |
| Vamana R100/L200 2-pass | 31.6 | 481 | — | 9,753 | 13,508 |

## Findings

**1. The hypothesis holds.** At T=8, mutation lifts completeness
0.525 -> 0.587 (T32 frozen: 0.590) and d@0.97 17,267 -> 14,015
(T32: 13,966). The feedback loop substitutes for scaffold redundancy:
one quarter of the trees plus mutation equals thirty-two trees frozen.

**2. It moves the frontier, not one point.** T8/ef400/B32 costs 28.9 G
-- essentially the paper's fast profile (T16/ef400, 28.6 G) -- and
gives d@0.97 14,182 against the fast profile's 15,527 (-8.7%) and the
quality profile's 13,966 (+1.5%) at 0.45x its cost. At matched quality
(~14.0k) the old frontier needs 50-64 G; the new one needs 28.9 G, a
1.7-2.2x reduction in build work.

**3. GRAFT now does less build work than Vamana** at parity quality:
28.9 G vs 31.56 G (0.91x), with d@0.95 9,670 vs Vamana's 9,753 (better)
and d@0.97 14,182 vs 13,508 (5% worse). Combined with the measured
per-distance cost factor (~1.5x on GloVe), predicted build wall-clock
is ~1.4x Vamana versus 3.2x today -- a 2.3x improvement, to be
confirmed by paired measurement.

**4. Coarse blocks suffice.** B=8 captures essentially all of B=32
(d@0.97 14,149 vs 14,015, 1%). The feedback is coarse-grained: what
matters is that a point sees a substrate improved by many predecessors,
not by its immediate predecessor. This is what keeps the scheme
deterministic and cheap -- 8 substrate rebuilds, not n.

**5. Determinism is not the price.** The trade is messier code and a
growing substrate (later blocks search a denser graph, which is why
ef600/B32 costs 40.8 G while ef400/B32 costs 28.9 G), not
reproducibility. Hash-identical across thread counts in every arm.

## Next
- paired wall-clock (the claim is build time; distances are a proxy)
- SIFT (does mutation hurt where the frozen design already wins?)
- Deep-10M (does the gain survive scale?)
- sweep (B, T, ef) for the new frontier's knee
- every quality number in the paper is measured on the frozen design;
  a mutation-based system is a NEW baseline and needs a full re-run.
