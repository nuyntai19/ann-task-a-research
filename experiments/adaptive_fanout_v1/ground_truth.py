"""Read provided SIFT GT and convert it to the native PiPNN representation."""
from pathlib import Path
import struct

import numpy as np


def load_gt_ids(path, source_query_count, base_count):
    path = Path(path)
    if path.suffix == ".ivecs":
        if path.stat().st_size < 4 or path.stat().st_size % 4:
            raise ValueError(f"Invalid ivecs ground truth size: {path}")
        raw = np.memmap(path, dtype="<i4", mode="r")
        width = int(raw[0])
        if width < 10 or width > base_count or raw.size % (width + 1):
            raise ValueError(f"Invalid ivecs ground truth width/size: {path}")
        rows = raw.reshape(-1, width + 1)
        if len(rows) != source_query_count or not np.all(rows[:, 0] == width):
            raise ValueError(f"Ground truth row count/width differs from source queries: {path}")
        ids = rows[:, 1:]
    elif path.suffix == ".ibin":
        with path.open("rb") as stream:
            header = stream.read(8)
        if len(header) != 8:
            raise ValueError(f"Truncated ground truth header: {path}")
        rows, width = struct.unpack("<II", header)
        if rows != source_query_count or not 10 <= width <= base_count:
            raise ValueError(f"Ground truth shape differs from source dataset: {path}")
        if path.stat().st_size not in (8 + rows * width * 4, 8 + rows * width * 8):
            raise ValueError(f"Invalid ibin ground truth size: {path}")
        ids = np.memmap(path, dtype="<u4", mode="r", offset=8, shape=(rows, width))
    else:
        raise ValueError(f"Unsupported ground truth format: {path}")
    if np.any(ids < 0) or np.any(ids >= base_count):
        raise ValueError(f"Ground truth has IDs outside the base dataset: {path}")
    return ids


def reuse_gt(base, queries, provided_ids):
    if len(queries) > len(provided_ids):
        raise ValueError("Not enough provided ground truth rows")
    width = min(100, provided_ids.shape[1])
    ids = np.array(provided_ids[:len(queries), :width], dtype="<u4")
    if np.any(np.diff(np.sort(ids, axis=1), axis=1) == 0):
        raise ValueError("Ground truth has duplicate neighbor IDs")
    distances = np.empty(ids.shape, dtype="<f4")
    # Compute only the distances to the known neighbor IDs (100/query), not
    # distances to the complete million-vector base. Bound temporary RAM.
    for start in range(0, len(queries), 32):
        end = min(start + 32, len(queries))
        delta = (np.asarray(base[ids[start:end]], dtype=np.float64)
                 - np.asarray(queries[start:end], dtype=np.float64)[:, None, :])
        values = np.einsum("qkd,qkd->qk", delta, delta)
        if not np.isfinite(values).all() or np.any(np.diff(values, axis=1) < 0):
            raise ValueError("Provided ground truth is not distance-sorted for these base/query vectors")
        distances[start:end] = values
    # Check only three queries against the full base to catch mismatched files
    # or query order. Keep the full-GT validation explicitly sample-based.
    checked = sorted({0, len(queries) // 2, len(queries) - 1})
    for q in checked:
        all_distances = np.empty(len(base), dtype=np.float64)
        query = np.asarray(queries[q], dtype=np.float64)
        for start in range(0, len(base), 8192):
            end = min(start + 8192, len(base))
            delta = np.asarray(base[start:end], dtype=np.float64) - query
            all_distances[start:end] = np.einsum("ij,ij->i", delta, delta)
        threshold = np.partition(all_distances, width - 1)[width - 1]
        required = np.flatnonzero(all_distances < threshold)
        if (np.any(all_distances[ids[q]] > threshold)
                or not np.isin(required, ids[q]).all()):
            raise ValueError(f"Provided ground truth does not match full base/query at query {q}")
    return ids, distances, {"exact_sample_queries": checked,
                            "all_query_neighbor_distances_sorted": True,
                            "validation_scope": "sample-based; not a full GT recertification"}
