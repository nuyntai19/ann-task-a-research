R90-P0A v1.2 BUILD-ONLY: 24 new SIFT1M / MS-Turing1M graph builds with six pinned P0A v1.1 binaries.

Scope / science
- This is BUILD-only exploratory evidence, not a final scientific comparative result, because matched-Recall@10 and QPS have NOT been measured for the NEW graph builds. Do not call a graph correct solely because a build ran.
- 18 OFF runs = Stock/H17/Fast ×3 independently built graphs ×2 datasets on CPU IDs 0,2,4,6.
- 6 ON runs = Stock/H17/Fast ×1 diagnostic graph ×2 datasets on CPU0. ON wall time NOT used for build-time comparison.
- All six original binary SHAs, three frozen original manifests, all six original graph/ELF/stdout/time checks and the native FTZ/DAZ report SHA are verified before any 1M work. Also verifies SIFT1M and MS-Turing1M dataset SHA, minimum 12 GiB disk free and 8 GiB MemAvailable.
- Uses ORIGINAL SHA-locked P0A v1.1 Python native_one() as the binary runner, only its OUT is rebound to an isolated NEW output directory. Six symlinks to frozen original ELF are stored in the NEW directory; source and binaries are NOT copied, edited or rebuilt.
- Every graph receives its own SHA and exact binary graph-file bounds audit (header, all degree <=64, all neighbor IDs in range, no selfloops, sampled duplicate-neighbor check). DOES NOT require Stock/H17/Fast graph SHA to match because FTZ/DAZ and Stage1 can change outcomes.
- Historical R90-P0A v1.1 auditpilot/full1m remains HOLD (its audit requires cross-arm graph SHA); the current runner is an isolated new experimental design, not a bypass of the old gate.
- A separate native evaluation of Search at matched Recall and same query+groundtruth is REQUIRED after these 24 builds before any quality/speed conclusion.
- The FTZ/DAZ synthetic controlled witness proves bit mutation when enabled, not that every historical Stock edge difference was caused by that exact Highway operation. H17/Fast are also not universally bitwise exact for two zero-subnormal keys with DAZ on.

First run:
  unzip -n "$HOME/Downloads/R90_P0A_V12_SIX_ELF_1M_BUILDONLY_BUNDLE.zip" -d "$HOME/Downloads"
  bash "$HOME/Downloads/R90_P0A_V12_1M_BUILDONLY_Ubuntu.sh"

New output:
  ~/ann-task-a/experiments/R90/r90_p0a_v12_pinned_six_elf_full1m_buildonly/
  Contains preregister.json, progress.json, compile_manifest.json, 24 per-graph JSON records, 24 graphs, time/stdout/counters, full1m_manifest.json, audit1m_buildonly.json.
  Main log: ~/R90_P0A_V12_PINNED_SIX_ELF_BUILDONLY.log

If interrupted mid-run: preserve all previous output. Do NOT rerun first-run shell, delete logs, manually edit source/manifest or patch SHA guard.
  F="$HOME/Downloads/r90_p0a_v12_pinned_six_elf_full1m_buildonly.py"
  python3 "$F" preflight
  python3 "$F" run
  python3 "$F" audit
The run resumes ONLY fully validated completed record files, and HOLDS on orphan/partial files. If HOLD occurs, send complete log + progress.json rather than removing any evidence.

Known limitation: Exact full 1M graph duplicate-neighbor detection is sampled for 1024 vertices/graph, not exhaustive. All IDs, degrees and self-loops are audited across every stored arc.
