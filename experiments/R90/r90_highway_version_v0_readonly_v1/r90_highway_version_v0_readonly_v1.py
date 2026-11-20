#!/usr/bin/env python3
"""R90 one-shot read-only audit. Historical binary/graph/data files never modified.
Do NOT use this audit to infer causal correctness of individual ANN graph edges.
"""
from __future__ import annotations
import argparse, array, hashlib, json, math, mmap, os, pathlib, struct, sys

HOME=pathlib.Path.home(); ROOT=HOME/'ann-task-a'; EXP=ROOT/'experiments'
OLD=EXP/'H85/r85_0_matched_baseline/build_stock/_deps/highway-src'
NEW=EXP/'R86/r86_v1_2_builds/stock_off/_deps/highway-src'
GRAPHROOT=EXP/'R90/r90_p0a_v12_pinned_six_elf_full1m_buildonly'
MANIFEST=GRAPHROOT/'full1m_manifest.json'
BASE=ROOT/'data/sift1m.fbin'
SCREEN=EXP/'R90/r90_p0a_v12_18graph_quality_screen_v1/quality_screen_summary.json'
REPORT=HOME/'R90_HIGHWAY_VERSION_V0_READONLY_v1_report.json'
BASE_SHA='8c7b3d999ba3133f865af72df078f77c2d248fdb80571d7ea1f1bb8e1750658e'
MANIFEST_SHA='4917142a7dcb5e6bab06bd4b8724f3bfac854bdcfbde2c5bc932220335fd6692'
SCREEN_SHA='340679635faa8b07b07ec5343e0c1d0ad4b080d8388b69d40ab4fab5d68f222e'
EXPECTED={
 'old': {'traits-inl.h':'b02ed8b9ab0d2e7d3d70f48c74f006531ff54753','sorting_networks-inl.h':'54b15230730ef3785ae1eaa09ce97485ce917021'},
 'new': {'traits-inl.h':'3a4d8506e6794432009c70ac312380b1d2ba801b','sorting_networks-inl.h':'92c2dfad48291f0c194d85f1bbe05dc6aee8d71a'} }

def sha256(path):
 h=hashlib.sha256()
 with path.open('rb') as f:
  for chunk in iter(lambda:f.read(4<<20),b''):h.update(chunk)
 return h.hexdigest()

def blob_sha1(path):
 raw=path.read_bytes()
 return hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()

def check_file(path,wanted,label):
 if not path.is_file() or path.is_symlink():raise RuntimeError('R90_HIGHWAY_V0_HOLD_MISSING_OR_SYMLINK_'+label)
 got=sha256(path)
 if got!=wanted:raise RuntimeError('R90_HIGHWAY_V0_HOLD_SHA_'+label+'_'+got)
 return got

def source_gate():
 result={}
 for name,root in [('old',OLD),('new',NEW)]:
  files={};
  for fname,wanted in EXPECTED[name].items():
   p=root/'hwy/contrib/sort'/fname
   if not p.is_file() or p.is_symlink():raise RuntimeError('R90_HIGHWAY_V0_HOLD_SOURCE_MISSING_'+name+'_'+fname)
   got=blob_sha1(p)
   if got!=wanted:raise RuntimeError('R90_HIGHWAY_V0_HOLD_SOURCE_BLOB_DRIFT_'+name+'_'+fname+'_'+got)
   files[fname]={'git_blob_sha1':got,'sha256':sha256(p)}
  t=(root/'hwy/contrib/sort/traits-inl.h').read_text()
  if name=='old':
   if 'if (sizeof(TFromD<D>) == 8)' not in t or 'a = IfThenElse(cmp, a, b);' not in t:raise RuntimeError('OLD_AVX2_BRANCH_ANCHOR_HOLD')
  else:
   if 'kLayout == PairLayout::kMirrored && IsFloat<TFromD<D>>()' not in t:raise RuntimeError('NEW_MIRRORED_FLOAT_BRANCH_ANCHOR_HOLD')
  result[name]={'source_root':str(root),'files':files,'traits_branch':('compare_blend_double' if name=='old' else 'mirrored_float_first_last')}
 return result

def first_vertex(path,expect_sha,base_mmap):
 check_file(path,expect_sha,'GRAPH_'+path.stem)
 with path.open('rb') as f:
  h=f.read(8)
  if len(h)!=8 or struct.unpack('<II',h)!=(1000000,64):raise RuntimeError('GRAPH_HEADER_HOLD_'+path.stem)
  raw=f.read(4000000)
  if len(raw)!=4000000:raise RuntimeError('GRAPH_DEGREES_TRUNCATED_'+path.stem)
  deg=array.array('I'); deg.frombytes(raw)
  if sys.byteorder!='little':deg.byteswap()
  if len(deg)!=1000000 or max(deg)>64:raise RuntimeError('GRAPH_DEGREE_HOLD_'+path.stem)
  arcs=sum(deg)
  if path.stat().st_size!=8+4*1000000+4*arcs:raise RuntimeError('GRAPH_SIZE_HOLD_'+path.stem)
  d0=deg[0];raw=f.read(4*d0)
  if len(raw)!=4*d0:raise RuntimeError('GRAPH_FIRST_ROW_TRUNCATED_'+path.stem)
  neighbors=list(struct.unpack('<'+'I'*d0,raw)) if d0 else []
  if len(set(neighbors))!=len(neighbors) or any(v>=1000000 or v==0 for v in neighbors):raise RuntimeError('GRAPH_FIRST_ROW_INVALID_'+path.stem)
  v0=struct.unpack_from('<128f',base_mmap,8)
  out=[]
  for v in neighbors:
   vec=struct.unpack_from('<128f',base_mmap,8+v*128*4)
   dist=math.fsum((float(x)-float(y))**2 for x,y in zip(v0,vec))
   out.append((v,dist))
  by_dist=sorted(out,key=lambda x:(x[1],x[0]))
  return {'graph_file':str(path),'graph_sha256':expect_sha,'degree_v0':d0,'total_directed_arcs':arcs,
    'v0_contains_neighbor_2':2 in neighbors,'v0_contains_neighbor_6':6 in neighbors,
    'v0_first_three_file_order':[{'id':j,'squared_l2':round(d,3)} for j,d in out[:3]],
    'v0_two_closest_in_stored_neighbors':[{'id':j,'squared_l2':round(d,3)} for j,d in by_dist[:2]],
    'v0_neighbors_squared_l2_gt_50000':sum(d>50000 for _,d in out),
    'v0_neighbors_squared_l2_mean':round(math.fsum(d for _,d in out)/len(out),3) if out else None,
    'warning':'First-vertex geometry is diagnostic, not definitive causal proof of FTZ damage.'}

