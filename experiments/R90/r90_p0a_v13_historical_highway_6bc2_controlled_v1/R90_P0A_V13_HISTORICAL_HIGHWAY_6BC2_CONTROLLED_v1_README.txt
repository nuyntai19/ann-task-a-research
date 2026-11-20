R90 P0A v1.3 — Historical Highway 6bc2d477 controlled rebuild
20 Nov 2026 | research evidence isolation | no GitHub writes

RATIONALE
  Native read-only v0 report, SHA256 7562055b2a548c67c4831570ae1923918fbafa762a25c4cb5b0230d4264e7d50,
  verified H85 Highway old Sort2 Compare+IfThenElse vs R86 new mirrored First/Last,
  and SIFT1M Stock v0 degree64 with neither neighbor2 nor6, versus H17/Fast
  containing both. Synthetic native Highway probe showed FTZ/DAZ can mutate
  packed-key bits. This is strong confounding evidence, but historical
  single-edge causation is not yet directly isolated.

DESIGN
  Only change from v1.1 one-snapshot six-source package: offline
  FetchContent Highway root uses preexisting H85 checkout at Git commit
  6bc2d477... instead of R86 0e0a01da... . Exact 6 variant source tree SHAs
  copied preserving two allowed ParlayANN relative symlinks; compiler SHA
  and -O3/-march=native/-ffast-math retained; same Canonical flags
  C160,K1024,MST_DEG2 and prune64. Source and binary are recompiled only
  in an entirely NEW isolated v1.3 output directory. Nothing touches
  P0A v1.1/v1.2 files or H85 baseline results. Exiting on partial evidence
  is deliberate; never rm -rf, delete old logs or 'repair' receipts.

ONE-TIME UNZIP
  unzip -n ~/Downloads/R90_P0A_V13_HISTORICAL_HIGHWAY_6BC2_CONTROLLED_v1_BUNDLE.zip -d ~/Downloads

STAGE A — RUN FIRST (NO 1M)
  bash ~/Downloads/R90_P0A_V13_STAGEA_6ELF_OLD_HIGHWAY_PILOT_Ubuntu.sh
  Read/write exclusively under
    ~/ann-task-a/experiments/R90/r90_p0a_v13_historical_highway_6bc2_controlled_v1/
  + new Stage A log ~/R90_P0A_V13_H85_HIGHWAY_STAGEA_6ELF_PILOT.log
  In order: local SHA selftest -> source/blob/Git HEAD preflight -> copy6
  source trees -> CMake offline compile6 ELFs -> check CMake cache and
  compile_commands each used old Highway and -ffast-math -> compile original
  126-case tiny C++ probe against actual new H85 Highway archives ->
  check single-zero packed-key preservation at n32/64/189/512 ->
  6 independent SIFT10K BUILD (3 OFF+3 ON), all graph ID/selfloop/duplicate
  checks -> Stage A audit. No global cross-arm graph SHA parity requirement.
  Output records: source_manifest, experiment_preregister, compile_manifest,
  compile_provenance_audit, probe_report, pilot_manifest, stageA_audit,
  v12_screen_metadata_errata (new file only).
  Expected successful terminal:
    R90_P0A_V13_H85HWY_STAGEA_AUDIT_PASS_6_H85_HIGHWAY_ELF_126_PROBE_6_10K_GRAPH_NO_1M
    R90_P0A_V13_STAGEA_EXIT_CODE=0
    TERMINAL_SAFE_END
  IMPORTANT: local selftest PASS is not native proof; the old Highway
  may still mutate synthetic two-value edge cases. If 24 targeted single-zero
  n>=32 cases lose index bits, Stage A HOLDS for review, NOT an automatic
  assertion that all Highway outputs are universally safe.

STAGE B — SEPARATE, ONLY AFTER STAGE A PASS and evidence review
  bash ~/Downloads/R90_P0A_V13_STAGEB_ONE_STOCK_SIFT1M_QUALITY_Ubuntu.sh
  BUILD exactly ONE Stock SIFT1M OFF graph (4 CPU 0,2,4,6).
  Audit whole graph: 1M degrees, all neighbor IDs, selfloops, duplicate slots;
  check vertex0 includes2,6 with degree below64, find exact duplicate
  SIFT1M vectors by BLAKE2b16+byte confirmation, count exact duplicate-pair
  graph retention; first10K large first/second L2 inversions are diagnostic,
  not hard correctness gate; run pinned native R72 10K-query Search and
  require >=0.99 Recall@10 beam80 and >=0.998 at beam160.
  Stock graph and Search output are stored in NEW v1.3 directory.
  Output: stageB_stock_sift1m_quality.json and B log.
  Stage B is NOT a 24-build 1M experiment, NOT a claim of exact
  matched Recall/noninferiority, and NOT authorization for 10M.

INTERPRETATION
  - The older Highway may preserve a single packed zero-distance key
    under AVX2 where the newer revision zeroes it; two subnormal keys
    under DAZ may still tie, including in H17/Fast.
  - Stage1 VQPartialSort is common to all three branches; graph SHA can
    vary even with same aggregate bucket counts. Compare recall and
    graph structure, NOT all-arm byte-identical graph SHA.
  - The v1.2 original search summary wrongly stores SIFT beam grid as
    [384,896]. New v13 v12_screen_metadata_errata.json gives the correct
    [10,20,40,80,160] without modifying original JSON or native Recall.
  - Historical source code, highway commit, compiler, flags and data must
    remain independently pinned. Performance and 1M quality require further
    same-source same-compiler repetitions after Stage B quality passes.

MANUAL SHA GATE
  Both Ubuntu scripts check Python and C++ SHA256 before any execution.
  Expected Python SHA:
    52805e517a8534732f0cbb6aeac374afc71dcbb88afc53aae0d7a4d624d9e5dc
  C++ SHA:
    93275ee4d3d273caf2864b523986097b7631b5bdd1c9f710a1f3563ed17caebb

If a CMake configuration cannot use the exact historical H85 old Highway,
if git HEAD is missing/mismatched, if an archive or source is modified, or
if the probe/graph quality fails, STOP. Do not alter historical artifacts.
