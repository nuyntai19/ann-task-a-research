#!/usr/bin/env python3
"""Isolated adaptive-fanout PiPNN build/search experiment; old runner is untouched."""
import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import tempfile

for key in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ[key] = "1"
import numpy as np
from ground_truth import load_gt_ids, reuse_gt

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent


def run_name(value):
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", value):
        raise argparse.ArgumentTypeError("Run name must be one ASCII filename component, 1-128 characters")
    return value


def beam_list(value):
    parts = [p.strip() for p in value.split(',')]
    if any(not re.fullmatch(r'[0-9]+', p) for p in parts):
        raise argparse.ArgumentTypeError('Use comma-separated beam integers')
    beams = list(map(int, parts))
    if not beams or min(beams)<10 or max(beams)>2147483647 or len(set(beams))!=len(beams):
        raise argparse.ArgumentTypeError('Beams must be distinct integers >=10 fitting a signed int')
    return beams


def validate_args(args, p):
    if (not math.isfinite(args.epsilon) or not 0<=args.epsilon<=10 or args.min_depth<0
            or not 1<=args.min_fanout<=512 or args.threads<1 or args.timeout<1
            or not 0<=args.seed<=2**32-1 or args.rows<256 or args.queries<1):
        p.error('Invalid experiment parameters')
    if hasattr(args,'repeats'):
        if (args.repeats<2 or args.seed+args.repeats-1>2**32-1
                or not 1<=args.calibration_queries<args.queries
                or not math.isfinite(args.recall_tolerance) or not 0<=args.recall_tolerance<1):
            p.error('Need valid build repeats, calibration/holdout split and Recall tolerance')
        if len(args.run_name)>80:
            p.error('Campaign name must be <=80 characters to leave room for arm/seed suffixes')
        if not any(80<=b<=160 for b in args.beams):
            p.error('Campaign requires at least one protected beam between 80 and 160')


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(2**20), b""):
            h.update(block)
    return h.hexdigest()


def save(path, obj):
    path.write_text(json.dumps(obj, indent=2, allow_nan=False) + "\n")


def matrix(path):
    with Path(path).open("rb") as f:
        n, d = struct.unpack("<II", f.read(8))
    if not n or not d or Path(path).stat().st_size != 8 + n*d*4:
        raise ValueError(f"Invalid matrix: {path}")
    return np.memmap(path, dtype="<f4", mode="r", offset=8, shape=(n, d))


def write_matrix(path, array):
    with path.open("xb") as f:
        f.write(struct.pack("<II", *array.shape))
        np.asarray(array, dtype="<f4").tofile(f)


def prepare_data(args):
    cache = HERE / "data" / f"sift_n{args.rows}_q{args.queries}"
    manifest = cache / "manifest.json"
    if manifest.exists():
        m = json.loads(manifest.read_text())
        for name, digest in m["sha256"].items():
            if sha(cache / name) != digest:
                raise ValueError(f"Frozen experiment data changed: {cache / name}")
        return cache, m
    source = args.data_dir.resolve()
    base = matrix(source / "sift_base.fbin")
    query = matrix(source / "sift_query.fbin")
    if not 256 <= args.rows <= len(base) or not 1 <= args.queries <= len(query):
        raise ValueError("Requested data size outside source bounds")
    cache.mkdir(parents=True, exist_ok=False)
    write_matrix(cache / "base.fbin", base[:args.rows])
    write_matrix(cache / "query.fbin", query[:args.queries])
    frozen_base = matrix(cache / "base.fbin")
    selected_query = np.array(query[:args.queries])
    gt_source = next((source / name for name in ("sift_groundtruth.ivecs", "sift_groundtruth.ibin")
                      if (source / name).exists()), None)
    if args.rows == len(base) and gt_source:
        print(f"GT_MODE=REUSE_EXISTING source={gt_source}", flush=True)
        provided = load_gt_ids(gt_source, len(query), len(base))
        ids, dists, check = reuse_gt(frozen_base, selected_query, provided)
        gt = {"mode": "reused_existing", "source": str(gt_source), "sha256": sha(gt_source), **check}
    else:
        # Blocked float64 GEMM gives exact SIFT integer squared distances while
        # avoiding a full queries-by-base matrix or one giant difference cube.
        print("GT_MODE=EXACT_SUBSET_GEMM", flush=True)
        b = np.array(frozen_base, dtype=np.float64)
        bnorm = np.einsum("ij,ij->i", b, b)
        k = min(100, len(b))
        ids = np.empty((args.queries, k), dtype="<u4")
        dists = np.empty((args.queries, k), dtype="<f4")
        for start in range(0, args.queries, 16):
            q = selected_query[start:start+16].astype(np.float64)
            scores = np.maximum(0, np.einsum("ij,ij->i", q, q)[:, None] + bnorm[None, :] - 2*(q @ b.T))
            order = np.argsort(scores, axis=1, kind="stable")[:, :k]
            ids[start:start+len(q)] = order
            dists[start:start+len(q)] = np.take_along_axis(scores, order, axis=1)
        gt = {"mode": "exact_subset_float64_gemm"}
    with (cache / "gt.ibin").open("xb") as f:
        f.write(struct.pack("<II", *ids.shape)); ids.tofile(f); dists.tofile(f)
    m = {"rows": args.rows, "queries": args.queries, "dimension": base.shape[1], "gt": gt,
         "source_base": str(source / "sift_base.fbin"), "source_query": str(source / "sift_query.fbin"),
         "sha256": {name: sha(cache / name) for name in ("base.fbin", "query.fbin", "gt.ibin")}}
    save(manifest, m)
    return cache, m


