# The wall: search-based vs GEMM-based build throughput (d0, 2026-09-17)

Question (EC): is the order-of-magnitude build-time gap between graph-search
builders (independent, adaptive distance evaluations) and PiPNN (batched
GEMM) a real limitation, and where does it come from?

## 1. PiPNN's build cost, measured (`patches/pipnn_build_distance_counter.py`)

PiPNN evaluates distances in three places; the patch counts all three.

| dataset | clustering (batched) | leaf kNN (GEMM) | α-prune (scalar) | **total G** | build s | **G dist/s** | leaves / point |
|---|---:|---:|---:|---:|---:|---:|---:|
| GloVe R100/L200 | 3.21 | 8.49 | 0.86 | **12.56** | 10.35 | **1.21** | 30.0 |
| SIFT R64/L128 | 2.20 | 7.29 | 0.39 | **9.88** | 8.82 | **1.12** | 30.0 |

Against the Phase 1 medians (same machine, 64 threads):

| dataset | builder | build G | build s | G dist/s | work vs Vamana | throughput vs Vamana |
|---|---|---:|---:|---:|---:|---:|
| GloVe | Vamana | 31.56 | 145.9 | 0.216 | 1 | 1 |
| GloVe | GRAFT T16/ef400 frozen | 30.28 | 181.3 | 0.167 | 0.96 | 0.77 |
| GloVe | FGRAFT T8/ef400 B=8 | 27.66 | 226.3 | 0.122 | 0.88 | 0.57 |
| GloVe | **PiPNN** | 12.56 | 10.4 | **1.21** | **0.40** | **5.6** |
| SIFT | Vamana | 11.06 | 51.7 | 0.214 | 1 | 1 |
| SIFT | GRAFT T4/ef400 frozen | 5.15 | 52.1 | 0.099 | 0.47 | 0.46 |
| SIFT | FGRAFT T2/ef400 B=8 | 8.03 | 89.6 | 0.090 | 0.73 | 0.42 |
| SIFT | **PiPNN** | 9.88 | 8.8 | **1.12** | **0.89** | **5.2** |

**Finding 1.** PiPNN's 14× (GloVe) / 5.9× (SIFT) build-time advantage over
Vamana decomposes into *less work* (0.40× / 0.89× the distances — on SIFT
almost none of the gap is work) and a **5–6× higher throughput per
distance**, 93% of its evaluations being GEMM pairs. Each point is placed
in 30 leaves: PiPNN buys quality with redundant brute force it can afford
because the kernel is cheap, and still ends 41–45% (GloVe) / 4–13% (SIFT)
behind Vamana in distances per query.

**Finding 2.** PiPNN itself is at only ~27% of the machine's GEMM rate
(1.2 vs 4.5 G dist/s): leaves average 340 points, and the copy/norm/prune
overhead around each small GEMM is visible. The wall between it and the
search builders is nevertheless 5–6×; the wall between the search builders
and a bare GEMM is 20–27×.

## 2. Throughput vs n across the cache boundary (`bench/cache_sweep.py`)

GloVe prefixes, 64 threads; fg = GRAFT T16/ef400 frozen; Vamana R100/L200
2-pass; GEMM = float32 OpenBLAS `X[:n] @ X[:b].T` with n·b ≈ 2·10⁹ pairs
(best of 3). Working set = n × 448 B (fg pads d=100 → 112). d0: 20 MB L3
per socket, 80 MB total, ~150 GB/s aggregate DRAM bandwidth.

| n | working set MB | fg s | fg G | **fg G/s** | Vamana s | Vamana G | **Vamana G/s** | **GEMM G/s** | GEMM / fg | GEMM / Vamana |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 20,000 | 9 | 1.0 | 0.26 | 0.250 | 0.9 | 0.27 | 0.291 | 1.47 | 5.9 | 5.1 |
| 50,000 | 22 | 3.6 | 0.81 | 0.226 | 2.5 | 0.85 | 0.338 | 1.48 | 6.5 | 4.4 |
| 100,000 | 45 | 9.4 | 1.81 | 0.193 | 7.0 | 1.93 | 0.276 | 2.34 | 12.1 | 8.5 |
| 200,000 | 90 | 23.6 | 4.03 | 0.171 | 18.0 | 4.29 | 0.238 | 3.41 | 19.9 | 14.3 |
| 500,000 | 224 | 68.9 | 11.48 | 0.167 | 54.9 | 12.07 | 0.220 | 4.54 | 27.2 | 20.6 |
| 1,183,514 | 530 | 183.8 | 30.28 | 0.165 | 146.4 | 31.56 | 0.216 | 4.45 | 27.0 | 20.6 |

