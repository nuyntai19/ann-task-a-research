#!/usr/bin/env python3
"""Download only official first 10M Microsoft Turing-ANNS prefix + matching GT.

--preflight: READ ONLY local 1M pin, resource & destination checks.
--download: resumable HTTP-Range GET of 4,000,000,008-byte base1b.fbin prefix
            and 80,000,008-byte official GT for first 10M.

Never downloads 50M/100M, never launches native BUILD. Range response must be
206 Partial Content with EXACT Content-Range: a server accidentally returning
200 (full ~400GB 1B download) is a FAIL BEFORE reading the body. Existing
final files are never overwritten. Verify that 10M prefix matches exact pinned
1M vector bytes (excluding header), verify GT ID bounds and record fresh SHA.
Official source: BigANN Benchmarks / MSTuringANNS, subset GT msturing-gt-10M.
No preknown SHA for 10M is asserted; recorded SHA is generated from download.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import struct
import sys
import urllib.request
import urllib.error
sys.dont_write_bytecode=True

ROOT=Path.home()/"ann-task-a"
DEST=ROOT/"data/MSTuring_10M_v1"
SRC=ROOT/"data/MSTuring_1M_v1"
BASE1=SRC/"base.1M.fbin"
QUERY1=SRC/"query.public.100K.fbin"
BASE_SHA_1M="44e83e1dd4c65999b75873101adc5ac06ca900d259a2befd05c2c3aa28ff4042"
QUERY_SHA_1M="48d087a17bec15a5ec9ea526fe9bd14ac31bbbb5cd200817b341adbb77695644"
BASE_OUT=DEST/"base.10M.fbin"
GT_OUT=DEST/"groundtruth.public.100K.ibin"
QUERY_OUT=DEST/"query.public.100K.fbin"
BASE_TOTAL=4_000_000_008
GT_TOTAL=80_000_008
QUERY_TOTAL=40_000_008
N=10_000_000
D=100
Q=100_000
K=100
REMOTE="https://comp21storage.z5.web.core.windows.net/comp21/MSFT-TURING-ANNS/"
BASE_URL=REMOTE+"base1b.fbin"
GT_URL=REMOTE+"msturing-gt-10M"
BLOCK=64<<20

def hold(s): raise RuntimeError("R86_MSTURING10M_DATA_HOLD "+s)
def sha(path, offset=0, limit=None):
    h=hashlib.sha256()
    with path.open('rb') as f:
        f.seek(offset)
        while True:
            todo=4<<20 if limit is None else min(4<<20,limit)
            if todo<=0: break
            b=f.read(todo)
            if not b: break
            h.update(b)
            if limit is not None: limit-=len(b)
    if limit is not None and limit>0: hold('PREFIX_NOT_LONG_ENOUGH '+str(path))
    return h.hexdigest()

def header_and_length(path, size, shape):
    if not path.is_file() or path.stat().st_size != size: hold('FILE_LENGTH_MISMATCH '+str(path))
    with path.open('rb') as f:
        try: hdr=struct.unpack('<II',f.read(8))
        except struct.error: hold('HEADER_TRUNCATED '+str(path))
    if hdr!=shape: hold('HEADER_SHAPE_MISMATCH '+str(path)+' '+str(hdr)+' want '+str(shape))

def available():
    if not ROOT.is_dir(): hold('ROOT_MISSING '+str(ROOT))
    header_and_length(BASE1,400000008,(1000000,100))
    header_and_length(QUERY1,QUERY_TOTAL,(Q,D))
    if sha(BASE1)!=BASE_SHA_1M or sha(QUERY1)!=QUERY_SHA_1M: hold('ANCHOR_1M_SHA_MISMATCH')
    free=shutil.disk_usage(ROOT).free/1024**3
    if free<12: hold(f'FREE_DISK_LT_12_GIB actual={free:.2f}')
    if DEST.exists() and not DEST.is_dir(): hold('DEST_NOT_DIRECTORY')
    # Never claim 10M full dataset validity from a 1M dataset proof.
    print(f'R86_10M_DATA_PREFLIGHT_ANCHOR_SHA_PASS free_gib={free:.2f}',flush=True)

def get_chunk(url, partial_path, total):
    if partial_path.exists() and not partial_path.is_file(): hold('PARTIAL_PATH_BAD_TYPE')
    offset=partial_path.stat().st_size if partial_path.exists() else 0
    if offset>total: hold('PARTIAL_FILE_TOO_LARGE')
    while offset<total:
        end=min(total,offset+BLOCK)-1
        request=urllib.request.Request(url,headers={"Range":f"bytes={offset}-{end}","Accept-Encoding":"identity","User-Agent":"R86-Turing-ANNS-Range-Subset-v1"})
        with urllib.request.urlopen(request,timeout=120) as response:
            status=response.status
            content_range=(response.headers.get('Content-Range') or '').strip()
            expected_start=f'bytes {offset}-{end}/'
            if status != 206 or not content_range.startswith(expected_start):
                hold(f'HTTP_RANGE_NOT_HONORED code={status} content_range={content_range!r}; stop to avoid full 1B download')
            expected=end-offset+1
            claimed=response.headers.get('Content-Length')
            if claimed is not None and int(claimed)!=expected: hold('HTTP_CONTENT_LENGTH_BAD')
            with partial_path.open('ab') as out:
                left=expected
                while left:
                    data=response.read(min(4<<20,left))
                    if not data: hold('HTTP_TRUNCATED_CHUNK_PARTIAL_RESUMABLE')
                    out.write(data)
                    left-=len(data)
                out.flush();os.fsync(out.fileno())
        offset=end+1
        print(f'R86_10M_DATA_RANGE_CHUNK_PASS written={offset} total={total}',flush=True)
    if partial_path.stat().st_size!=total: hold('FINAL_PARTIAL_LENGTH_MISMATCH')

def link_final_if_valid(part,out,size,shape):
    if out.exists():
        header_and_length(out,size,shape)
        print('R86_10M_EXISTING_FILE_PRESERVED '+str(out),flush=True)
        return
    # Atomic hard link creation fails if final exists; staged part preserved until final.
    os.link(part,out)
    print('R86_10M_FINAL_EXCLUSIVE_FILE_CREATED '+str(out),flush=True)
    part.unlink()

def verify_prefix(part):
    if part.stat().st_size!=BASE_TOTAL: hold('BASE_PREFIX_LENGTH_FAILED')
    with part.open('rb') as f: n,d=struct.unpack('<II',f.read(8))
    if d!=100 or n<10_000_000: hold(f'ORIGINAL_SOURCE_HEADER_UNEXPECTED count={n} dims={d}')
    # Compare exact original float bytes, not 10M synthetic replication of 1M.
    len_payload=400000000
    a=sha(BASE1,8,len_payload)
    b=sha(part,8,len_payload)
    if a!=b: hold('10M_BASE_PREFIX_DIFFERS_FROM_EXISTING_SHA_PINNED_1M_BASE')
    print('R86_10M_FIRST_1M_VECTOR_PAYLOAD_EXACT_MATCH_PASS',flush=True)
    with part.open('r+b') as f:
        f.seek(0);f.write(struct.pack('<II',N,D));f.flush();os.fsync(f.fileno())
    header_and_length(part,BASE_TOTAL,(N,D))

def verify_gt(part):
    header_and_length(part,GT_TOTAL,(Q,K))
    # Streaming 10M uint32 ids, no 80MB in-memory array.
    minid,maxid=N,0
    with part.open('rb') as f:
        f.seek(8)
        left=Q*K
        while left:
            count=min(200000,left)
            data=f.read(count*4)
            if len(data)!=count*4: hold('GT_IDS_TRUNCATED')
            ids=struct.iter_unpack('<i',data)
            for (v,) in ids:
                if v<0 or v>=N: hold(f'GT_ID_OUT_OF_RANGE id={v} n={N}')
                if v<minid:minid=v
                if v>maxid:maxid=v
            left-=count
    print(f'R86_10M_GT_ALL_IDS_RANGE_PASS min={minid} max={maxid} count={Q*K}',flush=True)

def acquisition():
    available()
    DEST.mkdir(parents=True,exist_ok=True)
    # If already valid base/GT, verify but do not redownload/overwrite.
    bp=BASE_OUT.with_suffix(BASE_OUT.suffix+'.part')
    gp=GT_OUT.with_suffix(GT_OUT.suffix+'.part')
    if not BASE_OUT.is_file():
        get_chunk(BASE_URL,bp,BASE_TOTAL)
        verify_prefix(bp)
        link_final_if_valid(bp,BASE_OUT,BASE_TOTAL,(N,D))
    header_and_length(BASE_OUT,BASE_TOTAL,(N,D))
    if sha(BASE_OUT,8,400000000)!=sha(BASE1,8,400000000): hold('EXISTING_10M_BASE_PREFIX_ANCHOR_MISMATCH')
    if not GT_OUT.is_file():
        get_chunk(GT_URL,gp,GT_TOTAL)
        verify_gt(gp)
        link_final_if_valid(gp,GT_OUT,GT_TOTAL,(Q,K))
    header_and_length(GT_OUT,GT_TOTAL,(Q,K))
    verify_gt(GT_OUT)
    if not QUERY_OUT.is_file():
        with QUERY_OUT.open('xb') as out,QUERY1.open('rb') as src:
            shutil.copyfileobj(src,out,4<<20)
    header_and_length(QUERY_OUT,QUERY_TOTAL,(Q,D))
    if sha(QUERY_OUT)!=QUERY_SHA_1M: hold('COPY_QUERY_SHA_MISMATCH')
    manifest=DEST/'dataset_manifest.json'
    vals=dict(dataset='Microsoft Turing-ANNS official prefix first 10M',n=N,d=D,query_count=Q,gt_k=K,
         source_base=BASE_URL,source_gt=GT_URL,
         base_sha256=sha(BASE_OUT),query_sha256=sha(QUERY_OUT),gt_sha256=sha(GT_OUT),
         prefix_payload_matches_sha_pinned_1m=True,gt_id_bounds_pass=True,
         note='Only download+schema/range check, NOT full top100 exact GT spotcheck and NOT 10M PiPNN build authorization; 50M GT not provided by official standard subsets.')
    if manifest.exists():
        if json.loads(manifest.read_text())!=vals: hold('EXISTING_MANIFEST_MISMATCH')
    else:
        with manifest.open('x',encoding='utf-8') as f:
            json.dump(vals,f,indent=2,sort_keys=True);f.write('\n')
    print(f'R86_10M_DATA_ACQUIRED_SHA_PINNED_GT_ID_RANGE_PASS base_sha={vals["base_sha256"]} gt_sha={vals["gt_sha256"]}',flush=True)
    print('R86_10M_NATIVE_BUILD_NOT_RUN_MEM_RESOURCE_PILOT_REQUIRED',flush=True)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    t=p.add_mutually_exclusive_group(required=True)
    t.add_argument('--preflight',action='store_true');t.add_argument('--download',action='store_true')
    a=p.parse_args()
    if a.preflight: available();print('R86_10M_DATA_PREFLIGHT_PASS_NO_WRITES',flush=True)
    else: acquisition()
    return 0

if __name__=='__main__':
    try:raise SystemExit(main())
    except (RuntimeError,OSError,ValueError,urllib.error.URLError) as e:
        print(str(e),file=sys.stderr,flush=True);raise SystemExit(2)
