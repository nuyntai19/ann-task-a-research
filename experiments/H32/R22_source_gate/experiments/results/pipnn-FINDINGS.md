# PiPNN on every corpus of paper 2 — the framing is refuted (2026-09-25, d0)

**Question (HANDOFF §2):** paper 2 (`DensePaper/dense.tex`) rests its
"partition-then-brute-force has been a quality compromise" framing on ONE
PiPNN row, GloVe, carried from Phase 1b and unlabelled. Does the GloVe gap
(PiPNN 41-45% behind Vamana) generalise? **It does not. GloVe is the outlier.**

## Protocol

d0 idle (load 1.0), 64 threads, one build per arm, `bench/d0_pipnn.sh`
(= `run_pipnn.sh` on d0, tmux `fgpipnn`, 33 min for the whole chain).
Binary `PiPNN/build/algorithms/PipNN/neighbors-pipnn_FLOAT_T_EUCLIDEAN`
(ParAlg/PiPNN 443a328 + our distance-counter patch, no algorithmic change).
Recipe = PiPNN's defaults, which are the README's recommended flags:
num_clusters 1, cluster_size 1024, mst_deg 2, fanout_scheme 10,3,1 (30
leaves per point), top_level_leaders 1000, fraction_leaders 0.005,
hash_bits 12, prune + prune_all; alpha = the Vamana alpha of the same table
(README: "we always use the same alpha as Vamana"); prune_degree 64 =
Vamana's R everywhere but GloVe (R100), where both 64 and 100 were run.
Graded in-process by the same ParlayANN searcher and Q ladder as every
Vamana row; d@r interpolated by `bench/parse_parlay.py`, which reproduces
every published Vamana/dense figure from the reference logs to the digit.
Logs: `results/pipnn/pipnn_<corpus>_d<deg>.log`; references re-parsed in
`results/pipnn/ref/` and `results/deep/`. Graphs on d0 in
`/mnt/raid/fgraft-campaign-2026-09-22/pipnn_*.graph` (20 GB, safe to delete).

**Two provenance corrections for Table 3.** (1) "PiPNN R100/L200" is a
mislabel: PiPNN ignores -R/-L; the Phase 1b graph had prune_degree 64 (max
degree 64 in its log), so the row is *not* degree-matched to Vamana R100.
(2) Rerun today it reproduces (13,302 / 18,770 vs 13,320 / 18,825), and the
degree-matched arm (prune_degree 100) is *worse*: 13,889 / 19,480.

## Quality: distance evaluations per query at the tables' recalls

| corpus | r | Vamana | dense | **PiPNN** | PiPNN vs Vamana | PiPNN vs dense |
|---|---|---:|---:|---:|---:|---:|
| GloVe 1.18M d100 | 0.95 | 9,204 | 9,069 | 13,302 | **+44.5%** | +46.7% |
| | 0.97 | 13,325 | 13,322 | 18,770 | **+40.9%** | +40.9% |
| SIFT 1M d128 | 0.98 | 1,619 | 1,682 (L700) | 1,784 | +10.2% | +6.1% |
| | 0.99 | 2,172 | 2,155 | 2,264 | +4.2% | +5.1% |
| GIST 1M d960 | 0.90 | 3,191 | — | 2,970 | **-6.9%** | — |
| | 0.95 | 5,281 | 5,209† | 4,548 | **-13.9%** | -12.7% |
| | 0.97 | 7,445 | — | 6,069 | **-18.5%** | — |
| Deep-10M d96 | 0.95 | 2,150 | 2,180 (L2400) | 2,463 | +14.6% | +13.0% |
| | 0.97 | 3,031 | 2,854 | 3,175 | +4.8% | +11.2% |
| | 0.99 | 5,159 | 4,811 | 5,225 | +1.3% | +8.6% |
| Wikipedia 6.35M d1024 | 0.90 | 2,087 | 1,974 | 2,048 | -1.9% | +3.7% |
| | 0.95 | 4,246 | 3,868 | 4,159 | -2.0% | +7.5% |
| | 0.97 | 6,942 | 6,705 | 6,624 | **-4.6%** | -1.2% |
| | 0.98 | 10,069 | 11,118 | 10,502 | +4.3% | **-5.5%** |
| Deep-100M d96 | 0.95 | 4,047 | 3,775 | 4,285 | +5.9% | +13.5% |
| | 0.97 | 5,650 | 5,105 | 5,757 | +1.9% | +12.8% |
| | 0.99 | 10,547 | 8,831 | 10,292 | **-2.4%** | +16.5% |

