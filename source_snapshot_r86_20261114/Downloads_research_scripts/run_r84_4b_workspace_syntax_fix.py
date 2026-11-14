#!/usr/bin/env python3
"""R84.4b: repair the R84.4 case-sensitive W-only accessor call and re-run syntax.

Runs on the USER's Ubuntu, where R84.4 staged sources and compiler DB exist.
Never edits H70, H80, or the original failed R84.4 directory. No native BUILD.
"""
from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

PIN = "443a328dc71a3b7be753d52ca2b3c9a4ba77f3fd"
OLD_SCRIPT_SHA = "7651b41e95a504027e8471f03ada518ed5da95bc2d985c070f1570880db193dd"
ORIGINAL_UTILS_SHA = "7083e8183554a1cb586b70cdb4c57920f49ec5a50680096aecf6b873f596595d"
ORIGINAL_PIPNN_SHA = "f4391ad8712d7757423dca872f9042c3271660dffde384a85b93854b9692f288"
SOURCE_DIR = "experiments/H70/pipnn-clean-443a328"
OLD_DIR = "experiments/H84/r84_4_workspace_stage_syntax"
NEW_DIR = "experiments/H84/r84_4b_workspace_syntax_fix"
BAD = """  auto N = active_indices.size();
  eigen_build_distmat(active_indices, Points);
  float* dist_mat = (float*)get_dist_mat(n);"""
GOOD = """  auto N = active_indices.size();
  eigen_build_distmat(active_indices, Points);
  float* dist_mat = (float*)get_dist_mat(N);"""


def require(p: bool, message: str):
    if not p:
        raise RuntimeError(message)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha_file(p: Path) -> str:
    return sha(p.read_bytes())


def fix(old: str) -> str:
    require(old.count(BAD) == 1 and old.count(GOOD) == 0,
            "R84_4B_BAD_EIGEN_KNN_CALLSITE_NOT_EXACT")
    require(old.count("get_dist_mat(n)") == 2,
            "R84_4B_EXPECTED_TWO_N_ACCESSOR_CALLS")
    require(old.count("get_point_mat(n, dimension)") == 1,
            "R84_4B_EXPECTED_ONE_POINT_ACCESSOR_CALL")
    new = old.replace(BAD, GOOD, 1)
    require(new.count("get_dist_mat(n)") == 1 and new.count("get_dist_mat(N)") == 1,
            "R84_4B_ACCESSOR_COUNTS_AFTER_FIX_FAIL")
    require(new.replace(GOOD, BAD, 1) == old, "R84_4B_NONLOCAL_CHANGE")
    return new


def selftest():
    x = "prefix\n" + BAD + "\n  float* point_mat = (float*)get_point_mat(n, dimension);\n" + "float* d = (float*)get_dist_mat(n);\n"
    y = fix(x)
    require(GOOD in y and BAD not in y, "R84_4B_SELFTEST_EDIT_FAIL")
    require(y.replace(GOOD, BAD, 1) == x, "R84_4B_SELFTEST_INVERSE_FAIL")
    print("R84_4B_PATCH_LOCALITY_SELFTEST_PASS", flush=True)


