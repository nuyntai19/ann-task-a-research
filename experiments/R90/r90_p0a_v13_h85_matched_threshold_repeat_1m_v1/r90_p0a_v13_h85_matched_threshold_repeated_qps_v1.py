#!/usr/bin/env python3
"""R90 P0A v1.3 H85 | pinned dynamic-beam CALIBRATION + REPEATED QPS on 18 frozen OFF graphs.

NO build, NO compile, NO mutation of old evidence. One calibration native call per
frozen graph with a pre-registered grid, then three timing repetitions per graph,
with BOTH Recall-target beams in a SINGLE evaluator process (54 timing processes,
108 per-target metric rows). Minimum beam among tested grid where ALL three graph
realizations of a given arm meet a target on the SAME query/GT set.

This is threshold-qualified and NOT a claim of equal Recall, independent holdout,
p95 latency, or statistical non-inferiority. MS evaluator legacy avg_cmps ignored.
"""
from __future__ import annotations
import argparse,hashlib,importlib.util,json,math,os,pathlib,re,shutil,statistics,subprocess,sys,tempfile,time
H=pathlib.Path.home(); ROOT=H/'ann-task-a'; R90=ROOT/'experiments/R90'
TAG='R90_P0A_V13_H85_MATCHED_REPEAT_V1'
SCREEN_PY=H/'Downloads/r90_p0a_v13_h85_18graph_search_screen_v1.py'
SCREEN_PY_SHA='dcfe8d6f856b37ca149ee4a00b257f2af11d7ef757a24d99859634633c2191a6'
SCREEN=R90/'r90_p0a_v13_h85_18graph_quality_screen_v1'
SCREEN_SUM_SHA='861c8734cab66a6d2dcbcee9aca56a981ab364ea7e14e04e64e9177bf3ddd7a7'
SCREEN_MANIFEST_SHA='767c8b95dcf9f2e91bb06612b1c0d82ee9814ea3e6b220cd755601705a1738ed'
BUILD_AUDIT_SHA='9550858dcb763349ed5180b3b65577e48a600e54becc0ecb9c755970a4d4bbfb'
BUILD_MANIFEST_SHA='0c76f3e5bc3dc0d82f70aa1aadac9b26c5b0e8f4607f31d9aa6d8b0b0a4121c3'
SIFT_DYN=ROOT/'experiments/H85/r85_a1c_matched_search/r85_a1c_graph_recall'
SIFT_DYN_SHA='11587916ffd70143d6d5246bf8d2e26c1927b81bf8b3298fbc2014bfb6c64a4e'
SIFT_DYN_MANIFEST=ROOT/'experiments/H85/r85_a1c_matched_search/evaluator_manifest.json'
OUT=R90/'r90_p0a_v13_h85_matched_threshold_repeat_1m_v1'
BEAMS={'SIFT1M':(64,68,72,76,80,128,136,144,152,160),
       'MS-Turing1M':(336,352,368,384,832,848,864,880,896)}
ANCHORS={'SIFT1M':(80,160),'MS-Turing1M':(384,896)}
TARGETS={'0.99':0.99,'0.998':0.998}
TIMING_REPS=3
RX=re.compile(r'^R72_RECALL_ROW\s+beam=(\d+)\s+recall=([+\-0-9.eE]+)\s+qps=([+\-0-9.eE]+)\s+avg_cmps=([+\-0-9.eE]+)\s+avg_visited=([+\-0-9.eE]+)\s*$',re.M)

def gate(x,desc):
 if not x:raise RuntimeError(TAG+'_HOLD_'+desc)
def sha(p):
 h=hashlib.sha256()
 with pathlib.Path(p).open('rb') as f:
  for b in iter(lambda:f.read(4<<20),b''):h.update(b)
 return h.hexdigest()
def pinned(p,digest,why):
 p=pathlib.Path(p);gate(p.is_file() and not p.is_symlink(),'MISSING_OR_SYMLINK_'+why)
 gate(sha(p)==digest,'SHA_'+why)
