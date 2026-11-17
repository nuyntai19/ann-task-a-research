# Warm-started k-means for the leaves — GIST-960, M5, 2026-09-29

**Question (author):** what share of the build is the k-means stage, how
many iterations does fg use, and is a warm start (centroids of a witness
plus its HSP neighbourhood, 1-2 hops) worth trying?

## Cost of the leaders stage in fg (10 Lloyd iterations on a sample of max(200k, 50L) points, then the n·L membership scan)

| build | leaders | candidates | prune | spine | leaders' share |
|---|---:|---:|---:|---:|---:|
| GloVe L240/m5 | 0.7 s | 74.4 | 18.8 | 10.6 | 0.7% |
| GIST L700/m5 | 13.2 s | 158.6 | 48.6 | 31.0 | 5% |
| Deep-10M L2400/m5 | 20.5 s | 606.8 | 106.4 | 37.0 | 2.7% |
| GIST L11200/m20 (stage A) | 1,266 s | 420.3 | 51.2 | 33.4 | 71% |
| GIST L25200/m30 (stage A) | 4,744 s | 692.5 | 48.9 | 31.1 | 86% |

At the paper's design points k-means is 1-5% of the build. It dominates
only at L ≥ 10⁴, and there because the sample grows with L (ns = 50L, so
Lloyd costs 500·L²·d per iteration), not because of the iteration count.

## Initialisation and iterations (`bench/kmeans_init_diag.py`, numpy replica of fg's Lloyd; L 700, m 5, symmetric leaves; pairs at 10 it. reproduce fg's 26.4 G)

| init | it 0 | it 1 | it 2 | it 3 | it 5 | it 10 |
|---|---|---|---|---|---|---|
| fg (random sample points) | 0.900 @ 120k, 61.3 G, max 88k | 0.887 @ 68k, 34.5 G | 0.887 @ 59k, 29.7 G | 0.891 @ 55k, 28.0 G | 0.893 @ 53k, 26.8 G | **0.895 @ 52k, 26.4 G, max 32k** |
| k-means++ | 0.926 @ 161k, 79.6 G | 0.904 @ 90k, 45.7 G | 0.908 @ 78k, 39.2 G | 0.906 @ 73k, 36.6 G | 0.904 @ 69k, 34.5 G | 0.909 @ 65k, 32.9 G, max 60k |
| HSP-smoothed, 1 hop (deg 15) | 0.816 @ 43k, 21.6 G, max 25k | 0.846 @ 40k, 20.3 G | 0.860 @ 41k, 20.4 G | 0.867 @ 41k, 20.7 G | 0.871 @ 42k, 21.2 G | 0.881 @ 44k, 22.1 G, max 23k |
| HSP-smoothed, 2 hops (deg 193) | 0.761 @ 78k, 38.9 G | 0.840 @ 54k, 27.1 G | 0.852 @ 47k, 23.8 G | 0.857 @ 46k, 23.0 G | 0.866 @ 45k, 22.7 G | 0.875 @ 46k, 23.1 G, max 36k |

(cells: recall of true-neighbour pairs @ pool per point, all-pairs cost, largest leaf)

Three findings.

1. **Lloyd's job is balance, not recall.** From random leaders (it 0) to
   ten iterations the recall moves from 0.900 to 0.895 while the pairs
   fall from 61 G to 26 G and the largest leaf from 88k to 32k. "k-means
   halves the pool" (Table 2) is really "Lloyd halves the pairs at the
   same recall by taming the hub cells". Three iterations get 28 G; ten
   get 26.4 G. The iteration count is not where time goes.
2. **k-means++ is the wrong direction for this use**: it spreads centroids
   into sparse regions, leaves the dense cells large (max 60k) and costs
   25% more pairs for one point of recall.
3. **The HSP-smoothed start converges to a different, cheaper partition:**
   22 G pairs at recall 0.881 against 26.4 G at 0.895, with the largest
   leaf 23k against 32k. The smoothing (each witness replaced by the mean
   of itself and its HSP neighbours) is a local-density move that Lloyd
   from random points does not find. A 16% cut in the candidate stage for
   1.4 points of pool recall; whether the graph notices the recall is the
   open question (with the heap, pools of recall ~0.8 built ceiling-class
   graphs). The two-hop smoothing is worse than one hop.

**Verdict.** Not worth it as a time saver at the paper's design points
(k-means is 1-5% of the build) and not the fix at L ≥ 10⁴ (the sample
rule is). Possibly worth it as a *pair* saver: an HSP-smoothed start plus
a few Lloyd iterations gives the same leaves at ~16% fewer pairs. The
end-to-end test needs fg to accept initial leaders from a file (small
change) and one GIST build; expected effect: candidate stage 159 s → ~135
s, quality unchanged if recall 0.88 suffices. Not run.

## End to end on d0 (2026-09-29, `bench/d0_warm.sh`, `results/warm/`): the warm start holds

