#!/usr/bin/env python3
"""Fail-closed MS-Turing ANNS 1M dataset acquisition and read-only validation.

Official benchmark provenance:
  https://github.com/harsha-simhadri/big-ann-benchmarks/blob/main/benchmark/datasets.py
  https://github.com/unum-cloud/usearch/blob/main/BENCHMARKS.md

Modes (choose exactly one): --probe, --download, --verify.
--probe makes tiny HTTP range requests and writes nothing.
--download fetches only 400,000,008 bytes from the 1B source, then patches the
  leading n=1,000,000 in its own new copy, and downloads query/GT exactly.
--verify hashes the 3 files, confirms (1000000,100) and (100000,100), checks
  GT split [ids:u32][distances:f32] and brute-forces 3 sample queries.
Never touches SIFT files or R85/R86 graph evidence; never overwrites output.
"""
from __future__ import annotations
import argparse, hashlib, json, math, os, re, shutil, struct, sys
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

BASE_URL = 'https://comp21storage.z5.web.core.windows.net/comp21/MSFT-TURING-ANNS/'
SPEC = {
 'base': ('base1b.fbin', 'base.1M.fbin', 8 + 1_000_000*100*4),
 'queries': ('query100K.fbin', 'query.public.100K.fbin', 8 + 100_000*100*4),
 'gt': ('msturing-gt-1M', 'groundtruth.public.100K.ibin', 8 + 100_000*100*8),
}
SRC_N, N, D, Q, K = 1_000_000_000, 1_000_000, 100, 100_000, 100
CHUNK=4<<20


def need(cond, msg):
 if not cond: raise RuntimeError(msg)

def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(CHUNK),b''):h.update(b)
 return h.hexdigest()

def url_for(key):return BASE_URL+SPEC[key][0]

def probe_one(key):
 url=url_for(key)
 req=Request(url,headers={'Range':'bytes=0-7','Accept-Encoding':'identity','User-Agent':'R86-research-dataset-gate/1.0'})
 with urlopen(req,timeout=35) as resp:
  status=resp.status
  cr=resp.headers.get('Content-Range','')
  data=resp.read(8)
  need(len(data)==8, f'{key}_REMOTE_TOO_SHORT')
  if key=='base':
   need(status==206 and re.fullmatch(r'bytes 0-7/\d+',cr),f'BASE_REMOTE_NO_RANGE_206 status={status} content_range={cr!r}')
  need(status in (200,206),f'{key}_REMOTE_STATUS_{status}')
  h=struct.unpack('<II',data)
  want=(SRC_N,D) if key=='base' else (Q,D) if key=='queries' else (Q,K)
  need(h==want,f'{key}_REMOTE_HEADER_HOLD got={h} expected={want}')
  print(f'PROBE_{key.upper()}_PASS status={status} header={h} range={cr or "none"} url={url}',flush=True)


def check_disk(dst):
 need(dst.parent.is_dir(),f'PARENT_DIR_NOT_FOUND {dst.parent}')
 free=shutil.disk_usage(dst.parent).free
 need(free>=int(1.6*1024**3),f'AVAILABLE_DISK_HOLD free={free} minimum=1.6GiB')
 print(f'DISK_FREE_GIB={free/1024**3:.2f}',flush=True)


