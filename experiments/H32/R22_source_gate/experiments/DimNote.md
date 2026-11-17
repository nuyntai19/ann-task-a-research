# The wall's dimension dependence — a note from outside the campaign

*2026-09-19. Evidence gathered on d0 while measuring a different system
(SOLO/MISIFU's signature build on MS MARCO Web Search, 768-d text embeddings,
metric ip); numbers reproducible from `IA/misi2/msmarco_*_d0.py` and
`IA/docs/LOG.md` 2026-09-19(b). Written for this campaign because it bears on
`wall-FINDINGS.md` §2–3 and on the scope sentence of the paper's abstract.*

## 0. REFUTED — read `results/dimnote-CHECK.md` §7–12 first

**The central claim of this note is wrong, and the sign is the opposite of
what I conjectured.** Measured idle on d0 with GIST-960 supplying the missing
high-d adaptive point: the adaptive side scales **d^1.04** (Vamana search,
matched degree) to **d^1.07** (fg beam) while the dense kernel scales
**d^0.63**, so W(d) ∝ d^0.4 — **the wall GROWS with dimension**, from ~17–19
at d ≈ 100 to ~37 (Vamana) and ~83 (fg) at d = 960. Every pairing sits 2–3.5×
above this note's own refutation threshold.

The error is in §3: I modelled both sides as paying the same arithmetic cost
per dimension (b·d and c·d), so that a constant bookkeeping term `a` had to
wash out as d grew. Measurement says b ≫ c and the gap *widens* — the dense
kernel's efficiency climbs from 27% of peak at d = 100 to 57% at d = 960,
while the adaptive side, which cannot block, holds its efficiency flat
(≈4.1 cycles per extra dimension against the dense side's 0.10). The
bookkeeping term does decay as I modelled; it is simply not what dominates at
embedding dimensions. Also, my contention worry was unfounded in the end:
idle, the kernel measures 2.805 / 0.781 G pairs/s at d = 100 / 768 against
this note's 3.20 / 0.87 — the campaign's *loaded* 1.10 was the outlier, not
§2 of this note.

Consequence, inverted from §5: a d ≈ 100 measurement **understates** the wall
for 384–1024-d corpora, so paper 1's "20–27×" is conservative there — but it
still needs the dimension label, now with the measured exponent attached.

What survives intact: **§4's task-level result** (at d = 768 the batched
signature build loses to the beam) and **§6's pool-versus-rate trade**. Both
turn on candidate quality and the pool needed per recall — data properties,
not kernel properties — and they, not the wall, are what decide whether a
batched builder wins. Note the companion fact from the same run: at d = 960
the dense *program* still builds a graph at parity quality in 0.68× Vamana's
time, because its work is bounded by the pool while a search builder's work
per point grows with n. Two independent levers; only one is dimension-
sensitive, and it is not the one this note was about.

### The superseded amendment (kept for the record)

The campaign's first reply corrected this note on two points, both since
overtaken by the idle measurement above.

1. **The dense kernel is sublinear in d (≈ d^0.64), not linear**, because at
   d ≈ 100 the GEMM is far from compute-bound (11–14% of peak) and only
   approaches it at embedding dimensions (27–28% at 768–960). So the
   bookkeeping term decays as d^-0.64, and the adaptive side's streaming term
   (4d bytes per dependent access) *rises* relative to dense as d^0.36. The
   corrected model, W(d) = a/dense(d) + s·d/dense(d), predicts
   **W: ~21 at d=100 → ~9 at 384 → ~6–7 at 768** — the wall falls by ≈3×,
   it does **not** collapse. §3's "well under 2× at d = 768" is wrong; the
   in-cache bookkeeping term alone decays that way, but it is not the whole
   wall.
2. **My kernel rates were taken on a contended machine** (d0 was running my
   own MSMARCO jobs; the same d = 100 kernel has measured 1.10, 3.20 and 4.45
   G pairs/s under different loads — a 4× spread). Contention hits the low-d
   rows hardest, which biases the ratio in the direction this note argues, so
   §2's table is *indicative only* and is superseded by the idle
   re-measurement queued behind the campaign's load guard, together with the
   GIST-960 (d = 960) point that gives the adaptive side its missing high-d
   value.
