# Enlarged Voronoi cells via witnessed adjacency — GIST-960, laptop, 2026-09-29

**Construct (author):** a permutant's cell plus its neighbouring cells,
the neighbours discovered combinatorially: q is adjacent to p when a
point of p's cell has q as its second-nearest permutant — the data
witness the Delaunay edges of the permutant set. Candidate pool = own
cell ∪ (top-m co-cited cells). `bench/cell_adjacency_diag.py`, 1,000
random permutants, 1,000 sampled points with exact 10-NN, run on the M5
in 25 s.

## The witnessed Delaunay graph of 1,000 random permutants in 960-d

Cells: mean 1,000, median 406, max 15,527. Witnessed degree (distinct
second-nearest cells cited by a cell's members): mean 93, median 80,
max 359 of 999 — far from complete, and concentrated: the top 5 co-cited
cells carry 41% of a cell's citations, top 10 57%, top 20 74%, top 50 91%.
A true-neighbour pair shares its cell 22% of the time.

## Coverage of true-neighbour pairs against pool size

| m | own cell + top-m co-cited (cell level) | pool | own + m nearest permutants (point level) | pool |
|---:|---:|---:|---:|---:|
| 1 | 0.290 | 9.6k | 0.340 | 7.3k |
| 2 | 0.338 | 15.0k | 0.422 | 10.7k |
| 5 | 0.430 | 27.6k | 0.581 | 20.5k |
| 10 | 0.544 | 47.4k | 0.717 | 35.9k |
| 15 | — | — | 0.797 | 50.1k |
| 20 | 0.654 | 78.4k | (k = 16 cap) | |
| 50 | 0.801 | 148k | | |
| 100 | 0.886 | 233k | | |

**At equal pool the point-level neighbourhood dominates the cell-level
one** (0.78 vs 0.54 near 47k; 0.80 at 50k vs 0.80 at 148k). The reason is
the one the construct was built to exploit, applied one level down: the
point's own ranking of permutants says which adjacent cells matter *for
that point*; the cell's citation ranking says which matter on average
for the cell, and a point near a boundary is not average. The enlarged
cell is a coarsening of the m-nearest-permutant membership, not a
refinement of it. Second-order neighbourhoods only multiply the pool.

## What this closes

Pool recall follows measure on GIST whatever the shape: 0.58 at 20k, 0.72
at 36k, 0.80 at 50k for nearest-permutant memberships; and 0.80 at
~50k is what the ceiling-class graphs used (k-means L700/m5 at 53k
effective, random L90000/m30 at 46k, both within 3% of the exact
ceiling). Cells, enlarged cells, trie blocks and nearest-permutant
memberships are one family under one law: pairs ∝ measure, measure ∝
recall. The only construction below the law was the count ranking
(4,000 candidates at ceiling quality), which pays in the integer merge
and random-access verification rather than in GEMM pairs.

The witnessed adjacency graph itself is a cheap, natural structure — a
Delaunay-like graph over the permutants with the data as witnesses — and
may have a use for routing between cells at search time; for candidate
generation it does not beat what each point already knows.

## Second pass (same day): adjacency ranked by rate, deeper witnesses, and the k-means reference

`bench/supercell_variants.py`, `bench/pool_recall_ref.py`, M5, GIST local.

**Every way of building and ranking the supercell lies on one curve.**
Coverage of true-neighbour pairs by own cell + top-m adjacent cells:

| adjacency from | ranking | m = 5 | m = 10 | m = 20 | m = 50 |
|---|---|---:|---:|---:|---:|
| 2nd nearest | raw count | 0.430 @ 28k | 0.544 @ 47k | 0.654 @ 78k | 0.801 @ 148k |
| 2nd nearest | count / \|q\| | 0.286 @ 9k | 0.343 @ 14k | 0.429 @ 26k | 0.617 @ 70k |
| 2nd nearest | count / √\|q\| | 0.373 @ 18k | 0.472 @ 32k | 0.583 @ 54k | 0.744 @ 112k |
| 2nd + 3rd | raw | 0.430 @ 28k | 0.544 @ 48k | 0.658 @ 80k | 0.808 @ 150k |
| 2nd..5th | raw | 0.433 @ 28k | 0.545 @ 49k | 0.662 @ 81k | 0.812 @ 153k |
| 2nd, symmetric | raw | 0.431 @ 28k | 0.542 @ 48k | 0.652 @ 79k | 0.804 @ 150k |

Normalising by cell size picks smaller cells and lands on the same
recall-per-pool line; deeper witnesses (3rd..5th nearest) add nothing;
symmetrising adds nothing. The construct's recall is a function of its
pool, and the line sits ~3x in pool below the point-level one (0.58 @ 20k,
0.72 @ 36k, 0.80 @ 50k).

**The reference that matters: the paper's own leaves.** Pool recall and
pair count of the multi-membership leaf schemes (symmetric: all pairs
inside every leaf; one-sided: each cell's primary members against all
its citers), from the numpy replica of fg's k-means (10 Lloyd iterations
on a 200k sample; the pair count reproduces fg's 26.4 G exactly):

| leaders | m | symmetric leaves: recall @ pool, pairs | one-sided: recall @ pool, pairs |
|---|---:|---|---|
| k-means L700 (paper) | 5 | **0.895 @ 52k, 26.4 G** | 0.604 @ 10k, 10.0 G |
| k-means L700 | 10 | 0.990 @ 219k, 110 G | 0.747 @ 20k, 20 G |
| k-means L700 | 15 | 0.999 @ 500k, 252 G | 0.831 @ 30k, 30 G |
| random L1000 | 5 | 0.866 @ 84k, 42 G | 0.542 @ 17k, 17 G |
| random L1000 | 10 | 0.987 @ 314k, 157 G | 0.697 @ 33k, 33 G |
| random L1000 | 15 | 0.998 @ 672k, 337 G | 0.784 @ 47k, 47 G |

Three things this settles:

1. **The symmetric leaf is the most pair-efficient block structure
   measured.** At m = 5 the k-means leaves reach recall 0.895 for 26 G
   pairs; the one-sided form needs m = 15 and 30 G for 0.83; the supercell
   needs 148k of pool for 0.80. The citer-by-citer pairs the symmetric leaf
   adds are not waste: two points that both rank q among their nearest
   leaders are shared-neighbour pairs, and they are where the recall is.
2. **k-means halves the pool against random leaders at equal memberships**
   (0.895 @ 26 G vs 0.866 @ 42 G) — the paper's Table 2 claim, reproduced on
   GIST. Random leaders match k-means only with many memberships in small
   cells (L90000/m30: 23 G pairs, 46k effective, d@0.95 4,419), which is the
   PiPNN design point.
3. **The supercell is dominated twice over**: by the per-point membership
   (a fixed neighbourhood per cell serves the average point of the cell; a
   point near one face needs the cells across that face, and its own
   permutant ranking says which), and then by the symmetric leaf, which
   evaluates exactly the per-point neighbourhoods as blocks. Concentration
   and hubness are not the reason; the reason is that adjacency is a
   property of points, not of cells, and the leaf scheme already computes it.

## Third pass (same day): supercells from the Half-Space Proximal graph of the witnesses

`bench/hsp_supercell_diag.py`. HSP on the 1,000 permutants (α = 1
occlusion, nearest-first), objects assigned to their nearest witness.

**The HSP is sparse where the Delaunay was not:** degree mean 10.9, median
9, max 50 (the witnessed Delaunay adjacency had ~93). The author's
premise holds.

| supercell | coverage | pool |
|---|---:|---:|
| own + HSP neighbours (directed) | 0.379 | 33k |
| own + HSP neighbours (symmetrised) | 0.453 | 44k |
| own + HSP two hops | 0.922 | 398k |
| own + 5 / 10 / 20 nearest HSP neighbours | 0.400 / 0.437 / 0.451 | 23k / 33k / 41k |
| *cell level, no HSP:* own + 5 / 10 / 20 / 50 nearest witnesses | 0.443 / 0.540 / 0.646 / 0.806 | 26k / 45k / 76k / 155k |
| *point level:* own + 5 / 10 / 15 nearest permutants | 0.581 / 0.717 / 0.797 | 20k / 36k / 50k |

At equal pool the HSP supercell sits slightly *below* the plain
nearest-witness cell neighbourhood (0.453 @ 44k against 0.540 @ 45k) and
far below the point-level membership (0.78 @ 47k); the occlusion rule
removes some near cells that still hold neighbours, and the second hop
buys its 0.92 with 398k of pool, on the same measure line. Sparse degree
is real and it does not help: a sparser cell-level neighbourhood is a
cheaper way to choose the *wrong* cells for most of a cell's points, for
the same reason as before — which neighbouring cells matter is decided
by the point, and every point of a cell decides differently. The HSP's
value is as a routing graph (its spanner property), not as a partition.
