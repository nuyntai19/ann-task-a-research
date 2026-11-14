#!/usr/bin/env bash
set -euo pipefail
SRC="${1:?Usage: check_and_dry_run.sh /path/to/H70-source [path/to/logging-kit]}"
KIT="${2:-}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
(
 cd "$SRC"
 sha256sum -c "$HERE/EXPECTED_SOURCE_SHA256.txt"
 patch -p1 --dry-run --batch < "$HERE/R86_counter_source_v1_2.patch"
)
if [[ -n "$KIT" ]];then
 (
  cd "$KIT"
  patch -p1 --dry-run --batch < "$HERE/R86_logger_importer.patch"
  patch -p1 --dry-run --batch < "$HERE/R86_logger_registry_v1_1.patch"
 )
fi
# G0 strong source parity on a temporary copy of only patch targets. No source writes.
TEMP="$(mktemp -d)"
trap 'rm -rf "$TEMP"' EXIT
mkdir -p "$TEMP/patched/algorithms/PipNN" "$TEMP/patched/algorithms/utils"
for f in algorithms/PipNN/CMakeLists.txt algorithms/PipNN/pipnn.h algorithms/PipNN/pipnn_utils.h algorithms/utils/graph.h; do
 cp "$SRC/$f" "$TEMP/patched/$f"
done
patch -s -d "$TEMP/patched" -p1 --batch < "$HERE/R86_counter_source_v1_2.patch"
python3 "$HERE/scripts/verify_g0.py" --baseline "$SRC" --patched "$TEMP/patched"
echo R86_V1_2_SOURCE_SHA_AND_G0_PASS_NO_H70_WRITES
