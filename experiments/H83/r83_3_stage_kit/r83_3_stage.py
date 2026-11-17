#!/usr/bin/env python3
"""R83.3: stage an isolated source-only Compact Fanout variant.

No ANN build, compiler, graph, dataset, Git mutation, or modification to H70.
Requires exact H70 working-tree source hashes seen in R81.3.
"""
from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import subprocess
import sys
from pathlib import Path

COMMIT = "443a328dc71a3b7be753d52ca2b3c9a4ba77f3fd"
EXPECTED = {
    "algorithms/PipNN/pipnn.h": "f4391ad8712d7757423dca872f9042c3271660dffde384a85b93854b9692f288",
    "algorithms/PipNN/pipnn_utils.h": "7083e8183554a1cb586b70cdb4c57920f49ec5a50680096aecf6b873f596595d",
}


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def once(s: str, old: str, new: str, tag: str) -> str:
    c = s.count(old)
    if c != 1:
        raise RuntimeError(f"R83_3_ANCHOR_MISMATCH {tag} expected=1 found={c}")
    return s.replace(old, new, 1)


def transform_utils(s: str) -> str:
    s = once(s, "template <class PR, class Bucket>\nvoid assign_leaders(",
             "template <class PR, class Bucket, class R83Output>\nvoid assign_leaders(", "utils-template")
    s = once(s, "parlay::sequence<std::pair<uint32_t,uint32_t>>& flat,",
             "R83Output& flat,", "utils-type")
    old = "flat[(start + ti)*fanout + fn] = std::make_pair(pairs[fn].second, ids[start + ti]);"
    new = ("#if defined(R83_COMPACT_FANOUT)\n"
           "        // Same selected leader and slot order; source ID is reconstructed during grouping.\n"
           "        flat[(start + ti)*fanout + fn] = static_cast<uint16_t>(pairs[fn].second);\n"
           "#else\n"
           "        flat[(start + ti)*fanout + fn] = std::make_pair(pairs[fn].second, ids[start + ti]);\n"
           "#endif")
    return once(s, old, new, "utils-store")


def transform_pipnn(s: str) -> str:
    s = once(s,
             "parlay::sequence<std::pair<uint32_t, uint32_t>> flat(ids.size() * fanout);",
             ("#if defined(R83_COMPACT_FANOUT)\n"
              "    // MAX_NUM_LEADERS is capped at 512 in the pinned source.\n"
              "    CHECK(leaders.size() <= 65535);\n"
              "    parlay::sequence<uint16_t> compact(ids.size() * fanout);\n"
              "#else\n"
              "    parlay::sequence<std::pair<uint32_t, uint32_t>> flat(ids.size() * fanout);\n"
              "#endif"), "pipnn-allocation")
    s = once(s,
             "assign_leaders(Points, ids, leaders, fanout, flat, granularity);",
             ("#if defined(R83_COMPACT_FANOUT)\n"
              "    assign_leaders(Points, ids, leaders, fanout, compact, granularity);\n"
              "#else\n"
              "    assign_leaders(Points, ids, leaders, fanout, flat, granularity);\n"
              "#endif"), "pipnn-assign")
    s = once(s,
             "parlay::sequence<Bucket> clusters =\n        parlay::group_by_index(flat, leaders.size());",
             ("#if defined(R83_COMPACT_FANOUT)\n"
              "    // Reconstruct the original (leader-index, point-ID) stream without an 8B pair array.\n"
              "    // The compact buffer is kept alive throughout group_by_index.\n"
              "    auto reconstructed = parlay::delayed_tabulate(compact.size(), [&](size_t k) {\n"
              "      return std::make_pair(static_cast<uint32_t>(compact[k]), ids[k / fanout]);\n"
              "    });\n"
              "    parlay::sequence<Bucket> clusters =\n"
              "        parlay::group_by_index(reconstructed, leaders.size());\n"
              "#else\n"
              "    parlay::sequence<Bucket> clusters =\n"
              "        parlay::group_by_index(flat, leaders.size());\n"
              "#endif"), "pipnn-group")
    return s


def transform_cmake(s: str) -> str:
    s = once(s,
             'option(R70_USE_TIER "R70 Two-Tier physical reservoir; logical C unchanged" OFF)',
             ('option(R70_USE_TIER "R70 Two-Tier physical reservoir; logical C unchanged" OFF)\n'
              'option(R83_COMPACT_FANOUT "R83 Compact 16-bit assignment buffer; test only" OFF)'),
             "cmake-option")
    s = once(s,
             '        if(R70_USE_TIER)\n            target_compile_definitions(${TARGET_NAME} PRIVATE R70_TWO_TIER=1)\n        endif()',
             ('        if(R70_USE_TIER)\n'
              '            target_compile_definitions(${TARGET_NAME} PRIVATE R70_TWO_TIER=1)\n'
              '        endif()\n'
              '        if(R83_COMPACT_FANOUT)\n'
              '            target_compile_definitions(${TARGET_NAME} PRIVATE R83_COMPACT_FANOUT=1)\n'
              '        endif()'),
             "cmake-definition")
    return s


