# HSP spine and adaptive memberships (2026-09-30, d0, chain `bench/d0_adaptive_spine.sh`)

Code: graft-ann `fgraft` working tree (uncommitted at run time; md5 in the
chain log): `--dense-spine 3 --dense-spine-s s` (exact HSP over a seeded
random sample S, point 0 in S and the entry; S's HSP out-edges unioned after
the prune; |S|^2 distances, no search) and `--dense-m-file` (n uint8,
per-point membership count, clamped to [1, dense-m]). Gates: an all-5 file
reproduces the uniform m=5 build (same candidate distances, same hash); an
all-2 file reproduces `--dense-m 2`'s distance count; HSP spine hash
identical at 1 and 10 threads. GIST gate (spine 1): edges 18,335,567 = the
paper's build. Logs `results/adaptive/`; d@r by `bench/parse_parlay.py`,
ParlayANN searcher (start point 0).

## 1. HSP spine

Clustered smoke (laptop, n 200k, d 128, 800 clusters, L240/m5, fg searcher,
recall@10 at ef 64 / 128): none 0.002 / 0.002; SAT 0.987 / 0.994 (26 M
dist, max deg 96); HSP s=1,000 0.531 / 0.611; **HSP s=10,000 0.993 / 1.000**
(100 M dist, max deg 84). s=1,000 leaves ~29% of the 800 clusters without a
sample point (e^{-1.25}); s=10,000 hits all of them. The guarantee is
"every region holding a sample point is reachable monotonically from the
entry", so s must cover the clusters (coupon collector).

| corpus | spine | spine dist / s | HSP out-deg mean / max deg | d@0.95 | d@0.97 |
|---|---|---|---|---|---|
| GloVe A | SAT (paper) | 985.5 M / 10.4 s | — / 483 | 9,069 | 13,322 |
| | none | — | — / 64 | 9,130 | 13,031 |
| | HSP 1k | 1.0 M / 1.6 s | 20.0 / 117 | 9,138 | **12,986** |
| | HSP 10k | 100 M / 2.8 s | 43.1 / 233 | 9,337 | 13,216 |
| | HSP 30k | 900 M / 17.5 s | 60.3 / 334 | 9,420 | 13,707 |
| GIST L700 | SAT (paper) | 1,677.6 M / 30.9 s | — / 1,133 | 4,485 | 6,055 |
| | none | — | — / 64 | 4,259 | 5,766 |
| | HSP 1k | 1.0 M / 0.5 s | 10.8 / 116 | **4,249** | 5,832 |
| | HSP 10k | 100 M / 3.9 s | 21.7 / 240 | 4,331 | 5,896 |
| | HSP 30k | 900 M / 28.4 s | 29.7 / 433 | 4,501 | 6,138 |

Reading:
1. **The SAT spine costs 5% on GIST** (4,485 vs 4,259 without; its root is a
   degree-1,133 hub). The paper only priced it on GloVe (a wash there).
2. HSP at small s is free on real data (GIST 4,249, GloVe 9,138 / 12,986 =
   no-spine quality) at ~1/1000 of the SAT's distances, and it repairs the
   clustered case once s covers the clusters.
3. **HSP degree grows with s in high dimension** (GloVe mean out-degree
   20 -> 43 -> 60; GIST 11 -> 22 -> 30), and the sample points' extra
   out-edges are paid by every beam that expands them: s=10k costs +1.7%
   (GIST) / +2.2% (GloVe) at 0.95 over no spine, still 3.4% better than SAT
   on GIST. s=30k is worse than SAT. The low-dimensional "HSP degree is
   bounded" intuition does not hold at LID 30-50.
4. Design implication: s is a coverage parameter, not a quality one; take
   the smallest s that hits every cluster, or cap the HSP out-degree, or
   keep HSP edges only as a fallback layer. Untested: degree-capped HSP,
   s ~ sqrt(n) on Deep-10M.

## 2. Adaptive memberships

Prep (`bench/adaptive_m_prep.py`): exact 10-NN of every point (faiss flat,
~1 h per corpus), local clustering cc; proxies: cc on the approximate graph
of a pilot m=2 pass (recall@10 0.730 GloVe / 0.543 GIST; Spearman with
oracle cc 0.896 / 0.677) and the leader margin d1/d2. Two-level policies
(hardest fraction f gets m_hi, the rest m_lo; f in .05-.5, m_lo 1-4,
m_hi to 10) on 200k sampled true pairs, at the paper's L.

**The cover/pairs frontier barely moves, even with the oracle.** Best at
the uniform-m5 pair budget: GloVe 0.9295-0.9314 cover at 84.5-85.3 G vs
uniform 0.9299 at 87.6 G (-3 to -4% pairs); GIST 0.8964-0.8986 at
26.2-26.35 G vs 0.8988 at 26.40 G (nothing). Every selected policy is the
mild f 0.3-0.5, m 4/6-7 split; aggressive ones (f 0.05-0.1, m_hi 8-10)
lose because a hard point's extra leaves grow those leaves for every member
(pairs are quadratic in leaf size).

End to end (spine 1 = the paper's build otherwise; candidate distances from
fg):

| corpus | arm | mean m | cand. dist | d@0.95 | d@0.97 |
|---|---|---|---|---|---|
| GloVe | uniform m5 | 5.0 | 88.6 G | 9,069 | 13,322 |
| | oracle A | 4.9 | 85.4 G | 8,997 | 13,288 |
| | pilot A (= B) | 4.9 | 85.4 G | 9,031 | 13,293 |
| | margin A | 4.9 | 84.8 G | 9,046 | 13,403 |
| GIST | uniform m5 | 5.0 | 26.38 G | 4,485 | 6,055 |
| | oracle A | 5.0 | 26.27 G | 4,430 | 5,956 |
| | pilot A | 5.0 | 26.42 G | 4,407 | 5,962 |
| | oracle/pilot/margin B | 5.5 | 32.0-32.2 G | 4,434-4,535 | 5,990-6,048 |

