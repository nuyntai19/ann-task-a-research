import argparse
import time

import h5py
import hnswlib
import numpy as np

parser = argparse.ArgumentParser()
parser.add_argument(
    "--threads",
    type=int,
    choices=[1, 2, 4, 8],
    required=True
)
args = parser.parse_args()

with h5py.File(
    "data/sift-128-euclidean.hdf5", "r"
) as f:
    base = f["train"][:]

assert base.shape == (1_000_000, 128)
assert base.dtype == np.float32

index = hnswlib.Index(
    space="l2",
    dim=128
)

index.init_index(
    max_elements=len(base),
    M=16,
    ef_construction=100,
    random_seed=42
)

print(
    f"BEGIN BUILD | threads={args.threads}",
    flush=True
)

start = time.perf_counter()

index.add_items(
    base,
    num_threads=args.threads
)

elapsed = time.perf_counter() - start

assert index.get_current_count() == 1_000_000

print(
    f"END BUILD | "
    f"threads={args.threads} | "
    f"seconds={elapsed:.4f}",
    flush=True
)
