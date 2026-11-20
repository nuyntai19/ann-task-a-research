#!/usr/bin/env python3
"""R90 P0A v1.2: SEARCH-ONLY fixed-beam quality SCREEN of 18 NEW 1M OFF graphs.

Uses SHA-pinned native evaluators already present from earlier research; no BUILD or
source/binary modification, no new evaluator compile. This is a quality SCREEN
at fixed tested beams, *not* a formal matched-Recall latency equivalence test.
MS-Turing evaluator's legacy avg_cmps may overflow at beam 896: intentionally
excluded from the computed comparison. QPS is internal native Search QPS; use
1CPU0, identical query/GT/evaluator within each dataset.

Phases --selftest, --preflight, --run, --audit.
"""
from __future__ import annotations
import argparse,hashlib,json,math,os,pathlib,re,struct,subprocess,sys,statistics,time,tempfile
H=pathlib.Path.home();ROOT=H/'ann-task-a';R90=ROOT/'experiments/R90'
SRC=R90/'r90_p0a_v12_pinned_six_elf_full1m_buildonly'
OUT=R90/'r90_p0a_v12_18graph_quality_screen_v1'
TAG='R90_P0A_V12_SEARCH_SCREEN_V1'
PIN={
 'audit':'dd90ce5c892e88235c1b611809ca9d2b43801ecd6d887ccb0f0ae75c49718f97',
 'full':'4917142a7dcb5e6bab06bd4b8724f3bfac854bdcfbde2c5bc932220335fd6692',
 'preregister':'8c9bb4fceebadd2dbd99d7b9a32993f0cd5e4da20de80cfd946535f226493304',
 'native_log':'720d04ecb5ab00ad25a05f449c65468a84b743db4a5f2257ed741d6404c9d43d'
}
DATA={
 'SIFT1M':{
 'base':ROOT/'data/sift1m.fbin','query':ROOT/'data/sift1m_queries.fbin',
 'gt':ROOT/'data/sift1m_gt.ibin',
 'base_sha':'8c7b3d999ba3133f865af72df078f77c2d248fdb80571d7ea1f1bb8e1750658e',
 'query_sha':'9b0082b67d0ac55b4c7d42216560344567ad87ce3e75a9d5214a0762f1c15d65',
 'gt_sha':'047418d19f3981e4fc2dd28ae3b6f72fa7108f40d9336bd2d80b07829885ba13',
 'dims':128,'nqueries':10000,'gt_k':100,'beams':(10,20,40,80,160),
 'evaluator':ROOT/'experiments/H70/build-r70/algorithms/PipNN/r72_graph_recall',
 'evaluator_sha':'3c2294efa1d7fb5d89c79ca5bf9c1eaca86247f7246e6d6d7c6c94549d08ed57',
 },
 'MS-Turing1M':{
 'base':ROOT/'data/MSTuring_1M_v1/base.1M.fbin',
 'query':ROOT/'data/MSTuring_1M_v1/query.public.100K.fbin',
 'gt':ROOT/'data/MSTuring_1M_v1/groundtruth.public.100K.ibin',
 'base_sha':'44e83e1dd4c65999b75873101adc5ac06ca900d259a2befd05c2c3aa28ff4042',
 'query_sha':'48d087a17bec15a5ec9ea526fe9bd14ac31bbbb5cd200817b341adbb77695644',
 'gt_sha':'fa5acf5ab262b42355296e99f920e6aa863f48820ca6f70fa37ca7966634c344',
 'dims':100,'nqueries':100000,'gt_k':100,'beams':(384,896),
 'evaluator':ROOT/'experiments/R86/msturing_1m_eval/r86_msturing1m_graph_recall_v4_highbeam',
 'evaluator_sha':'bb6576ad3e1e0cc770535aa06355c664993ca70bd1170d6dd4d202ab5767e144',
 }
}
RX=re.compile(r'^R72_RECALL_ROW\s+beam=(\d+)\s+recall=([+\-0-9.eE]+)\s+qps=([+\-0-9.eE]+)\s+avg_cmps=([+\-0-9.eE]+)\s+avg_visited=([+\-0-9.eE]+)\s*$',re.M)

def gate(x,label):
 if not x:raise RuntimeError(TAG+'_HOLD_'+label)
def sha(path):
 h=hashlib.sha256()
 with pathlib.Path(path).open('rb') as f:
  for part in iter(lambda:f.read(4<<20),b''):h.update(part)
 return h.hexdigest()
