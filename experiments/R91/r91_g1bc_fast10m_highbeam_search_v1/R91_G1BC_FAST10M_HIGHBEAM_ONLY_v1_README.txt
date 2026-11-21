R91-G1B-C / FAST V2 MS-TURING10M / HIGH-BEAM SEARCH-ONLY / v1
2026-11-21

PURPOSE
 Continue existing native Fast v2 G1B v2 10M Search at NEW beams 1792 and 2048.
 Old beam1536 Recall=.99774402 did NOT meet .998. There is no ANN graph BUILD,
 no change to original R86, R90, R91 G1 or G1B v1/v2 artifacts, and no Stock10M BUILD.

PINNED ORIGINALS
 Fast v2 10M graph SHA 4055dedc2ccb3b6406fed45ed28de2ec57c46fe2b085b5046ae13cd943702429
 Compiled 10M evaluator ELF SHA 394c6564750722001897254939ba4895e0d7ae6a6dbab44748c30937ea0413c9
 Previous G1B v2 Search summary SHA 960295996dc176dc6d1bb5074ff0543e96f43cba06907b5142c44be8949a44eb
 Previous G1B v2 preflight SHA ec040c05b3984c81cab38aeae85145d19391833a27ad4a0eb1f186d3f77b2b7c
 Previous evaluator receipt SHA 79373da654e102c9a115eb63bd1aca7937f1349d4a289c181bd9befd27b69f62
 NEW Python script SHA cdf8d779b5bc1a631d23759c7ee8ad0ea8b55f779ef81b72e7cca45b2f5de2f5

GUARDS
 Single-graph read-only Search: beams 1792,2048, public 100K GT100; CPU0.
 systemd-run --user --scope with actual inside-scope verification:
 memory.max=25769803776 (24 GiB), memory.swap.max=0.
 Source/graph/data SHA pinned, output roots unique, no overwrite.
 On any failure preserve logs; NEVER rerun old or current one-shot blindly.

STEP1: EXTRACT EXACT BUNDLE INTO ~/Downloads
 unzip -n "$HOME/Downloads/R91_G1BC_FAST10M_HIGHBEAM_ONLY_v1_BUNDLE.zip" -d "$HOME/Downloads"
 sha256sum "$HOME/Downloads/r91_g1bc_fast10m_highbeam_only_v1.py"

STEP2: SELFTEST + PREFLIGHT (NO SEARCH)
 bash "$HOME/Downloads/R91_G1BC_SELFTEST_PREFLIGHT_v1_Ubuntu.sh"
 Require R91_G1BC_PREFLIGHT_NATIVE_EXIT_CODE=0.

STEP3: SEARCH (ONLY IF STEP2 EXIT0; DO NOT RERUN)
 bash "$HOME/Downloads/R91_G1BC_RUN_SEARCH_v1_Ubuntu.sh"
 Require R91_G1BC_SEARCH_AUDIT_NATIVE_EXIT_CODE=0.

IF A RUN FAILS
 DO NOT RERUN. Preserve:
 ~/ann-task-a/experiments/R91/r91_g1bc_fast10m_highbeam_search_v1/
 Send original log, summary JSON, stdout/stderr/time as appropriate.

EXPECTED NEW ARTIFACTS
 experiments/R91/r91_g1bc_fast10m_highbeam_preflight_v1/preflight.json
 experiments/R91/r91_g1bc_fast10m_highbeam_search_v1/quality_screen_summary.json
 experiments/R91/r91_g1bc_fast10m_highbeam_search_v1/logs/native_highbeam.stdout
 experiments/R91/r91_g1bc_fast10m_highbeam_search_v1/logs/native_highbeam.stderr
 experiments/R91/r91_g1bc_fast10m_highbeam_search_v1/logs/native_highbeam.time

Local Python/Bash selftest, bytecode compile, syntax, missing HOME negative gate have
passed. Native Ubuntu preflight and Search are NOT YET RUN for this new script.
This newly authored runner is not a certified replica of prior G1B v2 runner:
if filesystem layout differs, HOLD rather than bypassing SHA/source checks.
