#!/usr/bin/env bash
set -euo pipefail
HERE="$(cd "$(dirname "$0")/.." && pwd)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
for MODE in 1 0; do
  g++ -std=c++17 -O2 -DR86_COUNTERS="$MODE" \
    -I "$HERE/files/algorithms/PipNN" \
    "$HERE/tests/test_counter_header.cpp" -o "$WORK/header_$MODE"
done
R86_COUNTER_OUT="$WORK/events.jsonl" R86_LEAF_SIZE_OUT="$WORK/leaves.jsonl" "$WORK/header_1"
"$WORK/header_0"
python3 - "$WORK" <<'PY'
from pathlib import Path
import json, sys
p=Path(sys.argv[1])
ev=[json.loads(x) for x in (p/'events.jsonl').read_text().splitlines()]
leaves=[json.loads(x) for x in (p/'leaves.jsonl').read_text().splitlines()]
assert any(e['metric_code']=='collision_same_id' and e['observed']==0 for e in ev)
assert any(e['metric_code']=='W_L' and e['depth'] is None and e['observed']==9 for e in ev)
assert leaves==[{'pass_id':1,'depth':None,'size':3}]
print('R86_STATIC_COUNTER_HEADER_PASS')
PY
