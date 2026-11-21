R91 — MS-Turing10M, G0.6/G0.7 and ONE guarded G1 native BUILD
2026-11-20. One-shot experimental bundle, WITHOUT network access or source edits.

CONFIRMED FROM USER UBUNTU BEFORE BUNDLE
- SHA256 -c base/query/GT from MSTuring_10M_v1 all 3 returned OK.
- User systemd-run --user --scope confirmed memory.max=25769803776
  (24 GiB) and memory.swap.max=0 on cgroup v2.
- Host MemAvailable ~25.98 GiB and disk ~41 GB at that past timestamp.
- R90 v1.3 old Highway 6bc2d477 Fast v2 OFF 1M quality/build passed.
  This runner does NOT edit any old R85/R90 data or run any compilations.

WHAT IT CONTAINS
  r91_g06_twotier_readonly_v1.py
  r91_g07_g1_mst10m_hardcap_v1.py
  R91_G06_TWOTIER_READONLY_v1_Ubuntu.sh
  R91_G07_MST10M_PREFLIGHT_v1_Ubuntu.sh
  R91_G1_ONE_FASTV2_MST10M_24G_NOSWAP_v1_Ubuntu.sh

RUN IN THIS ORDER
  unzip -n ~/Downloads/R91_G06_G07_G1_H85_MST10M_24G_BUNDLE_v1.zip -d ~/Downloads

  # STEP 1. Read-only TwoTier source+1M degree histogram, NO 10M build.
  bash ~/Downloads/R91_G06_TWOTIER_READONLY_v1_Ubuntu.sh

  # STEP 2. Rehash all original v1.3 1M evidence/source/ELF and all three
  # 10M dataset files, scan GT ID bounds; check exact 24G/no-swap in a
  # NEW systemd-run dry scope and resource/CPU/disk gate. NO 10M build.
  bash ~/Downloads/R91_G07_MST10M_PREFLIGHT_v1_Ubuntu.sh

  # STEP 3. ONLY if G0.7 shows exit0 and new preflight receipt PASS,
  # and researcher approves the resource/quality risk:
  bash ~/Downloads/R91_G1_ONE_FASTV2_MST10M_24G_NOSWAP_v1_Ubuntu.sh

G0.6 OUTPUT, new only:
  ~/ann-task-a/experiments/R91/r91_g06_twotier_degree_audit_v1/
    r91_g06_twotier_readonly_report.json
  ~/R91_G06_TWOTIER_READONLY_v1.log
  The ratio >64 comes from BOTH pinned 1M .degrees_pass2.u32le binary files,
  not unverified Gemini summary. Source snippets must still be reviewed for
  exact promotion/free lifetime. Reports 10M memory MODEL, not measured RSS.

G0.7 OUTPUT, new only:
  ~/ann-task-a/experiments/R91/r91_g07_mst10m_flat_c160_preflight_v1/
    r91_g07_preflight.json
  ~/R91_G07_MST10M_PREFLIGHT_v1.log
  If a filename/sha/source/provenance differs, this tool HOLDs; DO NOT edit SHA
  constants or delete/rewrite old artifacts. No 10M BUILD in G0.7.

G1 OUTPUT, only after G0.7 PASS:
  ~/ann-task-a/experiments/R91/r91_g1_one_fastv2_flat_c160_mst10m_24g_v1/
    pilot_preregister.json
    r91_g1_single10m_result.json (if in-scope supervisor survives OOM)
    cgroup_scope_path.txt
    graphs/MSTuring10M_fast_off_C160_K1024_N2.graph
    logs/MSTuring10M_fast_off_C160_K1024_N2.stdout
    logs/MSTuring10M_fast_off_C160_K1024_N2.time
  ~/R91_G1_ONE_FASTV2_MST10M_24G_NOSWAP_v1.log
  ~/R91_G1_OUTSIDE_CGROUP_MONITOR_v1.tsv (outside scope: survives cgroup kill)
  Persistent stage1/stage2/final-prune counters, GNU time wall+maxRSS+major
  faults, df-h before/after, host vmstat before/after, cgroup memory.peak,
  memory.events oom_kill/max, memory.swap.current, cgroup OOM failure status.
  If G1 succeeds, validates all 10M adjacency ID ranges, selfloops,
  duplicate neighbor rows and SHA graph. NO Search/QPS in this bundle.

SAFETY
- Builder MUST run inside exact kernel cgroup memory.max=25769803776 and
  memory.swap.max=0. Otherwise pre-build HOLD. No global swapoff and no sudo.
- In-flight abort when host MemAvailable stays <1.5 GiB for 2 checks,
  disk free <8 GiB, or cgroup swap.current >0. Starting gate requires
  MemAvailable >=25.5 GiB, disk free >=15 GiB and 4 pinned CPUs.
- A process that reaches 24 GiB can be killed by cgroup OOM. This is
  permitted as a measured LIMIT outcome, not as success. System performance
  can still degrade before hitting the limit; avoid other heavy tasks.
- One graph only. No auto-resume / retries; after partial crash DO NOT
  rerun or remove output. Preserve entire directory and logs for diagnosis.
- No 10M Recall/QPS claim until a G1 graph passes and a later evaluator runs
  exact 100K query/GT at the target Recall thresholds.
- Any confidence about TwoTier memory savings on MS10M must be earned from
  source + degree audit; R85 BIGANN1M TwoTier gains do NOT generalize.

IMPORTANT:
The original R90 native_one() has a fixed graph header check for 1M and
cannot be called for 10M. The new pilot reuses ONLY its byte-pinned Fast OFF
binary and EXACT 24 canonical flags; it handles the 10M graph separately.
On G1 OOM, any incomplete .graph is EVIDENCE and must remain untouched.
