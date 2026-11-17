# Scaffold cap + baseline build cost (2026-09-15)

## Vamana build distance count (new instrumentation)
Patched `external/PiPNN/algorithms/vamana/neighbors.h` to print the
build-side counter it already computes (`BUILD_DISTANCES`); only the
range-search branch printed it before. Backup:
`neighbors.h.bak-distcount`. Query numbers of the GloVe run reproduce
the paper's Vamana column exactly (9,753 / 13,508 at recall
0.954/0.971), so the configuration matches.

| system | build Gdist | vs Vamana | wall vs Vamana (paired) | per-distance cost |
|---|---:|---:|---:|---:|
| Vamana SIFT R64/L128 2-pass | 11.06 | — | — | — |
| GRAFT SIFT T4/ef400 | 5.3 | 0.48x | 0.94x | ~1.96x |
| GRAFT SIFT T16/ef400 | 12.1 | 1.09x | 2.22x | ~2.03x |
| Vamana GloVe R100/L200 2-pass | 31.56 | — | — | — |
| GRAFT GloVe T16/ef400 (fast) | 28.6 | 0.91x | 1.34x | ~1.47x |
| GRAFT GloVe T32/ef600 (quality) | 60.5 | 1.92x | 3.21x | ~1.67x |

**Finding 1.** The per-distance cost gap is 1.5-2.0x and stable across
datasets and profiles -- consistent with the searcher control (glass
serves the same graph 2.0x faster than our beam). This is the
engineering factor.

**Finding 2.** Work volume is regime-dependent: on SIFT at the
headline profile GRAFT does HALF Vamana's distance work (and still
only ties on wall-clock -> the SIFT deficit is entirely
implementation); on GloVe quality it does 1.9x the work, so about half
of the 3.2x there is genuinely more work.

## Scaffold-degree cap sweep (new `--scaffold-cap`, GloVe T32/ef600)
Determinism gate passes; `--scaffold-cap 0` reproduces the shipped
hash (default path untouched). Uncapped scaffold: mean degree ~56,
max 1511.

| cap | build Gdist | harvest s | compl | d@0.95 | d@0.97 |
|---:|---:|---:|---:|---:|---:|
| 0 (off) | 63.9 | 635 | 0.590 | 9,400 | 13,966 |
| 96 | 57.8 | 546 | 0.586 | 9,526 | 14,200 |
| 64 | 52.6 | 482 | 0.578 | 9,747 | 14,419 |
| 48 | 47.8 | 425 | 0.569 | 10,235 | 15,186 |
| 32 | 40.6 | 303 | 0.543 | 10,945 | 17,353 |
| 24 | 36.7 | 239 | 0.518 | 12,329 | — |

**Finding 3.** Capping works mechanically -- cap 32 cuts harvest
wall-clock by 52% and build distances by 36% -- but it is NOT free:
d@0.97 degrades monotonically (+3% at cap 64, +24% at cap 32), and
completeness falls 0.590 -> 0.518. Routability does need most of the
union's redundancy.

**Finding 4 (the decisive one).** Capping is OFF the efficient
frontier: at matched build cost, lowering harvest ef beats capping the
scaffold every time (ef 400 at 50.3 G gives d@0.97 14,047 while cap 64
at 52.6 G gives 14,419; the gap widens to 12% at the cheap end). The
existing ef knob already dominates this lever, so the scaffold cap is
not a new degree of freedom worth shipping as a recommendation.

## Consequence for the follow-up
The algorithmic lever is refuted: GRAFT's extra work on hard data
cannot be removed by thinning the scaffold without paying more in
query cost than is saved in build cost. What remains is the 1.5-2x
per-distance engineering factor. Closing it would make SIFT builds
~2x faster than Vamana and GloVe quality ~1.9x slower -- an
improvement, not a collapse of the regime map. On the threshold set
before running (within ~2x of PiPNN at preserved quality = paper;
otherwise note), this is a **note plus a codebase update**, not a
second paper.

Incidental: `data/glove_gold.npy` was missing; recomputed and verified
100% agreement (top-10 and top-100) with `glove_gt100`, the answer key
the baselines are graded on.
