# A 2-bit SOLO stream: screen and router (laptop, 2026-09-21)

Proposal (EC): store the scanned database 2-bit quantised, screen against it,
re-rank the survivors in SQ8, refine exactly. A page then holds ~4x more
vectors — "maybe less, because we have the object IDs".

Protocol mirrors SOLO: uniform alpha = 2% sample S; every object joins the
lists of its b = 8 nearest sample points (exact, build-time); a query scans
the lists of its ks nearest sample points. 200 queries, k = 10, gold from the
answer key. `bench/solo_screen.py`; logs `wiki.log`, `glove.log`.
Quantisers: SQ8/SQ4 per-dimension uniform, dequantised for scoring (float
query); EVP {d/2, d} ternary, both as **ft** (float query x 2-bit data) and
**tt** (both sides 2-bit).

## 1. The page arithmetic (exact, not measured)

Deep-96, 4 KB page: float+id 388 B = 10/page; SQ8+id 100 B = 40; SQ4+id 52 B
= 78; **EVP 2-bit+id 28 B = 146 (3.65x SQ8); ids in a parallel array, 24 B =
170 (4.27x)**. At d = 768: 772 -> 196 B, 3.94x with ids inline.

**The screen never needs an id — only the survivors do.** Splitting the list
into a code block and a parallel id array recovers the full 4.27x and is a
win independent of quantisation.

## 2. ROUTER: SQ8 is free; 2-bit is a dimension-split decision

Coverage of the true 10-NN by the ks routed lists (coverage **is** recall
under SOLO's Prop. 1, so this degrades the certificate, not the speed).

| ks | wiki-1024 float | sq8 | evp_ft | evp_tt | | GloVe-100 float | sq8 | evp_ft | evp_tt |
|---:|---:|---:|---:|---:|---|---:|---:|---:|---:|
| 8 | 0.8735 | **0.8735** | 0.8665 | 0.8555 | | 0.7065 | **0.7085** | 0.6085 | 0.5335 |
| 16 | 0.9440 | **0.9455** | 0.9375 | 0.9285 | | 0.7965 | **0.7965** | 0.7130 | 0.6335 |
| 32 | 0.9795 | **0.9795** | 0.9750 | 0.9715 | | 0.8615 | **0.8620** | 0.7970 | 0.7255 |
| 64 | 0.9950 | **0.9950** | 0.9920 | 0.9905 | | 0.9180 | **0.9180** | 0.8635 | 0.8145 |
| 128 | — | — | — | — | | 0.9615 | **0.9625** | 0.9235 | 0.8800 |

**Finding R1. An SQ8 router costs exactly nothing, on both corpora and at
every ks** — identical to float to three or four decimals, occasionally a
hair better. The paper's law already permits `c_r = d + g`; this measures
that the permission is free.

**Finding R2. A 2-bit router is fine at d = 1024 and bad at d = 100.**
wiki: -0.45 coverage points at ks = 32, recovered by widening ks 32 -> ~38
(+20% scanned). GloVe: **-6.5 points** at ks = 32, needing ks 32 -> 64
(+100% scanned). EVP keeps d/2 coordinates, so 512 survive at d = 1024 and
only 50 at d = 100; and GloVe's higher intrinsic dimension needs finer
discrimination. Use 2-bit routers at embedding dimensions only.

**Finding R3. Both-sides bitwise (tt) is never worth it.** The query is one
vector; keeping it float is free and worth 1-7 coverage points.

### Capacity, from the paper's own `c_r = 4d + g`, g = 64 B, alpha = 2%

| router codes | d=96: c_r | B/obj | n* at 1 GB | d=1024: c_r | B/obj | n* at 1 GB |
|---|---:|---:|---:|---:|---:|---:|
| float32 | 448 | 8.96 | 1.2e8 | 4,160 | 83.2 | 1.3e7 |
| **SQ8 (free)** | 160 | 3.20 | **3.4e8** | 1,088 | 21.8 | **4.9e7** |
| SQ4 | 112 | 2.24 | 4.8e8 | 576 | 11.5 | 9.3e7 |
| EVP 2-bit | 88 | 1.76 | 6.1e8 | 320 | 6.4 | 1.7e8 |

At d = 96 the 64-byte overhead `g` is 40% of an SQ8 `c_r` and 73% of a 2-bit
one: **below 8 bits, `g` is the binding constraint, not the vectors.**
At d = 1024 the codes dominate and float -> 2-bit is 13x capacity.

## 3. SCREEN: 2-bit needs 10-100x the pass set, and still wins on traffic

Pass set K at which an exact re-rank recovers the pool's ceiling (ks = 32):

| corpus | pool | ceiling | SQ8 | SQ4 | EVP ft | EVP tt |
|---|---:|---:|---:|---:|---:|---:|
| wiki-1024 | 10,436 (5.2%) | 0.9795 | 20 | 20 | 200 | 500 |
| GloVe-100 | 22,771 (1.9%) | 0.8615 | 20 | 200 | 2,000 | >5,000 |

**Finding S1. The inflation is 10x at d = 1024 and 100x at d = 100** — the
"lossless inside a pool" result of the dense campaign (`evp-FINDINGS` #5) was
measured at K = 500 against a 10^5 pool, i.e. already at the inflated K; it
does not mean 2-bit ranks as well as SQ8.

**Finding S2. It wins anyway, because the pass set is two orders of
magnitude smaller than the pool.** Bytes moved per query at ks = 32:

| design | wiki-1024 | GloVe-100 |
|---|---:|---:|
| SQ8 screen -> exact | 10.8 MB | 2,285 KB |
| 2-bit -> exact | 3.49 MB (3.1x) | 777 KB (2.9x) |
| **2-bit -> SQ8 -> exact** | **2.96 MB (3.6x)** | **777 KB (2.9x)** |
| ... charging gathers at SOLO's measured 3.5x | 2.5x | 1.8x (3.0x at 99.4% of ceiling) |

**Finding S3. The three-stage cascade earns its keep**, as proposed: the SQ8
middle stage converts a wide *exact* gather into a wide SQ8 gather plus a
narrow exact one. On GloVe, accepting 99.4% of the ceiling (K = 500 instead
of 2,000) is worth more than the last 0.6%: 3.0x against 1.8x.

## 4. What to do

1. **Ship the SQ8 router now.** Free, measured on two corpora, 2.8x (d=96) to
   3.8x (d=1024) on the capacity ceiling — SOLO's headline claim — with the
   certificate untouched.
2. **Split ids out of the code stream.** Pure win, 3.65x -> 4.27x at d = 96.
3. **2-bit screen + SQ8 re-rank + exact refine**: 2.9-3.6x less traffic at
   both dimensions.
4. **2-bit router only at embedding dimensions**, where it is another 3.4x
   for +20% scan.
5. **Attack `g`** before going below 8 bits at low d.

## 5. Caveats

* 200 queries, one alpha (2%), one b (8); ks swept. Not paired, single runs.
* Traffic is counted analytically from the measured pool and pass-set sizes;
  no kernel was written, so the gather penalty is imported from SOLO's own
  SQ8-gather vs SQ4-stream measurement (268 vs 936 qps) rather than measured
  here.
* Build-side assignment used exact float distances throughout, which is
  correct (assignment is offline with full vectors available); only the
  resident router was quantised.
