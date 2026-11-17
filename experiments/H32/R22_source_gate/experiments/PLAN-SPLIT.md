# PLAN-SPLIT — the membership split: is the dense pool the wrong shape?

Written 2026-09-25 after `results/pipnn-FINDINGS.md`. Theory first, every
stage with a refutation criterion (PLANv4-MERGE ground rules). Nothing here
is launched; the stage A/B/D launcher is `bench/d0_split.sh`.

## 0. The identity, and the hypothesis it licenses

Leaf size s = nm/L, pool per point P = ms = nm²/L, candidate work
Σ s²/2 ≈ nP/2 (plus a leaf-variance term). **At fixed P the split (m, s)
is free in the candidate stage.** Paper 2 fixed m = 5 with fat leaves on
the strength of tab:pool, which says the split does not matter — on GloVe,
the one corpus where only the measure scanned counts (high LID). It was
never measured elsewhere. PiPNN's pools are 30 memberships in ~330-point
cells, 3-13x smaller than ours, and PiPNN is within ±6% of Vamana on four
corpora and ahead on GIST, where our pool captures 33% of the true 10-NN
and prunes to mean degree 18 against PiPNN's 33.

| | H | prediction | refuted if |
|---|---|---|---|
| H1 | at fixed P, quality per candidate rises with m on partition-friendly corpora (GIST, Wiki, Deep) and is flat on GloVe | GIST completeness 0.328 → ≥ 0.55 at m = 30; d@0.95 (ParlayANN) < PiPNN's 4,548 at m ≥ 20 | completeness within ±0.05 of 0.328 across the sweep |
| H2 | at m = 30 the dense build reaches PiPNN's quality at PiPNN's pool, P ≈ 10⁴ | GIST d@0.95 within 10% of 4,548 at 5 G candidate distances (26 G today) | d@0.95 > 5,281 (Vamana) at P = 10⁴ |
| H3 | at m = 30 the leader choice stops mattering | random leaders within 5% of Lloyd at m = 30 | random ≥ 15% worse |
| H4 | R2 revisited: the two-level hierarchy's misassignment penalty is diluted at m = 30 (one thirtieth of the pool, not one fifth) | `--dense-top` at m = 30 within 3% of flat membership and no leaf-imbalance blow-up | > 10% worse, or candidate pairs > 1.2x flat |

If H1 fails, PiPNN's edge is not in the pool: look at the exact leaf kNN
and its table merge, not at leaders. If H1 passes and H2 fails, the shape
matters but the dense assembly needs P > 10⁴ and the build-time gap to
PiPNN (6-15x) stays; the paper's claim is then quality at the cost of
build time. If both pass, paper 2 changes its design point (§3), scopes the
"k-means halves the pool" claim (§4), and the GIST/Wiki rows improve.

## 1. Stage A — the split sweep at fixed P, GIST-960 (decisive)

n = 10⁶, baseline L = 700, m = 5: s = 7,143, P = 35,714. Holding P:
L = nm²/P = 28 m².

| arm | m | L | s | Lloyd cost (10 it.) | est. |
|---|---:|---:|---:|---:|---:|
| m5_L700 (baseline, re-run with `--dump-graph`) | 5 | 700 | 7,143 | 2e9 | 8 min |
| m10_L2800 | 10 | 2,800 | 3,571 | 5.6e9 | 10 min |
| m20_L11200 | 20 | 11,200 | 1,786 | 6.3e10 (ns 560k) | 15 min |
| m30_L25200 | 30 | 25,200 | 1,190 | 2.5e11 (ns = n) | 45 min |

Candidate distances ≈ nP/2 = 18 G in every arm (verify from the log; leaf
variance moves it ±30%). Small leaves run the tile at TB = 32 (the rule
halves TB until ≥ 100 blocks); expect the per-pair rate to fall 2-3x, as
measured on SIFT leaves of 3,571. That is a cost we are measuring, not a
confound: the graph does not depend on TB.