def pinned(path,s,label):
 p=pathlib.Path(path);gate(p.is_file() and not p.is_symlink(),'MISSING_OR_SYMLINK_'+label)
 gate(sha(p)==s,'SHA_'+label)
def parse(stdout,dataset):
 spec=DATA[dataset];rows={}
 gate(stdout.count('R72_RECALL_INPUT_PASS graph_nodes=1000000 queries='+str(spec['nqueries']))==1,'EVAL_INPUT_'+dataset)
 gate(stdout.count('R72_RECALL_EVAL_PASS')==1,'EVAL_FINAL_PASS_'+dataset)
 for m in RX.finditer(stdout):
  beam=int(m.group(1));nums=[float(m.group(j)) for j in range(2,6)]
  gate(beam in spec['beams'] and beam not in rows,'BEAM_DUP_'+dataset)
  rec,qps,cmps,visited=nums
  gate(all(math.isfinite(x) for x in nums) and 0<=rec<=1 and qps>0 and visited>=0,'EVAL_NONFINITE_'+dataset)
  rows[beam]={'recall_at10':rec,'qps':qps,'latency_us_proxy':1e6/qps,
              'avg_visited':visited,
              'avg_cmps_legacy_raw_NOT_FOR_COMPARISON':cmps if dataset=='MS-Turing1M' else None,
              'avg_cmps_sift_only':cmps if dataset=='SIFT1M' else None,
              'reaches_099':rec>=0.99,'reaches_0998':rec>=0.998}
 gate(tuple(rows)==tuple(spec['beams']),'BEAM_GRID_MISMATCH_'+dataset)
 return {str(k):rows[k] for k in spec['beams']}
def fbin(path,n,dim):
 with path.open('rb') as f:header=f.read(8)
 gate(len(header)==8 and struct.unpack('<II',header)==(n,dim),'FBIN_HEADER_'+path.name)
 gate(path.stat().st_size==8+n*dim*4,'FBIN_BYTES_'+path.name)
def gt_shape(path,n,k):
 with path.open('rb') as f:hdr=f.read(8)
 gate(len(hdr)==8 and struct.unpack('<II',hdr)==(n,k),'GT_HEADER_'+path.name)
 gate(path.stat().st_size==8+n*k*8,'GT_BYTES_'+path.name)
def graph_header(path):
 with path.open('rb') as f:
  gate(struct.unpack('<II',f.read(8))==(1000000,64),'GRAPH_HEADER_'+path.name)
  import array
  ar=array.array('I');ar.frombytes(f.read(4*1000000))
 gate(len(ar)==1000000 and max(ar)<=64,'GRAPH_DEGREES_'+path.name)
 arcs=sum(ar)
 gate(path.stat().st_size==8+4*1000000+4*arcs,'GRAPH_BYTES_'+path.name)
 return arcs
def load_json(path):
 gate(path.is_file() and not path.is_symlink(),'MISSING_'+path.name)
 return json.loads(path.read_text())
def atomic(path,obj):
 path=pathlib.Path(path);gate(not path.exists() and not path.is_symlink(),'EXISTS_'+path.name)
 tmp=path.with_name(path.name+'.part');gate(not tmp.exists(),'PART_EXISTS_'+path.name)
 with tmp.open('x') as f:
  json.dump(obj,f,indent=2,sort_keys=True,allow_nan=False)
  f.write('\n');f.flush();os.fsync(f.fileno())
 os.replace(tmp,path)
