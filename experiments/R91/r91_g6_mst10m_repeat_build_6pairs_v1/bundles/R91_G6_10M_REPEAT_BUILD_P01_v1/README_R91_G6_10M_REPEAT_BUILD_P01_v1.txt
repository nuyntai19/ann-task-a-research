R91 G6 MS-Turing10M | REPEATED PAIRED BUILD | PILOT PAIR 01 ONLY | v1
Prepared 2026-11-24; local-only validation, no Ubuntu native BUILD executed by this bundle's author.

SCIENTIFIC PRE-REGISTRATION
  The full repeated-design order is deliberately balanced by first-run arm:
    P01 C512->C64
    P02 C64->C512
    P03 C64->C512
    P04 C512->C64
    P05 C512->C64
    P06 C64->C512
  This bundle executes ONLY P01. Further pairs need separately validated runner artifacts.
  Same frozen G6 ELF (sha256 53be9510ead14aff25ec5adffc07d959c78d575f7ffcc9306435360ce9342690).
  Inputs and all original build flags copied byte-for-byte from the successful v1.3 runner.
  Only cap option differs: -r91_g6_d2_cap=512 vs =64 at depth2.
  Four CPU affinity: 0,2,4,6, PARLAY_NUM_THREADS=4, OMP_NUM_THREADS=4.
  Each native arm has systemd-run user scope MemoryMax=25769803776 (24GiB), MemorySwapMax=0.
  Native process timeout 5400s; abort on memory max/oom events, swap, 1.5GiB low host
    MemAvailable or free disk <38GiB. Start disk gate >=55GiB and before second arm >=48GiB.
  Stage-1 expected fixed-seed behavior is the research hypothesis and source inspection claim:
    SEED = 555 / hash64(SEED) source markers are CHECKED during native preflight.
    hash.h SHA recorded; SketchHash identifier reported, not used as an exhaustive proof.
    Exact per-pass Stage1 work / cap / leaf / fallback counter parity with v1.3 is
      mandatory; mismatch is HOLD, not silently called 'fixed-seed'.
  No claim of six independent randomized leader-seed graphs or statistically independent graph samples.
  Stage2 multithread scheduling is a plausible cause of graph SHA variation, NOT uniquely proven.
  Six all-faster results would yield 1-sided sign probability 1/64 only under
    the pre-registered direction and independent, exchangeable fair-sign null;
    do not treat small n or correlated machine effects as settled statistical evidence.

SOURCE LINEAGE AND IMMUTABILITY
  Original v1.3 frozen runner source is vendored byte-identically:
    vendor_r91_g6_mst10m_pair_v1_3.py SHA256
    0e62c69dcf73f499d4c99e3181c526c0d908150ff6e77ca4d1fde4144801cab7
  It provides proven original native CLI, strict parse_native, parse_stage, graph_audit,
    parse_time, resource_pass, original original G4+G6 inputs and SHA pins.
  Original parent BUILD/Search/preflight and C512/C64 receipt SHA pins are checked.
  Parent source graphs C512/C64 each 10M 2.2 GB are SHA-checked before native work.
  Matched Recall 10-beam preflight + summary are also pinned and read-only.
  Both new graphs built in new root; no old graph is reused as output or modified.

NEW ROOT (NO OVERWRITE, NO RESTART IN AN EXISTING SLOT)
  ~/ann-task-a/experiments/R91/r91_g6_mst10m_repeat_build_6pairs_v1/
    preflight.json
    pairs/p01/arms/C512/{graph.bin,native.stdout,native.stderr,native.time,preregister.json,receipt.json}
    pairs/p01/arms/C64/{graph.bin,native.stdout,native.stderr,native.time,preregister.json,receipt.json}
    pairs/p01/pilot_pair_audit.json
  All other pair roots P02-P06 remain NOT_RUN. Historical v1.1/v1.2/v1.3 untouched.

EXECUTION (ubuntu; stop and preserve any HOLD)
  1. Download ZIP to ~/Downloads; verify SHA256 provided separately by assistant.
  2. Extract under fresh isolated ~/Downloads/R91_G6_10M_REPEAT_BUILD_P01_V1_ISOLATED
     with mkdir -m700, unzip without overwrite, sha256sum -c manifest.
  3. bash R91_G6_REPEAT_P01_PREFLIGHT_v1_Ubuntu.sh
      - Python selftest; cgroup scopecheck; source seed markers; all pins; RAM/disk;
      - CREATE ONLY preflight.json. Native BUILDS NOT STARTED.
  4. Verify native preflight PASS / exit0 and preflight JSON SHA; THEN
     bash R91_G6_REPEAT_P01_PILOT_v1_Ubuntu.sh
      - builds C512 then C64 in separate 24GiB zero-swap cgroups.
      - EACH output is fully graph-audited in scope and stage1 counters matched
        against reference; C512 receipt must pass before starting C64.
  5. Only after two native arms PASS, bash R91_G6_REPEAT_P01_AUDIT_v1_Ubuntu.sh
      - full graph audit (again) and receipt/log SHA recheck in its OWN 24GiB scope;
      - pair summary compares wall, bucket/leaf/prune stage times, RAM, deep WP,
        fallback and graph SHA, with explicit evidence limits.
  6. Readonly subsequent audit: R91_G6_REPEAT_P01_AUDIT_READONLY_v1_Ubuntu.sh

LOCAL VALIDATION
  - Python compile, module/source selftest, all four Bash syntax, manifest SHA checks.
  - No source/ELF edits or compilation, no native 10M BUILD made in package preparation.

IMPORTANT LIMITATIONS
  - Requires original Ubuntu host environment, original pinned R91 G4/G6 data and source.
  - If pipnn.h source markers are missing due to different local source layout,
    preflight FAILS CLOSED without BUILD; do not bypass/patch the gate in-place.
  - Native run may be blocked if host MemAvailable <22 GiB or free disk <55GiB.
  - One pilot pair by itself cannot demonstrate timing significance or multiseed graph variance.
  - This pilot produces new graphs; Search/quality of these new graphs is NOT tested here.
  - Do NOT create or overwrite outputs for P02-P06 with this pilot runner.
