import argparse
import json
import resource
import time

import h5py
import hnswlib
import numpy as np

parser = argparse.ArgumentParser()
parser.add_argument("--threads", type=int, required=True)
args = parser.parse_args()

threads = args.threads
assert threads in [1, 2, 4, 8]

DATA = "data/sift-128-euclidean.hdf5"
N = 1_000_000
DIM = 128
K = 10
M = 16
EFC = 100
SEED = 42
EF_SEARCH = 200

print(f"\n=== SIFT1M | BUILD THREADS = {threads} ===",
      flush=True)

with h5py.File(DATA, "r") as f:
    base = f["train"][:]
    queries = f["test"][:]
    ground_truth = f["neighbors"][:, :K]

assert base.shape == (N, DIM)
assert queries.shape == (10_000, DIM)

index = hnswlib.Index(space="l2", dim=DIM)

index.init_index(
    max_elements=N,
    M=M,
    ef_construction=EFC,
    random_seed=SEED
)

start = time.perf_counter()

index.add_items(
    base,
    num_threads=threads
)

build_seconds = time.perf_counter() - start

peak_rss_mib = (
    resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    / 1024
)

index.set_ef(EF_SEARCH)

# Warm-up
index.knn_query(
    queries[:200],
    k=K,
    num_threads=1
)

start = time.perf_counter()

labels, _ = index.knn_query(
    queries,
    k=K,
    num_threads=1
)

search_seconds = time.perf_counter() - start

matches = (
    labels[:, :, None]
    == ground_truth[:, None, :]
).any(axis=2)

recall = float(matches.sum() / (len(queries) * K))
qps = len(queries) / search_seconds

report = {
    "dataset": "SIFT1M",
    "threads": threads,
    "build_seconds": round(build_seconds, 4),
    "build_vectors_per_second": round(N / build_seconds, 2),
    "recall_at_10": round(recall, 5),
    "ef_search": EF_SEARCH,
    "search_threads": 1,
    "qps": round(qps, 2),
    "peak_rss_through_build_mib": round(peak_rss_mib, 2)
}

print(json.dumps(report, indent=2), flush=True)

with open(
    f"results/sift1m_scaling_{threads}t.json",
    "w"
) as f:
    json.dump(report, f, indent=2)

print(f"=== DONE: {threads} THREADS ===", flush=True)
