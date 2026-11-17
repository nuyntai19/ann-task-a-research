# H21-R2 v4 — Same-build three-stage coverage audit

C0 reused from H21-R1 summary for the identical SHA-256 proposal log; no binary proposal decoder needed.
C1/C2 measured from SAME-BUILD H18-R1.2 before/after-final-prune graph snapshots.

| Group | n | C0 Pool | C1 Pre | C2 Post | Net C0-C1 | C1-C2 |
|---|---:|---:|---:|---:|---:|---:|
| random | 12 | 90.83% | 87.50% | 68.33% | +3.33% | +19.17% |
| low_in | 12 | 80.00% | 75.00% | 50.83% | +5.00% | +24.17% |
| low_out | 12 | 85.00% | 80.83% | 46.67% | +4.17% | +34.17% |
| high_in | 12 | 89.17% | 84.17% | 69.17% | +5.00% | +15.00% |
| overall | 48 | 86.25% | 81.88% | 58.75% | +4.38% | +23.12% |

- Actual exact Top10 edges removed at final prune (sample): **111**.
- IMPORTANT: C0-C1 is a NET coverage difference, not a count of specific edges removed before final prune.
- Coverage losses do NOT prove poor ANN search or imply the pruning policy is wrong.
- No H21-C1 algorithm or novelty established.
