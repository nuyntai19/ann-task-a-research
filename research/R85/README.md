# R85 — PiPNN ANN Graph Construction Research

## Source

The C++ source overlay comes from the pinned PiPNN
worktree at upstream commit
443a328dc71a3b7be753d52ca2b3c9a4ba77f3fd.

The modified pipnn.h and pipnn_utils.h support
H17 Packed Top-2 and R70 TwoTier options.

The source and patch are preserved for reproducibility.
The current preferred configurations use H17 with
TwoTier disabled.

## Experimental results

R85-0: Stock vs H17 + TwoTier baseline.

R85-A1: Flat C64 vs Flat C160 vs TwoTier.

R85-A1c: Measured matched-Recall beam comparison.

R85-A2/A2b: Edge matching, Recall interpolation,
and graph topology analysis.

R85-A3.1: Reservoir capacity sweep.

R85-A3.2: Alpha tuning.

R85-A3.3: Partition tuning.

## Current findings (SIFT1M, 4 P-cores)

H17 + Flat C64, cluster_size=512,
num_clusters=2, alpha=1.1:

Median BUILD wall: 35.515 seconds
Median peak RSS: 2039756 KiB
Median directed arcs: 24377149

H17 + Flat C64, cluster_size=1024,
num_clusters=1, alpha=1.1:

Median BUILD wall: 21.65 seconds
Median peak RSS: 1967926 KiB

Both configurations are parameter-tuned
engineering baselines, not established novel ANN
algorithms.

Results have only two BUILD repetitions per
new partition variant and require paired confirmation.
Search comparisons use interpolated matched Recall.

## Reproducibility

Use the pinned upstream PiPNN checkout and apply
the source overlay, then follow the experiment
runners in runners/.

Data files, built binaries, and graphs are excluded.
The full research chronology is maintained separately
in the project Google Doc.
