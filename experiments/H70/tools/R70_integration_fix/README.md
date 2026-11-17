# R70 integration fix — 04/11/2026

The original R70 integration script rejected the pinned `algorithms/PipNN/CMakeLists.txt` because `target_precompile_headers(${TARGET_NAME} PRIVATE neighbors.h)` appeared **twice**: once in a commented-out example and once as an active CMake command. It also used `.replace(..., 1)`, which would have patched the *comment* first if the count check were simply removed.

`r70_integrate_fixed.py` fixes **both** issues. It requires the exact active, indented line of the pinned CMake file and adds `R70_TWO_TIER=1` **only to the live target**. Other safety checks (pinned PiPNN commit and graph.h blob, original pipnn.h, generated two-tier header, isolated H70 worktree) are retained.

Run: `python3 experiments/H70/tools/R70_integration_fix/r70_integrate_fixed.py --worktree "$PWD/experiments/H70/pipnn-clean-443a328"`

Require `R70_INTEGRATION_PATCH_PASS` before compiling. Do not treat previously copied binary `r70_tier_pipnn` as tier: both previous binaries were identical and came from the stock code path.
