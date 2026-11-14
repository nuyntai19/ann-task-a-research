import csv
import gc
import statistics
import time
from pathlib import Path

import hnswlib
import numpy as np

N = 100_000
DIM = 128
M = 16
EFC = 100
SEED = 42
REPEATS = 3
THREADS = [1, 2, 4, 8]

rng = np.random.default_rng(SEED)
base = rng.standard_normal((N, DIM)).astype(np.float32)
ids = np.arange(N)

rows = []

print("=== PARALLEL HNSW BUILD BENCHMARK ===", flush=True)

for rep in range(REPEATS):
    order = THREADS if rep % 2 == 0 else THREADS[::-1]

    for threads in order:
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

        elapsed = time.perf_counter() - start

        rows.append({
            "repeat": rep + 1,
            "threads": threads,
            "build_seconds": elapsed
        })

        print(
            f"Repeat={rep+1} | "
            f"Threads={threads} | "
            f"BUILD={elapsed:.3f}s",
            flush=True
        )

        del index
        gc.collect()

output = Path.home() / "ann-task-a/results/parallel_build_100k.csv"

with output.open("w", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=rows[0].keys())
    writer.writeheader()
    writer.writerows(rows)

medians = {
    t: statistics.median(
        r["build_seconds"]
        for r in rows
        if r["threads"] == t
    )
    for t in THREADS
}

print("\n=== SUMMARY ===")
print("Threads | Median BUILD | Speedup | Efficiency")

for t in THREADS:
    speedup = medians[1] / medians[t]
    efficiency = speedup / t

    print(
        f"{t:7d} | "
        f"{medians[t]:12.3f}s | "
        f"{speedup:7.2f}x | "
        f"{efficiency:9.1%}"
    )

print(f"\nSaved: {output}")
