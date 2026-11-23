#!/usr/bin/env python3
"""Stage and compare the adaptive fanout experiment on frozen SIFT1M."""
import argparse
import json
from pathlib import Path
import shlex
import subprocess
import sys

import numpy as np

from run import HERE, run_name, save, sha

ARMS = ("fixed", "adaptive", "v2a", "v2b", "v3")
SEEDS = (555, 556, 557)
BEAMS = "40,60,67,70,80,90,93,96,100,110,120,125,131,140,150,152,158,160,180,200,220,232,236,240"
CORE_LIST = "0,2,4,6"
V1 = HERE.parent / "adaptive_fanout_v1"
ROOT = HERE / "runs"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=["v2a", "v2b", "v3", "compare"])
    parser.add_argument("--name", type=run_name, required=True)
    parser.add_argument("--resume", action="store_true", help="Keep completed comparison runs")
    opts = parser.parse_args()
    if opts.resume and opts.stage != "compare":
        parser.error("--resume is only supported for compare")
    name = opts.name

    if opts.stage == "compare":
        staged = {arm: json.loads((ROOT / f"{name}_{arm}_stage" / "threshold.json").read_text())
                  for arm in ARMS[2:]}
        for arm in ARMS[2:]:
            stage_summary = ROOT / f"{name}_{arm}_s555_stage" / "summary.json"
            if json.loads(stage_summary.read_text())["status"] != "PASS":
                raise RuntimeError(f"Stage {arm} is incomplete")
        order = [
            ["fixed", "v2b", "adaptive", "v3", "v2a"],
            ["v2a", "v3", "adaptive", "v2b", "fixed"],
            ["v3", "adaptive", "fixed", "v2a", "v2b"],
        ]
        planned = [(arm, seed, f"{name}_{arm}_s{seed}", BEAMS, False,
                    staged.get(arm, {}).get("margin", 0.0))
                   for seed, arms in zip(SEEDS, order) for arm in arms]
        directory = ROOT / f"{name}_comparison"
    else:
        directory = ROOT / f"{name}_{opts.stage}_stage"

    if opts.resume:
        saved_schedule = json.loads((directory / "schedule.json").read_text())
        if saved_schedule != [list(x) for x in planned]:
            raise ValueError("Resume schedule differs from the saved schedule")
    else:
        directory.mkdir(parents=True)
    protocol = {
        "driver_command": [sys.executable, *sys.argv],
        "driver_sha256": sha(Path(__file__)),
        "runner_sha256": sha(HERE / "run.py"),
        "affinity": CORE_LIST,
        "inputs": str(V1 / "data/sift_n1000000_q10000/manifest.json"),
        "calibration": "base vectors only, seed 555",
        "timing": "sequential processes, fixed CPU affinity, rotating arm order across seeds",
    }

    def run(arm, seed, label, beams, calibrate, margin):
        result = ROOT / label / "summary.json"
        if opts.resume and result.exists():
            saved = json.loads(result.read_text())
            if saved["status"] != "PASS" or saved["seed"] != seed or saved["mode"] != arm:
                raise RuntimeError(f"Unexpected result in {result}")
            print(f"KEEP_RUN={label}", flush=True)
            return saved
        command = ["taskset", "-c", CORE_LIST, sys.executable, "-B", str(HERE / "run.py"),
                   "--rows", "1000000", "--queries", "10000", "--threads", "4",
                   "--mode", arm, "--epsilon", ".15", "--min-depth", "1",
                   "--min-fanout", "1", "--seed", str(seed), "--margin", str(margin),
                   "--beams", beams, "--run-name", label]
        if calibrate:
            command.append("--calibrate")
        with (directory / "commands.sh").open("a") as out:
            out.write(shlex.join(command) + "\n")
        print(shlex.join(command), flush=True)
        subprocess.run(command, check=True)
        summary = json.loads(result.read_text())
        if summary["status"] != "PASS" or not 1 <= summary["reachable_from_start0"] <= 1000000:
            raise RuntimeError(f"Incomplete SIFT1M run {result}")
        return summary

    save(directory / ("resume_protocol.json" if opts.resume else "protocol.json"), protocol)
    if opts.stage in ("v2a", "v2b"):
        historical = V1 / "runs/af_eps015_sift1m_r1/adaptive_summary.json"
        depth = next(r for r in json.loads(historical.read_text())["by_depth"] if r["depth"] == 1)
        fraction = (depth["nominal_assignments"] - depth["actual_assignments"]) / (2 * depth["points"])
        probe = f"{name}_{opts.stage}_probe"
        full = run(opts.stage, 555, probe, "80", True, 0.0)
        if full["telemetry"]["actual_assignments"] != full["telemetry"]["nominal_assignments"]:
            raise RuntimeError("Calibration build must keep full fanout")
        scores = np.loadtxt(ROOT / probe / "margin_samples.txt")
        if scores.size < 1000 or not np.isfinite(scores).all():
            raise RuntimeError("Invalid calibration sample")
        threshold = float(np.quantile(scores, 1 - fraction, method="higher"))
        config = {"margin": threshold, "reference_optional_assignment_drop": fraction,
                  "sample_count": int(scores.size), "sample_drop": float(np.mean(scores > threshold)),
                  "calibration_run": probe, "reference": str(historical)}
    elif opts.stage == "v3":
        path = ROOT / f"{name}_v2b_stage" / "threshold.json"
        config = json.loads(path.read_text())
        config["inherited_threshold"] = str(path)
    else:
        if not opts.resume:
            save(directory / "thresholds.json", staged)
            save(directory / "schedule.json", planned)
        for spec in planned:
            run(*spec)

    if opts.stage != "compare":
        save(directory / "threshold.json", config)
        summary = run(opts.stage, 555, f"{name}_{opts.stage}_s555_stage", BEAMS, False, config["margin"])
        print(f"STAGE_PASS={opts.stage} output={directory} graph={summary['graph']['sha256']}", flush=True)
    else:
        print(f"COMPARISON_RUNS_PASS={directory}", flush=True)


if __name__ == "__main__":
    main()
