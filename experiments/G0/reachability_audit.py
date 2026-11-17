import json
import struct
from collections import deque
from pathlib import Path

import numpy as np

ROOT = Path.home() / "ann-task-a"
OUT = ROOT / "experiments/G0/results"

GRAPHS = {
    "f15": ROOT / "results/pipnn_static_sift1m_f15_4t.graph",
    "f30": ROOT / "results/pipnn_sift1m_4t.graph",
    "f60": ROOT / "results/pipnn_static_sift1m_f60_4t.graph",
}


def analyze_graph(path, start=0):
    with path.open("rb") as f:
        n, max_degree = struct.unpack("<II", f.read(8))

    degree = np.memmap(
        path, dtype="<u4", mode="r",
        offset=8, shape=(n,)
    )

    offsets = np.empty(n + 1, dtype=np.int64)
    offsets[0] = 0
    np.cumsum(degree, dtype=np.int64, out=offsets[1:])

    edge_count = int(offsets[-1])
    expected_size = 8 + 4 * n + 4 * edge_count

    if path.stat().st_size != expected_size:
        raise ValueError("Invalid graph file size")

    edges = np.memmap(
        path, dtype="<u4", mode="r",
        offset=8 + 4 * n,
        shape=(edge_count,)
    )

    distance = np.full(n, -1, dtype=np.int32)
    distance[start] = 0

    queue = deque([start])
    processed = 0

    while queue:
        vertex = queue.popleft()
        processed += 1

        begin = int(offsets[vertex])
        end = int(offsets[vertex + 1])
        next_depth = int(distance[vertex]) + 1

        for neighbor in edges[begin:end]:
            neighbor = int(neighbor)

            if distance[neighbor] == -1:
                distance[neighbor] = next_depth
                queue.append(neighbor)

        if processed % 200000 == 0:
            print(
                f"  Visited {processed:,} vertices",
                flush=True
            )

    reachable_depths = distance[distance >= 0]
    reachable = int(reachable_depths.size)

    return {
        "vertices": n,
        "max_degree": max_degree,
        "entry_point": start,
        "reachable": reachable,
        "unreachable": n - reachable,
        "reachable_fraction": reachable / n,
        "bfs_hops_p50": float(
            np.percentile(reachable_depths, 50)
        ),
        "bfs_hops_p90": float(
            np.percentile(reachable_depths, 90)
        ),
        "bfs_hops_p99": float(
            np.percentile(reachable_depths, 99)
        ),
        "bfs_hops_max": int(reachable_depths.max()),
    }


results = {}

for name, path in GRAPHS.items():
    print(f"\n===== REACHABILITY {name} =====", flush=True)

    if not path.exists():
        raise FileNotFoundError(path)

    result = analyze_graph(path)
    results[name] = result

    for key, value in result.items():
        print(f"{key}: {value}")

OUT.mkdir(parents=True, exist_ok=True)

output = OUT / "reachability_audit.json"
output.write_text(
    json.dumps(results, indent=2),
    encoding="utf-8"
)

print("\n===== REACHABILITY AUDIT COMPLETE =====")
print(f"Saved: {output}")