GIST L 700 / m 5, fg with `--dense-leaders-file` (graft-ann 3811ead); the
gate reproduced the paper's build exactly. Random and HSP-smoothed leaders
start from the same 700 points (seed 1, laptop), HSP degree 16.

| leaders | Lloyd it. | max leaf | candidate pairs | candidates s | compl. | d@0.90 | d@0.95 | d@0.97 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| fg's own sample (paper) | 10 | 28,204 | 26.4 G | 160.6 | 0.328 | 2,898 | 4,485 | 6,055 |
| random file (control) | 10 | 44,394 | 28.2 G | 172.8 | 0.331 | 3,070 | 4,559 | 5,894 |
| random file | 3 | 44,510 | 29.6 G | 172.4 | 0.327 | 3,096 | 4,705 | 6,054 |
| **HSP-smoothed, 1 hop** | 10 | 33,286 | **23.2 G** | **145.2** | 0.326 | 3,065 | 4,591 | 6,002 |
| **HSP-smoothed, 1 hop** | 3 | 36,638 | **22.0 G** | **136.3** | 0.326 | 3,091 | 4,615 | 6,183 |
| *exact ceiling* | — | — | 500 G | — | 0.336 | 3,065 | 4,601 | 6,025 |

Against its own control (same 700 seed points) the HSP-smoothed start
cuts the candidate pairs by 18% and the candidate stage by 16% at ten
iterations, and by 26% / 21% at three; against the paper's build, 12% /
10% and 17% / 15%. Quality is unchanged within the seed-to-seed spread:
every arm sits in the ±3% band around the exact ceiling (the two random
seeds differ by 2% between themselves). Three Lloyd iterations lose
nothing. The mechanism is the one the laptop replica showed: the
smoothed start converges to a more balanced partition (largest leaf 33k
against 44k from the same points) — the hub cells that dominate Σ leaf²
are the ones the smoothing shrinks.

**Kept.** A 15-20% cut in the dominant stage for a 700 × 700 HSP and a
leader average, at no quality cost, is a real if modest engineering
result, and the object behind it — an HSP-smoothed facility set as a
k-means warm start — has independent interest in facility location, as
the author noted. Untested: other corpora, larger L (where the HSP is
L² but still cheap to 10⁴), k-means++ + smoothing, and two-hop at larger L.

## Iterated smoothing as an algorithm (author, same day; `bench/hsp_iter_diag.py`, laptop replica)

Repeat "HSP on the leaders → replace each by the mean of itself and its
HSP neighbours" r times, with no data pass, then evaluate directly and
after three Lloyd iterations. L 700, m 5, symmetric leaves.

| smoothing rounds | no Lloyd: recall @ pool, pairs, max leaf | + 3 Lloyd | leader spread |
|---:|---|---|---:|
| 0 | 0.900 @ 120k, 61.3 G, 88k | 0.891 @ 55k, 28.0 G, 29k | 1.38 |
| 1 | 0.816 @ 43k, 21.6 G, 25k | 0.867 @ 41k, 20.7 G, 19k | 0.71 |
| 2 | 0.749 @ 46k, 23.0 G, 18k | 0.859 @ 40k, 19.9 G, 19k | 0.54 |
| 3 | 0.696 @ 53k, 26.6 G, 24k | 0.859 @ 39k, 19.7 G, 16k | 0.48 |
| 5 | 0.610 @ 65k, 32.7 G, 33k | 0.852 @ 40k, 20.2 G, 17k | 0.43 |

**As a standalone algorithm it is a contraction.** With no data anchor the
leader set shrinks toward its centre (mean distance to the centroid 1.38
→ 0.42 in six rounds), recall falls a point per round and the pair count
rises again after round two as the cells lose balance. The data pass is
what keeps the facilities where the mass is; the smoothing only decides
where they start. **With Lloyd after it, one or two rounds are the
optimum:** 20.7 G at 0.867 (one round) or 19.7-19.9 G at 0.859 (two or
three); beyond that nothing changes. So the construction is "smooth once
or twice, then a few Lloyd iterations" — a warm start after all, not a
replacement for it.

## HSP-enlarged Lloyd (author's clarified iteration, 2026-09-29): a data-anchored fixed point

Each round: HSP on the leaders → assign the sample → enlarged cell = own
cell + the cells of the leader's HSP neighbours → new center = mean of the
enlarged cell's points. `bench/hsp_lloyd_diag.py`, `bench/hsp_hybrid_diag.py`
(replica); `bench/d0_enl.sh` (fg, `--dense-leaders-file` + `--dense-kmeans k`).

