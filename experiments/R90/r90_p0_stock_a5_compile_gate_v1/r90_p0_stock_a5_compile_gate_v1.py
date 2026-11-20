#!/usr/bin/env python3
"""R90 source-pinned stock/A5 C++ build gate; no graph BUILD, no ANN Search.

Only run on user's Ubuntu with already frozen R90 local stock/a5 trees and
existing pinned R86 dependency source directories. Never edits prior trees.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

UP = "443a328dc71a3b7be753d52ca2b3c9a4ba77f3fd"
RESEARCH = "938698037f2c3d419a9ea6e370a99ff4fd4c4beb"
REL = Path("algorithms/PipNN")
STOCK_BLOBS = {
    "pipnn.h": "ebe6e521fbd10d2f739cc0707a005b72540392c2",
    "pipnn_utils.h": "81b91496a73baee66f2fa8237738120decb204a5",
    "neighbors.h": "877e087da7cf362d547d75f1393dfb3737d4e303",
    "CMakeLists.txt": "913ad605c7d1ef16d1cf057a8a2f89204a1ad6de",
}
A5_BLOBS = {
    "pipnn.h": "8401c9275eebe5e441a1f092679db5d2f572ed32",
    "CMakeLists.txt": "639af8f4d29d429f337ac51df376c3c05042e7df",
}
GLUE_OLD = "  add_subdirectory(${parlaylib_SOURCE_DIR} EXCLUDE_FROM_ALL)"
GLUE_NEW = "  add_subdirectory(${parlaylib_SOURCE_DIR} ${parlaylib_BINARY_DIR} EXCLUDE_FROM_ALL)"
BINARY = Path("algorithms/PipNN/neighbors-pipnn_FLOAT_T_EUCLIDEAN")
DEF_TARGET = "neighbors-pipnn_FLOAT_T_EUCLIDEAN"
HIGHWAY_SHA = "6bc2d47793bae9c521fb4150936669647700765d"


def require(cond, code):
    if not cond:
        raise RuntimeError("R90_" + code + "_HOLD")


def out(cmd, cwd=None):
    return subprocess.check_output(cmd, cwd=cwd, text=True, stderr=subprocess.STDOUT).strip()


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1048576), b""):
            h.update(block)
    return h.hexdigest()


def git_blob(path):
    return out(["git", "hash-object", str(path)])


def roots():
    home = Path.home()
    base = home / "ann-task-a/experiments/R90/a5_stock_443a328_v0"
    repo = home / "ann-task-a/experiments/R90/r90_github_a5_review_v0"
    build = home / "ann-task-a/experiments/R90/r90_p0_stock_a5_compile_gate_v1"
    return base, repo, build


def dep_paths():
    home = Path.home()
    root = home / "ann-task-a/experiments/R86/r86_v1_2_builds/stock_off/_deps"
    h85 = home / "ann-task-a/experiments/H85/r85_0_matched_baseline/build_stock/_deps/highway-src"
    return {
        "PARLAYLIB": root / "parlaylib-src",
        "EIGEN": root / "eigen-src",
        "ABSEIL-CPP": root / "abseil-cpp-src",
        "HIGHWAY": h85,
        "GOOGLEBENCHMARK": root / "googlebenchmark-src",
    }


def git_info(path):
    require(path.is_dir(), "MISSING_SOURCE_DIR_" + path.name)
    return out(["git", "-C", str(path), "rev-parse", "HEAD"])


def preflight(print_report=True):
    base, repo, build = roots()
    stock, a5 = base / "stock", base / "a5"
    require(git_info(stock) == UP, "UPSTREAM_COMMIT")
    require(git_info(a5) == UP, "A5_UPSTREAM_BASE_COMMIT")
    require(git_info(repo) == RESEARCH, "RESEARCH_BRANCH_COMMIT")
    require(not out(["git", "-C", str(stock), "status", "--porcelain"]), "STOCK_DIRTY")
    changed = out(["git", "-C", str(a5), "diff", "--name-only"]).splitlines()
    require(sorted(changed) == ["algorithms/PipNN/CMakeLists.txt", "algorithms/PipNN/pipnn.h"], "A5_UNEXPECTED_SOURCE_DIFF")
    require(not out(["git", "-C", str(a5), "diff", "--check"]), "A5_DIFF_WHITESPACE")
    blob_receipt = {}
    for arm, source in (("stock", stock), ("a5", a5)):
        require((source / "external/mirage/CMakeLists.txt").is_file(), "MIRAGE_CHECKOUT_INCOMPLETE")
        for name, b in STOCK_BLOBS.items():
            actual = git_blob(source / REL / name)
            expected = A5_BLOBS.get(name, b) if arm == "a5" else b
            require(actual == expected, f"{arm.upper()}_{name.replace('.', '_')}_GIT_BLOB")
            blob_receipt[arm + "/" + name] = actual
        root_cmake = (source / "CMakeLists.txt").read_text()
        require(root_cmake.count(GLUE_OLD) == 1 and GLUE_NEW not in root_cmake, "UPSTREAM_CMAKE_GLUE_CHANGED")
    deps = {}
    for name, path in dep_paths().items():
        require(path.is_dir() and (path / "CMakeLists.txt").is_file(), f"DEP_{name}_MISSING")
        try:
            deps[name] = {"path": str(path.resolve()), "commit": git_info(path)}
        except (subprocess.CalledProcessError, FileNotFoundError):
            raise RuntimeError("R90_DEP_" + name + "_NON_GIT_HOLD")
    require(deps["HIGHWAY"]["commit"] == HIGHWAY_SHA, "HIGHWAY_DEP_SHA")
    for cmd in ("cmake", "c++", "git"):
        require(shutil.which(cmd) is not None, "MISSING_" + cmd)
    receipt = {"upstream_commit": UP, "research_commit": RESEARCH,
               "stock": str(stock), "a5": str(a5), "source_git_blobs": blob_receipt,
               "build_root": str(build), "deps": deps,
               "expected_glue_fix": {"before": GLUE_OLD, "after": GLUE_NEW},
               "compiler": out(["c++", "--version"]).splitlines()[0],
               "cmake": out(["cmake", "--version"]).splitlines()[0]}
    if print_report:
        print("R90_P0_SOURCE_UPSTREAM_2FILE_DIFF_GIT_BLOB_PASS")
        print("R90_P0_DEPENDENCY_PINNED_R86_H85_PREFLIGHT_PASS", json.dumps({k:v["commit"] for k,v in deps.items()}, sort_keys=True))
        print("R90_P0_PREPARATION_ONLY_NOT_COMPILED")
    return receipt


def selftest():
    sample = f"line\n{GLUE_OLD}\nline\n"
    require(sample.count(GLUE_OLD) == 1, "SELFTEST_ANCHOR")
    fixed = sample.replace(GLUE_OLD, GLUE_NEW)
    require(fixed.count(GLUE_NEW) == 1 and GLUE_OLD not in fixed, "SELFTEST_PATCH")
    require(sorted(["algorithms/PipNN/pipnn.h", "algorithms/PipNN/CMakeLists.txt"]) == ["algorithms/PipNN/CMakeLists.txt", "algorithms/PipNN/pipnn.h"], "SELFTEST_DIFF")
    print("R90_P0_PURE_SELFTEST_COMMON_CMAKE_GLUE_PATCH_PASS")


def run_capture(cmd, log, cwd=None):
    print("R90_COMMAND", " ".join(map(str, cmd)), "LOG", log, flush=True)
    with open(log, "w", encoding="utf-8") as f:
        p = subprocess.run(cmd, cwd=cwd, stdout=f, stderr=subprocess.STDOUT, check=False)
    if p.returncode != 0:
        tail = log.read_text(errors="replace").splitlines()[-25:]
        for line in tail:
            print("R90_FAILURE_LOG_TAIL", line[:300])
        raise RuntimeError("R90_NATIVE_CPP_CONFIGURE_OR_BUILD_FAILED_EXIT_" + str(p.returncode) + "_HOLD")


def copy_source(source, dest):
    def ignore(_dir, contents):
        return {p for p in contents if p in (".git", "build", "build_off", "build_on", "build_r90")}
    shutil.copytree(source, dest, ignore=ignore, symlinks=True)
    path = dest / "CMakeLists.txt"
    text = path.read_text()
    require(text.count(GLUE_OLD) == 1, "GLUE_PATCH_ANCHOR")
    path.write_text(text.replace(GLUE_OLD, GLUE_NEW))
    return sha256(path)


def build():
    receipt = preflight()
    base, repo, root = roots()
    require(not root.exists() and not root.is_symlink(), "BUILD_OUTPUT_EXISTS")
    root.mkdir(parents=True)
    receipt["arms"] = {}
    for arm, macro in (("stock", "OFF"), ("a5", "ON")):
        src = root / (arm + "_source")
        build_dir = root / (arm + "_build")
        root_hash = copy_source(base / arm, src)
        require(root_hash and (src / REL / "pipnn.h").is_file(), "COPIED_SOURCE")
        params = ["cmake", "-S", str(src), "-B", str(build_dir),
                  "-DCMAKE_BUILD_TYPE=Release", "-DCMAKE_CXX_FLAGS=-O3 -pthread",
                  "-DCMAKE_EXPORT_COMPILE_COMMANDS=ON", "-DFETCHCONTENT_FULLY_DISCONNECTED=ON"]
        if arm == "a5":
            params += ["-DR90_A5_GATE=ON"]
        for dep, data in receipt["deps"].items():
            params += [f"-DFETCHCONTENT_SOURCE_DIR_{dep}={data['path']}"]
        run_capture(params, root / (arm + "_configure.log"))
        run_capture(["cmake", "--build", str(build_dir), "--target", DEF_TARGET, "--parallel", "2"],
                    root / (arm + "_build.log"))
        binary = build_dir / BINARY
        require(binary.is_file() and binary.stat().st_size > 1024, arm.upper() + "_ELF_MISSING")
        cmd_file = build_dir / "compile_commands.json"
        require(cmd_file.is_file(), arm.upper() + "_COMPILE_COMMANDS_MISSING")
        receipt["arms"][arm] = {
            "root_cmake_glue_sha256": root_hash,
            "pipnn_h_sha256": sha256(src / REL / "pipnn.h"),
            "pipnn_utils_h_sha256": sha256(src / REL / "pipnn_utils.h"),
            "bin_path": str(binary), "elf_sha256": sha256(binary),
            "compile_commands_sha256": sha256(cmd_file),
            "configure_log_sha256": sha256(root / (arm + "_configure.log")),
            "build_log_sha256": sha256(root / (arm + "_build.log")),
            "macro": macro,
        }
        print(f"R90_P0_{arm.upper()}_CPP_ELF_BUILD_PASS", json.dumps(receipt["arms"][arm], sort_keys=True))
    (root / "RECEIPT.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print("R90_P0_BOTH_CPP_SOURCE_COMPILATION_COMPLETE_NO_NATIVE_GRAPH_BUILT")


def audit():
    _, _, root = roots()
    receipt_path = root / "RECEIPT.json"
    require(receipt_path.is_file(), "NO_BUILD_RECEIPT")
    data = json.loads(receipt_path.read_text())
    require(data["upstream_commit"] == UP and data["research_commit"] == RESEARCH, "RECEIPT_ID")
    for arm in ("stock", "a5"):
        d = data["arms"][arm]
        src = root / (arm + "_source")
        require(sha256(src / "CMakeLists.txt") == d["root_cmake_glue_sha256"], "AUDIT_CMAKE_GLUE")
        require(sha256(src / REL / "pipnn.h") == d["pipnn_h_sha256"], "AUDIT_PIPNN_SOURCE")
        require(sha256(src / REL / "pipnn_utils.h") == d["pipnn_utils_h_sha256"], "AUDIT_UTILS_SOURCE")
        require(sha256(Path(d["bin_path"])) == d["elf_sha256"], "AUDIT_BINARY")
        require(sha256(root / (arm + "_build/compile_commands.json")) == d["compile_commands_sha256"], "AUDIT_COMPILE_COMMANDS")
        for tag in ("configure", "build"):
            require(sha256(root / f"{arm}_{tag}.log") == d[f"{tag}_log_sha256"], "AUDIT_LOG_" + tag)
    print("R90_P0_STOCK_A5_CPP_ELF_SOURCE_DEP_RECEIPTS_AUDIT_PASS_NO_GRAPH_SEARCH_RUN")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("mode", choices=["selftest", "preflight", "build", "audit"])
    a = p.parse_args()
    try:
        {"selftest": selftest, "preflight": preflight, "build": build, "audit": audit}[a.mode]()
    except (RuntimeError, subprocess.CalledProcessError, OSError, KeyError, ValueError) as exc:
        print("R90_P0_HOLD", str(exc), file=sys.stderr)
        sys.exit(2)

if __name__ == "__main__":
    main()
