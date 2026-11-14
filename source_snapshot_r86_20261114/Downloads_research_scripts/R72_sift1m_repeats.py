#!/usr/bin/env python3
"""R72.3: run two additional, counterbalanced 4-thread SIFT1M BUILD rounds.

Read-only for the existing pilot and all source/binaries. Every new graph/log is
written under a newly created unique directory. This is BUILD-only: SEARCH
quality must be evaluated separately on the newly generated graphs.
"""
from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
import tempfile
from statistics import median

ARMS = ("A_stock", "B_h17", "C_tier", "D_h17_tier")
SCHEDULE = (
    (2, ("D_h17_tier", "C_tier", "B_h17", "A_stock")),
    (3, ("B_h17", "D_h17_tier", "A_stock", "C_tier")),
)
LABELS = {
    "A_stock": ("STOCK_FLAT_C160", "STOCK_HIGHWAY"),
    "B_h17": ("STOCK_FLAT_C160", "H17_PACKED_TOP2"),
    "C_tier": ("TIER_B64_C160", "STOCK_HIGHWAY"),
    "D_h17_tier": ("TIER_B64_C160", "H17_PACKED_TOP2"),
}
PARAMS = (
    "-num_clusters", "2", "-cluster_size", "1024",
    "-top_level_leaders", "100", "-fanout_scheme", "10,3,1",
    "-mst_deg", "2", "-prune_degree", "64", "-table_size", "160",
    "-hash_bits", "12", "-alpha", "1.1",
)