3. Correspondingly, **§5's refutation criterion was badly calibrated**: the
   corrected model predicts W(768)/W(100) ≈ 0.34, so "refute if ≥ 0.5" sits
   close enough to the prediction that measurement noise decides it. Restate
   it as: *refute the dimension-dependence claim if the idle-measured
   W(960)/W(100) ≥ 0.7*, and treat anything in 0.4–0.7 as "falls, weaker than
   modelled".
4. One method note taken from the reply: the adaptive rate needs **no** new
   counter for the W(d) curve — QPS × distances-per-query from the existing
   ladders gives it. The `n_dist_search` counter is still worth having, but
   for a different reason: in MISIFU the beam is a *build* step whose work is
   never printed.

What survives unchanged: the direction (the wall is a d ≈ 100 number and
falls at embedding dimensions), the task-level result of §4, and the
pool-versus-rate trade of §6 — which is what actually decides whether a
batched builder wins, and which the reply's §6 sharpens: at high d the two
programs' *work* ratio is only a few fold, so the wall's **consequence**
weakens even where the wall itself stands.

## 1. Why this is here

The wall is stated as a machine constant: search-based builders run **20–27×
below a dense kernel** on d0, "five to six times of it with the data resident
in cache". Every number behind it was measured at **d = 100 (GloVe) and
d = 128 (SIFT)**. The `--dense` program that grew out of it — leaders, exact
GEMM in leaves, prune — then won on GloVe (0.65× Vamana at parity) and tied
on SIFT, and the paper explains the difference by intrinsic dimension.

Embedding corpora are not 100-dimensional. MSMARCO, the VIBE twins, every
BERT/E5/BGE-class corpus is 384–1024. If the wall's *height* depends on d,
the dense program's reach depends on d too, and the abstract's scope sentence
("absent only for decomposable distances evaluated on pair sets fixed in
advance") needs a second clause about how much that absence is worth.

It does depend on d, and in the direction that shrinks the wall.

## 2. The kernel side gets *better* with d (measured, d0, 64 threads)

`X[:200k] @ Y[:m].T`, f32 OpenBLAS, 2·10⁹ pairs, best of 3:

| d | G pairs/s | TFLOP/s | core-cycles/pair (32 c @ 2.0 GHz) |
|---:|---:|---:|---:|
| 100 | 3.20 | 0.64 | 20.0 |
| 768 | 0.87 | **1.34** | 73.4 |

7.7× the dimensions costs only 3.7× the time per pair: at d = 100 the GEMM
runs at 32% of d0's ~2 TFLOP/s FMA peak, at d = 768 at 67%. (The campaign's
own 4.45 G pairs/s at d = 100 is the same kernel at a friendlier shape; the
*ratio* between the two rows is what matters here.)

Fused kernels behave the same way. FAISS `knn` (blocked GEMM + k-select),
real data, 20k × 200k at d = 768: **0.392 G pairs/s** = 163 cycles/pair, 2.2×
the bare GEMM — the same k-select tax the campaign's own tile pays (1.65 of
4.45 G/s at d = 100, 2.7×).

## 3. The adaptive side pays a d-independent surcharge

Model the two sides per pair, in cycles:

    dense:     c·d
    adaptive:  a + b·d        a = beam bookkeeping (heap, visited stamp,
                              candidate sort, occlusion test, dependent
                              random access); b·d = the distance itself

so the wall factor is

    W(d) = (a + b·d) / (c·d)  →  b/c   as d → ∞,

i.e. **W falls hyperbolically in d toward the ratio of the two arithmetic
efficiencies**, which is small (both sides are SIMD; the dense side wins only
through register/cache blocking). The campaign already measured the pieces at
d = 100: Vamana 0.216 G pairs/s = 296 cycles/pair against the GEMM's 20, and
`wall-FINDINGS.md` §3 attributes 5–6× of the 20–27× to `a` (it survives with
the data in cache) and the rest to memory. With `a` constant and `c·d` growing
7.7× from d = 100 to d = 768, the bookkeeping that costs 5–6× at d = 100 costs
well under 2× at d = 768, and the memory term shrinks as well (the same 3 KB
row now serves 768 useful flops instead of 100).

