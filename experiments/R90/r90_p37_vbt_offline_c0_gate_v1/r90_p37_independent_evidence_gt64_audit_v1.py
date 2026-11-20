#!/usr/bin/env python3
"""R90-P3.7 read-only independent *evidence and sampled GT* audit.

Does NOT reimplement partition/seam/Top2; this archive lacks tile IDs and join
edge lists, so cannot independently verify its C0 numerators. Does check the
archive/manifest/CSV/NPZ, data SHA, 72-row consistency, and independently
recalculate selected anchors' base-to-base top10 using float64 distances.

Usage:
  python3 THIS.py --selftest
  python3 THIS.py --archive "$HOME/R90_P37_EVIDENCE_v1.tar.gz" \
      --base "$HOME/ann-task-a/data/sift100k.fbin" --sample 128
"""
from __future__ import annotations
import argparse, csv, hashlib, io, json, math, pathlib, struct, tarfile
import numpy as np

EXPECTED_TAR_SHA = '43cc4bcf7bf7b6ad43f5967c160d98a38acd2183aa4dc57d768b37777cc5fec9'
EXPECTED_BASE_SHA = 'e50ff1bc34bcc6d1c97dd001023c09a666971cde64605cc06671ed8a8ff1ed12'
EXPECTED_SCRIPT_SHA = '7090021f62af082abe38fa3cca54492cc0afebf589caea57dc914532baabb4cf'
EXPECTED_FILES = {'result_manifest.json', 'offline_arms.csv', 'eval_qids_and_gt10.npz'}

def h_bytes(b): return hashlib.sha256(b).hexdigest()
def h_file(p):
    h=hashlib.sha256()
    with pathlib.Path(p).open('rb') as f:
        for b in iter(lambda:f.read(4<<20),b''):h.update(b)
    return h.hexdigest()
def nh(a):return h_bytes(np.asarray(a).tobytes(order='C'))
def check(x,s):
    if not x:raise RuntimeError('HOLD_'+s)

def read_bundle(path):
    print('ARCHIVE_SHA256',h_file(path),flush=True)
    check(h_file(path)==EXPECTED_TAR_SHA,'ARCHIVE_SHA_MISMATCH')
    with tarfile.open(path,'r:gz') as f:
        names=[m.name for m in f.getmembers()]
        check(len(names)==3 and set(names)==EXPECTED_FILES,'ARCHIVE_MEMBERS')
        for m in f.getmembers():check(m.isfile() and m.size<100*1024*1024,'ARCHIVE_MEMBER_TYPE_OR_SIZE')
        files={name:f.extractfile(name).read() for name in names}
    manifest=json.loads(files['result_manifest.json'])
    check(manifest['base_sha']==EXPECTED_BASE_SHA,'MANIFEST_BASE_SHA')
    check(manifest['rows']==72 and len(manifest['cases'])==6,'MANIFEST_COUNTS')
    check(manifest['csv_sha']==h_bytes(files['offline_arms.csv']),'CSV_SHA')
    check(manifest['eval_npz_sha']==h_bytes(files['eval_qids_and_gt10.npz']),'GT_NPZ_SHA')
    with np.load(io.BytesIO(files['eval_qids_and_gt10.npz']),allow_pickle=False) as a:
        qids=np.array(a['qids']);gt=np.array(a['gt10']);base_sha=str(a['base_sha'].item())
    check(base_sha==EXPECTED_BASE_SHA,'NPZ_BASE_SHA')
    check(qids.shape==(2000,) and gt.shape==(2000,10),'NPZ_SHAPE')
    check(np.array_equal(np.sort(qids),qids),'QIDS_ORDER')
    check(np.unique(qids).size==2000,'QIDS_UNIQUE')
    check(np.all((gt>=0)&(gt<100000)) and np.all(gt!=qids[:,None]),'GT_IDS')
    check(np.all([np.unique(r).size==10 for r in gt]),'GT_UNIQUE_ROW')
    check(nh(qids)==manifest['eval_qids_sha'],'QIDS_ARRAY_SHA')
    check(nh(gt)==manifest['eval_gt10_sha'],'GT_ARRAY_SHA')
    rows=list(csv.DictReader(io.StringIO(files['offline_arms.csv'].decode('utf-8'))))
    check(len(rows)==72,'CSV_ROW_COUNT')
    keyset=set()
    for r in rows:
        key=(int(r['seed']),r['center_mode'],int(r['kb']),r['control'])
        check(key not in keyset,'DUPLICATE_CASE');keyset.add(key)
        check(key[0] in (555,556,557) and key[1] in ('random','sample1pct_kmeans') and key[2] in (8,12,16,20) and key[3] in ('seam','center_topk','center_workmatched'),'INVALID_ARM')
        n=int(r['exact_top10_total'])
        raw=int(r['raw_hits']);post=int(r['post_top2_hits'])
        check(n==20000 and 0<=post<=raw<=n,'INVALID_HITS')
        check(abs(raw/n-float(r['raw_C0']))<1e-7,'RAW_C0_RATIO')
        check(abs(post/n-float(r['post_top2_C0']))<1e-7,'POST_C0_RATIO')
        check(int(r['max_tile'])<=256,'TILE_LIMIT')
    print('EVIDENCE_MANIFEST_CSV_NPZ_SHA_AND_72_ARM_PASS',flush=True)
    print('GT_ORIGINAL_SHA',manifest['eval_gt10_sha'],'QUERY_IDS_SHA',manifest['eval_qids_sha'],flush=True)
    return qids,gt,rows

