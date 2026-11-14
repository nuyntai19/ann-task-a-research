#!/usr/bin/env python3
"""H24-R0c: inspect, plan, or explicitly run a PAIR of fgraft Dense baselines.

No STH implementation. Does NOT download or modify sources/data. Default is PLAN.
BUILD seconds are parsed from source-reported Dense phases, not CLI wall time,
which includes ANN evaluation. Read README/report before executing expensive runs.
"""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from datetime import datetime, timezone
from statistics import median

DENSE_RE = re.compile(
    r"dense:\s+L=(\d+)\s+m=(\d+)\s+C=(\d+)\s+over n=(\d+).*?"
    r"leaders\s+([\d.]+)s\s+candidates\s+([\d.]+)s\s+prune\s+([\d.]+)s"
)
GRAPH_RE = re.compile(
    r"candidates:\s+(\d+) directed.*?edges:\s+(\d+) directed.*?"
    r"memory\s+([\d.]+)MB"
)
LADDER_RE = re.compile(r"^\s*(\d+)\s+(0?\.\d+)\s+([\d.]+)\s+([\d.]+)\s*$")
THRESHOLD = 1.0 / 1.15


def parse_log(content: str):
    d = DENSE_RE.search(content)
    if not d:
        raise ValueError("Missing Dense BUILD line; cannot extract stage timings")
    L, m, C, n = [int(t) for t in d.groups()[:4]]
    leader, candidate, ending = [float(t) for t in d.groups()[4:]]
    gr = GRAPH_RE.search(content)
    rows = []
    inside = False
    started = False
    for line in content.splitlines():
        if re.match(r"^\s*entry=", line):
            if inside and started:
                break
            inside = line.strip() == "entry=hub"
            continue
        if not inside:
            continue
        if "recall@10" in line and "QPS" in line:
            started = True
            continue
        if started:
            mm = LADDER_RE.match(line)
            if mm:
                ef, recall, dist_per_query, qps = mm.groups()
                rows.append(dict(ef=int(ef), recall10=float(recall),
                                 dist_per_query=float(dist_per_query), qps=float(qps)))
            elif rows and not line.strip():
                break
    return dict(L=L, m=m, C=C, n=n, leader_s=leader, candidate_s=candidate,
                ending_spine_s=ending, build_s=round(leader + candidate + ending, 4),
                graph=(dict(candidate_edges=int(gr.group(1)), directed_edges=int(gr.group(2)),
                            csr_memory_MB=float(gr.group(3))) if gr else None),
                query_hub=rows,
                limitations=["Stage timings have 0.01s display rounding",
                             "CLI wall time includes query evaluation; do not use it as BUILD",
                             "CSR memory in log excludes vectors, other index state, peak BUILD RSS"])


def source_revision(binary: Path):
    try:
        r = subprocess.run(["git", "-C", str(binary.parent.parent), "rev-parse", "HEAD"],
                           capture_output=True, text=True, timeout=5)
        return r.stdout.strip() if r.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired):
        return None


def check_inputs(opts):
    for label in ("binary", "data", "queries", "gold"):
        p = getattr(opts, label)
        if not p:
            raise SystemExit(f"ERROR: --{label} is required in {opts.mode} mode")
        if not Path(p).is_file():
            raise SystemExit(f"ERROR: missing {label} file: {p}")
    try:
        import numpy as np
    except ImportError as exc:
        raise SystemExit("ERROR: numpy required for cheap NPY header checks") from exc
    X = np.load(opts.data, mmap_mode="r", allow_pickle=False)
    Q = np.load(opts.queries, mmap_mode="r", allow_pickle=False)
    gold = np.load(opts.gold, mmap_mode="r", allow_pickle=False)
    if X.ndim != 2 or Q.ndim != 2 or gold.ndim != 2:
        raise SystemExit("ERROR: X, Q, gold must be 2D NPY arrays")
    if X.shape[1] != Q.shape[1] or gold.shape[0] != Q.shape[0] or gold.shape[1] < 10:
        raise SystemExit(f"ERROR: incompatible shapes X={X.shape}, Q={Q.shape}, gold={gold.shape}")
    if X.dtype != np.float32 or Q.dtype != np.float32 or gold.dtype.kind not in "iu":
        raise SystemExit(f"ERROR: expected float32 X,Q and integer gold; got {X.dtype}, {Q.dtype}, {gold.dtype}")
    if int(X.shape[0]) < 1000 or int(Q.shape[0]) < 100:
        raise SystemExit("ERROR: need a representative base set and >=100 fixed queries")
    if gold.min() < 0 or gold.max() >= X.shape[0]:
        raise SystemExit("ERROR: gold has IDs outside X base set; do not crop a dataset without regenerating GT")
    return dict(n=int(X.shape[0]), dim=int(X.shape[1]), nq=int(Q.shape[0]),
                gold_k=int(gold.shape[1]),
                files={z: dict(path=str(Path(getattr(opts,z)).resolve()),
                               bytes=Path(getattr(opts,z)).stat().st_size)
                       for z in ("data","queries","gold")})


