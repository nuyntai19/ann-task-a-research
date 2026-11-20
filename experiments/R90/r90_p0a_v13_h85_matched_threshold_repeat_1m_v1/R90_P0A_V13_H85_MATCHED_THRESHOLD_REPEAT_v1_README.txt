R90 P0A v1.3 H85 historical Highway 6bc2d477: THRESHOLD-QUALIFIED REPEATED QPS v1
SHA-pinned SEARCH ONLY, no new graph BUILD, no source compilation, no mutation of historical evidence.

INPUTS (ALL MUST MATCH EXACT NATIVE SHA):
  - Existing /home/tai/ann-task-a/experiments/R90/r90_p0a_v13_h85_24build_native_v1/ 18 OFF graphs.
  - Existing fixed-beam v1.3 18graph Search screen outputs.
  - Original screen script ~/Downloads/r90_p0a_v13_h85_18graph_search_screen_v1.py (SHA dcfe8d6f856b37ca149ee4a00b257f2af11d7ef757a24d99859634633c2191a6).
  - Existing H85 dynamic SIFT evaluator ~/ann-task-a/experiments/H85/r85_a1c_matched_search/r85_a1c_graph_recall (SHA 11587916ffd70143d6d5246bf8d2e26c1927b81bf8b3298fbc2014bfb6c64a4e) and its evaluator_manifest.json.
  - Existing MS-Turing1M native evaluator r86_msturing1m_graph_recall_v4_highbeam.
  - Original pinned 10KQ/100KQ query and GT files, graph audit and Build manifest.

DESIGN:
  CALIBRATION: all 18 existing OFF graphs, SIFT beams [64,68,72,76,80,128,136,144,152,160], MS beams [336,352,368,384,832,848,864,880,896]. One evaluator call per graph (18 calls).
  Check SIFT anchor Recall beam 80 and160 against original r72 screen (within 0.0001), MS anchor beam384 and896 (within 0.000001). If incompatible dynamic evaluator, HOLD rather than mixing semantics.
  Select per dataset+arm+target the MINIMUM TESTED beam where all 3 distinct OFF graph realizations reach Recall@10>=.99 or>=.998, NOT exact equal Recall.
  TIMING: 3 repeated native single-core evaluator processes per graph, 18 graphs => 54 processes. Each process evaluates BOTH selected beams; 108 target-metric observations. Rotate arm order across repeats. Uses same query/GT as calibration; not an independent generalization estimate.
  MS legacy high-beam avg_cmps is INVALID/OVERFLOW and never included in comparisons.
  Audit each receipt's raw stdout/stderr SHA and parser; graph bytes remain unmodified. Non-overwriting JSON receipts and unique logs.

FIRST RUN AFTER DOWNLOADING ZIP TO ~/Downloads:
 unzip -n "$HOME/Downloads/R90_P0A_V13_H85_MATCHED_THRESHOLD_REPEAT_v1_BUNDLE.zip" -d "$HOME/Downloads"
 bash "$HOME/Downloads/R90_P0A_V13_H85_MATCHED_THRESHOLD_REPEAT_v1_Ubuntu.sh"

ONLY IF A PARTIAL RUN IS VERIFIED SAFE TO RESUME:
 bash "$HOME/Downloads/R90_P0A_V13_H85_MATCHED_THRESHOLD_REPEAT_v1_RESUME_Ubuntu.sh"

NEW OUTPUT ROOT (historical files preserved):
 ~/ann-task-a/experiments/R90/r90_p0a_v13_h85_matched_threshold_repeat_1m_v1/
 Main files: preregister.json, calibration_manifest.json, selected_threshold_beams.json, timing_manifest.json, threshold_matched_qps_summary.json.
 New terminal log: ~/R90_P0A_V13_H85_MATCHED_THRESHOLD_REPEAT_v1.log

SCIENTIFIC LIMITS:
 - Per-target qualified thresholds vs exact equal-Recall differ. Report actual achieved Recall separately.
 - Calibration and timing on the same query/GT; no independent test split.
 - 3 builds x 3 timing repeats are nested observations; cannot treat nine as nine independent graph samples.
 - QPS or 1e6/QPS is NOT a measured p95/p99 query latency distribution; no formal noninferiority test here.
 - If any pinned dependency missing or SHA differs, stop/HOLD. Do not rebuild or overwrite anything to bypass.

RUNNER SCRIPT SHA256: aecf431e4768d868a74b7c0562de4d87cba4ef44c4619c8d88dec63e1414f959