def download_one(key,dst):
 src,filename,size=SPEC[key]; final=dst/filename
 if final.exists():
  check_header_size(key,final)
  print(f'SKIP_EXISTING_VERIFIED_SHAPE_{key.upper()} file={final} sha256={sha(final)}',flush=True)
  return
 part=dst/(filename+'.part')
 need(not part.exists(),f'PARTIAL_FILE_EXISTS_STOP_NO_DELETE {part}')
 end=size-1
 req=Request(url_for(key),headers={'Range':f'bytes=0-{end}','Accept-Encoding':'identity','User-Agent':'R86-research-dataset-gate/1.0'})
 with urlopen(req,timeout=60) as resp:
  cr=resp.headers.get('Content-Range','')
  expected_prefix=f'bytes 0-{end}/'
  need(resp.status==206 and cr.startswith(expected_prefix),
       f'{key}_RANGE_HOLD status={resp.status} content_range={cr!r}; REFUSE_FULL_DOWNLOAD')
  received=0
  try:
   # Exclusive-create: never overwrite an existing partial file.
   with part.open('xb') as f:
    while True:
     buf=resp.read(CHUNK)
     if not buf:break
     received+=len(buf)
     need(received<=size,f'{key}_DOWNLOAD_EXCEEDED_EXPECTED_BYTES')
     f.write(buf)
    f.flush();os.fsync(f.fileno())
   need(received==size,f'{key}_DOWNLOAD_SHORT got={received} want={size}')
   with part.open('r+b') as f:
    head=f.read(8)
    got=struct.unpack('<II',head)
    want=(SRC_N,D) if key=='base' else (Q,D) if key=='queries' else (Q,K)
    need(got==want,f'{key}_DOWNLOAD_HEADER_HOLD got={got} expected={want}')
    if key=='base':
     f.seek(0);f.write(struct.pack('<I',N));f.flush();os.fsync(f.fileno())
   need(not final.exists(),f'{key}_FINAL_APPEARED_DURING_DOWNLOAD_NO_OVERWRITE')
   part.rename(final)
   check_header_size(key,final)
  except Exception:
   # Retain partial for inspection; next run refuses to overwrite it.
   raise
 print(f'DOWNLOAD_{key.upper()}_PASS bytes={size} sha256={sha(final)} file={final}',flush=True)


def check_header_size(key,p):
 n,d=(N,D) if key=='base' else (Q,D) if key=='queries' else (Q,K)
 need(p.is_file(),f'{key}_FILE_MISSING {p}')
 need(p.stat().st_size==SPEC[key][2],f'{key}_SIZE_HOLD actual={p.stat().st_size} expected={SPEC[key][2]}')
 with p.open('rb') as f: got=struct.unpack('<II',f.read(8))
 need(got==(n,d),f'{key}_HEADER_HOLD got={got} wanted={(n,d)}')
 print(f'SHAPE_{key.upper()}_PASS shape={(n,d)} bytes={p.stat().st_size}',flush=True)


