#!/usr/bin/env python3
"""R90 P0A v1.2 exploratory SAME-COMPILER six-ELF 1M BUILD evidence.

Native Ubuntu ONLY. Read-only with respect to prior P0A v1.1 trees, ELF, graphs,
original logs. Reuses, does not compile, the six pinned v1.1 binaries. Does NOT
run Search or certify quality and never waives the historical v1.1 audit.

Reconstructed 1M BUILD experiment has real FTZ/DAZ + Stage1 nondeterminism
risk; therefore every graph is checked individually, not cross-arm SHA equality.
"""
from __future__ import annotations
import argparse, hashlib, importlib.util, json, os, re, shutil, struct, sys
from pathlib import Path

HOME=Path.home(); ROOT=HOME/'ann-task-a'; R90=ROOT/'experiments/R90'
OLD=R90/'r90_p0a_unified_1m_three_arm_v1_1'
NEW=R90/'r90_p0a_v12_pinned_six_elf_full1m_buildonly'
PROBE=R90/'r90_p0a_ftz_stage1_probe_v1/probe_report.json'
SCRIPT=HOME/'Downloads/r90_p0a_unified_1m_three_arm_v1_1.py'
SIFT10K=R90/'r90_p38_h17_top2_prefilter_native_v2/data/sift10k.fbin'
ORIG_PY_SHA='fa9cdc09b3f447161f5c1f65382b15a0bc9645f425a679b73ca26f5ce8abecf0'
ORIG_SRC_SHA='6e5d82c4ca331476240950afedfad970d8358fc7252d0d2b8b9ac441e1afb298'
ORIG_PILOT_SHA='b45ab2841b6f8ade980735d9b5414b921366eeab65d48dd52e770b8aef5947c9'
ORIG_DIAG_SHA='cffe7fb508b3d5550e9ea7a41a11fa41f101b23a0034cd6b4c051a15fec9e519'
PROBE_SHA='1ecaa86646921e3abd600ba3108aa6537737813f065d9c1cc02e6966a8e48a31'
COMPILER_SHA='1353e9bdd29a7295c7226bf6c63abccce056d8cac31f112e5cdbecc3f28c2769'
SIFT10K_SHA='94320c4336a35f046de768a24ada57aa8998f511df9aa2a7c72fe9ed8c67c1f5'
ARMS=('stock','h17','fast');MODES=('off','on')
TAG='R90_P0A_V12_BUILDONLY'


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
 need(exists_regular(SCRIPT) and sha(SCRIPT)==ORIG_PY_SHA,'ORIGINAL_PY_SHA')
 spec=importlib.util.spec_from_file_location('p0a_original_frozen_v11',SCRIPT)
 need(spec is not None and spec.loader is not None,'ORIGINAL_IMPORT')
 mod=importlib.util.module_from_spec(spec)
 spec.loader.exec_module(mod)
 need(mod.OUT==OLD and set(mod.ARMS)==set(ARMS) and set(mod.MODES)==set(MODES),'ORIGINAL_API')
 return mod

