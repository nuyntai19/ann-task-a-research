#!/usr/bin/env python3
"""R90 P0A v1.3 controlled H85 Highway (6bc2d477) 1M BUILD-only 24-run protocol.

Reuses the six existing v1.3 SHA-pinned OFF/ON ELF; fresh isolated outputs.
Three balanced 4-CPU OFF BUILD repetitions per arm/dataset and one 1-CPU ON
work-counter diagnostic per arm/dataset, 24 total.
Never changes v1.1/v1.2/v1.3 source, binary, graph, log, or prior receipts.
Keeps Stage B one-Stock SIFT1M quality graph as an independent anchor, not a
performance replicate. No Search, no 10M, no formal Recall equivalence claim.
"""
from __future__ import annotations
import argparse, hashlib, importlib.util, json, os, re, shutil, struct, sys, math, mmap
from pathlib import Path

HOME=Path.home(); ROOT=HOME/'ann-task-a'; R90=ROOT/'experiments/R90'
OLD=R90/'r90_p0a_v13_historical_highway_6bc2_controlled_v1'
V11=R90/'r90_p0a_unified_1m_three_arm_v1_1'
NEW=R90/'r90_p0a_v13_h85_24build_native_v1'
SCRIPT=HOME/'Downloads/r90_p0a_unified_1m_three_arm_v1_1.py'
V13_PY=HOME/'Downloads/r90_p0a_v13_historical_highway_controlled_v1.py'
V13_PY_SHA='52805e517a8534732f0cbb6aeac374afc71dcbb88af53aae0d7a4d624d9e5dc'
ORIG_PY_SHA='fa9cdc09b3f447161f5c1f65382b15a0bc9645f425a679b73ca26f5ce8abecf0'
ORIG_SRC_SHA='5f42250caa47659daf978a73355857e355cc86096571d327518e676d41f1423b'
ORIG_PILOT_SHA='eb8b155038051a8dcd8f0bbaebd6ced880c2424f184e021d9f1472cd695ce20f'
STAGEA_SHA='58406df0aaa4813a8562623726a627e133efdf08ddb2eaec1c5501f6157e230a'
STAGEB_SHA='5827a3f5e52d552521cd4f64ce42324a0f13d6549be5cb37e5f2e987fdf9f785'
COMPILE_PROVENANCE_SHA='81dd161594fb92c8dc3c8bea54c004afdbdc6f7ba71d8ed5b187ecd01d64d89e'
PROBE_SHA='277e30167756f11953812d2079f6151c6fca1bcf4b16c7e26e3d54dce2de466f'
COMPILER_SHA='1353e9bdd29a7295c7226bf6c63abccce056d8cac31f112e5cdbecc3f28c2769'
H85_COMMIT='6bc2d47793bae9c521fb4150936669647700765d'
STAGEB_GRAPH_SHA='c60d2fed5d6b5c2a59b7f7fa1549f89436bc36fa4315d410d87c0f4be5a8735b'
SIFT=ROOT/'data/sift1m.fbin'
ARMS=('stock','h17','fast');MODES=('off','on')
TAG='R90_P0A_V13_H85_24BUILD'


def need(ok,msg):
 if not ok:raise RuntimeError(TAG+'_HOLD_'+str(msg))

def sha(p):
 d=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(4<<20),b''):d.update(b)
 return d.hexdigest()

def exists_regular(p):
 p=Path(p);return p.is_file() and not p.is_symlink()

def js(p):
 p=Path(p);need(exists_regular(p),'MISSING_OR_SYMLINK_'+p.name)
 return json.loads(p.read_text())

