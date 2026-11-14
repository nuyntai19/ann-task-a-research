#!/usr/bin/env python3
"""R86 MS-Turing-1M evaluator compile gate v2.

Fixes v1's omitted Parlay include path without changing any evaluator source.
The original H85 binary/source and the R86 evaluator source remain pinned.
Build only a new evaluator binary; no ANN graph builds, no Search, no downloads.
The previous v1 failed compiler log is left untouched.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys

ROOT = Path.home() / "ann-task-a"
H70 = ROOT / "experiments/H70/pipnn-clean-443a328"
R86 = ROOT / "experiments/R86/r86_v1_2_source"
E = ROOT / "experiments/R86/msturing_1m_eval"
R85_SRC = ROOT / "experiments/H85/r85_a1c_matched_search/r85_a1c_graph_recall.cc"
R85_BIN = ROOT / "experiments/H85/r85_a1c_matched_search/r85_a1c_graph_recall"
NEW_SRC = E / "r86_msturing1m_graph_recall.cc"
OUT = E / "r86_msturing1m_graph_recall"
LOG = E / "r86_msturing1m_eval_compile_v2.log"
MANIFEST = E / "r86_msturing1m_eval_compile_v2.json"
PINS = {
    R85_SRC: "a2b4f27e8dd9f7cd428c5568b1691eb6dc810d2cb7813a4e421ea238c13fb2c0",
    R85_BIN: "11587916ffd70143d6d5246bf8d2e26c1927b81bf8b3298fbc2014bfb6c64a4e",
    NEW_SRC: "91078479eb7fdb05a6070526797c4feaf01d6e994c13f699108e497ea0609b7e",
}
THREE_EDITS = (
    ("base.dimension() != 128", "base.dimension() != 100"),
    ("queries.size() != 10000", "queries.size() != 100000"),
    ("queries.dimension() != 128", "queries.dimension() != 100"),
)


def hold(msg: str) -> None:
    raise RuntimeError("R86_MST_EVAL_V2_HOLD " + msg)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def verified_source() -> None:
    for path, expected in PINS.items():
        if not path.is_file() or sha256(path) != expected:
            hold(f"PIN_MISSING_OR_MISMATCH {path}")
        print(f"PIN_PASS sha256={expected} path={path}", flush=True)
    expected = R85_SRC.read_text(encoding="utf-8")
    for old, new in THREE_EDITS:
        if expected.count(old) != 1:
            hold(f"R85_SOURCE_UNEXPECTED_GUARD {old}")
        expected = expected.replace(old, new, 1)
    if expected != NEW_SRC.read_text(encoding="utf-8"):
        hold("EVALUATOR_SOURCE_CHANGED_BEYOND_THREE_GUARDS")
    if not (H70 / "algorithms/utils/check_nn_recall.h").is_file():
        hold("H70_NATIVE_CHECK_RECALL_MISSING")
    print("THREE_INPUT_GUARDS_ONLY_SOURCE_EQUIVALENCE_PASS")


def search_parlay_parent(explicit: str | None) -> tuple[Path, list[Path]]:
    """Find a directory I such that I/parlay/parallel.h is a regular file."""
    if explicit:
        path = Path(explicit).expanduser().resolve()
        if not (path / "parlay/parallel.h").is_file():
            hold(f"EXPLICIT_PARLAY_INCLUDE_MISSING {path}/parlay/parallel.h")
        return path, [path]

    # Prefer the exact source tree used to compile the four pinned R86 binaries.
    # H70 is retained for the evaluator's absolute-include checkRecall implementation.
    parents = [
        R86 / "external",
        H70 / "external",
        ROOT / "experiments/H85/r85_b1_controlled/isolation_v4/source/external",
        ROOT / "experiments/H85/r85_b1_controlled/isolation_v3/source/external",
        ROOT / "experiments/H85/r85_a1c_matched_search",
        ROOT / "external",
    ]
    candidates: list[Path] = []
    # First search common layouts without walking whole external trees.
    for parent in parents:
        for name in ("parlaylib/include", "parlaylib", "parlay/include", "ParlayLib/include", "ParlayLib", "include", "."):
            p = (parent / name).resolve()
            if (p / "parlay/parallel.h").is_file() and p not in candidates:
                candidates.append(p)
    # Only if no candidate found, perform bounded search of the known experiment source trees.
    if not candidates:
        for parent in parents:
            if not parent.is_dir():
                continue
            try:
                found = subprocess.run(
                    ["find", str(parent), "-type", "f", "-path", "*/parlay/parallel.h", "-print"],
                    capture_output=True, text=True, timeout=75, check=False,
                )
            except subprocess.TimeoutExpired:
                hold("PARLAY_SEARCH_TIMEOUT_USE_EXPLICIT_--parlay-include")
            if found.returncode != 0:
                hold(f"PARLAY_SEARCH_FAILED {parent} {found.stderr.strip()[:200]}")
            for line in found.stdout.splitlines():
                path = Path(line).resolve()
                include = path.parent.parent
                if (include / "parlay/parallel.h").is_file() and include not in candidates:
                    candidates.append(include)
            if candidates:  # priority fixed by parents array
                break
    if not candidates:
        for path in (Path("/usr/local/include"), Path("/usr/include")):
            if (path / "parlay/parallel.h").is_file():
                candidates.append(path)
    if not candidates:
        hold("PARLAY_HEADER_NOT_FOUND: run find '$HOME/ann-task-a/experiments' -type f -path '*/parlay/parallel.h' -print")
    return candidates[0], candidates


def preflight(explicit: str | None) -> tuple[str, list[str], Path, str]:
    verified_source()
    parlay_include, candidates = search_parlay_parent(explicit)
    parlay_hdr = parlay_include / "parlay/parallel.h"
    hdr_sha = sha256(parlay_hdr)
    print(f"PARLAY_INCLUDE_RESOLVED {parlay_include}")
    print(f"PARLAY_PARALLEL_H_SHA256 {hdr_sha}")
    for candidate in candidates:
        print(f"PARLAY_CANDIDATE include={candidate} sha256={sha256(candidate/'parlay/parallel.h')}")
    # Parlay is first, so the source headers and external implementation can find their dependency.
    paths = [
        parlay_include,
        H70 / "external/Parallel-KMeans",
        H70 / "external/Parallel-KMeans/seeding",
        H70 / "external/Highway",
        H70 / "algorithms",
        H70 / "algorithms/utils",
        H70,
        Path("/usr/include/eigen3"),
    ]
    includes = [str(p) for p in paths if p.is_dir()]
    comp = shutil.which("g++") or shutil.which("c++")
    if not comp:
        hold("CXX_COMPILER_NOT_FOUND")
    print(f"COMPILER={comp}")
    print(f"INCLUDE_PATHS={len(includes)}")
    for p in includes:
        print("INCLUDE " + p)
    print("R86_MST_EVAL_V2_PARLAY_RESOLVED_SOURCE_PIN_PREFLIGHT_PASS")
    return comp, includes, parlay_hdr, hdr_sha


def compile_eval(compiler: str, includes: list[str], hdr: Path, hdr_sha: str) -> None:
    for f in (OUT, LOG, MANIFEST):
        if f.exists():
            hold(f"DESTINATION_ALREADY_EXISTS_REFUSE_OVERWRITE {f}")
    E.mkdir(parents=True, exist_ok=True)
    tmp = OUT.with_name(OUT.name + f".part.{os.getpid()}")
    if tmp.exists():
        hold(f"TEMP_PATH_ALREADY_EXISTS {tmp}")
    cmd = [compiler, "-std=c++17", "-O3", "-DNDEBUG", "-pthread", "-fopenmp"]
    for incl in includes:
        cmd.extend(["-I", incl])
    cmd += [str(NEW_SRC), "-o", str(tmp)]
    print("COMPILER_COMMAND " + shlex.join(cmd), flush=True)
    try:
        with LOG.open("x", encoding="utf-8") as fp:
            res = subprocess.run(cmd, stdout=fp, stderr=subprocess.STDOUT, check=False)
        print(f"COMPILE_EXIT_CODE={res.returncode} log={LOG}", flush=True)
        if res.returncode:
            print("===== V2 COMPILER LOG LAST 60 LINES =====")
            print("\n".join(LOG.read_text(errors="replace").splitlines()[-60:]))
            hold("COMPILE_FAILED_LOG_RETAINED_NO_BINARY")
        usage = subprocess.run([str(tmp)], capture_output=True, text=True, timeout=15, check=False)
        if usage.returncode != 2 or "Usage:" not in usage.stderr:
            hold(f"NO_ARG_USAGE_SMOKE_FAIL code={usage.returncode} stderr={usage.stderr[:240]}")
        if sha256(hdr) != hdr_sha or sha256(NEW_SRC) != PINS[NEW_SRC]:
            hold("BUILD_INPUT_MODIFIED_DURING_COMPILE")
        if OUT.exists():
            hold("OUTPUT_RACED_REFUSE_OVERWRITE")
        os.link(tmp, OUT)  # Atomic no-clobber creation on same filesystem.
        manifest = {
            "status": "COMPILATION_AND_NO_ARGUMENT_USAGE_PASS_SEARCH_NOT_YET_VALIDATED",
            "original_evaluator_source_sha256": PINS[R85_SRC],
            "original_evaluator_binary_sha256": PINS[R85_BIN],
            "new_evaluator_source_sha256": sha256(NEW_SRC),
            "new_evaluator_binary_sha256": sha256(OUT),
            "parlay_header": str(hdr),
            "parlay_header_sha256": hdr_sha,
            "compile_log_sha256": sha256(LOG),
            "compiler": compiler,
            "compile_command": cmd[:-1] + [str(OUT)],
            "notes": "Native H70 checkRecall identical; only three guarded dimension/query checks changed. Not a graph Search gate.",
        }
        with MANIFEST.open("x", encoding="utf-8") as fp:
            json.dump(manifest, fp, ensure_ascii=False, indent=2)
        print(f"NEW_EVAL_BINARY_SHA256 {sha256(OUT)}")
        print(f"NEW_EVAL_MANIFEST {MANIFEST}")
        print("R86_MST_EVAL_V2_COMPILE_USAGE_PASS_SEARCH_NOT_YET_APPROVED")
    finally:
        if tmp.exists():
            tmp.unlink()


def main() -> int:
    p = argparse.ArgumentParser()
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--preflight", action="store_true")
    mode.add_argument("--compile", action="store_true")
    p.add_argument("--parlay-include", type=str, default=None, help="Directory containing parlay/parallel.h; optional explicit pin")
    args = p.parse_args()
    try:
        compiler, includes, header, hdr_sha = preflight(args.parlay_include)
        if args.compile:
            compile_eval(compiler, includes, header, hdr_sha)
        return 0
    except (RuntimeError, OSError, subprocess.TimeoutExpired) as exc:
        print(exc, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
