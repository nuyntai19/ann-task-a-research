#!/usr/bin/env python3
"""Compile the MS-Turing evaluator using EXISTING native CMake compilation/link inputs.

This script never edits H70/H85/R86 old sources, CMake build trees, datasets,
old evaluators or graphs. It reads one proven native *Stock* target's flags.make
and link.txt, and compiles the separately pinned R86 MS-Turing evaluator source
into an isolated output path. No shell is used to execute CMake link.txt.

Usage:
  python3 THIS.py --preflight
  python3 THIS.py --compile
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys

ROOT = Path.home() / "ann-task-a"
H70 = ROOT / "experiments/H70/pipnn-clean-443a328"
R85_SRC = ROOT / "experiments/H85/r85_a1c_matched_search/r85_a1c_graph_recall.cc"
R85_BIN = ROOT / "experiments/H85/r85_a1c_matched_search/r85_a1c_graph_recall"
E = ROOT / "experiments/R86/msturing_1m_eval"
NEW_SRC = E / "r86_msturing1m_graph_recall.cc"
OUT = E / "r86_msturing1m_graph_recall_v3"
LOG = E / "r86_msturing1m_eval_native_link_v3.log"
MANIFEST = E / "r86_msturing1m_eval_native_link_v3.json"
PINS = {
    R85_SRC: "a2b4f27e8dd9f7cd428c5568b1691eb6dc810d2cb7813a4e421ea238c13fb2c0",
    R85_BIN: "11587916ffd70143d6d5246bf8d2e26c1927b81bf8b3298fbc2014bfb6c64a4e",
    NEW_SRC: "91078479eb7fdb05a6070526797c4feaf01d6e994c13f699108e497ea0609b7e",
}
EDITS = (
    ("base.dimension() != 128", "base.dimension() != 100"),
    ("queries.size() != 10000", "queries.size() != 100000"),
    ("queries.dimension() != 128", "queries.dimension() != 100"),
)
CANDIDATES = [
    ROOT / "experiments/R86/r86_v1_2_builds/stock_off",
    ROOT / "experiments/H85/r85_0_matched_baseline/build_stock",
]
TARGET = "neighbors-pipnn_FLOAT_T_EUCLIDEAN"


def fail(reason: str) -> None:
    raise RuntimeError("R86_MST_EVAL_V3_HOLD " + reason)


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for c in iter(lambda: f.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest()


def verify_source() -> None:
    for path, expected in PINS.items():
        if not path.is_file():
            fail("MISSING_PIN " + str(path))
        actual = sha(path)
        if actual != expected:
            fail(f"PIN_SHA_MISMATCH {path} wanted={expected} got={actual}")
        print(f"SOURCE_OR_BINARY_PIN_PASS sha256={actual} file={path}", flush=True)
    derived = R85_SRC.read_text(encoding="utf-8")
    for old, new in EDITS:
        if derived.count(old) != 1:
            fail(f"R85_EDIT_MARKER_MISMATCH {old}")
        derived = derived.replace(old, new, 1)
    if derived != NEW_SRC.read_text(encoding="utf-8"):
        fail("SOURCE_HAS_NON_GUARD_EDITS")
    if not (H70 / "algorithms/utils/check_nn_recall.h").is_file():
        fail("H70_CHECK_RECALL_HEADER_MISSING")
    print("R86_MST_V3_THREE_INPUT_GUARDS_ONLY_SOURCE_EQUIVALENCE_PASS", flush=True)


def parse_native_flags(path: Path) -> tuple[list[str], list[str], list[str]]:
    props = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        for key in ("CXX_DEFINES", "CXX_INCLUDES", "CXX_FLAGS"):
            if line.startswith(key + " ="):
                if key in props:
                    fail(f"DUPLICATE_NATIVE_FLAGS_KEY {key}")
                props[key] = shlex.split(line.split("=", 1)[1].strip())
    if set(props) != {"CXX_DEFINES", "CXX_INCLUDES", "CXX_FLAGS"}:
        fail(f"INCOMPLETE_NATIVE_FLAGS {path} got={sorted(props)}")
    defines, includes, flags = (props[k] for k in ("CXX_DEFINES", "CXX_INCLUDES", "CXX_FLAGS"))
    for t in defines:
        if not t.startswith("-D"):
            fail(f"UNEXPECTED_NATIVE_DEFINE {t}")
        if any(name in t for name in ("R70_TWO_TIER", "R71_H17_TOP2", "R86_COUNTERS")):
            fail("NON_STOCK_EVAL_COMPILE_MACRO " + t)
    for x in includes:
        if not x.startswith("-I") or not Path(x[2:]).is_dir():
            fail("MISSING_OR_MALFORMED_NATIVE_INCLUDE " + x)
    for x in flags:
        if not x.startswith("-"):
            fail("UNEXPECTED_NATIVE_COMPILER_FLAG " + x)
    return defines, includes, flags


def parse_native_link(link: Path, base_dir: Path) -> tuple[str, list[str], list[Path]]:
    toks = shlex.split(link.read_text(encoding="utf-8").strip())
    if not toks or not Path(toks[0]).is_file():
        fail("NATIVE_LINK_COMPILER_MISSING " + str(toks[:1]))
    if toks.count("-o") != 1:
        fail("NATIVE_LINK_UNEXPECTED_OUTPUT_COUNT")
    idx = toks.index("-o")
    if idx < 1 or idx + 2 >= len(toks):
        fail("NATIVE_LINK_UNEXPECTED_SHAPE")
    if TARGET not in toks[idx + 1]:
        fail("NATIVE_LINK_WRONG_TARGET")
    if not any(x.endswith(".o") for x in toks[1:idx]):
        fail("NATIVE_LINK_HAS_NO_OBJECT")
    # All library arguments are AFTER the native output filename. Preserve ORDER
    # and duplicates: Abseil + Highway static libraries are order-sensitive.
    raw = toks[idx + 2:]
    if not raw:
        fail("NATIVE_LINK_HAS_NO_LIBRARIES")
    result: list[str] = []
    library_files: list[Path] = []
    for x in raw:
        if x.endswith((".a", ".so")) or ".so." in x:
            p = Path(x)
            if not p.is_absolute():
                p = (base_dir / p).resolve()
            if not p.is_file():
                fail("NATIVE_LINK_LIBRARY_MISSING " + str(p))
            result.append(str(p))
            library_files.append(p)
        elif x in ("-lrt", "-ldl", "-lm", "-lpthread", "-pthread", "-fopenmp"):
            result.append(x)
        elif x.startswith("-Wl,") or x.startswith("-l") or x.startswith("-L"):
            result.append(x)
        else:
            fail("NATIVE_LINK_UNRECOGNIZED_ARGUMENT " + x)
    if not any("absl_synchronization" in str(p) for p in library_files):
        fail("NATIVE_LINK_MISSING_ABSL_SYNCHRONIZATION")
    if not any("hwy" in p.name for p in library_files):
        fail("NATIVE_LINK_MISSING_HIGHWAY")
    return toks[0], result, library_files


def plan_for(build: Path) -> dict:
    target_dir = build / "algorithms/PipNN"
    obj_dir = target_dir / f"CMakeFiles/{TARGET}.dir"
    flags_path, link_path = obj_dir / "flags.make", obj_dir / "link.txt"
    if not flags_path.is_file() or not link_path.is_file():
        fail("NATIVE_TARGET_FILES_MISSING " + str(build))
    defines, includes, flags = parse_native_flags(flags_path)
    compiler, libs, lib_files = parse_native_link(link_path, target_dir)
    if not (build / "CMakeCache.txt").is_file():
        fail("NATIVE_CMAKE_CACHE_MISSING")
    cache = (build / "CMakeCache.txt").read_text(errors="replace")
    for x in ("CMAKE_BUILD_TYPE:STRING=Release", "R70_USE_TIER:BOOL=OFF"):
        if x not in cache:
            fail("NATIVE_STOCK_RELEASE_CACHE_GUARD " + x)
    if "R71_USE_H17:BOOL=ON" in cache or "R86_USE_COUNTERS:BOOL=ON" in cache:
        fail("NATIVE_STOCK_CACHE_GUARD_NONSTOCK")
    # Resolve the H70 headers from the original evaluator. The native stock
    # target already includes its corresponding H70/R86 dependencies.
    extra = ["-I" + str(H70 / "algorithms"), "-I" + str(H70 / "algorithms/utils")]
    cmd = [compiler, *defines, *includes, *extra, *flags]
    for opt in ("-pthread", "-fopenmp"):
        if opt not in cmd:
            cmd.append(opt)
    # Preserve native-link library ordering exactly after compiled source.
    cmd += [str(NEW_SRC), "-o", "__OUTPUT_PART__", *libs]
    return {
        "build": str(build), "compiler": compiler, "command_template": cmd,
        "flags_make": str(flags_path), "flags_make_sha256": sha(flags_path),
        "link_txt": str(link_path), "link_txt_sha256": sha(link_path),
        "library_files": list(dict.fromkeys(map(str, lib_files))),
        "library_arguments_count": len(libs),
        "abseil_header": str(build / "_deps/abseil-cpp-src/absl/synchronization/mutex.h"),
        "parlay_header": str(build / "_deps/parlaylib-src/include/parlay/parallel.h"),
    }


def preflight() -> dict:
    verify_source()
    diagnostics = []
    for build in CANDIDATES:
        try:
            plan = plan_for(build)
            if not Path(plan["abseil_header"]).is_file():
                fail("ABSEIL_HEADER_MISSING " + plan["abseil_header"])
            if not Path(plan["parlay_header"]).is_file():
                fail("PARLAY_HEADER_MISSING " + plan["parlay_header"])
            print("NATIVE_PROVEN_BUILD_SELECTED " + str(build), flush=True)
            print("ABSEIL_HEADER_SHA256 " + sha(Path(plan["abseil_header"])), flush=True)
            print("PARLAY_HEADER_SHA256 " + sha(Path(plan["parlay_header"])), flush=True)
            print("NATIVE_FLAGS_SHA256 " + plan["flags_make_sha256"])
            print("NATIVE_LINK_SHA256 " + plan["link_txt_sha256"])
            print("NATIVE_STATIC_LIBRARY_FILES=" + str(len(plan["library_files"])))
            print("NATIVE_LIBRARY_ARGUMENTS=" + str(plan["library_arguments_count"]))
            print("R86_MST_EVAL_V3_NATIVE_FLAGS_AND_STATIC_LINK_PREFLIGHT_PASS", flush=True)
            return plan
        except (OSError, ValueError, RuntimeError) as e:
            diagnostics.append(f"{build}: {e}")
            print("NATIVE_BUILD_CANDIDATE_HOLD " + str(e), flush=True)
    fail("NO_COMPLETE_NATIVE_STOCK_BUILD; " + " | ".join(diagnostics))


def compile_eval(plan: dict) -> None:
    for f in (OUT, LOG, MANIFEST):
        if f.exists():
            fail("DESTINATION_EXISTS_NO_OVERWRITE " + str(f))
    if not E.is_dir():
        fail("EVALUATOR_OUTPUT_DIR_MISSING")
    tmp = E / (OUT.name + f".part.{os.getpid()}")
    if tmp.exists():
        fail("TMP_DEST_EXISTS " + str(tmp))
    cmd = [str(tmp) if x == "__OUTPUT_PART__" else x for x in plan["command_template"]]
    print("NATIVE_COMPILER_COMMAND " + shlex.join(cmd), flush=True)
    try:
        with LOG.open("x", encoding="utf-8") as fp:
            r = subprocess.run(cmd, stdout=fp, stderr=subprocess.STDOUT, check=False)
        print(f"NATIVE_COMPILE_EXIT_CODE={r.returncode} log={LOG}", flush=True)
        if r.returncode:
            print("===== NATIVE LINK V3 LOG LAST 60 LINES =====")
            print("\n".join(LOG.read_text(errors="replace").splitlines()[-60:]))
            fail("COMPILE_OR_LINK_FAILED_NO_BINARY")
        smoke = subprocess.run([str(tmp)], capture_output=True, text=True, timeout=15, check=False)
        if smoke.returncode != 2 or "Usage:" not in smoke.stderr:
            fail(f"EVALUATOR_NO_ARG_SMOKE_FAIL rc={smoke.returncode} stderr={smoke.stderr[:150]}")
        verify_source()
        if sha(Path(plan["flags_make"])) != plan["flags_make_sha256"] or sha(Path(plan["link_txt"])) != plan["link_txt_sha256"]:
            fail("NATIVE_BUILD_CONFIG_CHANGED_DURING_COMPILATION")
        os.link(tmp, OUT)  # No-clobber atomic new name on same filesystem.
        manifest = {
            "status": "COMPILE_AND_NO_ARGUMENT_USAGE_PASS_SEARCH_NOT_YET_VALIDATED",
            "native_stock_build": plan["build"],
            "native_flags_sha256": plan["flags_make_sha256"],
            "native_link_sha256": plan["link_txt_sha256"],
            "original_evaluator_source_sha256": PINS[R85_SRC],
            "original_evaluator_binary_sha256": PINS[R85_BIN],
            "derived_evaluator_source_sha256": PINS[NEW_SRC],
            "new_evaluator_binary_sha256": sha(OUT),
            "native_library_files": plan["library_files"],
            "compile_log_sha256": sha(LOG),
            "compile_command": [str(OUT) if x == "__OUTPUT_PART__" else x for x in plan["command_template"]],
            "no_arg_smoke_exit_code": smoke.returncode,
            "note": "No Search was run; runtime graph and recall protocol require separate gate.",
        }
        with MANIFEST.open("x", encoding="utf-8") as fp:
            json.dump(manifest, fp, indent=2, ensure_ascii=False)
        print("EVAL_V3_NEW_BINARY_SHA256=" + sha(OUT), flush=True)
        print("EVAL_V3_MANIFEST " + str(MANIFEST), flush=True)
        print("R86_MST_EVAL_V3_COMPILE_USAGE_PASS_SEARCH_NOT_YET_APPROVED", flush=True)
    finally:
        if tmp.is_file():
            tmp.unlink()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--preflight", action="store_true")
    mode.add_argument("--compile", action="store_true")
    args = ap.parse_args()
    try:
        plan = preflight()
        if args.compile:
            compile_eval(plan)
        return 0
    except (OSError, RuntimeError, subprocess.TimeoutExpired, ValueError) as e:
        print(str(e), file=sys.stderr, flush=True)
        return 2


if __name__ == "__main__":
    sys.exit(main())
