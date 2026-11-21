R91 G1 Stock OFF MS-Turing10M — ONE BUILD, historical Highway, 24 GiB / no swap.
Python SHA256: 84d1d7b5409f215667dbd7b92176ff8c3383cf17a4742bdbb42efebe98b95b63
1. Verify ZIP SHA, extract into ~/Downloads (unzip -n).
2. bash ~/Downloads/R91_G1STOCK_NATIVE_PREFLIGHT_v1_Ubuntu.sh
   Require R91_G1STOCK_PREFLIGHT_NATIVE_EXIT_CODE=0. No build in this phase.
3. bash ~/Downloads/R91_G1STOCK_ONE_BUILD_v1_Ubuntu.sh only after preflight PASS.
   Exactly ONE stock_off BUILD, CPU 0,2,4,6, C160 K1024 N2, original G1 actual GNU time CLI must match.
   New scope with memory.max 24 GiB and memory.swap.max 0. No search, no recompilation.
   Guards: >=26GiB available before launch, >=12GiB disk; abort on sustained host memory <2GiB, free disk <8GiB, OOM, swap, or 1h builder time. Monitor inside/outside scope, no auto retry.
   Full structural streaming audit on stock graph. Stage parser records missing timers as null; raw stdout retained.
4. Upload new preflight.json, stock_result.json, outside_scope_receipt.json, and native.time/stdout/stderr plus monitor TSV files (compress if desired). Also upload ~/R91_G1STOCK_ONE_BUILD_v1.log. If HOLD or no result, send available orphan logs and do not delete or rerun.
Paths under ~/ann-task-a/experiments/R91/r91_g1stock_native_preflight_v1 and r91_g1stock_one_stock_flat_c160_mst10m_24g_v1.
Native Ubuntu preflight/build not tested here. Synthetic graph and marker selftest only. One pilot is not replicated; structural PASS is not Search quality PASS. A cgroup OOM is a failure under the tested cap, not universal Stock failure.