def check_protected():
    expected = json.loads((HERE / "protected_originals.sha256.json").read_text())
    changed = [name for name, digest in expected.items() if sha(REPO / name) != digest]
    if changed:
        raise ValueError(f"Original files changed since experiment snapshot: {changed}")
    return len(expected)


def graph_audit(path, n):
    a = np.memmap(path, dtype="<u4", mode="r")
    if len(a) < n+2 or int(a[0]) != n or int(a[1]) != 64:
        raise ValueError("Graph header mismatch")
    degree = a[2:n+2]
    edges = a[n+2:]
    if np.any(degree > 64) or int(degree.sum(dtype=np.uint64)) != len(edges) or np.any(edges >= n):
        raise ValueError("Invalid graph degree, file length or neighbor ID")
    return {"nodes": n, "edges": len(edges), "average_degree": float(degree.mean()),
            "isolated_nodes": int(np.count_nonzero(degree == 0)), "sha256": sha(path)}


def read_queries(path, beams, count):
    result = {}
    with path.open(newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            beam, q = int(row["beam"]), int(row["query_id"])
            if beam not in beams or not 0 <= q < count:
                raise ValueError("Unexpected query or beam in native CSV")
            entry = result.setdefault(beam, {})
            if q in entry:
                raise ValueError("Duplicate query row")
            latency, recall, hits = float(row["latency_us"]), float(row["recall_at_10"]), int(row["hits_at_10"])
            if not math.isfinite(latency) or latency <= 0 or not 0 <= hits <= 10 or abs(recall-hits/10) > 1e-10:
                raise ValueError("Invalid native query measurement")
            entry[q] = (latency, recall)
    arrays = {}
    for beam in beams:
        if len(result.get(beam, {})) != count:
            raise ValueError(f"Incomplete query rows at beam {beam}")
        arrays[beam] = np.array([result[beam][q] for q in range(count)])
    return arrays


def run_case(args, data, name, mode=None, epsilon=None, seed=None, min_fanout=None):
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", name):
        raise ValueError("Run name must be a single ASCII filename component")
    out = HERE / "runs" / name
    out.mkdir(parents=True, exist_ok=False)
    mode = args.mode if mode is None else mode
    epsilon = args.epsilon if epsilon is None else epsilon
    seed = args.seed if seed is None else seed
    floor = args.min_fanout if min_fanout is None else min_fanout
    binary = HERE / "build/algorithms/PipNN/neighbors-pipnn_FLOAT_T_EUCLIDEAN"
    evaluator = HERE / "build/local_graph_recall"
    env = {k: v for k, v in os.environ.items() if not k.startswith(("AF_", "R86_"))}
    env.update(PARLAY_NUM_THREADS=str(args.threads), OMP_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1", MKL_NUM_THREADS="1",
               AF_MODE=mode, AF_EPSILON=str(epsilon), AF_MIN_DEPTH=str(args.min_depth),
               AF_MIN_FANOUT=str(floor), AF_SEED=str(seed),
               AF_STATS_OUT=str(out / "adaptive_summary.json"), AF_BUCKET_OUT=str(out / "buckets.jsonl"))
    cmd = [str(binary), "-base_path", str(data / "base.fbin"), "-graph_outfile", str(out / "index.graph"),
           "-num_clusters", "1", "-cluster_size", "256", "-top_level_leaders", "100",
           "-fanout_scheme", "10,3,1", "-mst_deg", "2", "-prune", "1", "-prune_all", "1",
           "-prune_degree", "64", "-table_size", "160", "-hash_bits", "12", "-alpha", "1.1", "-k", "0"]
    summary = {"status": "RUNNING", "utc": datetime.now(timezone.utc).isoformat(), "run_name": name,
               "mode": mode, "epsilon": epsilon, "min_fanout": floor, "min_depth": args.min_depth,
               "seed": seed, "threads": args.threads, "beams": args.beams, "rows": args.rows,
               "queries": args.queries, "data": str(data), "command": cmd,
               "binary_sha256": sha(binary), "evaluator_sha256": sha(evaluator),
               "experiment_source_sha256": {str(p.relative_to(HERE)): sha(p)
                                            for p in list((HERE / "source").rglob('*')) + list(HERE.glob('*.h')) + list(HERE.glob('*.cc')) if p.is_file()}}
    save(out / "summary.json", summary)
    print(f"START_RUN={name} mode={mode} epsilon={epsilon} seed={seed}", flush=True)
    try:
        timed = ["/usr/bin/time", "-f", "wall_s=%e\npeak_rss_kib=%M", "-o", str(out / "time.txt"), *cmd]
        with (out / "build.log").open('w') as f:
            subprocess.run(timed, stdout=f, stderr=subprocess.STDOUT, check=True, env=env, cwd=out, timeout=args.timeout)
        for line in (out / "time.txt").read_text().splitlines():
            if '=' in line:
                key, value = line.split('=', 1); summary[key] = float(value)
        summary['telemetry'] = json.loads((out / "adaptive_summary.json").read_text())
        summary['graph'] = graph_audit(out / "index.graph", args.rows)
        search = [str(evaluator), str(out / "index.graph"), str(data / "base.fbin"), str(data / "query.fbin"),
                  str(data / "gt.ibin"), str(out / "query_metrics.csv"), ','.join(map(str, args.beams))]
        summary['search_command'] = search
        with (out / "search.log").open('w') as f:
            subprocess.run(search, stdout=f, stderr=subprocess.STDOUT, check=True, env=env, cwd=out, timeout=args.timeout)
        text = (out / "search.log").read_text()
        values = re.findall(r"LOCAL_RECALL_ROW beam=(\d+) recall=([\d.eE+-]+) qps=([\d.eE+-]+)", text)
        if [int(v[0]) for v in values] != args.beams or 'LOCAL_RECALL_EVAL_PASS' not in text:
            raise ValueError("Incomplete search output")
        arrays = read_queries(out / "query_metrics.csv", args.beams, args.queries)
        summary['reachable_from_start0'] = int(re.search(r'AF_GRAPH_REACHABLE=(\d+)', text).group(1))
        summary['search'] = []
        lines = []
        for b, recall, qps in values:
            beam = int(b); measurements = arrays[beam]
            if abs(measurements[:, 1].mean() - float(recall)) > 1e-6:
                raise ValueError("Per-query Recall does not match native aggregate")
            latency = dict(zip(['mean','p50','p95','p99'], [float(measurements[:, 0].mean()), *map(float, np.percentile(measurements[:, 0], [50,95,99]))]))
            summary['search'].append({'beam': beam, 'recall_at_10': float(recall), 'qps': float(qps), 'latency_us': latency})
            lines.append(f"AF_SEARCH beam={beam} recall={recall} qps={qps} " + ' '.join(f'latency_{k}_us={v:.6f}' for k,v in latency.items()))
        with (out / "search.log").open('a') as f: f.write('\n'.join(lines)+'\n')
        summary['status'] = 'PASS'
        print(f"RUN_PASS={name} wall_s={summary['wall_s']} proposals={summary['telemetry']['directed_proposals']} edges={summary['graph']['edges']}", flush=True)
    except Exception as error:
        summary.update(status='FAILED', error=str(error)); raise
    finally:
        save(out / "summary.json", summary)
    return out, summary, arrays


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--rows', type=int, default=1000000)
    p.add_argument('--queries', type=int, default=10000)
    p.add_argument('--data-dir', type=Path, default=REPO/'data')
    p.add_argument('--threads', type=int, default=4)
    p.add_argument('--timeout', type=int, default=1800)
    p.add_argument('--mode', choices=['fixed','adaptive'], default='adaptive')
    p.add_argument('--epsilon', type=float, default=.03)
    p.add_argument('--min-fanout', type=int, default=1)
    p.add_argument('--min-depth', type=int, default=1)
    p.add_argument('--seed', type=int, default=555)
    p.add_argument('--beams', type=beam_list, default=[40,60,80,100,120,140,160,240])
    p.add_argument('--run-name', type=run_name, required=True)
    return p


def main():
    p=parser(); args=p.parse_args()
    validate_args(args,p)
    check_protected()
    if (HERE/'runs'/args.run_name).exists(): p.error('Run name already exists')
    data, _ = prepare_data(args)
    run_case(args, data, args.run_name)
    print(f'PROTECTED_ORIGINALS_UNCHANGED={check_protected()}', flush=True)


if __name__=='__main__':
    main()
