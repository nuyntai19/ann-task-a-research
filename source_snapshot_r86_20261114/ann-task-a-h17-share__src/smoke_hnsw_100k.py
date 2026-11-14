import json
import time
import resource
from pathlib import Path

import hnswlib
import numpy as np
from scipy.spatial.distance import cdist

# Cấu hình thí nghiệm
N = 100_000
DIM = 128
N_QUERIES = 200
K = 10
THREADS = 4
SEED = 42

rng = np.random.default_rng(SEED)

print("=== ANN TASK A: HNSW SMOKE TEST ===", flush=True)
print(f"N={N}, dim={DIM}, queries={N_QUERIES}", flush=True)

# 1. Sinh dữ liệu thử nghiệm
base = rng.standard_normal((N, DIM)).astype(np.float32)
queries = rng.standard_normal(
    (N_QUERIES, DIM)
).astype(np.float32)

# 2. Xây graph HNSW
index = hnswlib.Index(space="l2", dim=DIM)
index.init_index(
    max_elements=N,
    M=16,
    ef_construction=100,
    random_seed=SEED
)

start = time.perf_counter()
index.add_items(
    base,
    ids=np.arange(N),
    num_threads=THREADS
)
build_seconds = time.perf_counter() - start

print(f"BUILD: {build_seconds:.3f} giây", flush=True)

# 3. Tính ground truth chính xác bằng brute force
print("Đang tính exact ground truth...", flush=True)

ground_truth = []

for start_row in range(0, N_QUERIES, 25):
    q = queries[start_row:start_row + 25]

    distances = cdist(q, base, metric="sqeuclidean")
    topk = np.argpartition(
        distances, kth=K - 1, axis=1
    )[:, :K]

    ground_truth.extend(topk)

ground_truth = np.asarray(ground_truth)

# 4. Đánh giá Recall@10 và QPS
results = []

for ef in [20, 50, 100, 200]:
    index.set_ef(ef)

    start = time.perf_counter()
    labels, _ = index.knn_query(
        queries, k=K, num_threads=THREADS
    )
    search_seconds = time.perf_counter() - start

    correct = sum(
        len(set(labels[i]) & set(ground_truth[i]))
        for i in range(N_QUERIES)
    )

    recall = correct / (N_QUERIES * K)
    qps = N_QUERIES / search_seconds

    results.append({
        "ef_search": ef,
        "recall_at_10": recall,
        "qps": qps
    })

    print(
        f"ef={ef:3d} | "
        f"Recall@10={recall:.4f} | "
        f"QPS={qps:.1f}",
        flush=True
    )

peak_rss_mib = (
    resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    / 1024
)

report = {
    "dataset": "synthetic_gaussian",
    "n": N,
    "dim": DIM,
    "queries": N_QUERIES,
    "seed": SEED,
    "threads": THREADS,
    "M": 16,
    "ef_construction": 100,
    "build_seconds": build_seconds,
    "peak_process_rss_mib": peak_rss_mib,
    "search_results": results
}

output = Path.home() / "ann-task-a/results/smoke_hnsw_100k.json"
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps(report, indent=2))

print(f"Peak RSS: {peak_rss_mib:.1f} MiB")
print(f"Đã lưu kết quả: {output}")
print("=== HOÀN THÀNH ===")