def command(opts, m, seed):
    cmd = [str(Path(opts.binary).expanduser().resolve()),
           "--data", str(Path(opts.data).expanduser().resolve()),
           "--queries", str(Path(opts.queries).expanduser().resolve()),
           "--gold", str(Path(opts.gold).expanduser().resolve()),
           "--metric", opts.metric,
           "--dense", str(opts.L), "--dense-m", str(m), "--dense-C", str(opts.C),
           "--dense-prune", "1", "--dense-spine", str(opts.spine),
           "--dense-kmeans", str(opts.kmeans),
           "--harvest-cap", str(opts.R), "--harvest-alpha", str(opts.alpha),
           "--threads", str(opts.threads), "--search-threads", "1",
           "--seed", str(seed), "--k", "10", "--entry", "hub",
           "--ef", *[str(e) for e in opts.ef]]
    if opts.spine == 3:
        cmd += ["--dense-spine-s", str(opts.spine_s),
                "--dense-spine-cap", str(opts.spine_cap),
                "--dense-spine-repair", str(opts.spine_repair)]
    return cmd


def record_path(out, label, m, seed):
    return out / f"dense_{label}_m{m}_seed{seed}.log"


def inspect(out, opts):
    reports = []
    for seed in opts.seeds:
        entry = {"seed": seed, "arms": {}}
        for label, m in (("low", opts.m_low), ("high", opts.m_high)):
            path = record_path(out, label, m, seed)
            if path.exists():
                entry["arms"][label] = parse_log(path.read_text(errors="replace"))
                entry["arms"][label]["log"] = str(path)
            else:
                entry["arms"][label] = {"error": "MISSING_LOG", "log": str(path)}
        lo, hi = entry["arms"]["low"], entry["arms"]["high"]
        if "build_s" in lo and "build_s" in hi:
            ratio = lo["build_s"] / hi["build_s"]
            allowance = hi["build_s"] / 1.15 - lo["build_s"]
            lo_map = {x["ef"]: x for x in lo["query_hub"]}
            hi_map = {x["ef"]: x for x in hi["query_hub"]}
            quality_rows = []
            for ef in sorted(set(lo_map) & set(hi_map)):
                quality_rows.append({"ef": ef,
                                     "low_recall10": lo_map[ef]["recall10"],
                                     "high_recall10": hi_map[ef]["recall10"],
                                     "delta_recall10": round(hi_map[ef]["recall10"] - lo_map[ef]["recall10"], 6),
                                     "low_qps": lo_map[ef]["qps"], "high_qps": hi_map[ef]["qps"]})
            status = "NEGATIVE_ALLOWANCE_FOR_THIS_PAIR" if allowance <= 0 else "POSITIVE_TIME_ALLOWANCE_ONLY"
            if not quality_rows:
                status = "INCOMPLETE_QUERY_LADDER" if allowance > 0 else "NEGATIVE_ALLOWANCE_FOR_THIS_PAIR"
            elif allowance > 0 and max(x["delta_recall10"] for x in quality_rows) <= 0:
                status = "HIGH_HAS_NO_RECALL_ADVANTAGE_AT_TESTED_EF"
            entry["gate"] = dict(status=status, low_div_high=round(ratio, 5),
                                 additional_seconds_max=round(allowance, 4),
                                 stage_only_no_actual_rescue=True, recall_at_same_ef=quality_rows)
        reports.append(entry)
    valid = [v for v in reports if "gate" in v]
    overview = {"status": "INPUT_MISSING" if not valid else "MEASURED_DENSE_PAIR_ONLY",
                "runs_found": len(valid), "runs_expected": len(opts.seeds),
                "speedup_goal": 1.15, "gate_tlow_over_thigh": round(THRESHOLD, 6),
                "runs": reports,
                "decision_note": "A single seed is preliminary; three paired seeds and stable quality evidence required for robust decision."}
    if valid:
        overview["median_tlow_over_thigh"] = round(median(v["gate"]["low_div_high"] for v in valid), 5)
        overview["median_allowance_seconds"] = round(median(v["gate"]["additional_seconds_max"] for v in valid), 4)
    return overview


