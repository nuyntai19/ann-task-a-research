# Coherent-block density: can the harvest be batched into GEMMs? (laptop, 2026-09-17)

Question (EC): group the products in advance and use PiPNN's trick. The
decisive number is the *density* of a lockstep block: needed pairs /
(B × |union of evaluated ids|). GEMM runs 20–27× faster than the beam on d0
(`wall-FINDINGS.md`), so density must exceed ≈1/27 = 3.7% to break even.

Instrumentation: `fg --dump-parents` (tree-0 parents ⇒ SAT subtrees) and
`fg --log-visited MASK OUT` (every id whose distance to p was evaluated, in
order, with expansion markers). Blocks: 64 coherent = maximal tree-0 subtrees
of size ≤512 (median 178 on GloVe, 214 on SIFT); 64 random of the same
size as control. `bench/density.py`. Frozen scaffold, harvest cap 64.

## 1. Lockstep density (union scheme: compute B × |∪V_i| once, lazily by column)

| run | block | B | evaluated / point | ∣∪V_i∣ | **density** | union MB |
|---|---|---:|---:|---:|---:|---:|
| GloVe T16/ef400 | coherent | 178 | 11,547 | 384,776 | **0.028** | 172 |
| GloVe T16/ef400 | random | 178 | 12,427 | 875,260 | 0.014 | 392 |
| GloVe T16/ef100 | coherent | 178 | 3,917 | 191,922 | **0.020** | 86 |
| GloVe T16/ef100 | random | 178 | 4,033 | 462,430 | 0.009 | 207 |
| SIFT T4/ef400 | coherent | 214 | 2,742 | 86,375 | **0.032** | 39 |
| SIFT T4/ef400 | random | 214 | 2,823 | 406,245 | 0.007 | 182 |

**Refuted.** Density is 2–3% in every configuration: below break-even, and
B cannot fix it (the union saturates at n as B grows, so density → |V_i|/n
≈ 1%). Coherence (same SAT subtree) helps only 2× on GloVe, 4.5× on SIFT.

Per-phase profile (GloVe ef400, coherent): density is 1.2% in expansions
1–10 and rises only to 4% after step 240 — **neighbouring points' beams
diverge immediately** after the shared entry set; the top of the descent is
not shared (the 16 roots have degree in the hundreds, and the argmin over
them differs from point to point).

## 2. Column multiplicity (sparse batching: reuse of a loaded vector)

Share of *needed* evaluations that fall on ids also needed by ≥k other
queries of the same block (GloVe ef400, 24 blocks):

| block | mean mult. | needed on ids with mult ≥8 | mult ≥32 |
|---|---:|---:|---:|
| coherent | 5.3 | **0.66** | 0.32 |
| random | 2.6 | 0.13 | 0.007 |

So a *column-batched* kernel (group the block's pending evaluations by
target id; the block's query rows, 178 × 448 B = 80 KB, live in L2) would
load each target vector once per ~8–30 uses for two thirds of the work.
That removes the DRAM term of the wall (the 1.3–1.5× measured in the sweep)
but **not the adaptivity term** (the 5–6× that exists in cache): every
evaluation still feeds a heap, a visited stamp, a top-cap tracker and an
occlusion test before the next expansion can be chosen. Column batching
cannot beat ≈2× on the harvest.

## 3. Non-adaptive (structural) candidate sets — the PiPNN route

If the candidate set of a block is fixed in advance from the scaffold, the
GEMM is dense by construction and the cost is the candidate count:

| block (GloVe T16 scaffold, mean deg 29.7) | ∣1-hop ∪∣ | per point | ∣2-hop ∪∣ | per point |
|---|---:|---:|---:|---:|
| coherent (SAT subtree, B=178) | 4,699 | 26 | 121,134 | 648 |
| random (B=178) | 5,488 | 31 | 187,649 | 1,054 |

**SAT subtrees are not compact in the scaffold**: the 1-hop union is
≈ B × degree (siblings' neighbourhoods barely overlap; a SAT subtree is a
cone, not a ball). A dense 2-hop set costs 648 distances/point — 18× fewer
than the beam evaluates — but whether it is a *good* candidate set is
exactly GRAFT's open "structure vs search provenance" question, and GRAFT
measured that search provenance wins for the long-range edges.

Reference point: PiPNN evaluates 12.56 G / 1.18 M = **10,600 distances per
point on GloVe** — the same count as our ef400 beam (11,500). Its speed is
not less work; it is the same work done densely on leader-clustered leaves
(343 points, 30 memberships per point) with one partial sort per point
instead of a heap operation per distance.

## 4. Reading

1. **Lockstep GEMM over the existing beam is dead**: 2–3% density, and the
   divergence is immediate, not a late-phase effect.
2. **Sparse column batching is real but bounded (~2×)**: it attacks the
   memory term only; the wall's larger term is the per-distance bookkeeping
   that adaptivity forces.
3. **The batched design that can pay is non-adaptive candidates + cheap
   adaptive provenance**: dense brute force inside tight leaves (leader /
   k-means clusters, *not* SAT subtrees) for the local edges, and a
   small-ef far-start search (ef 100: 3.9k evaluations/point, 5.7 G total ≈
   35 s on d0) for the route/shortcut edges that PiPNN's graph lacks (its
   graph trails Vamana by 41–45% in distances/query). Projected GloVe build
   ≈ 45–50 s on d0 vs Vamana 146 s, at GRAFT-class quality if the union of
   the two edge sets prunes well. That is a *quality* experiment (build the
   union, serve it), and it is the next measurement.
4. **For the paper**: the density numbers are themselves a result — they
   quantify why search-based construction cannot be made dense after the
   fact, and locate the only batching that works (fixed pair sets), which
   is the honest reading of PiPNN's advantage.
