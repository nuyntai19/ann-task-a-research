#!/usr/bin/env python3
"""R86 W(n): PINNED preflight and optional prefix preparation; DOES NOT RUN ANN.

Checks SIFT100K == SIFT1M prefix bytewise, validates fbin shapes, reports
existing R86 100K ON binaries + command references and resource headroom.
With --prepare-prefixes, creates only 10K/30K/300K fbin prefix datasets
under a new isolated folder, verifies them after write, and makes manifest.
Uses existing sift100k.fbin and sift1m.fbin for n=100K,1M, no duplicate copy.
No shell set -e, no changes to original data, binaries, graphs or source.
"""
from __future__ import annotations
import argparse,csv,hashlib,json,os,re,shutil,struct
from pathlib import Path

SOURCE_SHA={'sift100k.fbin':'e50ff1bc34bcc6d1c97dd001023c09a666971cde64605cc06671ed8a8ff1ed12'}
ON_BINARY_SHA={
 'A0':'396ef852992428cd3f935bcb33eeeeacc1bae565fbc4a441c1fa9d19720122ff',
 'A3':'ef707479be221cb7a3c6257298d22f614678878f0a7bfc724dc8b28fabdd21c4',
 'A4':'ef707479be221cb7a3c6257298d22f614678878f0a7bfc724dc8b28fabdd21c4',
}
ARMS={
 'A0':('stock_C160_K1024_N2_on_r1',160,1024,2),
 'A3':('h17_C64_K512_N2_on_r1',64,512,2),
 'A4':('h17_C64_K512_N1_on_r1',64,512,1),
}


def sha(path):
 h=hashlib.sha256()
 with path.open('rb') as f:
  for block in iter(lambda:f.read(4*1024*1024),b''):h.update(block)
 return h.hexdigest()


def hdr(path):
 with path.open('rb') as f:
  raw=f.read(8)
 if len(raw)!=8:raise RuntimeError(f'INVALID_FBIN_HEADER {path}')
 n,d=struct.unpack('<II',raw)
 if d!=128 or path.stat().st_size!=8+n*d*4:
  raise RuntimeError(f'INVALID_FBIN_SHAPE_SIZE {path} ({n},{d}) size={path.stat().st_size}')
 return n,d


def same_prefix(small,large):
 remain=small.stat().st_size-8
 with small.open('rb') as a,large.open('rb') as b:
  a.seek(8);b.seek(8)
  while remain:
   k=min(remain,4*1024*1024)
   if a.read(k)!=b.read(k):return False
   remain-=k
 return True


def scan_binary_candidates(root):
 places=[root/'00_PROJECT_HOME/02_BINARIES',root/'experiments/R86/r86_v1_2_builds',root/'experiments/R86/builds',root/'experiments/R86/gates',root/'experiments/R86/scaling']
 found={}
 seen=set()
 for folder in places:
  if not folder.exists():continue
  for p in folder.rglob('*'):
   # Files may be symlinks in the Project Hub.
   if not p.is_file() or not os.access(p,os.X_OK):continue
   try:
    real=str(p.resolve())
    if real in seen:continue
    seen.add(real)
    if p.stat().st_size>80_000_000 or p.stat().st_size<50_000:continue
    digest=sha(p)
    if digest in set(ON_BINARY_SHA.values()):
     found.setdefault(digest,[]).append(str(p))
   except (OSError,PermissionError):continue
 return found


def preview_command_refs(bench):
 csvfile=bench/'runs.csv'
 if csvfile.is_file():
  with csvfile.open(newline='',errors='replace') as f:
   r=csv.DictReader(f)
   print('RUNS_CSV_COLUMNS',list(r.fieldnames or []))
   for row in r:
    if any(row.get(k,'') in [v[0] for v in ARMS.values()] for k in ['run_id','run','name','id']):
     print('SAMPLE_ON_RECORD',json.dumps(row,ensure_ascii=False)[:1600])
 txt=bench/'protocol.txt'
 if txt.is_file():
  print('PROTOCOL_PATH',txt)
  for line in txt.read_text(errors='replace').splitlines()[:35]:
   if any(k in line.lower() for k in ['command','pipnn','num_cluster','cpu','thread','build','dataset','base','source','run']):print('PROTOCOL_LINE',line[:320])
 for arm,(run,C,K,N) in ARMS.items():
  folder=bench/run
  if not folder.is_dir():print('ON_RUN_NOT_FOUND',run);continue
  log=folder/(run+'.build.log')
  if not log.is_file():
   logs=list(folder.glob('*.build.log'))
   log=logs[0] if len(logs)==1 else None
  if log and log.is_file():
   lines=log.read_text(errors='replace').splitlines()
   matches=[x for x in lines if ('-num_clusters' in x or '-base_file' in x or '-input' in x or '-file' in x and 'fbin' in x)]
   print('ON_LOG',run,log,'command_candidates',len(matches))
   for x in matches[:3]:print('ON_LOG_LINE',x[:800])
  else:print('ON_LOG_MISSING',run)


