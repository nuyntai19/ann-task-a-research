#!/usr/bin/env python3
"""R84.5: matched D0/W native object compile and link on the user's Ubuntu PC.

Inputs: H70 pinned source; R84.4 D0 syntax PASS; R84.4b W corrected syntax PASS;
original CMake FLOAT/L2 compile/link specifications. No graph, BUILD, SEARCH, H70
source writes, or Git operations. Fails closed if any provenance is ambiguous.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

PIN = "443a328dc71a3b7be753d52ca2b3c9a4ba77f3fd"
TARGET = "neighbors-pipnn_FLOAT_T_EUCLIDEAN"
OLD_STAGE = Path("experiments/H84/r84_4_workspace_stage_syntax")
NEW_STAGE = Path("experiments/H84/r84_4b_workspace_syntax_fix")
DEST_REL = Path("experiments/H84/r84_5_matched_native_binary")
H70_REL = Path("experiments/H70/pipnn-clean-443a328")
PINS = {
    "algorithms/PipNN/pipnn.h": "f4391ad8712d7757423dca872f9042c3271660dffde384a85b93854b9692f288",
    "algorithms/PipNN/pipnn_utils.h": "7083e8183554a1cb586b70cdb4c57920f49ec5a50680096aecf6b873f596595d",
    "algorithms/utils/graph.h": "17e51779f32db56c9c50b6d514a8ff68539fd19b734804df3abdb63f88dd443e",
    "algorithms/utils/r70_two_tier_lshgraph.h": "ac0bece4804c7bc552b30db0df57ee92492033065cef62330ddb58a19d470af1",
}
BAD = "  auto N = active_indices.size();\n  eigen_build_distmat(active_indices, Points);\n  float* dist_mat = (float*)get_dist_mat(n);"
GOOD = "  auto N = active_indices.size();\n  eigen_build_distmat(active_indices, Points);\n  float* dist_mat = (float*)get_dist_mat(N);"


def need(test: bool, code: str):
    if not test:
        raise RuntimeError(code)


def sha(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def json_read(path: Path) -> dict:
    need(path.is_file(), f"R84_5_JSON_MISSING {path}")
    return json.loads(path.read_text())


def locate_link(compdb: Path, workdir: Path) -> tuple[Path, list[str]]:
    """Mirror proven R83.5b locator without recursive ambiguous discovery."""
    build_root = compdb.parent.resolve()
    target_relative = Path("CMakeFiles") / (TARGET + ".dir") / "link.txt"
    candidates = [build_root / "algorithms/PipNN" / target_relative,
                  workdir / target_relative,
                  workdir / "algorithms/PipNN" / target_relative]
    uniq = list(dict.fromkeys(p.resolve() for p in candidates))
    found = [p for p in uniq if p.is_file()]
    if not found:
        print("R84_5_LINK_PROBED", " | ".join(str(p) for p in uniq), flush=True)
    need(len(found) == 1, f"R84_5_LINK_LOCATOR_EXPECT_ONE_FOUND_{len(found)}")
    link = found[0]
    need(link.is_relative_to(build_root), "R84_5_LINK_OUTSIDE_SELECTED_COMPDB")
    raw = link.read_text().strip()
    need(raw and "\n" not in raw, "R84_5_MULTILINE_LINK_TXT")
    argv = shlex.split(raw)
    need(len(argv) > 3 and not any(x.startswith("@") for x in argv), "R84_5_LINK_RESPONSE_FILE_OR_SHORT")
    need(not any(x in {"&&", "||", ";", "|", "cd"} for x in argv), "R84_5_SHELL_LINK_UNSUPPORTED")
    need(sum(x.endswith("neighborsTime.C.o") for x in argv) == 1,
         "R84_5_LINK_OBJECT_NOT_UNIQUE")
    need(argv.count("-o") == 1 and argv.index("-o") + 1 < len(argv),
         "R84_5_LINK_OUTPUT_NOT_UNIQUE")
    need(Path(argv[argv.index("-o") + 1]).name == TARGET, "R84_5_LINK_WRONG_TARGET")
    need(shutil.which(argv[0]) is not None or Path(argv[0]).is_file(), "R84_5_LINKER_NOT_FOUND")
    return link, argv


def make_link_cmd(template: list[str], obj: Path, exe: Path) -> list[str]:
    new = template.copy()
    oi = [i for i, val in enumerate(new) if val.endswith("neighborsTime.C.o")]
    need(len(oi) == 1, "R84_5_LINK_OBJECT_COUNT_NOT_ONE")
    new[oi[0]] = str(obj)
    idx = new.index("-o")
    need(not exe.exists(), "R84_5_EXE_EXISTS")
    new[idx + 1] = str(exe)
    return new


def make_object_cmd(syntax_cmd: list[str], obj: Path) -> list[str]:
    need(syntax_cmd.count("-fsyntax-only") == 1 and "-c" not in syntax_cmd,
         "R84_5_SYNTAX_CMD_UNEXPECTED")
    need("-o" not in syntax_cmd and not any(x.startswith("-o") for x in syntax_cmd[1:]),
         "R84_5_OUTPUT_FLAG_IN_SYNTAX_CMD")
    need("-x" in syntax_cmd and "c++" in syntax_cmd, "R84_5_NO_EXPLICIT_CPP_MODE")
    cmd = ["-c" if val == "-fsyntax-only" else val for val in syntax_cmd]
    cmd.extend(["-o", str(obj)])
    return cmd


def checked_syntax_command(overlay: Path, arm: str) -> list[str]:
    path = overlay / "compile_command.txt"
    need(path.is_file(), f"R84_5_{arm}_COMMAND_MISSING")
    cmd = shlex.split(path.read_text().strip())
    need(len(cmd) > 15, f"R84_5_{arm}_COMMAND_SHORT")
    need(shutil.which(cmd[0]) is not None or Path(cmd[0]).is_file(),
         f"R84_5_{arm}_COMPILER_MISSING")
    for required in ["-DUSE_DATATYPE_FLOAT_T", "-DUSE_DISTANCE_EUCLIDEAN",
                     "-DR70_TWO_TIER=1", "-DR71_H17_TOP2=1",
                     f"-DR84_LEAF_WORKSPACE={0 if arm == 'D0' else 1}"]:
        need(cmd.count(required) == 1, f"R84_5_{arm}_FLAG_MISSING_{required}")
    need("-DR84_LEAF_WORKSPACE=" + ("1" if arm == "D0" else "0") not in cmd,
         f"R84_5_{arm}_CONTRADICTORY_DEFINE")
    need(cmd.count("-fsyntax-only") == 1,
         f"R84_5_{arm}_NO_SYNTAX_FLAG")
    expected_wrapper = (overlay / "r84_4_real_benchmark_instantiation.cc").resolve()
    need(cmd.count(str(expected_wrapper)) == 1,
         f"R84_5_{arm}_WRAPPER_NOT_SELECTED")
    need(cmd.count(f"-I{overlay / 'algorithms'}") == 1,
         f"R84_5_{arm}_OWN_OVERLAY_INCLUDE_MISSING")
    other = (Path(NEW_STAGE) if arm == "D0" else Path(OLD_STAGE))
    need(not any(str(other) in x for x in cmd), f"R84_5_{arm}_OTHER_OVERLAY_LEAK")
    need(not any(re.match(r"-DR(?:78|79|80|81|82|83)_", x) for x in cmd),
         f"R84_5_{arm}_FOREIGN_EXPERIMENT_DEFINE")
    return cmd


def check_overlay(base: Path, stage: Path, arm: str):
    pip = stage / "algorithms/PipNN"
    need(pip.is_dir(), f"R84_5_{arm}_OVERLAY_MISSING")
    for name in ("pipnn.h", "neighbors.h"):
        need(sha(pip / name) == sha(base / "algorithms/PipNN" / name),
             f"R84_5_{arm}_{name}_NOT_BASELINE")
    for name in ("utils", "bench"):
        node = stage / "algorithms" / name
        need(node.is_symlink() and node.resolve() ==
             (base / "algorithms" / name).resolve(),
             f"R84_5_{arm}_{name}_SYMLINK_NOT_PINNED")
    wrapper = stage / "r84_4_real_benchmark_instantiation.cc"
    expected = ('#include "algorithms/PipNN/neighbors.h"\n'
                f'#include "{base / "algorithms/bench/neighborsTime.C"}"\n')
    need(wrapper.read_text() == expected, f"R84_5_{arm}_WRAPPER_CHANGED")
    return pip / "pipnn_utils.h"


def preflight(root: Path) -> dict:
    base = root / H70_REL
    old = root / OLD_STAGE
    new = root / NEW_STAGE
    out = root / DEST_REL
    need(base.is_dir(), "R84_5_H70_MISSING")
    need(not out.exists(), "R84_5_OUTPUT_EXISTS_FAIL_CLOSED")
    head = subprocess.check_output(["git", "-C", str(base), "rev-parse", "HEAD"], text=True).strip()
    need(head == PIN, "R84_5_H70_PIN_COMMIT_FAIL")
    for rel, wanted in PINS.items():
        need(sha(base / rel) == wanted, f"R84_5_H70_SHA_FAIL {rel}")
    r4 = json_read(old / "r84_4_summary.json")
    r4b = json_read(new / "r84_4b_summary.json")
    need(r4.get("source_commit") == PIN, "R84_5_R84_4_REPORT_COMMIT_MISMATCH")
    need(r4.get("arms", {}).get("D0", {}).get("exit_code") == 0,
         "R84_5_R84_4_D0_SYNTAX_NOT_PASS")
    need(r4.get("arms", {}).get("W", {}).get("exit_code") not in (0, None),
         "R84_5_R84_4_W_WAS_NOT_RECORDED_FAILURE")
    need(r4b.get("status") == "R84_4B_W_FULL_INSTANTIATION_SYNTAX_PASS" and
         r4b.get("exit_code") == 0, "R84_5_R84_4B_W_SYNTAX_NOT_PASS")
    d0 = old / "D0"
    w = new / "W"
    d0util = check_overlay(base, d0, "D0")
    wutil = check_overlay(base, w, "W")
    need(sha(d0util) == PINS["algorithms/PipNN/pipnn_utils.h"],
         "R84_5_D0_UTILS_SOURCE_CHANGED")
    oldw = (old / "W/algorithms/PipNN/pipnn_utils.h").read_text()
    need(oldw.count(BAD) == 1 and oldw.count(GOOD) == 0,
         "R84_5_OLD_W_FAIL_STAGE_NOT_PINNED")
    neww = wutil.read_text()
    need(neww == oldw.replace(BAD, GOOD, 1),
         "R84_5_W_SOURCE_NOT_PRECISE_R84_4B_PATCH")
    need(sha(wutil) == r4b.get("corrected_header_sha256"),
         "R84_5_W_HEADER_SHA_REPORT_MISMATCH")
    need(sha(d0util) == r4.get("arms", {}).get("D0", {}).get("utils_sha256"),
         "R84_5_D0_STAGE_REPORT_SHA_MISMATCH")
    # Ensure only the corrected case-switch is the difference from failed W stage.
    need(neww.count("get_dist_mat(N)") == 1 and
         neww.count("get_dist_mat(n)") == 1 and
         neww.count("get_point_mat(n, dimension)") == 1,
         "R84_5_W_WORKSPACE_CALLSITE_COUNTS_FAIL")
    d0cmd = checked_syntax_command(d0, "D0")
    wcmd = checked_syntax_command(w, "W")
    need(d0cmd[0] == wcmd[0], "R84_5_DIFFERENT_COMPILERS")
    def normalize(cmd, overlay, arm):
        result = []
        for x in cmd:
            x = x.replace(str(overlay), "<OVERLAY>")
            if x == f"-DR84_LEAF_WORKSPACE={0 if arm=='D0' else 1}":
                x = "-DR84_LEAF_WORKSPACE=<ARM>"
            result.append(x)
        return result
    need(normalize(d0cmd, d0, "D0") == normalize(wcmd, w, "W"),
         "R84_5_UNMATCHED_COMPILE_SPECS")
    compdb = Path(r4.get("compiler_db", ""))
    need(compdb.is_file() and compdb.name == "compile_commands.json",
         "R84_5_COMPILE_DB_MISSING")
    raw = json_read(compdb)
    candidates = []
    for item in raw:
        argv = item.get("arguments") or shlex.split(item.get("command", ""))
        if (TARGET not in " ".join(argv) or
            "-DUSE_DATATYPE_FLOAT_T" not in argv or
            "-DUSE_DISTANCE_EUCLIDEAN" not in argv):
            continue
        src = Path(item.get("file", ""))
        if not src.is_absolute():
            src = Path(item["directory"]) / src
        if (src.is_file() and src.name == "neighborsTime.C" and
                sha(src) == sha(base / "algorithms/bench/neighborsTime.C")):
            candidates.append(item)
    need(len(candidates) == 1, f"R84_5_MATCHED_COMPILE_DB_COUNT_{len(candidates)}")
    workdir = Path(candidates[0]["directory"]).resolve()
    need(workdir.is_dir() and workdir == Path(r4b["compile_workdir"]).resolve(),
         "R84_5_R84_4B_WORKDIR_MISMATCH")
    linkfile, linkargv = locate_link(compdb, workdir)
    need(Path(linkargv[0]).name in ("c++", "g++", "clang++") or
         "c++" in Path(linkargv[0]).name,
         "R84_5_UNEXPECTED_LINKER")
    need((linkfile.parent.parent.parent).is_dir(), "R84_5_LINK_CWD_INVALID")
    print("R84_5_PINNED_H70_R84_4_D0_R84_4B_W_SOURCE_GATES_PASS", flush=True)
    print("R84_5_MATCHED_FLOAT_L2_COMPILER_LINK_SPEC_PASS",
          f"compiler={d0cmd[0]}", f"compile_db={compdb}", f"link={linkfile}", flush=True)
    return {"root": root, "base": base, "old": old, "new": new, "out": out,
            "workdir": workdir, "compiler_db": compdb, "link_file": linkfile,
            "link_argv": linkargv, "syntax_cmd": {"D0": d0cmd, "W": wcmd},
            "source": {"D0": d0util, "W": wutil}}


def selftest():
    a = ["/usr/bin/c++", "-I/tmp/overlay/algorithms", "-DUSE_DATATYPE_FLOAT_T",
         "-DUSE_DISTANCE_EUCLIDEAN", "-fsyntax-only", "-x", "c++", "/tmp/overlay/x.cc"]
    b = make_object_cmd(a, Path("/tmp/result.o"))
    need(b == ["/usr/bin/c++", "-I/tmp/overlay/algorithms", "-DUSE_DATATYPE_FLOAT_T",
               "-DUSE_DISTANCE_EUCLIDEAN", "-c", "-x", "c++",
               "/tmp/overlay/x.cc", "-o", "/tmp/result.o"], "R84_5_COMPILE_SELFTEST_FAIL")
    link = ["/usr/bin/c++", "CMakeFiles/foo.dir/neighborsTime.C.o", "-o", TARGET, "-lm"]
    fixed = make_link_cmd(link, Path("/tmp/result.o"), Path("/tmp/out"))
    need(fixed == ["/usr/bin/c++", "/tmp/result.o", "-o", "/tmp/out", "-lm"],
         "R84_5_LINK_SELFTEST_FAIL")
    with tempfile.TemporaryDirectory(prefix="r84_5_linktest_") as td:
        build = Path(td) / "build"
        targetdir = build / "algorithms/PipNN"
        linkfile = targetdir / "CMakeFiles" / (TARGET + ".dir") / "link.txt"
        linkfile.parent.mkdir(parents=True)
        linkfile.write_text(f"/usr/bin/c++ CMakeFiles/abc.dir/neighborsTime.C.o -o {TARGET} -lm\n")
        got, _ = locate_link(build / "compile_commands.json", targetdir)
        need(got == linkfile, "R84_5_LINK_LOCATOR_SELFTEST_FAIL")
    print("R84_5_MATCHED_COMPILE_AND_LINK_SELFTEST_PASS", flush=True)


def run(ctx, dry_run: bool):
    out = ctx["out"]
    if dry_run:
        print("R84_5_DRY_RUN_PASS_NO_WRITES", f"planned_dir={out}", flush=True)
        return
    out.mkdir(parents=True, exist_ok=False)
    report = {"status": "RUNNING", "source_commit": PIN,
              "baseline": "D0=H17+TwoTier", "experimental": "W=grow-only-leaf-workspace",
              "compile_db": str(ctx["compiler_db"]), "link_file": str(ctx["link_file"]),
              "build_host": subprocess.run(["uname", "-m"], capture_output=True, text=True).stdout.strip(),
              "compiler_version": subprocess.run([ctx["syntax_cmd"]["D0"][0], "--version"],
                                                 capture_output=True, text=True).stdout.splitlines()[:1],
              "variants": {}, "note": "native object + link only; not graph BUILD or parity"}
    dest_report = out / "r84_5_summary.json"
    dest_report.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    for arm in ("D0", "W"):
        dest = out / arm
        dest.mkdir(parents=True, exist_ok=False)
        obj = dest / "neighborsTime.C.o"
        exe = dest / TARGET
        cmd = make_object_cmd(ctx["syntax_cmd"][arm], obj)
        need(not obj.exists(), f"R84_5_{arm}_OBJECT_EXISTS")
        (dest / "compile_command.txt").write_text(shlex.join(cmd) + "\n")
        print(f"R84_5_{arm}_OBJECT_COMPILE_START", flush=True)
        with (dest / "compile.log").open("x") as log:
            done = subprocess.run(cmd, cwd=ctx["workdir"], stdout=log, stderr=subprocess.STDOUT,
                                  check=False)
        report["variants"][arm] = {"compile_exit": done.returncode,
                                     "source_header_sha256": sha(ctx["source"][arm])}
        dest_report.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
        if done.returncode:
            errors = [x for x in (dest / "compile.log").read_text(errors="replace").splitlines()
                      if "error:" in x or "fatal error:" in x]
            print("R84_5_COMPILE_ERRORS", "\n".join(errors[:10]) or
                  (dest / "compile.log").read_text(errors="replace")[-1500:], file=sys.stderr)
            raise RuntimeError(f"R84_5_{arm}_OBJECT_COMPILE_FAIL log={dest / 'compile.log'}")
        need(obj.is_file() and obj.stat().st_size > 0,
             f"R84_5_{arm}_OBJECT_NOT_WRITTEN")
        report["variants"][arm]["object_sha256"] = sha(obj)
        print(f"R84_5_{arm}_OBJECT_COMPILE_PASS sha256={sha(obj)}", flush=True)
        link_cmd = make_link_cmd(ctx["link_argv"], obj, exe)
        (dest / "link_command.txt").write_text(shlex.join(link_cmd) + "\n")
        print(f"R84_5_{arm}_NATIVE_LINK_START", flush=True)
        with (dest / "link.log").open("x") as log:
            done = subprocess.run(link_cmd,
                                  cwd=ctx["link_file"].parent.parent.parent,
                                  stdout=log, stderr=subprocess.STDOUT, check=False)
        report["variants"][arm]["link_exit"] = done.returncode
        dest_report.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
        if done.returncode:
            print("R84_5_LINK_ERRORS", (dest / "link.log").read_text(errors="replace")[-2500:],
                  file=sys.stderr)
            raise RuntimeError(f"R84_5_{arm}_LINK_FAIL log={dest / 'link.log'}")
        need(exe.is_file() and exe.stat().st_size > 0 and exe.read_bytes()[:4] == b"\x7fELF",
             f"R84_5_{arm}_NOT_AN_ELF")
        report["variants"][arm]["binary_path"] = str(exe)
        report["variants"][arm]["binary_sha256"] = sha(exe)
        dest_report.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
        print(f"R84_5_{arm}_NATIVE_LINK_PASS sha256={sha(exe)}", flush=True)
    need(sha(ctx["source"]["D0"]) == PINS["algorithms/PipNN/pipnn_utils.h"],
         "R84_5_D0_SOURCE_CHANGED_DURING_BUILD")
    need(sha(ctx["source"]["W"]) == json_read(ctx["new"] / "r84_4b_summary.json")["corrected_header_sha256"],
         "R84_5_W_SOURCE_CHANGED_DURING_BUILD")
    for rel, expected in PINS.items():
        need(sha(ctx["base"] / rel) == expected, f"R84_5_H70_SOURCE_CHANGED_DURING_BUILD {rel}")
    report["status"] = "R84_5_PAIRED_NATIVE_BINARY_BUILD_PASS"
    dest_report.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    print("R84_5_PAIRED_NATIVE_BINARY_BUILD_PASS", flush=True)
    print("R84_5_NO_GRAPH_BUILD_NO_SEARCH_NO_RECALL_NO_PUSH", flush=True)
    print("R84_5_REPORT", dest_report, flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=False)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--selftest", action="store_true")
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--run", action="store_true")
    args = parser.parse_args()
    selftest()
    if args.selftest:
        return
    need(args.root is not None, "R84_5_ROOT_REQUIRED")
    ctx = preflight(args.root.expanduser().resolve())
    run(ctx, args.dry_run)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("R84_5_STOP", str(e), file=sys.stderr, flush=True)
        sys.exit(2)
