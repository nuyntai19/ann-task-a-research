import json
import struct
from pathlib import Path

import numpy as np


ROOT = Path.home() / "ann-task-a"
OUT = ROOT / "experiments/G0/results"

FILES = {
    "f15": ROOT / "results/pipnn_static_sift1m_f15_4t.graph",
    "f30": ROOT / "results/pipnn_sift1m_4t.graph",
    "f60": ROOT / "results/pipnn_static_sift1m_f60_4t.graph",
}


def load_graph(path):
    if not path.is_file():
        raise FileNotFoundError(path)

    with open(path, "rb") as file:
        header = file.read(8)

    if len(header) != 8:
        raise ValueError(f"Invalid graph header: {path}")

    n, max_degree = struct.unpack("<II", header)

    degrees = np.memmap(
        path,
        dtype="<u4",
        mode="r",
        offset=8,
        shape=(n,),
    )

    edge_count = int(degrees.sum(dtype=np.uint64))

    expected_bytes = 8 + 4 * n + 4 * edge_count

    if path.stat().st_size != expected_bytes:
        raise ValueError(
            f"Graph file size mismatch: {path}"
        )

    if np.any(degrees > max_degree):
        raise ValueError(
            f"Degree limit exceeded: {path}"
        )

    offsets = np.empty(n + 1, dtype=np.int64)
    offsets[0] = 0

    np.cumsum(
        degrees,
        dtype=np.int64,
        out=offsets[1:],
    )

    edges = np.memmap(
        path,
        dtype="<u4",
        mode="r",
        offset=8 + 4 * n,
        shape=(edge_count,),
    )

    if edge_count > 0 and int(edges.max()) >= n:
        raise ValueError(
            f"Invalid destination vertex ID: {path}"
        )

    return {
        "n": n,
        "max_degree": max_degree,
        "degrees": degrees,
        "offsets": offsets,
        "edges": edges,
        "edge_count": edge_count,
    }


def get_neighbors(graph, vertex):
    start = graph["offsets"][vertex]
    end = graph["offsets"][vertex + 1]

    return set(
        int(x) for x in graph["edges"][start:end]
    )


print("===== G0.1 — LOADING GRAPHS =====")

graphs = {}

for label, path in FILES.items():
    graphs[label] = load_graph(path)
    print(f"Loaded {label}: {path.name}")


n = graphs["f15"]["n"]

if any(g["n"] != n for g in graphs.values()):
    raise ValueError(
        "Graph vertex counts do not match"
    )


rng = np.random.default_rng(20261023)

sample = np.sort(
    rng.choice(
        n,
        size=min(20000, n),
        replace=False,
    )
)


report = {
    "dataset": "SIFT1M",
    "seed": 20261023,
    "sample_size": int(len(sample)),
    "graphs": {},
    "comparisons": {},
}


print("\n===== GRAPH STRUCTURE =====")

for label, graph in graphs.items():
    degrees = graph["degrees"]

    indegrees = np.bincount(
        graph["edges"],
        minlength=n,
    )

    result = {
        "vertices": int(n),
        "directed_edges": int(graph["edge_count"]),
        "max_degree": int(graph["max_degree"]),
        "average_degree": float(degrees.mean()),
        "median_degree": float(np.median(degrees)),
        "degree_p90": float(np.percentile(degrees, 90)),
        "degree_p99": float(np.percentile(degrees, 99)),
        "zero_out_degree": int(
            np.count_nonzero(degrees == 0)
        ),
        "zero_in_degree": int(
            np.count_nonzero(indegrees == 0)
        ),
        "in_degree_p99": float(
            np.percentile(indegrees, 99)
        ),
        "graph_bytes": int(
            FILES[label].stat().st_size
        ),
    }

    report["graphs"][label] = result

    print(f"\n--- {label} ---")

    for name, value in result.items():
        print(f"{name}: {value}")


print("\n===== EDGE RETENTION =====")

for old_label, new_label in [
    ("f15", "f30"),
    ("f30", "f60"),
    ("f15", "f60"),
]:
    old_graph = graphs[old_label]
    new_graph = graphs[new_label]

    old_edges = 0
    new_edges = 0
    shared_edges = 0
    changed_vertices = 0

    for vertex in sample:
        vertex = int(vertex)

        a = get_neighbors(old_graph, vertex)
        b = get_neighbors(new_graph, vertex)

        old_edges += len(a)
        new_edges += len(b)
        shared_edges += len(a & b)

        if a != b:
            changed_vertices += 1

    result = {
        "sample_vertices": int(len(sample)),
        "retention_old_edges": (
            shared_edges / old_edges
            if old_edges else 0.0
        ),
        "new_only_edges_sample": int(
            new_edges - shared_edges
        ),
        "old_only_edges_sample": int(
            old_edges - shared_edges
        ),
        "changed_vertex_fraction": (
            changed_vertices / len(sample)
        ),
    }

    name = f"{old_label}_to_{new_label}"

    report["comparisons"][name] = result

    print(f"\n--- {name} ---")

    for key, value in result.items():
        print(f"{key}: {value}")


OUT.mkdir(parents=True, exist_ok=True)

output = OUT / "topology_audit.json"

output.write_text(
    json.dumps(report, indent=2),
    encoding="utf-8",
)

print("\n===== FINAL STATUS =====")
print(f"Saved results: {output}")
print("G0.1 TOPOLOGY AUDIT: PASS")
