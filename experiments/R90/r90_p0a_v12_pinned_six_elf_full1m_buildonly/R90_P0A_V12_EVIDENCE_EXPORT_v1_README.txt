R90 P0A v1.2 READ-ONLY compact evidence export v1

PURPOSE
- After 24 native 1M BUILD-only graphs passed structure audit, export exact
  /usr/bin/time -v timings, stage stdout, 6 ON R86 counters, all run manifests.
- Independently stream-SHA all 24 NEW graph files and all 24 stdout/time records
  plus six ON R86 counter files, against original recorded checksums.
- DO NOT run BUILD, Search, compile or change any original files.

PRE-REQUISITES
- Original P0A v1.2 R90 24 graphs/records, preregister.json,
  full1m_manifest.json, audit1m_buildonly.json must remain unchanged.
- Original native top-level log must remain at:
  ~/R90_P0A_V12_PINNED_SIX_ELF_BUILDONLY.log
- This exporter checks original audit SHA256:
  dd90ce5c892e88235c1b611809ca9d2b43801ecd6d887ccb0f0ae75c49718f97
- It checks original native log SHA256:
  720d04ecb5ab00ad25a05f449c65468a84b743db4a5f2257ed741d6404c9d43d
- Original v1.2 runner SHA256:
  cd696087b03135699b4272357964f840f6148d9fe818b65c31a37064d122fabc

EXECUTION
unzip -n "$HOME/Downloads/R90_P0A_V12_EVIDENCE_EXPORT_v1_BUNDLE.zip" -d "$HOME/Downloads"
bash "$HOME/Downloads/R90_P0A_V12_EVIDENCE_EXPORT_v1_Ubuntu.sh"

OUTPUTS (new files only, original R90 files kept untouched)
~/R90_P0A_V12_NATIVE_EVIDENCE_EXPORT_v1.tar.gz
~/R90_P0A_V12_EVIDENCE_EXPORT_v1.log

Archive includes 24 run JSON, 24 stdout, 24 time, 6 ON counters, the
preregister/full/audit/compile manifests, original log and derived_summary.json.
Archive explicitly excludes the 24 graph bytes (several GiB); it includes their
verified SHA256 and directed arc counts. The other archive files are SHA verified.

IMPORTANT LIMITATIONS
- Sources/ELF/datasets were pinned by original R90 P0A v1.2 native runner;
  this additional exporter independently rehashes 24 graph bytes, not original
  stock/highway source or data files.
- OFF wall and Peak RSS are native system measurements, but must be interpreted
  together with major faults and build metadata. ON timing is DIAGNOSTIC ONLY.
- Stock top2 SIMD internal comparisons, assignments and data moves are NOT
  measured. Source Q writes/sort calls are not the same as SIMD operations.
- This archive does not run Search. New graph Recall/QPS remain UNMEASURED.
- If a failure occurs, do not edit or remove the original graph, binary or logs.
  Send the exporter log to audit and create a separate versioned recovery if needed.
