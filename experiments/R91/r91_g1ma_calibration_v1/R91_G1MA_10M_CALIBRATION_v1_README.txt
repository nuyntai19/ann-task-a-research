R91 G1M-A calibration v1 | NO ANN BUILD | 2026-11-21
Two immutable MS-Turing10M graphs, 100K queries, CPU0, 24GiB/no-swap.
Stock then Fast v2, one native evaluator invocation per arm with beams 512,576,640,1664. Separate cgroup scopes. QPS is screening only, not paired timing. Prior 6-beam receipts plus both graph hashes, evaluator, base/query/GT and original build receipts are pinned. No mutation of historic results. OMP_NUM_THREADS=1 and PARLAY_NUM_THREADS=1 for both arms. Legacy avg_cmps excluded. No automatic next stage or extra search. Threshold brackets describe tested grid only, not a global minimum; nonmonotonic observations are flagged.
Runner SHA256: 2f64af73c6969ae9c7233fa57b586a0238fb004cea1d22a7d0727060d4c4d59e
1. unzip -n into ~/Downloads. Run R91_G1MA_PREFLIGHT_v1_Ubuntu.sh; require exit0.
2. Run R91_G1MA_RUN_v1_Ubuntu.sh only after preflight PASS; require exit0.
3. Send original preflight.json, calibration_summary.json, both arm receipt.json and both native.stdout/native.time. Preserve stderr and any HOLD logs. Never delete/reuse a failed output directory.
Output: ~/ann-task-a/experiments/R91/r91_g1ma_calibration_v1/{stock,fast}/ and calibration_summary.json; preflight at ~/ann-task-a/experiments/R91/r91_g1ma_calibration_preflight_v1/preflight.json.
Optional read-only audit after success: R91_G1MA_AUDIT_v1_Ubuntu.sh. Does not execute evaluator.
Local synthetic selftest and script/ZIP validation only. Native Ubuntu not tested here.