def readj(p):
 p=pathlib.Path(p);gate(p.is_file() and not p.is_symlink(),'JSON_MISSING_OR_SYMLINK_'+p.name)
 return json.loads(p.read_text())
def writej(p,x):
 p=pathlib.Path(p);gate(not p.exists() and not p.is_symlink(),'OUTPUT_EXISTS_'+p.name)
 tmp=p.with_name(p.name+'.part');gate(not tmp.exists() and not tmp.is_symlink(),'PART_EXISTS_'+p.name)
 with tmp.open('x') as f:
  json.dump(x,f,indent=2,sort_keys=True,allow_nan=False);f.write('\n');f.flush();os.fsync(f.fileno())
 os.replace(tmp,p)
def parse(s,ds,beams):
 beams=tuple(beams)
 nq=10000 if ds=='SIFT1M' else 100000
 gate(s.count(f'R72_RECALL_INPUT_PASS graph_nodes=1000000 queries={nq}')==1,'EVAL_INPUT_'+ds)
 gate(s.count('R72_RECALL_EVAL_PASS')==1,'EVAL_COMPLETE_'+ds)
 if ds=='SIFT1M':
  gate(s.count('R85_A1C_DYNAMIC_BEAMS count=')==1,'SIFT_DYNAMIC_EVALUATOR_MARKER')
  gate(f'R85_A1C_DYNAMIC_BEAMS count={len(beams)}' in s,'SIFT_DYNAMIC_BEAM_COUNT')
 out={}
 for m in RX.finditer(s):
  b=int(m.group(1));v=[float(m.group(j)) for j in range(2,6)]
  gate(b in beams and b not in out,'WRONG_OR_DUP_BEAM_'+ds)
  rec,qps,cmps,visited=v
  gate(all(math.isfinite(x) for x in v) and 0<=rec<=1 and qps>0 and visited>=0,'BAD_METRIC_'+ds)
  out[str(b)]={'recall_at10':rec,'qps':qps,'latency_us_proxy':1e6/qps,'avg_visited':visited,
   'avg_cmps_sift_only':cmps if ds=='SIFT1M' else None,
   'ms_legacy_avg_cmps_IGNORED':None}
 gate(tuple(map(int,out))==beams,'BEAM_ORDER_OR_MISSING_'+ds)
 return out

def screen_module():
 pinned(SCREEN_PY,SCREEN_PY_SHA,'ORIGINAL_V13_SCREEN_RUNNER')
 spec=importlib.util.spec_from_file_location('r90_v13_h85_original_screen_SHA',SCREEN_PY)
 gate(spec is not None and spec.loader is not None,'IMPORT_SCREEN_SPEC')
 obj=importlib.util.module_from_spec(spec);spec.loader.exec_module(obj)
 return obj

