"""Canonical v1.2 metrics and Google Sheets column contract. Python 3.9+ stdlib only."""
from __future__ import annotations

SCHEMA_VERSION = '1.2'
RECALL_TARGETS = [0.89, 0.96, 0.99, 0.998]
METRICS = {
    'W_P': ('logical_point_leader_pairs', 'Partition: sum |ids| * num_leaders'),
    'W_A': ('memberships', 'Partition: sum |ids| * fanout'),
    'W_L': ('matrix_entries', 'Leaf: sum leaf_size**2'),
    'W_pairs': ('unordered_pairs', 'Leaf: sum leaf_size*(leaf_size-1)//2'),
    'leaf_count': ('leaves', 'Number of executed leaf buckets'),
    'leaf_size_sum': ('point_occurrences', 'Sum of leaf sizes (with overlap)'),
    'max_depth': ('levels', 'Highest observed partition recursion depth'),
    'proposals': ('directed_proposals', 'Directed edges proposed by Pick'),
    'merge_attempts': ('events', 'Forward and reverse candidate merge attempts'),
    'collision_same_id': ('events', 'Hash collision and same current candidate ID'),
    'collision_diff_id': ('events', 'Hash collision but different ID'),
    'hash_accept': ('events', 'Accepted hash candidate updates'),
    'hash_reject': ('events', 'Rejected hash candidate updates'),
    'hash_replace': ('events', 'Replaced candidate slots'),
    'hash_early_break': ('events', 'Candidate ended before hash matching'),
    'hash_full': ('events', 'Full-capacity handling events'),
    'prune_distance_calls': ('distance_evaluations', 'Final RobustPrune distance calls'),
    'top2_comparisons': ('comparisons', 'Top-2 microbenchmark only'),
    'top2_assignments': ('assignments', 'Top-2 microbenchmark only; conventional swap=3'),
    'top2_moves': ('element_moves', 'Top-2 microbenchmark only'),
}
DIAGNOSTIC_METRICS = {
    'degree_p50': 'edges_per_node',
    'degree_p95': 'edges_per_node',
    'edge_jaccard': 'fraction',
    'weak_component_fraction': 'fraction',
    'strong_component_fraction': 'fraction',
    'entry_reachability': 'fraction',
    'co_leaf_coverage_at_k': 'fraction',
    'pick_retention_at_k': 'fraction',
    'duplicate_pair_rate': 'fraction',
    'reservoir_occupancy': 'fraction',
    'hash_eviction_count': 'events',
    'search_expansions': 'nodes_per_query',
    'search_visited': 'nodes_per_query',
    'search_hops': 'hops_per_query',
    'local_minima_failures': 'queries',
    'parallel_speedup': 'ratio',
    'parallel_efficiency': 'fraction',
    'work_span': 'model_units',
    'load_imbalance': 'ratio',
    'cpu_instructions': 'instructions',
    'cache_misses': 'events',
    'branch_misses': 'events',
    'memory_bandwidth': 'bytes_per_second',
    'page_faults': 'events',
    'energy_joules': 'J',
    'ssd_reads': 'read_operations',
    'ssd_bytes': 'bytes',
    'ssd_queue_depth': 'requests',
    'ssd_io_latency_us': 'microseconds',
    'bound_checks': 'evaluations',
    'exact_leader_distances_saved': 'logical_pairs',
    'false_prunes': 'events',
    'boundary_gap_f_f1': 'distance',
}

SHEET_HEADERS = {
    'RUN_INDEX': ['run_id', 'campaign', 'arm_id', 'n', 'dataset', 'graph_id', 'run_type', 'status', 'source_commit', 'binary_sha256', 'folder_or_uri', 'date_local', 'notes'],
    'A_SYSTEM': ['run_id', 'graph_id', 'arm_id', 'n', 'C', 'slot_bytes', 'storage_variant', 'build_rep', 'T_build_s', 'T_partition_s', 'T_leaf_s', 'T_prune_s', 'M_reservoir_model_B', 'M_alloc_B', 'peak_rss_KiB', 'index_bytes', 'measurement_status', 'notes'],
    'B_SEARCH': ['run_id', 'graph_id', 'arm_id', 'recall_target', 'recall_at10', 'recall_method', 'k', 'beam', 'latency_us', 'latency_p95_us', 'latency_p99_us', 'ndc_per_query', 'qps', 'qps_method', 'directed_arcs', 'degree_mean', 'degree_max', 'status', 'notes'],
    'C_WORK': ['run_id', 'graph_id', 'arm_id', 'n', 'pass_id', 'depth', 'metric_code', 'observed', 'unit', 'predicted', 'obs_to_pred', 'per_n', 'phase_time_s', 'ns_per_work', 'source_method', 'status', 'notes'],
    'D_DIAGNOSTICS': ['run_id', 'graph_id', 'arm_id', 'hypothesis_id', 'metric_code', 'value', 'unit', 'method', 'status', 'notes'],
    'E_PROTOCOL': ['run_id', 'graph_id', 'source_commit', 'source_diff_sha', 'binary_sha256', 'build_flags', 'dataset_id', 'base_sha256', 'queries_sha256', 'gt_sha256', 'n', 'd', 'k', 'C', 'K', 'N', 'R', 'h', 'threads', 'affinity', 'seed', 'random_source', 'rep', 'timed_or_instrumented', 'status', 'notes'],
}

ARM_SPEC = {
  'A0': {'label': 'Stock C160 K1024 N2', 'H17': False, 'TwoTier': False, 'C': 160, 'K': 1024, 'N': 2},
  'A1': {'label': 'H17 Flat C160 K1024 N2', 'H17': True, 'TwoTier': False, 'C': 160, 'K': 1024, 'N': 2},
  'A2': {'label': 'H17 Flat C64 K1024 N2', 'H17': True, 'TwoTier': False, 'C': 64, 'K': 1024, 'N': 2},
  'A3': {'label': 'H17 Flat C64 K512 N2', 'H17': True, 'TwoTier': False, 'C': 64, 'K': 512, 'N': 2},
  'A4': {'label': 'H17 Flat C64 K512 N1', 'H17': True, 'TwoTier': False, 'C': 64, 'K': 512, 'N': 1},
  'D0': {'label': 'H17 TwoTier C160 K1024 N2', 'H17': True, 'TwoTier': True, 'C': 160, 'K': 1024, 'N': 2},
}

SOURCE_SHA_HISTORY = {
  'H17_flat_binary': '8757b9be9fa3ae1f90febe082001fa60ba22c71ba6b6cdd899e013f6c0bcd500',
  'Stock_binary': 'e07853b3e1832e2d9a95d6ed8ed6660bf34bc719dffcfd78789f6f672c6a05a5',
  'TwoTier_binary': '5e4620d45c0d43c091038c3edac2b863983310b4e40a970943a307db87950d9b',
  'H70_pipnn_h': 'f4391ad8712d7757423dca872f9042c3271660dffde384a85b93854b9692f288',
  'H70_pipnn_utils_h': '7083e8183554a1cb586b70cdb4c57920f49ec5a50680096aecf6b873f596595d',
  'upstream_git_head': '443a328dc71a3b7be753d52ca2b3c9a4ba77f3fd',
}