def make_prefix(dst,large,n):
 target=dst/f'sift1m_prefix_{n}.fbin'
 if target.exists():
  if hdr(target)!=(n,128):raise RuntimeError('EXISTING_PREFIX_SHAPE_FAIL '+str(target))
  # Bytewise compare each previously written file; do not trust existing name.
  with large.open('rb') as src,target.open('rb') as check:
   src.seek(8);check.seek(8);remain=n*128*4
   while remain:
    size=min(remain,4*1024*1024)
    if src.read(size)!=check.read(size):raise RuntimeError('EXISTING_PREFIX_CONTENT_FAIL '+str(target))
    remain-=size
  print('PREFIX_REUSE_VERIFIED',target)
  return target
 tmp=target.with_suffix('.fbin.tmp')
 if tmp.exists():raise RuntimeError('PARTIAL_TMP_EXISTS_NO_OVERWRITE: '+str(tmp))
 try:
  with tmp.open('xb') as out,large.open('rb') as src:
   out.write(struct.pack('<II',n,128));src.seek(8)
   remain=n*128*4
   while remain:
    data=src.read(min(remain,4*1024*1024))
    if not data:raise RuntimeError('UNEXPECTED_INPUT_EOF')
    out.write(data);remain-=len(data)
  os.replace(tmp,target)
 except BaseException:
  if tmp.exists():tmp.unlink()
  raise
 if hdr(target)!=(n,128):raise RuntimeError('WRITTEN_PREFIX_BAD_SHAPE')
 print('PREFIX_PREPARED',target)
 return target


def main():
 ap=argparse.ArgumentParser(description=__doc__)
 ap.add_argument('--root',type=Path,default=Path.home()/'ann-task-a')
 ap.add_argument('--prepare-prefixes',action='store_true')
 ap.add_argument('--out',type=Path)
 args=ap.parse_args()
 root=args.root.expanduser().resolve();d=root/'data';bench=root/'experiments/R86/benchmarks/sift100k_a0a4_hw85_7ueCvd'
 s=d/'sift100k.fbin';l=d/'sift1m.fbin'
 for p in (s,l):
  if not p.is_file():raise RuntimeError('MISSING_FBIN '+str(p))
 print('SMALL',hdr(s),'LARGE',hdr(l))
 if hdr(s)!=(100000,128) or hdr(l)!=(1000000,128):raise RuntimeError('FBIN_N_DIM_HOLD')
 if sha(s)!=SOURCE_SHA[s.name]:raise RuntimeError('PINNED_100K_SHA_HOLD')
 if not same_prefix(s,l):raise RuntimeError('SIFT100K_NOT_SIFT1M_PREFIX')
 print('PREFIX_AUDIT_PASS_BYTE_IDENTICAL_100K')
 print('SIFT1M_SHA256',sha(l))
 found=scan_binary_candidates(root)
 for arm,digest in ON_BINARY_SHA.items():
  p=found.get(digest,[])
  print('BINARY',arm,digest,'FOUND',p if p else 'MISSING_HOLD')
 preview_command_refs(bench)
 free=shutil.disk_usage(root).free
 memavail_kb=None
 try:
  for line in Path('/proc/meminfo').read_text().splitlines():
   if line.startswith('MemAvailable:'):memavail_kb=int(line.split()[1]);break
 except OSError:pass
 print('FREE_DISK_GIB',round(free/1024**3,2),'MEM_AVAILABLE_GIB',round(memavail_kb*1024/1024**3,2) if memavail_kb else 'UNKNOWN')
 print('SOURCE_100K_AND_BINARIES_AUDITED_NO_BUILD')
 if not args.prepare_prefixes:
  print('W_N_PREFLIGHT_DONE_RUN_WITH_--prepare-prefixes_TO_PREPARE_DATA_ONLY')
  return
 if free<300*1024**2:raise RuntimeError('INSUFFICIENT_DISK_FOR_PREFIXES')
 out=(args.out or root/'experiments/R86/scaling_wn_sift1m_prefixes_v1_0').expanduser().resolve()
 if bench in out.parents or out==root or out==root/'data' or out==l.parent:
  raise RuntimeError('UNSAFE_PREFIX_DESTINATION')
 out.mkdir(parents=True,exist_ok=True)
 paths={100000:s,1000000:l}
 for n in (10000,30000,300000):paths[n]=make_prefix(out,l,n)
 manifest={'purpose':'R86 W(n) SIFT1M prefix study; data only, ANN BUILD NOT RUN',
           'source_sift1m':str(l),'source_sha256':sha(l),
           'datasets':{str(n):{'path':str(p),'sha256':sha(p),'n':n,'d':128} for n,p in sorted(paths.items())},
           'candidate_arms':{arm:{'C':v[1],'K':v[2],'N':v[3],'binary_sha256':ON_BINARY_SHA[arm]} for arm,v in ARMS.items()},
           'status':'PREFIX_DATA_PREPARED_NATIVE_ON_BUILD_NOT_STARTED'}
 man=out/'prefix_manifest.json'
 if man.exists():
  if json.loads(man.read_text())!=manifest:raise RuntimeError('EXISTING_MANIFEST_DIFFERS_NO_OVERWRITE')
 else:man.write_text(json.dumps(manifest,indent=2)+'\n')
 print('PREFIX_MANIFEST',man)
 print('R86_WN_PREFIXES_READY_NO_BUILD')

if __name__=='__main__':
 try:main()
 except Exception as e:
  print('R86_WN_PREFLIGHT_OR_PREFIX_HOLD',str(e));raise SystemExit(1)
