# Claude quick reviewer checklist — R86 v1.1

- [ ] Check CMake `R86_USE_COUNTERS` only emits `R86_COUNTERS=1` on ON; Flat graph only; no HashSetGraph/Tier ON accidental build.
- [ ] Confirm `LSHGraph::merge_neighbors` is unchanged for candidate insertion / replacement / ordering / worst logic, aside from counters and comparator's same `<` result.
- [ ] Confirm `r86::record_hash_work(work)` **after** `locks[i].Unlock()`, only once per merge; no thread-shared writes inside the lock.
- [ ] Validate `hash_moves` formulas against `std::move_backward` and `std::move`; compare `hash_lb_compares` to `Cmp` invocations.
- [ ] Validate the corrected outcomes partition when same-ID is not accept/reject, plus bf16 same-ID rewrite.
- [ ] Verify stock `Q.push_back` writes `s*(s-1)` and exactly `s` partial-sort invocations per executed leaf (MST_DEG==2); H17 branch zero.
- [ ] `ExportToGraph` occupancy scan must be BEFORE `graph.finalize`, and must only be enabled in ON. `R86_OCCUPANCY_OUT` required absolute new filename.
- [ ] Confirm SFINAE on occupancy avoids instantiating kMaxDegree/degree access for unsupported `GraphH` templates (no_reservoir path).
- [ ] Verify local RobustPrune distance counting increments just before the real vector `distance(...)`; flush once per node, OFF compiler guard.
- [ ] Check `leaf` counters / independent leaf dump both omit singleton buckets; any gap to `Total points` must be described.
- [ ] Verify `W_P` per depth sums to the **increment** in upstream cumulative `COMPARISONS` per pass, not its cumulative value for both passes.
- [ ] Counter/occ/leaf files always link by E_manifest run_id and graph_id; no timings from ON runs used in performance claims.
- [ ] Decide native build PASS/FAIL on Ubuntu only after reviewing actual output. Synthetic static tests are not a substitute.

**Open conceptual issue:** Colliding IDs at distinct hashes are impossible for same ID with the same hash function and fixed point center, but repeated proposal could have been evicted earlier. Report collision_same_id as observed lower bound, not full duplicate count. Infer R85 occupied slots under C160 carefully: 55 is integer-truncated, not exact histogram.
