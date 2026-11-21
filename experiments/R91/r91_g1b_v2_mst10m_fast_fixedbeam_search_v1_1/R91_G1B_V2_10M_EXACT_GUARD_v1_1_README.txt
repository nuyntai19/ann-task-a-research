R91-G1B v2 MS-Turing10M Fast v2 EXISTING GRAPH Search-only
==========================================================
SOURCE FIX (narrow): R86 eval v4 SHA256 6aa0e38a3b0a536ccbcd3bfe0ca690257ab963215b5135d642cbb60d259c3f89
original guard: base.size() != 1000000 || base.dimension() != 100 ||
modified guard: base.size() != 10000000 || base.dimension() != 100 ||

NEW patched source expected SHA256 c851ec10cdc673eb2ef7237340c95a035656cad890f94b03df87b3595390baef
The script will extract ORIGINAL compile_command from R86 pinned manifest
SHA256 8f6b9b87f8bcf0e1651cf2b8a168526c8e8d56175224bbeda534431be57e4f22,
substitute exactly source and output paths into new R91 directory, re-use
ALL original compiler flags, include directories, linked libraries, and compiler.
It never builds an ANN graph or overwrites a previous R86/R90/R91 artifact.

G1B v1 HOLD reason is proven from source: original R86 v4 check hardcoded
base.size()!=1000000. Native log showed R72_RECALL_INPUT_MISMATCH rc3 after
loading valid 10M graph and data, with cgroup OOM=0 / swap=0.

REQUIRED Ubuntu path: /home/tai (the original v4 manifest embeds absolute paths)
REQUIRED intact R86 original .cc, original highbeam v4 manifest & ELF; full
R86 CMake deps/static .a libraries referenced by original compile_command.
REQUIRED intact MS-Turing10M data/100Kquery/GT, G1 original frozen graph,
G07 original report, G1B old preflight and old HOLD quality summary.

INSTRUCTIONS (do not skip steps)
1. unzip -n ~/Downloads/R91_G1B_V2_MST10M_EXACT_GUARD_v1_1_BUNDLE.zip -d ~/Downloads
2. bash ~/Downloads/R91_G1B_V2_V11_PREPARE_EVALUATOR_10M_Ubuntu.sh
   Creates NEW R91 .cc, patched diff, new binary, compile receipts. It verifies
   source SHA, manifest SHA, binary source chain, exact 1-line diff, rebuild
   command and ELF usage. Does NOT Search or ANN BUILD.
3. bash ~/Downloads/R91_G1B_V2_V11_PREFLIGHT_10M_Ubuntu.sh
   Pins all original G1/G07/H85 assets, graph SHA, data/GT ID bounds, new
   compiled evaluator SHA. Checks 24GiB/no-swap cgroup. Does NOT Search.
4. bash ~/Downloads/R91_G1B_V2_V11_RUN_SEARCH_10M_Ubuntu.sh
   One existing graph only, single core 0, 100K public queries, beams
   [384,896,1024,1536]. Hard 24GiB/zero-swap cgroup, no BUILD, no graph edits.
   1 native evaluator process. Retains logs on any failure.

NEW output roots (will HOLD if any already exists):
~/ann-task-a/experiments/R91/r91_g1b_v2_native_eval_mst10m_exactguard_v1_1/
~/ann-task-a/experiments/R91/r91_g1b_v2_mst10m_fast_preflight_v1_1/
~/ann-task-a/experiments/R91/r91_g1b_v2_mst10m_fast_fixedbeam_search_v1_1/

If prepare fails, DO NOT run preflight/Search. Inspect compile.stderr and
new eval_build_receipt.json. Do not edit original R86 source or skip SHA gates.
If preflight fails, DO NOT run Search. If Search fails, DO NOT rerun old
one-shot command; preserve original stdout/stderr/time and report.

After running: upload three JSON artifacts:
- eval_build_receipt.json
- r91_g1b_v2_preflight.json
- quality_screen_summary.json
and log ~/R91_G1B_V2_RUN_SEARCH_10M.log.

SCIENTIFIC LIMITATIONS
- This is an exact one-guard source adaptation, not a new ANN algorithm.
- 10M Search Recall/QPS not yet measured until native run completes.
- Beam grid may or may not meet .990 and .998. No exact matched-Recall
  equivalence or formal noninferiority from fixed-beam screening.
- Legacy R86 avg_cmps may overflow. Do not report it as reliable NDC.
- Throughput reciprocal is NOT per-query p95/p99.
- PiPNN Stock 10M has NOT been built; no 10M speedup claim.

CRITICAL: use this v1.1 bundle, NOT the superseded first ZIP!
The superseded local draft had an incorrect byte count in a graph-degree
preflight reader, caught before native use. v1.1 reads EXACTLY 10M uint32
degree words and has a boundary regression fixture. Distinct file names/paths
protect even if an old ZIP had already been extracted.
