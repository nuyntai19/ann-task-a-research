R91-G1B | MS-Turing10M | Search-only pinned fixed-beam screen v1
=================================================================

PURPOSE
- Preserve the existing native G1 Fast v2 Flat C160 graph and run only SEARCH.
- This is NOT a native BUILD of PiPNN Stock or H17, and not 10M speedup evidence.
- Frozen graph: MSTuring10M_fast_off_C160_K1024_N2.graph.
- SHA256 graph: 4055dedc2ccb3b6406fed45ed28de2ec57c46fe2b085b5046ae13cd943702429
- Frozen original G1 result JSON SHA bd46f8327e634e05ebdf3975c602d3c069df749be8dc3a6e140f286a606e3835
- Frozen G07 preflight JSON SHA 70e9f33fa933b791f45e3254185b0374b129b6c4297a0e469c7d3ae02f38b8b0
- Original R86 v4 highbeam evaluator SHA bb6576ad3e1e0cc770535aa06355c664993ca70bd1170d6dd4d202ab5767e144
- Python runner SHA 3566fc7e04d0b8833c3fed07fdd0a2612ecc7612223b7e43781f594a5e9223b5

CRITICAL LIMITATION
- The R86 evaluator is named MS-Turing1M, and 10M runtime compatibility has
  NOT yet been empirically established. Its stdout MUST contain precisely
  graph_nodes=10000000 queries=100000 gt_k=100. If it does not, HOLD: do not
  modify the original data, graph, or binary and do not silently switch evaluators.
- Beams 384/896 are a first screen only; Recall target .990/.998 is NOT
  assumed. A follow-on larger beam grid is needed if either target is not met.
- Legacy evaluator avg_cmps can overflow at high beams: excluded, QPS is not
  p95 or p99. Same query set used in preliminary screen; not a final
  statistical noninferiority protocol.

UNZIP
  unzip -n "$HOME/Downloads/R91_G1B_FASTV2_MST10M_SEARCH_v1_1_BUNDLE.zip" -d "$HOME/Downloads"

STEP 1: preflight, read original source/data & isolated 24GiB no-swap scope.
  bash "$HOME/Downloads/R91_G1B_FASTV2_MST10M_SEARCH_PREFLIGHT_v1_Ubuntu.sh"
Expected status R91_G1B_SEARCH_PREFLIGHT_NO_BUILD_NO_SEARCH_PASS.
No old files changed. New preflight JSON only.

STEP 2: only when Step1 PASS; run one 100Kq evaluator process at beams384,896.
  bash "$HOME/Downloads/R91_G1B_FASTV2_MST10M_SEARCH_RUN_v1_Ubuntu.sh"
Expected status R91_G1B_NATIVE_SINGLE10M_GRAPH_SEARCH_SCREEN_AUDIT_PASS_NO_BUILD.
If HOLD, inspect logs and preserve orphan outputs. DO NOT automatically rerun.

STEP 3: read-only standalone re-audit (optional)
  bash "$HOME/Downloads/R91_G1B_FASTV2_MST10M_SEARCH_AUDIT_v1_Ubuntu.sh"

Upload files for next step:
  ~/ann-task-a/experiments/R91/r91_g1b_mst10m_fastv2_search_preflight_v1/r91_g1b_preflight.json
  ~/ann-task-a/experiments/R91/r91_g1b_mst10m_fastv2_search_screen_v1/quality_screen_summary.json
  ~/R91_G1B_FASTV2_MST10M_SEARCH_RUN_v1.log
  [If HOLD] native_fixedbeam.stdout/.stderr in the new R91 output logs

Systemd memory.max = 25769803776 bytes, memory.swap.max = 0, 1CPU(0)
No BUILD, source-code patch, graph file write, or new ANN graph involved.
