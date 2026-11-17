<!-- GENERATED_BY_ANN_PROJECT_HOME_V1_0. Keep personal notes in 09_MY_NOTES.md. -->
# PROJECT STATUS (auto-generated)

Generated at UTC: 2026-11-13T09:22:54+00:00

- Main project root: `/home/tai/ann-task-a`
- Navigation hub: `/home/tai/ann-task-a/00_PROJECT_HOME`
- Current active code: `/home/tai/ann-task-a/experiments/R86/r86_v1_2_source`
- Main 100K campaign: `/home/tai/ann-task-a/experiments/R86/benchmarks/sift100k_a0a4_hw85_7ueCvd`
- Graph inventory: **runs.csv=20 rows; graph_present=20; graph_nonempty=20; graph_missing=0**
- 100K counter audit: `COUNTER_IDENTITIES_PASS_ALL_FIVE_100K` (from user terminal log; files under analysis_exports)
- 100K search: **NOT RUN / B_SEARCH not filled**
- Ground-truth SIFT100K candidate `sift100k_gt300.ibin`: HEADER_UNVERIFIED: first_u32=300,100, bytes=240008, expected_if_u32=120008
- Candidate query files found under `data` with obvious names: **2**

Candidate queries (not yet chosen):
- `/home/tai/ann-task-a/data/sift100k_queries_300.fbin`
- `/home/tai/ann-task-a/data/sift1m_queries.fbin`

## Next work

1. Verify native graph adjacency format and one or more 100K graph variants (no rebuild).
2. Find/verify a query dataset and match it to the `sift100k_gt300.ibin` candidate; independently recompute a sample of exact neighbor answers using SIFT100K base.
3. Pin ONE evaluator and CPU/query protocol; run matched-Recall search on already-built graphs; upload B_SEARCH metrics.
4. Only after B_SEARCH, draw A0..A4 conclusion and n-scaling plots.
