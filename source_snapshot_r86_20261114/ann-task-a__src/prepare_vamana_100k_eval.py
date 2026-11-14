import struct
from pathlib import Path

import h5py
import numpy as np
from scipy.spatial.distance import cdist

root = Path.home() / "ann-task-a"
n = 100_000
q = 300
k = 100

with h5py.File(root / "data/sift-128-euclidean.hdf5", "r") as f:
    base = f["train"][:n]
    queries = f["test"][:q]

query_path = root / "data/sift100k_queries_300.fbin"
gt_path = root / "data/sift100k_gt300.ibin"

with query_path.open("wb") as out:
    out.write(struct.pack("<II", q, 128))
    out.write(
        np.asarray(queries, dtype="<f4").tobytes()
    )

ids = np.empty((q, k), dtype="<u4")
distances = np.empty((q, k), dtype="<f4")

print("Computing exact SIFT100K ground truth...", flush=True)

for start in range(0, q, 10):
    end = min(start + 10, q)

    d = cdist(
        queries[start:end],
        base,
        metric="sqeuclidean"
    )

    top = np.argpartition(
        d, kth=k-1, axis=1
    )[:, :k]

    values = np.take_along_axis(d, top, axis=1)
    order = np.argsort(values, axis=1, kind="stable")

    ids[start:end] = np.take_along_axis(
        top, order, axis=1
    )
    distances[start:end] = np.take_along_axis(
        values, order, axis=1
    )

with gt_path.open("wb") as out:
    out.write(struct.pack("<II", q, k))
    out.write(ids.tobytes())
    out.write(distances.tobytes())

print("Queries:", query_path)
print("Ground truth:", gt_path)
print("Completed successfully")
