# FGRAFT — the campaign

Goal: turn "T=8 with block mutation costs less build work than Vamana at
parity quality, deterministically" from a one-dataset distance-count result
into a defensible paper. Phases are ordered so that the cheapest thing that
could refute the claim runs first.

Machines: **laptop** (M5, 10 threads, thermally noisy — distances only, or the
paired protocol) and **d0** (4-socket Xeon E7-4809 v3, 32 cores / 64 threads,
1.5 TB RAM, NVMe; no thermal drift, IQR 1–3%). Datasets at 10^6 on both;
Deep-10^7/10^8 and Wikipedia-6.35M on d0 only.

---

## Phase 0 — gate (30 min, either machine)  — DONE 2026-09-16/17 (both machines)

- [ ] Apply `patches/fg-mutation-and-scaffold-cap.patch` to a clean
      `graft-ann` clone; build with 0 warnings.
- [ ] `--check-determinism` with `--harvest-blocks` 0, 2, 8, 32: identical
      hash across thread counts in each case.
- [ ] `--harvest-blocks 0` reproduces the shipped GRAFT hash on that machine
      (the frozen path must be untouched).
- [ ] Re-run one published GRAFT arm and confirm the paper's numbers
      reproduce (GloVe T32/ef600 frozen → d@0.95 ≈ 9.4k, d@0.97 ≈ 14.0k).

**Refutes if:** any hash differs across threads, or the frozen path moved.

## Phase 1 — the build-time claim (d0, ~1 day)  — DONE 2026-09-17: 1.55× (GloVe) / 1.73× (SIFT) Vamana; see results/phase1-NOTES.md

Distances are a proxy; the claim is wall-clock. Paired, repeated-build design
(block = pairing unit, seeded random order, Hodges–Lehmann ratio + exact
Wilcoxon, `bench/paired_stats.py`), 10 blocks, all 64 threads, GloVe and SIFT.

Arms: GRAFT frozen T32/ef600 (published quality profile) · GRAFT frozen
T16/ef400 (fast) · **FGRAFT T8/ef400 B=8** · **FGRAFT T8/ef400 B=32** ·
Vamana (authors' params) · PiPNN · hnswlib M16/M32.

- [ ] wall-clock ratios with CIs, per pair
- [ ] build distance counts for every arm (fg prints them; ParlayANN via
      `patches/parlayann-build-distance-counter.patch`)
- [ ] per-distance cost = (wall ratio)/(distance ratio) for each arm

**The number the paper lives on:** FGRAFT vs Vamana build wall-clock at
matched quality. Predicted ~1.4× (i.e. still slower) from 0.91× work × ~1.5×
per-distance cost. If the mutating path's per-distance cost is *worse* than
the frozen path's (denser substrate, worse locality), the prediction fails —
measure it, do not assume it.

**Refutes if:** wall-clock ratio ≥ the frozen design's 3.2×.

## Phase 2 — generality (d0 + laptop, ~1 day)  — NOT RUN (superseded by the wall finding; SIFT covered in Phase 1)

- [ ] SIFT: does mutation help, or hurt where the frozen design already wins
      on work (0.48× Vamana)? Arms: T4 frozen, T4 B=8, T2 B=8, T4 B=32.
- [ ] GIST (960-d, the ambient-dimension case) and Fashion (the easy case).
- [ ] Wikipedia BGE-M3 200k (high concentration, easy search).
- [ ] The (T, ef, B) frontier on GloVe: T ∈ {4,8,16}, ef ∈ {200,300,400,600},
      B ∈ {1,4,8,16,32}. Report the frontier, not a point; the knee is the
      paper's recommended default.

**Expected shape:** mutation buys the most where the frozen scaffold needed
the most trees (GloVe, GIST); little or nothing where T is already small
(SIFT, Fashion, BGE-M3). That regime dependence is a *result*, not a caveat.

## Phase 3 — scale (d0, ~2 days)  — NOT RUN

- [ ] Deep-10^7: T8/ef400 B∈{1,8,32} vs the published T8/ef400 frozen arm.
- [ ] Deep-10^8 if 10^7 holds. Watch memory: the substrate grows by ~2·cap
      edges per harvested point (~+50 GB at 10^8 with cap 64 — check before
      launching, and consider capping the *added* edges, which is a new
      experiment, not a default).
- [ ] Does patience compose with mutation? (`--harvest-patience 64` on the
      best B arm.) Both cut harvest cost; they may not be additive.

**Refutes if:** the gain vanishes at 10^7, or memory makes 10^8 infeasible
without a quality-costing cap.

## Phase 4 — mechanism (laptop, ~1 day)  — NOT RUN (density study covers the block-coherence question)

The paper needs *why*, not just *how much*.

- [ ] Per-block instrumentation: substrate degree, harvest distances per
      point, and completeness of the rows produced, as a function of block
      index. The prediction is that early blocks are expensive and poor, later
      blocks cheap and good — the feedback loop made visible.
- [ ] Funnel census (`bench/funnel_census.py` in graft-ann) on an FGRAFT graph
      vs a frozen GRAFT graph vs Vamana: does mutation raise certified funnel
      mass, or just completeness?
- [ ] Ablation: union-into-scaffold (current) vs replace-scaffold (expected to
      collapse, per GRAFT's S2×2 result) vs union-with-cap.
- [ ] Block assignment ablation: `p mod B` vs seeded random blocks vs
      contiguous id ranges. Tests whether the result depends on mixing.

## Phase 5 — write (~3 days)  — DONE 2026-09-18 as the short paper with the wall finding

Draft exists: `../FGRAFTPaper/fgraft.tex`. Fill in the measured tables, then:

- [ ] decide the honest framing against ParlayANN's batch rounds (related
      work must be explicit: what is new is the forest bootstrap + the
      quantified separation of feedback from serial dependency)
- [ ] the determinism proposition needs restating for the blocked case
      (function of data, seed, params **and B**)
- [ ] target venue: SISAP (short, if the result is modest) or
      VLDB/EDBT/Information Systems (full, if Phase 1 lands ≤1.5× Vamana with
      parity quality and the mechanism section holds)

---

## Decision rule (set in advance, do not move it)

- **Full paper** if: FGRAFT reaches Vamana-parity quality at ≤1.5× Vamana's
  build wall-clock on GloVe *and* the gain survives Deep-10^7 *and*
  determinism holds.
- **Short paper / note** if: the gain is real but ≤1.3× improvement over the
  frozen design, or it does not survive scale.
- **Codebase update only** if: Phase 1 shows the wall-clock does not follow
  the distance count.
