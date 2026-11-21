R91 G1-STOCK SEARCH ONLY: MS-Turing10M, six fixed beams, v1
2026-11-21

Existing stock graph: 6beda1aa823a49ca928e6046f411a4b6945d2eb56e125d85a50e30c8ab3deffe
Existing evaluator: 394c6564750722001897254939ba4895e0d7ae6a6dbab44748c30937ea0413c9
Python SHA256: 6fe8bdd5fb8ae59c6b48aeb429bf4dd2a2aae4086862460962f6f7248d9da717

NO ANN BUILD, no native recompile, no prior output writes or deletion.
Beams 384,896,1024,1536,1792,2048; 100K queries, GT100, recall@10.
CPU0, PARLAY_NUM_THREADS=1, LC_ALL=C (GNU time parsing), existing evaluator.
Actual systemd user scope memory.max=24GiB and memory.swap.max=0 verified.
Read-only SHA checks include both stock and fast graphs, stock receipts, both
Fast Search summaries, evaluator receipt/ELF, base/query/GT. New outputs only.
Preflight minimum available RAM 12GiB, disk 8GiB. Native evaluator timeout 7200s.
Cgroup accounting includes input file cache and runner, not just native RSS.

1. Extract ZIP to ~/Downloads (unzip -n). Verify ZIP SHA against release message.
2. bash ~/Downloads/R91_G1STOCK_SEARCH_PREFLIGHT_v1_Ubuntu.sh
   Require R91_G1STOCK_SEARCH_PREFLIGHT_NATIVE_EXIT_CODE=0.
3. bash ~/Downloads/R91_G1STOCK_SEARCH_RUN_v1_Ubuntu.sh
   Require R91_G1STOCK_SEARCH_RUN_AUDIT_NATIVE_EXIT_CODE=0.
   A successful native screen does not require reaching either Recall floor.
4. Read-only audit, optional:
   bash ~/Downloads/R91_G1STOCK_SEARCH_AUDIT_v1_Ubuntu.sh

Send artifacts:
~/ann-task-a/experiments/R91/r91_g1stock_search_10m_sixbeam_preflight_v1/preflight.json
~/ann-task-a/experiments/R91/r91_g1stock_search_10m_sixbeam_v1/quality_screen_summary.json
~/ann-task-a/experiments/R91/r91_g1stock_search_10m_sixbeam_v1/logs/native.{stdout,stderr,time}
If HOLD, preserve directories/logs and report exact terminal output, do not rerun
or delete the existing outputs. If preflight did not pass, do not run Search.

This is a fixed-beam screen, one measurement per beam. Neither equal beam nor
threshold crossing proves exact matched recall. Legacy avg_cmps is null;
1e6/QPS is a throughput-derived proxy, not p95/p99 or actual latency.
Local tests are synthetic only; native Ubuntu preflight/Search NOT executed.
