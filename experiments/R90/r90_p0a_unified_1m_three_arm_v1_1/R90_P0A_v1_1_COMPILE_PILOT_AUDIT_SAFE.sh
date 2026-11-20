#!/usr/bin/env bash
# R90-P0A v1.1 -- compile six same-source OFF/ON variants; run 10K pilot and audit.
# This command NEVER runs full1m or modifies previous R90 evidence.
# If a gate fails, preserve logs/output and do not rerun blindly.
set -uo pipefail
F="$HOME/Downloads/r90_p0a_unified_1m_three_arm_v1_1.py"
EXPECTED_F="fa9cdc09b3f447161f5c1f65382b15a0bc9645f425a679b73ca26f5ce8abecf0"
OUT="$HOME/ann-task-a/experiments/R90/r90_p0a_unified_1m_three_arm_v1_1"
MANIFEST="$OUT/source_manifest.json"
EXPECTED_MANIFEST="6e5d82c4ca331476240950afedfad970d8358fc7252d0d2b8b9ac441e1afb298"
LOG="$HOME/R90_P0A_V11_COMPILE_PILOT_AUDIT.log"

echo '===== R90 P0A V1.1 COMPILE SIX + PILOT10K + AUDIT (NO 1M BUILD) ====='
if [[ ! -f "$F" || -L "$F" ]] || [[ "$(sha256sum "$F" | awk '{print $1}')" != "$EXPECTED_F" ]]; then
  echo 'R90_P0A_V11_SCRIPT_SHA_HOLD'
elif [[ ! -f "$MANIFEST" || -L "$MANIFEST" ]] || [[ "$(sha256sum "$MANIFEST" | awk '{print $1}')" != "$EXPECTED_MANIFEST" ]]; then
  echo 'R90_P0A_V11_SOURCE_MANIFEST_SHA_HOLD'
elif [[ -e "$LOG" || -L "$LOG" ]]; then
  echo 'R90_P0A_V11_COMPILE_LOG_EXISTS_HOLD'
elif [[ -e "$OUT/compile_manifest.json" || -L "$OUT/compile_manifest.json" || -e "$OUT/pilot_manifest.json" || -L "$OUT/pilot_manifest.json" || -e "$OUT/pilot_audit.json" || -L "$OUT/pilot_audit.json" ]]; then
  echo 'R90_P0A_V11_PHASE_MANIFEST_EXISTS_HOLD'
elif [[ ! -d "$OUT/source" || ! -d "$OUT/logs" || ! -d "$OUT/build" || ! -d "$OUT/graphs" ]] || \
     [[ -n "$(find "$OUT/logs" "$OUT/build" "$OUT/graphs" -mindepth 1 -print -quit 2>/dev/null)" ]]; then
  echo 'R90_P0A_V11_COMPILE_OUTPUT_NOT_CLEAN_HOLD'
else
  (
    set -euo pipefail
    # Recheck every source tree/fingerprint before any compiler call.
    python3 - "$F" "$MANIFEST" <<'PY'
import importlib.util, json, sys
from pathlib import Path
script = Path(sys.argv[1])
manifest = Path(sys.argv[2])
spec = importlib.util.spec_from_file_location('r90_p0a_v11_local_checked', script)
assert spec is not None and spec.loader is not None
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
m = json.loads(manifest.read_text())
assert m['status'] == 'SOURCE_6_VARIANTS_PREPARED__NO_COMPILE_NO_BUILD'
assert len(m['variants']) == 6
assert {x['variant'] for x in m['variants']} == {
    'stock_off','h17_off','fast_off','stock_on','h17_on','fast_on'
}
assert m['input']['allowed_source_links'] == module.ALLOWED_LINKS
assert m['input']['source_tree_sha256'] == module.digest_tree(module.BASE_SOURCE)
for record in m['variants']:
    root = module.OUT / 'source' / record['variant']
    assert module.digest_tree(root) == record['tree_sha256'], record['variant']
    assert module.sha(module.header(root)) == record['utils_sha256']
    assert module.sha(module.main_h(root)) == record['pipnn_sha256']
    assert record['base_source_sha256'] == m['input']['source_tree_sha256']
print('R90_P0A_V11_SIX_SOURCE_REHASH_AND_LINK_GATE_PASS', flush=True)
PY
    python3 "$F" compile
    python3 "$F" pilot10k
    python3 "$F" auditpilot
    echo 'R90_P0A_V11_COMPILE_PILOT_AUDIT_SEQUENCE_COMPLETE'
  ) 2>&1 | tee "$LOG"
  RC=${PIPESTATUS[0]}
  echo "R90_P0A_V11_COMPILE_PILOT_EXIT_CODE=$RC"
fi
printf '%s\n' TERMINAL_SAFE_END
