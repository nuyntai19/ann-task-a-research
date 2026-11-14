# R70 — isolated preflight (not yet native experiment)

This package performs a **read-only** code inventory and computes the **nominal allocation model** described in H32-R69. It intentionally does **not** claim to implement or test an equivalent Two-Tier `LSHGraph`; that requires the pinned original `graph.h`, its build dependencies, and a working source-level fixture.

On Ubuntu:

```bash
cd ~/ann-task-a
mkdir -p experiments/H70
python3 /path/to/r70_preflight.py --root "$PWD" --out experiments/H70/r70_preflight.json
python3 /path/to/r70_memory_model.py | tee experiments/H70/r70_nominal_model.json
```

Verify where the *original* PiPNN repository lives (not necessarily `~/ann-task-a`); rerun preflight with `--root /exact/path/to/pipnn` if needed. Read `potential_source_files` and its SHA256, then verify original pinned commit `443a328` in its own repository. Do not mutate existing source or experiments.

## Gates for actual source-level R70 implementation

1. Pin original repository and exact `graph.h` SHA. Use an isolated Git worktree at pinned commit. Confirm `sizeof(LSHCandidate<uint32_t,float>) == 8`, cap C=160, sentinel layout, and lock ownership via source + native compile checks.
2. Implement `TwoTierLSHGraph` with base row `(B+1)` 8B slots (B=64), per-node stable active row pointer, and full `(C+1)` row on the 64→65 migration. Migrate under the **same vertex mutex**, copying sentinel and candidates, with memory lifetime and alignment correct. Do not silently change HashPrune or merge order.
3. Run the exact same **ordered** candidate streams against stock and Two-Tier. Compare complete slots and cached degree/worst selection bitwise after each merge. Cases: no collision; repeated hash; BF16 rounding collision; equal distances; full cap; 64→65 promotion; duplicate winner; per-source multithread pressure.
4. Only after native correctness passes: separate subprocess microbenchmarks with `GNU time -v`, randomized/counterbalanced arm order and same inputs. Record **peak RSS and wall time**; include allocation, pointer lookup, merge and migration. Never report nominal bytes as RSS.
5. If successful, SIFT100K 2×2 controlled BUILD (stock+flat, H17+flat, stock+tier, H17+tier), >=3 independent builds/arm, matched search settings/Recall and graph integrity. No full SIFT1M BUILD at first.

**Kill gates:** parity failure on identical ordered input; migration/cached sentinel bug; worse throughput beyond preregistered margin; no measured peak RSS decrease; or combined arm failing two-metric objective / quality noninferiority.

Status: R70 **preflight package prepared**. Native results, PiPNN code modifications, RSS improvement, and H33 opening are **NOT** established.
