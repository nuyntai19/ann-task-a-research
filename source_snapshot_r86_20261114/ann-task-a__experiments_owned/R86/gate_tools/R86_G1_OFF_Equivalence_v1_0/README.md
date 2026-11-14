# R86 G1 — OFF Equivalence, BIGANN1M (v1.0)

This is a **new R86-only experiment**, not R85 resume. The uploaded `R86_G1_R85_Protocol_Evidence.tar.gz` was inspected and was the source of the two selected CLI commands, source checksums, dataset hashes, native evaluator hash, and historical pass-count predictions.

## Precisely what this does

- Uses only R86 native **counter-OFF** `stock_off` and `h17_off` compiled in `r86_v1_2_builds`; no ON timing, no TwoTier.
- Pairs **the exact R85 variants** `STOCK` (C160 K1024 N2) and `C64_K512_N2` (H17 Flat C64 K512 N2), with BIGANN1M, 4 P-cores 0,2,4,6, fanout 10,3,1, h12, R64, alpha1.1, `-prune 1 -prune_all 1 -k 0` and the same environment variables. This is **not** the one-factor H17 comparison; later A1 H17 C160 is required.
- SHA-pins the original R85 runner, original R85 protocol manifest, G0 manifest, both new executables, base/query/GT and the original native evaluator. Verifies the exact CLI tuple before running.
- `--preflight` and `--dry-run` are **read-only** (no file write or graph build). The full dataset is hashed in preflight; can be disk intensive.
- `--run-build` creates a unique **new** session under `~/ann-task-a/experiments/R86/gates/g1_off_bigann1m/g1_*/`, runs Stock then H17 sequentially, verifies binary graph header/size/degree bound, self-loops/duplicate/out-of-range neighbors, and checks the **per-pass historical bucket + cumulative point–leader COMPARISONS + integer occupancy**. It writes `.graph`, `.record.json`, `.build.log`, `.time` and `build_results.json`. Fail closed on mismatches: never delete/move or overwrite existing historical artifacts.
- `--run-quality` is a separate phase, requiring successful 2-graph build session. Uses the original pinned evaluator and 25 beams, writes `.quality.log` and `.quality_record.json`. Marker PASS means **evaluator executed**; it is **NOT** proof of matched-Recall equivalence. Numerical Recall/latency compare with R85 still requires reviewing logged values. No automatic matched latency claims.
- `package_g1_evidence.py` archives small manifests and logs from R86, and two historical R85 reference logs/quality logs (when present), explicitly excluding all `.graph` and dataset files.

## On Ubuntu: preflight only (first)

```bash
DEST="$HOME/ann-task-a/experiments/R86/gate_tools"
mkdir -p "$DEST"
unzip -n "$HOME/Downloads/R86_G1_OFF_Equivalence_v1_0.zip" -d "$DEST"
P="$DEST/R86_G1_OFF_Equivalence_v1_0"
python3 "$P/r86_g1_off_equivalence.py" --preflight 2>&1 | tee "$HOME/R86_G1_preflight.log"
printf 'preflight_exit_code=%s\n' "${PIPESTATUS[0]}"
python3 "$P/r86_g1_off_equivalence.py" --dry-run 2>&1 | tee "$HOME/R86_G1_dry_run.log"
printf 'dry_run_exit_code=%s\n' "${PIPESTATUS[0]}"
```

Expected `R86_G1_PREFLIGHT_PASS_READ_ONLY_NO_GRAPH_BUILD` and `R86_G1_DRY_RUN_PASS_NO_WRITES` with two exact commands. If preflight fails, stop and send the log.

## On Ubuntu: build two NEW R86 BIGANN1M graphs

Only after preflight/dry-run PASS:

```bash
python3 "$P/r86_g1_off_equivalence.py" --run-build 2>&1 | tee "$HOME/R86_G1_build.log"
printf 'build_exit_code=%s\n' "${PIPESTATUS[0]}"
```

Expected **only if the native experiments really match R85**:

`R86_G1_OFF_BUILD_2_GRAPHS_PARTITION_PASS_QUALITY_NOT_YET_EVALUATED /home/tai/.../g1_...`

If it fails, do not delete the session or change H70/H85.

## After the two graphs pass: run native quality (optional separate step)

Use the exact session path printed by `R86_G1_SESSION`:

```bash
SESSION="/home/tai/ann-task-a/experiments/R86/gates/g1_off_bigann1m/g1_..."
python3 "$P/r86_g1_off_equivalence.py" --run-quality "$SESSION" \
  2>&1 | tee "$HOME/R86_G1_quality.log"
printf 'quality_exit_code=%s\n' "${PIPESTATUS[0]}"
```

Then package **small evidence only**:

```bash
python3 "$P/package_g1_evidence.py" --session "$SESSION"
```

Upload the generated `~/R86_G1_Evidence_g1_....tar.gz` for comparison with the R85 original quality logs. The package deliberately does not include binary graph files.

## Tests here

Five synthetic/local tests cover exact manifest command substitution, historical log parsing, mismatch detection, and graph-format validation. They are **not** native R86 tests and do not imply G1 PASS.

```bash
python3 -m unittest discover -s "$P/tests" -v
```

## Status labels

`G0`: PASS from user Ubuntu log, verified by captured `g0_manifest.json`.
`G1-PREFLIGHT`: NOT RUN on Ubuntu until the user runs script.
`G1-NATIVE-BUILD`: NOT RUN.
`G1-QUALITY`: NOT RUN.
`G2/G3`: NOT RUN.