def verify(dst,spots=3):
 import numpy as np
 for key in SPEC: check_header_size(key,dst/SPEC[key][1])
 bas=dst/SPEC['base'][1];qry=dst/SPEC['queries'][1];gt=dst/SPEC['gt'][1]
 hashes={k:sha(dst/v[1]) for k,v in SPEC.items()}
 for k,v in hashes.items():print(f'SHA_{k.upper()}={v}',flush=True)
 X=np.memmap(bas,dtype='<f4',mode='r',offset=8,shape=(N,D))
 Y=np.memmap(qry,dtype='<f4',mode='r',offset=8,shape=(Q,D))
 IDs=np.memmap(gt,dtype='<u4',mode='r',offset=8,shape=(Q,K))
 DIST=np.memmap(gt,dtype='<f4',mode='r',offset=8+4*Q*K,shape=(Q,K))
 mi,ma=int(IDs.min()),int(IDs.max())
 need(0<=mi<=ma<N,f'GT_ID_RANGE_HOLD min={mi} max={ma}')
 need(bool(np.isfinite(DIST).all() and (DIST>=0).all()),'GT_DISTANCES_INVALID')
 need(not np.any(np.diff(DIST,axis=1)<-1e-4),'GT_NOT_SORTED_BY_DISTANCE')
 print(f'GT_LAYOUT_IDS_AND_FLOAT_DIST_PASS min_id={mi} max_id={ma} min_dist={float(DIST.min()):.5f} max_dist={float(DIST.max()):.5f}',flush=True)
 qs=[0, Q//2, Q-1, 17, 7777, 97001]
 need(1<=spots<=len(qs),'SPOTCHECK_COUNT_OUT_OF_RANGE')
 for qi in qs[:spots]:
  q=np.asarray(Y[qi]);need(bool(np.isfinite(q).all()),f'QUERY_NONFINITE_{qi}')
  best_ids=np.empty(0,dtype=np.int64);best_sq=np.empty(0,dtype=np.float32)
  for a in range(0,N,20000):
   b=min(N,a+20000)
   delta=np.asarray(X[a:b])-q
   sq=np.einsum('ij,ij->i',delta,delta,optimize=True)
   need(bool(np.isfinite(sq).all()),f'BASE_NONFINITE_IN_DISTANCE_{qi}')
   top=np.argpartition(sq,K-1)[:K]
   ids=np.concatenate([best_ids, a+top.astype(np.int64)])
   v=np.concatenate([best_sq,sq[top]])
   z=np.argpartition(v,K-1)[:K]
   best_ids,best_sq=ids[z],v[z]
  gtids=IDs[qi]
  need(len(set(map(int,gtids)))==K,f'GT_DUPLICATE_IDS_{qi}')
  cutoff=float(best_sq.max());tol=max(0.04,2e-5*cutoff)
  gtfirst=int(gtids[0]);delta=np.asarray(X[gtfirst])-q
  got_first=float(np.dot(delta,delta))
  need(got_first<=float(best_sq.min())+tol,f'GT_TOP1_ID_MISMATCH q={qi}')
  missing=set(map(int,gtids))-set(map(int,best_ids))
  if missing:
   aa=np.asarray(sorted(missing),dtype=np.int64)
   delta=np.asarray(X[aa])-q
   v=np.einsum('ij,ij->i',delta,delta,optimize=True)
   need(float(v.max())<=cutoff+tol,f'GT_TOP100_MISMATCH q={qi} missing={len(missing)}')
  observed=float(DIST[qi,0]);
  if abs(observed-math.sqrt(got_first))<=max(.04,2e-4*math.sqrt(got_first)):
   convention='L2'
  elif abs(observed-got_first)<=max(.04,2e-4*got_first):convention='L2_SQUARED'
  else:raise RuntimeError(f'GT_DISTANCE_CONVENTION_UNKNOWN q={qi} observed={observed} expected_sq={got_first}')
  print(f'GT_EXACT_TOP100_SPOTCHECK_PASS query={qi} 100/100 cutoff_sq={cutoff:.5f} convention={convention}',flush=True)
 receipt={'dataset':'MS-Turing ANNS 1M first prefix of 1B','n':N,'d':D,'queries':Q,'k':K,
          'sha256':hashes,'official_base_url':BASE_URL,'validation':'shape, SHA, GT u32+f32, '+str(spots)+' brute-force L2 spotchecks'}
 manifest=dst/'MS_TURING_1M_REPRO_MANIFEST.json'
 if manifest.exists():
  need(json.loads(manifest.read_text())==receipt,'EXISTING_MANIFEST_MISMATCH_NO_OVERWRITE')
 else:
  manifest.write_text(json.dumps(receipt,indent=2,sort_keys=True)+'\n')
 print(f'R86_MSTURING1M_DATA_GT_GATE_PASS manifest={manifest}',flush=True)


def main():
 p=argparse.ArgumentParser(description=__doc__)
 g=p.add_mutually_exclusive_group(required=True)
 g.add_argument('--probe',action='store_true');g.add_argument('--download',action='store_true');g.add_argument('--verify',action='store_true')
 p.add_argument('--root',type=Path,default=Path.home()/'ann-task-a')
 p.add_argument('--spotchecks',type=int,default=3)
 a=p.parse_args()
 root=a.root.resolve();need(root.is_dir(),'PROJECT_ROOT_MISSING')
 dest=root/'data'/'MSTuring_1M_v1'
 if a.probe:
  check_disk(dest)
  for k in SPEC:probe_one(k)
  print('R86_MSTURING1M_HTTP_RANGE_PROBE_PASS_NO_DOWNLOAD_NO_WRITES')
 elif a.download:
  check_disk(dest)
  if not dest.exists():dest.mkdir(parents=False)
  for k in SPEC:download_one(k,dest)
  print('R86_MSTURING1M_DOWNLOADS_COMPLETE_NEXT_VERIFY')
 else:verify(dest,a.spotchecks)

if __name__=='__main__':
 try:main()
 except (RuntimeError,ValueError,OSError,HTTPError,URLError) as e:
  print('R86_MSTURING1M_HOLD',str(e),file=sys.stderr,flush=True)
  sys.exit(2)
