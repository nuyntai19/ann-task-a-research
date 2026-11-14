#!/usr/bin/env python3
"""R84.4: source-pinned, isolated D0 vs grow-only leaf workspace STAGE + SYNTAX.

No native graph build, no ELF link, no benchmarks, no H70/H80 edits, no Git push.
The optimization is experimental: thread-local buffers grow by powers of two,
are 64-byte aligned, and are not pre-zeroed. The used point rows are fully
written, and the used distance matrix is setZero() in the original code.
"""
from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

PIN = "443a328dc71a3b7be753d52ca2b3c9a4ba77f3fd"
TARGET = "neighbors-pipnn_FLOAT_T_EUCLIDEAN"
SOURCE_SHA = {
    "algorithms/PipNN/pipnn.h": "f4391ad8712d7757423dca872f9042c3271660dffde384a85b93854b9692f288",
    "algorithms/PipNN/pipnn_utils.h": "7083e8183554a1cb586b70cdb4c57920f49ec5a50680096aecf6b873f596595d",
    "algorithms/utils/graph.h": "17e51779f32db56c9c50b6d514a8ff68539fd19b734804df3abdb63f88dd443e",
    "algorithms/utils/r70_two_tier_lshgraph.h": "ac0bece4804c7bc552b30db0df57ee92492033065cef62330ddb58a19d470af1",
}


def require(ok: bool, msg: str):
    if not ok:
        raise RuntimeError(msg)


