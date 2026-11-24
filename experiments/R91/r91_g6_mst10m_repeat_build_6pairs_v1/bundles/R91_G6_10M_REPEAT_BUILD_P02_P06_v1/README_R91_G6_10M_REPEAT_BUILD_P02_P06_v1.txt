R91 G6 10M | Fixed-seed repeated BUILD P02-P06 v1 | frozen original G6 ELF | Search NOT RUN

STATUS AT BUNDLE CREATION (2026-11-24)
- Independent P01 JSON SHA on uploader's data: preflight 1999377c94cd71a5f1bc2cb5a11c6589645985cb033ef1b264b45d10ab1b0c93, pair audit 5844ca60f5ffa3ab01a6d03b23047ddff0982f60d7a8ccd2793416e029fa575c.
- P01 native parent graph SHA C512=614b2fe5e05b168abdd327cb1dbcd731a70ab142deb85e652c9153053fd905ae, C64=45b561197a7c1c1dccb2d2ffc72ca7e89e812ea86225f6263d1d8c2dd673d482, according to user's native full-graph audit.
- Two original P01 build receipts P01 C512 80bc90efdbb41d47d7165e17e684808ddb8adc44c22e8cad66b148724f5590bf, P01 C64 b668a9966bdb6c62ca1a653aae349cedd51250ed32882c0aee1a94a3400f3888. Original receipt bytes/graphs are NOT uploaded here; verified in native preflight on the Ubuntu user host.
- This ZIP has NO Ubuntu native results. Fixture tests are synthetic, never evidence of measured speedup.

RESEARCH PRE-REGISTRATION AND CLAIM LIMITS
  P01: C512 then C64 (native BUILD complete; old output immutable)
  P02: C64 then C512 (next native pair)
  P03: C64 then C512
  P04: C512 then C64
  P05: C512 then C64
  P06: C64 then C512
  Six orders AB/BA/BA/AB/AB/BA are balanced (three starting C512, three C64).
  They are repeated timing runs at fixed source SEED=555, NOT six randomized leader/clustering seeds.
  Work/leaf/fallback per-pass native Stage 1 counters must exactly equal original v1.3 for each cap.
  Graph SHA may differ between runs, but every new graph requires full 10M vertex audit.
  Stage 2 thread-scheduling is a plausible reason for graph SHA differences, NOT a proven unique cause.
  Even all six positive timing differences would give one-sided sign p=1/64 only if fair-sign,
    independent/exchangeable pair assumptions hold; host drift/correlations matter.
  No native Search/Recall or cross-graph quality testing is done by this bundle.

IMMUTABLE INPUTS
  Frozen G6 ELF SHA 53be9510ead14aff25ec5adffc07d959c78d575f7ffcc9306435360ce9342690.
  Original P01 code vendored byte-for-byte SHA 0b363339c5d02e6cf23701074f06d9f0dc83b7a5516550d9a27d1f1951baa216.
  Original v1.3 code vendored byte-for-byte SHA 0e62c69dcf73f499d4c99e3181c526c0d908150ff6e77ca4d1fde4144801cab7.
  Source pipnn.h/hash.h fixed SEED=555 and hash64(SEED) markers rechecked against P01 pinned source SHAs.
  Frozen original G4/G6/code/data/exactguard/parent 10M graphs and calibration are SHA-pinned
    by imported original P01/v1.3 audited code and checked before work.
  No compile or change of native inputs or flags. -r91_g6_d2_cap is 64 or 512 only.

HOST RESOURCES & FAIL-CLOSED CONDITIONS
  CPU taskset=0,2,4,6; PARLAY_NUM_THREADS=4; OMP_NUM_THREADS=4, single BUILD process per scope.
  Each native BUILD arm and audit/preflight runs under distinct systemd --user scopes with
    MemoryMax=25769803776 bytes (24 GiB) and MemorySwapMax=0.
  New extension preflight needs MemAvailable >=22GiB and free disk >=75GiB.
  Each arm start needs MemAvailable >=22GiB, free disk >=55GiB before first and >=48GiB before second.
  Monitor aborts if free disk <38GiB, MemAvailable <1.5GiB, cgroup swap nonzero,
    memory.events max/oom/oom_kill increment, or elapsed >=5400 seconds per arm.
  Any existing output or symlink causes HOLD, never overwrite/retry in that slot.
  A failed arm leaves its receipt/log/graph intact and blocks audit/later pairs.
  P03 requires P02 native audited summary; P04 requires P03, P05 requires P04, P06 requires P05.

NEW ARTIFACTS (inside existing P01 root; P01 remains untouched)
  ~/ann-task-a/experiments/R91/r91_g6_mst10m_repeat_build_6pairs_v1/
    preflight.json                                # ORIGINAL P01, immutable
    pairs/p01/...                                # ORIGINAL P01, immutable
    extension_p02_p06_preflight_v1.json           # NEW preflight, exclusive create
    pairs/p02/arms/C64/{... graph.bin, stdout, stderr, time, receipt}
    pairs/p02/arms/C512/{... graph.bin, stdout, stderr, time, receipt}
    pairs/p02/pair_audit.json
    pairs/p03 ... similarly, then p04/p05/p06
    repeat_6pair_summary.json                    # ONLY after p01-p06 full audits PASS

SAFE OPERATION ORDER (execute only one section at a time, STOP on HOLD)
  1. Download ZIP, verify exact ZIP sha from assistant, extract in a NEW directory,
     run sha256sum -c R91_G6_REPEAT_P02_P06_SHA256SUMS_v1.txt.
  2. bash R91_G6_REPEAT_P02_P06_PREFLIGHT_v1_Ubuntu.sh
     - Python selftest; synthetic fixture suite; scoped 24GiB/zero-swap probe;
       read-only P01 full graph audit and readback; pinned data source;
       then records extension_p02_p06_preflight_v1.json.
     - NO new BUILD and NO new p02-p06 pair directories.
  3. Verify full terminal PASS and extension preflight SHA before starting p02.
  4. For each next pair ONLY after previous pair audited PASS:
     bash R91_G6_REPEAT_P02_P06_RUN_PAIR_v1_Ubuntu.sh p02
     bash R91_G6_REPEAT_P02_P06_AUDIT_PAIR_v1_Ubuntu.sh p02
     # Stop. Inspect P02 results before opening P03.
     # Then do p03, p04, p05, p06 in the registered order.
  5. After all six paired native BUILDs audited PASS:
     bash R91_G6_REPEAT_P02_P06_AGGREGATE_v1_Ubuntu.sh
     # Aggregate produces paired stats and graph SHA inventory; no Search.
  6. Read-only pair readback:
     bash R91_G6_REPEAT_P02_P06_AUDIT_READONLY_v1_Ubuntu.sh p02

SUCCESS CONDITIONS
  PRE: R91_G6_10M_REPEAT_BUILD_P02_P06_V1_PREFLIGHT_PASS_NO_BUILD <sha>
       R91_G6_REPEAT_P02_P06_V1_PREFLIGHT_CHAIN_PASS_NO_BUILD
  P02 BUILD: ...BUILD_GRAPH_WORK_RESOURCE_AUDIT_PASS_p02_C64 and p02_C512
  P02 AUDIT: ...PAIRED_BUILD_FULL_AUDIT_PASS_p02 <sha>
  AGGREGATE: ...SIX_PAIR_AGGREGATE_AUDIT_PASS <sha> (P01-P06 only)

IMPORTANT: This is a fail-closed repeat-build scheduling bundle. An invalid fixture is not a
reason to change any source/file SHA gates in place; STOP and diagnose if validation fails.
