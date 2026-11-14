#!/usr/bin/env bash
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
for MODE in 1 0; do
 g++ -std=c++17 -O2 -DR86_COUNTERS="$MODE" -I "$HERE/cpp" "$HERE/tests/test_counter_header.cpp" -o "$WORK/header_$MODE"
done
R86_COUNTER_OUT="$WORK/header_events.jsonl" R86_LEAF_SIZE_OUT="$WORK/header_leaves.jsonl" R86_OCCUPANCY_OUT="$WORK/header_occupancy.json" "$WORK/header_1"
"$WORK/header_0"
python3 - "$WORK/header_events.jsonl" <<'PY'
import json,sys
r=[json.loads(x) for x in open(sys.argv[1])]
assert any(x['metric_code']=='collision_same_id' and x['observed']==0 for x in r)
assert any(x['metric_code']=='hash_moves' and x['observed']==0 for x in r)
assert any(x['metric_code']=='W_L' and x['observed']==9 for x in r)
print('R86_v1_2_ZERO_VS_NOT_MEASURED_PASS')
PY
python3 "$HERE/tests/test_hash_work.py"
echo 'R86_v1_2_SYNTHETIC_STATIC_SUITE_PASS (not a native PiPNN build)'
