# Metric Contract v1.2 (đối chiếu Google Sheet)

Sheet: https://docs.google.com/spreadsheets/d/12ApqgMV8YykflyFXUT2VMbUhgyiGirtoOmRWCXCz3Ek/edit

## A System and Memory
`T_build_s`, `T_partition_s`, `T_leaf_s`, `T_prune_s`, `M_reservoir_model_B`, `M_alloc_B`, `peak_rss_KiB`, `index_bytes`. Data đo: wall/RSS do `/usr/bin/time`, index size qua stat. Data tính: `n*(C+1)*sizeof(slot)` chỉ khi FLAT và sizeof thực được xác nhận. TwoTier cần model khác.

## B Search
4 recall targets `0.89`, `0.96`, `0.99`, `0.998`; `recall_at10`, `latency_us`, `latency_p95_us`, `latency_p99_us`, `ndc_per_query`, `qps`, `qps_method`, `directed_arcs`, `degree_mean`, `degree_max`. `COMPARISONS` trong cluster builder KHÔNG là evaluator NDC.

## C Work
`W_P`, `W_A`, `W_L`, `W_pairs`, `leaf_count`, `leaf_size_sum`, `max_depth`, `proposals`, `merge_attempts`, `collision_same_id`, `collision_diff_id`, `hash_accept`, `hash_reject`, `hash_replace`, `hash_early_break`, `hash_full`, `prune_distance_calls`, `top2_comparisons`, `top2_assignments`, `top2_moves`. Each counter has `observed`, `predicted`, `per_n`, `obs_to_pred`, `phase_time_s`, `ns_per_work`, `pass_id`, `depth`.

Leaf histogram: separate `leaf_histogram`, populated only if leaf-size records are actually produced by instrumentation; don't guess histogram from `W_L` alone. Top2 operation counts use independent microbenchmark only.

## D Diagnostics
Topology, candidate coverage, search trace, parallelism/work-span, cache/page faults, memory bandwidth, SSD/IO, geometric pruning bounds. Only populate if a named test is performed; all others `NOT_MEASURED`.

## E Protocol & Reliability
Source commit/dirty SHA, binary SHA, dataset/query/GT SHA, build flags, seed and true random source, number of threads/affinity, independent rep, graph SHA, status. Median/min-max/IQR are not properties of **one** run: aggregate several independent runs before reporting them. A single instrumented run is descriptive and has no meaningful confidence interval.

## Invariants
- No replacing unmeasured values by zero.
- One `run_id` and `graph_id` per result bundle. Reuse `graph_id` to link same graph's SEARCH results; use separate `run_id` when measurement protocol changes.
- Use paired comparisons within same dataset and comparable protocols. Don't combine SIFT1M H17-B160 with BIGANN1M SCALE1 for a controlled effect of C.
- Computational complexity claims require code analysis; plots across n are empirical support only.
- Source path and binary SHA are complementary. Different binary SHA from build paths need not mean different algorithm; equal binary SHA says nothing about inputs/flags supplied during execution.
