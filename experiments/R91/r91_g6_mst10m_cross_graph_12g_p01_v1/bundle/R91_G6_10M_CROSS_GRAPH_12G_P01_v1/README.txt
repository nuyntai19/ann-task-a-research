R91 G6 MS-Turing10M Cross-Graph Quality 12G / P01 only
Frozen 6-pair aggregate and 12 original graph + receipt SHA pins.
Preflight checks all 12 graphs and input bytes, no native Search.
Pilot only C512 -> C64 on p01, four beams 544,576,1728,1792, 100K queries,
unchanged exactguard, CPU0, one thread, 24GiB memory.max, swap.max=0.
No BUILD/compile or writes to source graphs. New output:
~/ann-task-a/experiments/R91/r91_g6_mst10m_cross_graph_12g_p01_v1
Preflight requires absent output; no automatic retry on HOLD.
Each arm has separate scope, exclusive output and preregistration.
Pilot wrapper then audit wrapper; read-only audit optional. Preserve output on HOLD.
Quality floor misses are reported, not hidden or rejected. Same beam not exact matched Recall;
no extrapolation or matched Recall estimates in this four-point screen. No p95/p99.
Only P01 native slots executed; 10 remaining graph slots intentionally not implemented in this pilot.
Local selftest synthetic, not real native Search. Original vendor calibration runner preserved verbatim;
only its helper functions reused and four-beam parser grid set in new runner.