def exact64_gt_sample(base,qids,gt,sample=128,seed=451937):
    check(pathlib.Path(base).is_file(),'BASE_FILE_MISSING')
    check(h_file(base)==EXPECTED_BASE_SHA,'BASE_INPUT_SHA')
    with pathlib.Path(base).open('rb') as f: n,d=struct.unpack('<II',f.read(8))
    check((n,d)==(100000,128),'BASE_INPUT_SHAPE')
    check(pathlib.Path(base).stat().st_size==8+4*n*d,'BASE_INPUT_BYTES')
    x=np.memmap(base,mode='r',dtype='<f4',offset=8,shape=(n,d))
    x64=np.array(x,dtype=np.float64,order='C')
    norms=np.einsum('ij,ij->i',x64,x64,dtype=np.float64)
    rng=np.random.default_rng(seed)
    chosen=np.sort(rng.choice(len(qids),size=min(sample,len(qids)),replace=False))
    all_ids=np.arange(n)
    differences=[];order_differences=[]
    for s in range(0,len(chosen),8):
        ix=chosen[s:s+8]
        query_ids=qids[ix]
        dist=norms[None,:]+norms[query_ids,None]-2*(x64[query_ids]@x64.T)
        np.maximum(dist,0,out=dist)
        dist[np.arange(len(query_ids)),query_ids]=np.inf
        for j,r in enumerate(ix):
            # Independently derive top10 by float64, tie-break ascending ID.
            row=dist[j]
            arg=np.argpartition(row,9)[:10]
            threshold=float(np.max(row[arg]))
            candidates=np.flatnonzero(row<=threshold)
            top=candidates[np.lexsort((candidates,row[candidates]))][:10]
            old=gt[r]
            if set(top.tolist())!=set(old.tolist()):
                differences.append({'q_id':int(query_ids[j]),'gt_fp32':old.tolist(),'gt_fp64':top.tolist(),'overlap':len(set(top.tolist())&set(old.tolist()))})
            elif not np.array_equal(top,old):
                order_differences.append(int(query_ids[j]))
    print('FP64_INDEPENDENT_CHECKED_ANCHORS',len(chosen),flush=True)
    print('GT10_SET_MISMATCH_ANCHORS',len(differences),flush=True)
    print('GT10_ORDER_ONLY_DIFFERENCES',len(order_differences),flush=True)
    for d in differences[:8]:print('GT_DISAGREEMENT',json.dumps(d,separators=(',',':')),flush=True)
    if differences:
        print('RESULT_HOLD_GT_FP32_VS_FP64_NOT_IDENTICAL__REASSESS_C0_GT',flush=True)
    else:
        print('RESULT_PASS_SAMPLED_GT_FP64_SET_CONSISTENCY__NOT_FULL_2000_PROOF',flush=True)
    print('C0_INDEPENDENT_RECOMPUTE_NOT_POSSIBLE_FROM_3FILE_ARCHIVE__TILE_MAP_AND_JOIN_EDGES_NOT_EXPORTED',flush=True)

def selftest():
    x=np.array([[0,0],[1,0],[2,0],[3,0],[4,0]],dtype=np.float64)
    d=np.sum((x-x[0])**2,axis=1);d[0]=np.inf
    res=np.argsort(d,kind='stable')[:2]
    check(res.tolist()==[1,2],'INDEPENDENT_GT_TOY')
    print('R90_P37_INDEPENDENT_GT64_AUDIT_SELFTEST_PASS',flush=True)

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--archive',default=str(pathlib.Path.home()/'R90_P37_EVIDENCE_v1.tar.gz'))
    p.add_argument('--base',default=str(pathlib.Path.home()/'ann-task-a/data/sift100k.fbin'))
    p.add_argument('--sample',type=int,default=128)
    p.add_argument('--selftest',action='store_true')
    args=p.parse_args()
    if args.selftest:selftest();return
    check(1<=args.sample<=2000,'SAMPLE_COUNT')
    qids,gt,rows=read_bundle(args.archive)
    exact64_gt_sample(args.base,qids,gt,args.sample)
if __name__=='__main__':main()
