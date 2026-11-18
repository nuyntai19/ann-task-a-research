#!/usr/bin/env python3
"""Prepare local data, build an R86 graph, audit it, and run native search."""
import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import struct
import subprocess
import sys
import tempfile
import time

# Keep NumPy/BLAS from consuming all cores during exact-GT preparation.
for key in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ[key] = "1"
import numpy as np

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
SOURCE = REPO / "experiments/R86/r86_v1_2_source"


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_matrix(path, dtype="<f4"):
    with Path(path).open("rb") as stream:
        header = stream.read(8)
    if len(header) != 8:
        raise ValueError(f"Truncated header: {path}")
    rows, dims = struct.unpack("<II", header)
    if not rows or not dims or Path(path).stat().st_size != 8 + rows * dims * 4:
        raise ValueError(f"Invalid matrix dimensions/file size: {path}")
    return np.memmap(path, dtype=dtype, mode="r", offset=8, shape=(rows, dims))


def write_matrix(path, values):
    values = np.asarray(values, dtype="<f4")
    with path.open("xb") as stream:
        stream.write(struct.pack("<II", *values.shape))
        values.tofile(stream)


def prepare(args):
    n = args.rows if args.rows is not None else (2048 if args.dataset == "synthetic" else 10000)
    nq = args.queries
    if n < 256 or nq < 1:
        raise ValueError("Use at least 256 base vectors and one query")
    if args.dataset == "synthetic":
        rng = np.random.default_rng(20261118)
        base = rng.normal(size=(n, 128)).astype("<f4")
        queries = rng.normal(size=(nq, 128)).astype("<f4")
        origin = {"kind": "synthetic", "seed": 20261118}
    else:
        candidates = [REPO / "data", REPO.parent.parent / "PipeANN/data/sift1m_run/converted"]
        data_root = args.sift_dir
        if data_root is None:
            data_root = next((p for p in candidates if (p / "sift_base.fbin").is_file()
                              and (p / "sift_query.fbin").is_file()), None)
        if data_root is None:
            raise ValueError("SIFT not found. Use --sift-dir DIRECTORY containing sift_base.fbin and sift_query.fbin")
        data_root = data_root.expanduser().resolve()
        source_base, source_query = data_root / "sift_base.fbin", data_root / "sift_query.fbin"
        full_base, full_query = read_matrix(source_base), read_matrix(source_query)
        if n > len(full_base) or nq > len(full_query) or full_base.shape[1] != full_query.shape[1]:
            raise ValueError("Requested subset exceeds source sizes or dimensions differ")
        base, queries = np.array(full_base[:n]), np.array(full_query[:nq])
        origin = {"kind": "SIFT prefix subset", "base": str(source_base), "query": str(source_query),
                  "source_base_shape": list(full_base.shape), "source_query_shape": list(full_query.shape)}
    # Each invocation keeps its own inputs and matching exact GT. Never reuse
    # the SIFT1M GT for a smaller base or replace files from the PipeANN project.
    data_parent = HERE / "data"
    data_parent.mkdir(exist_ok=True)
    data = Path(tempfile.mkdtemp(prefix=f"{args.dataset}-n{n}-q{nq}-", dir=data_parent))
    write_matrix(data / "base.fbin", base)
    write_matrix(data / "query.fbin", queries)
    k = min(100, n)
    ids = np.empty((nq, k), dtype="<u4")
    distances = np.empty((nq, k), dtype="<f4")
    # Float64 direct differences avoid cancellation and make SIFT integer ties
    # exact. Process one query at a time to keep temporary memory bounded.
    base64 = base.astype(np.float64)
    for i, query in enumerate(queries):
        delta = base64 - query.astype(np.float64)
        dists = np.einsum("ij,ij->i", delta, delta)
        order = np.argsort(dists, kind="stable")[:k]
        ids[i] = order
        distances[i] = dists[order]
    with (data / "gt.ibin").open("xb") as stream:
        stream.write(struct.pack("<II", nq, k))
        ids.tofile(stream)
        distances.tofile(stream)
    manifest = {"base_rows": n, "query_rows": nq, "dimension": base.shape[1], "gt_k": k,
                "origin": origin, "purpose": "LOCAL_FUNCTIONAL_CHECK_NOT_ARCHIVAL_BENCHMARK",
                "sha256": {p.name: sha256(p) for p in data.iterdir()}}
    (data / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"DATA_READY={data}", flush=True)
    return data, manifest


