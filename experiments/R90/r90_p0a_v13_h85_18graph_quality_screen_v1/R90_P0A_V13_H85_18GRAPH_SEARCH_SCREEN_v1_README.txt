R90 P0A V1.3 H85 (Highway 6bc2d477) / 18 OFF 1M SEARCH FIXED-BEAM QUALITY SCREEN / v1

EXACT PYTHON SHA256: dcfe8d6f856b37ca149ee4a00b257f2af11d7ef757a24d99859634633c2191a6

Provenance gates:
- Native v1.3 H85 BUILD audit SHA: 9550858dcb763349ed5180b3b65577e48a600e54becc0ecb9c755970a4d4bbfb
- Native v1.3 H85 full manifest SHA: 0c76f3e5bc3dc0d82f70aa1aadac9b26c5b0e8f4607f31d9aa6d8b0b0a4121c3
- Native v1.3 H85 BUILD log SHA: eb12eafb1693cf1b06ab3b6a9f6473385ee864924c2678df984b369717ecbd58
- Historical H85 commit SHA: 6bc2d47793bae9c521fb4150936669647700765d
- Crosslinks audit + full + original build preregistration, 18 graph full SHA and 4CPU OFF timing source ELF SHA.
- Queries, GT100 and existing evaluator ELF SHA pinned independently per dataset.

What happens:
1. Selftest without BUILD / Search.
2. SHA preflight 18 ORIGINAL H85 4CPU OFF graphs + native query/GT/evaluator binary + graph header.
3. Search all 18 graphs ONE native 1CPU0 evaluator call per graph.
   SIFT1M: 10,000 queries, tested beams [10,20,40,80,160], existing R72 evaluator.
   MS-Turing1M: 100,000 queries, tested beams [384,896], existing native R86 v4 evaluator.
4. Native stdout rows recorded with per-graph SHA, Recall@10 and Search QPS.
5. Read-only audit re-parses and re-hashes all source receipts, writes correct dataset-local tested_beam_grid in summary.

This is a quality SCREEN, not repeated QPS or target-matched latency. In particular MS legacy high-beam avg_cmps may be invalid (32-bit overflow) and is not compared. No new graph BUILD, no source modifications, no 10M, no overwrite of old v1.1/v1.2/v1.3 artifacts. Native graph bytes not bundled/exported.

Unpack:
unzip -n ~/Downloads/R90_P0A_V13_H85_18GRAPH_SEARCH_SCREEN_v1_BUNDLE.zip -d ~/Downloads

FIRST RUN:
bash ~/Downloads/R90_P0A_V13_H85_18GRAPH_SEARCH_SCREEN_v1_Ubuntu.sh

Read-only results after native PASS:
~/ann-task-a/experiments/R90/r90_p0a_v13_h85_18graph_quality_screen_v1/quality_screen_summary.json
~/ann-task-a/experiments/R90/r90_p0a_v13_h85_18graph_quality_screen_v1/full_manifest.json
~/R90_P0A_V13_H85_18GRAPH_SEARCH_SCREEN_v1.log

On native HOLD preserve all output and log; send them for review. RESUME shell is only for a partial state with complete receipt+stdout+stderr SHA (or after complete full_manifest and no audit), and must not be run to bypass graph or query SHA drift:
bash ~/Downloads/R90_P0A_V13_H85_18GRAPH_SEARCH_SCREEN_v1_RESUME_Ubuntu.sh

Experimental caveat: H85 old Highway no single-zero packed-bit clearing in controlled StageA probe; simultaneous-subnormal tie ordering differences remain under DAZ. ON 1CPU graph byte equality is observed for 1 native run per arm/dataset; independent 4CPU graph SHA variation is expected. No formal statistical quality equivalence claim before repeated matched-Recall QPS.