def selftest():
 raw=b'hello'
 assert hashlib.sha1(b'blob 5\0'+raw).hexdigest()=='b6fc4c620b67d95f953a5c1c1230aaab5db5a1b0'
 assert struct.unpack('<II',struct.pack('<II',1000000,64))==(1000000,64)
 print('R90_HIGHWAY_VERSION_V0_V1_SELFTEST_PASS')

def audit():
 if REPORT.exists() or REPORT.is_symlink():raise RuntimeError('R90_HIGHWAY_V0_OUTPUT_EXISTS_HOLD')
 src=source_gate()
 print('R90_HIGHWAY_VERSION_V0_SOURCE_BLOB_PASS_OLD_6BC2_NEW_0E0A',flush=True)
 check_file(MANIFEST,MANIFEST_SHA,'ORIGINAL_FULL1M_MANIFEST')
 manifest=json.loads(MANIFEST.read_text())
 base_sha=check_file(BASE,BASE_SHA,'SIFT1M_BASE')
 if BASE.stat().st_size!=8+1000000*128*4:raise RuntimeError('BASE_SIZE_HOLD')
 with BASE.open('rb') as f:
  if struct.unpack('<II',f.read(8))!=(1000000,128):raise RuntimeError('BASE_HEADER_HOLD')
 with BASE.open('rb') as f,mmap.mmap(f.fileno(),0,access=mmap.ACCESS_READ) as mm:
  gs={}
  for arm in ('stock','h17','fast'):
   entries=[r for r in manifest['runs'] if r['dataset']=='SIFT1M' and r['arm']==arm and r['mode']=='off' and r['rep']==1]
   if len(entries)!=1:raise RuntimeError('MANIFEST_MISSING_SIFT_R1_'+arm)
   entry=entries[0]
   p=pathlib.Path(entry['graph'])
   if p.parent != GRAPHROOT/'graphs':raise RuntimeError('GRAPH_DIR_OUTSIDE_PINNED_ROOT_'+arm)
   gs[arm]=first_vertex(p,entry['graph_sha'],mm)
   print('R90_HIGHWAY_VERSION_V0',arm,'degree',gs[arm]['degree_v0'],'contains_2',gs[arm]['v0_contains_neighbor_2'],'contains_6',gs[arm]['v0_contains_neighbor_6'],'nearest',gs[arm]['v0_two_closest_in_stored_neighbors'],flush=True)
 screen_record={}
 if SCREEN.is_file() and not SCREEN.is_symlink():
  check_file(SCREEN,SCREEN_SHA,'SEARCH_SCREEN_SUMMARY')
  j=json.loads(SCREEN.read_text())
  for ds in ('SIFT1M','MS-Turing1M'):
   screen_record[ds]={}
   for arm in ('stock','h17','fast'):
    actual=j['report'][ds][arm]['target_screen']['0.99']['tested_beam_grid']
    expected=[10,20,40,80,160] if ds=='SIFT1M' else [384,896]
    screen_record[ds][arm]={'grid_from_summary':actual,'expected_from_original_runner':expected,'metadata_error':actual!=expected}
 report={'status':'NATIVE_READONLY_SOURCE_REVISION_AND_V0_GRAPH_OBSERVATION_COMPLETE',
 'old_new_highway_source':src,'original_full_manifest_sha256':MANIFEST_SHA,'sift1m_base_sha256':base_sha,
 'v0':gs,'original_screen_grid_metadata':screen_record,
 'interpretation':['Confirms source differences and observed v0 graph geometry, not historical graph causality.',
  'Before claiming stock SIFT1M edge corruption due to new Highway, collect same-leaf packed-key trace or controlled old/new Highway build comparison.',
  'Do not run old matched-threshold timing on potentially confounded stock baseline.','Keep original results unchanged.']}
 data=(json.dumps(report,indent=2,ensure_ascii=False,sort_keys=True)+'\n').encode()
 with REPORT.open('xb') as out:out.write(data)
 print('R90_HIGHWAY_VERSION_V0_V1_REPORT',REPORT,'sha256',hashlib.sha256(data).hexdigest(),flush=True)
 print('R90_HIGHWAY_VERSION_V0_V1_AUDIT_PASS_NO_ORIGINAL_MODIFICATION',flush=True)

if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--selftest',action='store_true');ap.add_argument('--audit',action='store_true');a=ap.parse_args()
 try:
  if a.selftest:selftest()
  elif a.audit:audit()
  else:ap.error('choose --selftest or --audit')
 except Exception as e:
  print('R90_HIGHWAY_VERSION_V0_V1_HOLD',str(e),file=sys.stderr,flush=True);sys.exit(2)