def build_rows(require_empty_output=True):
 pinned(SRC/'audit1m_buildonly.json',PIN['audit'],'AUDIT')
 pinned(SRC/'full1m_manifest.json',PIN['full'],'FULL_MANIFEST')
 pinned(SRC/'preregister.json',PIN['preregister'],'PREREG')
 pinned(H/'R90_P0A_V12_PINNED_SIX_ELF_BUILDONLY.log',PIN['native_log'],'NATIVE_LOG')
 audit=load_json(SRC/'audit1m_buildonly.json');full=load_json(SRC/'full1m_manifest.json');prereg=load_json(SRC/'preregister.json')
 gate(audit['status']=='NATIVE_24_GRAPH_SHA_STRUCTURE_PASS__SEARCH_RECALL_QPS_NOT_MEASURED','AUDIT_STATE')
 gate(len(full['runs'])==24 and len(audit['runs'])==24 and len(prereg['jobs'])==24,'RUN_COUNT')
 gate(audit['full_manifest_sha256']==PIN['full'],'MANIFEST_LINK')
 by_name={a['name']:a for a in audit['runs']};rows={}
 for run in full['runs']:
  if run['mode']!='off':continue
  name=f"{run['dataset']}_{run['arm']}_{run['mode']}_r{run['rep']}"
  gate(name not in rows and name in by_name,'RUN_NAME_'+name)
  target=by_name[name]
  gate(target['graph']['sha256']==run['graph_sha'],'AUDIT_GRAPH_SHA_'+name)
  gate(target['graph']['invalid_neighbor_count']==0 and target['graph']['selfloops']==0 and target['graph']['duplicate_neighbor_rows_in_1024_deterministic_sample']==0,'GRAPH_STRUCTURE_'+name)
  path=pathlib.Path(run['graph'])
  gate(path.is_file() and not path.is_symlink() and path.resolve().parent==(SRC/'graphs').resolve(),'GRAPH_PATH_'+name)
  gate(sha(path)==run['graph_sha'],'GRAPH_SHA_'+name)
  gate(graph_header(path)==target['graph']['arcs'],'GRAPH_ARCS_'+name)
  rows[name]={'name':name,'dataset':run['dataset'],'arm':run['arm'],'rep':run['rep'],'graph_path':str(path),'graph_sha256':run['graph_sha'],'arcs':target['graph']['arcs']}
 gate(len(rows)==18,'OFF_GRAPH_COUNT')
 for ds,s in DATA.items():
  for key in ['base','query','gt','evaluator']:
   pinned(s[key],s[key+'_sha'],ds+'_'+key)
  fbin(s['base'],1000000,s['dims']);fbin(s['query'],s['nqueries'],s['dims']);gt_shape(s['gt'],s['nqueries'],s['gt_k'])
 gate(0 in os.sched_getaffinity(0),'CPU0_NOT_ALLOWED')
 if require_empty_output: gate(not OUT.exists() and not OUT.is_symlink(),'OUTPUT_EXISTS')
 print(TAG+'_PREFLIGHT_PASS_18_SHA_GRAPHS_TWO_PINNED_EVALUATORS_TWO_QUERY_GT_SETS',flush=True)
 return rows

def plan(rows):
 jobs=[]
 for ds in DATA:
  for rep in (1,2,3):
   for arm in ('stock','h17','fast'):
    name=f'{ds}_{arm}_off_r{rep}'
    gate(name in rows,'PLANNED_JOB_MISSING_'+name)
    jobs.append(rows[name])
 return jobs

def selftest():
 examples={
  'SIFT1M':"R72_RECALL_INPUT_PASS graph_nodes=1000000 queries=10000 gt_k=100\n"+''.join(f'R72_RECALL_ROW beam={b} recall=0.99000000 qps=1000.0000 avg_cmps=1000 avg_visited=88\n' for b in DATA['SIFT1M']['beams'])+'R72_RECALL_EVAL_PASS\n',
  'MS-Turing1M':"R72_RECALL_INPUT_PASS graph_nodes=1000000 queries=100000 gt_k=100\n"+''.join(f'R72_RECALL_ROW beam={b} recall=0.99850000 qps=1000.0000 avg_cmps=0 avg_visited=700\n' for b in DATA['MS-Turing1M']['beams'])+'R72_RECALL_EVAL_PASS\n'}
 for ds,s in examples.items():
  v=parse(s,ds);gate(len(v)==len(DATA[ds]['beams']),'SELFTEST_ROWS')
  try:parse(s.replace('R72_RECALL_EVAL_PASS',''),ds)
  except RuntimeError:pass
  else:gate(False,'SELFTEST_MISSING_SUCCESS_MISSED')
  old='recall='+s.split('recall=')[1].split()[0]
  try:parse(s.replace(old,'recall=nan',1),ds)
  except RuntimeError:pass
  else:gate(False,'SELFTEST_BAD_NUMERIC_MISSED')
 with tempfile.TemporaryDirectory() as d:
  p=pathlib.Path(d)/'x.json';atomic(p,{'z':1})
  try:atomic(p,{'z':2})
  except RuntimeError:pass
  else:gate(False,'SELFTEST_NO_OVERWRITE')
 print(TAG+'_SELFTEST_PASS_FIXED_BEAM_QUERY_GT_PARSER_NO_BUILD',flush=True)
