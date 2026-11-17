import json
import time
import heapq
import struct
import numpy as np
from pathlib import Path

ROOT = Path.home() / "ann-task-a"
OUT = ROOT / "experiments/G0/results"
SEED = 20261023

PROBE_Q = 24
TARGET_Q = 80
N_DEV = 600
N_VAL = 600


def read_matrix(path, dtype):
    with open(path, "rb") as f:
        header = f.read(8)
    n, d = struct.unpack("<II", header)

    expected = 8 + n * d * np.dtype(dtype).itemsize
    if path.stat().st_size != expected:
        raise ValueError(f"File size mismatch: {path}")

    data = np.memmap(
        path, dtype=dtype, mode="r",
        offset=8, shape=(n, d)
    )
    return data


def read_graph(path):
    with open(path, "rb") as f:
        n, maxdeg = struct.unpack("<II", f.read(8))

    degree = np.memmap(
        path, dtype="<u4", mode="r",
        offset=8, shape=(n,)
    )

    offsets = np.empty(n + 1, dtype=np.int64)
    offsets[0] = 0
    np.cumsum(degree, out=offsets[1:])

    total = int(offsets[-1])

    if path.stat().st_size != 8 + 4*n + 4*total:
        raise ValueError("Invalid graph size")

    edges = np.memmap(
        path, dtype="<u4", mode="r",
        offset=8 + 4*n, shape=(total,)
    )

    return degree, offsets, edges


print("Loading SIFT1M and graph...", flush=True)

base = read_matrix(
    ROOT / "data/sift1m.fbin", "<f4"
)
queries = read_matrix(
    ROOT / "data/sift1m_queries.fbin", "<f4"
)
def read_ground_truth_ids(path):
    with open(path, "rb") as f:
        header = f.read(8)

    if len(header) != 8:
        raise ValueError("Invalid ground truth header")

    n, k = struct.unpack("<II", header)

    if n == 0 or k < 10:
        raise ValueError(
            f"Invalid ground truth shape: n={n}, k={k}"
        )

    # ParlayANN .ibin:
    # 8-byte header + N*K uint32 IDs + N*K float32 distances
    expected = 8 + n * k * 8
    actual = path.stat().st_size

    print(
        f"GT shape: {n} queries x {k} neighbors",
        flush=True
    )
    print(
        f"GT size: actual={actual}, expected={expected}",
        flush=True
    )

    if actual != expected:
        raise ValueError(
            f"Ground truth size mismatch: {path}"
        )

    # Chỉ cần IDs cho Recall@10.
    # Distances vẫn nằm trong file nhưng không cần đọc.
    return np.memmap(
        path,
        dtype="<u4",
        mode="r",
        offset=8,
        shape=(n, k),
    )


gt = read_ground_truth_ids(
    ROOT / "data/sift1m_gt.ibin"
)

degree, offsets, edges = read_graph(
    ROOT / "results/pipnn_sift1m_4t.graph"
)

assert base.shape[0] == len(degree)
assert queries.shape[0] == gt.shape[0]
assert gt.shape[1] >= 10