def preflight(root: Path):
    orig = root / SOURCE_DIR
    old = root / OLD_DIR
    dest = root / NEW_DIR
    require(not dest.exists(), "R84_4B_OUTPUT_EXISTS_FAIL_CLOSED")
    require(orig.is_dir() and old.is_dir(), "R84_4B_MISSING_R84_4_OR_H70")
    git_head = subprocess.check_output(["git", "-C", str(orig), "rev-parse", "HEAD"], text=True).strip()
    require(git_head == PIN, "R84_4B_H70_COMMIT_CHANGED")
    original_util = orig / "algorithms/PipNN/pipnn_utils.h"
    original_pip = orig / "algorithms/PipNN/pipnn.h"
    require(sha_file(original_util) == ORIGINAL_UTILS_SHA and sha_file(original_pip) == ORIGINAL_PIPNN_SHA,
            "R84_4B_H70_SOURCE_SHA_CHANGED")
    old_runner = root / "../Downloads/run_r84_4_workspace_stage_syntax.py"
    # On the user's machine ROOT=$HOME/ann-task-a; downloads is its sibling.
    if not old_runner.is_file():
        old_runner = Path.home() / "Downloads/run_r84_4_workspace_stage_syntax.py"
    require(old_runner.is_file() and sha_file(old_runner) == OLD_SCRIPT_SHA,
            "R84_4B_R84_4_SCRIPT_PIN_MISSING_OR_CHANGED")
    # Import the pinned stage tool as a pure source-text transform, validating
    # the W header is precisely the one produced by the previous experiment.
    import importlib.util
    loader = importlib.util.spec_from_file_location("r84_4_pinned", old_runner)
    require(loader is not None and loader.loader is not None, "R84_4B_IMPORT_SPEC_FAIL")
    module = importlib.util.module_from_spec(loader)
    loader.loader.exec_module(module)
    stage = old / "W/algorithms/PipNN/pipnn_utils.h"
    d0stage = old / "D0/algorithms/PipNN/pipnn_utils.h"
    require(stage.is_file() and d0stage.is_file(), "R84_4B_OLD_STAGE_MISSING")
    raw = original_util.read_text()
    require(d0stage.read_text() == raw and stage.read_text() == module.patch(raw),
            "R84_4B_STAGE_PROVENANCE_MISMATCH")
    report_path = old / "r84_4_summary.json"
    require(report_path.is_file(), "R84_4B_R84_4_SUMMARY_MISSING")
    oldreport = json.loads(report_path.read_text())
    require(oldreport.get("arms", {}).get("D0", {}).get("exit_code") == 0 and
            oldreport.get("arms", {}).get("W", {}).get("exit_code") not in (None, 0),
            "R84_4B_R84_4_FAILURE_STATE_UNEXPECTED")
    oldlog = old / "W/compiler.log"
    require(oldlog.is_file(), "R84_4B_OLD_COMPILER_LOG_MISSING")
    err = [z.strip() for z in oldlog.read_text(errors="replace").splitlines() if re.search(r"\berror:", z)]
    print("R84_4B_OLD_COMPILER_ERRORS", json.dumps(err[:12], ensure_ascii=False), flush=True)
    require(any(re.search(r"['‘]n['’].*not declared", e, re.IGNORECASE) for e in err),
            "R84_4B_COMPILER_LOG_DOES_NOT_CONFIRM_N_ERROR_REVIEW_ERRORS")
    fixed = fix(stage.read_text())
    command_path = old / "W/compile_command.txt"
    require(command_path.is_file(), "R84_4B_COMPILE_COMMAND_MISSING")
    oldargv = shlex.split(command_path.read_text().strip())
    require(oldargv and oldargv.count("-fsyntax-only") == 1 and
            "-DR84_LEAF_WORKSPACE=1" in oldargv, "R84_4B_SYNTAX_COMMAND_NOT_PINNED")
    old_w_root = str(old / "W")
    new_w_root = str(dest / "W")
    require(sum(old_w_root in x for x in oldargv) >= 2,
            "R84_4B_COMMAND_NO_STAGE_OVERRIDES")
    cmd = [x.replace(old_w_root, new_w_root) for x in oldargv]
    require(all(old_w_root not in x for x in cmd), "R84_4B_COMMAND_REWRITE_INCOMPLETE")
    require(any(x.startswith("-I") and new_w_root in x for x in cmd),
            "R84_4B_OVERLAY_INCLUDE_MISSING")
    benchmark = oldreport.get("compiler_db")
    require(benchmark and Path(benchmark).is_file(), "R84_4B_COMPILER_DB_MISSING")
    dbp, entry, original_compiler_argv = module.spec(root, orig)
    require(str(dbp) == benchmark,
            "R84_4B_COMPILER_DB_SELECTED_CHANGED")
    require(original_compiler_argv[0] == cmd[0],
            "R84_4B_COMPILER_EXECUTABLE_CHANGED")
    cwd = Path(entry["directory"])
    require(cwd.is_dir(), "R84_4B_COMPILER_WORKDIR_MISSING")
    require(shutil.which(cmd[0]) or Path(cmd[0]).is_file(), "R84_4B_COMPILER_NOT_FOUND")
    return {
        "root": root, "original_utils": original_util, "old_dir": old, "new_dir": dest,
        "old_util": stage, "fixed": fixed, "cwd": cwd, "cmd": cmd,
        "old_report": oldreport, "old_log_errors": err,
    }


