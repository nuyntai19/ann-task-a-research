"""Generate exact, self-excluded SIFT1M calibration queries from the base."""
import os
os.environ["OPENBLAS_NUM_THREADS"] = "4"
os.environ["OMP_NUM_THREADS"] = "4"

import argparse
import json
from pathlib import Path
import struct
import time

import numpy as np


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    begin = time.perf_counter()
    with args.base.open("rb") as f:
        n, d = struct.unpack("<II", f.read(8))
    if (n, d) != (1_000_000, 128):
        raise ValueError("Expected SIFT1M")
    base = np.memmap(args.base, dtype="<f4", mode="r", offset=8, shape=(n,d))
    # Integers in [0,255] make both dot products and squared-distance
    # intermediates exactly representable in float32 for dimension 128.
    for i in range(0,n,100_000):
        tile = base[i:i+100_000]
        if not np.all(np.isfinite(tile) & (tile >= 0) & (tile <= 255) & (tile == np.floor(tile))):
            raise ValueError("Unsupported SIFT coordinates")
    rng = np.random.default_rng(20261123)
    ids = rng.choice(n-1, 1536, replace=False) + 1
    norms = np.einsum("ij,ij->i", base, base)
    with args.output.open("x") as out:
        for start in range(0,len(ids),32):
            selected = ids[start:start+32]
            q = base[selected]
            scores = q @ base.T
            scores *= -2
            scores += norms
            scores += norms[selected,None]
            scores[np.arange(len(selected)),selected] = np.inf
            for j, (qid, ds) in enumerate(zip(selected,scores)):
                shortlist = np.argpartition(ds, 9)[:10]
                kth = ds[shortlist].max()
                possible = np.flatnonzero(ds <= kth)
                order = np.lexsort((possible,ds[possible]))
                top = possible[order[:10]]
                exact = base[top].astype("i8") - base[qid].astype("i8")
                if qid in top or not np.array_equal(np.sum(exact**2,axis=1),ds[top]):
                    raise ValueError("Exact distance validation failed")
                split = int(start+j >= 1024)
                out.write(" ".join(map(str,[split,int(qid),int(kth),*top]))+"\n")
    record = {"base_shape":[n,d],"mine_queries":1024,"verify_queries":512,
              "seed":20261123,"ground_truth":"float32 exact integer GEMM; ties accepted at exact kth radius",
              "elapsed_seconds":time.perf_counter()-begin}
    args.output.with_suffix(".json").write_text(json.dumps(record,indent=2)+"\n")


if __name__ == "__main__":
    main()
