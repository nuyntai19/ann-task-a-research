R90-P0A v1.3 Historical H85 Highway (6bc2d477) — 24 x 1M BUILD-only, v1
2026-11-20

PROVENANCE
- Requires existing v1.3 StageA and StageB PASS. Both native JSON SHA values pinned.
- Requires original six compiled Stock/H17/Fast OFF/ON ELF from v1.3; source trees,
  compiler, historical Highway commit and archive SHA commitments verified.
- Includes NO native binary, source code patches or graph data.
- Reuses P0A frozen v1.1 native_one() routine with exact same C160 K1024 MST_DEG2
  flags and six H85 v1.3 ELF SHA values; six symlinks in NEW output root.
- StageB single Stock SIFT1M quality graph remains an independent quality anchor
  and IS NOT counted among 3 new controlled performance repetitions.
- Builds 18 OFF (4 CPU cores 0,2,4,6; 3 repetitions for each arm x dataset),
  then 6 ON (core0; source work counters; NOT timing reference).
- Datasets: SIFT1M and MS-Turing1M, exactly pinned SHA via original v1.1.
- Audits all graph bytes/headers, all neighbor IDs, self-loops, and ALL 1M rows
  for duplicate-neighbor slots; SIFT1M graphs additionally report v0,
  first-10K large first/second inversion diagnostics and the 14,538 duplicate
  representative-pair retention statistic. Those geometric diagnostics are
  NOT substitutes for Search Recall.
- Reports mean OFF wall_s, RSS, and leaf-stage; ON counter JSONLs retained.
- CANNOT establish new-graph Search Recall/QPS or formal paired equivalence.

FIRST RUN (only after extracting this ZIP into ~/Downloads):
  bash "$HOME/Downloads/R90_P0A_V13_H85_FULL1M_24BUILD_v1_Ubuntu.sh"

RESUME only if the first-run command halted without orphan files and all
existing records pass SHA gates. NEVER delete/repair old evidence to pass:
  bash "$HOME/Downloads/R90_P0A_V13_H85_FULL1M_24BUILD_v1_RESUME_Ubuntu.sh"

OUTPUT ROOT:
  ~/ann-task-a/experiments/R90/r90_p0a_v13_h85_24build_native_v1
OUTPUT SUMMARY:
  audit1m_buildonly.json
  full1m_manifest.json
  preregister.json
MAIN LOG:
  ~/R90_P0A_V13_H85_FULL1M_24BUILD_v1.log

HOLD rules: never overwrite source/binary/graph/log; orphans halt safely.
Do not run older v1.1 Full1M/global cross-arm SHA parity checks.
Do not run 10M; separate RAM gate required. Avoid 108-run v1.2 matched
QPS: its Stock SIFT1M graph baseline was built with newer Highway.
