# R85-A4 — SIFT1M Baseline Confirmation

Date: 2026-11-11

- 6 arms, 3 BUILD repetitions per arm
- 18/18 BUILD PASS
- 18/18 SEARCH QUALITY PASS (25 beams/graph)
- 90/90 QPS graph-passes PASS

## BUILD medians

| Arm | Wall (s) | Peak RSS (KiB) |
|---|---:|---:|
| Stock PiPNN | 64.78 | 2803552 |
| H17 + TwoTier | 48.32 | 2213260 |
| Flat C64 K1024 N2 | 54.06 | 2029324 |
| Flat C64 K512 N2 | 42.86 | 2046952 |
| Flat C64 K1024 N1 | 24.09 | 1977884 |
| Flat C64 K512 N1 | 18.39 | 1978304 |

## Decision

Primary technical SIFT1M baseline:
H17 + Flat C64 K512 N2.

BUILD-fast candidate:
H17 + Flat C64 K512 N1.

## Limitations

Matched-Recall comparisons are interpolated.
QPS uses measured beams reaching the target Recall.
Some N1 beam choices overshoot the target markedly.
Additional SEARCH-only QPS measurements are needed.

Three BUILD repetitions do not establish statistical
equivalence or cross-dataset generalization.

See JSON files for exact measurements.