def sha(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


# Dedicated, immutable source patch of only pipnn_utils.h. In particular:
#   - n <= kMaxClusterSize=2048 and dimension <= kMaxDimension=2048
#   - allocation is grow-only, power-of-two, >= required floats, 64B aligned
#   - old buffers are freed only at the beginning of a different leaf call
#   - no new realloc between eigen_build_distmat and eigen_knn accessor read
#   - all active P data is written and active D is setZero before rankUpdate
# This is NOT a proof; actual graph parity is a separate required next gate.
REPLACEMENT = '''thread_local uint8_t* tl_dist_mat = nullptr;
thread_local uint8_t* tl_point_mat = nullptr;
thread_local size_t tl_dist_capacity_bytes = 0;
thread_local size_t tl_point_capacity_bytes = 0;
size_t kMaxClusterSize = 2048;
size_t kMaxDimension = 2048;

// R84 prototype only: capacity monotonically grows per worker, with 64-byte
// alignment. No blind initialization of unused bytes. The callers fully write
// active P and zero active D before any mathematical read.
static void* r84_grow_leaf_buffer(uint8_t*& p, size_t& capacity,
                                  size_t needed_bytes) {
  CHECK(needed_bytes > 0);
  CHECK(needed_bytes <= kMaxClusterSize * kMaxDimension * sizeof(float));
  if (needed_bytes > capacity) {
    size_t next_capacity = capacity == 0 ? 4096 : capacity;
    while (next_capacity < needed_bytes) {
      next_capacity *= 2;
    }
    uint8_t* fresh = (uint8_t*)_mm_malloc(next_capacity, 64);
    CHECK(fresh != nullptr);
    _mm_free(p);
    p = fresh;
    capacity = next_capacity;
  }
  return p;
}

void* get_point_mat(size_t n, size_t dimension) {
  CHECK(n > 0 && n <= kMaxClusterSize);
  CHECK(dimension > 0 && dimension <= kMaxDimension);
  return r84_grow_leaf_buffer(tl_point_mat, tl_point_capacity_bytes,
                              n * dimension * sizeof(float));
}

void* get_dist_mat(size_t n) {
  CHECK(n > 0 && n <= kMaxClusterSize);
  return r84_grow_leaf_buffer(tl_dist_mat, tl_dist_capacity_bytes,
                              n * n * sizeof(float));
}

'''


def patch(original: str) -> str:
    first = "thread_local uint8_t* tl_dist_mat = nullptr;"
    last = "// Materializes the output floating-point distmat into the"
    require(original.count(first) == 1 and original.count(last) == 1,
            "R84_4_EXPECTED_WORKSPACE_BLOCK_NOT_UNIQUE")
    a = original.index(first)
    b = original.index(last)
    old = original[a:b]
    for phrase in (
        "tl_point_mat = (uint8_t*)_mm_malloc(",
        "tl_dist_mat = (uint8_t*)_mm_malloc(",
        "tl_point_mat[i] = 0;",
        "tl_dist_mat[i] = 0;",
        "void* get_point_mat()",
        "void* get_dist_mat()",
        "kMaxClusterSize = 2048",
        "kMaxDimension = 2048",
    ):
        require(phrase in old, f"R84_4_WORKSPACE_ANCHOR_CHANGED {phrase}")
    # Fail closed if an unexpected accessor is used elsewhere; only 3 known
    # call sites are allowed: 2 get_dist_mat, 1 get_point_mat.
    require(original.count("get_point_mat()") == 2 and
            original.count("get_dist_mat()") == 3,
            "R84_4_UNKNOWN_WORKSPACE_ACCESSOR_CALLSITE")
    patched = original[:a] + REPLACEMENT + original[b:]
    patched = patched.replace("float* dist_mat = (float*)get_dist_mat();",
                              "float* dist_mat = (float*)get_dist_mat(n);")
    patched = patched.replace("float* point_mat = (float*)get_point_mat();",
                              "float* point_mat = (float*)get_point_mat(n, dimension);")
    require(patched.count("get_dist_mat(n)") == 2 and
            patched.count("get_point_mat(n, dimension)") == 1 and
            "get_dist_mat()" not in patched and
            "get_point_mat()" not in patched,
            "R84_4_PATCHED_CALLSITE_INVALID")
    require("D.setZero();" in patched and "rankUpdate(P);" in patched and
            "point_mat[i*dimension + j] = static_cast<float>(loc[j]);" in patched,
            "R84_4_MATRIX_INIT_INVARIANT_NOT_FOUND")
    return patched


def source_gate(root: Path):
    original = root / "experiments/H70/pipnn-clean-443a328"
    require(original.is_dir(), "R84_4_PINNED_H70_MISSING")
    head = subprocess.check_output(["git", "-C", str(original), "rev-parse", "HEAD"], text=True).strip()
    require(head == PIN, "R84_4_GIT_HEAD_MISMATCH")
    for rel, wanted in SOURCE_SHA.items():
        fp = original / rel
        require(fp.is_file() and sha(fp) == wanted, f"R84_4_PINNED_SHA_FAIL {rel}")
    return original


def spec(root: Path, original: Path):
    paths = [
        root / "src/PiPNN/build/compile_commands.json",
        root / "src/PiPNN/build-r70/compile_commands.json",
        original / "build-r70/compile_commands.json",
        root / "experiments/H70/build-r70/compile_commands.json",
    ]
    expected_benchmark = original / "algorithms/bench/neighborsTime.C"
    require(expected_benchmark.is_file(), "R84_4_BENCHMARK_SOURCE_MISSING")
    good = []
    for path in paths:
        if not path.is_file():
            continue
        try:
            entries = json.loads(path.read_text())
        except Exception:
            continue
        matches = []
        for entry in entries:
            argv = entry.get("arguments") or shlex.split(entry.get("command", ""))
            if not argv or TARGET not in " ".join(argv):
                continue
            if "-DUSE_DATATYPE_FLOAT_T" not in argv or "-DUSE_DISTANCE_EUCLIDEAN" not in argv:
                continue
            src = Path(entry.get("file", ""))
            if not src.is_absolute():
                src = Path(entry["directory"]) / src
            if not src.is_file() or src.name != "neighborsTime.C" or sha(src) != sha(expected_benchmark):
                continue
            if not Path(entry["directory"]).is_dir():
                continue
            if not (Path(argv[0]).is_file() or shutil.which(argv[0])):
                continue
            if any(re.match(r"-DR(?:78|79|80|81|82|83|84)_", x) for x in argv):
                continue
            matches.append((entry, argv))
        if len(matches) == 1:
            good.append((path, *matches[0]))
    require(bool(good), "R84_4_FLOAT_L2_COMPILER_DB_NOT_FOUND")
    return good[0]


def compiler_flags(argv):
    flags = []
    two_args = {"-o", "-MF", "-MT", "-MQ", "-include", "-imacros", "-x"}
    singles = {"-c", "-MD", "-MMD", "-MP", "-MG", "-MM", "-M", "-E", "-S", "-fsyntax-only"}
    i = 1
    while i < len(argv):
        x = argv[i]
        if x in two_args:
            require(i + 1 < len(argv), "R84_4_TRUNCATED_FLAG")
            i += 2
            continue
        if x in singles or x.startswith(("-o", "-MF", "-MT", "-MQ", "-fpch-", "-fmodule-")):
            i += 1
            continue
        if x.startswith("@"):
            raise RuntimeError("R84_4_RESPONSE_FILE_UNSUPPORTED")
        if x.endswith(("neighborsTime.C", "neighborsTime.cc")):
            i += 1
            continue
        if x.startswith(("-DR70_TWO_TIER", "-DR71_H17_TOP2", "-DR83_COMPACT_FANOUT", "-DR84_LEAF_WORKSPACE")):
            i += 1
            continue
        flags.append(x)
        i += 1
    require("-DUSE_DATATYPE_FLOAT_T" in flags and "-DUSE_DISTANCE_EUCLIDEAN" in flags,
            "R84_4_INVALID_COMPILER_FLAVOR")
    return flags


def overlay_stage(overlay: Path, original: Path, utils: bytes, arm: str):
    pip = overlay / "algorithms/PipNN"
    pip.mkdir(parents=True, exist_ok=False)
    for name in ("pipnn.h", "neighbors.h"):
        (pip / name).write_bytes((original / "algorithms/PipNN" / name).read_bytes())
    (pip / "pipnn_utils.h").write_bytes(utils)
    for dirname in ("bench", "utils"):
        (overlay / "algorithms" / dirname).symlink_to(original / "algorithms" / dirname,
                                                        target_is_directory=True)
    wrapper = overlay / "r84_4_real_benchmark_instantiation.cc"
    wrapper.write_text('#include "algorithms/PipNN/neighbors.h"\n'
                       f'#include "{original / "algorithms/bench/neighborsTime.C"}"\n')
    require((overlay / "algorithms/utils/graph.h").resolve() ==
            (original / "algorithms/utils/graph.h").resolve(),
            "R84_4_GRAPH_HEADER_PROVENANCE_FAIL")
    return wrapper


def run(root: Path, mode: str):
    base = source_gate(root)
    raw = (base / "algorithms/PipNN/pipnn_utils.h").read_text()
    fixed = patch(raw)
    require(fixed != raw, "R84_4_EMPTY_PATCH")
    print("R84_4_PINNED_SOURCE_AND_PATCH_SELFTEST_PASS", flush=True)
    if mode == "selftest":
        print("R84_4_SELFTEST_PASS_NO_FILE_WRITES", flush=True)
        return
    db, entry, argv = spec(root, base)
    flags = compiler_flags(argv)
    print(f"R84_4_COMPDB_PASS path={db} compiler={argv[0]}", flush=True)
    out = root / "experiments/H84/r84_4_workspace_stage_syntax"
    require(not out.exists(), "R84_4_OUTPUT_EXISTS_FAIL_CLOSED")
    if mode == "dry-run":
        print(f"R84_4_DRY_RUN_PASS_NO_WRITES planned_dir={out}", flush=True)
        return
    out.mkdir(parents=True, exist_ok=False)
    originals = {rel: sha(base / rel) for rel in SOURCE_SHA}
    (out / "source_patch.diff").write_text("".join(difflib.unified_diff(
        raw.splitlines(keepends=True), fixed.splitlines(keepends=True),
        fromfile="D0/pipnn_utils.h", tofile="W/pipnn_utils.h")))
    report = {"status": "STAGING", "source_commit": PIN, "compiler_db": str(db),
              "baseline": "D0=H17+TwoTier", "experimental": "W=grow-only-uninitialized-leaf-workspace",
              "original_source_sha256": originals, "arms": {},
              "note": "No real graph build, link, or Recall; graph parity required next."}
    for arm in ("D0", "W"):
        overlay = out / arm
        binary_src = raw.encode() if arm == "D0" else fixed.encode()
        wrapper = overlay_stage(overlay, base, binary_src, arm)
        cmd = [argv[0], f"-I{overlay / 'algorithms'}", *flags,
               "-DR70_TWO_TIER=1", "-DR71_H17_TOP2=1",
               f"-DR84_LEAF_WORKSPACE={1 if arm == 'W' else 0}",
               "-fsyntax-only", "-x", "c++", str(wrapper)]
        (overlay / "compile_command.txt").write_text(shlex.join(cmd) + "\n")
        print(f"R84_4_SYNTAX_START arm={arm}", flush=True)
        with (overlay / "compiler.log").open("x") as f:
            done = subprocess.run(cmd, cwd=entry["directory"], stdout=f,
                                  stderr=subprocess.STDOUT, check=False)
        report["arms"][arm] = {
            "exit_code": done.returncode,
            "utils_sha256": sha(overlay / "algorithms/PipNN/pipnn_utils.h"),
            "wrapper": str(wrapper),
            "syntax_log": str(overlay / "compiler.log"),
            "compile_command": str(overlay / "compile_command.txt"),
        }
        (out / "r84_4_summary.json").write_text(json.dumps(report, indent=2) + "\n")
        if done.returncode != 0:
            tail = (overlay / "compiler.log").read_text(errors="replace")[-5500:]
            print(tail, file=sys.stderr)
            raise RuntimeError(f"R84_4_{arm}_FULL_SYNTAX_FAILED log={overlay/'compiler.log'}")
        print(f"R84_4_{arm}_FULL_INSTANTIATION_SYNTAX_PASS", flush=True)
    for rel, value in originals.items():
        require(sha(base / rel) == value, f"R84_4_H70_MODIFIED_UNEXPECTEDLY {rel}")
    report["status"] = "R84_4_SOURCE_STAGE_AND_SYNTAX_PASS"
    (out / "r84_4_summary.json").write_text(json.dumps(report, indent=2) + "\n")
    print("R84_4_SOURCE_STAGE_AND_SYNTAX_PASS", flush=True)
    print("R84_4_NO_ANN_BUILD_NO_BINARY_LINK_NO_GRAPH_PARITY_NO_RECALL_NO_PUSH", flush=True)
    print(f"R84_4_REPORT {out/'r84_4_summary.json'}", flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", type=Path, required=True)
    a = ap.add_mutually_exclusive_group(required=True)
    a.add_argument("--selftest", action="store_true")
    a.add_argument("--dry-run", action="store_true")
    a.add_argument("--run", action="store_true")
    opts = ap.parse_args()
    try:
        run(opts.root.resolve(), "selftest" if opts.selftest else "dry-run" if opts.dry_run else "run")
    except Exception as exc:
        print(f"R84_4_STOP {exc}", file=sys.stderr)
        sys.exit(2)