**Negative.** Adaptive m buys at most ~4% of the candidate stage on GloVe,
nothing on GIST, and quality stays inside the ±3% ceiling band whatever the
score; +22% pairs (B) buy nothing either. Per-point clustering explains
*which* pairs a cover misses (transitivity-FINDINGS) but the misses are not
concentrated enough to be bought separately: the cost of the clique cover is
spread over the corpus. Combined with the ceiling result, uniform m is
near-optimal among membership policies at the paper's operating point.

## 3. Capped degree vs capped sample size (2026-09-30 evening; `bench/d0_spine_cap.sh`, logs `results/spinecap/`, smoke `results/adaptive/smoke_spine_cap.log`)

`--dense-spine-cap c`: each HSP row keeps its first c neighbours in sweep
(nearest-first) order. Gates: s=1k uncapped reproduces the section-1 edge
counts on GloVe (53,704,153) and GIST (16,778,882) and on the smoke.

**Guarantee (clustered smoke, 800 clusters, fg searcher, recall@10 ef64/128):**

| s \ cap | none | 32 | 16 | 8 |
|---|---|---|---|---|
| 1k | 0.531 / 0.611 | 0.531 / 0.611 | 0.467 / 0.561 | 0.237 / 0.310 |
| 3k | 0.865 / 0.949 | 0.865 / 0.949 | 0.756 / 0.903 | 0.441 / 0.599 |
| 10k | 0.993 / 1.000 | 0.992 / 1.000 | 0.968 / 0.996 | 0.657 / 0.828 |
| 30k | 1.000 / 1.000 | 1.000 / 1.000 | 0.998 / 1.000 | 0.808 / 0.918 |

(SAT: 0.987 / 0.994.) Cap 8 breaks the guarantee at every s: the dropped
far HSP neighbours are the eliminators the monotone argument needs. Cap 16
costs little once s >= 10k.

**Price (ParlayANN d@0.95 / d@0.97; no spine: GloVe 9,130 / 13,031, GIST 4,259 / 5,766; SAT: 9,069 / 13,322 and 4,485 / 6,055):**

| corpus | s | none | cap 32 | cap 16 | cap 8 |
|---|---|---|---|---|---|
| GloVe | 1k | 9,138 / 12,986 | 9,136 / 12,997 | 9,121 / 12,995 | 9,140 / 13,028 |
| | 3k | 9,165 / 12,998 | 9,159 / 13,016 | 9,184 / 13,042 | 9,139 / 13,052 |
| | 10k | 9,337 / 13,216 | 9,198 / 13,076 | 9,172 / 13,057 | 9,181 / 13,069 |
| | 30k | 9,420 / 13,707 | 9,295 / 13,210 | 8,961 / 13,117 | 9,163 / 13,063 |
| | 100k | 10,743 / 15,637 | | | |
| GIST | 1k | 4,249 / 5,832 | 4,249 / 5,832 | 4,246 / 5,827 | 4,244 / 5,829 |
| | 3k | 4,289 / 5,903 | 4,290 / 5,900 | 4,287 / 5,890 | 4,300 / 5,888 |
| | 10k | 4,331 / 5,896 | 4,296 / 5,854 | 4,268 / 5,817 | 4,268 / 5,822 |
| | 30k | 4,501 / 6,138 | 4,330 / 5,896 | 4,298 / 5,864 | 4,283 / 5,799 |
| | 100k | 5,349 / 7,232 | | | |

The search price of a spine is its degree, not its size: capped at 16 or 8,
every s up to 30k sits within ~1% of no spine (GloVe s=30k c16 is 1.9%
*below* it at 0.95, likely noise); uncapped it climbs to +6% at 30k and
+18-26% at 100k.

**Verdict: both caps, with different jobs.** s is set by coverage (the
smoke needs s >= ~10k for 800 clusters), the degree cap by price, and the
cap has a floor set by the guarantee (16 holds, 8 does not). The operating
point **s = 10k, cap 16**: smoke 0.968 / 0.996 (SAT 0.987 / 0.994), GloVe
9,172 / 13,057, GIST 4,268 / 5,817 (no-spine quality; GIST -4.8% / -3.9%
vs SAT), spine 100 M distances, 2.3 s / 4.2 s (SAT 985 M / 10.4 s and
1,678 M / 30.9 s). The s^2 term is the cost to watch: at s = 30k the spine
is as expensive as the SAT in distances.

**HSP degree vs sample size (uncapped, median out-degree):**

| s | 1k | 3k | 10k | 30k | 100k | fit p50 ~ s^a |
|---|---|---|---|---|---|---|
| smoke d128 (800 clusters) | 20 | 24 | 28 | 31 | — | a ~ 0.13 (saturating) |
| GloVe d100, LID 32 | 19 | 28 | 41 | 57 | 81 | a ~ 0.31 |
| GIST d960, LID 50 | 9 | 12 | 17 | 23 | 32 | a ~ 0.27 |

p99 / max at 100k: GloVe 182 / 381, GIST 163 / 1,048 (heavy tail; the
GIST max is a hub). On real data the degree is still growing as a power of
s at 10^5 with no sign of saturation; the clustered smoke saturates
(its local structure is 250-point Gaussian clusters). GIST's degree is
lower than GloVe's despite the higher MLE LID, so LID alone does not fix
the level.
