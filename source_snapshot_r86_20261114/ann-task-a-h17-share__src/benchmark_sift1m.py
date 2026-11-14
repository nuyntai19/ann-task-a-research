import json
import platform
import resource
import statistics
import time
from pathlib import Path
from importlib.metadata import version

import h5py
import hnswlib
import numpy as np

ROOT = Path.home() / "ann-task-a"
DATA = ROOT / "data/sift-128-euclidean.hdf5"
OUTPUT = ROOT / "results/sift1m_hnsw_baseline.json"
INDEX = ROOT / "indexes/sift1m_hnsw_M16_efc100.bin"

M = 16
EFC = 100
BUILD_THREADS = 4
SEARCH_THREADS = 1
SEED = 42
K = 10
EF_VALUES = [100, 200, 400, 800]

assert DATA.is_file(), f"Missing dataset: {DATA}"

print("=== SIFT1M HNSW BENCHMARK ===", flush=True)

# Load the training vectors
start_total = time.perf_counter()
start_load = time.perf_counter()

with h5py.File(DATA, "r") as f:
    base = f["train"][:]

assert base.shape == (1_000_000, 128)
assert base.dtype == np.float32

load_seconds = time.perf_counter() - start_load
n, dim = base.shape

print(f"Loaded {n} vectors, dim={dim}", flush=True)
print(f"Train load: {load_seconds:.3f}s", flush=True)

# Initialize and build HNSW
start_init = time.perf_counter()

index = hnswlib.Index(space="l2", dim=dim)
index.init_index(
    max_elements=n,
    M=M,
    ef_construction=EFC,
    random_seed=SEED
)

init_seconds = time.perf_counter() - start_init

print("Building HNSW...", flush=True)

start_build = time.perf_counter()

index.add_items(
    base,
    num_threads=BUILD_THREADS
)

build_seconds = time.perf_counter() - start_build

assert index.get_current_count() == n

peak_rss_build_mib = (
    resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    / 1024
)

print(f"BUILD: {build_seconds:.3f}s", flush=True)
print(
    f"Peak process RSS through BUILD: "
    f"{peak_rss_build_mib:.1f} MiB",
    flush=True
)

# Save index
INDEX.parent.mkdir(parents=True, exist_ok=True)

start_save = time.perf_counter()
index.save_index(str(INDEX))
save_seconds = time.perf_counter() - start_save

index_bytes = INDEX.stat().st_size
raw_to_index_seconds = time.perf_counter() - start_total

print(
    f"Index size: {index_bytes / (1024**2):.1f} MiB",
    flush=True
)

# Load query and ground truth
with h5py.File(DATA, "r") as f:
    queries = f["test"][:]
    ground_truth = f["neighbors"][:, :K]

assert queries.shape == (10_000, 128)
assert ground_truth.shape == (10_000, K)
assert np.all(ground_truth >= 0)
assert np.all(ground_truth < n)

q = len(queries)
results = []

# Search quality and speed
for ef in EF_VALUES:
    index.set_ef(ef)

    # Warm-up
    index.knn_query(
        queries[:200],
        k=K,
        num_threads=SEARCH_THREADS
    )

    times = []
    labels = None

    for _ in range(3):
        t0 = time.perf_counter()

        current_labels, _ = index.knn_query(
            queries,
            k=K,
            num_threads=SEARCH_THREADS
        )

        times.append(time.perf_counter() - t0)
        labels = current_labels

    matches = (
        labels[:, :, None]
        == ground_truth[:, None, :]
    ).any(axis=2)

    recall = float(matches.sum() / (q * K))
    median_search_seconds = statistics.median(times)
    qps = q / median_search_seconds

    results.append({
        "ef_search": ef,
        "recall_at_10": recall,
        "qps": qps,
        "search_times_seconds": times
    })

    print(
        f"ef={ef:3d} | "
        f"Recall@10={recall:.4f} | "
        f"QPS={qps:.1f}",
        flush=True
    )

report = {
    "dataset": "SIFT1M",
    "dataset_file_bytes": DATA.stat().st_size,
    "n": n,
    "dim": dim,
    "queries": q,
    "k": K,
    "metric": "l2",
    "algorithm": "hnswlib",
    "hnswlib_version": version("hnswlib"),
    "python_version": platform.python_version(),
    "seed": SEED,
    "M": M,
    "ef_construction": EFC,
    "build_threads": BUILD_THREADS,
    "search_threads": SEARCH_THREADS,
    "train_load_seconds": load_seconds,
    "init_seconds": init_seconds,
    "build_seconds": build_seconds,
    "save_seconds": save_seconds,
    "raw_to_index_seconds": raw_to_index_seconds,
    "peak_process_rss_through_build_mib": peak_rss_build_mib,
    "index_bytes": index_bytes,
    "search_results": results
}

OUTPUT.parent.mkdir(parents=True, exist_ok=True)
OUTPUT.write_text(json.dumps(report, indent=2))

print(f"Results: {OUTPUT}", flush=True)
print("=== COMPLETED ===", flush=True)