def preflight():
 mod=original_module()
 need(sha(OLD/'source_manifest.json')==ORIG_SRC_SHA,'SOURCE_MANIFEST_SHA')
 need(sha(OLD/'pilot_manifest.json')==ORIG_PILOT_SHA,'PILOT_MANIFEST_SHA')
 need(sha(R90/'r90_p0a_v11_pilot_hold_diagnostic_v1/diagnostic_report.json')==ORIG_DIAG_SHA,'DIAGNOSTIC_SHA')
 need(sha(PROBE)==PROBE_SHA,'PROBE_NATIVE_SHA')
 need(sha(SIFT10K)==SIFT10K_SHA,'SIFT10K_DATA_SHA')
 manifest=js(OLD/'source_manifest.json')
 pilot=js(OLD/'pilot_manifest.json')
 probe=js(PROBE)
 comp=js(OLD/'compile_manifest.json')
 need(probe['status']=='NATIVE_HIGHWAY_PROBE_AND_THREE_REPS_EACH_ARM_COMPLETE__FULL1M_NOT_AUTHORIZED','PROBE_STATUS')
 hp=probe['highway_probe']
 need(hp['case_count']==126 and hp['bit_mutation_on']==32 and hp['bit_mutation_off']==0 and hp['mismatch_on']==36,'PROBE_WITNESS')
 need(len(probe['stage1_sift10k_repetitions'])==9,'NINE_STAGE1_REPS')
 need(comp['compiler_sha256']==COMPILER_SHA,'PIN_COMPILER_SHA')
 need(exists_regular(comp['cxx_binary']) and sha(comp['cxx_binary'])==COMPILER_SHA,'ACTUAL_COMPILER_SHA')
 need(set(comp['binaries'])=={a+'_'+m for a in ARMS for m in MODES},'SIX_BINARIES')
 pv=probe['source_pins']
 need(len(pilot['runs'])==6,'ORIGINAL_SIX_PILOT_GRAPHS')
 for arm in ARMS:
  for mode in MODES:
   key=arm+'_'+mode
   exe=oldbin(arm,mode)
   need(exists_regular(exe) and sha(exe)==comp['binaries'][key]==pv['previous_elf_shas'][key],'PIN_ELF_'+key)
   variant=next((r for r in manifest['variants'] if r['variant']==key),None)
   need(variant is not None,'SOURCE_VARIANT_'+key)
   need(mod.digest_tree(OLD/'source'/key)==variant['tree_sha256'],'SOURCE_TREE_'+key)
   pilot_record=next((r for r in pilot['runs'] if (r['arm'],r['mode'])==(arm,mode)),None)
   need(pilot_record is not None,'PILOT_RECORD_'+key)
   for name,path,expected in [('graph',pilot_record['graph'],pv['previous_source_graph_sha'][key]),
                              ('stdout',pilot_record['stdout'],pilot_record['stdout_sha']),
                              ('timefile',pilot_record['timefile'],pilot_record['timefile_sha'])]:
    need(exists_regular(path) and sha(path)==expected,'PILOT_'+name+'_SHA_'+key)
 for k,base in mod.BASES.items():
  need(exists_regular(base) and sha(base)==mod.BASE_SHAS[k],'DATA_SHA_'+k)
 need(not (NEW/'audit1m_buildonly.json').exists(),'ALREADY_AUDITED')
 # Bounded native resource gate: 1M peak RSS previously ~3 GiB, output worst-case graph volume up to 6.24 GB.
 need(shutil.disk_usage(R90).free >= 12*(1<<30),'DISK_HEADROOM_LT12GIB')
 meminfo=Path('/proc/meminfo')
 if meminfo.is_file():
  m=re.search(r'^MemAvailable:\s+(\d+)\s+kB',meminfo.read_text(),re.M)
  need(m is not None and int(m.group(1)) >= 8*(1<<20),'MEM_HEADROOM_LT8GIB')
 print(TAG+'_PREFLIGHT_PASS_SIX_ELF_SIX_SOURCE_SIX_10K_GRAPH_AND_FTZ_PROBE_1M_DATA_SHA',flush=True)
 return mod,comp,probe

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
 pin={'status':'EXPLORATORY_BUILD_ONLY_NO_SEARCH_QUALITY_CERTIFICATE','original_p0a_py_sha':ORIG_PY_SHA,'runner_sha256':sha(Path(__file__)),
      'original_source_manifest_sha':ORIG_SRC_SHA,'original_pilot_manifest_sha':ORIG_PILOT_SHA,
      'ftz_native_probe_sha':PROBE_SHA,'existing_elf_sha':dict(comp['binaries']),
      'compiler_sha':COMPILER_SHA,'data_shas':dict(mod.BASE_SHAS),
      'jobs':jobs(),'protocol':'New isolated 4CPU OFF 18 + 1CPU0 ON 6 BUILD runs using original P0A v1.1 native_one only; no graph SHA equality across arms, no quality claim.',
      'known_risks':['Controlled Highway FTZ/DAZ packed bit mutation; Stock can produce different graph SHA even with same Stage1 bucket counts.','H17/Fast are also bitwise inexact under DAZ for two zero-subnormal packed keys.', 'Recall@10 and QPS have not been tested on these new 1M graphs.']}
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
  dataset=job['dataset'];base=mod.BASES[dataset]
  record=mod.native_one(job['arm'],job['mode'],base,dataset,job['rep'],job['cpu'])
  need(record['threads']==job['cpu'],'CPU_MISMATCH')
  seen.append(record)
  atomic(NEW/'progress.json',{'status':f'{len(seen)}_OF_24_NATIVE_BUILD_RECORDS_SHA_VERIFIED','completed':seen})
  print(TAG+'_1M_BUILD_RECORD_PASS',len(seen),'of24',label(job),record['graph_sha'],flush=True)
 for job in jobs():guarded_output(mod,job)
 atomic(NEW/'full1m_manifest.json',{'status':'OFF18_ON6_BUILT_PENDING_GRAPH_STRUCTURE_AND_QUERY_QUALITY','runs':seen,
  'note':'1M BUILD-only, no ANN Search Recall/QPS measured. Never claim any arm quality equivalence from graph SHA.'},first=True)
 print(TAG+'_NATIVE_24_BUILDS_COMPLETE_AUDIT_REQUIRED',flush=True)