def must(condition: bool, description: str) -> None:
    if not condition:
        raise ValueError(description)


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(4 * 1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def manifest_verify(pilot: Path, base: Path, bins: dict[str, Path]) -> None:
    manifest = pilot / "inputs.sha256"
    must(manifest.is_file(), "pilot input manifest missing")
    parsed: dict[Path, str] = {}
    for ln in manifest.read_text().splitlines():
        m = re.fullmatch(r"([0-9a-f]{64})\s+\*?(.+)", ln)
        must(m is not None, "malformed SHA256 manifest")
        sig, file_name = m.groups()
        p = Path(file_name).resolve()
        must(p.is_file(), f"missing manifest input {p}")
        must(sha(p) == sig, f"changed input SHA256 for {p}")
        must(p not in parsed, f"duplicate manifest entry {p}")
        parsed[p] = sig
    must(set(parsed) == {base.resolve(), *(p.resolve() for p in bins.values())},
         "pilot manifest does not pin the requested base and four binaries")
    print("R72_REPEAT_INPUT_SHA256_PASS entries=5", flush=True)


def graph_quick(path: Path) -> tuple[int, str]:
    must(path.is_file(), f"graph missing: {path}")
    size = path.stat().st_size
    must(size >= 4_000_008 and size % 4 == 0, f"bad graph length: {path}")
    with path.open("rb") as f:
        pre = f.read(8)
    must(len(pre) == 8 and struct.unpack("<II", pre) == (1_000_000, 64),
         f"wrong n/maxdeg graph header: {path}")
    return size, sha(path)


def parse_time(path: Path) -> tuple[float, int]:
    must(path.is_file(), f"time log missing: {path}")
    pairs = dict(v.split("=", 1) for v in path.read_text().split() if "=" in v)
    must(pairs.get("EXIT") == "0", f"nonzero exit in {path}")
    wall = float(pairs["WALL_SEC"])
    rss = int(pairs["MAX_RSS_KiB"])
    must(math.isfinite(wall) and 0 < wall < 1800 and rss > 0,
         f"invalid time/RSS in {path}")
    return wall, rss


def verify_log(path: Path, arm: str) -> None:
    must(path.is_file(), f"log missing: {path}")
    data = path.read_text(errors="replace")
    reserv, selection = LABELS[arm]
    must(f"R70_RESERVOIR_VARIANT={reserv}" in data and
         f"R71_SELECTION_VARIANT={selection}" in data,
         f"wrong variant labels in {path}")


def check_pilot(pilot: Path) -> dict[str, object]:
    records = {}
    for arm in ARMS:
        graph = pilot / f"{arm}.graph"
        nbytes, digest = graph_quick(graph)
        wall, rss = parse_time(pilot / f"{arm}.time")
        verify_log(pilot / f"{arm}.log", arm)
        records[arm] = {"wall": wall, "rss": rss, "graph_bytes": nbytes,
                        "graph_sha256": digest}
    print("R72_REPEAT_PILOT_FOUR_ARMS_PASS", flush=True)
    return records


def resources_ok(folder: Path) -> None:
    free = shutil.disk_usage(folder).free
    text = Path("/proc/meminfo").read_text()
    avail_kib = next(int(x.split()[1]) for x in text.splitlines()
                     if x.startswith("MemAvailable:"))
    gib = 1024**3
    print(f"R72_REPEAT_RESOURCES disk_free_GiB={free/gib:.2f} "
          f"mem_available_GiB={avail_kib*1024/gib:.2f}", flush=True)
    must(free >= 2*gib, "at least 2 GiB free disk required for eight graphs")
    must(avail_kib*1024 >= 4*gib,
         "at least 4 GiB currently available RAM required as conservative safety gate")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", type=Path, required=True, help="~/ann-task-a")
    p.add_argument("--pilot", type=Path, required=True, help="existing SIFT1M pilot directory")
    p.add_argument("--plan-only", action="store_true")
    args = p.parse_args()
    root = args.root.expanduser().resolve()
    pilot = args.pilot.expanduser().resolve()
    h70 = root / "experiments/H70"
    base = root / "data/sift1m.fbin"
    bins = {arm: h70 / "r71-bin" / arm for arm in ARMS}
    must(root.is_dir() and h70.is_dir(), "project/H70 directory missing")
    must(pilot.is_dir() and pilot.parent == h70 and
         pilot.name.startswith("r72-sift1m-pilot-4t-"), "wrong pilot path")
    must(base.is_file() and base.stat().st_size == 512000008,
         "SIFT1M file missing or size changed")
    with base.open("rb") as f:
        must(struct.unpack("<II", f.read(8)) == (1_000_000, 128),
             "wrong SIFT1M header")
    manifest_verify(pilot, base, bins)
    prior = check_pilot(pilot)
    for round_no, order in SCHEDULE:
        print("R72_REPEAT_SCHEDULE", round_no, " ".join(order), flush=True)
    resources_ok(h70)
    must(shutil.which("timeout") is not None and Path("/usr/bin/time").is_file(),
         "requires GNU timeout and /usr/bin/time")
    if args.plan_only:
        print("R72_REPEAT_PLAN_ONLY_PASS no_new_builds=TRUE", flush=True)
        return

    folder = Path(tempfile.mkdtemp(prefix="r72-sift1m-repeats-4t-", dir=h70))
    print(f"R72_REPEAT_RUN_DIR={folder}", flush=True)
    (folder / "inputs.sha256").write_text((pilot / "inputs.sha256").read_text())
    (folder / "pilot_provenance.json").write_text(json.dumps({
        "pilot_dir": str(pilot), "pilot_runs": prior,
        "created_at": datetime.now().astimezone().isoformat(),
        "params": list(PARAMS), "build_threads": 4,
        "schedule": [{"round": r, "order": list(v)} for r, v in SCHEDULE],
        "note": "Existing pilot files are never modified; repeat graphs require separate SEARCH validation."
    }, indent=2) + "\n")
    print("R72_REPEAT_NO_EXISTING_DATA_MODIFIED", flush=True)

    records: dict[str, list[dict[str, object]]] = {
        arm: [{"round": 1, **prior[arm]}] for arm in ARMS
    }
    for round_no, order in SCHEDULE:
        for arm in order:
            tag = f"r{round_no}_{arm}"
            binary = bins[arm]
            graph = folder / f"{tag}.graph"
            logfile = folder / f"{tag}.log"
            timelog = folder / f"{tag}.time"
            print(f"R72_REPEAT_START {tag}", flush=True)
            cmd = ["/usr/bin/time", "-f", "WALL_SEC=%e MAX_RSS_KiB=%M EXIT=%x",
                   "-o", str(timelog), "timeout", "--kill-after=5s", "1800s",
                   str(binary), "-base_path", str(base),
                   "-graph_outfile", str(graph), *PARAMS]
            env = dict(os.environ)
            env["PARLAY_NUM_THREADS"] = "4"
            with logfile.open("x") as out:
                result = subprocess.run(cmd, stdout=out, stderr=subprocess.STDOUT, env=env,
                                        check=False)
            must(result.returncode == 0, f"BUILD failed for {tag} rc={result.returncode}: {logfile}")
            verify_log(logfile, arm)
            wall, rss = parse_time(timelog)
            nbytes, digest = graph_quick(graph)
            records[arm].append({"round": round_no, "wall": wall,
                                 "rss": rss, "graph_bytes": nbytes,
                                 "graph_sha256": digest})
            print(f"R72_REPEAT_BUILD_PASS {tag} wall_sec={wall:.2f} "
                  f"rss_KiB={rss} graph_bytes={nbytes} sha256={digest}", flush=True)

    summary = {}
    for arm in ARMS:
        rr = sorted(records[arm], key=lambda e: e["round"])
        walls = [float(x["wall"]) for x in rr]
        rss = [int(x["rss"]) for x in rr]
        summary[arm] = {"runs": rr, "wall_median": median(walls),
                        "rss_median": median(rss)}
    baseline = summary["A_stock"]
    for arm in ARMS:
        s = summary[arm]
        wall_delta = (s["wall_median"] / baseline["wall_median"] - 1) * 100
        rss_delta = (s["rss_median"] / baseline["rss_median"] - 1) * 100
        s["wall_delta_pct"] = wall_delta
        s["rss_delta_pct"] = rss_delta
        print(f'R72_REPEAT_ARM {arm} wall_median={s["wall_median"]:.2f}s '
              f'wall_runs={[x["wall"] for x in s["runs"]]} '
              f'rss_median={s["rss_median"]}KiB '
              f'rss_runs={[x["rss"] for x in s["runs"]]} '
              f'wall_delta_pct={wall_delta:+.2f} rss_delta_pct={rss_delta:+.2f}',
              flush=True)
    output = folder / "r72_repeats_summary.json"
    output.write_text(json.dumps({"kind": "R72_SIFT1M_BUILD_3_PER_ARM",
                                  "pilot": str(pilot), "repeats": str(folder),
                                  "source_manifest": str(folder / "inputs.sha256"),
                                  "summary": summary,
                                  "limitations": ["Three BUILD runs per arm; no formal significance test.",
                                                  "Repeat graph validity and Recall@10 have not yet been checked.",
                                                  "One SIFT1M dataset and one 4-thread configuration."]},
                                 indent=2) + "\n")
    print(f"R72_REPEAT_12_BUILDS_TOTAL_PASS output={output}", flush=True)
    print(f"R72_REPEAT_RUN_DIR={folder}", flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"R72_REPEAT_FAIL {type(e).__name__}: {e}", file=sys.stderr, flush=True)
        sys.exit(1)