def native_state(expect_new_output=False):
 mod=screen_module()
 graph_rows=mod.build_rows(require_empty_output=False)  # pinned full 18 graph SHA, 2 evaluators, query+GT
 pinned(SCREEN/'quality_screen_summary.json',SCREEN_SUM_SHA,'SCREEN_SUMMARY')
 pinned(SCREEN/'full_manifest.json',SCREEN_MANIFEST_SHA,'SCREEN_MANIFEST')
 ss=readj(SCREEN/'quality_screen_summary.json');mf=readj(SCREEN/'full_manifest.json')
 gate(ss['status']=='NATIVE_18_GRAPH_SEARCH_FIXED_BEAM_SCREEN_PASS__MATCHED_RECALL_LATENCY_NOT_PROVEN','ORIGINAL_SCREEN_STATUS')
 gate(ss['full_search_manifest_sha256']==SCREEN_MANIFEST_SHA,'SCREEN_MANIFEST_LINK')
 gate(ss['original_build_audit_sha256']==BUILD_AUDIT_SHA and ss['source_build_full_manifest_sha256']==BUILD_MANIFEST_SHA,'SCREEN_BUILD_PROVENANCE')
 gate(len(mf['runs'])==18 and set(x['name'] for x in mf['runs'])==set(graph_rows),'ORIGINAL_SCREEN_18_GRAPH_SET')
 for r in mf['runs']:
  n=r['name'];ds=r['dataset']
  gate(r['status']=='NATIVE_QUERY_SEARCH_PASS' and r['graph_sha256']==graph_rows[n]['graph_sha256'],'SCREEN_GRAPH_'+n)
  a=SCREEN/'logs'/(n+'.stdout');b=SCREEN/'logs'/(n+'.stderr')
  pinned(a,r['stdout_sha'],'SCREEN_STDOUT_'+n);pinned(b,r['stderr_sha'],'SCREEN_STDERR_'+n)
  gate(mod.parse(a.read_text(),ds)==r['beams'],'SCREEN_REPARSE_'+n)
 pinned(SIFT_DYN,SIFT_DYN_SHA,'H85_SIFT_DYNAMIC_EVAL')
 man=readj(SIFT_DYN_MANIFEST)
 gate(man.get('dynamic_evaluator_sha256')==SIFT_DYN_SHA,'SIFT_EVAL_MANIFEST_SHA')
 gate(0 in os.sched_getaffinity(0) and shutil.which('taskset'),'CPU_0_AFFINITY_TASKSET')
 txt=pathlib.Path('/proc/meminfo').read_text();m=re.search(r'^MemAvailable:\s+(\d+) kB',txt,re.M)
 gate(m and int(m.group(1))>=4*1024*1024,'AVAILABLE_MEMORY_LT_4GIB')
 gate(shutil.disk_usage(OUT.parent).free>=2*(1<<30),'FREE_DISK_LT_2GIB')
 if expect_new_output:gate(not OUT.exists() and not OUT.is_symlink(),'OUTPUT_ALREADY_EXISTS')
 print(TAG+'_PREFLIGHT_PASS_SCREEN_SHA_MANIFEST_18_GRAPH_SHA_DATA_GT_TWO_DYNAMIC_EVALUATORS',flush=True)
 return mod,graph_rows,mf,ss

def original_recall(mf,name,beam):
 r=next(x for x in mf['runs'] if x['name']==name)
 return r['beams'][str(beam)]['recall_at10']

def native(ds,row,beams,stem,mod):
 beams=tuple(beams)
 spec=mod.DATA[ds]
 eval_path=SIFT_DYN if ds=='SIFT1M' else spec['evaluator']
 stdout=OUT/'logs'/(stem+'.stdout');stderr=OUT/'logs'/(stem+'.stderr')
 gate(not stdout.exists() and not stderr.exists(),'ORPHAN_NATIVE_LOG_'+stem)
 cmd=['taskset','-c','0',str(eval_path),row['graph_path'],str(spec['base']),str(spec['query']),str(spec['gt']),','.join(map(str,beams))]
 env=dict(os.environ);env.update(PARLAY_NUM_THREADS='1',OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='1')
 t=time.perf_counter()
 with stdout.open('x') as a,stderr.open('x') as b:proc=subprocess.run(cmd,stdout=a,stderr=b,env=env,check=False)
 wall=time.perf_counter()-t
 gate(proc.returncode==0,'NATIVE_EXIT_'+stem+'_'+str(proc.returncode))
 gate(sha(row['graph_path'])==row['graph_sha256'],'POST_NATIVE_GRAPH_DRIFT_'+stem)
 vals=parse(stdout.read_text(),ds,beams)
 gate(stderr.stat().st_size==0,'NATIVE_STDERR_NOT_EMPTY_'+stem)
 return {'metrics':vals,'stdout_sha256':sha(stdout),'stderr_sha256':sha(stderr),'elapsed_external_s':wall}

def verify_receipt(receipt,stem,ds,beams,graphsha):
 q=readj(receipt);gate(q['graph_sha256']==graphsha and q['dataset']==ds and q['stem']==stem and q['beams_tested']==list(beams),'RECEIPT_ID_'+stem)
 stdout=OUT/'logs'/(stem+'.stdout');stderr=OUT/'logs'/(stem+'.stderr')
 pinned(stdout,q['stdout_sha256'],'RECEIPT_STDOUT_'+stem);pinned(stderr,q['stderr_sha256'],'RECEIPT_STDERR_'+stem)
 gate(parse(stdout.read_text(),ds,beams)==q['metrics'],'RECEIPT_PARSER_'+stem)
 return q

