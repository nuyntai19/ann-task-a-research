# Phase 1 — paired build wall-clock on d0 (running notes)

d0: 4-socket Xeon E7-4809 v3, 64 threads, otherwise idle. Driver
`bench/d0_phase1.py`, launched 2026-09-16 19:53 in tmux; 10 blocks, 8 arms
per block, seeded random order within block, COOL 5 s. Manifest
`results/phase1/phase1-glove-d0-s1.json`; per-build stdout in
`results/phase1/glove-bNN-<arm>.log`. Statistics come at the end from
`graft-ann/bench/paired_stats.py` (Hodges–Lehmann + exact Wilcoxon).

## Phase 0 on d0 (closed)
- determinism hash identical at 1 vs 64 threads for B ∈ {0,2,8,32}
  (smoke config n=200k d=128 T16 ef64): 7bd92120d7274f84 / 1fcb23145cf9ed2e /
  4dd4fc11f7e61790 / a21721a651d1ba40.
- frozen path (`--harvest-blocks 0`) reproduces the published `main` hash on
  d0 (7bd92120d7274f84; AVX2 kernels, so it differs from the laptop's NEON
  379f5544ef827321 by design).
- Vamana SIFT build count reproduces exactly (11,057,965,320) and the GloVe
  query ladder reproduces the paper's column (9,752 @0.954, 13,508 @0.971).
- laptop: published T32/ef600 arm reproduces exactly (63.9 G, compl 0.590,
  d@0.95 9,400, d@0.97 13,966).

## Block 0 (GloVe, single block — NOT the paired statistic yet)

| arm | build s | Gdist | compl | d@0.95 | d@0.97 | wall/Vam | dist/Vam | per-dist |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| graft T32/ef600 frozen | 399.8 | 63.87 | 0.590 | 9,400 | 13,950 | 2.73 | 2.02 | 1.35 |
| graft T16/ef400 frozen | 182.2 | 30.28 | 0.550 | 10,151 | 15,513 | 1.25 | 0.96 | 1.30 |
| **fgraft T8/ef400 B=8** | **227.8** | **27.66** | 0.570 | 9,739 | 14,234 | **1.56** | 0.88 | 1.78 |
| fgraft T8/ef400 B=32 | 288.4 | 28.86 | 0.574 | 9,662 | 14,156 | 1.97 | 0.91 | 2.16 |
| Vamana R100/L200 α1 2-pass | 146.3 | 31.56 | — | 9,204 | 13,325 | 1.00 | 1.00 | 1.00 |
| PiPNN R100/L200 | 10.3 | — | — | 13,324 | 18,855 | 0.07 | — | — |
| hnswlib M16 (efC 200) | 41.0 | — | — | — | — | 0.28 | — | — |
| hnswlib M32 (efC 200) | 65.6 | — | — | — | — | 0.45 | — | — |