**This is a prediction, not yet a measurement**, because GRAFT exposes
`n_dist_build` but has **no search-side distance counter**: the beam's build
on MSMARCO cannot be split into work × rate the way this campaign splits
Vamana's. A thread-local counter exposed as `n_dist_search` (and printed by
`fg` for the harvest) would close it in an afternoon and is worth having for
both papers.

## 4. The task-level evidence at d = 768

MISIFU's signature build is the cleanest possible case for the dense program:
each of n objects needs its top-64 inside a vocabulary S fixed before the
build starts (|S| = 200k here, n = 10M), no dependencies at all — a pair set
fixed in advance by construction. Measured on d0, 64 threads, signature recall
against exact ip:

| builder | pool scanned | recall@64 | obj/s | full 10M |
|---|---:|---:|---:|---:|
| FAISS IVF (nlist 256) nprobe 5 | 2.0% | 0.716 | 6,024 | 28 min |
| … nprobe 13 | 5.1% | 0.854 | 2,770 | 60 min |
| … nprobe 32 | 12.5% | 0.936 | 1,196 | 139 min |
| … nprobe 64 | 25% | 0.973 | 604 | 276 min |
| … nprobe 128 | 50% | 0.994 | 316 | 528 min |
| **GRAFT beam (ef 256)** | — | **0.976–0.99** | **2,950** | **56.5 min** |

At matched quality the batched build is **4.8× slower** than the adaptive one
— the opposite of the d = 100 result, and the reason this note exists.

Two effects are tangled in that table and they must be separated before the
number means anything:

1. **Pool.** The pool needed for a given recall is a property of the data.
   This campaign already saw it (`evp-FINDINGS` #22: on Deep-96 at 10⁷ a 1%
   pool reaches Vamana quality, while on GloVe the 3% → 9% step was worth
   7.6%). MSMARCO-768 is far past GloVe: 5% of the vocabulary gives 0.85
   where the beam gives 0.98, and matching the beam needs 25%. Adaptivity
   buys candidate quality, and the harder the data the more it buys.
2. **Kernel — and here the table is unfair to the dense side.** The IVF rows
   run at 0.024–0.030 G pairs/s (50k pairs/object at 604 obj/s), **13× below
   the same library's exhaustive kernel** (0.392) and 29× below the bare
   GEMM. FAISS scans an inverted list per query with a heap; this campaign's
   `fg --dense` instead blocks a set of points against a leaf and selects in
   C++, reaching 37% of SGEMM. A blocked implementation at 0.39 G pairs/s
   would do the 25%-pool build in ≈21 min against the beam's 56.5 — the
   conclusion would flip. It does not: see §6, where the blocked kernel was
   measured and the reason it cannot have both the pool and the rate is the
   most transferable thing in this note.

## 5. What this implies for the campaign

- **Qualify the wall's height by dimension.** "20–27× on d0" is a d ≈ 100
  number. The model of §3 says W(d) = b/c + a/(c·d); with two more rows of
  the cache sweep (d = 256 and d = 768, e.g. random-projected GloVe or an
  MSMARCO slice, with the search-side counter in place) the paper can print
  W(d) as a curve and fit a, b, c. That is a stronger result than a constant:
  it tells a reader with 768-d embeddings what the wall costs *them*.
- **The abstract's scope sentence gains a clause.** The wall is absent for
  decomposable distances on fixed pair sets — *and its height falls as 1/d*,
  so the dense program's advantage is largest exactly where the campaign
  measured it (d ≈ 100) and smallest on the high-dimensional embeddings that
  dominate current benchmarks.
- **The dense program's real constraint at high d is the pool, not the
  kernel.** On Deep-96 a 1% pool sufficed; on MSMARCO-768 the same recall
  needs 25%, and the batched cost is n·|S|·pool — quadratic in n at a fixed
  sampling rate, against the beam's n log n. Even where density wins at 10⁷
  it loses at 10⁸ unless the pool shrinks with n. The lever that survives is
  the one `evp-FINDINGS` already identified: a cheaper *stage-1* kernel
  (one-sided 2-bit/SQ4 data, 16×/8× less traffic, cache-resident vocabulary)
  and the GPU, not a bigger pool.
