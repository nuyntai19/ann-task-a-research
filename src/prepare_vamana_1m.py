import struct
from pathlib import Path

import h5py
import numpy as np

root = Path.home() / "ann-task-a"
source = root / "data/sift-128-euclidean.hdf5"

with h5py.File(source, "r") as f:
    for key, filename in [
        ("train", "sift1m.fbin"),
        ("test", "sift1m_queries.fbin"),
    ]:
        dataset = f[key]
        n, dim = dataset.shape
        path = root / "data" / filename

        with path.open("wb") as out:
            out.write(struct.pack("<II", n, dim))

            for start in range(0, n, 10000):
                end = min(start + 10000, n)
                block = np.asarray(
                    dataset[start:end],
                    dtype="<f4",
                    order="C"
                )
                out.write(block.tobytes())

        print(filename, n, dim, path.stat().st_size)

    ids = np.asarray(f["neighbors"][:], dtype="<u4")
    distances = np.asarray(f["distances"][:], dtype="<f4")

    assert ids.shape == distances.shape
    assert ids.min() >= 0
    assert ids.max() < f["train"].shape[0]

    gt_path = root / "data/sift1m_gt.ibin"

    with gt_path.open("wb") as out:
        out.write(struct.pack("<II", *ids.shape))
        out.write(ids.tobytes())
        out.write(distances.tobytes())

    print("Ground truth:", ids.shape)
    print("Completed successfully")