def preregistration(rows):
 return {'status':'V13_H85_SAME_QUERY_GT_BEAM_THRESHOLD_SCREEN_AND_REPEATED_QPS',
  'screen_summary_sha256':SCREEN_SUM_SHA,'screen_manifest_sha256':SCREEN_MANIFEST_SHA,'screen_runner_sha256':SCREEN_PY_SHA,
  'build_audit_sha256':BUILD_AUDIT_SHA,'build_full_manifest_sha256':BUILD_MANIFEST_SHA,
  'sift_dynamic_evaluator_sha256':SIFT_DYN_SHA,'ms_evaluator_sha256':'bb6576ad3e1e0cc770535aa06355c664993ca70bd1170d6dd4d202ab5767e144',
  'calibration_grids':{k:list(v) for k,v in BEAMS.items()},'target_recalls':TARGETS,'timing_repeats':TIMING_REPS,
  'graph_shas':{k:rows[k]['graph_sha256'] for k in sorted(rows)},'one_cpu':0,'native_build':False,
  'limitations':['min eligible among tested beam values only; not continuous optimization or equal Recall',
                 'same query/GT used for calibration and timing, no independent test split',
                 'MS v4 legacy avg_cmps ignored due overflow',
                 'QPS=throughput; 1e6/QPS is inverse throughput, NOT latency p95/p99',
                 '3 timing repetitions nested in 3 graph builds, no formal non-inferiority proof']}

def init_output(rows):
 p=preregistration(rows)
 if not OUT.exists():
  OUT.mkdir(exist_ok=False);(OUT/'logs').mkdir(exist_ok=False)
  writej(OUT/'preregister.json',p)
 else:
  gate(OUT.is_dir() and not OUT.is_symlink() and (OUT/'logs').is_dir() and not (OUT/'threshold_matched_qps_summary.json').exists(),'OUTPUT_STATE')
  gate(readj(OUT/'preregister.json')==p,'PREREG_DRIFT')

def jobs(rows):
 return [rows[f'{ds}_{arm}_off_r{rep}'] for ds in BEAMS for rep in (1,2,3) for arm in ('stock','h17','fast')]

def validate_anchor(vals,ds,name,mf):
 for b in ANCHORS[ds]:
  difference=abs(vals[str(b)]['recall_at10']-original_recall(mf,name,b))
  limit=0.0001 if ds=='SIFT1M' else 0.000001
  gate(difference<=limit,'DYNAMIC_VS_FIXED_ANCHOR_RECALL_MISMATCH_'+name+'_'+str(b))

def calibrate():
 mod,rows,mf,_=native_state();init_output(rows)
 allobs=[]
 for i,row in enumerate(jobs(rows),1):
  ds=row['dataset'];name=row['name'];beams=BEAMS[ds];stem=name+'_calibration';receipt=OUT/(stem+'.json')
  if receipt.exists():
   r=verify_receipt(receipt,stem,ds,beams,row['graph_sha256']);gate(r['name']==name and r['status']=='CALIBRATED_NATIVE_PASS','CALIB_RESUME_'+name)
   validate_anchor(r['metrics'],ds,name,mf)
   print(TAG+'_CALIB_RESUME_SHA_PASS',i,'of18',name,flush=True)
  else:
   print(TAG+'_CALIB_START',i,'of18',name,'beams',list(beams),flush=True)
   r=native(ds,row,beams,stem,mod)
   validate_anchor(r['metrics'],ds,name,mf)
   r.update(stem=stem,name=name,dataset=ds,arm=row['arm'],build_rep=row['rep'],graph_sha256=row['graph_sha256'],beams_tested=list(beams),status='CALIBRATED_NATIVE_PASS')
   writej(receipt,r)
   print(TAG+'_CALIB_PASS',name,'targets',{'0.99':max(x['recall_at10'] for x in r['metrics'].values()),'0.998':r['metrics'][str(ANCHORS[ds][1])]['recall_at10']},flush=True)
  allobs.append(r)
 obj={'status':'CALIBRATION_18_FROZEN_GRAPHS_NATIVE_COMPLETE','rows':allobs,'preregister_sha256':sha(OUT/'preregister.json')}
 target=OUT/'calibration_manifest.json'
 if target.exists():gate(readj(target)==obj,'CALIB_MANIFEST_DRIFT')
 else:writej(target,obj)
 print(TAG+'_CALIB_18_GRAPH_NATIVE_COMPLETE',flush=True)

