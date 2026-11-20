R90-P0A Pilot10K graph parity HOLD -- READ-ONLY diagnostic v1

Purposes:
  1) SHA audit preexisting 6 source trees, 6 binaries, 6 graphs, stdout/timefiles and manifests.
  2) Parse both build passes' Total buckets/points/clustering comparisons from original stdout.
  3) Report graph edge-set differences and selected L2 neighbor geometry for nodes 2,15,746,2887.
  4) Demonstrate IEEE bit encoding of packFloatAndInt(0,12) as subnormal binary64.

NOT a proof by itself of the actual root cause: Highway SIMD FTZ/DAZ bit loss,
random pivot seed selection, and the claimed 53 edge anomalies require a separate
controlled MXCSR+Highway probe and/or native scratch receipts.

NOT a new BUILD, not a Search, not a waiver of auditpilot or audit1m.
DO NOT call original P0A v1.1 full1m/audit1m as long as pilot_audit.json is absent.

Copy BOTH files to ~/Downloads:
  r90_p0a_v11_pilot_hold_diagnostic_v1.py
  R90_P0A_V11_PILOT_HOLD_READONLY_DIAGNOSTIC_v1_Ubuntu.sh
Run:
  bash "$HOME/Downloads/R90_P0A_V11_PILOT_HOLD_READONLY_DIAGNOSTIC_v1_Ubuntu.sh"

Script SHA256: e2714a0e9ab66531c4e8c72a6c0fc457696062e189a4a6d04ad984b848e9acb2

Output (new only):
  ~/ann-task-a/experiments/R90/r90_p0a_v11_pilot_hold_diagnostic_v1/diagnostic_report.json
  ~/ann-task-a/experiments/R90/r90_p0a_v11_pilot_hold_diagnostic_v1/graph_pair_differences.csv
  ~/R90_P0A_V11_PILOT_HOLD_DIAGNOSTIC_V1.log

If any HOLD, preserve old/new files and send log. Never delete/patch old manifests.
