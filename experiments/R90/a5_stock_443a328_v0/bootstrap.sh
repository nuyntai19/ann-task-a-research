#!/usr/bin/env bash
set -euo pipefail
HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROOT="${1:-$HOME/ann-task-a/experiments/R90/a5_stock_443a328_v0}"
UP="443a328dc71a3b7be753d52ca2b3c9a4ba77f3fd"
if [[ -e "$ROOT" ]]; then echo "R90_DEST_EXISTS_HOLD"; exit 2; fi
command -v git >/dev/null || { echo "R90_GIT_MISSING_HOLD"; exit 2; }
mkdir -p "$ROOT"
git clone --quiet https://github.com/ParAlg/PiPNN.git "$ROOT/stock"
git -C "$ROOT/stock" checkout --quiet --detach "$UP"
if [[ "$(git -C "$ROOT/stock" rev-parse HEAD)" != "$UP" ]]; then
    echo "R90_UPSTREAM_HEAD_HOLD"; exit 2
fi
if [[ -n "$(git -C "$ROOT/stock" status --porcelain)" ]]; then
    echo "R90_STOCK_TREE_DIRTY_HOLD"; exit 2
fi
cp -a "$ROOT/stock" "$ROOT/a5"
cp "$HERE/algorithms/PipNN/pipnn.h" "$ROOT/a5/algorithms/PipNN/pipnn.h"
cp "$HERE/algorithms/PipNN/CMakeLists.txt" "$ROOT/a5/algorithms/PipNN/CMakeLists.txt"
git -C "$ROOT/a5" diff --check
git -C "$ROOT/a5" diff --name-only | LC_ALL=C sort > "$ROOT/modified_files.txt"
printf '%s\n' 'algorithms/PipNN/CMakeLists.txt' 'algorithms/PipNN/pipnn.h' > "$ROOT/expected_modified_files.txt"
if ! cmp -s "$ROOT/modified_files.txt" "$ROOT/expected_modified_files.txt"; then
    echo "R90_UNEXPECTED_DIFF_HOLD"; exit 2
fi
(
  cd "$ROOT/a5"
  sha256sum algorithms/PipNN/pipnn.h algorithms/PipNN/CMakeLists.txt
) > "$ROOT/patched_sha256.txt"
echo "R90_STOCK_AND_A5_LOCAL_SOURCE_COPY_TWO_FILE_DIFF_PASS"
echo "R90_CPP_NATIVE_BUILD_NOT_RUN"
echo "STOCK=$ROOT/stock"
echo "A5=$ROOT/a5"