def run():
 rows=build_rows(require_empty_output=False)
 jobs=plan(rows)
 if not OUT.exists():
  OUT.mkdir(parents=True,exist_ok=False);(OUT/'logs').mkdir()
  atomic(OUT/'preregister.json',{'status':'SEARCH_FIXED_BEAM_SCREEN_NOT_MATCHED_EQUIVALENCE','jobs':jobs,'data':{ds:{k:str(v) if isinstance(v,pathlib.Path) else v for k,v in s.items()} for ds,s in DATA.items()},'evaluator_cmps_note':'MS v4 highbeam raw avg_cmps invalid/overflow; ignore. For MS use Counter64 diagnostic separately.','search_only':True,'cpu':0})
 else:
  gate(OUT.is_dir() and not OUT.is_symlink(),'OUTPUT_DIR_BAD')
  gate((OUT/'logs').is_dir() and not (OUT/'full_manifest.json').exists(),'PARTIAL_STATE_BAD')
  prior=load_json(OUT/'preregister.json')
  gate(prior['status']=='SEARCH_FIXED_BEAM_SCREEN_NOT_MATCHED_EQUIVALENCE' and prior['jobs']==jobs,'PREREG_DRIFT')
 progress={'status':'RUNNING','runs':[]}
 for j,row in enumerate(jobs,1):
  ds=row['dataset'];spec=DATA[ds];name=row['name'];stdout_path=OUT/'logs'/(name+'.stdout');stderr_path=OUT/'logs'/(name+'.stderr')
  receipt=OUT/(name+'.json')
  if receipt.exists():
   done=load_json(receipt)
   gate(done['name']==name and done['graph_sha256']==row['graph_sha256'] and done['evaluator_sha256']==spec['evaluator_sha'] and done['status']=='NATIVE_QUERY_SEARCH_PASS','RESUME_RECORD_'+name)
   gate(stdout_path.is_file() and stderr_path.is_file() and sha(stdout_path)==done['stdout_sha'] and sha(stderr_path)==done['stderr_sha'],'RESUME_LOG_SHA_'+name)
   gate(parse(stdout_path.read_text(),ds)==done['beams'],'RESUME_PARSE_'+name)
   progress['runs'].append(done)
   print(TAG+'_RESUME_VERIFIED',name,flush=True)
   continue
  gate(not stdout_path.exists() and not stderr_path.exists() and not receipt.exists(),'ORPHAN_OUTPUT_'+name)
  cmd=['taskset','-c','0',str(spec['evaluator']),str(row['graph_path']),str(spec['base']),str(spec['query']),str(spec['gt'])]
  if ds=='MS-Turing1M':cmd.append(','.join(map(str,spec['beams'])))
  env=dict(os.environ);env.update(PARLAY_NUM_THREADS='1',OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='1')
  print(TAG+'_SEARCH_START',j,'of18',name,'beams',list(spec['beams']),flush=True)
  t0=time.perf_counter()
  with stdout_path.open('x') as fo,stderr_path.open('x') as fe:
   cp=subprocess.run(cmd,stdout=fo,stderr=fe,env=env,check=False)
  elapsed=time.perf_counter()-t0
  gate(cp.returncode==0,'NATIVE_EVAL_RC_'+name+'_'+str(cp.returncode))
  parsed=parse(stdout_path.read_text(),ds)
  gate(sha(row['graph_path'])==row['graph_sha256'],'GRAPH_DRIFT_AFTER_SEARCH_'+name)
  progress['runs'].append({'name':name,'dataset':ds,'arm':row['arm'],'rep':row['rep'],'graph_sha256':row['graph_sha256'],'evaluator_sha256':spec['evaluator_sha'],'beams':parsed,'stdout_sha':sha(stdout_path),'stderr_sha':sha(stderr_path),'wall_elapsed_s':elapsed,'status':'NATIVE_QUERY_SEARCH_PASS'})
  atomic(OUT/(name+'.json'),progress['runs'][-1])
  print(TAG+'_SEARCH_PASS',name,'recall_by_beam',{b:round(q['recall_at10'],6) for b,q in parsed.items()},flush=True)
  # Persist progress after each successful graph without overwriting a receipt.
  atomic(OUT/(f'progress_{j:02d}.json'),progress)
 progress['status']='18_GRAPH_FIXED_BEAM_SEARCH_NATIVE_COMPLETE_AUDIT_REQUIRED'
 atomic(OUT/'full_manifest.json',progress)
 print(TAG+'_RUN_18_GRAPH_COMPLETE_AUDIT_REQUIRED',flush=True)