def select_beams(ds,arm,obs):
 sub=[r for r in obs if r['dataset']==ds and r['arm']==arm]
 gate(len(sub)==3 and {x['build_rep'] for x in sub}=={1,2,3},'CALIB_GROUP_'+ds+'_'+arm)
 out={}
 for target,threshold in TARGETS.items():
  eligible=[b for b in BEAMS[ds] if all(r['metrics'][str(b)]['recall_at10']>=threshold for r in sub)]
  gate(bool(eligible),'TARGET_NOT_BRACKETED_'+ds+'_'+arm+'_'+target)
  b=min(eligible);r=[v['metrics'][str(b)]['recall_at10'] for v in sub]
  out[target]={'beam':b,'target':threshold,'recall_min':min(r),'recall_mean':statistics.mean(r),'recall_max':max(r),
               'min_among_preselected_grid_only':True}
 return out

def auditcal():
 _,rows,mf,_=native_state();p=OUT/'calibration_manifest.json';full=readj(p)
 gate(full['status']=='CALIBRATION_18_FROZEN_GRAPHS_NATIVE_COMPLETE' and full['preregister_sha256']==sha(OUT/'preregister.json') and len(full['rows'])==18,'CALIB_MANIFEST_STATUS')
 gate({r['name'] for r in full['rows']}==set(rows),'CALIB_ALL_GRAPHS')
 for r in full['rows']:
  ds=r['dataset'];name=r['name'];verify_receipt(OUT/(r['stem']+'.json'),r['stem'],ds,BEAMS[ds],rows[name]['graph_sha256'])
  validate_anchor(r['metrics'],ds,name,mf)
 selected={ds:{arm:select_beams(ds,arm,full['rows']) for arm in ('stock','h17','fast')} for ds in BEAMS}
 obj={'status':'MINIMUM_TESTED_BEAM_ALL_3_BUILD_REPS_THRESHOLD_QUALIFIED','calibration_manifest_sha256':sha(p),
      'selected':selected,'limits':['not exact same Recall across arms','selected using same query/GT as timing','not continuous minimal beam']}
 q=OUT/'selected_threshold_beams.json'
 if q.exists():gate(readj(q)==obj,'SELECTED_BEAM_DRIFT')
 else:writej(q,obj)
 for ds,v in selected.items():
  for arm,w in v.items():print(TAG+'_SELECTED',ds,arm,{t:ob['beam'] for t,ob in w.items()},flush=True)
 print(TAG+'_CALIBRATION_AUDIT_PASS',str(q),'sha256',sha(q),flush=True)

def timing_jobs(rows,selected):
 ans=[]
 for ds in BEAMS:
  for repeat in (1,2,3):
   arms=('stock','h17','fast');arms=arms[(repeat-1)%3:]+arms[:(repeat-1)%3]
   for build_rep in (1,2,3):
    for arm in arms:
     row=rows[f'{ds}_{arm}_off_r{build_rep}'];bmap={t:selected[ds][arm][t]['beam'] for t in TARGETS}
     ans.append((row,repeat,bmap))
 gate(len(ans)==54,'TIMING_54_EVALUATIONS')
 return ans

