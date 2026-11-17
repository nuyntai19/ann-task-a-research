# Claude follow-up review — R86 v1.2

Claude approved native build for v1.1 and requested (1) restore original comments/formatting, (2) fail loudly for unsupported occupancy graphs, (3) P1/P2 occupancy and optional per-node degree arrays, plus G0 source OFF equivalence.

## Implemented; please re-check

- [ ] `graph.h` original comments and whitespace remain unchanged outside R86 branches. Confirm G0 OFF projection exactly matches known H70 SHA (`graph.h` 17e51779…, `pipnn.h` f4391ad8…, `pipnn_utils.h` 7083e818…). The CMake configuration is explicitly different and not part of the code OFF-projection equality claim.
- [ ] ON `emit_reservoir_occupancy` with unsupported `GraphH`: runtime error, not silent skip. OFF stub accepts a `pass_id` argument. No accidental native template compile failures for HashSetGraph path.
- [ ] `require_output_paths` creates a fresh empty occupancy JSONL before pass1; per-pass append produces P1, P2, ..., then pass0. File is not overwritten between passes. The source refuses paths that already exist at startup.
- [ ] Optional `R86_DEGREES_PREFIX` produces `*_pass1.u32le`/`*_pass2.u32le`; inspect data layout and correctness at n=10K, then 1M.
- [ ] `tests/verify_event_stream.py` checks all occupancy snapshots and the optional node-degree array with exact node histograms.
- [ ] Inspect the pre-prune/post-pass scanning overhead; ON time must never be compared against OFF time.
- [ ] Check current `merge_attempts=2*proposals` and `accept/reject/same_id` invariants against a *real* 10K build; synthetic parity is necessary, not sufficient.
- [ ] Confirm patch only touches isolated R86 source; native CMake `stock_off/on`, `h17_off/on` produce correct binary and source provenance.

**Important:** In v1.2 the new JSONL occupancy file is intentionally incompatible with v1.1 `json.load(single occupancy)`; use the included v1.2 gate script for R86 runs. Please note any additional blocker before native G1/G2/G3.