d@r interpolated between adjacent ladder points for every system (the
paper's Vamana column quoted raw ladder points, 9,752/13,508).

Observations (provisional, one block):
1. The distance counts are platform-independent to <1% (T32 63.87 G on both
   machines; B32 28.86 vs 28.9; Vamana 31.56 exact) — the proxy transfers.
2. **The mutating path costs more per distance**: 1.78× (B8) / 2.16× (B32)
   against 1.30–1.35× for the frozen arms. Threat 1 of CONTEXT.md §6 is
   real: the denser, growing substrate is a worse pointer chase. The
   prediction "0.91× work × 1.5× ⇒ ~1.4× wall" comes out at **1.56× (B8)**;
   B32 at 1.97× buys nothing over B8 in quality and costs 27% more wall.
   B=8 is the operating point.
3. Against the decision rule (≤1.5× Vamana at parity quality): block 0 says
   1.56× with d@0.95 +5.8% / d@0.97 +6.8% vs Vamana. Marginal on the wall
   threshold, not yet at parity on quality. Versus the frozen design it is
   2.73× → 1.56×, a 1.75× improvement in build time at the same quality
   class (T32/ef600 gives 9,400/13,950).
4. Laptop-table note: the "T16/ef400 = 28.6 G" entry in CONTEXT.md came
   from a run with different flags; the standard arm is 30.3–30.4 G on both
   machines.

## GloVe, 10 blocks (complete 2026-09-17; paired statistics)

Medians over 10 blocks; IQR ≤ 0.5% for every arm (no drift on d0). Every
GRAFT-family arm produced an identical distance count and completeness in
all 10 blocks (deterministic graph, 64 threads). d@r interpolated at r.

| arm | median s | Gdist | compl | d@0.95 | d@0.97 | d@0.95 /Vam | d@0.97 /Vam |
|---|---:|---:|---:|---:|---:|---:|---:|
| GRAFT T32/ef600 frozen | 390.6 | 63.87 | 0.590 | 9,400 | 13,950 | 1.021 | 1.047 |
| GRAFT T16/ef400 frozen | 181.3 | 30.28 | 0.550 | 10,151 | 15,513 | 1.103 | 1.164 |
| **FGRAFT T8/ef400 B=8** | **226.3** | 27.66 | 0.570 | 9,739 | 14,234 | 1.058 | 1.068 |
| FGRAFT T8/ef400 B=32 | 287.2 | 28.86 | 0.574 | 9,662 | 14,156 | 1.050 | 1.062 |
| Vamana R100/L200 α1 2-pass | 145.9 | 31.56 | — | 9,204 | 13,325 | 1 | 1 |
| PiPNN R100/L200 | 10.4 | — | — | 13,320 | 18,825 | 1.447 | 1.413 |
| hnswlib M16 / M32 (efC 200) | 41.2 / 65.9 | — | — | — | — | — | — |

Hodges–Lehmann build-time ratios (10 paired blocks, exact Wilcoxon p = 0.002
in every row, 10/10 or 0/10 blocks agree):

| A vs B | HL ratio [95% CI] |
|---|---|
| FGRAFT B=8 vs Vamana | **1.55 [1.55, 1.56]** |
| FGRAFT B=32 vs Vamana | 1.97 [1.96, 1.98] |
| GRAFT T32/ef600 vs Vamana | 2.68 [2.67, 2.70] |
| GRAFT T16/ef400 vs Vamana | 1.24 [1.24, 1.25] |
| FGRAFT B=8 vs GRAFT T32/ef600 | 0.58 [0.58, 0.58] |
| FGRAFT B=8 vs GRAFT T16/ef400 | 1.25 [1.24, 1.26] |
| FGRAFT B=8 vs PiPNN | 21.8 [21.6, 22.2] |
| FGRAFT B=8 vs hnswlib M16 / M32 | 5.49 [5.47, 5.53] / 3.43 [3.42, 3.45] |

Per-distance cost (wall ratio / distance ratio vs Vamana): frozen 1.33×
(T32) / 1.29× (T16); mutating **1.77× (B=8) / 2.16× (B=32)**.

### Reading against PLAN.md's decision rule
- **Refutation criterion ("wall-clock ratio ≥ the frozen design's 3.2×")**:
  not triggered. FGRAFT B=8 is 1.55× Vamana; the frozen quality profile on
  this machine is 2.68× (the paper's 3.21× was the laptop).
- **Full-paper criterion ("≤ 1.5× Vamana at parity quality")**: **missed on
  both counts, narrowly**. 1.55× (CI excludes 1.5), and quality is 5.8% /
  6.8% more distances per query than Vamana at 0.95 / 0.97 — the same
  quality *class* as GRAFT T32/ef600 (+2.1% / +4.7%), not parity.
- **Versus the frozen design at matched quality class**: 0.58× the build
  time of T32/ef600 (1.73× faster) with 0.43× its distance work; the
  wall-clock gain is smaller than the distance gain because the mutating
  harvest costs 1.77× per distance against the frozen 1.33×.
- **B=8 dominates B=32**: same quality within 1%, 27% less wall-clock.
  The feedback is coarse-grained (CONTEXT §4.3 finding iv) *and* the
  finer batching costs real time — later blocks search a denser substrate.

Open for the rest of the campaign: (a) the per-distance gap of the mutating
path is the new engineering target (substrate degree growth; the
"union-with-cap" ablation of Phase 4 is now a *cost* question, not only a
quality one); (b) whether an ef/T retune of the B=8 arm (e.g. T8/ef300 or
T4/ef400) reaches ≤1.5× while holding the T32-class quality — a cheap
Phase 2 sweep on d0 decides this; (c) SIFT (running) and Deep-10^7.

## SIFT, 10 blocks (complete 2026-09-17; paired statistics)

Medians over 10 blocks; the fg beam ladder starts at ef 60, where every
GRAFT-family graph is already above recall 0.97 on SIFT, so quality is
matched at 0.98 and 0.99 (bracketed for all arms). Distance counts identical
in all 10 blocks for every GRAFT-family arm.

| arm | median s | IQR % | Gdist | compl | d@0.98 | d@0.99 | d@0.98 /Vam | d@0.99 /Vam | wall /Vam | dist /Vam | per-dist |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| GRAFT T4/ef400 frozen | 52.1 | 5.8 | 5.15 | 0.483 | 1,739 | 2,317 | 1.074 | 1.067 | 1.01 | 0.47 | 2.16 |
| GRAFT T16/ef400 frozen | 104.3 | 1.1 | 12.08 | 0.498 | 1,623 | 2,150 | 1.002 | 0.990 | 2.02 | 1.09 | 1.85 |
| FGRAFT T4/ef400 B=8 | 95.5 | 3.5 | 8.38 | 0.496 | 1,637 | 2,180 | 1.011 | 1.004 | 1.85 | 0.76 | 2.44 |
| **FGRAFT T2/ef400 B=8** | **89.6** | 1.1 | 8.03 | 0.492 | 1,633 | 2,195 | 1.008 | 1.011 | **1.73** | 0.73 | 2.39 |
| FGRAFT T4/ef400 B=32 | 122.7 | 2.0 | 8.72 | 0.498 | 1,631 | 2,166 | 1.007 | 0.997 | 2.37 | 0.79 | 3.01 |
| Vamana R64/L128 α1.15 2-pass | 51.7 | 0.5 | 11.06 | — | 1,619 | 2,172 | 1 | 1 | 1 | 1 | 1 |
| PiPNN R64/L128 | 8.8 | 1.2 | — | — | 1,782 | 2,264 | 1.100 | 1.042 | 0.17 | — | — |
| hnswlib M16 / M32 (efC 200) | 29.4 / 37.2 | 0.3 | — | — | — | — | — | — | 0.57 / 0.72 | — | — |

Hodges–Lehmann build-time ratios (10 paired blocks):

| A vs B | HL ratio [95% CI] | Wilcoxon p |
|---|---|---|
| GRAFT T4/ef400 vs Vamana | 1.02 [0.99, 1.03] | 0.30 (5/10 blocks) — parity |
| GRAFT T16/ef400 vs Vamana | 2.01 [2.00, 2.03] | 0.002 |
| FGRAFT T4/ef400 B=8 vs Vamana | 1.85 [1.83, 1.88] | 0.002 |
| FGRAFT T2/ef400 B=8 vs Vamana | 1.73 [1.72, 1.75] | 0.002 |
| FGRAFT T4/ef400 B=32 vs Vamana | 2.37 [2.35, 2.39] | 0.002 |
| FGRAFT T2/ef400 B=8 vs GRAFT T4/ef400 | 1.72 [1.67, 1.75] | 0.002 |

### Reading
- **The expected regime dependence shows up** (PLAN.md Phase 2 prediction):
  on SIFT the frozen scaffold is already cheap (T4 does 0.47× Vamana's work
  at wall parity), so mutation has little cost to remove. What it buys is
  *quality*: T4 frozen is 7% behind Vamana in distances/query, and every
  mutating arm reaches parity (within ±1%) — the same quality as T16 frozen.
- **At parity quality, mutation is 8–14% faster than the frozen T16**
  (1.73–1.85× vs 2.01× Vamana) while doing 0.73–0.76× Vamana's distance
  work against T16's 1.09× — i.e. the *work* drops 30% but the wall-clock
  only 10%, because the mutating path's per-distance cost on SIFT is
  **2.4× (B=8) / 3.0× (B=32)** against the frozen 1.85–2.16×.
- **T2 + mutation = T16 frozen quality**, with one eighth of the trees. The
  substitution result of GloVe holds on SIFT at an even more extreme ratio.
- **B=8 dominates B=32 again** (2.37× vs 1.73–1.85×, same quality).
- **Per-distance cost is now the dominant term** on both datasets: the
  mutating harvest's edge is a denser substrate (union of scaffold + finished
  rows), and the beam over it is a worse pointer chase than over the frozen
  scaffold. Closing *that* gap (not adding trees or ef) is what would move
  FGRAFT under the 1.5× line: at the measured work ratios (0.73–0.88×) any
  per-distance cost ≤ 1.7× would do it on both datasets.

### Phase 1 verdict (both datasets)
Wall-clock follows the distance count on both datasets (refutation criterion
not triggered), the mutating design is 1.55× (GloVe) / 1.73× (SIFT) Vamana at
the T32/T16-frozen quality class, and never at ≤1.5× with parity. Decision
rule → **short-paper territory unless the per-distance cost of the mutating
path is engineered down or a (T, ef) retune crosses 1.5×**. Next: Phase 2
sweep of (T, ef) at B=8 on GloVe (d0, cheap), then the substrate-degree
instrumentation of Phase 4, which is now a cost question.