def audit_graph(path,expected_n):
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
 offsets=np.zeros(n+1,dtype=np.uint64)
 np.cumsum(deg,dtype=np.uint64,out=offsets[1:])
 edges=np.memmap(path,mode='r',dtype='<u4',offset=8+4*n,shape=(arcs,))
 need(bool(np.all(edges<n)),'GRAPH_BAD_NEIGHBOR_'+path.name)
 # Full self-loop test with bounded memory chunks; no per-vertex Python overhead.
 for lo in range(0,n,12000):
  hi=min(n,lo+12000)
  start=int(offsets[lo])
  end=int(offsets[hi])
  if end>start:
   sources=np.repeat(np.arange(lo,hi,dtype=np.uint32),deg[lo:hi].astype(np.int64))
   need(not bool(np.any(sources==edges[start:end])),'GRAPH_SELFLOOP_'+path.name)
 # Audit duplicates on a deterministic 1024-row sample; explicitly not full-graph proof.
 sampled=np.unique(np.linspace(0,n-1,min(n,1024),dtype=np.int64))
 dup_rows=0
 for i in sampled:
  a,b=int(offsets[i]),int(offsets[i+1])
  if b-a>1 and np.unique(edges[a:b]).size!=(b-a):dup_rows+=1
 need(dup_rows==0,'GRAPH_DUPLICATE_NEIGHBOR_SAMPLE_'+path.name)
 return {'nodes':n,'degree_cap':md,'arcs':arcs,'max_observed_degree':int(deg.max()),
  'sha256':sha(path),'invalid_neighbor_count':0,'selfloops':0,
  'duplicate_neighbor_rows_in_1024_deterministic_sample':dup_rows,
  'duplicate_audit_scope':'SAMPLED_ONLY_NOT_FULL_GRAPH'}

def audit():
 mod,comp,_=preflight();pre=js(NEW/'preregister.json');recheck_links()
 full=js(NEW/'full1m_manifest.json')
 need(full['status']=='OFF18_ON6_BUILT_PENDING_GRAPH_STRUCTURE_AND_QUERY_QUALITY','FULL_STATUS')
 need(len(full['runs'])==24 and len(pre['jobs'])==24,'RUNS_24')
 validated=[]
 for job,record in zip(jobs(),full['runs']):
  good=guarded_output(mod,job)
  need(record==good,'MANIFEST_RECORD_CHANGED_'+label(job))
  report=audit_graph(record['graph'],1000000)
  n=label(job)
  # No graph SHA cross-arm equality requirement. Even within-arm 4CPU differs by scheduler.
  validated.append({'name':n,'arm':job['arm'],'mode':job['mode'],'dataset':job['dataset'],
    'graph':report,'original_elf_sha':record['elf_sha'],'qps_not_measured':True})
  print(TAG+'_AUDIT_GRAPH_PASS',n,'arcs',report['arcs'],flush=True)
 data={'status':'NATIVE_24_GRAPH_SHA_STRUCTURE_PASS__SEARCH_RECALL_QPS_NOT_MEASURED',
  'runs':validated,'graph_sha_criterion':'Each graph checked against its original recorded bytes; never expect cross-arm SHA equality.',
  'requirements_before_scientific_claim':['SIFT1M and MS-Turing1M per-graph native evaluator with identical queries/GT and matched Recall@10.',
    'Validate actual counters for Stock source q_writes/sort calls and H17/Fast D6 + assignment taxonomy.',
    'Validate true same-input Top2 kernel equivalence for the relevant distance/duplicate-key domain.',
    'No Stock-H17/Fast causal graph claim from controlled synthetic FTZ witness alone.'],
  'ftz_probe_sha':PROBE_SHA,'original_source_manifest_sha':ORIG_SRC_SHA,
  'full_manifest_sha256':sha(NEW/'full1m_manifest.json')}
 atomic(NEW/'audit1m_buildonly.json',data,first=True)
 print(TAG+'_AUDIT_PASS_24_GRAPHS_BUILD_ONLY_QUALITY_SEARCH_PENDING',flush=True)
 print(TAG+'_AUDIT_REPORT',NEW/'audit1m_buildonly.json','sha256',sha(NEW/'audit1m_buildonly.json'),flush=True)

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
 print(TAG+'_SELFTEST_PASS_24_JOB_MATRIX_NO_OLD_SOURCE_MODIFICATION',flush=True)

def main():
 a=argparse.ArgumentParser();a.add_argument('phase',choices=['selftest','preflight','prepare','run','audit']);arg=a.parse_args()
 try:globals()[arg.phase if arg.phase!='prepare' else 'prep']()
 except Exception as ex:
  print(TAG+'_ERROR',repr(ex),file=sys.stderr,flush=True);raise SystemExit(2)

if __name__=='__main__':main()
