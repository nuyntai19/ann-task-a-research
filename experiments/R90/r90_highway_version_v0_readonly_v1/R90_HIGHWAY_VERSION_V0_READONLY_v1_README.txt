R90 HIGHWAY REVISION and SIFT1M entrypoint v=0 diagnostic v1

RUN ONLY THIS INSTEAD OF THE OLD R90-P0A v1.2 matched-threshold bundle.
This script performs read-only original SHA checks. It does not compile, BUILD, Search,
modify, delete, replace, or rehash user history to alter its interpretation.

Source check:
  H85 Highway source root: H85/r85_0_matched_baseline/build_stock/_deps/highway-src
  R86 Highway source root: R86/r86_v1_2_builds/stock_off/_deps/highway-src
  Exact source Git blob SHA (not a guessed git HEAD) for traits-inl.h and
  sorting_networks-inl.h at google/highway commits 6bc2d477 vs 0e0a01da.
  Independently verified those blob IDs from publicly accessible GitHub.
Graph check:
  P0A v1.2 full1m_manifest.json original SHA and SIFT1M source SHA;
  Original Stock/H17/Fast OFF graph r1 byte SHA and full graph headers/degrees;
  SIFT1M entrypoint v0 neighbor degree, presence of ID 2 and ID 6, and true L2
  distances to all v0 stored neighbors. This probes Gemini's claimed entrypoint
  anomaly; it does not by itself prove that any specific edge resulted from FTZ.
  If available, inspect original quality_screen_summary.json for incorrect
  'tested_beam_grid' SIFT1M metadata, preserving original unmodified file.

OUTPUT (new files, never overwrite):
  ~/R90_HIGHWAY_VERSION_V0_READONLY_v1_report.json
  ~/R90_HIGHWAY_VERSION_V0_READONLY_v1.log

Usage: save ZIP into ~/Downloads, then:
  unzip -n ~/Downloads/R90_HIGHWAY_VERSION_V0_READONLY_v1_BUNDLE.zip -d ~/Downloads
  bash ~/Downloads/R90_HIGHWAY_VERSION_V0_READONLY_v1_Ubuntu.sh

On HOLD, don't delete or edit originals: send the terminal log and path.
On PASS, upload JSON report to ChatGPT. Old matched-threshold Search v1
must remain unrun pending source-version and graph correctness resolution.
