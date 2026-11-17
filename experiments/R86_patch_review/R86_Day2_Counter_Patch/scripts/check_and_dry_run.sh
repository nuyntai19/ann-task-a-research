#!/usr/bin/env bash
set -euo pipefail
BASE="${1:?Usage: check_and_dry_run.sh /path/to/isolated/R86/source}"
HERE="$(cd "$(dirname "$0")/.." && pwd)"
if [[ ! -f "$BASE/algorithms/PipNN/pipnn.h" ]]; then
  echo 'R86_SOURCE_GATE_FAIL missing pipnn.h' >&2; exit 2
fi
for line in \
 'f4391ad8712d7757423dca872f9042c3271660dffde384a85b93854b9692f288  algorithms/PipNN/pipnn.h' \
 '7083e8183554a1cb586b70cdb4c57920f49ec5a50680096aecf6b873f596595d  algorithms/PipNN/pipnn_utils.h' \
 '29293c2a6210db7c666db1f4589ecbfc0c8864ac57f07b743fa33797931bc1ef  algorithms/PipNN/neighbors.h' \
 '17e51779f32db56c9c50b6d514a8ff68539fd19b734804df3abdb63f88dd443e  algorithms/utils/graph.h'; do
  (cd "$BASE" && printf '%s\n' "$line" | sha256sum --check --status) || { echo "R86_SOURCE_GATE_FAIL $line" >&2; exit 2; }
done
(cd "$BASE" && patch --dry-run --batch -p1 < "$HERE/R86_counter_source.patch")
echo 'R86_SOURCE_HASH_AND_PATCH_DRY_RUN_PASS (no writes)'