def selftest():
    demo = """dense: L=240 m=3 C=200 over n=200000  leaves mean 2500 max 2777  leaders 2.30s candidates 12.10s prune 3.50s (4 threads), 120.0M dist (leaders 2.0M, candidates 100.0M, prune 10.0M, spine 8.0M in 0.50s)
  candidates: 2400000 directed (12.0/vertex); edges: 3300000 directed (16.5/vertex, max 128); memory 15MB
  entry=hub
     ef  recall@10  dist/query   QPS(1thr)
     60     0.9700         1400        1400
    100     0.9880         2000        1000
"""
    p = parse_log(demo)
    assert p["build_s"] == 17.9 and p["graph"]["directed_edges"] == 3300000
    assert p["query_hub"][1]["ef"] == 100 and p["query_hub"][1]["recall10"] == 0.988
    # Important: no quality outcome may override a negative time allowance.
    test_dir = Path(__file__).parent / "_h24_selftest_temp"
    try:
        test_dir.mkdir(exist_ok=True)
        for label, m in (("low",3),("high",5)):
            path = test_dir / f"dense_{label}_m{m}_seed42.log"
            text = demo.replace("m=3", f"m={m}")
            text = text.replace("leaders 2.30s candidates 12.10s prune 3.50s",
                                "leaders 2.30s candidates 12.10s prune 3.50s" if label=="low"
                                else "leaders 2.30s candidates 12.20s prune 3.50s")
            path.write_text(text)
        from types import SimpleNamespace
        o = SimpleNamespace(seeds=[42],m_low=3,m_high=5)
        rep = inspect(test_dir,o)
        assert rep["runs"][0]["gate"]["status"] == "NEGATIVE_ALLOWANCE_FOR_THIS_PAIR"
    finally:
        if test_dir.exists():
            for f in test_dir.iterdir(): f.unlink()
            test_dir.rmdir()
    print("SELFTEST PASS: parses BUILD phases, graph, native Recall-QPS ladder")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--mode", choices=["plan", "run", "inspect", "selftest"], default="plan")
    ap.add_argument("--binary")
    ap.add_argument("--data")
    ap.add_argument("--queries")
    ap.add_argument("--gold")
    ap.add_argument("--metric", choices=["l2", "cos"], default="l2")
    ap.add_argument("--out", default="./h24_dense_pair_outputs")
    ap.add_argument("--L", type=int, default=240)
    ap.add_argument("--m-low", type=int, default=3)
    ap.add_argument("--m-high", type=int, default=5)
    ap.add_argument("--C", type=int, default=200)
    ap.add_argument("--R", type=int, default=64)
    ap.add_argument("--alpha", type=float, default=1.0)
    ap.add_argument("--kmeans", type=int, default=10)
    ap.add_argument("--spine", type=int, choices=[1, 3], default=3)
    ap.add_argument("--spine-s", type=int, default=0)
    ap.add_argument("--spine-cap", type=int, default=16)
    ap.add_argument("--spine-repair", type=int, choices=[0, 1], default=1)
    ap.add_argument("--threads", type=int, default=4)
    ap.add_argument("--ef", type=int, nargs="+", default=[60, 100, 140, 200, 300, 400, 600])
    ap.add_argument("--seeds", type=int, nargs="+", default=[42])
    args = ap.parse_args()
    if args.mode == "selftest":
        selftest(); return
    if args.m_low < 1 or args.m_high <= args.m_low or args.m_high > args.L or args.C <= 0 or args.threads < 1:
        ap.error("Need 1 <= m_low < m_high <= L; C>0; threads>=1")
    out = Path(args.out).expanduser().resolve()
    if args.mode == "inspect":
        print(json.dumps(inspect(out, args), ensure_ascii=False, indent=2)); return
    info = check_inputs(args)
    if args.mode == "plan":
        print("PLAN ONLY; nothing executed. Dataset:")
        print(json.dumps(info, indent=2))
        for seed in args.seeds:
            for label,m in (("low",args.m_low),("high",args.m_high)):
                print(f"\n{label} seed {seed}:", " ".join(command(args,m,seed)))
        print("\nUse --mode run to explicitly execute BUILDs; use --mode inspect to parse old logs.")
        return
    for seed in args.seeds:
        for label,m in (("low", args.m_low), ("high", args.m_high)):
            path = record_path(out, label, m, seed)
            if path.exists():
                raise SystemExit(f"REFUSE TO OVERWRITE: {path}; inspect or change --out")
    out.mkdir(parents=True, exist_ok=True)
    meta = dict(created=datetime.now(timezone.utc).isoformat(),
                source_revision=source_revision(Path(args.binary).resolve()),
                dataset=info, parameters=vars(args),
                build_accounting="Dense log stages only: leaders+candidates+prune(includes spine)")
    (out / "run_manifest.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2))
    env = os.environ.copy()
    env.update(OMP_NUM_THREADS=str(args.threads), OPENBLAS_NUM_THREADS=str(args.threads),
               MKL_NUM_THREADS=str(args.threads), OMP_DYNAMIC="FALSE")
    for seed in args.seeds:
        arms = [("low", args.m_low), ("high", args.m_high)]
        if seed % 2:
            arms.reverse()
        for label,m in arms:
            log = record_path(out,label,m,seed)
            if log.exists():
                raise SystemExit(f"REFUSE TO OVERWRITE: {log}; inspect it or change --out")
            cmd = command(args,m,seed)
            print("RUN", label, "seed", seed, "→", log, flush=True)
            with log.open("w") as f:
                f.write("# COMMAND: " + " ".join(cmd) + "\n"); f.flush()
                proc = subprocess.run(cmd, cwd=str(Path(args.binary).resolve().parent.parent),
                                      stdout=f, stderr=subprocess.STDOUT, env=env)
            if proc.returncode != 0:
                raise SystemExit(f"ERROR: {label} seed {seed} exited {proc.returncode}; see {log}")
    report = inspect(out,args)
    (out / "gate_results.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