def execute(ctx: dict, dry_run: bool):
    dest = ctx["new_dir"]
    print("R84_4B_H70_PINNED_AND_R84_4_FAILED_STAGE_VERIFIED", flush=True)
    print("R84_4B_CONFIRMED_FIX eigen_knn_get_dist_mat_n_to_N", flush=True)
    if dry_run:
        print(f"R84_4B_DRY_RUN_PASS_NO_WRITES planned_dir={dest}", flush=True)
        return
    old_w = ctx["old_dir"] / "W"
    new_w = dest / "W"
    dest.mkdir(parents=True, exist_ok=False)
    shutil.copytree(old_w, new_w, symlinks=True)
    header = new_w / "algorithms/PipNN/pipnn_utils.h"
    header.write_text(ctx["fixed"])
    # Copy old error log for comparison, keeping all previous R84.4 artifacts unchanged.
    oldlog = new_w / "compiler.log"
    oldlog.rename(new_w / "r84_4_old_compiler.log")
    cmd_path = new_w / "compile_command.txt"
    cmd_path.write_text(shlex.join(ctx["cmd"]) + "\n")
    src = ctx["original_utils"].read_text()
    (dest / "W_vs_D0.diff").write_text("".join(difflib.unified_diff(
        src.splitlines(keepends=True), ctx["fixed"].splitlines(keepends=True),
        fromfile="D0/pipnn_utils.h", tofile="W/pipnn_utils.h")))
    report = {
        "status": "R84_4B_SYNTAX_RUNNING", "corrected_header_sha256": sha_file(header),
        "original_header_sha256": sha_file(ctx["original_utils"]),
        "previous_attempt": str(ctx["old_dir"]),
        "old_error_excerpt": ctx["old_log_errors"][:12],
        "compile_workdir": str(ctx["cwd"]),
        "compiler_command": shlex.join(ctx["cmd"]),
        "note": "No object compilation, linking, graph BUILD, or Recall."
    }
    summary = dest / "r84_4b_summary.json"
    summary.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    print("R84_4B_W_SYNTAX_START", flush=True)
    with (new_w / "compiler.log").open("x") as fp:
        proc = subprocess.run(ctx["cmd"], cwd=ctx["cwd"], stdout=fp, stderr=subprocess.STDOUT, check=False)
    report["exit_code"] = proc.returncode
    report["compiler_log"] = str(new_w / "compiler.log")
    report["compiler_errors"] = [x.strip() for x in (new_w / "compiler.log").read_text(errors="replace").splitlines() if "error:" in x][:20]
    if proc.returncode:
        report["status"] = "R84_4B_W_SYNTAX_FAIL"
        summary.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
        print("R84_4B_NEW_COMPILER_ERRORS", json.dumps(report["compiler_errors"], ensure_ascii=False), flush=True)
        raise RuntimeError(f"R84_4B_W_SYNTAX_FAIL log={new_w / 'compiler.log'}")
    require(sha_file(ctx["original_utils"]) == ORIGINAL_UTILS_SHA,
            "R84_4B_H70_UTILS_CHANGED_DURING_SYNTAX")
    report["status"] = "R84_4B_W_FULL_INSTANTIATION_SYNTAX_PASS"
    summary.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    print("R84_4B_W_FULL_INSTANTIATION_SYNTAX_PASS", flush=True)
    print("R84_4B_MATCHED_D0_PREVIOUS_PASS_W_FIXED_PASS", flush=True)
    print("R84_4B_NO_OBJECT_NO_LINK_NO_ANN_BUILD_NO_GRAPH_NO_RECALL_NO_PUSH", flush=True)
    print("R84_4B_REPORT", summary, flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--selftest", action="store_true")
    modes.add_argument("--dry-run", action="store_true")
    modes.add_argument("--run", action="store_true")
    args = parser.parse_args()
    selftest()
    if args.selftest:
        return
    context = preflight(args.root.resolve())
    execute(context, args.dry_run)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("R84_4B_STOP", e, file=sys.stderr)
        sys.exit(2)
