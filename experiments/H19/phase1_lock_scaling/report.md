# H19-R1 — Measured SIFT1M worker scaling and sampled reservoir mutex latency

This is a DIAGNOSTIC run on the H17 Top-2 baseline, not a new ANN algorithm.

| Workers | BUILD wall (s) | Leaf wall (s) | Avg sampled wait (ns) | Avg sampled hold (ns) | Wait share |
|---:|---:|---:|---:|---:|---:|
| 1 | 142.900 | 100.161 | 58.3 | 114.6 | 33.72% |
| 2 | 81.200 | 58.703 | 63.3 | 129.7 | 32.81% |
| 4 | 44.680 | 30.693 | 63.1 | 129.9 | 32.69% |

Instrumented 1→4 BUILD speedup: **3.198×**; efficiency vs linear: **80.0%**.

**Interpretation gates**:
- If sampled wait share rises sharply at 4 workers, examine per-vertex contention and repeated writers. Do not yet implement a new scheduler.
- If sampled wait stays low but efficiency is poor, investigate DRAM/cache bandwidth, serial partition+prune, and work imbalance instead.
- If 4 workers scale well, lock contention is not a compelling primary H19-C1 problem on SIFT1M f30.

Limitations: one run per p is not an inferential benchmark; H17 phase worker-seconds are not wall-clock critical path; C++ probes change time.
Original G0 graph hashes are checked before/after. No output graph is saved.