def selftest() -> None:
    u = ("template <class PR, class Bucket>\nvoid assign_leaders(\n"
         "parlay::sequence<std::pair<uint32_t,uint32_t>>& flat,\n"
         "flat[(start + ti)*fanout + fn] = std::make_pair(pairs[fn].second, ids[start + ti]);\n")
    h = ("parlay::sequence<std::pair<uint32_t, uint32_t>> flat(ids.size() * fanout);\n"
         "assign_leaders(Points, ids, leaders, fanout, flat, granularity);\n"
         "parlay::sequence<Bucket> clusters =\n        parlay::group_by_index(flat, leaders.size());\n")
    c = ('option(R70_USE_TIER "R70 Two-Tier physical reservoir; logical C unchanged" OFF)\n'
         '        if(R70_USE_TIER)\n            target_compile_definitions(${TARGET_NAME} PRIVATE R70_TWO_TIER=1)\n        endif()\n')
    a, b, d = transform_utils(u), transform_pipnn(h), transform_cmake(c)
    assert "R83Output& flat" in a and "R83_COMPACT_FANOUT" in a
    assert "ids[k / fanout]" in b and "#else" in b
    assert "option(R83_COMPACT_FANOUT" in d
    for func, text in ((transform_utils, u), (transform_pipnn, h), (transform_cmake, c)):
        try:
            func(text + text)
        except RuntimeError:
            continue
        raise AssertionError("duplicate anchor not rejected")
    print("R83_3_SYNTHETIC_PATCHER_SELFTEST_PASS")


def run(root: Path):
    base = root / "experiments/H70/pipnn-clean-443a328"
    out = root / "experiments/H83/r83_3_source_stage"
    cp = subprocess.run(["git", "-C", str(base), "rev-parse", "HEAD"],
                        text=True, capture_output=True, check=True)
    if cp.stdout.strip() != COMMIT:
        raise RuntimeError("R83_3_PINNED_GIT_COMMIT_MISMATCH")
    print("R83_3_PINNED_GIT_COMMIT_PASS")

    original = {}
    targets = list(EXPECTED) + ["algorithms/PipNN/CMakeLists.txt"]
    for rel in targets:
        path = base / rel
        payload = path.read_bytes()
        if rel in EXPECTED and sha(payload) != EXPECTED[rel]:
            raise RuntimeError(f"R83_3_PINNED_FILE_SHA_MISMATCH {rel} observed={sha(payload)}")
        original[rel] = payload.decode("utf-8")
    print("R83_3_PINNED_WORKTREE_SOURCE_PASS")

    updated = {
        "algorithms/PipNN/pipnn.h": transform_pipnn(original["algorithms/PipNN/pipnn.h"]),
        "algorithms/PipNN/pipnn_utils.h": transform_utils(original["algorithms/PipNN/pipnn_utils.h"]),
        "algorithms/PipNN/CMakeLists.txt": transform_cmake(original["algorithms/PipNN/CMakeLists.txt"]),
    }
    if out.exists():
        raise RuntimeError(f"R83_3_OUTPUT_ALREADY_EXISTS_FAIL_CLOSED {out}")
    # Do not create any output until every source anchor and hash has passed.
    out.mkdir(parents=True, exist_ok=False)
    diff_all = []
    manifest = {"status": "STAGED_SOURCE_ONLY_NOT_COMPILED_NOT_BUILD_NOT_RECALL",
                "root": str(root), "source_git_head": COMMIT,
                "source_sha256": {}, "staged_sha256": {}, "files": targets}
    for rel in targets:
        dst = out / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(updated[rel], encoding="utf-8")
        manifest["source_sha256"][rel] = sha(original[rel].encode())
        manifest["staged_sha256"][rel] = sha(updated[rel].encode())
        diff_all.extend(difflib.unified_diff(
            original[rel].splitlines(keepends=True),
            updated[rel].splitlines(keepends=True),
            fromfile=f"H70/{rel}", tofile=f"H83/{rel}"))
    (out / "r83_3_compact_source.diff").write_text("".join(diff_all), encoding="utf-8")
    (out / "r83_3_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print("R83_3_SOURCE_PATCH_STAGE_PASS", len(targets), "files")
    for rel in targets:
        print("R83_3_STAGED_SHA256", manifest["staged_sha256"][rel], rel)
    print("R83_3_DIFF", out / "r83_3_compact_source.diff")
    print("R83_3_MANIFEST", out / "r83_3_manifest.json")
    print("R83_3_NOT_COMPILED_NOT_GRAPH_BUILD_NOT_RECALL_NOT_PUSH")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path)
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args()
    try:
        selftest()
        if not args.selftest:
            if args.root is None:
                parser.error("--root is required except with --selftest")
            run(args.root.expanduser().resolve())
    except Exception as exc:
        print("R83_3_STOP", str(exc), file=sys.stderr)
        sys.exit(1)
