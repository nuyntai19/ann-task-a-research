R90-P0A controlled native Highway FTZ/DAZ + Stage1 repeat diagnostic v1
2026-11-19

GOAL
1. Rehash all SIX frozen P0A-v1.1 binary, graph, stdout and time files and source trees.
2. Compile ONE separate tiny C++ witness using the EXACT existing R90 P0A stock_off
   libhwy_contrib.a and libhwy.a (R86 HIGHWAY source cache), SHA-pinned compiler,
   -O3 -march=native -ffast-math. Does not relink/recompile 6 original P0A ELFs.
3. Explicit MXCSR FTZ+DAZ OFF vs ON using 126 paired native cases:
   zero-distance candidate packed at raw bits 0x000000000000000c,
   n=2,8,16,32,64,189,512; one or two subnormal candidates; 3 repeats.
   Compare Highway first-2 with reference uint64 packed keys and scalar H17/Fast
   Top2 analogues, and compare RAW MULTISET OF ALL INPUT/OUTPUT BITS to distinguish
   actual bit mutation from mere reorder/tie behavior.
4. Re-run each of the 3 existing OFF executables (Stock/H17/Fast) THREE times on
   SIFT10K with taskset CPU0 one thread, writing 9 NEW graph/logs ONLY to a NEW
   output directory. Parse buckets per clustering pass, cumulative clustering
   comparisons, and SHA of each new graph. Do NOT claim graph SHA is a leaf
   membership fingerprint. Actual leaf membership requires instrumentation.

CRITICAL LIMITATIONS
A witnessed synthetic Highway bit mutation does NOT automatically prove why
historic Stock lost specific graph neighbors. Stage1 bucket-count drift does not
prove randomized pivot cause. No Recall@10 tested in this bundle. This
bundle DOES NOT authorize P0A-v1.1 full1m/audit1m and does not run any 1M/10M BUILD.
Original 6 P0A-v1.1 binaries, source, graphs, stdout and timefiles are READ ONLY.
No old logs should be deleted or modified. No GitHub writes.

DELIVERY
Save R90_P0A_FTZ_STAGE1_PROBE_v1_BUNDLE.zip in ~/Downloads then:
  unzip -n "$HOME/Downloads/R90_P0A_FTZ_STAGE1_PROBE_v1_BUNDLE.zip" -d "$HOME/Downloads"
  bash "$HOME/Downloads/R90_P0A_FTZ_STAGE1_PROBE_v1_Ubuntu.sh"

PREREQUISITES
The original P0A-v1.1 compile and 6 SIFT10K pilot BUILD artifacts must still
exist untouched, including original v1.1 Python in ~/Downloads. The previous
read-only diagnostic report must remain at its original path and SHA.
Original HIGHWAY source cache & P0A stock_off compiled .a archives must exist.
Only standard g++, Python3, taskset, /usr/bin/time are used. No sudo/network.

OUTPUTS
  ~/ann-task-a/experiments/R90/r90_p0a_ftz_stage1_probe_v1/probe_report.json
  ~/ann-task-a/experiments/R90/r90_p0a_ftz_stage1_probe_v1/logs/highway_probe.stdout
  ~/R90_P0A_FTZ_STAGE1_NATIVE_PROBE_v1.log
Send probe_report.json and run log. On HOLD, preserve all outputs and send
compile log / stdout: never manually bypass SHA or delete existing evidence.

EXPECTED LIFECYCLE
  SELFTEST PASS -> ORIGINAL SIX ARTIFACTS + EXACT ARCHIVES SHA PREFLIGHT PASS
  -> COMPILE TINY PROBE -> RUN CONTROLLED MXCSR PAIRS
  -> NINE SIFT10K ONLY REBUILDS -> REPORT -> AUDIT PASS

A PASS means diagnostic execution is valid, NOT Full1M quality readiness.
