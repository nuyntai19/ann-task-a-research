# R71 H17 Packed Top-2 × R70 Two-Tier

Use only in `~/ann-task-a/experiments/H70/pipnn-clean-443a328` which already contains the successful R70 integration. Does NOT touch `~/ann-task-a/src/PiPNN` or overwrite `experiments/H70/bin`.

## Preconditions

- Pinned original PiPNN commit `443a328dc71a3b7be753d52ca2b3c9a4ba77f3fd`.
- `algorithms/utils/graph.h` Git blob `7c5b8c1196a3ad741dfd22fe8f35b72acae2b19f`.
- Phase3 H17 historical source `experiments/H17/phase3_top2_e2e/PiPNN-top2/algorithms/PipNN/pipnn_utils.h` SHA256 `b4a7e39a1ddf6c9f41f136360773aa9aef50ae7d19921b0b49b6422408c4c520`.
- H70 worktree `pipnn_utils.h` SHA256 `ee2048738ad4462f21bdfea4a1cf7c2ac140f72fbd8875d869bc4f613d93db53` before integration.

## Core method

Extract *only* Phase3 `if (MST_DEG == 2)` Packed Top-2 selector, gated by compile-time macro `R71_H17_TOP2`, leaving pinned stock Highway selector unchanged for OFF and MST_DEG != 2. No H17 profiler, no H25 code. Add variant print to the existing R70 worktree for runtime provenance.

## Run

```bash
cd ~/ann-task-a
OUT="$PWD/experiments/H70"
unzip -o ~/Downloads/R71_h17_factorial_kit.zip -d "$OUT/tools"
python3 "$OUT/tools/R71_h17_factorial_kit/r71_integrate_h17.py" \
  --worktree "$OUT/pipnn-clean-443a328" \
  --phase3 "$PWD/experiments/H17/phase3_top2_e2e/PiPNN-top2/algorithms/PipNN/pipnn_utils.h"
# Only if R71_H17_INTEGRATION_PATCH_PASS
bash "$OUT/tools/R71_h17_factorial_kit/r71_build_4arms.sh" "$PWD" | tee "$OUT/r71_build_4arms.log"
```

Build script produces new `experiments/H70/r71-bin/{A_stock,B_h17,C_tier,D_h17_tier}`. It refuses to overwrite that directory on reruns. Build logs are there as well. Compile with one job (-j1). All four SHA256 must differ.

**Important:** Four distinct binaries are not end-to-end parity evidence. Next must use guarded one-thread smoke test comparing A/B/C/D graphs, then 4-thread SIFT100K 3 runs/arm with quality checks. Do not directly claim H17 + R70 improves two metrics before benchmark results.