† tab:gist's dense figure is from fg's OWN searcher (`results/deep/fg_dense_gist.log`,
ef 120-200 bracket), while its Vamana row is ParlayANN-graded. The table
mixes searchers and the caption does not say so — a third provenance fix.
No GIST dense graph dump exists on d0 to regrade; ~8 min if wanted.

## Cost: build wall-clock, build distances, peak RSS

| corpus | Vamana | dense | **PiPNN** | PiPNN G dist (Vam / dense) | PiPNN RSS |
|---|---:|---:|---:|---:|---:|
| GloVe | 146.2 s | 97.6 s | **10.3 s** | 12.6 (31.6 / 93.4) | 5.5 GB |
| SIFT | 51.5 s | 51.5 s | **8.8 s** | 9.9 (11.1 / —) | 5.1 GB |
| GIST | 632.5 s | 430.5 s | **35.0 s** | 11.3 (19.6 / 30.9) | 8.8 GB |
| Deep-10M | 699 s | 734 s | **92.3 s** | 134 (278 / 661) | 25 GB |
| Wikipedia | 5,176 s | 2,507 s | **243.5 s** | 87 (282 / —) | 39 GB |
| Deep-100M | 9,784 s | 15,186 s | **1,025 s** | 1,627 (4,151 / 9,696) | 228 GB (dense 327) |

PiPNN's build is 6-18x faster than Vamana and 6-15x faster than the dense
construction on every corpus, with the fewest distance evaluations of the
three everywhere (its leaf stage is a GEMM at 1024-point leaves).

## What this does to paper 2

1. **The introduction's premise is false as stated.** "What is also
   established ... is that they have been a quality compromise" is true on
   GloVe (+41-45%) and false on GIST (PiPNN *beats* Vamana by 7-19%),
   Wikipedia (within ±5%) and Deep-100M (within ±6%, ahead at 0.99). The
   supporting citation to `chavez2026wall` reports GloVe only.
2. **§4's regime explanation survives, inverted.** The paper already says the
   partition loss is "the signature of high intrinsic dimension" and "why
   PiPNN places every point in 30 leaves and still trails". That is the
   right mechanism and it now predicts the table: GloVe (high LID, hubness)
   is where partitioning loses; GIST/Wikipedia, high *ambient* d but
   partition-friendly, are where it wins. The regime is a property of the
   corpus, not of the method class.
3. **The dense construction's advantage over PiPNN is real but narrow:**
   GloVe (32-47%), Deep-10M (9-13%), Deep-100M (13-17%). It is a draw or a
   loss on SIFT (5-6%), GIST (-13%) and Wikipedia (-5% to +8%). And on
   every corpus PiPNN builds 6-15x faster than dense.
4. **The k-means claim in §4 ("the difference between PiPNN's design point
   and ours") needs the GIST/Wiki caveat:** random leaders with 30
   memberships beat Lloyd leaders with 5 memberships on those two corpora.
5. **The GloVe/Deep-100M result stands and is now sharper:** the only
   corpora where the dense build beats Vamana (Deep-100M, -16% at 0.99)
   are also where it beats PiPNN by the widest margin outside GloVe.

The honest reframing: partition-then-brute-force is *not* a quality
compromise in general (PiPNN shows that on 4 of 6 corpora); the dense
construction is the one that reaches Vamana parity on the corpus where
partitioning does lose (GloVe) and pulls ahead of both at 10^8, at the
price of a build 6-15x slower than PiPNN's. Whether that price is worth
paying is now the paper's question, and §5 and the abstract have to say
so. **Author decision: the framing rewrite is not something to do without
you.**

## Open

* Why GloVe. LID / hubness of the six corpora against the PiPNN-vs-Vamana
  gap would turn item 2 into a measured law rather than a story; the pool
  study (tab:pool) is GloVe-only.
* PiPNN with Lloyd leaders, or dense with 30 random memberships, would
  separate leader choice from membership count. One afternoon on d0.
* Regrade GIST dense on ParlayANN's searcher (dump + `-graph_path`).