def timing():
 mod,rows,_,_=native_state();sel=readj(OUT/'selected_threshold_beams.json')
 gate(sel['status']=='MINIMUM_TESTED_BEAM_ALL_3_BUILD_REPS_THRESHOLD_QUALIFIED' and sel['calibration_manifest_sha256']==sha(OUT/'calibration_manifest.json'),'SELECTED_BEAMS_PROVENANCE')
 init_output(rows);obs=[]
 for i,(row,repeat,bmap) in enumerate(timing_jobs(rows,sel['selected']),1):
  ds=row['dataset'];name=row['name'];beamset=tuple(sorted(set(bmap.values())))
  stem=name+f'_timing_r{repeat}';receipt=OUT/(stem+'.json')
  if receipt.exists():
   r=verify_receipt(receipt,stem,ds,beamset,row['graph_sha256'])
   gate(r['repeat']==repeat and r['target_beams']==bmap and r['status']=='TIMING_THRESHOLD_SEARCH_NATIVE_PASS','TIMING_RESUME_RECEIPT_'+stem)
   print(TAG+'_TIMING_RESUME_SHA_PASS',i,'of54',stem,flush=True)
  else:
   print(TAG+'_TIMING_START',i,'of54',stem,'target_beams',bmap,flush=True)
   r=native(ds,row,beamset,stem,mod)
   for target,t in TARGETS.items():gate(r['metrics'][str(bmap[target])]['recall_at10']>=t,'TIMING_TARGET_BELOW_'+stem+'_'+target)
   r.update(stem=stem,name=name,dataset=ds,arm=row['arm'],build_rep=row['rep'],repeat=repeat,graph_sha256=row['graph_sha256'],
            target_beams=bmap,beams_tested=list(beamset),status='TIMING_THRESHOLD_SEARCH_NATIVE_PASS')
   writej(receipt,r)
   print(TAG+'_TIMING_PASS',stem,'per_target',{t:{'beam':b,'recall':r['metrics'][str(b)]['recall_at10'],'qps':r['metrics'][str(b)]['qps']} for t,b in bmap.items()},flush=True)
  obs.append(r)
 obj={'status':'TIMING_54_NATIVE_EVALUATOR_INVOCATIONS_108_TARGET_ROWS_COMPLETE','rows':obs,'selected_beams_sha256':sha(OUT/'selected_threshold_beams.json'),
      'native_evaluator_invocations':54,'per_target_metrics':108}
 q=OUT/'timing_manifest.json'
 if q.exists():gate(readj(q)==obj,'TIMING_MANIFEST_DRIFT')
 else:writej(q,obj)
 print(TAG+'_TIMING_54_RUN_108_BEAM_TARGET_METRICS_COMPLETE_AUDIT_REQUIRED',flush=True)

def summarize(rows,sel):
 out={}
 for ds in BEAMS:
  out[ds]={}
  for target in TARGETS:
   out[ds][target]={}
   for arm in ('stock','h17','fast'):
    v=[x for x in rows if x['dataset']==ds and x['arm']==arm]
    gate(len(v)==9,'GROUP_NINE_TIMING_'+ds+'_'+arm+'_'+target)
    b=sel[ds][arm][target]['beam']; qps=[x['metrics'][str(b)]['qps'] for x in v]
    recall=[x['metrics'][str(b)]['recall_at10'] for x in v]
    by_graph={}
    for r in (1,2,3):
     tmp=[x for x in v if x['build_rep']==r]
     gate(len(tmp)==3 and {x['repeat'] for x in tmp}=={1,2,3},'GRAPH_REP_THREE_'+ds+arm)
     by_graph[str(r)]={'qps_median':statistics.median(x['metrics'][str(b)]['qps'] for x in tmp),
                       'recall_mean':statistics.mean(x['metrics'][str(b)]['recall_at10'] for x in tmp),
                       'qps_samples':[x['metrics'][str(b)]['qps'] for x in sorted(tmp,key=lambda x:x['repeat'])]}
    out[ds][target][arm]={'beam':b,'recall_mean':statistics.mean(recall),'recall_min':min(recall),'recall_max':max(recall),
        'qps_mean':statistics.mean(qps),'qps_median':statistics.median(qps),'qps_sample_stddev':statistics.stdev(qps),
        'inverse_qps_us_proxy_median':1e6/statistics.median(qps),
        'three_graph_replicate_medians':by_graph,'n_graph_realizations':3,'n_timing_reps_per_graph':3,'n_total_qps_samples':9}
   out[ds][target]['pairwise']={}
   for base,other in [('stock','h17'),('h17','fast'),('stock','fast')]:
    a=out[ds][target][base];b=out[ds][target][other]
    qdiff=100*(b['qps_median']/a['qps_median']-1)
    paired=[100*(b['three_graph_replicate_medians'][str(rep)]['qps_median']/a['three_graph_replicate_medians'][str(rep)]['qps_median']-1) for rep in (1,2,3)]
    out[ds][target]['pairwise'][base+'_vs_'+other]={'difference_in_qps_median_percent':qdiff,
       'three_build_rep_matched_median_qps_pct_changes':paired,'achieved_recall_mean_difference_other_minus_base':b['recall_mean']-a['recall_mean'],
       'NOT_a_formal_noninferiority_test':True}
 return out