Replica (L 700, m 5): plain Lloyd converges to 0.894 @ 26.5 G (max leaf
31k); the enlarged iteration converges from round 2 to **0.784 @ 19.4 G
(max leaf 22k)** — no contraction (the mean is anchored to data), 26%
fewer pairs, 11 points less pool recall: a wide kernel puts the centers
on the regional mass, balanced but less tight. Hybrid (enlarged rounds,
then plain Lloyd): 2 Lloyd rounds → 0.86 @ 20.8-21.1 G for any number of
enlarged rounds; 5 → 0.875 @ 22 G.

End to end on d0 (GIST, ParlayANN):

| leaders | fg Lloyd it. | max leaf | pairs | candidates s | compl. | d@0.90 | d@0.95 | d@0.97 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| paper (fg k-means, 10 it.) | 10 | 28,204 | 26.4 G | 160.6 | 0.328 | 2,898 | 4,485 | 6,055 |
| enlarged fixed point (5 rounds) | 0 | 23,565 | **19.6 G** | **129.9** | 0.320 | 3,130 | 4,853 | 6,453 |
| enlarged 5 rounds | 2 | 23,229 | 20.8 G | 136.6 | 0.325 | 3,115 | 4,693 | 6,196 |
| enlarged 2 rounds | 2 | 25,986 | 21.0 G | 134.3 | 0.323 | 3,083 | 4,632 | 5,995 |
| *warm start: HSP-smoothed once* | 3 | 36,638 | 22.0 G | 136.3 | 0.326 | 3,091 | 4,615 | 6,183 |
| *exact ceiling* | — | — | 500 G | — | 0.336 | 3,065 | 4,601 | 6,025 |

The fixed point alone (no Lloyd) is 26% cheaper and 5% above the ceiling
at 0.95 (8% above the paper's build): pool recall 0.78 is where the graph
starts to notice. Two Lloyd steps after two or five enlarged rounds bring
it back inside the ceiling band at ~20% fewer pairs — the same point the
one-round warm start reaches (4,615 @ 22.0 G vs 4,632 @ 21.0 G). So the
enlarged iteration is a second route to the balanced basin, not a better
one; both need Lloyd's local step at the end, and both save a fifth of
the dominant stage on GIST at unchanged quality.

## The other corpora (2026-09-29/30, `bench/d0_warm_all.sh`, `results/warm/`): the GIST gain does not transfer

Per corpus at the paper's configuration: gate (fg's k-means, 10 it.),
HSP-smoothed once + 3 Lloyd, two enlarged-Lloyd rounds + 2 Lloyd. Leaders
from `bench/hsp_enl_leaders.py` (200k sample, centers normalised on the
cosine corpora). ParlayANN grading with each corpus's recipe.

| corpus | arm | largest leaf | candidate pairs | candidates s | d@r (paper's targets) |
|---|---|---:|---:|---:|---|
| GIST L700 | paper / smoothed+3 / enlarged×2+2 | 28k / 37k / 26k | 26.4 / 22.0 / 21.0 G | 161 / 136 / 134 | 4,485 / 4,615 / 4,632 (@0.95) |
| SIFT L700 | paper / smoothed / enlarged | 19k / 26k / 21k | 20.2 / 21.7 / 19.8 G | 38 / 43 / 41 | 1,682 / 1,718 / 1,706 (@0.98); 2,155 / 2,159 / 2,153 (@0.99) |
| Deep-10M L2400 | paper / smoothed / enlarged | 72k / 102k / 100k | 614 / 658 / 640 G | 599 / 641 / 625 | 2,180 / 2,197 / 2,176 (@0.95); 4,689 / 4,709 / 4,721 (@0.99) |
| Wikipedia L1600 | paper / smoothed / enlarged | 58k / 66k / 94k | 381 / 384 / 416 G | 1,942 / 1,937 / 2,051 | 3,868 / 3,864 / 3,933 (@0.95); 6,705 / 6,688 / 6,747 (@0.97) |
| GloVe L240 | paper / smoothed / enlarged | 61k / 59287 / 53k | 88.6 / 0.0 / 79.8 G | 74 / 72.09 / 68 | 9,069 / 9,519 / 9,475 (@0.95); 13,322 / 13,634 / 13,505 (@0.97) |

**Verdict: corpus-specific, not a construction improvement.** The pair
saving appears only on GIST (−17/−20%). On SIFT the leaves are already
balanced and nothing changes; on Deep-10M the smoothing *grows* the
largest leaf (72k → 100k) and costs 4-7% more pairs; on Wikipedia the
enlarged start grows it to 94k (+9% pairs, +1.7% at 0.95); on GloVe the
enlarged start saves 10% of the pairs but the graph pays 4.5% at 0.95 —
GloVe is the corpus where the pool's measure still buys quality (ceiling
4.6% above the paper's pool), so a smaller pool is a worse graph there.
Nothing in the construction controls whether the smoothing shrinks or
grows the hub cells. The warm start stays as a documented negative with
one positive corpus; the facility-location object (HSP-smoothed start,
enlarged-cell Lloyd) may still have interest on its own terms, outside
this construction.
