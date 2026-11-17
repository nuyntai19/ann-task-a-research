#!/usr/bin/env bash
set -euo pipefail
SRC="${1:?Usage: check_and_dry_run.sh /path/to/H70-snapshot [optional_copy_of_logging_kit]}"
KIT="${2:-}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
[[ -f "$SRC/algorithms/PipNN/pipnn.h" ]] || { echo 'NO_H70_SOURCE' >&2; exit 2; }
(
 cd "$SRC"
 sha256sum --check --status "$HERE/EXPECTED_SOURCE_SHA256.txt"
 patch --dry-run --batch -p1 < "$HERE/R86_counter_source_v1_1.patch"
)
if [[ -n "$KIT" ]]; then
 [[ -f "$KIT/scripts/r86_log.py" ]] || { echo 'NO_KIT' >&2; exit 2; }
 (
 cd "$KIT"
 patch --dry-run --batch -p1 < "$HERE/R86_logger_importer.patch"
 patch --dry-run --batch -p1 < "$HERE/R86_logger_registry_v1_1.patch"
 )
fi
echo 'R86_V1_1_SOURCE_SHA_PATCH_DRY_RUN_PASS_NO_WRITES'
