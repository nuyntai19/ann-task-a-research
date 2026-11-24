"""Make disjoint base-alias calibration and holdout queries with exact leave-one-out GT."""
import os
os.environ["OPENBLAS_NUM_THREADS"]="4"
os.environ["OMP_NUM_THREADS"]="4"

import json
from pathlib import Path
import struct
import sys
import time
import numpy as np


def main(base_path, out):
    start=time.perf_counter()
    base=np.memmap(base_path,dtype="<f4",mode="r",offset=8,shape=(1_000_000,128))
    for i in range(0,len(base),100_000):
        x=base[i:i+100_000]
        if not np.all(np.isfinite(x)&(x>=0)&(x<=255)&(x==np.floor(x))):
            raise ValueError("Exact float32 scoring requires integer vectors in [0,255]")
    rng=np.random.default_rng(662017)
    ids=rng.choice(len(base)-1,8192+1024+3072,replace=False)+1
    out.mkdir()
    np.savetxt(out/"selection.ids",ids[:8192],fmt="%d")
    norms=np.einsum("ij,ij->i",base,base)
    for name,query_ids in (("cal",ids[8192:9216]),("proxy",ids[9216:])):
        np.savetxt(out/(name+".ids"),query_ids,fmt="%d")
        neighbors=np.empty((len(query_ids),10),dtype="<u4")
        distances=np.empty((len(query_ids),10),dtype="<f4")
        for start_idx in range(0,len(query_ids),48):
            block=query_ids[start_idx:start_idx+48]
            d=base[block]@base.T
            d*=-2
            d+=norms
            d+=norms[block,None]
            d[np.arange(len(block)),block]=np.inf
            for j, row in enumerate(d):
                bound=np.partition(row[:16384],9)[9]
                eligible=np.flatnonzero(row<=bound)
                top=eligible[np.lexsort((eligible,row[eligible]))[:10]]
                truth=base[top].astype("i8")-base[block[j]].astype("i8")
                if block[j] in top or not np.array_equal(row[top],np.sum(truth*truth,axis=1)):
                    raise ValueError("Exact GT failed")
                neighbors[start_idx+j],distances[start_idx+j]=top,row[top]
        with (out/(name+".ibin")).open("xb") as f:
            f.write(struct.pack("<II",len(query_ids),10))
            neighbors.tofile(f)
            distances.tofile(f)
    report={"selection":8192,"calibration":1024,"holdout_proxy":3072,
            "sampling_seed":662017,"elapsed_s":time.perf_counter()-start,
            "gt":"exhaustive integer squared L2, self excluded by ID",
            "holdout_scope":"held-out base vectors, not an independent external distribution"}
    (out/"manifest.json").write_text(json.dumps(report,indent=2)+"\n")


if __name__=="__main__":
    main(*map(Path,sys.argv[1:]))
