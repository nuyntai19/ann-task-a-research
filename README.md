# ANN Task A Research (`ann-task-a`)

Source-only mirror of `/home/tai/ann-task-a` for code review and research collaboration (datasets, built graph files, compiled binaries, build directories, and heavy raw trace/log dumps are excluded).

## Key Directories

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
