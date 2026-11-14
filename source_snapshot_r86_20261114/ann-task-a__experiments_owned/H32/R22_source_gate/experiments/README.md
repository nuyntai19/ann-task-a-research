# fgraft-experiments

Experiments, logs and patches behind two papers on building navigable graph
indexes for approximate nearest neighbor search:

1. **Batched Feedback and the Random-Access Wall in Search-Based Graph
   Construction** — [arXiv:2609.30493](https://arxiv.org/abs/2609.30493).
   Search-based builders run an order of magnitude below the machine's dense
   arithmetic; most of the gap is present with the data in cache.
2. **Building Navigable Graphs Without Search in Three Composable Stages**
   (pool, ending, spine) — [arXiv:2610.09041](https://arxiv.org/abs/2610.09041).
   Partition, evaluate every pair inside each part, and turn the candidates
   into edges; the ending composes with PiPNN's partition and, with enough
   memberships per point, matches or beats a full dense construction on six
   corpora from 10^6 to 10^8 points.

Every number in both papers traces to a log and a findings file here. The
code base is that of GRAFT (É. Chávez, *Graft: Navigable graphs grown on
spatial-approximation rootstock*, Information Systems, 2026, article 102812,
[doi:10.1016/j.is.2026.102812](https://doi.org/10.1016/j.is.2026.102812)).

## Where the code is

| component | where |
|---|---|
| the construction (`fg --dense ...`, HSP spine, per-point memberships, automatic spine size, orphan repair) | [`zevahcle/graft-ann`, branch `fgraft`](https://github.com/zevahcle/graft-ann/tree/fgraft) (dense flags as of commit `a032c2d`) |
| PiPNN with reservoir export and determinism | [`ParAlg/PiPNN`](https://github.com/ParAlg/PiPNN) at `443a328` + `patches/pipnn-443a328-graft.patch` |
| ParlayANN distance counter | `patches/parlayann-build-distance-counter.patch` |
| drivers, analysis, d0 chains | `bench/` |
| logs and findings | `results/` |

### The PiPNN patch

`git apply patches/pipnn-443a328-graft.patch` in a PiPNN checkout at
`443a328`. It adds build-distance counters and two opt-in features driven by
environment variables; with none set, PiPNN behaves as upstream apart from
printing the counters.

* `PIPNN_DUMP=<file> PIPNN_DUMP_C=<C>` — export each point's candidate
  reservoir, exactly re-ranked, immediately before PiPNN's final prune, as
  `n x C` int32 rows (nearest first, `-1` padded). Read-only: PiPNN's own
  graph is unchanged. `fg --dense 1 --dense-C C --dense-cands <file>` applies
  our ending to it.
* `PIPNN_SEED=<s> PIPNN_DETERMINISTIC=1` — a deterministic build: fixed
  partition seed, merged buckets sorted before positional leader sampling,
  sequential draw of the sketch-hash vectors, and an order-free reservoir
  merge (total order on (bfloat16 distance, id); a bucket keeps its minimum,
  a full table evicts its maximum). Byte-identical across thread counts at
  10^6 (`results/open-items-FINDINGS.md`, D).

PiPNN is MIT-licensed; the patch modifies its source and remains under its
terms (copyright the PiPNN authors).

## Findings, by question

| question | file |
|---|---|
| the random-access wall (paper 1) | `results/wall-FINDINGS.md`, `results/density-FINDINGS.md`, `results/dimnote-CHECK.md` |
| PiPNN on every corpus | `results/pipnn-FINDINGS.md` |
| pool vs exact-kNN ceiling; the 200-nearest heap confound | `results/capped-FINDINGS.md` |
| pool shape and the measure law | `results/perm-FINDINGS.md`, `results/cell-adjacency-FINDINGS.md`, `results/random-FINDINGS.md`, `results/kmeans-init-FINDINGS.md` |
| clustering of the kNN graph vs block-cover cost | `results/transitivity-FINDINGS.md` |
| adaptive memberships (negative); HSP spine; sample size x degree cap | `results/adaptive-spine-FINDINGS.md` |
| our ending on PiPNN's pool | `results/pipnn-ending-FINDINGS.md` |
| tests T1-T5 (10^8, alpha, GloVe, spine in every table, clustering vs n) | `results/framing-FINDINGS.md` |
| determinism, k=100 and QPS for all systems, hnswlib, automatic spine, orphans | `results/open-items-FINDINGS.md` |
| memberships at scale (Deep-100M, Wikipedia, GIST, Deep-10M) | `results/memscale-FINDINGS.md` |
| 2-bit quantisation inside a pool; the dense construction's history | `results/evp-FINDINGS.md` |

`results/CAMPAIGN-2026-09-22.md`, `PLAN.md` and `PLAN-SPLIT.md` record the
campaign's design, including branches that were refuted. Some notes refer to
internal session notes that are not part of this release.

## Reproducing

* **Machine.** Builds were run on a 4-socket Xeon E7-4809 v3 (32 cores, 64
  threads, 1.5 TB). The `bench/d0_*.sh` chains assume its paths
  (`/mnt/claude/graft-work/fgraft`, `/mnt/raid/...`); set `W`, `O`, `D` and the
  binary paths at the top of each chain for another machine. Laptop scripts
  assume a local data directory; edit the path at the top.
* **Data** (not included): GloVe-100 (1,183,514 points, unit-normalised),
  SIFT1M, GIST1M, Deep-10M and Deep-100M (prefixes of Deep1B), and 6.35 M
  BGE-M3 Wikipedia embeddings (d = 1024). Ground truth: exact 100-NN.
* **Grading.** Every graph is dumped and graded by ParlayANN's searcher
  (`neighbors-vamana ... -graph_path`); `bench/parse_parlay.py` and
  `bench/parse_qps.py` turn its logs into distance evaluations and QPS at fixed
  recall; `parse_parlay.py` reproduces every published figure from the logs.
* **Determinism gate.** Every `fg` graph is checked with
  `--check-determinism` (adjacency hash at 1 and 64 threads) and by its total
  distance count before a number is recorded.

## License

Apache License 2.0 (see `LICENSE`), except `patches/pipnn-443a328-graft.patch`,
which modifies MIT-licensed PiPNN source and is distributed under PiPNN's
license.
