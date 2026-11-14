#!/usr/bin/env python3
"""R83.5 source-pinned matched D0/E compile+link, NO ANN execution.

Inputs: verified R83.4b overlays, exact H70 working tree, existing CMake
compile_commands.json and target link.txt. Outputs only H83/R83.5.
No source edits, no CMake reconfiguration, no data or graph access.
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
from pathlib import Path

COMMIT = "443a328dc71a3b7be753d52ca2b3c9a4ba77f3fd"
TARGET = "neighbors-pipnn_FLOAT_T_EUCLIDEAN"
ORIG = {
    "pipnn.h": "f4391ad8712d7757423dca872f9042c3271660dffde384a85b93854b9692f288",
    "pipnn_utils.h": "7083e8183554a1cb586b70cdb4c57920f49ec5a50680096aecf6b873f596595d",
}
STAGED = {
    "pipnn.h": "1788d8541db1727c3aaa39e84c9e915c240847338f69b53d8ff5e0c72e57e1a6",
    "pipnn_utils.h": "17941f13594fdbd2479464ea417878d899e71ce546835ffe0d711bee6713f669",
    "CMakeLists.txt": "329f237404310ce4036aba103bf01a520ff72a396b9a42f070a0037926e1d35e",
}


def gate(condition, label):
    if not condition:
        raise RuntimeError(label)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for buf in iter(lambda: f.read(1024 * 1024), b""):
            h.update(buf)
    return h.hexdigest()


def resolve_source_file(row):
    path = Path(row["file"])
    return (path if path.is_absolute() else Path(row["directory"]) / path).resolve()


def find_compile_spec(root, base):
    candidates = [
        root / "src/PiPNN/build/compile_commands.json",
        root / "src/PiPNN/build-r70/compile_commands.json",
        base / "build-r70/compile_commands.json",
        root / "experiments/H70/build-r70/compile_commands.json",
    ]
    validated = []
    for path in candidates:
        if not path.is_file():
            continue
        try:
            entries = json.loads(path.read_text())
        except Exception:
            continue
        matches = []
        for row in entries:
            argv = row.get("arguments") or shlex.split(row.get("command", ""))
            if not argv:
                continue
            combined = " ".join(argv)
            if (TARGET in combined and
                    "-DUSE_DATATYPE_FLOAT_T" in argv and
                    "-DUSE_DISTANCE_EUCLIDEAN" in argv and
                    str(row.get("file", "")).endswith("algorithms/bench/neighborsTime.C")):
                matches.append((row, argv))
        if len(matches) != 1:
            continue
        row, argv = matches[0]
        if not Path(row["directory"]).is_dir():
            continue
        p = resolve_source_file(row)
        if not p.is_file() or sha(p) != sha(base / "algorithms/bench/neighborsTime.C"):
            continue
        if not (Path(argv[0]).is_file() or shutil.which(argv[0])):
            continue
        foreign = [x for x in argv if re.match(r"-DR(?:78|79|80|81|82|83)_", x)]
        gate(not foreign, "R83_5_FOREIGN_EXPERIMENT_COMPILER_DEFINE")
        validated.append((path, row, argv))
    gate(len(validated) > 0, "R83_5_NO_MATCHING_VALID_COMPILE_DB")
    # Deterministic preferred order; the first path is the one that passed R83.4b.
    print(f"R83_5_VALID_COMPDB_COUNT count={len(validated)} selected={validated[0][0]}", flush=True)
    return validated[0]


def get_compiler_flags(argv):
    compiler = argv[0]
    flags = []
    skip_next = {"-o", "-MF", "-MT", "-MQ", "-include", "-imacros", "-x"}
    drop_exact = {"-c", "-MD", "-MMD", "-MP", "-MG", "-MM", "-M", "-E", "-S", "-fsyntax-only"}
    i = 1
    while i < len(argv):
        arg = argv[i]
        if arg in skip_next:
            gate(i + 1 < len(argv), "R83_5_TRUNCATED_COMPILER_FLAG")
            i += 2
            continue
        if arg in drop_exact or arg.startswith(("-o", "-MF", "-MT", "-MQ")):
            i += 1
            continue
        if arg.startswith("@"):
            raise RuntimeError("R83_5_COMPILER_RESPONSE_FILE_UNSUPPORTED")
        if arg.endswith(("neighborsTime.C", "neighborsTime.cc")):
            i += 1
            continue
        if arg.startswith(("-DR70_TWO_TIER", "-DR71_H17_TOP2", "-DR83_COMPACT_FANOUT")):
            i += 1
            continue
        if arg.startswith(("-fpch-", "-fmodule-")):
            i += 1
            continue
        flags.append(arg)
        i += 1
    gate("-DUSE_DATATYPE_FLOAT_T" in flags and "-DUSE_DISTANCE_EUCLIDEAN" in flags,
         "R83_5_WRONG_DATATYPE_OR_DISTANCE")
    return compiler, flags


def original_link_command(build_dir, compdb):
    """Locate target link.txt without duplicating algorithms/PipNN.

    A CMake compile DB entry's `directory` can be the TARGET build folder
    (.../build/algorithms/PipNN), not the build root (.../build).  The v1
    script appended algorithms/PipNN unconditionally and produced a path
    with that component twice.  Limit discovery to this pinned compile DB's
    build root and compile-entry working directory; do NOT recursively scan.
    """
    build_root = compdb.parent.resolve()
    target_rel = Path("CMakeFiles") / (TARGET + ".dir") / "link.txt"
    candidates = [
        build_root / "algorithms/PipNN" / target_rel,
        build_dir / target_rel,
        build_dir / "algorithms/PipNN" / target_rel,
    ]
    unique = []
    for p in candidates:
        resolved = p.resolve()
        if resolved not in unique:
            unique.append(resolved)
    found = [p for p in unique if p.is_file()]
    if not found:
        print("R83_5_LINK_LOCATOR_PROBED " +
              " | ".join(str(p) for p in unique), flush=True)
    gate(len(found) == 1, "R83_5_LINK_TXT_MISSING" if not found
         else f"R83_5_LINK_TXT_AMBIGUOUS count={len(found)}")
    link = found[0]
    # Only accept a target linker command in the selected compile DB's tree.
    gate(link.is_relative_to(build_root), "R83_5_LINK_OUTSIDE_SELECTED_BUILD_TREE")
    content = link.read_text().strip()
    gate(content and "\n" not in content, "R83_5_MULTILINE_LINK_UNSUPPORTED")
    argv = shlex.split(content)
    gate(len(argv) > 3 and not any(x.startswith("@") for x in argv),
         "R83_5_LINK_RESPONSE_FILE_UNSUPPORTED")
    gate(all(x not in ("&&", "||", ";", "|", "cd") for x in argv),
         "R83_5_COMPLEX_LINK_UNSUPPORTED")
    gate(sum(x.endswith("neighborsTime.C.o") for x in argv) == 1,
         "R83_5_LINK_TARGET_OBJECT_AMBIGUOUS")
    gate("-o" in argv and argv.index("-o") + 1 < len(argv),
         "R83_5_LINK_OUTPUT_MISSING")
    raw_target = Path(argv[argv.index("-o") + 1]).name
    gate(raw_target == TARGET, f"R83_5_LINK_WRONG_TARGET {raw_target}")
    return link, argv


def adapt_link_command(argv, object_path, binary_path):
    new = argv.copy()
    obj_idx = [i for i, x in enumerate(new) if x.endswith("neighborsTime.C.o")]
    gate(len(obj_idx) == 1, f"R83_5_LINK_OBJECT_COUNT_{len(obj_idx)}")
    new[obj_idx[0]] = str(object_path)
    output_indices = [i for i, x in enumerate(new) if x == "-o"]
    gate(len(output_indices) == 1 and output_indices[0] + 1 < len(new),
         "R83_5_LINK_OUTPUT_FLAG_AMBIGUOUS")
    new[output_indices[0] + 1] = str(binary_path)
    gate(not binary_path.exists(), "R83_5_LINK_OUTPUT_ALREADY_EXISTS")
    return new


def verify_pins(root, base, stage, passed):
    head = subprocess.check_output(["git", "-C", str(base), "rev-parse", "HEAD"], text=True).strip()
    gate(head == COMMIT, "R83_5_HEAD_MISMATCH")
    for name, wanted in {
        "graph.h": "17e51779f32db56c9c50b6d514a8ff68539fd19b734804df3abdb63f88dd443e",
        "r70_two_tier_lshgraph.h": "ac0bece4804c7bc552b30db0df57ee92492033065cef62330ddb58a19d470af1",
    }.items():
        gate(sha(base / "algorithms/utils" / name) == wanted,
             f"R83_5_UTILS_SOURCE_SHA_MISMATCH {name}")
    for name, expected in ORIG.items():
        gate(sha(base / "algorithms/PipNN" / name) == expected,
             f"R83_5_ORIGINAL_SHA_MISMATCH {name}")
    for name, expected in STAGED.items():
        gate(sha(stage / "algorithms/PipNN" / name) == expected,
             f"R83_5_STAGED_SHA_MISMATCH {name}")
    gate(passed.is_file(), f"R83_5_R83_4B_SUMMARY_MISSING {passed}")
    report = json.loads(passed.read_text())
    gate(report.get("source_commit") == COMMIT, "R83_5_4B_COMMIT_MISMATCH")
    for arm in ("D0", "E"):
        gate(report.get("compiled", {}).get(arm, {}).get("exit_code") == 0,
             f"R83_5_R83_4B_{arm}_NOT_PASSED")
    print("R83_5_PINNED_SOURCES_AND_R83_4B_SYNTAX_GATES_PASS", flush=True)


def run(root):
    base = root / "experiments/H70/pipnn-clean-443a328"
    stage = root / "experiments/H83/r83_3_source_stage"
    passed_dir = root / "experiments/H83/r83_4b_syntax_gate"
    out = root / "experiments/H83/r83_5_matched_binary"
    gate(not out.exists(), "R83_5_OUTPUT_EXISTS_FAIL_CLOSED")
    verify_pins(root, base, stage, passed_dir / "r83_4_summary.json")
    compdb, entry, compiler_argv = find_compile_spec(root, base)
    compiler, flags = get_compiler_flags(compiler_argv)
    build_dir = Path(entry["directory"]).resolve()
    linker_file, linker_argv = original_link_command(build_dir, compdb)
    gate(Path(linker_argv[0]).name in ("c++", "g++", "clang++") or
         "c++" in Path(linker_argv[0]).name,
         "R83_5_UNEXPECTED_LINKER")
    print(f"R83_5_MATCHED_COMPDB_AND_LINK_SPEC_PASS compile_db={compdb} link={linker_file}", flush=True)
    metadata = {"source_commit": COMMIT, "compiler_db": str(compdb),
                "link_file": str(linker_file), "variants": {}}
    out.mkdir(parents=True, exist_ok=False)
    for arm in ("D0", "E"):
        source = passed_dir / arm
        wrapper = source / "r83_4_real_benchmark_instantiation.cc"
        gate(wrapper.is_file(), f"R83_5_{arm}_WRAPPER_MISSING")
        graph = source / "algorithms/utils/graph.h"
        gate(graph.is_file() and graph.resolve() == (base / "algorithms/utils/graph.h").resolve(),
             f"R83_5_{arm}_GRAPH_HEADER_REALPATH_MISMATCH")
        for name, expected in (STAGED if arm == "E" else ORIG).items():
            if name == "CMakeLists.txt":
                continue
            gate(sha(source / "algorithms/PipNN" / name) == expected,
                 f"R83_5_{arm}_OVERLAY_SHA_MISMATCH {name}")
        dest = out / arm
        dest.mkdir(parents=True, exist_ok=False)
        obj = dest / "neighborsTime.C.o"
        binary = dest / TARGET
        cmd = [compiler, f"-I{source / 'algorithms'}", *flags,
               "-DR70_TWO_TIER=1", "-DR71_H17_TOP2=1"]
        if arm == "E":
            cmd.append("-DR83_COMPACT_FANOUT=1")
        cmd += ["-c", "-x", "c++", str(wrapper), "-o", str(obj)]
        (dest / "compile_command.txt").write_text(shlex.join(cmd) + "\n")
        print(f"R83_5_COMPILE_START variant={arm}", flush=True)
        with (dest / "compile.log").open("w") as f:
            proc = subprocess.run(cmd, cwd=build_dir, stdout=f, stderr=subprocess.STDOUT)
        metadata["variants"][arm] = {"compile_exit": proc.returncode}
        (out / "r83_5_summary.json").write_text(json.dumps(metadata, indent=2) + "\n")
        if proc.returncode != 0:
            errors = [l.strip() for l in (dest / "compile.log").read_text(errors="replace").splitlines()
                      if "error:" in l or "fatal error:" in l]
            print("\n".join(errors[:8]) or (dest / "compile.log").read_text(errors="replace")[-2000:],
                  file=sys.stderr)
            raise RuntimeError(f"R83_5_{arm}_COMPILE_FAIL log={dest/'compile.log'}")
        gate(obj.is_file() and obj.stat().st_size > 0, "R83_5_OBJECT_MISSING")
        metadata["variants"][arm]["object_sha256"] = sha(obj)
        print(f"R83_5_{arm}_OBJECT_COMPILE_PASS sha256={sha(obj)}", flush=True)
        link_cmd = adapt_link_command(linker_argv, obj, binary)
        (dest / "link_command.txt").write_text(shlex.join(link_cmd) + "\n")
        print(f"R83_5_LINK_START variant={arm}", flush=True)
        with (dest / "link.log").open("w") as f:
            proc = subprocess.run(link_cmd, cwd=linker_file.parent.parent.parent,
                                  stdout=f, stderr=subprocess.STDOUT)
        metadata["variants"][arm]["link_exit"] = proc.returncode
        (out / "r83_5_summary.json").write_text(json.dumps(metadata, indent=2) + "\n")
        if proc.returncode != 0:
            print((dest / "link.log").read_text(errors="replace")[-3000:], file=sys.stderr)
            raise RuntimeError(f"R83_5_{arm}_LINK_FAIL log={dest/'link.log'}")
        gate(binary.is_file() and binary.read_bytes()[:4] == b"\x7fELF",
             f"R83_5_{arm}_NOT_ELF_EXECUTABLE")
        metadata["variants"][arm]["binary_sha256"] = sha(binary)
        metadata["variants"][arm]["binary_path"] = str(binary)
        (out / "r83_5_summary.json").write_text(json.dumps(metadata, indent=2) + "\n")
        print(f"R83_5_{arm}_NATIVE_LINK_PASS sha256={sha(binary)}", flush=True)
    print("R83_5_PAIRED_BINARY_BUILD_PASS", flush=True)
    print("R83_5_NO_ANN_GRAPH_BUILD_NO_RECALL_NO_DATA_MODIFICATION_NO_PUSH", flush=True)
    print("R83_5_REPORT", out / "r83_5_summary.json", flush=True)


def selftest():
    a = ["/usr/bin/c++", "CMakeFiles/X.dir/__/bench/neighborsTime.C.o", "-o", "foo", "-labsl", "-lm"]
    b = adapt_link_command(a, Path("/tmp/d0.o"), Path("/tmp/d0.exe"))
    assert b[1] == "/tmp/d0.o" and b[3] == "/tmp/d0.exe" and b[-1] == "-lm"
    flags = get_compiler_flags(["/usr/bin/c++", "-DUSE_DATATYPE_FLOAT_T", "-DUSE_DISTANCE_EUCLIDEAN",
                               "-o", "foo.o", "-c", "-include", "foo.pch", "foo/neighborsTime.C"])
    assert "foo.o" not in flags[1] and "-c" not in flags[1]
    from tempfile import TemporaryDirectory
    with TemporaryDirectory(prefix="r83_5_link_locator_") as tmp:
        build = Path(tmp) / "build"
        target_build = build / "algorithms/PipNN"
        link_file = target_build / "CMakeFiles" / (TARGET + ".dir") / "link.txt"
        link_file.parent.mkdir(parents=True)
        link_file.write_text(
            f"/usr/bin/c++ CMakeFiles/{TARGET}.dir/__/bench/neighborsTime.C.o "
            f"-o {TARGET} -lm\n"
        )
        selected, cmd = original_link_command(target_build, build / "compile_commands.json")
        assert selected == link_file and cmd[-1] == "-lm"
    print("R83_5_LINK_LOCATOR_SELFTEST_PASS")
    print("R83_5_SCRIPT_SELFTEST_PASS")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--root", type=Path)
    p.add_argument("--selftest", action="store_true")
    args = p.parse_args()
    try:
        selftest()
        if not args.selftest:
            gate(args.root is not None, "R83_5_ROOT_REQUIRED")
            run(args.root.expanduser().resolve())
    except Exception as exc:
        print("R83_5_STOP", str(exc), file=sys.stderr, flush=True)
        sys.exit(1)