def search_and_probe(query):
    # Best-first surrogate; NOT identical to C++ beam search.
    initial = base[0] - query
    d0 = float(np.dot(initial, initial))

    frontier = [(d0, 0)]
    seen = {0: d0}

    best_d = d0
    last_improve = 0
    best_history = []
    degree_history = []

    features = None

    for step in range(1, TARGET_Q + 1):
        if not frontier:
            break

        _, vertex = heapq.heappop(frontier)
        degree_history.append(int(degree[vertex]))

        start = int(offsets[vertex])
        end = int(offsets[vertex + 1])

        new_ids = []

        for neighbor in edges[start:end]:
            neighbor = int(neighbor)
            if neighbor not in seen:
                # Reserve ID before processing the batch.
                seen[neighbor] = float("inf")
                new_ids.append(neighbor)

        if new_ids:
            ids = np.asarray(new_ids, dtype=np.int64)
            diff = base[ids] - query

            dist = np.einsum(
                "ij,ij->i", diff, diff
            )

            for neighbor, distance in zip(new_ids, dist):
                distance = float(distance)
                seen[neighbor] = distance
                heapq.heappush(
                    frontier, (distance, neighbor)
                )

                if distance < best_d:
                    best_d = distance
                    last_improve = step

        best_history.append(best_d)

        if step == PROBE_Q:
            frontier_best = (
                frontier[0][0]
                if frontier else best_d
            )

            earlier = best_history[PROBE_Q // 2 - 1]

            features = {
                "best_distance": best_d,
                "degree_deficit": (
                    32.0 - float(np.mean(degree_history))
                ),
                "stall_fraction": (
                    (step - last_improve) / step
                ),
                "late_progress": (
                    max(0.0, earlier - best_d)
                    / max(earlier, 1e-9)
                ),
                "frontier_gap": (
                    max(0.0, frontier_best - best_d)
                    / max(best_d, 1e-9)
                ),
            }

    if features is None:
        return None

    # Top-10 from all discovered candidates.
    top10 = heapq.nsmallest(
        10, seen.items(), key=lambda item: item[1]
    )
    predicted = {vertex for vertex, _ in top10}

    return features, predicted


def auc(scores, labels):
    scores = np.asarray(scores, dtype=np.float64)
    labels = np.asarray(labels, dtype=np.int32)

    pos = scores[labels == 1]
    neg = np.sort(scores[labels == 0])

    if len(pos) == 0 or len(neg) == 0:
        return None

    left = np.searchsorted(neg, pos, side="left")
    right = np.searchsorted(neg, pos, side="right")

    wins = left + 0.5 * (right - left)
    return float(np.mean(wins / len(neg)))


rng = np.random.default_rng(SEED)

indices = rng.permutation(len(queries))[:N_DEV + N_VAL]

X = []
y = []
recalls = []

start_time = time.perf_counter()

for i, qid in enumerate(indices):
    result = search_and_probe(queries[qid])
    if result is None:
        raise RuntimeError(f"Probe failed on query {qid}")

    features, predicted = result
    truth = set(int(x) for x in gt[qid, :10])

    recall = len(predicted & truth) / 10.0

    X.append(features)
    y.append(int(recall < 1.0))
    recalls.append(recall)

    if (i + 1) % 200 == 0:
        print(
            f"Processed {i+1}/{len(indices)} queries",
            flush=True
        )

y = np.asarray(y, dtype=np.int32)
recalls = np.asarray(recalls, dtype=np.float64)

dev = slice(0, N_DEV)
val = slice(N_DEV, N_DEV + N_VAL)

summary = {
    "experiment": "G0.2A surrogate feedback validation",
    "seed": SEED,
    "probe_expansions": PROBE_Q,
    "target_expansions": TARGET_Q,
    "dev_queries": N_DEV,
    "validation_queries": N_VAL,
    "surrogate_recall_at_10": float(recalls.mean()),
    "official_cpp_recall_reference_Q80": 0.98573,
    "dev_failure_rate": float(y[dev].mean()),
    "validation_failure_rate": float(y[val].mean()),
    "elapsed_seconds": time.perf_counter() - start_time,
    "features": {},
}

print("\n===== SURROGATE SANITY CHECK =====")
print(
    "Python surrogate Recall@10:",
    round(float(recalls.mean()), 6)
)
print("Official C++ Q80 reference: 0.98573")

difference = abs(float(recalls.mean()) - 0.98573)
print("Absolute Recall difference:", round(difference, 6))

if difference > 0.02:
    print(
        "WARNING: Surrogate differs substantially "
        "from C++ evaluator. Do not infer C++ results."
    )

print("\n===== FEEDBACK VALIDATION =====")
print(
    "Dev failure rate:",
    round(float(y[dev].mean()), 5)
)
print(
    "Validation failure rate:",
    round(float(y[val].mean()), 5)
)

for name in X[0]:
    values = np.array([x[name] for x in X])

    dev_auc = auc(values[dev], y[dev])

    if dev_auc is None:
        continue

    # Direction is selected on development only.
    sign = 1 if dev_auc >= 0.5 else -1

    validation_auc = auc(
        sign * values[val], y[val]
    )

    summary["features"][name] = {
        "direction": sign,
        "dev_auc_oriented": max(dev_auc, 1 - dev_auc),
        "validation_auc": validation_auc,
    }

    print(
        f"{name:18s} "
        f"DEV={max(dev_auc, 1-dev_auc):.4f} "
        f"VALIDATION={validation_auc}"
    )

OUT.mkdir(parents=True, exist_ok=True)

path = OUT / "feedback_validation.json"

path.write_text(
    json.dumps(summary, indent=2),
    encoding="utf-8"
)

print("\nSaved:", path)
print("G0.2A SURROGATE ANALYSIS COMPLETE")