def audit():
 _,gr,_,_=native_state();cal=readj(OUT/'calibration_manifest.json');sel=readj(OUT/'selected_threshold_beams.json');full=readj(OUT/'timing_manifest.json')
 gate(sel['calibration_manifest_sha256']==sha(OUT/'calibration_manifest.json') and full['selected_beams_sha256']==sha(OUT/'selected_threshold_beams.json'),'CALIB_TIMING_LINK')
 gate(full['status']=='TIMING_54_NATIVE_EVALUATOR_INVOCATIONS_108_TARGET_ROWS_COMPLETE' and len(full['rows'])==54,'TIMING_MANIFEST_COUNT')
 seen=set()
 for r in full['rows']:
  k=(r['dataset'],r['arm'],r['build_rep'],r['repeat']);gate(k not in seen,'TIMING_DUP_KEY');seen.add(k)
  gate(r['graph_sha256']==gr[r['name']]['graph_sha256'],'GRAPH_NAME_AND_SHA_'+r['name'])
  bmap={t:sel['selected'][r['dataset']][r['arm']][t]['beam'] for t in TARGETS}
  gate(r['target_beams']==bmap,'TARGET_BEAM_MATCH_'+r['stem'])
  verify_receipt(OUT/(r['stem']+'.json'),r['stem'],r['dataset'],sorted(set(bmap.values())),r['graph_sha256'])
  for t,threshold in TARGETS.items():gate(r['metrics'][str(bmap[t])]['recall_at10']>=threshold,'TIMING_RECALL_'+r['stem']+'_'+t)
 gate(len(seen)==54,'UNIQUE_TIMING_JOBS')
 result={'status':'V13_H85_18_GRAPH_THRESHOLD_QUALIFIED_CALIBRATED_REPEATED_QPS_AUDIT_PASS__NO_STATISTICAL_NONINFERIORITY_CLAIM',
    'original_quality_screen_sha256':SCREEN_SUM_SHA,'original_screen_full_manifest_sha256':SCREEN_MANIFEST_SHA,
    'original_build_audit_sha256':BUILD_AUDIT_SHA,'calibration_manifest_sha256':sha(OUT/'calibration_manifest.json'),
    'selected_threshold_beams_sha256':sha(OUT/'selected_threshold_beams.json'),
    'timing_manifest_sha256':sha(OUT/'timing_manifest.json'),'native_evaluator_invocations_calibration':18,
    'native_evaluator_invocations_timing':54,'timing_qps_per_target_observations':108,
    'report':summarize(full['rows'],sel['selected']),
    'limitations':['Minimum among preregistered discrete beams meeting threshold on all three graph builds, not equal attained Recall across arms.',
                   'Calibration and timing use SAME queries/GT; results are conditional on this benchmark set.',
                   'QPS derived from evaluator internal Search throughput, reciprocal is latency proxy not perquery p50/p95/p99.',
                   'Three build graph realizations and three correlated repeated timings per graph; not a non-inferiority test.',
                   'MS-Turing legacy high-beam avg_cmps may overflow: excluded from all comparisons.',
                   'Historical Highway H85 DAZ still has simultaneous subnormal tie order differences in controlled probe.',
                   'All native graph, query/GT and binary SHA verified on user Ubuntu; raw 18 graph bytes not uploaded here.']}
 writej(OUT/'threshold_matched_qps_summary.json',result)
 print(TAG+'_AUDIT_PASS_18_OLD_HIGHWAY_GRAPHS_18_CALIB_54_TIMING_CALLS_108_TARGET_ROWS_NO_BUILD',flush=True)
 print(TAG+'_REPORT',str(OUT/'threshold_matched_qps_summary.json'),'sha256',sha(OUT/'threshold_matched_qps_summary.json'),flush=True)

