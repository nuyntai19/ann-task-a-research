#!/usr/bin/env python3
"""R86 D0 isolated offline CMake build gate (source/cache audit; never builds ANN graphs).
Usage: python3 this.py --preflight | --build
Requires an intact local R86 research tree. No network fetching, no overwrites.
"""
import argparse
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path.home() / "ann-task-a"
SRC = ROOT / "experiments/R86/r86_v1_2_source"
REF = ROOT / "experiments/R86/gates/highway_r85_four_binary_jvYREW/build_h17_off"
R86_STOCK_DEPS = ROOT / "experiments/R86/r86_v1_2_builds/stock_off/_deps"
DEST = ROOT / "experiments/R86/msturing_1m_sixarm/build_d0_h17_tier_off_v1"
TARGET = "neighbors-pipnn_FLOAT_T_EUCLIDEAN"
REL_BIN = Path("algorithms/PipNN") / TARGET
REL_FLAGS = Path("algorithms/PipNN/CMakeFiles") / (TARGET + ".dir/flags.make")
PIN_H17_SHA = "5f673586210f93b424fc81791ec7873cb74600843b5004c0a4aaaf32bf936297"


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def require(cond, message):
    if not cond:
        raise RuntimeError(message)


def cache_value(cache, key):
    matches = re.findall(r"^" + re.escape(key) + r":[^=]*=(.*)$", cache, re.M)
    return matches[-1] if matches else None


def preflight():
    require(shutil.which("cmake"), "CMAKE_NOT_FOUND")
    require(Path("/usr/bin/c++").is_file(), "PINNED_COMPILER_MISSING")
    require(not DEST.exists(), "DEST_ALREADY_EXISTS_DO_NOT_OVERWRITE: " + str(DEST))
    cmake_file = SRC / "algorithms/PipNN/CMakeLists.txt"
    require(cmake_file.is_file(), "R86_SOURCE_CMAKE_MISSING")
    source_cmake = cmake_file.read_text(errors="replace")
    for flag in ("R70_USE_TIER", "R71_USE_H17", "R86_USE_COUNTERS"):
        require(re.search(r"option\s*\(\s*" + flag + r"\b", source_cmake, re.I), "SOURCE_OPTION_MISSING_" + flag)
    require("R86 counters only support Flat" in source_cmake, "COUNTER_TIER_CONFLICT_GATE_MISSING")
    cache_file = REF / "CMakeCache.txt"
    flags_file = REF / REL_FLAGS
    ref_binary = REF / REL_BIN
    for f in (cache_file, flags_file, ref_binary):
        require(f.is_file(), "REF_FILE_MISSING: " + str(f))
    require(digest(ref_binary) == PIN_H17_SHA, "REF_H17_BINARY_SHA_MISMATCH")
    cache = cache_file.read_text(errors="replace")
    expected = {
        "CMAKE_HOME_DIRECTORY": str(SRC),
        "CMAKE_BUILD_TYPE": "Release",
        "R70_USE_TIER": "OFF",
        "R71_USE_H17": "ON",
        "R86_USE_COUNTERS": "OFF",
        "CMAKE_CXX_COMPILER": "/usr/bin/c++",
    }
    for k, value in expected.items():
        require(cache_value(cache, k) == value, f"REF_CACHE_{k}_MISMATCH expected={value} got={cache_value(cache,k)}")
    flags = flags_file.read_text(errors="replace")
    require("R71_H17_TOP2=1" in flags and "R70_TWO_TIER=1" not in flags and "R86_COUNTERS=1" not in flags,
            "REF_H17_COMPILE_MACROS_MISMATCH")
    match = re.search(r"-I([^\s]+/_deps/highway-src)(?=\s|$)", flags)
    require(match is not None, "REF_HIGHWAY_SOURCE_NOT_RESOLVED_FROM_FLAGS")
    highway_src = Path(match.group(1))
    deps = {
        "ABSEIL_CPP": R86_STOCK_DEPS / "abseil-cpp-src",
        "PARLAYLIB": R86_STOCK_DEPS / "parlaylib-src",
        "EIGEN": R86_STOCK_DEPS / "eigen-src",
        "HIGHWAY": highway_src,
    }
    for name, path in deps.items():
        require((path / "CMakeLists.txt").is_file(), "FETCHCONTENT_SOURCE_MISSING_" + name + ": " + str(path))
    require((deps["PARLAYLIB"] / "include/parlay/parallel.h").is_file(), "PARLAY_HEADER_MISSING")
    require((deps["ABSEIL_CPP"] / "absl/synchronization/mutex.h").is_file(), "ABSEIL_HEADER_MISSING")
    free_gib = shutil.disk_usage(DEST.parent if DEST.parent.exists() else ROOT).free / (1024 ** 3)
    require(free_gib >= 4.0, f"FREE_DISK_LT_4_GIB {free_gib:.2f}")
    provenance = {
        "source": str(SRC),
        "source_pipnn_cmakelists_sha256": digest(cmake_file),
        "ref_h17_build": str(REF),
        "ref_h17_binary_sha256": digest(ref_binary),
        "ref_h17_cmakecache_sha256": digest(cache_file),
        "ref_h17_flags_sha256": digest(flags_file),
        "deps": {k: str(v) for k, v in deps.items()},
        "dep_header_shas": {
            "parlay_parallel_h": digest(deps["PARLAYLIB"] / "include/parlay/parallel.h"),
            "absl_mutex_h": digest(deps["ABSEIL_CPP"] / "absl/synchronization/mutex.h"),
        },
        "destination": str(DEST),
        "free_disk_gib": round(free_gib, 2),
        "requested_flags": {"R70_USE_TIER": "ON", "R71_USE_H17": "ON", "R86_USE_COUNTERS": "OFF"},
        "note": "No ANN graph built; binary compile only; equivalent source/dependency intended, must audit resulting command macros and graph behavior.",
    }
    print("REF_H17_BINARY_SHA_PASS " + provenance["ref_h17_binary_sha256"])
    print("REF_SOURCE_CMAKE_SHA " + provenance["source_pipnn_cmakelists_sha256"])
    print("REF_HIGHWAY_SOURCE " + str(highway_src))
    print("DISK_FREE_GIB %.2f" % free_gib)
    for k, path in deps.items():
        print("OFFLINE_DEP_%s=%s" % (k, path))
    print("R86_D0_OFFLINE_SOURCE_AND_REFERENCE_PREFLIGHT_PASS_NO_WRITES")
    return deps, provenance