- **Refutation criterion for the claim in §3** — as restated in §0.3 after
  the reply: measure both rates on an idle machine at d ∈ {100, 256, 768,
  960} (QPS × cmps for the adaptive side; no new counter needed). Refute if
  **W(960) ≥ 0.7·W(100)**; 0.4–0.7 means the wall falls more weakly than
  modelled; ≤ 0.4 confirms the corrected model, which predicts ≈ 0.30 at
  d = 960. The streaming term (4d bytes per dependent access) is now *in* the
  model rather than its alternative.

## 6. Resolved: the pool and the rate cannot both be had

`misi2/msmarco_blocked_rate_d0.py` runs the campaign's own recipe — group the
objects by leaf, one blocked `faiss.knn` per (leaf, object block), select in
C++ — at several leaf granularities. The rate turns out to be governed by the
**block size**, not by the paradigm:

| scan | leaf size | G pairs/s | fraction of exhaustive |
|---|---:|---:|---:|
| FAISS IVF (list-at-a-time, heap per query) | 747 | 0.024–0.032 | 7–9% |
| blocked `faiss.knn`, L = 256 | 612 | 0.040–0.067 | 11–18% |
| blocked `faiss.knn`, L = 32 | 6.2k | 0.013–0.031 | 4–8% |
| blocked `faiss.knn`, L = 8 | 25k | **0.176–0.256** | 48–70% |
| exhaustive, whole vocabulary as one block | 200k | **0.366–0.392** | 1 |

(The non-monotonicity at L = 16/32 is FAISS's internal blocking thresholds,
not a law; the two ends of the table are the law.) This is PiPNN's own
handicap measured again — *"at only ~27% of the machine's GEMM rate: leaves
average 340 points, and the copy/norm/prune overhead around each small GEMM is
visible"* (`wall-FINDINGS.md` Finding 2) — and the same rate loss
`evp-FINDINGS` #23 recorded when Deep's 21k leaves ran at 1.01 G/s against
GloVe's 1.2.

**The tension, stated plainly: pool selectivity needs many cells, kernel
efficiency needs few, large blocks.** Shrinking the pool by 8× shrinks the
blocks by 8×, and on this machine that costs most of the kernel advantage it
was supposed to buy. The best batched point measured at d = 768 (L = 8,
nprobe 4: 53% pool, 0.234 G pairs/s) reaches signature recall 0.917 in a
projected 69 min; exhaustive reaches 1.0 in 91 min; the adaptive beam reaches
0.813 in **33 min** and 0.976 (against its own kernel) in 56 min. The batched
build is not refuted by a bad kernel — it is bounded by a real trade the
campaign has already met twice.

Corollary for the dense program at scale: since the pool cannot be shrunk
without losing the rate, the batched cost stays ≈ n·|S|·pool with pool large,
i.e. quadratic in n at a fixed sampling rate, against the beam's n log n. The
levers that remain are the ones `evp-FINDINGS` already named — a cheaper
stage-1 kernel (one-sided 2-bit/SQ4: the vocabulary is 77 MB at 4 bits and
stays resident, so the scan becomes compute-bound and the block can be the
*whole* vocabulary, keeping both the rate and the selectivity) and the GPU.
That combination, not a finer partition, is where a batched builder at d = 768
would have to win.

## 7. Provenance

- Kernel rates: d0, 64 threads, `numpy`/OpenBLAS and `faiss-cpu` 1.15.1
  (installed in the misifu venv today), measured against MSMARCO base vectors
  and the 200k sample described in `IA/docs/LOG.md` 2026-09-19.
- Signature-build frontier: `IA/misi2/msmarco_dense_sig2_d0.py`
  (`~/msmarco/dense2-10M.log` on d0), beam reference from
  `IA/misi2/msmarco_gate_d0.py` (3,389.5 s for 10M objects, single run —
  not the paired protocol; at a 4.8× ratio pairing is not what is at stake,
  but a build-time claim in a paper would need it).
- Blocked-kernel table: `IA/misi2/msmarco_blocked_rate_d0.py`
  (`~/msmarco/blocked-10M.log`), 20k probe objects against the same 200k
  vocabulary, `faiss-cpu` 1.15.1, 64 threads.
- The beam at the ip kernel: `IA/misi2/msmarco_beam_ip_d0.py` — 10M objects
  in 1,956 s (5,112 obj/s), 1.73× faster than the same beam routing the
  augmented point, with better shared-neighbour coverage at every parameter;
  see `IA/docs/LOG.md` 2026-09-19(c).
