# R86 G0 native executable audit — v1.0

**Scope**: checks source OFF projection (unchanged H70), staging provenance, original source SHA pins, all four compiled CMake binary configurations, SHA256 receipts, compiler/Release flags and ON/OFF binary distinctness. It **does not build, modify H70/H85/R86 binaries, run ANN index, or upload data to Google Sheets**.

No non-standard Python dependencies. It uses the exact paths already established in the user's R86 environment. It writes only into a **new** `~/ann-task-a/experiments/R86/gates/g0_YYYYMMDD_HHMMSS` directory and refuses overwrites. It works from *any* terminal current directory.

## Run on Ubuntu

Download `R86_G0_Native_Audit_v1_0.zip` into `~/Downloads`, then:

```bash
mkdir -p "$HOME/ann-task-a/experiments/R86/gate_tools"
unzip -n "$HOME/Downloads/R86_G0_Native_Audit_v1_0.zip" -d "$HOME/ann-task-a/experiments/R86/gate_tools"
python3 "$HOME/ann-task-a/experiments/R86/gate_tools/R86_G0_Native_Audit_v1_0/r86_g0_native_audit.py"
```

Look for `R86_G0_NATIVE_BINARY_AUDIT_PASS`. If `FAIL`, do not delete source/build dirs. Send the printed output or `g0_readable.log` and `g0_manifest.json`. The script's exit code is 0 on PASS, 1 on FAIL.

### Checked expected configs

| variant | H17 | R86 counters | TwoTier |
| --- | --- | --- | --- |
| stock_off | OFF | OFF | OFF |
| stock_on | OFF | ON | OFF |
| h17_off | ON | OFF | OFF |
| h17_on | ON | ON | OFF |

Reference R85 compiler cache: `/usr/bin/c++`, `Release`, `CMAKE_CXX_FLAGS=''`, `CMAKE_CXX_FLAGS_RELEASE='-O3 -DNDEBUG'`.

**Important:** G0 only proves that the prepared executables match the expected source/build metadata. G1 must still run graph construction/search with pinned R85 CLI and dataset; G2 must test native counters on 10K; G3 must test BIGANN1M. Do not put C++ compilation timings into ANN `T_build_s`.
