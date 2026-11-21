#!/usr/bin/env python3
"""R91 G0.6: read-only R90 H85 TwoTier source/degree snapshot audit.

Never builds, modifies R85/R90 files or counts a theoretical RAM model as native RSS.
On success writes a new immutable report under experiments/R91 only.
"""
from __future__ import annotations
import array, hashlib, importlib.util, json, os, struct, sys, tempfile
from pathlib import Path

TAG='R91_G06_TWOTIER_READONLY_V1'
H=Path.home(); ROOT=H/'ann-task-a'; R90=ROOT/'experiments/R90'; R91=ROOT/'experiments/R91'
V13=R90/'r90_p0a_v13_historical_highway_6bc2_controlled_v1'
MATRIX=R90/'r90_p0a_v13_h85_24build_native_v1'
DEST=R91/'r91_g06_twotier_degree_audit_v1'
V11_PY=H/'Downloads/r90_p0a_unified_1m_three_arm_v1_1.py'
V11_SHA='fa9cdc09b3f447161f5c1f65382b15a0bc9645f425a679b73ca26f5ce8abecf0'
V13_SRC_SHA='5f42250caa47659daf978a73355857e355cc86096571d327518e676d41f1423b'
AUDIT_SHA='9550858dcb763349ed5180b3b65577e48a600e54becc0ecb9c755970a4d4bbfb'
FULL_SHA='0c76f3e5bc3dc0d82f70aa1aadac9b26c5b0e8f4607f31d9aa6d8b0b0a4121c3'
H85='6bc2d47793bae9c521fb4150936669647700765d'
N=1_000_000;B=64;C=160

def hold(x):raise RuntimeError(TAG+'_HOLD_'+x)
def must(v,msg):
 if not v:hold(msg)
def regular(p):return Path(p).is_file() and not Path(p).is_symlink()
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for x in iter(lambda:f.read(8<<20),b''):h.update(x)
 return h.hexdigest()
def pinned(p,d):
 must(regular(p),'MISSING_OR_SYMLINK_'+p.name);must(sha(p)==d,'SHA_'+p.name)
 return json.loads(p.read_text())
def hist(path,n=N):
 must(regular(path),'DEGREES_ABSENT_'+path.name)
 must(path.stat().st_size==n*4,'DEGREE_EXPECT_EXACT_RAW_U32LE_NO_HEADER_'+path.name)
 above=zero=total=maxd=0; bins=[0,0,0,0,0]; count=0
 with path.open('rb',buffering=8<<20) as f:
  while True:
   raw=f.read(4*(1<<18))
   if not raw:break
   must(len(raw)%4==0,'DEGREES_PARTIAL_WORD')
   arr=array.array('I');arr.frombytes(raw)
   if sys.byteorder!='little':arr.byteswap()
   for d in arr:
    count+=1;total+=d;maxd=max(maxd,d)
    if d>B:above+=1
    if d==0:zero+=1
    if d<=B:bins[0]+=1
    elif d<=96:bins[1]+=1
    elif d<=112:bins[2]+=1
    elif d<=128:bins[3]+=1
    else:bins[4]+=1
 must(count==n,'DEGREES_COUNT')
 must(0<=maxd<=C,'DEGREES_ABOVE_LOGICAL_CAP160')
 return {'raw_u32le_sha256':sha(path),'n':n,'count_gt_64':above,'fraction_gt_64':above/n,
         'mean_degree':total/n,'zero_degree':zero,'maximum':maxd,
         'bins_le64_65to96_97to112_113to128_gt128':bins}
def memory_model(p,n=10_000_000):
 # Interpret B64 small (65 slots) + C160 promoted (161 slots) + 8-byte active pointer.
 flat=n*(C+1)*8;small=n*(B+1)*8;large=round(n*p)*(C+1)*8;ptr=n*8
 return {'n':n,'promotion_fraction_1m_extrapolated':p,'flat_slot_bytes':flat,
         'small_slot_bytes':small,'promoted_slot_bytes':large,'active_rows_pointer_bytes':ptr,
         'two_tier_slot_plus_pointer_bytes':small+large+ptr,
         'relative_over_flat_pct':100*(small+large+ptr-flat)/flat,
         'limitations':['Requires native source confirmation that old small rows remain allocated, promoted chunks grow per owner, and active_rows_ has a pointer per owner.',
                        '1M preprune degree distribution extrapolation to 10M is NOT measured 10M occupancy.',
                        'Slab allocator metadata, alignment, other graph/data structures and peak RSS not modeled.']}
def selftest():
 with tempfile.TemporaryDirectory() as d:
  p=Path(d)/'degree.u32le'
  x=[0,64,65,96,97,112,113,128,129,160]
  p.write_bytes(struct.pack('<10I',*x))
  r=hist(p,10)
  must(r['count_gt_64']==8 and r['mean_degree']==sum(x)/10 and sum(r['bins_le64_65to96_97to112_113to128_gt128'])==10,'SELFTEST_HIST')
  q=memory_model(.9441)
  must(q['flat_slot_bytes']==12_880_000_000 and q['small_slot_bytes']==5_200_000_000 and q['active_rows_pointer_bytes']==80_000_000,'SELFTEST_BYTES')
 print(TAG+'_SELFTEST_PASS_RAW_U32LE_HIST_AND_10M_CAPACITY_MODEL',flush=True)
