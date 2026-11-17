# H21-R1 — Read-only candidate supply vs ending audit

Input: H18-R1 SAME-RUN graph/proposals; 48 base anchors; exact top-10.
## Chỉ số trực tiếp theo từng stratum (không phải ANN Recall)
| Nhóm | Số node | Pool exact-topk coverage | Graph direct exact-topk coverage | Pool–graph gap | Mean pool size |
|---|---:|---:|---:|---:|---:|
| random | 12 | 0.9083 | 0.6833 | 0.2250 | 38.8 |
| low_in | 12 | 0.8000 | 0.5083 | 0.2917 | 22.2 |
| low_out | 12 | 0.8500 | 0.4667 | 0.3833 | 21.4 |
| high_in | 12 | 0.8917 | 0.6833 | 0.2083 | 65.0 |

## Pre-registered diagnostic flags
- LOW_IN_CANDIDATE_POOL_COVERAGE_10PP_BELOW_RANDOM_IN_SAMPLE
- POOL_VS_GRAPH_DIRECT_TOPK_GAP_GE_10PP_IN_SAMPLE

## Giới hạn
- Exact top-k is computed for BASE POINTS, not SIFT query vectors. This is 1-hop local kNN coverage, NOT graph search Recall or navigability.
- Candidate pool counts any incident directed proposal pair in either orientation because PiPNN merges reverse proposals. It is an available edge set, not proof that final ending could keep all top-k simultaneously under degree/directional constraints.
- Low-degree/in-degree groups are selected from the FINAL graph (post-outcome stratification); differences are descriptive, not causal.
- Missing a true base kNN edge from candidate pool does NOT prove beam search cannot reach it over multiple hops.
- Pool-vs-graph gap does NOT attribute loss to HashPrune vs RobustPrune vs geometric trade-offs or final reverse update.
- One SIFT1M graph, one sample, potential duplicate base vectors and distance ties, no CI; no build-time or recall claims.
- No graph is built, no source bytes modified. No H21-C1 selected even with large observed gaps.

**Phán quyết:** H21-R1 chỉ định vị ứng viên của điểm dữ liệu còn thiếu hay cạnh một-hop có bị loại. Nó không tự xác nhận novelty, tốc độ BUILD, Recall hoặc hướng H21-C1.
