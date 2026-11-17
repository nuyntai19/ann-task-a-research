<!-- GENERATED_BY_ANN_PROJECT_HOME_V1_0. Keep personal notes in 09_MY_NOTES.md. -->
# ANN / PiPNN -- PROJECT HOME

**One place to navigate:** `/home/tai/ann-task-a/00_PROJECT_HOME`. **Important:** this is a SAFE INDEX built from symlinks; source, input data, graphs and logs stay at their original paths. Do not manually move the old folders.

## Open these files first

| Need | Open here | What it is |
|---|---|---|
| Main C++ source | `01_SOURCE/PIPNN_CORE_CODE/pipnn.h` and `pipnn_utils.h` | R86 PiPNN implementation used in the 100K builds |
| Full pinned source tree | `01_SOURCE/R86_PINNED_SOURCE/` | CMake + PiPNN sources |
| Compiled binaries | `02_BINARIES/R86_HW85_FOUR_BINARIES/` | `build_stock_off`, `build_stock_on`, `build_h17_off`, `build_h17_on` |
| Base vectors | `03_DATA_AND_GT/SIFT100K_BASE.fbin` | n=100,000 input |
| Candidate ground truth | `03_DATA_AND_GT/SIFT100K_GT300_CANDIDATE.ibin` | NOT YET CERTIFIED; query must match |
| Built ANN graphs | `04_RUNS_AND_GRAPHS/SIFT100K_A0_A4_20_RUNS/` | 20 graph files in subdirs named `run_id` |
| Build stdout logs | `04_RUNS_AND_GRAPHS/SIFT100K_A0_A4_20_RUNS/<run_id>/<run_id>.build.log` | Per-graph logs; do not use random old Hxx logs |
| High-level logs | `06_LOGS/` | nohup launch log and audit log |
| Summary of timings/RSS | `05_RESULTS_AND_COUNTERS/build_only_summary.json` | Five arm medians + SHA stability |
| Counter identities | `05_RESULTS_AND_COUNTERS/audit_summary.json` | 20 graph SHA checks and 5/5 counter checks |
| Detailed counter CSV | `05_RESULTS_AND_COUNTERS/C_WORK_100K_counter_records.csv` | Data to upload for full per-depth Sheet import |
| Status of search | `08_SEARCH_EVALUATOR/` and `PROJECT_STATUS.md` | Evaluator is a candidate; query and exact GT not yet confirmed |
| Study notes | `09_MY_NOTES.md` | Your own notes, safe to edit |

## 100K experiment arms

A0 = Stock PiPNN C160 K1024 N2; A1 = H17-only C160 K1024 N2; A2 = H17 C64 K1024 N2; A3 = H17 C64 K512 N2; A4 = H17 C64 K512 N1. Each arm has 3 OFF timing runs + 1 ON counter run.

## What is verified, what is missing?

- Verified: 20/20 graph files nonempty and SHA checked by the separate postbuild audit; 5/5 ON counter mathematical identities pass. Build wall-time medians (A0..A4) = 3.26, 2.68, 2.66, 2.08, 1.10 s; peak RSS KiB = 415664, 414848, 339940, 341152, 336868.
- CAUTION: all five arms have non-identical graph SHA across repeats, and at least the OFF graph byte lengths differ. Independent graph adjacency validation and Recall are NOT DONE.
- Not yet measured: SIFT100K exact-GT-matched Recall@10, search latency, p95/p99, QPS and NDC. Do not call A4 the best ANN configuration before these are checked.
- Detailed counter CSV is already linked here; do not move it out of the original export directory.

## Google report destinations

- Google Sheet (A_SYSTEM, B_SEARCH, C_WORK, E_PROTOCOL, ABLATION, WEEK_PLAN): https://docs.google.com/spreadsheets/d/12ApqgMV8YykflyFXUT2VMbUhgyiGirtoOmRWCXCz3Ek/edit
- Google Doc (methodology and H45 post-build audit): https://docs.google.com/document/d/185pgBkUudDkF-HvqxM2xPgV3f1Q7hwjbIuusq6AnIbc/edit

## Quick commands

```bash
cd "$HOME/ann-task-a/00_PROJECT_HOME"
cat PROJECT_STATUS.md
ls -la 05_RESULTS_AND_COUNTERS
ls 04_RUNS_AND_GRAPHS/SIFT100K_A0_A4_20_RUNS | head
# Open the whole hub in Files (GNOME):
xdg-open "$HOME/ann-task-a/00_PROJECT_HOME"
```

**Rule from now on:** any future campaign produces raw files under `experiments/R86/...`; link its final output here and register the run in Google Sheets. Never create a second 'main project' directory.