def atomic(p,v,first=False):
 p=Path(p);temp=p.with_suffix(p.suffix+'.part')
 need(not temp.exists() and not temp.is_symlink(),'PART_EXISTS_'+temp.name)
 if first:need(not p.exists() and not p.is_symlink(),'EXISTS_'+p.name)
 else:need(not p.is_symlink(),'OUTPUT_SYMLINK_'+p.name)
 with temp.open('x') as f:
  json.dump(v,f,sort_keys=True,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
 os.replace(temp,p)

def oldbin(arm,mode):
 return OLD/'build'/(arm+'_'+mode)/'algorithms/PipNN/neighbors-pipnn_FLOAT_T_EUCLIDEAN'

def original_module():
 need(exists_regular(SCRIPT) and sha(SCRIPT)==ORIG_PY_SHA,'ORIGINAL_V11_PY_SHA')
 spec=importlib.util.spec_from_file_location('p0a_v13_import_frozen_v11',SCRIPT)
 need(spec is not None and spec.loader is not None,'ORIGINAL_IMPORT')
 mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
 need(mod.OUT==V11 and tuple(mod.ARMS)==ARMS and tuple(mod.MODES)==MODES,'ORIGINAL_API')
 return mod

def v13_module():
 need(exists_regular(V13_PY) and sha(V13_PY)==V13_PY_SHA,'V13_PY_SHA')
 spec=importlib.util.spec_from_file_location('p0a_v13_frozen_stageab',V13_PY)
 need(spec is not None and spec.loader is not None,'V13_IMPORT')
 v=importlib.util.module_from_spec(spec);spec.loader.exec_module(v)
 need(v.OUT==OLD and v.H85.is_dir(),'V13_API')
 return v

def preflight():
 mod=original_module();v=v13_module()
 # Delegates the immutable legacy-source, dependency, and actual-compiler checks
 # to the frozen v1.3 Stage A runner, without invoking preflightB's NO_B_OUTPUT gate.
 v.base_gate()
 for name,dig in [('source_manifest.json',ORIG_SRC_SHA),('pilot_manifest.json',ORIG_PILOT_SHA),
                  ('stageA_audit.json',STAGEA_SHA),('stageB_stock_sift1m_quality.json',STAGEB_SHA),
                  ('compile_provenance_audit.json',COMPILE_PROVENANCE_SHA),('probe_report.json',PROBE_SHA)]:
  need(exists_regular(OLD/name) and sha(OLD/name)==dig,'V13_'+name+'_SHA')
 src=js(OLD/'source_manifest.json');pilot=js(OLD/'pilot_manifest.json')
 a=js(OLD/'stageA_audit.json');b=js(OLD/'stageB_stock_sift1m_quality.json')
 comp=js(OLD/'compile_manifest.json');prov=js(OLD/'compile_provenance_audit.json')
 need(src['highway_historical_pin']['git_head']==H85_COMMIT and a['highway_commit_full']==H85_COMMIT and b['h85_commit']==H85_COMMIT,'HIGHWAY_COMMIT')
 need(src['input']['deps']['HIGHWAY']==str(v.H85),'HIGHWAY_OLD_DEP_PATH')
 need(a['status']=='STAGEA_SIX_ELF_H85_HWY_PROBE_AND_SIFT10K_GRAPH_STRUCTURE_PASS','STAGEA_STATUS')
 need(b['status']=='STAGEB_STOCK_SIFT1M_QUALITY_PASS_READY_FOR_REVIEW','STAGEB_STATUS')
 need(all(b['gates'][k] for k in ('v0_contains_2_and_6_degree_under64','recall_80_atleast_099_and_160_atleast_0998','duplicate_either_endpoint_retention_atleast_095')),'STAGEB_GATE')
 need(b['search_recall_by_beam']['80']['recall']>=.99 and b['search_recall_by_beam']['160']['recall']>=.998,'STAGEB_RECALL')
 need(b['stock_graph']['graph_sha256']==STAGEB_GRAPH_SHA,'STAGEB_GRAPH_PIN')
 stageb_record=OLD/'SIFT1M_stock_off_r1.json'
 need(exists_regular(stageb_record) and sha(stageb_record)==b['stock_graph_record_sha256'],'STAGEB_RECORD')
 prior=js(stageb_record)
 for key,path,expected in [('graph',prior['graph'],STAGEB_GRAPH_SHA),('stdout',prior['stdout'],prior['stdout_sha']),('timefile',prior['timefile'],prior['timefile_sha'])]:
  need(exists_regular(path) and sha(path)==expected,'STAGEB_PRIOR_'+key)
 need(comp['compiler_sha256']==COMPILER_SHA and prov['six_binary_compiler_sha256']==COMPILER_SHA,'COMPILER_SHA')
 need(exists_regular(comp['cxx_binary']) and sha(comp['cxx_binary'])==COMPILER_SHA,'COMPILER_BINARY')
 need(set(comp['binaries'])=={x+'_'+m for x in ARMS for m in MODES},'SIX_ELF')
 need(len(pilot['runs'])==6 and len(a['pilot_graphs'])==6,'STAGEA_SIX_GRAPH')
 for arm in ARMS:
  for mode in MODES:
   key=arm+'_'+mode;exe=oldbin(arm,mode)
   need(exists_regular(exe) and sha(exe)==comp['binaries'][key]==prov['per_arm'][key]['elf_sha256'],'PIN_ELF_'+key)
   variant=next((r for r in src['variants'] if r['variant']==key),None)
   need(variant is not None and mod.digest_tree(OLD/'source'/key)==variant['tree_sha256'],'SOURCE_TREE_'+key)
   rec=next((r for r in pilot['runs'] if r['arm']==arm and r['mode']==mode),None)
   need(rec is not None,'STAGEA_PILOT_'+key)
   for field,digest in [('graph','graph_sha'),('stdout','stdout_sha'),('timefile','timefile_sha')]:
    need(exists_regular(rec[field]) and sha(rec[field])==rec[digest],'STAGEA_'+field+'_'+key)
 for k,base in mod.BASES.items():
  need(exists_regular(base) and sha(base)==mod.BASE_SHAS[k],'DATA_SHA_'+k)
 need(mod.BASES['SIFT1M']==SIFT,'SIFT_PATH')
 need(os.sched_getaffinity(0).issuperset({0,2,4,6}),'FOUR_CPU_AFFINITY')
 need(shutil.disk_usage(R90).free>=4*(1<<30),'DISK_HEADROOM_LT4GIB')
 meminfo=Path('/proc/meminfo')
 mm=re.search(r'^MemAvailable:\s+(\d+)\s+kB',meminfo.read_text(),re.M)
 need(mm and int(mm.group(1))>=4*(1<<20),'MEM_HEADROOM_LT4GIB')
 need(not (NEW/'audit1m_buildonly.json').exists(),'ALREADY_AUDITED')
 print(TAG+'_PREFLIGHT_PASS_V13_6ELF_H85_COMMIT_STAGEA_STAGEB_FTZ_SIFT_MS_DATA_SHA',flush=True)
 return mod,comp,js(OLD/'probe_report.json')

def jobs():
 out=[]
 for dataset in ('SIFT1M','MS-Turing1M'):
  for rep in (1,2,3):
   seq={1:ARMS,2:('fast','stock','h17'),3:('h17','fast','stock')}[rep]
   for arm in seq:out.append(dict(dataset=dataset,arm=arm,mode='off',rep=rep,cpu=4))
  for arm in ARMS:out.append(dict(dataset=dataset,arm=arm,mode='on',rep=1,cpu=1))
 need(len(out)==24 and len({label(x) for x in out})==24,'JOBS_UNIQUE_24')
 return out

def label(x):return f"{x['dataset']}_{x['arm']}_{x['mode']}_r{x['rep']}"

def prep():
 mod,comp,probe=preflight()
 need(shutil.disk_usage(R90).free>=12*(1<<30),'NEW_MATRIX_DISK_HEADROOM_LT12GIB')
 m=re.search(r'^MemAvailable:\s+(\d+)\s+kB',Path('/proc/meminfo').read_text(),re.M)
 need(m is not None and int(m.group(1))>=8*(1<<20),'NEW_MATRIX_MEM_HEADROOM_LT8GIB')
 need(not NEW.exists() and not NEW.is_symlink(),'OUTPUT_ROOT_ALREADY_EXISTS')
 NEW.mkdir(parents=True,exist_ok=False)
 for d in ('build','graphs','logs'):(NEW/d).mkdir()
 for key,digest in comp['binaries'].items():
  arm,mode=key.rsplit('_',1)
  target=oldbin(arm,mode)
  dest=NEW/'build'/key/'algorithms/PipNN/neighbors-pipnn_FLOAT_T_EUCLIDEAN'
  dest.parent.mkdir(parents=True,exist_ok=False)
  dest.symlink_to(target)
  need(dest.resolve(strict=True)==target.resolve(strict=True) and sha(dest)==digest,'ELF_PIN_LINK_'+key)
 shutil.copyfile(OLD/'compile_manifest.json',NEW/'compile_manifest.json')
 need(sha(NEW/'compile_manifest.json')==sha(OLD/'compile_manifest.json'),'PIN_COMPILER_MANIFEST')
 pin={'status':'V13_H85_BUILDONLY_BASELINE_QUALITY_STAGEB_PASS_NO_NEW_GRAPH_SEARCH','original_p0a_py_sha':ORIG_PY_SHA,'runner_sha256':sha(Path(__file__)),
      'original_source_manifest_sha':ORIG_SRC_SHA,'original_pilot_manifest_sha':ORIG_PILOT_SHA,'stageA_sha':STAGEA_SHA,'stageB_sha':STAGEB_SHA,'historical_highway_commit':H85_COMMIT,
      'ftz_native_probe_sha':PROBE_SHA,'existing_elf_sha':dict(comp['binaries']),
      'compiler_sha':COMPILER_SHA,'data_shas':dict(mod.BASE_SHAS),
      'jobs':jobs(),'protocol':'New isolated 4CPU OFF 18 + 1CPU0 ON 6 BUILD runs using original pinned V11 native_one with six new V13 H85 ELF symlinks; Stage B Stock graph independent anchor not timing repetition. No across-arm exact graph SHA requirement.',
      'known_risks':['H85 Highway synthetic one-zero bit-clearing not observed but simultaneous subnormal ties still change ordering under DAZ.','Historical Stage B Stock graph is NOT part of this performance repetition matrix.','Recall@10/QPS have not been tested on the NEW 24 graph instances; Stage B only certifies its separate Stock graph.']}
 atomic(NEW/'preregister.json',pin,first=True)
 atomic(NEW/'progress.json',{'status':'PREPARED_NO_1M_BUILD','completed':[]},first=True)
 print(TAG+'_PREPARE_PASS_OUTPUT_ISOLATED_SIX_ELF_SYMLINKS_PINNED_NO_BUILD_YET',flush=True)

def guarded_output(mod,job):
 name=label(job);record_path=NEW/(name+'.json')
 g=NEW/'graphs'/(name+'.graph');o=NEW/'logs'/(name+'.stdout');t=NEW/'logs'/(name+'.time')
 if record_path.exists():
  record=js(record_path)
  need(all(record.get(k)==v for k,v in [('arm',job['arm']),('mode',job['mode']),('dataset',job['dataset']),('rep',job['rep']),('threads',job['cpu'])]),'RESUME_RECORD_FIELDS_'+name)
  for k,p,v in [('graph',g,'graph_sha'),('stdout',o,'stdout_sha'),('timefile',t,'timefile_sha')]:
   need(record.get(k)==str(p) and exists_regular(p) and sha(p)==record[v],'RESUME_'+k+'_SHA_'+name)
  need(record['elf_sha']==js(NEW/'compile_manifest.json')['binaries'][job['arm']+'_'+job['mode']],'RESUME_ELF_PIN_'+name)
  if job['mode']=='on':
   counters=NEW/'logs'/(name+'.counters.jsonl')
   need(exists_regular(counters) and sha(counters)==record['r86_work_jsonl_sha'],'RESUME_COUNTER_SHA_'+name)
  return record
 need(not any(x.exists() or x.is_symlink() for x in (record_path,g,o,t)),'PARTIAL_OR_ORPHAN_LOG_HOLD_'+name)
 return None

def recheck_links():
 comp=js(NEW/'compile_manifest.json')
 for k,digest in comp['binaries'].items():
  arm,mode=k.rsplit('_',1)
  p=NEW/'build'/k/'algorithms/PipNN/neighbors-pipnn_FLOAT_T_EUCLIDEAN'
  need(p.is_symlink() and p.resolve(strict=True)==oldbin(arm,mode).resolve(strict=True),'ELF_LINK_DRIFT_'+k)
  need(sha(p)==digest,'ELF_SHA_DRIFT_'+k)

def run():
 mod,comp,_=preflight()
 pre=js(NEW/'preregister.json');need(pre['jobs']==jobs() and pre['original_p0a_py_sha']==ORIG_PY_SHA and pre['runner_sha256']==sha(Path(__file__)),'PREREG_PIN')
 recheck_links()
 need(not (NEW/'full1m_manifest.json').exists(),'FULL_MANIFEST_EXISTS')
 mod.OUT=NEW
 seen=[]
 for job in jobs():
  existing=guarded_output(mod,job)
  if existing is not None:
   seen.append(existing)
   print(TAG+'_RESUME_VERIFIED',label(job),flush=True)
   continue
  # Do not start a job if available memory becomes too small mid-sequence.
  mm=re.search(r'^MemAvailable:\s+(\d+)\s+kB',Path('/proc/meminfo').read_text(),re.M)
  need(mm is not None and int(mm.group(1)) >= 8*(1<<20),'MEM_DURING_RUN_LT8GIB_'+label(job))
  need(shutil.disk_usage(R90).free>=4*(1<<30),'DISK_DURING_RUN_LT4GIB_'+label(job))
  dataset=job['dataset'];base=mod.BASES[dataset]
  record=mod.native_one(job['arm'],job['mode'],base,dataset,job['rep'],job['cpu'])
  need(record['threads']==job['cpu'],'CPU_MISMATCH')
  seen.append(record)
  atomic(NEW/'progress.json',{'status':f'{len(seen)}_OF_24_NATIVE_BUILD_RECORDS_SHA_VERIFIED','completed':seen})
  print(TAG+'_1M_BUILD_RECORD_PASS',len(seen),'of24',label(job),record['graph_sha'],flush=True)
 for job in jobs():guarded_output(mod,job)
 atomic(NEW/'full1m_manifest.json',{'status':'OFF18_ON6_BUILT_PENDING_GRAPH_STRUCTURE_AND_QUERY_QUALITY','runs':seen,
  'note':'1M BUILD-only on historical H85 Highway; Stage B one-Stock anchor separately passed. NEW 24 graphs have NOT been searched; no exact same-graph/quality claim from graph SHA.'},first=True)
 print(TAG+'_NATIVE_24_BUILDS_COMPLETE_AUDIT_REQUIRED',flush=True)

def parse_time(txt):
 m=re.search(r'^\s*Elapsed \(wall clock\) time \(h:mm:ss or m:ss\):\s*(\S+)',txt,re.M)
 need(m is not None,'TIME_WALL_MISSING')
 v=[float(x) for x in m.group(1).split(':')]
 need(len(v) in (2,3),'TIME_WALL_FORMAT')
 wall=60*v[0]+v[1] if len(v)==2 else 3600*v[0]+60*v[1]+v[2]
 def n(label):
  x=re.search(r'^\s*'+re.escape(label)+r':\s*(\d+)\s*$',txt,re.M)
  need(x is not None,'TIME_METRIC_MISSING_'+label)
  return int(x.group(1))
 need(0<wall<1e6,'INVALID_WALL')
 return {'wall_seconds':wall,'max_rss_KiB':n('Maximum resident set size (kbytes)'),
         'major_page_faults':n('Major (requiring I/O) page faults')}

def parse_stage(txt):
 stage={}
 for key,pat,count in [('buckets','buckets time',2),('leaf','build leaf time',2),('prune','Final prune time',1)]:
  vals=[]
  for line in txt.splitlines():
   if pat.lower() not in line.lower():continue
   mat=re.search(r'(?i)'+re.escape(pat)+r'\s*[:=]?\s*([0-9]+(?:\.[0-9]+)?)',line)
   if not mat:mat=re.search(r'([0-9]+(?:\.[0-9]+)?)\s*(?:s\s*)?'+re.escape(pat),line,re.I)
   if mat:vals.append(float(mat.group(1)))
  stage[key+'_seconds']=sum(vals) if len(vals)==count else None
  stage[key+'_line_count']=len(vals)
 stage['buckets_two_passes']=[int(x) for x in re.findall(r'^\s*Total buckets:\s*(\d+)\s*$',txt,re.M)]
 stage['clustering_comparisons_final']=list(map(int,re.findall(r'^\s*# of comparisons during clustering:\s*(\d+)\s*$',txt,re.M)))
 return stage

def audit_graph(path,expected_n):
 """Full graph audit: all million vertices, all IDs, all loops, ALL duplicate slots.

 10k-row bounded-memory sorting with UINT32_MAX as padding.  No source data
 or persisted graph bytes are changed.
 """
 import numpy as np
 path=Path(path);n=expected_n
 with path.open('rb') as f:hdr=f.read(8)
 need(len(hdr)==8,'GRAPH_SHORT_HEADER_'+path.name)
 nr,md=struct.unpack('<II',hdr)
 need(nr==n and md==64,'GRAPH_HEADER_'+path.name)
 deg=np.memmap(path,mode='r',dtype='<u4',offset=8,shape=(n,))
 need(bool(np.all(deg<=md)),'GRAPH_DEGREE_'+path.name)
 arcs=int(np.sum(deg,dtype=np.uint64))
 need(arcs>0 and path.stat().st_size==8+4*n+4*arcs,'GRAPH_EXACT_BYTES_'+path.name)
 offsets=np.empty(n+1,dtype=np.uint64);offsets[0]=0
 np.cumsum(deg,dtype=np.uint64,out=offsets[1:])
 edges=np.memmap(path,mode='r',dtype='<u4',offset=8+4*n,shape=(arcs,))
 need(bool(np.all(edges<n)),'GRAPH_BAD_NEIGHBOR_'+path.name)
 duplicate_rows=0
 for lo in range(0,n,10000):
  hi=min(n,lo+10000); aa=int(offsets[lo]);bb=int(offsets[hi]); d=deg[lo:hi]
  if bb==aa:continue
  rowids=np.repeat(np.arange(lo,hi,dtype=np.uint32),d.astype(np.int64))
  need(len(rowids)==bb-aa,'GRAPH_ROWS_EXPANSION')
  need(not bool(np.any(rowids==edges[aa:bb])),'GRAPH_SELFLOOP_'+path.name)
  start=offsets[lo:hi]-np.uint64(aa)
  colids=np.arange(bb-aa,dtype=np.int64)-np.repeat(start.astype(np.int64),d.astype(np.int64))
  padded=np.full((hi-lo,md),np.uint32(0xFFFFFFFF),dtype=np.uint32)
  padded[(rowids.astype(np.int64)-lo),colids]=edges[aa:bb]
  padded.sort(axis=1)
  dupl=np.any((padded[:,1:]==padded[:,:-1]) & (padded[:,:-1]!=np.uint32(0xFFFFFFFF)),axis=1)
  duplicate_rows+=int(dupl.sum())
  need(not bool(np.any(dupl)),'GRAPH_DUPLICATE_NEIGHBOR_FULL_'+path.name)
 return {'nodes':n,'degree_cap':md,'arcs':arcs,'max_observed_degree':int(deg.max()),
   'sha256':sha(path),'invalid_neighbor_count':0,'selfloops':0,
   'duplicate_neighbor_rows_full_graph':duplicate_rows,
   'duplicate_audit_scope':'FULL_1M_ROWS_ALL_GRAPH_ARCS'}

def sift_duplicate_pairs():
 """Exact raw 512-byte vector equality, one representative per duplicate class."""
 import hashlib
 pairs=[];seen={}
 with SIFT.open('rb') as f,mmap.mmap(f.fileno(),0,access=mmap.ACCESS_READ) as m:
  need(m[:8]==struct.pack('<II',1000000,128),'SIFT_FBIN_HEADER')
  for i in range(1000000):
   raw=m[8+i*512:8+(i+1)*512]
   digest=hashlib.blake2b(raw,digest_size=16).digest()
   prev=seen.get(digest)
   if prev is None:seen[digest]=i
   else:
    need(m[8+prev*512:8+(prev+1)*512]==raw,'DUP_HASH_COLLISION')
    pairs.append((prev,i))
 need(len(pairs)==14538,'SIFT_EXPECTED_DUPLICATE_PAIR_COUNT_DRIFT')
 return pairs

def sift_geometry(graph,pairs):
 import numpy as np
 path=Path(graph);n=1000000
 deg=np.memmap(path,mode='r',dtype='<u4',offset=8,shape=(n,))
 offsets=np.empty(n+1,dtype=np.uint64);offsets[0]=0
 np.cumsum(deg,dtype=np.uint64,out=offsets[1:])
 edges=np.memmap(path,mode='r',dtype='<u4',offset=8+4*n,shape=(int(offsets[-1]),))
 base=np.memmap(SIFT,mode='r',dtype='<f4',offset=8,shape=(n,128))
 def row(v):return edges[int(offsets[v]):int(offsets[v+1])]
 def d2(v,w):
  a=base[v].astype(np.float64); b=base[int(w)].astype(np.float64)
  diff=a-b;return float(np.dot(diff,diff))
 n0=row(0)
 ds=sorted(((int(v),d2(0,v)) for v in n0),key=lambda z:(z[1],z[0]))
 big=0
 for v in range(10000):
  ngh=row(v)
  if len(ngh)<2:continue
  a=d2(v,ngh[0]);b=d2(v,ngh[1])
  big+=int(a-b>10000 and a>1.5*max(b,1e-9))
 both=either=first=0
 for i,j in pairs:
  ri=row(i);rj=row(j);left=bool(np.any(ri==j));right=bool(np.any(rj==i))
  both+=int(left and right);either+=int(left or right)
  first+=int((len(ri)>0 and int(ri[0])==j) or (len(rj)>0 and int(rj[0])==i))
 return {'v0':{'degree':len(n0),'has_2':bool(np.any(n0==2)),'has_6':bool(np.any(n0==6)),
    'nearest':[{'id':j,'squared_l2':round(dist,3)} for j,dist in ds[:5]],
    'mean_neighbor_l2_squared':round(sum(x for _,x in ds)/len(ds),3) if ds else None},
   'big_inv_first_10000':big,'big_inv_is_diagnostic_not_hard_gate':True,
   'exact_duplicate_vectors':{'detected_representative_pairs':len(pairs),
    'both_directions_direct_neighbors':both,'at_least_one_direct_neighbor':either,
    'one_endpoint_first_neighbor':first,
    'either_end_retention_ratio':either/len(pairs) if pairs else None,
    'pair_definition':'One initial representative per exact 512-byte vector equivalence class, not all pairwise combinations'},
   'quality_diagnostic_flags':{'v0_has_2_and_6_with_degree_under64':len(n0)<64 and bool(np.any(n0==2)) and bool(np.any(n0==6)),
    'duplicate_either_end_retention_above_095':either/len(pairs)>=.95}}

def audit():
 mod,comp,_=preflight();pre=js(NEW/'preregister.json');recheck_links()
 full=js(NEW/'full1m_manifest.json')
 need(full['status']=='OFF18_ON6_BUILT_PENDING_GRAPH_STRUCTURE_AND_QUERY_QUALITY','FULL_STATUS')
 need(len(full['runs'])==24 and len(pre['jobs'])==24,'RUNS_24')
 pairs=sift_duplicate_pairs()
 validated=[]
 for job,record in zip(jobs(),full['runs']):
  good=guarded_output(mod,job)
  need(record==good,'MANIFEST_RECORD_CHANGED_'+label(job))
  structure=audit_graph(record['graph'],1000000)
  stdout=Path(record['stdout']).read_text(errors='replace');timing=parse_time(Path(record['timefile']).read_text(errors='replace'))
  stage=parse_stage(stdout)
  if job['mode']=='off':need(timing['max_rss_KiB']>0,'OFF_MAX_RSS_MISSING_'+label(job))
  geometry=sift_geometry(record['graph'],pairs) if job['dataset']=='SIFT1M' else None
  checked={'name':label(job),'arm':job['arm'],'mode':job['mode'],'rep':job['rep'],
    'dataset':job['dataset'],'graph':structure,'timing':timing,'stage':stage,
    'sift_quality_diagnostic':geometry,'original_elf_sha':record['elf_sha'],
    'search_on_new_graph_NOT_DONE':True}
  validated.append(checked)
  print(TAG+'_GRAPH_AUDIT_PASS',label(job),'arcs',structure['arcs'],
    'v0degree',geometry['v0']['degree'] if geometry else 'NA',
    'duplicates',geometry['exact_duplicate_vectors']['either_end_retention_ratio'] if geometry else 'NA',flush=True)
 means=[]
 for dataset in ('SIFT1M','MS-Turing1M'):
  for arm in ARMS:
   a=[x for x in validated if x['dataset']==dataset and x['arm']==arm and x['mode']=='off']
   need(len(a)==3,'OFF_REPS_MISSING_'+dataset+'_'+arm)
   means.append({'dataset':dataset,'arm':arm,'repetitions':3,
    'wall_s_mean':sum(x['timing']['wall_seconds'] for x in a)/3,
    'rss_KiB_mean':sum(x['timing']['max_rss_KiB'] for x in a)/3,
    'major_faults_by_rep':[x['timing']['major_page_faults'] for x in a],
    'stage_leaf_seconds_mean':sum(x['stage']['leaf_seconds'] for x in a)/3 if all(x['stage']['leaf_seconds'] is not None for x in a) else None})
 result={'status':'V13_H85_24GRAPH_BUILD_WORK_AND_FULL_STRUCTURAL_AUDIT_PASS__NEW_SEARCH_QUALITY_PENDING',
  'runs':validated,'off_group_means':means,'prior_StageB_report_sha':STAGEB_SHA,
  'known_StageB_stock_anchor_graph_sha':STAGEB_GRAPH_SHA,
  'graph_sha_policy':'Graph SHA locked within each graph receipt, NOT required equal across branches or replications.',
  'sift_diagnostics':'v0/zero-distance duplicate statistics and big inversions are diagnostics, not substitute for Recall. All original graph bytes remain immutable.',
  'limitations':['No Search Recall/QPS performed on these 24 new graphs.','Three OFF repetitions, not a hypothesis test.',
   'Stage B Stock1M independent anchor NOT used as performance repetition.',
   'Old H85 Highway still has simultaneous-subnormal tie ordering differences under DAZ.',
   'Stock Highway internal SIMD comparisons/moves not measured; no false zero counters.'],
  'full_manifest_sha256':sha(NEW/'full1m_manifest.json'),'source_manifest_sha256':ORIG_SRC_SHA,
  'Highway_commit':H85_COMMIT}
 atomic(NEW/'audit1m_buildonly.json',result,first=True)
 print(TAG+'_AUDIT_PASS_24_H85_HIGHWAY_GRAPHS_FULL_STRUCTURAL_SIFT_GEOMETRY__NEW_SEARCH_PENDING',flush=True)
 print(TAG+'_AUDIT_REPORT',NEW/'audit1m_buildonly.json','sha256',sha(NEW/'audit1m_buildonly.json'),flush=True)
 for x in means:print(TAG+'_EVIDENCE_MEAN_OFF',x['dataset'],x['arm'],'wall_s',round(x['wall_s_mean'],4),'rss_KiB',round(x['rss_KiB_mean'],1),'stage_leaf_s',round(x['stage_leaf_seconds_mean'],4) if x['stage_leaf_seconds_mean'] is not None else 'UNPARSED',flush=True)

def selftest():
 a=jobs();need(len(a)==24 and len({label(v) for v in a})==24,'SELFTEST_JOBS')
 need(sum(x['mode']=='off' and x['cpu']==4 for x in a)==18,'SELFTEST_OFF')
 need(sum(x['mode']=='on' and x['cpu']==1 for x in a)==6,'SELFTEST_ON')
 need(len({x['dataset'] for x in a})==2,'SELFTEST_DATASETS')
 from tempfile import TemporaryDirectory
 with TemporaryDirectory(prefix='r90_p0a_v12_graph_test_') as td:
  p=Path(td)/'graph'
  p.write_bytes(struct.pack('<II',3,64)+struct.pack('<III',1,1,0)+struct.pack('<II',1,2))
  need(audit_graph(p,3)['arcs']==2,'SELFTEST_GRAPH_FIXTURE')
  p.write_bytes(struct.pack('<II',3,64)+struct.pack('<III',1,1,0)+struct.pack('<II',99,2))
  try:audit_graph(p,3)
  except RuntimeError as e:need('GRAPH_BAD_NEIGHBOR' in str(e),'SELFTEST_GRAPH_BAD_ID')
  else:need(False,'SELFTEST_GRAPH_BAD_ID_NOT_HELD')
  p.write_bytes(struct.pack('<II',3,64)+struct.pack('<III',2,1,0)+struct.pack('<III',1,1,2))
  try:audit_graph(p,3)
  except RuntimeError as e:need('GRAPH_DUPLICATE_NEIGHBOR_FULL' in str(e),'SELFTEST_GRAPH_DUP_BAD')
  else:need(False,'SELFTEST_GRAPH_DUP_NOT_HELD')
 need(parse_time('Elapsed (wall clock) time (h:mm:ss or m:ss): 0:35.45\nMaximum resident set size (kbytes): 123456\nMajor (requiring I/O) page faults: 0\n')['wall_seconds']==35.45,'TIME_PARSER')
 need(parse_stage('buckets time: 3\nbuckets time: 4\nbuild leaf time: 5\nbuild leaf time: 6\nFinal prune time: 2\n')['leaf_seconds']==11,'STAGE_PARSER')
 print(TAG+'_SELFTEST_PASS_24_JOB_FULL_GRAPH_INVALID_DUPLICATE_ID_TIME_STAGE_NO_SOURCE_MODIFICATION',flush=True)

def main():
 a=argparse.ArgumentParser();a.add_argument('phase',choices=['selftest','preflight','prepare','run','audit']);arg=a.parse_args()
 try:globals()[arg.phase if arg.phase!='prepare' else 'prep']()
 except Exception as ex:
  print(TAG+'_ERROR',repr(ex),file=sys.stderr,flush=True);raise SystemExit(2)

if __name__=='__main__':main()
