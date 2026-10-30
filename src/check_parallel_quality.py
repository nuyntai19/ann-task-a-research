import csv
import time
from pathlib import Path

import hnswlib
import numpy as np
from scipy.spatial.distance import cdist

N = 100_000
DIM = 128
Q = 1_000
K = 10
M = 16
EFC = 100
SEED = 42

THREADS = [1, 2, 4, 8]
EF_VALUES = [100, 200, 400, 800]

rng = np.random.default_rng(SEED)

base = rng.standard_normal(
    (N, DIM)
).astype(np.float32)

queries = rng.standard_normal(
    (Q, DIM)
).astype(np.float32)

ids = np.arange(N)

print("Computing exact ground truth...", flush=True)

ground_truth = np.empty((Q, K), dtype=np.int64)

for start in range(0, Q, 25):
    end = min(start + 25, Q)

    distances = cdist(
        queries[start:end],
        base,
        metric="sqeuclidean"
    )

    ground_truth[start:end] = np.argpartition(
        distances,
        kth=K - 1,
        axis=1
    )[:, :K]

rows = []

for threads in THREADS:
    print(f"\nBuilding with {threads} threads...", flush=True)

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
        ids=ids,
        num_threads=threads
    )

    build_time = time.perf_counter() - start

    for ef in EF_VALUES:
        index.set_ef(ef)

        # Warm-up, không tính vào QPS
        index.knn_query(
            queries[:100],
            k=K,
            num_threads=1
        )

        start = time.perf_counter()

        labels, _ = index.knn_query(
            queries,
            k=K,
            num_threads=1
        )

        search_time = time.perf_counter() - start

        correct = sum(
            len(set(labels[i]) & set(ground_truth[i]))
            for i in range(Q)
        )

        recall = correct / (Q * K)
        qps = Q / search_time

        rows.append({
            "threads": threads,
            "build_seconds": round(build_time, 4),
            "ef_search": ef,
            "recall_at_10": round(recall, 4),
            "qps": round(qps, 2)
        })

        print(
            f"threads={threads} "
            f"ef={ef} "
            f"BUILD={build_time:.3f}s "
            f"Recall@10={recall:.4f} "
            f"QPS={qps:.1f}",
            flush=True
        )

    del index

output = Path.home() / (
    "ann-task-a/results/parallel_quality_100k.csv"
)

with output.open("w", newline="") as f:
    writer = csv.DictWriter(
        f,
        fieldnames=rows[0].keys()
    )
    writer.writeheader()
    writer.writerows(rows)

print(f"\nSaved: {output}")
print("=== COMPLETED ===")