def original_v11():
 must(regular(V11_PY) and sha(V11_PY)==V11_SHA,'V11_RUNNER_SHA')
 spec=importlib.util.spec_from_file_location('r91_v11_pin',V11_PY)
 must(spec is not None and spec.loader is not None,'IMPORT_PIN')
 m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def run():
 must(not DEST.exists() and not DEST.is_symlink(),'DEST_ALREADY_EXISTS_PRESERVE')
 source=pinned(V13/'source_manifest.json',V13_SRC_SHA)
 audit=pinned(MATRIX/'audit1m_buildonly.json',AUDIT_SHA)
 full=pinned(MATRIX/'full1m_manifest.json',FULL_SHA)
 must(audit['Highway_commit']==H85 and audit['full_manifest_sha256']==FULL_SHA,'PROVENANCE_LINK')
 must(len(full['runs'])==24,'MATRIX_24')
 mod=original_v11()
 variant=next((v for v in source['variants'] if v['variant']=='fast_off'),None)
 must(variant is not None,'FAST_OFF_SOURCE_MANIFEST')
 src=V13/'source/fast_off'
 must(mod.digest_tree(src)==variant['tree_sha256'],'FAST_OFF_TREE_DRIFT')
 header=src/'algorithms/utils/r70_two_tier_lshgraph.h'
 must(regular(header),'LEGACY_TWOTIER_HEADER_MISSING')
 lines=header.read_text(errors='replace').splitlines()
 tokens=('small_rows_','active_rows_','chunks_')
 for tok in tokens:must(any(tok in line for line in lines),'LEGACY_TOKEN_ABSENT_'+tok)
 snippets=[{'line':i,'text':line.strip()[:350]} for i,line in enumerate(lines,1) if any(k in line for k in ('small_rows_','active_rows_','chunks_','promot','R70_TWO_TIER'))]
 rows={}
 for ds in ('SIFT1M','MS-Turing1M'):
  rec=next((x for x in full['runs'] if x['dataset']==ds and x['arm']=='fast' and x['mode']=='on' and x['rep']==1),None)
  must(rec is not None,'ON_RUN_'+ds)
  # Pin the ON counter receipt; histogram is separate unpinned artifact hashed in this report.
  p=Path(rec['stdout']);must(regular(p) and sha(p)==rec['stdout_sha'],'ON_STDOUT_SHA_'+ds)
  degrees=MATRIX/'logs'/(ds+'_fast_on_r1.degrees_pass2.u32le')
  rows[ds]=dict(path=str(degrees),**hist(degrees))
 models={ds:memory_model(z['fraction_gt_64']) for ds,z in rows.items()}
 report={'status':'READONLY_SOURCE_TREE_PIN_AND_TWO_ON_HISTOGRAMS_VERIFIED__10M_PROJECTION_ONLY',
  'legacy_two_tier_header':str(header),'header_sha256':sha(header),'source_manifest_sha256':V13_SRC_SHA,
  'fast_off_source_tree_sha256':variant['tree_sha256'],'audit_sha256':AUDIT_SHA,'full_manifest_sha256':FULL_SHA,
  'source_code_snippets_for_human_review':snippets[:120], 'degree_audits':rows,
  'projection_10m':models,'notes':['This is a 1M preprune histogram and theoretical 10M reservoir model, not observed native 10M RSS.','R85 TwoTier benefits on BIGANN1M do not establish benefit on MS-Turing10M.','Merely detecting source symbols does not prove allocator lifetime; review snippet in report.']}
 DEST.mkdir(parents=True,exist_ok=False)
 out=DEST/'r91_g06_twotier_readonly_report.json'
 with out.open('x') as f:json.dump(report,f,indent=2,sort_keys=True);f.write('\n')
 print(TAG+'_AUDIT_PASS_H85_SOURCE_PIN_2_ON_1M_HISTOGRAMS',flush=True)
 for ds,x in rows.items():print(TAG+'_DATASET',ds,'over64',x['count_gt_64'],'fraction',round(x['fraction_gt_64'],7),'mean_degree',round(x['mean_degree'],4),'sha256',x['raw_u32le_sha256'],flush=True)
 print(TAG+'_REPORT',out,'sha256',sha(out),flush=True)

def main():
 try:
  import argparse
  p=argparse.ArgumentParser();p.add_argument('mode',choices=['selftest','audit']);a=p.parse_args()
  (selftest if a.mode=='selftest' else run)()
 except Exception as e:
  print(TAG+'_ERROR',repr(e),file=sys.stderr);raise SystemExit(2)
if __name__=='__main__':main()