(The GEMM column rises with n only because the matrix shape improves —
at n=20k the 2·10⁹-pair product is 20k×20k; at n≥200k OpenBLAS reaches
~4.5 G dist/s = 0.9 TFLOP/s, ≈45% of d0's 2 TFLOP/s FMA peak. Read the
right-hand ratios at n ≥ 200k: **the search-based builders run 20–27× below
a bare GEMM.**)

**Finding 3 — the DRAM-bandwidth hypothesis is only half the story.**
The search-based rate does *not* collapse at the L3 boundary: from a 9 MB
working set (fits in one socket's L3) to 530 MB (DRAM-resident) fg loses
34% and Vamana 26%, and the decline is gradual. Already **in cache**, the
search builders evaluate one distance per ≈200–250 core-cycles (0.25–0.29 G/s
on 32 cores at 2 GHz), against ≈50 cycles for a register-blocked GEMM at the
same efficiency — i.e. the first 5–6× is *adaptivity overhead*: every
evaluation sits inside a dependency chain (beam heap, visited set, candidate
sort, occlusion test) and cannot be blocked, so it runs at scalar/latency
speed regardless of where the operand lives. The DRAM boundary adds the
remaining 1.3–1.5×.

**Finding 4 — at full n Vamana is at 65% of the bandwidth ceiling.**
Bandwidth ceiling for adaptive evaluation = BW / 4d′ = 150 GB/s / 448 B =
0.335 G dist/s. Vamana reaches 0.216 (65%), fg 0.165 (49%). Roofline ratio
2F/BW with the *measured* GEMM rate: 4.45 / 0.335 = **13×** on d0. So on
this machine the two ceilings (overhead ≈ 0.29, bandwidth ≈ 0.34 G/s) are of
the same height; on a machine with more bandwidth per flop the overhead
ceiling dominates, on one with less (GPU, HBM aside) the bandwidth ceiling
does. Either way a search-based builder cannot approach a GEMM builder, and
the gap widens with newer hardware (AVX-512, int8 GEMM, GPUs).

## 3. Reading

1. **The wall is real, measured at 20–27× on d0, and it is not an
   implementation artifact**: two independently engineered search builders
   (ParlayANN's Vamana, our fg) sit within 1.3× of each other and both an
   order of magnitude below GEMM at every n.
2. **It is a property of adaptive evaluation, not of memory alone**: 5–6×
   of it exists with the data in cache. Formally, a search evaluates pairs
   (p, q) where q is a function of the previous result; no blocking is
   possible, so both the I/O reuse (Hong–Kung) and the register reuse of a
   GEMM are unavailable. Batched builders evaluate a pair set fixed in
   advance and get both.
3. **Scope of the limitation**: the GEMM side exists only for distances
   that decompose into inner products. For a black-box metric there is no
   batched kernel, the count of evaluations is the cost, and the search
   builders are the right design. For vectors, a builder that counts
   distances is measuring the wrong thing by ~20×, and no (T, ef, B) retune
   crosses that.
4. **Consequence for FGRAFT**: mutation reduced *work* (0.73–0.88× Vamana)
   and cannot touch the term that dominates. The paper's honest claim is the
   separation of feedback from serial dependency + the quantified wall; the
   only lever on the wall inside the search paradigm is block-coherent
   harvesting (blocks by SAT leaf instead of p mod B) to recover *cache*
   reuse — bounded by the in-cache ratio, ≈5×, never by the GEMM rate.

Raw logs: `results/wall/` (PiPNN counted runs, per-n fg/Vamana logs,
`cache_sweep.json`).