def execute(cmd, logfile):
    with logfile.open("w", encoding="utf-8") as fout:
        p = subprocess.run(cmd, stdout=fout, stderr=subprocess.STDOUT, text=True, check=False)
    print("COMMAND_EXIT_CODE=%d log=%s" % (p.returncode, logfile))
    if p.returncode:
        lines = logfile.read_text(errors="replace").splitlines()
        print("===== LOG TAIL (last 45 lines) =====")
        print("\n".join(lines[-45:]))
        raise RuntimeError("D0_BUILD_STAGE_FAILED; LOG_SAVED; NO_SEARCH_APPROVAL")


def build():
    deps, prov = preflight()
    DEST.parent.mkdir(parents=True, exist_ok=True)
    DEST.mkdir()  # preflight requires non-existent: never overwrite historical directory
    configure = [
        "cmake", "-G", "Unix Makefiles", "-S", str(SRC), "-B", str(DEST),
        "-DCMAKE_BUILD_TYPE=Release", "-DCMAKE_CXX_COMPILER=/usr/bin/c++",
        "-DR70_USE_TIER=ON", "-DR71_USE_H17=ON", "-DR86_USE_COUNTERS=OFF",
        "-DFETCHCONTENT_FULLY_DISCONNECTED=ON", "-DFETCHCONTENT_UPDATES_DISCONNECTED=ON",
        "-DFETCHCONTENT_SOURCE_DIR_PARLAYLIB=" + str(deps["PARLAYLIB"]),
        "-DFETCHCONTENT_SOURCE_DIR_EIGEN=" + str(deps["EIGEN"]),
        "-DFETCHCONTENT_SOURCE_DIR_EIGEN3=" + str(deps["EIGEN"]),
        "-DFETCHCONTENT_SOURCE_DIR_ABSEIL_CPP=" + str(deps["ABSEIL_CPP"]),
        "-DFETCHCONTENT_SOURCE_DIR_ABSEIL-CPP=" + str(deps["ABSEIL_CPP"]),
        "-DFETCHCONTENT_SOURCE_DIR_HIGHWAY=" + str(deps["HIGHWAY"]),
    ]
    (DEST / "d0_provenance_before_build.json").write_text(json.dumps(prov, indent=2) + "\n")
    execute(configure, DEST / "d0_cmake_configure_v1.log")
    cache_path = DEST / "CMakeCache.txt"
    require(cache_path.is_file(), "D0_CMAKE_CACHE_MISSING")
    cc = cache_path.read_text(errors="replace")
    for key, val in (("R70_USE_TIER", "ON"), ("R71_USE_H17", "ON"),
                     ("R86_USE_COUNTERS", "OFF"), ("CMAKE_HOME_DIRECTORY", str(SRC))):
        require(cache_value(cc, key) == val, "D0_ACTUAL_CACHE_MISMATCH_" + key)
    macro_file = DEST / REL_FLAGS
    require(macro_file.is_file(), "D0_TARGET_FLAGS_MISSING")
    flags = macro_file.read_text(errors="replace")
    require("R70_TWO_TIER=1" in flags and "R71_H17_TOP2=1" in flags,
            "D0_COMPILE_DEFINITIONS_TIER_H17_MISSING")
    require("R86_COUNTERS=1" not in flags, "D0_COUNTERS_WRONGLY_ENABLED")
    reference_flags = (REF / REL_FLAGS).read_text(errors="replace")
    def make_var(txt, key):
        match = re.search(r"^" + re.escape(key) + r"\s*=\s*(.*)$", txt, re.M)
        return shlex.split(match.group(1)) if match else None
    ref_cxx_flags = make_var(reference_flags, "CXX_FLAGS")
    new_cxx_flags = make_var(flags, "CXX_FLAGS")
    require(ref_cxx_flags is not None and new_cxx_flags is not None,
            "D0_COMPILER_FLAGS_NOT_FOUND")
    require(sorted(ref_cxx_flags) == sorted(new_cxx_flags),
            "D0_COMPILER_FLAGS_NOT_EQUIVALENT_TO_H17_OFF")
    ref_defs = make_var(reference_flags, "CXX_DEFINES")
    new_defs = make_var(flags, "CXX_DEFINES")
    require(ref_defs is not None and new_defs is not None,
            "D0_COMPILE_DEFINITIONS_NOT_FOUND")
    require(set(new_defs) == set(ref_defs) | {"-DR70_TWO_TIER=1"},
            "D0_DEFINITIONS_NOT_ONE_FACTOR_TIER_FROM_H17")
    include_args = " ".join(make_var(flags, "CXX_INCLUDES") or [])
    for dep_name, dep_path in (("HIGHWAY", deps["HIGHWAY"]),
                               ("ABSEIL_CPP", deps["ABSEIL_CPP"]),
                               ("PARLAYLIB", deps["PARLAYLIB"])):
        expected_path = str(dep_path / "include") if dep_name == "PARLAYLIB" else str(dep_path)
        require(expected_path in include_args, "D0_DEP_INCLUDE_NOT_PINNED_" + dep_name)
    print("R86_D0_CMAKE_CACHE_FLAGS_AND_ONLY_TIER_MACRO_DELTA_PASS")
    execute(["cmake", "--build", str(DEST), "--target", TARGET, "--parallel", "2"], DEST / "d0_native_build_v1.log")
    binary = DEST / REL_BIN
    require(binary.is_file() and os.access(binary, os.X_OK), "D0_BINARY_NOT_EXECUTABLE")
    prov["new_d0_binary"] = str(binary)
    prov["new_d0_binary_sha256"] = digest(binary)
    prov["new_d0_flags_sha256"] = digest(macro_file)
    prov["new_d0_cmakecache_sha256"] = digest(cache_path)
    prov["new_d0_link_sha256"] = digest(DEST / "algorithms/PipNN/CMakeFiles" / (TARGET + ".dir/link.txt"))
    (DEST / "d0_build_manifest_v1.json").write_text(json.dumps(prov, indent=2) + "\n")
    print("R86_D0_NEW_BINARY_SHA256 " + prov["new_d0_binary_sha256"])
    print("R86_D0_OFFLINE_NATIVE_BINARY_COMPILE_PASS_NO_GRAPH_OR_SEARCH")


def main():
    p = argparse.ArgumentParser()
    group = p.add_mutually_exclusive_group(required=True)
    group.add_argument("--preflight", action="store_true")
    group.add_argument("--build", action="store_true")
    a = p.parse_args()
    try:
        preflight() if a.preflight else build()
        return 0
    except Exception as exc:
        print("R86_D0_HOLD " + str(exc))
        return 2


if __name__ == "__main__":
    sys.exit(main())