def selftest():
 for ds,beams in BEAMS.items():
  nq=10000 if ds=='SIFT1M' else 100000
  s=('R85_A1C_DYNAMIC_BEAMS count='+str(len(beams))+'\n' if ds=='SIFT1M' else '')+f'R72_RECALL_INPUT_PASS graph_nodes=1000000 queries={nq} gt_k=100\n'+''.join(
   f'R72_RECALL_ROW beam={b} recall=0.99870000 qps=1234.5000 avg_cmps=4294955363 avg_visited=700\n' for b in beams)+'R72_RECALL_EVAL_PASS\n'
  got=parse(s,ds,beams);gate(len(got)==len(beams),'SELFTEST_PARSE_'+ds)
  gate(all(got[str(b)]['ms_legacy_avg_cmps_IGNORED'] is None for b in beams),'SELFTEST_MS_COUNTER_EXCLUDED')
  try:parse(s.replace('R72_RECALL_EVAL_PASS',''),ds,beams)
  except RuntimeError:pass
  else:gate(False,'SELFTEST_MISSING_FINAL_ACCEPTED')
  try:parse(s.replace('recall=0.99870000','recall=nan',1),ds,beams)
  except RuntimeError:pass
  else:gate(False,'SELFTEST_NONFINITE_ACCEPTED')
  try:parse(s,ds,beams[:-1])
  except RuntimeError:pass
  else:gate(False,'SELFTEST_BEAM_DRIFT_ACCEPTED')
 # Threshold selection is STRICT over every graph realization, not mean Recall.
 trial=[{'dataset':'SIFT1M','arm':'stock','build_rep':i,'metrics':{str(b):{'recall_at10':(.9986 if b==160 else .989 if b==72 and i==3 else .991)} for b in BEAMS['SIFT1M']}} for i in (1,2,3)]
 gate(select_beams('SIFT1M','stock',trial)['0.99']['beam']==64,'SELFTEST_MIN_THRESHOLD')
 with tempfile.TemporaryDirectory() as d:
  p=pathlib.Path(d)/'r.json';writej(p,{'ok':True})
  try:writej(p,{'ok':False})
  except RuntimeError:pass
  else:gate(False,'SELFTEST_OVERWRITE_ACCEPTED')
 gate(len(BEAMS['SIFT1M'])==10 and len(BEAMS['MS-Turing1M'])==9,'SELFTEST_GRID')
 print(TAG+'_SELFTEST_PASS_DYNAMIC_SIFT_MS_PARSER_BEAM_TARGET_NONFINITE_NO_OVERWRITE_54_CALLS_NO_BUILD',flush=True)

def main():
 p=argparse.ArgumentParser();p.add_argument('phase',choices=('selftest','preflight','calibrate','auditcal','timing','audit'))
 phase=p.parse_args().phase
 if phase=='selftest':selftest()
 elif phase=='preflight':native_state(expect_new_output=True)
 elif phase=='calibrate':calibrate()
 elif phase=='auditcal':auditcal()
 elif phase=='timing':timing()
 else:audit()
if __name__=='__main__':
 try:main()
 except Exception as e:
  print(TAG+'_ERROR',repr(e),flush=True);sys.exit(2)