def audit():
 rows=build_rows(require_empty_output=False)
 full=load_json(OUT/'full_manifest.json')
 gate(full['status']=='18_GRAPH_FIXED_BEAM_SEARCH_NATIVE_COMPLETE_AUDIT_REQUIRED','FULL_STATUS')
 gate(len(full['runs'])==18,'FULL_RUNS')
 groups={}; seen=set()
 for r in full['runs']:
  name=r['name'];gate(name not in seen,'DUP_RUN');seen.add(name)
  gate(name in rows and r['graph_sha256']==rows[name]['graph_sha256'],'GRAPH_ANCHOR_'+name)
  gate(r['status']=='NATIVE_QUERY_SEARCH_PASS','NATIVE_STATUS_'+name)
  ds=r['dataset'];spec=DATA[ds]
  gate(r['evaluator_sha256']==spec['evaluator_sha'],'EVAL_SHA_'+name)
  gate(r['stdout_sha']==sha(OUT/'logs'/(name+'.stdout')),'STDOUT_SHA_'+name)
  gate(r['stderr_sha']==sha(OUT/'logs'/(name+'.stderr')),'STDERR_SHA_'+name)
  parsed=parse((OUT/'logs'/(name+'.stdout')).read_text(),ds)
  gate(parsed==r['beams'],'REPARSE_'+name)
  for b in spec['beams']:
   groups.setdefault(ds,{}).setdefault(r['arm'],{}).setdefault(b,[]).append(parsed[str(b)])
 gate(set(seen)==set(rows),'MISSING_GRAPH_SEARCH')
 out={}
 for ds,dd in groups.items():
  out[ds]={}
  for arm,arms in dd.items():
   sums={}
   for b,vals in arms.items():
    gate(len(vals)==3,'GROUP_N_'+ds+arm+str(b))
    sums[str(b)]={'recall_mean':statistics.mean(v['recall_at10'] for v in vals),'recall_min':min(v['recall_at10'] for v in vals),'recall_max':max(v['recall_at10'] for v in vals),'qps_mean':statistics.mean(v['qps'] for v in vals),'qps_median':statistics.median(v['qps'] for v in vals),'qps_range':[min(v['qps'] for v in vals),max(v['qps'] for v in vals)],'n_graphs':3}
   targets={}
   for t,threshold in [('0.99',.99),('0.998',.998)]:
    eligible=[b for b,v in arms.items() if min(x['recall_at10'] for x in v)>=threshold]
    targets[t]={'min_tested_beam_all_3_graphs_meet_threshold':min(eligible) if eligible else None,'tested_beam_grid':list(spec['beams']),'not_exact_matched_recall':True}
   out[ds][arm]={'beams':sums,'target_screen':targets}
 record={'status':'NATIVE_18_GRAPH_SEARCH_FIXED_BEAM_SCREEN_PASS__MATCHED_RECALL_LATENCY_NOT_PROVEN','source_build_full_manifest_sha256':PIN['full'],'original_build_audit_sha256':PIN['audit'],'full_search_manifest_sha256':sha(OUT/'full_manifest.json'),'report':out,'limitations':['These are fixed tested beam grids, not a continuous matched-Recall optimization.','SIFT1M grid: 10,20,40,80,160; may not bracket recall=0.998.','MS-Turing1M grid: 384,896 only, 100K queries; legacy avg_cmps may overflow and MUST NOT be used.','Only one native Search trial per graph; QPS sensitive to scheduling/thermal state, need repeated paired QPS if formal timing equivalence is desired.','Legacy Stock packed-double FTZ/DAZ vulnerability may impact graph correctness.','Quality gate not a proof of same-input Top2 equivalence.']}
 atomic(OUT/'quality_screen_summary.json',record)
 print(TAG+'_AUDIT_PASS_18_FROZEN_GRAPH_NATIVE_SEARCH_SCREEN_QUALITY_ONLY',flush=True)
 print(TAG+'_AUDIT_REPORT',str(OUT/'quality_screen_summary.json'),'sha256',sha(OUT/'quality_screen_summary.json'),flush=True)
def main():
 ap=argparse.ArgumentParser()
 ap.add_argument('phase',choices=('selftest','preflight','run','audit'))
 args=ap.parse_args()
 if args.phase=='selftest':selftest()
 elif args.phase=='preflight':build_rows()
 elif args.phase=='run':run()
 else:audit()
if __name__=='__main__':
 try:main()
 except Exception as e:
  print(TAG+'_ERROR',str(e),flush=True)
  sys.exit(2)
