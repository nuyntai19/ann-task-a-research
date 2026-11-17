# R78.2 — Native Export graph parity and synthetic reservoir microbenchmark

Inputs: PINNED H70 worktree, `H70/build-r70` compiler/link specs, and already working R78 `r78_segmented_lshgraph.h`.

**Read/Write boundary:** The runner **reads** H70's stock code, Two-Tier header and existing build flags/libs, and **writes** only new R78.2 object/executables under this extracted directory. It does not run CMake, modify any H70 source/binary/graph/dataset, and does not build a PiPNN ANN index. It refuses unexpected source hashes.

1. Place `r78_2_native_gate.tar.gz` in `~/Downloads`.
2. Extract into the existing `~/ann-task-a/experiments/H78/r78_s1_pilot` (creates a new `r78_2_native_gate/` subfolder):

```bash
cd ~/ann-task-a/experiments/H78/r78_s1_pilot
tar -xzf ~/Downloads/r78_2_native_gate.tar.gz
python3 ./r78_2_native_gate/run_r78_2_native_gate.py --phase export
```

**Only after Export gate PASS**, optionally measure the synthetic workload with three isolated independent processes per arm (Stock/Tier/S1). This uses at most 100k synthetic nodes and is NOT an ANN graph BUILD or SIFT dataset performance result:

```bash
python3 ./r78_2_native_gate/run_r78_2_native_gate.py --phase bench --nodes 100000 --reps 3
```

Successful export markers: `R78_2_EXPORT_GRAPH_PARITY_PASS` (four cases), `R78_2_REAL_PIPNN_ROBUSTPRUNE_EXPORT_PASS`, `R78_2_EXPORT_GATE_COMPLETE`. No such markers can be assumed until real Ubuntu output is observed.

Scientific limits: no claim of multi-thread schedule equivalence, end-to-end BUILD/RSS/Recall equivalence, performance on SIFT1M, or algorithmic novelty. The microbenchmark models a fixed category occupancy distribution and uses a single sequential batch per node; results depend on CPU/allocator/hugepages, do not predict full BUILD or tail latency, and must be viewed together with original R72 baseline.
