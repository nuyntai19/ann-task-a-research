# ANN Task A Research (`ann-task-a`)

Source-only mirror of `/home/tai/ann-task-a` for code review and research collaboration (datasets, built graph files, compiled binaries, build directories, and heavy raw trace/log dumps are excluded).

## Key Directories

- [`experiments/R91/`](experiments/R91/) — **MS-Turing10M** scale-up & memory-optimization campaign under strict 24 GiB / zero-swap cgroup v2:
  - **Baseline (`G0.6–G1M-D`):** TwoTier degree audit (`G0.6`), `Fast v2` vs `Stock` Flat C160 10M BUILD (`377.47s` vs `437.77s`, `−13.77%` total / `−26.28%` Stage 2, both hitting `24.00 GiB` cgroup peak with `333–345` `memory.events.max`), exact-guard 10M evaluator (`G1B v2`), 10-beam Recall calibration (`G1B`/`G1B-C`/`G1-Stock Search`/`G1M-A`), and 12-run interleaved paired QPS (`G1M-D`, beams `576` & `1792`).
  - **Memory Optimization Track (`G2A.0–G2A.3`):** Source/memory audit (`G2A.0`), `~LSHGraph()` destructor leak fix (`G2A.1`), early post-clustering `SketchHash` + `LSHGraph::locks` release (`G2A.2`, `sketch_locks`), and blockwise lazy `GraphI` initialization + 2 MiB-aligned `MADV_DONTNEED` `LSHGraph` reclamation (`G2A.3`, `lazy_reclaim`). Verified end-to-end across SIFT100K/1-CPU (8/8 byte-identical graphs `4998cb93…`), MS-Turing1M/4-CPU (same-session `−190.3 MiB` Max RSS for `G2A.3` vs `G2A.2`; `−24.3%` Max RSS / `−29.1%` cgroup peak vs historical Original; 8/8 100K-query Search PASS), and native **MS-Turing10M/4-CPU** (`Fast v2 + G2A.1–G2A.3`: Max RSS `20.59 GiB`, cgroup peak `20.64 GiB`, `0` `memory.events.max`, `370.02s` wall, forensic 10M full-graph audit PASS, and 8/8 exact-guard 100K-query Search PASS at beams `576` & `1792`).
- [`experiments/R90/`](experiments/R90/) — Complete R90 Stock vs H17 vs Fast v2 campaign: exploratory P0–P3.8 gates, D6/D7 & P4/P4Q/P4M/P4R 1M studies, P0B counter64 audit, P0A v1.1–v1.2 unified builds + Highway `0e0a01da` vs `6bc2d477` FTZ/DAZ root-cause audit, and final **P0A v1.3** historical Highway `6bc2d477` controlled 1M benchmark (Stage A/B, 24-build 1M audit, 18-graph search screen, and 108-observation matched-threshold repeated QPS).
- [`experiments/R86/r86_v1_2_source/`](experiments/R86/r86_v1_2_source/) — Active R86 instrumented PiPNN C++ implementation (`algorithms/PipNN/pipnn.h`, `pipnn_utils.h`, `CMakeLists.txt`).
- [`experiments/R86/`](experiments/R86/) — Latest R86 diagnostics, gate tools, counter64 campaigns (`g11_*`), beam/trace diagnostics (`g12_*`, `g15_*`), MSTuring 1M evaluation/six-arm runs (`msturing_1m_*`), prefix scaling, and matched-recall runners.
- [`00_PROJECT_HOME/`](00_PROJECT_HOME/) — Navigation hub (`00_START_HERE.md`, `PROJECT_STATUS.md`, `LINK_MAP.tsv`), R86 shell/Python runner scripts (`07_SCRIPTS/`), and lightweight result summaries (`05_RESULTS_AND_COUNTERS/`).
- [`src/`](src/) — Base `PiPNN` and `ParlayANN` source trees and top-level Python benchmark/smoke scripts.
- [`experiments/`](experiments/) — Full series of research experiments (`G0`, `H17`–`H85`, `R86*`), patches, and small JSON/CSV summaries.
- [`ann_task_a_r29.py`](ann_task_a_r29.py) .. [`ann_task_a_r67_progress_witness_audit.py`](ann_task_a_r67_progress_witness_audit.py) & `README_H32_R*.md` — Root-level R29–R67 analysis scripts, self-tests, and notes.
- [`exports/TaskD_R86_MST1M_Handoff_v1/`](exports/TaskD_R86_MST1M_Handoff_v1/) — Text/JSON/CSV handoff provenance and checksums (`.tar` graph bundles excluded).

## Excluded Heavy / Non-Source Paths

- Input datasets (`data/`, `*.fbin`, `*.u8bin`, `*.ibin`, `*.hdf5`, `*.npy`, `*.i32`)
- Built graph indexes and binaries (`indexes/`, `*.graph`, `results/perf_*.data`, ELF binaries)
- CMake build trees & downloaded dependencies (`build/`, `cmake-build*/`, `_deps/`, `CMakeFiles/`, `*.gch`, `*.o`, `*.a`, `*.so`)
- Python virtual environments (`.venv/`, `experiments/**/.venv*`)
- Large run traces/logs/archives (`exports/*.tar*`, `*.tar.gz`, `pass*.tsv`, `query.csv`, `steps.csv`, `leaf.sizes.jsonl`, `*.trace`, `experiments/**/*.log`)
- Duplicate unmodified third-party copies inside `experiments/` (`external/`, `parlaylib/`, `third_party/`, `vendor/`); full `src/PiPNN` and `src/ParlayANN` trees remain under `src/`.