Record per arm: completeness, mean degree, stage times, distance counts,
fg's own ladder (continuity with tab:gist) and the ParlayANN ladder via
`-graph_path` (the paper's grader; also fixes tab:gist mixing searchers).
`bench/parse_parlay.py` for d@0.90 / 0.95 / 0.97.

**Gate G0:** the baseline arm must reproduce the paper's GIST row on d0's
current `fg` (built 2026-09-23): completeness 0.328, 18,335,567 directed
edges, candidates 26,377.7 M distances. If it does not, stop and diff the
sources against the laptop's `fgraft` branch before any other arm.

## 2. Stage B — leader choice at high m (H3), GIST

m30_L25200 with `--dense-kmeans 0` (leaders = the seeded sample, no Lloyd)
and `--dense-kmeans 3`. Two arms, ~20 and ~30 min. This decides whether
the 25-min Lloyd at L = 25,200 is needed at all, and therefore whether
Stage C and Stage E can run flat. Note that `--dense-top` does NOT remove
the Lloyd cost — the code runs Lloyd over all L on the sample first and
clusters the leaders afterwards — so at L ≥ 5·10⁴ with Lloyd on, the only
options are random leaders or a hierarchical Lloyd that does not exist yet
(Stage F).

## 3. Stage C — pool reduction at the best split (H2, H4), GIST

Only if H1 passes. P = 10⁴: m = 30, L = 90,000, s = 333 (candidates 5 G);
P = 2·10⁴: m = 30, L = 45,000, s = 667. Flat membership is nL = 9·10¹⁰ at
d = 960, ~10 min; Lloyd is impossible flat (9·10¹² for 10 iterations), so:

| arm | leaders | membership |
|---|---|---|
| P1e4_flat | `--dense-kmeans 0` | flat |
| P1e4_top | `--dense-kmeans 0 --dense-top 300 --dense-probe 3` | approximate, n(300 + 3·300) |
| P2e4_flat | `--dense-kmeans 0` | flat |

P1e4_top vs P1e4_flat is the H4 test. At s = 333 the tile runs 11 blocks
of 32; the per-pair rate measured here decides whether the small-leaf GEMM
kernel (Stage F) is worth writing. Do not write it first.

Success: P1e4 d@0.95 within 10% of PiPNN's 4,548 and a whole build under
150 s (430 s today; PiPNN 35 s).

## 4. Stage D — the same frontier for PiPNN (fairness), GIST

PiPNN at our current pool so both methods are compared at equal P:
`-fanout_scheme 10,10,1` (100 memberships, P ≈ 3.3·10⁴) and
`-cluster_size 4096` (30 × ~1,300, P ≈ 3.9·10⁴). Two arms, ~2 min each,
same flags as `bench/d0_pipnn.sh` otherwise. Prediction: PiPNN improves
further (its ceiling is not saturated at P = 10⁴). If it beats the best
dense arm at equal P, the dense pool assembly is inferior at equal budget
and the k-means claim falls outright; if the m = 30 dense arm matches it,
the two are the same method modulo leaders and the paper should say so.

## 5. Stage E — replication where the paper's rows live

Only after A-D. Same protocol, dump + ParlayANN grading.

| corpus | current (m, L, s, P) | split arms | leaders | est. |
|---|---|---|---|---:|
| GloVe (control) | 5, 240, 24,657, 1.2e5 | m20/L3840 | Lloyd 10 | 5 min |
| Deep-10M | 5, 2,400, 20,833, 1.0e5 | m20/L38400, m30/L86400 | kmeans 0 (Lloyd 45 min at L = 86k; add it only if B says it matters) | 30 min each |
| Wikipedia | 5, 1,600, 19,844, 1.0e5 | m20/L25600, m30/L57600 | kmeans 0 (Lloyd flat is 3.5 h); flat membership nL = 3.7e11 at d = 1024 ≈ 45 min, or `--dense-top 240 --dense-probe 3` if H4 passed | 1-1.5 h each |

Predictions: GloVe flat within 3% (the regime story: the split matters only
where partitioning localises); Deep-10M gains ≤ 5% (its pool already
captures 0.60 and dense already beats PiPNN there); Wikipedia gains, and
its d@0.98 deficit to Vamana (+10%) closes with the higher degree.

## 6. Stage F — engineering, only if A and C pass

1. **Small-leaf kernel:** below ~2,000 points, a plain s × s × d GEMM of the
   leaf against itself (PiPNN's EigenKNN) instead of the 4x4 tile at
   TB = 32. Gate: bitwise-identical graph (offers commute).
2. **Hierarchical Lloyd:** Lloyd on a top level of √L centroids, then
   per-group Lloyd on the sample — makes k-means affordable at L ≥ 5·10⁴ if
   Stage B says it is needed. Gate: Proposition 1 (hash identical at 1 vs
   64 threads).
3. **Membership scan as a blocked GEMM** (already flagged in R3: 3.2x).

## 7. Machine, order, cost

d0, idle at the time of writing (load 1.0, no campaign tmux). **d0 is shared
with the SOLO 10⁹ line; check `uptime` and `tmux ls` and the author before
launching.** Outputs to `/mnt/raid/fgraft-campaign-2026-09-22/split/`
(GIST graphs ~100 MB each, Wikipedia ~1 GB; safe to delete). Stages A+B+D
are one chain, `bench/d0_split.sh` → `run_split.sh` on d0, tmux
`fgsplit`, marker `SPLIT_DONE`, **~2.5 h wall**. Stage C is a second chain
of ~1 h once A is read. Stage E is ~5 h. Stage F is laptop work, days.

## 8. Stage A result (2026-09-25): H1 refuted — see `results/split-FINDINGS.md`

Completeness 0.328 → 0.337, degree 18.3 → 18.0, d@0.95 flat within 2.5%
across m = 5..30 at fixed P; candidate cost rose 2.1x from leaf imbalance
and Lloyd 370x. Stages B, C are moot. The regrade puts the paper's GIST
dense row at d@0.95 = 4,485 on ParlayANN (tie with PiPNN, 15% ahead of
Vamana). Next: the P-sweep at m = 5 (§ "What to test next" in the findings).

## 9. SOLO candidates (author's idea, 2026-09-25): E1 refuted under count scoring — see `results/solo-FINDINGS.md`

Count-ranked top-C pools from MISIFU (α 2%, k_b 16/32, C 500-4000) build
graphs 23-67% worse than the leaf pool at 0.95 on GIST; d@0.95 saturates
in C, k_b helps. Edge diagnostic: precision failure from hub posting lists
(fewer near edges, more far ones). E1b (idf, rank-idf) running.

## 10. Branch closed (2026-09-25, author): the SOLO-candidates line is dropped

idf scoring changed nothing (5,809 / 5,874 vs count 5,773 / 5,818);
rank-idf and the α 1.2 arm were stopped unfinished. Closing assessment in
`results/solo-FINDINGS.md`. PLAN-SPLIT as a whole ends here: neither the
split (stage A) nor a count-ranked pool improves the dense construction on
GIST; what stands from the day is the ParlayANN regrade of tab:gist
(dense 4,485, a tie with PiPNN and 15% ahead of Vamana) and the 255 s build
time. The untested remainder is the P-sweep at m = 5 (§ "What to test
next" in `results/split-FINDINGS.md`), which is a cost question only.

## 11. The localizer construction, single-id form (author, 2026-09-25): works, converges on PiPNN — see `results/random-FINDINGS.md`

`--dense-kmeans 0` with many memberships: random L 90,000 / m 30 gives
d@0.95 = 4,419 on GIST (paper's k-means build 4,485, PiPNN 4,548) at a
nominal pool 3.6x smaller — but 50 min against PiPNN's 35 s, all of it in
the n·L membership scan (1,576 s), hub cells (max 25k vs mean 333, 4.6x
the nominal pairs) and the tile on tiny cells (0.017 G/s). Quality tracks
the effective (size-biased) pool with a ~2% bonus for many memberships.
§4's "only the measure matters" sentence contradicts Table 2 and must be
fixed. Untested: the subset-hashed keys, the part with no flag.
