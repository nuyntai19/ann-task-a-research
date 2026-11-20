R90-P0A v1.1 — STRICT INTERNAL SYMLINK REPAIR + SAME-R86 HIGHWAY
Date: 2026-11-19

Bug in v1: digest_tree() rejected two *legitimate relative* ParlayANN links:
  data_tools/utils  -> ../algorithms/utils
  rangeSearch/utils -> ../algorithms/utils
v1 also dereferenced symlink targets on copy. v1.1 validates precisely those
link paths+literal target strings+their resolved in-tree directory. No other
symlinks are accepted. copytree(...,symlinks=True) preserves original links;
source tree fingerprints include each relative link and its literal target.

HIGHWAY dependency is pinned to the same R86 v1_2 stock_off build cache as
PARLAYLIB/EIGEN/ABSEIL-CPP/GOOGLEBENCHMARK. If missing, HOLD, do not substitute.

Stock ON source counters:
- stock_candidates_derived_from_q_writes / stock_pack_calls_derived_from_q_writes
  are EXACT SAME VALUE AS measured top2_q_writes, derived by invariant:
  one packFloatAndInt + one Q.push_back per j != i in Stock leaf loop.
  These are NOT independent Pack hardware/instrumented call counters.
- stock_partial_sort_calls_source_count is directly counted by R86.
- Highway internal comparisons, shuffles, moves and scalar assignments remain
  NOT_MEASURED: R86 enum declarations alone do NOT count executed events.

LOCAL status: Python syntax + synthetic strict symlink selftest PASS;
Ubuntu source tree, dependency hashes and native compile/pilot NOT VERIFIED.

FILES:
 - r90_p0a_unified_1m_three_arm_v1_1.py SHA256 fa9cdc09b3f447161f5c1f65382b15a0bc9645f425a679b73ca26f5ce8abecf0
 - r90_p0a_unified_1m_three_arm_v1_1_Ubuntu_PREPARE_ONLY.sh

FIRST STEP ONLY: place files in ~/Downloads, run:
 bash "$HOME/Downloads/r90_p0a_unified_1m_three_arm_v1_1_Ubuntu_PREPARE_ONLY.sh"
This invokes selftest + preflight + prepare. No CMake/no BUILD/no Search.
It writes new OUT = ~/ann-task-a/experiments/R90/r90_p0a_unified_1m_three_arm_v1_1
and NEW LOG = ~/R90_P0A_UNIFIED_SOURCE_PREPARE_ONLY_v1_1.log.
Never delete or overwrite old v1 log. On HOLD preserve everything.

NEXT phases are intentionally NOT invoked by wrapper:
 python3 "$HOME/Downloads/r90_p0a_unified_1m_three_arm_v1_1.py" compile
 python3 "$HOME/Downloads/r90_p0a_unified_1m_three_arm_v1_1.py" pilot10k
 python3 "$HOME/Downloads/r90_p0a_unified_1m_three_arm_v1_1.py" auditpilot
 ... then, only after native auditpilot PASS: full1m / audit1m.
The six variants must share same compiler SHA and all six 10K graph SHA parity.

PERF (OPTIONAL, separate independent experiment ONLY after same-source OFF
binary compile + source pilot): perf_event_paranoid=4 denies unprivileged
perf stat. Do not change kernel sysctls or run sudo in this wrapper. If the
user manually grants perf access, use isolated OFF binaries and identical
workloads to measure instructions, cycles, branches, cache-references, etc.
Those are process-wide CPU events, NOT exact Highway comparator/assignment counts.

SAFETY: never run full 1M/10M automatically. No GitHub push.