def audit_graph(path, expected_n):
    values = np.fromfile(path, dtype="<u4")
    if len(values) < 2 or int(values[0]) != expected_n or int(values[1]) != 64:
        raise ValueError("Graph header mismatch")
    degrees = values[2:2 + expected_n]
    if len(degrees) != expected_n or np.any(degrees > 64):
        raise ValueError("Truncated graph or invalid degrees")
    edges = values[2 + expected_n:]
    edge_count = int(degrees.sum(dtype=np.uint64))
    if not edge_count or len(edges) != edge_count or np.any(edges >= expected_n):
        raise ValueError("Graph edge count or neighbor IDs invalid")
    offset = 0
    self_edges = duplicates = 0
    for node, degree in enumerate(degrees):
        row = edges[offset:offset + int(degree)]
        self_edges += int(np.count_nonzero(row == node))
        duplicates += len(row) - len(np.unique(row))
        offset += int(degree)
    if self_edges or duplicates:
        raise ValueError(f"Graph has {self_edges} self edges and {duplicates} duplicate edges")
    return {"nodes": expected_n, "max_degree": 64, "edges": edge_count,
            "isolated_nodes": int(np.count_nonzero(degrees == 0)), "sha256": sha256(path)}


def read_latency(path, query_count, beams):
    samples = {beam: {} for beam in beams}
    with path.open(newline="") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames != ["beam", "query_id", "latency_us"]:
            raise ValueError("Invalid latency CSV header; rebuild the evaluator")
        for row in reader:
            beam, query_id, value = int(row["beam"]), int(row["query_id"]), float(row["latency_us"])
            if beam not in samples or not 0 <= query_id < query_count:
                raise ValueError("Unexpected beam or query ID in latency CSV")
            if query_id in samples[beam] or not np.isfinite(value) or value <= 0:
                raise ValueError("Duplicate query or invalid latency sample")
            samples[beam][query_id] = value
    result = {}
    for beam, values in samples.items():
        if len(values) != query_count:
            raise ValueError(f"Incomplete latency samples for beam {beam}")
        data = np.array(list(values.values()), dtype=np.float64)
        p50, p95, p99 = np.percentile(data, [50, 95, 99])
        result[beam] = {"query_count": query_count, "mean": float(data.mean()),
                        "p50": float(p50), "p95": float(p95), "p99": float(p99),
                        "min": float(data.min()), "max": float(data.max())}
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", choices=["synthetic", "sift"], default="synthetic")
    parser.add_argument("--variant", choices=["stock_off", "h17_on"], default="stock_off")
    parser.add_argument("--rows", type=int)
    parser.add_argument("--queries", type=int, default=32)
    parser.add_argument("--sift-dir", type=Path)
    parser.add_argument("--threads", type=int, default=min(4, len(os.sched_getaffinity(0))))
    parser.add_argument("--timeout", type=int, default=600)
    parser.add_argument("--prepare-only", action="store_true")
    args = parser.parse_args()
    if args.threads < 1 or args.timeout < 1:
        raise ValueError("Threads and timeout must be positive")
    build = HERE / "build" / args.variant
    binary = build / "algorithms/PipNN/neighbors-pipnn_FLOAT_T_EUCLIDEAN"
    evaluator = build / "local_graph_recall"
    if not args.prepare_only and (not binary.is_file() or not evaluator.is_file()):
        raise ValueError(f"Binaries not built. Run: bash {HERE / 'setup.sh'}")
    if not args.prepare_only:
        subprocess.run([sys.executable, str(HERE / "fetch_deps.py"), "--offline"], check=True)
    data, data_manifest = prepare(args)
    if args.prepare_only:
        return
    runs = HERE / "runs"
    runs.mkdir(exist_ok=True)
    out = Path(tempfile.mkdtemp(prefix=f"{args.dataset}-{args.variant}-", dir=runs))
    print(f"RUN_DIR={out}", flush=True)
    env = {k: v for k, v in os.environ.items() if not k.startswith("R86_")}
    env["PARLAY_NUM_THREADS"] = str(args.threads)
    if args.variant == "h17_on":
        env.update(R86_COUNTER_OUT=str(out / "counters.jsonl"),
                   R86_LEAF_SIZE_OUT=str(out / "leaf_sizes.out"),
                   R86_OCCUPANCY_OUT=str(out / "occupancy.jsonl"))
    graph = out / "index.graph"
    command = [str(binary), "-base_path", str(data / "base.fbin"),
               "-graph_outfile", str(graph), "-num_clusters", "1", "-cluster_size", "256",
               "-top_level_leaders", "100", "-fanout_scheme", "10,3,1", "-mst_deg", "2",
               "-prune", "1", "-prune_all", "1", "-prune_degree", "64",
               "-table_size", "160", "-hash_bits", "12", "-alpha", "1.1", "-k", "0"]
    summary = {"status": "RUNNING", "utc": datetime.now(timezone.utc).isoformat(),
               "variant": args.variant, "threads": args.threads, "data": str(data),
               "data_manifest": data_manifest, "command": command,
               "binary_sha256": sha256(binary), "evaluator_sha256": sha256(evaluator),
               "deps_lock_sha256": sha256(HERE / "deps.lock.json"),
               "local_source_sha256": {name: sha256(HERE / name) for name in
                                       ("evaluate.cc", "latency_probe.h", "instrument_latency.py",
                                        "run.py", "CMakeLists.txt")},
               "source_sha256": {str(p.relative_to(REPO)): sha256(p)
                                  for p in (SOURCE / "algorithms").rglob("*") if p.is_file()}}
    def save():
        (out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    save()
    try:
        start = time.monotonic()
        with (out / "build.log").open("w") as log:
            subprocess.run(command, env=env, cwd=out, stdout=log, stderr=subprocess.STDOUT,
                           check=True, timeout=args.timeout)
        summary["build_seconds"] = time.monotonic() - start
        summary["graph_audit"] = audit_graph(graph, data_manifest["base_rows"])
        if args.variant == "h17_on":
            for name in ("counters.jsonl", "leaf_sizes.out", "occupancy.jsonl"):
                if not (out / name).is_file() or not (out / name).stat().st_size:
                    raise ValueError(f"Missing counter output: {name}")
            with (out / "counters.jsonl").open() as stream:
                records = [json.loads(line) for line in stream if line.strip()]
            if not records:
                raise ValueError("Counter file contains no records")
            summary["counter_records"] = len(records)
        latency_csv = out / "query_latency.csv"
        search_command = [str(evaluator), str(graph), str(data / "base.fbin"),
                          str(data / "query.fbin"), str(data / "gt.ibin"), str(latency_csv)]
        summary["search_command"] = search_command
        summary["latency_measurement"] = {
            "unit": "microseconds", "scope": "per_query_service_time",
            "clock": "std::chrono::steady_clock", "includes_queue_wait": False,
            "includes_file_io": False, "percentile_method": "linear", "csv": str(latency_csv),
            "note": "Concurrent query processing time; QPS includes timer overhead. No warmup or repetitions.",
        }
        with (out / "search.log").open("w") as log:
            subprocess.run(search_command, env=env, cwd=out, stdout=log, stderr=subprocess.STDOUT,
                           check=True, timeout=args.timeout)
        search_log = (out / "search.log").read_text()
        rows = re.findall(r"LOCAL_RECALL_ROW beam=(\d+) recall=([\d.eE+-]+) qps=([\d.eE+-]+)", search_log)
        if len(rows) != 5 or "LOCAL_RECALL_EVAL_PASS" not in search_log:
            raise ValueError("Incomplete native search output")
        summary["search"] = [{"beam": int(b), "recall_at_10": float(r), "qps": float(q)}
                             for b, r, q in rows]
        if any(not 0 <= row["recall_at_10"] <= 1 or row["qps"] <= 0 for row in summary["search"]):
            raise ValueError("Invalid search metrics")
        latencies = read_latency(latency_csv, data_manifest["query_rows"],
                                 [row["beam"] for row in summary["search"]])
        latency_lines = []
        for row in summary["search"]:
            row["latency_us"] = latencies[row["beam"]]
            stats = row["latency_us"]
            latency_lines.append(
                f"LOCAL_LATENCY_ROW beam={row['beam']} queries={stats['query_count']} "
                + " ".join(f"{name}_us={stats[name]:.6f}" for name in
                           ("mean", "p50", "p95", "p99", "min", "max")))
        latency_log = "\n".join(latency_lines) + "\n"
        with (out / "search.log").open("a") as log:
            log.write(latency_log)
        search_log += latency_log
        summary["status"] = "LOCAL_FUNCTIONAL_CHECK_PASS"
        print(search_log, end="")
        print(f"LOCAL_FUNCTIONAL_CHECK_PASS summary={out / 'summary.json'}")
    except Exception as error:
        summary.update(status="FAILED", error=str(error))
        print(f"Run failed; logs are retained in {out}", file=sys.stderr)
        raise
    finally:
        save()


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        sys.exit(1)
