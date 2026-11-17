# Check on `DimNote.md` (the wall's dimension dependence) — 2026-09-19

Reply to `../DimNote.md`. The note's direction is confirmed; its magnitude
needs a correction, and its evidence needs a clean machine.

## 1. Kernel side: the shape reproduces

`X[:200k] @ Y[:b].T`, f32 OpenBLAS, n·b ≈ 2·10⁹ pairs, best of 3, d0.

| d | G pairs/s | TFLOP/s | cycles/pair (32 c @ 2 GHz) | % of 2.05 TFLOP/s peak |
|---:|---:|---:|---:|---:|
| 96 | 1.278 | 0.245 | 50.1 | 12% |
| 100 | 1.101 | 0.220 | 58.1 | 11% |
| 128 | 1.132 | 0.290 | 56.5 | 14% |
| 256 | 0.723 | 0.370 | 88.5 | 18% |
| 384 | 0.606 | 0.465 | 105.6 | 23% |
| 768 | 0.354 | 0.544 | 180.6 | 27% |
| 960 | 0.294 | 0.565 | 217.4 | 28% |

10× the dimensions costs 4.3× the time per pair (the note: 7.7× for 3.7×).
**Dense cost is sublinear in d: ≈ d^0.64, not c·d.**

## 2. Adaptive side: flat, but only over d = 96–128

Search-side rate needs no new counter — ParlayANN and `fg` both print QPS and
distances/query, so the rate is their product. Extracted at recall ≈ 0.95
over every run in `results/` (all threads):

| dataset | d | fg beam | ParlayANN beam |
|---|---:|---:|---:|
| Deep-96 | 96 | 0.084 G/s (760 cyc/pair) | 0.128–0.174 G/s (368–500) |
| GloVe | 100 | 0.079–0.105 G/s (607–807) | 0.140–0.162 G/s (396–456) |
| SIFT | 128 | — | 0.128–0.139 G/s (459–500) |

That span is far too narrow to fit a law. **The missing measurement is a
high-d adaptive point**, which is why GIST-960 is queued (§5).

## 3. The model, corrected

The note's W(d) = (a + b·d)/(c·d) → b/c assumes a dense cost linear in d and
an adaptive memory term that shrinks relatively. Neither holds:

* dense(d) ∝ d^0.64 (§1), so the bookkeeping term decays as **d^-0.64**, not 1/d;
* the adaptive side streams 4d bytes per dependent access, a term
  **proportional to d** whose ratio to dense(d) *rises* as d^0.36.

So W(d) = a/dense(d) + s·d/dense(d): a decaying term plus a slowly rising one.
With the campaign's clean d = 100 values (dense 14.4 cyc/pair at 4.45 G/s,
Vamana build 296 cyc/pair) and s ≈ 0.1 cyc/dim (4d/75 B-per-cycle plus
unblocked SIMD):

| d | predicted adaptive | predicted dense | **W(d)** |
|---:|---:|---:|---:|
| 100 | 296 | 14.4 | **20.6** (measured) |
| 384 | 324 | 34.8 | 9.3 |
| 768 | 363 | 54.3 | 6.7 |
| 960 | 382 | 62.6 | 6.1 |

**The wall falls ≈3×, from ~21 to ~6–7 at embedding dimensions — it does not
vanish.** Note the consequence for the note's own refutation criterion
(W(768) ≥ 0.5·W(100) refutes): the corrected model predicts the ratio 0.34,
so the test is tight and a noisy measurement lands on the wrong side of it.

## 4. Contention — the finding to act on first

When the §1 sweep was taken, d0 was at **load 78**, with the note's own
queued job (`misi2/msmarco_beam_ip_d0.py`) holding ~54 cores. The same
kernel at d = 100 has now measured 1.10 (loaded), 3.20 (the note), and 4.45
(`wall-FINDINGS.md`, idle) G pairs/s — a 4× spread. Contention penalises the
low-d rows hardest (they are bandwidth-bound; the high-d rows are
compute-bound), which **biases the ratio in exactly the direction the note
concludes**. The note records that its numbers were gathered while measuring
another system, so it may carry the same bias. My run was stopped rather than
corrupt both; §1 above is therefore indicative only.

## 5. Queued on d0 behind a load guard (starts when load < 8)

* the §1 kernel sweep, re-measured idle (`results/deep/wd_probe_idle.log`);
* **GIST-960** (1M, d = 960, already on d0): Vamana R64/L128 α1.2 and
  `fg --dense L=700`, both build and search — the high-d point for both sides.

## 6. Smaller points

* The requested `n_dist_search` counter is *not* needed for the W(d) curve
  (QPS × cmps suffices, §2). Its value is the MSMARCO case, where the beam is
  a **build** step whose work is never printed. Still worth adding.
* The d = 768 task table (note §4) has a third confound beyond pool and
  kernel: at a 25% pool the batched build does ≈50k pairs/object against the
  beam's ef × degree, so the *work* ratio is only a few fold. With a blocked
  kernel the two programs sit within a small factor — which weakens the
  wall's **consequence** at high d without touching the wall itself.
* **Pending decision (not applied):** paper 1's abstract states the wall as
  "20–27×" unqualified, and every number behind it is d = 100 or 128. That
  should become a dimension-qualified claim.

---

# Measured on an idle d0 — the claim is refuted (2026-09-19, later)

