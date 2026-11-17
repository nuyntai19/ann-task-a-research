# R86 Day 2 — COUNTER PATCH CANDIDATE FOR CLAUDE REVIEW (NO BUILD)

**Status:** patch prepared, source-level static audit complete, independent header ON/OFF tests PASS, logger importer unit tests PASS; **native PiPNN compile/build/10K gating NOT RUN**.

## Source of truth / scope

- Uploaded source-review archive SHA256: `cc278dedd7bb6eb3ef4e06ef4037e33087ed23f579167e8b7c1ca0ef9e81b32f`.
- Baseline H70 is a **dirty** Git checkout on commit `443a328dc71a3b7be753d52ca2b3c9a4ba77f3fd`; patch requires actual source file SHA values recorded in `EXPECTED_SOURCE_SHA256.txt`, not clean upstream checkout.
- **Do not apply this patch to `isolation_v4/pipnn.h`**. That version has R85_B1 snapshot/paired-export code. Use the R85 `isolation_v4` **staging strategy**, but copy the exact H70 baseline snapshot without the R85_B1 instrumentation into an isolated R86 working tree before applying.
- Existing H70/R85 source, builds and saved graphs are **read-only**.

## Files

- `R86_counter_source.patch` — CMake ON/OFF, instrumentation in H70 PiPNN source, new `r86_counters.hpp`.
- `R86_logger_importer.patch` — logger accepts **leaf depth=null** because merged/split leaf buckets in PiPNN no longer retain their construction depth.
- `CLAUDE_REVIEW_CHECKLIST.md` — exact hook points, invariants, limitations and requests for review.
- `EXPECTED_SOURCE_SHA256.txt` — the specific H70 file SHA values required for this patch.
- `scripts/check_and_dry_run.sh` — **read-only** checksum gate and dry-run patch verification.
- `tests/test_counter_header.cpp` — synthetic ON/OFF test fixture, not a PiPNN build.

## Key hook placement in the actual submitted source

1. `pipnn.h / multiple_clustertrees()` — `begin_pass(i+1)` **before** the blocking `recursively_sketch_wrapper()`. Pass0 is reserved for **final** robustPrune.
2. `pipnn.h / SelectAndAssignLeaders()` — `W_P += ids.size()*num_leaders`, `W_A += ids.size()*actual_fanout`, `note_depth(depth)`; upstream COMPARISONS is separately retained.
3. `pipnn.h / RunLeaf()` — leaf_count, leaf_size_sum, `W_L += s*s`, `W_pairs += s*(s-1)/2`; depth=null, because `RunLeaf` only receives the *final* bucket.
4. `pipnn.h / recursively_sketch_wrapper()` — independent JSONL leaf-size dump from the bucket list **before** calling `RunLeaf` (only `size>1`); pass ID recorded, depth **null**. This is for counter cross-check, not timing.
5. `pipnn_utils.h / eigen_knn()` — directed proposals counted once for each edge in `directed_edges`, not twice.
6. `graph.h / LSHGraph::merge_neighbors()` — actual processed merge attempts counted once per visited candidate. `collision_same_id` versus `collision_diff_id` only within actual `hash==cand_hash` branch, *after* early-break. Hash accept/reject/replace/full counts have explicit event semantics; production logic preserved.
7. `pipnn_utils.h / robustPrune()` — increment immediately before actual `Points[p_star].distance(Points[p_prime])` call. `dist_traversed` was counting candidates visited, **not** this distance count.
8. `pipnn.h / build_index_impl()` — refuses ON output files not given or non-absolute, declares final pass0 counter, writes counter JSONL only after ExportToGraph has fully joined.
9. `CMakeLists.txt` — ON only when `R86_USE_COUNTERS=ON` (sets `R86_COUNTERS=1`). OFF has no counter effects; source uses `#if defined(R86_COUNTERS) && R86_COUNTERS` so even `-DR86_COUNTERS=0` is OFF.

## Zero versus NOT_MEASURED

The original header silently omitted metrics with measured value 0. This patch declares the relevant per-pass metric scopes and emits `observed:0` when measured. No declared scope means NOT_MEASURED. This prevents conflation.

## Semantic limitations / important caveats

- `W_L=s²` is a logical matrix-entry proxy, **not** FLOPs or exactly the number of unique pairs.
- `W_P` counts planned point–leader entries; it is **not** search NDC.
- `collision_same_id` is a **lower bound** on repeated IDs reaching a hash-collision branch, not a unique-pair duplicate rate.
- `hash_full` counts visited candidate events while degree is at logical capacity, including early-break cases. `hash_replace` counts replacements *of an existing slot*, both collision and full-capacity replacement; `hash_accept` counts successful state updates. `hash_reject` counts collision rejection or early-break. Counts are not a partition of proposals because one proposal may increment multiple metrics, and proposals can be further processed in both forward and reverse directions.
- `merge_attempts` counts candidates *entered* by LSHGraph merge (after acquiring node lock), including early-break candidate; not necessarily all elements of a multi-item span. The current PiPNN `eigen_knn()` uses singleton spans. Compare only with `2*proposals` when baseline semantics and no alternate producers are verified.
- `max_depth` comes from the deepest executed call of `SelectAndAssignLeaders`; not necessarily the depth of a final leaf.
- The recorded `std::random_device` seeds a local `parlay::random rnd` in `recursively_sketch_wrapper`, **but that `rnd` variable is unused in the supplied source**. It is therefore not justified to claim that this line itself makes the partitions non-deterministic. Other parallel scheduling/order effects remain possible; use actual reproducibility tests.
- The counters only instrument `LSHGraph` flat storage. This patch is for A0–A4; D0 TwoTier and HashSetGraph are not part of the native Day2 counter evaluation.
- Buffered thread-local counts avoid atomics per candidate but instrumentation still changes runtime and memory layout. The ON binary is **never** used for benchmark timing claims.
- The current snapshot has no independent native build in this environment (dependencies not present in uploaded source review). Exact compiler integration is **pending Claude review and Ubuntu test**.

## After Claude review — recommended gates (not yet executed)

1. On Ubuntu, create an isolated R86 source stage using B1's known copy/symlink workflow, **from H70 baseline**, not from B1's instrumented `pipnn.h`.
2. Run `bash scripts/check_and_dry_run.sh /path/to/R86/source` (read-only).
3. Apply `R86_counter_source.patch` only to that isolated staging source; apply `R86_logger_importer.patch` only to an isolated copy of R86 logging kit.
4. Build A0 Stock and H17 Flat each with `R86_USE_COUNTERS=OFF` and `ON` (four binaries) *only after code review*.
5. OFF build 100K: use identical dataset/parameters/evaluator to R85 and compare graph validation, arc count and Recall at identical beams. Random/order effects may require a pre-declared tolerance and replicate builds; do not require binary SHA identity or exact graph SHA identity.
6. ON build 10K 1 worker: export JSONL from `R86_COUNTER_OUT` and `R86_LEAF_SIZE_OUT` **unique absolute nonexistent filenames**; check independent leaf-size audit and summary invariants, then graph validation.
7. If the gate passes, begin the pre-registered n-sweep; if it fails, stop and keep raw output.
