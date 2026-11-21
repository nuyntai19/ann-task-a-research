R91-G1M-D: 10M, 3-round interleaved paired QPS pilot, Stock vs Fast v2
Date 2026-11-21, bundle version v1

SCOPE: Same 10M Stock & Fast v2 graphs, H85/evaluator exactguard; 100K public queries;
new per-beam Search ONLY. No BUILD or compilation. Same CPU core0, 1 thread,
24GiB hard cgroup cap and 0 cgroup swap, verified inside each child scope.

Pre-registered threshold operating points from verified G1M-A:
  beam576: both Recall >=0.990, smallest TESTED qualifying beam (b512 fails).
  beam1792: both Recall >=0.998, smallest TESTED qualifying beam (b1664 fails).
These are threshold-matched beams, NOT exactly equal Recall.

3 rounds x 2 beams x 2 arms =12 independent native evaluator processes.
Order is interleaved and reversed across rounds; three pairs Stock-first and
three Fast-first overall. This 3-round pilot cannot perfectly counterbalance
order *within each beam* (uneven number of pairs). Do not claim formal
noninferiority or an unbiased causal Search speedup solely from this pilot.

Requires prior G1M-A native preflight and both arm receipts; SHA all pinned.
Each run has new scope+GNU time, raw stdout/stderr and receipt JSON;
abort on OOM/swap/invalid Recall or any SHA/source drift, never overwrite.

Files:
  ~/Downloads/r91_g1md_paired_qps_10m_v1.py
  ~/Downloads/R91_G1MD_PREFLIGHT_v1_Ubuntu.sh
  ~/Downloads/R91_G1MD_RUN_v1_Ubuntu.sh
  ~/Downloads/R91_G1MD_AUDIT_v1_Ubuntu.sh

Script SHA256 f25edb81d6c8dfbbaf90872d5fd184501e31df39cdc546d06f334d8d375bf397

1. unzip -n R91_G1MD_PAIRED_QPS_10M_v1_BUNDLE.zip -d ~/Downloads
2. bash ~/Downloads/R91_G1MD_PREFLIGHT_v1_Ubuntu.sh
   Require R91_G1MD_PREFLIGHT_NATIVE_EXIT_CODE=0.
3. bash ~/Downloads/R91_G1MD_RUN_v1_Ubuntu.sh
   Require R91_G1MD_RUN_NATIVE_EXIT_CODE=0 and read-only audit PASS.

New receipts:
  ~/ann-task-a/experiments/R91/r91_g1md_paired_qps_preflight_v1/preflight.json
  ~/ann-task-a/experiments/R91/r91_g1md_paired_qps_v1/paired_qps_summary.json
  ~/ann-task-a/experiments/R91/r91_g1md_paired_qps_v1/runs/r1_b576_stock/receipt.json
  ... /r1_b576_fast, /r1_b1792_fast, /r1_b1792_stock, etc.

If a run HOLDs, preserve ALL folders and do not rerun any original one-shot.
Call read-only audit separately only after complete native RUN success.

Local tests: only synthetic selftest, Python syntax, shell syntax and archive
integrity. No Ubuntu native preflight or Search has run in bundle build context.