The load guard released, the queued runs completed on an otherwise idle
machine (load 1.2), and GIST-960 supplies the high-d adaptive point.
Logs: `results/deep/{wd_probe_idle,vamana_gist,fg_dense_gist}.log`.

## 7. First, a correction to §4: the note's kernel table was fine

Idle, the kernel measures 2.805 G pairs/s at d = 100 and 0.781 at d = 768,
against the note's 3.20 and 0.87. **My loaded run (1.10) was the outlier, not
the note's numbers.** The contention caveat stands as a method note; it does
not impeach §2 of `DimNote.md`.

| d | G pairs/s (idle) | cycles/pair | % of 2.05 TFLOP/s peak |
|---:|---:|---:|---:|
| 96 | 2.606 | 24.6 | 24% |
| 100 | 2.805 | 22.8 | 27% |
| 128 | 2.499 | 25.6 | 31% |
| 256 | 1.664 | 38.5 | 42% |
| 384 | 1.298 | 49.3 | 49% |
| 768 | 0.781 | 81.9 | 59% |
| 960 | 0.606 | 105.6 | 57% |

**dense(d) ∝ d^0.63** — the sublinearity of §1/§3 is confirmed idle.

## 8. The adaptive side is LINEAR in d — so W(d) *rises*

Search-side rate = QPS × distances/query at recall ≈ 0.95, all 64 threads.

| system | d | cycles/pair | dense | **W** |
|---|---:|---:|---:|---:|
| Vamana R64 (SIFT) | 128 | 491 | 25.6 | 19.2 |
| Vamana R100 (GloVe) | 100 | 396 | 22.8 | 17.3 |
| Vamana R64 (Deep) | 96 | 368 | 24.6 | 15.0 |
| **Vamana R64 (GIST)** | **960** | **3,960** | 105.6 | **37.5** |
| fg beam (GloVe) | 100 | 782 | 22.8 | 34.3 |
| **fg beam (GIST)** | **960** | **8,765** | 105.6 | **83.0** |

Per-pair scaling exponents: **adaptive d^1.04** (Vamana search, matched
degree R64, d = 128 → 960) and **d^1.07** (fg beam, d = 100 → 960), against
**dense d^0.63**. Hence

    W(d) ∝ d^{1.04-0.63} = d^{0.4}   — the wall GROWS with dimension.

The test, against the amended criterion (*refute if W(960)/W(100) ≥ 0.7*):

| pairing | W(960)/W(low) |
|---|---:|
| Vamana search, d = 128 → 960 (matched degree) | **1.96** |
| Vamana search, d = 100 → 960 | 2.16 |
| fg beam, d = 100 → 960 | 2.42 |
| Vamana build, d = 100 → 960 | 1.51 |

Every pairing is 2–3.5× above the refutation threshold. **The
dimension-dependence claim is refuted, and the sign is the opposite of the
one conjectured.**

## 9. Why — §2 was right, §3's inference was not

`DimNote.md` §3 models both sides as paying the same arithmetic cost per
dimension (`b·d` and `c·d`), so that a d-independent `a` must wash out. The
measurement says `b > c` and, worse, **the gap widens with d**: the dense
kernel's *efficiency* climbs from 27% of peak at d = 100 to 57% at d = 960,
while the adaptive side, which cannot block, holds its efficiency flat.
Concretely, per extra dimension the adaptive side pays ≈4.1 cycles (Vamana
search, 491 → 3,960 over 832 dimensions) while the dense side pays ≈0.10.
The bookkeeping term does decay as modelled; it is simply not what dominates
at embedding dimensions. At d = 100 both sides are partly overhead-bound and
therefore *closer*; high d is where the dense kernel gets to be what it is.

## 10. But the dense *program* still wins at d = 960 — for another reason

GIST-960 (1M × 960, L2), same machine, same run:

| arm | build | G dist | d@0.95 | compl. |
|---|---:|---:|---:|---:|
| `fg --dense` L700/m5/C200 + spine | **430.5 s** (leaders 12, candidates 336, prune 51, spine 32) | 30.9 | **5,209** | 0.328 |
| Vamana R64/L128 α1.2 2-pass | 632.5 s | 19.6 | 5,281 | — |

Parity quality at **0.68× the build time** — the same verdict as GloVe
(0.65×), reached despite the wall being twice as high here. The dense
program's advantage was never only the kernel: its work is bounded by the
pool (30.9 G distances, set by L and C), whereas the search builder's work
per point grows with the data. Two independent levers, and only one of them
is dimension-sensitive.

## 11. Fixable: fg's own tile degrades at high d

fg's dense candidate stage reaches 1.21 G pairs/s at d = 100 (W = 2.3 vs
OpenBLAS) but only 0.0786 at d = 960 (W = 7.7). The 4×4 register tile has no
blocking over the dimension: eight rows of 960 floats is 30 KB and overflows
L1. Splitting d into ~1 KB chunks with accumulator carry would recover most
of it, and matters for any embedding-dimension corpus.

## 12. Consequences

* `DimNote.md` §5's first two bullets invert: the wall is **worst** at
  embedding dimensions, so a d ≈ 100 measurement *understates* it for
  384–1024-d corpora. Paper 1's "20–27×" is conservative there, not
  optimistic — but it still must be labelled as a d ≈ 100 number, now with
  the measured exponent attached.
* What survives from the note intact: §4's task-level result and §6's
  pool-versus-rate trade. Those turn on candidate quality and on the pool
  needed per recall, which are data properties — and they, not the wall, are
  what decide whether a batched builder wins at high d.
