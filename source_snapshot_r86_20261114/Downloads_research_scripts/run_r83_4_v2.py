#!/usr/bin/env python3
"""R83.4 v2: resolve a validated existing FLOAT/L2 compiler spec.

READS H70 pinned sources, H83/R83.3 staged sources and existing CMake
compile_commands.json. WRITES ONLY H83/r83_4_syntax_gate; no ANN BUILD.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path

COMMIT = "443a328dc71a3b7be753d52ca2b3c9a4ba77f3fd"
ORIG = {
    "pipnn.h": "f4391ad8712d7757423dca872f9042c3271660dffde384a85b93854b9692f288",
    "pipnn_utils.h": "7083e8183554a1cb586b70cdb4c57920f49ec5a50680096aecf6b873f596595d",
}
STAGED = {
    "pipnn.h": "1788d8541db1727c3aaa39e84c9e915c240847338f69b53d8ff5e0c72e57e1a6",
    "pipnn_utils.h": "17941f13594fdbd2479464ea417878d899e71ce546835ffe0d711bee6713f669",
    "CMakeLists.txt": "329f237404310ce4036aba103bf01a520ff72a396b9a42f070a0037926e1d35e",
}
TARGET = "neighbors-pipnn_FLOAT_T_EUCLIDEAN"


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda: f.read(4 * 1024 * 1024), b""):
            digest.update(b)
    return digest.hexdigest()


def require(condition, marker):
    if not condition:
        raise RuntimeError(marker)


def candidate_commands(compdb: Path):
    rows = json.loads(compdb.read_text(encoding="utf-8"))
    matches = []
    for row in rows:
        argv = row.get("arguments") or shlex.split(row.get("command", ""))
        if not argv:
            continue
        joined = " ".join(argv)
        if (TARGET in joined and
                re.search(r"(?:^|\s)-DUSE_DATATYPE_FLOAT_T(?:\s|$)", joined) and
                re.search(r"(?:^|\s)-DUSE_DISTANCE_EUCLIDEAN(?:\s|$)", joined) and
                str(row.get("file", "")).endswith("algorithms/bench/neighborsTime.C")):
            matches.append((row, argv))
    return matches


def isolated_flags(argv):
    require(len(argv) > 1, "R83_4_EMPTY_COMPILER_FLAGS")
    compiler = argv[0]
    flags = []
    skip_next = {"-o", "-MF", "-MT", "-MQ", "-include", "-imacros"}
    drop_single = {"-c", "-MD", "-MMD", "-MP", "-MG", "-MM", "-M", "-E", "-S"}
    j = 1
    while j < len(argv):
        a = argv[j]
        if a in skip_next:
            require(j + 1 < len(argv), "R83_4_TRUNCATED_COMPILER_ARG")
            j += 2
            continue
        if a in drop_single or a.startswith(("-o", "-MF", "-MT", "-MQ")):
            j += 1
            continue
        if a.startswith("@"):
            raise RuntimeError("R83_4_RESPONSE_FILE_NOT_SUPPORTED")
        if a.endswith(("neighborsTime.C", "neighborsTime.cc")):
            j += 1
            continue
        if (a.startswith("-DR70_TWO_TIER") or a.startswith("-DR71_H17_TOP2") or
                a.startswith("-DR83_COMPACT_FANOUT")):
            j += 1
            continue
        if a.startswith(("-fpch-", "-fmodule-")):
            j += 1
            continue
        flags.append(a)
        j += 1
    # Syntax-only must explicitly typecheck the actual benchmark instantiation.
    return [compiler, *flags, "-DR70_TWO_TIER=1", "-DR71_H17_TOP2=1", "-fsyntax-only", "-x", "c++"]


def prepare_overlay(out: Path, original_base: Path, inputs: Path, stage: bool):
    pip = out / "algorithms" / "PipNN"
    pip.mkdir(parents=True)
    for filename in ("pipnn.h", "pipnn_utils.h"):
        src = ((inputs / "algorithms" / "PipNN" / filename)
               if stage else (original_base / "algorithms" / "PipNN" / filename))
        (pip / filename).write_bytes(src.read_bytes())
    (pip / "neighbors.h").write_bytes((original_base / "algorithms/PipNN/neighbors.h").read_bytes())
    for dirname in ("bench", "utils"):
        src = original_base / "algorithms" / dirname
        require(src.is_dir(), f"R83_4_MISSING_DEPENDENCY {src}")
        (out / "algorithms" / dirname).symlink_to(src, target_is_directory=True)
    wrapper = out / "r83_4_real_benchmark_instantiation.cc"
    benchmark = original_base / "algorithms/bench/neighborsTime.C"
    require(benchmark.is_file(), "R83_4_MISSING_NATIVE_BENCHMARK")
    wrapper.write_text('#include "algorithms/PipNN/neighbors.h"\n'
                       f'#include "{benchmark}"\n', encoding="utf-8")
    return wrapper


def compiler_identity_ok(row, argv, original_base):
    """A matching target is not sufficient if found in a foreign source tree."""
    src = Path(row["file"])
    if not src.is_absolute():
        src = Path(row["directory"]) / src
    src = src.resolve()
    pinned = original_base / "algorithms/bench/neighborsTime.C"
    if not src.is_file() or sha(src) != sha(pinned):
        return False, "BENCH_SOURCE_SHA_MISMATCH"
    if not Path(row["directory"]).is_dir():
        return False, "BUILD_DIRECTORY_MISSING"
    if not (Path(argv[0]).is_file() or shutil_which(argv[0])):
        return False, "COMPILER_MISSING"
    # A foreign experimental CMake flag would compromise matched D/E attribution.
    bad = [v for v in argv if v.startswith("-DR") and
           any(v.startswith(f"-DR{n}_") for n in (78, 79, 80, 81, 82, 83))]
    if bad:
        return False, "FOREIGN_EXPERIMENT_DEFINES=" + ",".join(bad)
    return True, "SOURCE_SHA_AND_TARGET_OK"


def find_compile_specs(root: Path, original_base: Path, explicit: Path | None):
    """Inspect existing DBs only; no CMake generation or worktree writes."""
    paths = []
    def add(p):
        if p.is_file() and p not in paths:
            paths.append(p)

    if explicit is not None:
        require(explicit.is_file(), f"R83_4_EXPLICIT_COMPILE_DB_NOT_FOUND {explicit}")
        add(explicit.resolve())
    else:
        preferred = [
            original_base / "build-r70/compile_commands.json",
            root / "src/PiPNN/build-r70/compile_commands.json",
            root / "src/PiPNN/build/compile_commands.json",
            root / "build-r70/compile_commands.json",
            root / "experiments/H70/build-r70/compile_commands.json",
        ]
        for p in preferred:
            add(p)
        # Restricted recursive search (never scan datasets or large archives).
        search_roots = [original_base, root / "src/PiPNN",
                        root / "experiments/H70"]
        for parent in search_roots:
            if not parent.is_dir():
                continue
            for current, dirs, files in os.walk(parent):
                rel_depth = len(Path(current).relative_to(parent).parts)
                dirs[:] = [d for d in dirs if d not in (
                    ".git", "_deps", "node_modules", "runs", "data", "third_party")]
                if rel_depth >= 6:
                    dirs[:] = []
                if "compile_commands.json" in files:
                    add(Path(current) / "compile_commands.json")
                if len(paths) > 40:
                    break
    print(f"R83_4_COMPDB_DISCOVERY count={len(paths)}", flush=True)
    for path in paths:
        try:
            entries = candidate_commands(path)
        except Exception as exc:
            print(f"R83_4_COMPDB_REJECT path={path} reason=PARSE_{type(exc).__name__}", flush=True)
            continue
        if len(entries) != 1:
            print(f"R83_4_COMPDB_REJECT path={path} reason=TARGET_COUNT_{len(entries)}", flush=True)
            continue
        row, argv = entries[0]
        ok, reason = compiler_identity_ok(row, argv, original_base)
        if not ok:
            print(f"R83_4_COMPDB_REJECT path={path} reason={reason}", flush=True)
            continue
        print(f"R83_4_COMPDB_VERIFIED path={path} source={row['file']}", flush=True)
        return path, row, argv
    if explicit is not None:
        raise RuntimeError("R83_4_EXPLICIT_COMPILER_SPEC_NOT_ACCEPTABLE")
    raise RuntimeError("R83_4_NO_VALID_EXISTING_COMPILER_DB; "
                       "use --compile-db /absolute/path/compile_commands.json "
                       "only after verifying FLOAT/L2 target and pinned benchmark source")


def run(root: Path, compile_db: Path | None = None):
    base = root / "experiments/H70/pipnn-clean-443a328"
    stage = root / "experiments/H83/r83_3_source_stage"
    out = root / "experiments/H83/r83_4_syntax_gate"
    require(not out.exists(), "R83_4_OUTPUT_EXISTS_FAIL_CLOSED")
    head = subprocess.check_output(["git", "-C", str(base), "rev-parse", "HEAD"], text=True).strip()
    require(head == COMMIT, "R83_4_SOURCE_COMMIT_MISMATCH")
    for name, digest in ORIG.items():
        src = base / "algorithms/PipNN" / name
        require(src.is_file() and sha(src) == digest, f"R83_4_ORIGINAL_SOURCE_SHA_FAIL {name}")
    for name, digest in STAGED.items():
        src = stage / "algorithms/PipNN" / name
        require(src.is_file() and sha(src) == digest, f"R83_4_STAGED_SOURCE_SHA_FAIL {name}")
    print("R83_4_PINNED_SOURCE_AND_STAGE_PASS", flush=True)

    compdb, entry, argv = find_compile_specs(root, base, compile_db)
    flags = isolated_flags(argv)
    require(os.path.isfile(flags[0]) or shutil_which(flags[0]), "R83_4_COMPILER_NOT_FOUND")
    # Do not silently omit essential specialization flags from the pinned command.
    require(any(a == "-DUSE_DATATYPE_FLOAT_T" for a in flags), "R83_4_FLOAT_DEFINE_MISSING")
    require(any(a == "-DUSE_DISTANCE_EUCLIDEAN" for a in flags), "R83_4_L2_DEFINE_MISSING")
    print("R83_4_PINNED_FLOAT_L2_COMPILER_SPEC_PASS", flush=True)

    out.mkdir(parents=True, exist_ok=False)
    metadata = {"source_commit": COMMIT, "compiler": flags[0], "compiled": {},
                "output_folder": str(out), "benchmark": str(base / "algorithms/bench/neighborsTime.C")}
    for variant in ("D0", "E"):
        overlay = out / variant
        wrapper = prepare_overlay(overlay, base, stage, stage=(variant == "E"))
        cmd = [*flags]
        if variant == "E":
            cmd.append("-DR83_COMPACT_FANOUT=1")
        cmd.append(str(wrapper))
        (overlay / "command.txt").write_text(shlex.join(cmd) + "\n")
        print(f"R83_4_SYNTAX_START variant={variant}", flush=True)
        with (overlay / "compiler.log").open("w", encoding="utf-8") as log:
            run = subprocess.run(cmd, cwd=entry["directory"], stdout=log, stderr=subprocess.STDOUT,
                                 text=True, check=False)
        metadata["compiled"][variant] = {"exit_code": run.returncode,
                                         "compiler_log": str(overlay / "compiler.log")}
        (out / "r83_4_summary.json").write_text(json.dumps(metadata, indent=2) + "\n")
        if run.returncode != 0:
            snippet = (overlay / "compiler.log").read_text(errors="replace")[-4000:]
            print(snippet, file=sys.stderr)
            raise RuntimeError(f"R83_4_{variant}_SYNTAX_FAIL log={overlay/'compiler.log'}")
        print(f"R83_4_{variant}_FULL_INSTANTIATION_SYNTAX_PASS", flush=True)
    print("R83_4_MATCHED_SOURCE_SYNTAX_PASS", flush=True)
    print("R83_4_NO_BINARY_NO_ANN_BUILD_NO_GRAPH_NO_RECALL_NO_PUSH", flush=True)
    print("R83_4_REPORT", out / "r83_4_summary.json", flush=True)


def shutil_which(command):
    from shutil import which
    return which(command)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True, type=Path)
    ap.add_argument("--compile-db", type=Path, default=None,
                    help="Existing validated CMake compile_commands.json, optional")
    args = ap.parse_args()
    try:
        run(args.root.expanduser().resolve(),
            args.compile_db.expanduser().resolve() if args.compile_db else None)
    except Exception as exc:
        print("R83_4_STOP", str(exc), file=sys.stderr, flush=True)
        sys.exit(1)
