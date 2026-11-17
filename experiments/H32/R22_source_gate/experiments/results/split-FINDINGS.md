# PLAN-SPLIT stage A — H1 REFUTED on GIST-960 (2026-09-25, d0)

Fixed pool P = 35,714, L = 28 m², one build per arm, `bench/d0_split.sh`
(STAGES=A), logs `results/split/`, graded on ParlayANN's searcher via
`-graph_path`. G0 gate passed exactly (0.328 / 18,335,567 / 26,377.7 M).

| arm | leaf mean / max | compl. | deg | cand. G dist | leaders s | cand. s | build wall | d@0.90 | d@0.95 | d@0.97 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| m5_L700 | 7,143 / 28,204 | 0.328 | 18.3 | 26.4 | 12.8 | 160 | 4:31 | 2,898 | **4,485** | 6,055 |
| m10_L2800 | 3,571 / 21,584 | 0.334 | 18.2 | 34.9 | 52 | 242 | 6:22 | 2,929 | 4,560 | 5,895 |
| m20_L11200 | 1,786 / 16,071 | 0.337 | 18.1 | 44.9 | 1,266 | 420 | 29:43 | 3,054 | 4,496 | 6,014 |
| m30_L25200 | 1,190 / 15,573 | 0.337 | 18.0 | 56.3 | 4,744 | 693 | 1:32:03 | 3,066 | 4,596 | 5,995 |

**Refutation criterion met:** completeness moved 0.328 → 0.337 (criterion:
±0.05), degree 18.3 → 18.0, d@0.95 flat within 2.5%. At a fixed pool the
split (memberships × leaf size) does not change what the pool captures on
GIST, exactly as tab:pool found on GloVe. Stages B and C, whose premise was
H1, are moot as designed.

**Cost went the wrong way.** Candidate distances rose 26 → 56 G at "fixed"
P: the identity nP/2 assumes balanced leaves and Lloyd cells on GIST are
not — the largest leaf is 13x the mean at L = 25,200 — so Σ s² grows as
leaves shrink on average but not at the top. Lloyd itself rose 13 s →
4,744 s (ns = n at L ≥ 20,000). PiPNN avoids both with random leaders and a
hard cluster-size cap from its recursive sketch; that is a cost design, not
a quality one.

**The finding that matters is a grading correction.** On ParlayANN's
searcher the paper's own GIST configuration is **d@0.95 = 4,485**, not the
5,209 that tab:gist carries from fg's searcher. Against the same grader:
Vamana 5,281, PiPNN 4,548. So on GIST the dense graph is **15% better than
Vamana and 1.4% better than PiPNN**, and `pipnn-FINDINGS.md`'s "-12.7% vs
dense" line was the searcher mismatch. GIST is a tie with PiPNN on quality;
the difference is cost only: 26 G candidates and 255 s against PiPNN's
7 G and 35 s, at a pool 3.6x larger.

**Build-time correction for tab:gist:** 430.5 s (336 s candidates) was the
pre-adaptive-tile kernel; today's identical graph builds in 255 s (160 s
candidates), 0.40x Vamana rather than 0.68x.

## What to test next (not launched)

Since shape is irrelevant, the only lever left on GIST is the pool's
measure, and PiPNN says 10⁴ suffices for this quality. **P-sweep at m = 5:**
L = 1,400 (P = 1.8·10⁴), 2,500 (10⁴), 5,000 (5·10³); each arm ~2-3 min,
Lloyd and membership trivial. Prediction: d@0.95 within 5% of 4,485 at
P = 10⁴, candidates 5 G, build ~60 s — the GIST row then beats Vamana on
quality at ~0.1x its build time, and PiPNN's cost edge shrinks to ~2x. The
identical sweep on Wikipedia (L = 6,400 / 16,000) is the replication.
Refuted if d@0.95 > 5,281 at P = 10⁴ (dense falls to Vamana at PiPNN's
pool, and PiPNN's per-candidate efficiency is real).
