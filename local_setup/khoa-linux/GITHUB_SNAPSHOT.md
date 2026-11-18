# Branch snapshot — 2026-11-19

This branch preserves the original cloned repository and adds the local Ubuntu
setup, latency logging, named runs, configurable beams, isolated adaptive fanout
experiment, source snapshots, change history, reports, and saved run summaries
and build/search logs. The original main branch is unchanged.

Start with `README.md` in this directory and
`experiments/adaptive_fanout_v1/README.md` at the repository root.
The user's matched-Recall comparison is in
`experiments/adaptive_fanout_v1/comparisons/user_af_eps015_vs_fixed_r2/comparison.md`.

Datasets, generated graphs, native builds/dependencies, caches and large per-query
CSV / bucket dumps stay on the original machine under the existing ignore rules.
They are not included in this Git snapshot. Saved summary paths refer to that
machine; obtain the data and build locally before reproducing runs. Read the
limitations in the reports when interpreting timing and quality results.
