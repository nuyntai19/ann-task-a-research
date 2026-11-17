# R86 Day 2 Counter Patch v1.1 — Claude review, **NO NATIVE BUILD YET**

**Scope.** Full patch against the exact 2026-11-12 H70 dirty source snapshot, not against pristine commit 443a328 or the already-instrumented B1 `isolation_v4`. Copy the **B1 isolation workflow**, not B1's patched `pipnn.h`. This packet is for code review first. **Do not patch H70/R85 directly.**

## Changes made after Claude's v1.0 review

| Review | v1.1 response |
|---|---|
| B1: missing HashPrune comparisons/moves | `hash_compute`, `hash_lb_compares` (actual `Cmp` calls), `hash_moves` (number of shifted `T` slots), `hash_worst_scan` (slots touched), `hash_worst_compares` (`deg-1`), `hash_bound_compares` and `hash_slot_writes`. `HashWork` is accumulated locally while the node is locked and transferred once **after** `Unlock`. |
| B2: missing invariants | `tests/verify_event_stream.py` verifies exact, mutually exclusive branch accounting, proposal/merge parity, leaf dump, source cumulative `COMPARISONS`, Top-2 fallback Q writes, and occupancy. |
| W1: same ID | `collision_same_id` counted separately. `hash_same_id_rewrite` counts BF16 rounding-induced self rewrite **without** `hash_accept`/`hash_replace`. |
| W2: hot-loop atomic/add overhead | No `r86::add()` inside `LSHGraph::merge_neighbors` lock. A single `record_hash_work()` call after unlocking. RobustPrune distance calls accumulate local and flush once per vertex; **OFF guards** make these changes compile away in OFF. |
| W3: Stock Top2 | `top2_q_writes += leaf_size*(leaf_size-1)`, `partial_sort_calls += leaf_size` in the Stock/fallback branch. These count staging writes and calls, **not** moves/comparisons inside SIMD `VQPartialSort`, which still need a separate microbenchmark. |
| W4: reservoir occupancy | One pre-prune scan in `ExportToGraph` emits `R86_OCCUPANCY_OUT` JSON: precise counts by degree 0..C, `occupied_slots`, `full_nodes`, exact mean. Not an extra timed-binary operation. |

## Important correction to Claude's B2 proposed identity

Because same-ID candidates are kept in **a separate bucket** (W1), `hash_accept + hash_reject == merge_attempts` is **not valid** in general.

The corrected exhaustive invariant is:

```text
merge_attempts = hash_accept + hash_reject + collision_same_id
merge_attempts = hash_early_break + collision_same_id + collision_diff_id
                 + hash_insert_not_full + hash_replace_full
collision_diff_id = hash_diff_collision_rewrite + hash_diff_collision_reject
hash_accept = hash_insert_not_full + hash_replace_full + hash_diff_collision_rewrite
hash_reject = hash_early_break + hash_diff_collision_reject
hash_replace = hash_replace_full + hash_diff_collision_rewrite
hash_same_id_rewrite <= collision_same_id
hash_compute = merge_attempts - hash_early_break
```

`merge_attempts == 2 * proposals` is valid for the verified current PiPNN singleton forward/reverse merge path; tests gate it rather than assuming this identity for all possible `GraphH` implementations.

**Units and semantics:**
- `hash_moves` counts shifts of 8-byte candidate slots made by `std::move` or `std::move_backward`, *excluding* explicit writes at insertion/overwrite. `hash_slot_writes` separately counts one logical slot overwrite per successful branch.
- `hash_lb_compares` counts only comparator calls in `std::lower_bound`, not every relational comparison in the function.
- `hash_worst_scan` counts `deg` slots for each `recompute_worst()` call; `hash_worst_compares` counts `(deg-1)` comparisons (when `deg>0`).
- `collision_same_id` is a **lower bound** on repeated IDs reaching the hash-collision branch (not a count of all duplicates).
- `R86_COUNTERS=OFF` means the macro is **not defined**; CMake emits `R86_COUNTERS=1` only when the separate ON target is built. Header also handles `-DR86_COUNTERS=0` as OFF.
- `active_pass=0` denotes final RobustPrune and occupancy only; `pass>=1` means tree pass. Leaf post-merge depth is unknown and correctly recorded as JSON `null`.

## Files

- `R86_counter_source_v1_1.patch`: full patch for H70's exact snapshot.
- `R86_logger_importer.patch`: accepts leaf-size event `depth: null` in kit.
- `R86_logger_registry_v1_1.patch`: registers newly created metrics in kit parser.
- `cpp/r86_counters.hpp`: complete new header, already included by source patch.
- `kit_overlay/r86_log.py` and `kit_overlay/registry.py`: reference files after applying both logger patches, for review/diff.
- `R86_PASS1_INVARIANTS.json` and `tests/verify_event_stream.py`: 10K gate definitions.
- `tests/test_hash_work.py` and `tests/fixtures/merge_neighbors.inc`: standalone C++ stub using the **exact method text** from the v1.1 patch. ON/OFF state parity and mutually exclusive accounting tested with 305 merges including same-ID BF16 rewrite and different-ID collision.
- `R85_BUILD_PHASE_HISTORY_from_user_logs.csv`: **historical** 18 build-log excerpt records, never new R86 counter results.

## Read-only verification command (user's Ubuntu)

```bash
bash scripts/check_and_dry_run.sh \
  "$HOME/ann-task-a/experiments/H70/pipnn-clean-443a328" \
  "$HOME/ann-task-a/experiments/R86_logging_kit/ANN_R86_Logging_Kit_v1_2"
bash tests/run_static_tests.sh
```

These commands do not modify H70 or R85; the static tests compile a separate stub under a temporary directory. **The patch is not yet verified with PiPNN's native dependencies/build system.**

### After independent reviewer approval — not automatically executed

1. Stage a separate R86 source snapshot using B1's proven symlink-safe isolation procedure. Check source hashes and use exact H70 baseline; not instrumented B1 `pipnn.h`.
2. Apply the full source patch there, and both logger patches to a separate copy of the logging kit.
3. Build four binary configurations: Stock/H17 × counter OFF/ON, with TwoTier OFF.
4. For ON, pass distinct, previously nonexistent absolute paths in `R86_COUNTER_OUT`, `R86_LEAF_SIZE_OUT`, `R86_OCCUPANCY_OUT`.
5. Run OFF 100K same dataset/config as an available R85 baseline and check graph validity + edge counts + same-beam Recall within predeclared tolerances (not binary hash identity).
6. Run ON 10K on one thread; use `tests/verify_event_stream.py` with counter, leaf, occupancy files and the actual build log, then inspect graph validity.
7. Only after the native gate passes run the planned n sweep. ON build times are *not* performance results.
