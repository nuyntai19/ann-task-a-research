#!/usr/bin/env python3
"""R83.2 reproducible SYNTHETIC Parlay group-by dataflow pilot; no ANN build.

- Pins H70 PiPNN HEAD and Parlay submodule HEAD.
- Compiles a separate benchmark, runs in new H83 location.
- Compares full member-order fingerprints between flat and compact.
- Records process-level VmHWM via GNU time, without modifying H70.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import statistics
import subprocess
import sys
import time

PIPNN_COMMIT = "443a328dc71a3b7be753d52ca2b3c9a4ba77f3fd"
PARLAY_COMMIT = "7cdb4cae8f020525f5eb4ad82e2565d1e38cfbc3"
RE = re.compile(
    r"R83_2_ARM=(\w+) pattern=(\w+) points=(\d+) fanout=(\d+) leaders=(\d+) "
    r"slots=(\d+) populate_s=(\S+) grouping_s=(\S+) subtotal_s=(\S+) "
    r"checksum=(\d+) memberships=(\d+)"
)


def call(cmd, **kwargs):
    return subprocess.run(cmd, check=True, text=True, capture_output=True, **kwargs)


def preflight(root):
    base = root / "experiments/H70/pipnn-clean-443a328"
    parlay = root / "src/PiPNN/parlaylib"
    if call(["git", "-C", str(base), "rev-parse", "HEAD"]).stdout.strip() != PIPNN_COMMIT:
        raise RuntimeError("R83_2_PIPNN_HEAD_MISMATCH")
    if call(["git", "-C", str(parlay), "rev-parse", "HEAD"]).stdout.strip() != PARLAY_COMMIT:
        raise RuntimeError("R83_2_PARLAY_HEAD_MISMATCH")
    if not (parlay / "include/parlay/primitives.h").is_file():
        raise RuntimeError("R83_2_PARLAY_INCLUDE_MISSING")
    print("R83_2_PINNED_SOURCE_GATES_PASS", flush=True)
    return parlay / "include"


def measured(binary, mode, points, fanout, leaders, pattern, folder, label):
    times = folder / (label + ".time")
    stdout = folder / (label + ".stdout")
    stderr = folder / (label + ".stderr")
    cmd = ["/usr/bin/time", "-f", "RSS_KiB=%M WALL_s=%e", "-o", str(times),
           str(binary), mode, str(points), str(fanout), str(leaders), pattern]
    env = os.environ.copy()
    env.update(PARLAY_NUM_THREADS="4", OMP_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1")
    run = subprocess.run(cmd, env=env, text=True, capture_output=True)
    stdout.write_text(run.stdout)
    stderr.write_text(run.stderr)
    if run.returncode:
        raise RuntimeError(f"R83_2_BINARY_FAILED {label} exit={run.returncode}: {run.stderr[-2000:]}")
    match = RE.search(run.stdout)
    if not match:
        raise RuntimeError(f"R83_2_UNPARSABLE {label}: {run.stdout}")
    groups = match.groups()
    m = dict(zip(["arm", "pattern", "points", "fanout", "leaders", "slots",
                 "populate_s", "grouping_s", "subtotal_s", "checksum", "memberships"], groups))
    content = times.read_text()
    rss = re.search(r"RSS_KiB=(\d+)", content)
    wall = re.search(r"WALL_s=([0-9.]+)", content)
    if not rss or not wall:
        raise RuntimeError(f"R83_2_GNU_TIME_FAIL {label}: {content}")
    return dict(arm=mode, label=label, checksum=m["checksum"], members=int(m["memberships"]),
                populate_s=float(m["populate_s"]), grouping_s=float(m["grouping_s"]),
                subtotal_s=float(m["subtotal_s"]), peakRSS_KiB=int(rss.group(1)),
                process_wall_s=float(wall.group(1)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    ap.add_argument("--phase", choices=("selftest", "pilot"), required=True)
    args = ap.parse_args()
    root = Path(args.root).resolve()
    parlay_inc = preflight(root)
    source = Path(__file__).with_name("r83_compact_fanout.cc").resolve()
    kit = Path(__file__).resolve().parent
    target = kit / "r83_compact_fanout"
    if target.exists():
        raise RuntimeError("R83_2_BINARY_ALREADY_EXISTS_FAIL_CLOSED")
    compiler = ["g++", "-std=c++17", "-O3", "-pthread", "-I", str(parlay_inc),
                str(source), "-o", str(target)]
    print("R83_2_COMPILING_PINNED_PARLAY", flush=True)
    c = subprocess.run(compiler, text=True, capture_output=True)
    if c.returncode:
        raise RuntimeError("R83_2_COMPILE_FAILED " + c.stderr[-7000:])
    print("R83_2_COMPILE_PASS", flush=True)
    if c.stderr:
        print("R83_2_COMPILE_WARNINGS", c.stderr[-1500:])
    manifest = dict(phase=args.phase, source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                    parlay_head=PARLAY_COMMIT, pipnn_head=PIPNN_COMMIT,
                    native_cpp_flags=compiler)
    patterns = ("clustered", "uniform")
    for pattern in patterns:
        run_rows = []
        params = (4096, 3, 32) if args.phase == "selftest" else (1_000_000, 10, 100)
        reps = 1 if args.phase == "selftest" else 3
        # Each independent process writes unique logs; no graph/index modifications.
        for i in range(reps):
            order = ["flat", "compact"] if i % 2 == 0 else ["compact", "flat"]
            by_arm = {}
            for mode in order:
                label = f"{pattern}_r{i+1}_{mode}"
                r = measured(target, mode, *params, pattern, kit, label)
                run_rows.append(r)
                by_arm[mode] = r
                print("R83_2_RESULT", json.dumps(r, sort_keys=True), flush=True)
            if (by_arm["flat"]["checksum"] != by_arm["compact"]["checksum"]
                    or by_arm["flat"]["members"] != by_arm["compact"]["members"]):
                raise RuntimeError(f"R83_2_ORDERED_BUCKET_PARITY_FAIL pattern={pattern} rep={i+1}")
        print(f"R83_2_ORDERED_BUCKET_PARITY_PASS pattern={pattern} reps={reps}", flush=True)
        if args.phase == "pilot":
            summary = {}
            for mode in ("flat", "compact"):
                arm_rows = [r for r in run_rows if r["arm"] == mode]
                summary[mode] = {k: statistics.median(r[k] for r in arm_rows)
                                 for k in ("subtotal_s", "grouping_s", "peakRSS_KiB", "process_wall_s")}
            print("R83_2_MEDIANS", pattern, json.dumps(summary, sort_keys=True), flush=True)
        manifest[pattern] = run_rows
    (kit / "r83_2_report.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print("R83_2_REPORT", kit / "r83_2_report.json", flush=True)
    print("R83_2_" + args.phase.upper() + "_PASS", flush=True)
    print("R83_2_NOT_PIPNN_BUILD_NOT_REAL_LEADER_ASSIGNMENT_NOT_RECALL", flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("R83_2_BLOCKED_OR_FAIL", str(exc), file=sys.stderr)
        sys.exit(1)
