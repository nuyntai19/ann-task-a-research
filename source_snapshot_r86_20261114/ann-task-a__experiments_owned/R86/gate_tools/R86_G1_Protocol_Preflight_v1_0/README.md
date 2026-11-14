# R86 G1 — R85 Protocol Preflight (read-only)

G0 has passed according to Ubuntu user output `g0_20261113_011256`.

This tool finds the **pinned historical R85 SCALE1 Python runner**, copies that Python source plus *selected small* R85 manifest/config/log files into a **new R86 evidence directory**, along with G0 manifest. It never executes the historical runner, never reads or copies large vector data or graph files, and never creates ANN indexes. It never modifies any H70/H85 files. The evidence package is required to reconstruct a **new isolated R86 G1 runner with exact known command-line/seed/affinity/data/quality protocol**, rather than guessing flags.

## Ubuntu commands

Download this ZIP to `~/Downloads`, then:

```bash
DEST="$HOME/ann-task-a/experiments/R86/gate_tools"
mkdir -p "$DEST"
unzip -n "$HOME/Downloads/R86_G1_Protocol_Preflight_v1_0.zip" -d "$DEST"
python3 "$DEST/R86_G1_Protocol_Preflight_v1_0/r86_g1_collect_protocol.py" 2>&1 | tee "$HOME/R86_G1_r85_protocol_preflight.log"
```

The tool prints a **new directory path** under `~/ann-task-a/experiments/R86/gates/g1_r85_protocol_YYYYMMDD_HHMMSS`.

Compress ONLY that directory for sharing with ChatGPT, for example replacing the directory name with the exact one printed in terminal:

```bash
DIR="$(grep '^EVIDENCE_DIR ' "$HOME/R86_G1_r85_protocol_preflight.log" | tail -1 | cut -d' ' -f2-)"
test -d "$DIR" || { echo 'PREFLIGHT_DIR_MISSING'; return 1 2>/dev/null || true; }
OUT="$HOME/R86_G1_R85_Protocol_Evidence.tar.gz"
tar -czf "$OUT" -C "$(dirname "$DIR")" "$(basename "$DIR")"
ls -lh "$OUT"
```

Upload `~/R86_G1_R85_Protocol_Evidence.tar.gz`; do not upload `.graph` or base vectors. The script copies at most 35 small manifest/config files and 2 R85 build logs, and prints whether the R85 runner was found. If it cannot locate the script/session, it still creates a diagnostics manifest, and exits nonzero.

**Next stage after review:** new R86 G1 source+binary OFF graph-build calls under a fresh R86-only output directory, then native graph validity and pinned evaluator checks. Keep R85 original artifacts untouched.
