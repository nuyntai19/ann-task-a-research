#!/usr/bin/env python3
"""R90 P4Q: read-only native MS-Turing1M Search on P4 Stock/H17/Fast graphs.

First pilot: one existing graph/arm (rep1) at beams 384 and 896, 100,000
queries, pinned v4 high-beam evaluator. After independent inspection, `full`
searches the six remaining graphs. No BUILD, compilation, source modifications,
or writes outside this independent P4Q result directory.

Phases: selftest -> preflight -> pilot -> auditpilot -> full -> audit.
NOTE: fixed-beam screening is NOT matched Recall latency or equivalence.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import statistics
import subprocess
import sys
import tempfile
import time

HOME=Path.home()
ROOT=HOME/'ann-task-a'
R86=ROOT/'experiments/R86'
R90=ROOT/'experiments/R90'
OUT=R90/'r90_p4q_mst1m_three_arm_100kq_search_v1'
RUNNER=HOME/'Downloads/r90_p4_msturing1m_stock_h17_fastv2_4cpu_build_v1.py'
RUNNER_SHA='c28ffbb20f729ce4d88f06da3c2be54d8d8b87c0e8ebef379528c93d22b30e43'
RESCUE=HOME/'Downloads/r90_p4_readonly_audit_recovery_v1.py'
RESCUE_SHA='b7cb57828d280eaeccb92c975e922cccf8e6b95860fdbda06071d7e215a74d04'
RESCUE_ROOT=HOME/'R90_P4_RESCUE_AUDIT_v1'
EVAL=R86/'msturing_1m_eval/r86_msturing1m_graph_recall_v4_highbeam'
EVAL_SHA='bb6576ad3e1e0cc770535aa06355c664993ca70bd1170d6dd4d202ab5767e144'
EVAL_SRC=R86/'msturing_1m_eval/r86_msturing1m_graph_recall_v4_highbeam.cc'
EVAL_SRC_SHA='6aa0e38a3b0a536ccbcd3bfe0ca690257ab963215b5135d642cbb60d259c3f89'
EVAL_MANIFEST=R86/'msturing_1m_eval/r86_msturing1m_highbeam_v4_manifest.json'
BASE=ROOT/'data/MSTuring_1M_v1/base.1M.fbin'
QUERY=ROOT/'data/MSTuring_1M_v1/query.public.100K.fbin'
GT=ROOT/'data/MSTuring_1M_v1/groundtruth.public.100K.ibin'
DATA_SHA={'base':'44e83e1dd4c65999b75873101adc5ac06ca900d259a2befd05c2c3aa28ff4042',
'query':'48d087a17bec15a5ec9ea526fe9bd14ac31bbbb5cd200817b341adbb77695644',
'gt':'fa5acf5ab262b42355296e99f920e6aa863f48820ca6f70fa37ca7966634c344'}
GRAPH_SHA={
('stock',1):'c24e1a506c4adaca82d398bbc51a68d0fc8caab7f6472219182614a874081ca3',
('h17',1):'64a670d0136cc070cfe376a27a5dd3aabebb7be784f2a258734a35635717c6d7',
('fast',1):'6936e95d42ff27c8511e791b1f53164d1273709b2b4fcf8d710edc081838fdac',
('stock',2):'3161a570d03daccb498ef1e6a8fcd11063e4899e9e0044242adab8a11aa6a3aa',
('h17',2):'8a89f28ae3d1617e0e9a8d8d132a433f8c6682335ab28e768f3f354d2e2918cf',
('fast',2):'ef92e69ba759910cc8399ae84723e58d5665f06022ebf407786597fc79a10aa9',
('stock',3):'6ff7c6b143eced4e666799ce6c7eef39f96e8771b7bb76244f04cffef72da505',
('h17',3):'a20fdc5a6bf1b927eac9584b729c43ec71bf97bedb8a918850a0206570fda9d6',
('fast',3):'324973bf593f4db0cf17f543376cb4184e302437e758418a1867a138b2fe9e17'}
ARMS=('stock','h17','fast')
BEAMS=(384,896)
TAG='R90_P4Q'
PAT=re.compile(r'^R72_RECALL_ROW beam=(\d+) recall=([0-9.eE+-]+) qps=([0-9.eE+-]+) avg_cmps=([0-9.eE+-]+) avg_visited=([0-9.eE+-]+)$',re.M)


def stop(label): raise RuntimeError(f'{TAG}_HOLD_{label}')
def ensure(cond,label):
    if not cond: stop(label)


def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for c in iter(lambda:f.read(4<<20), b''): h.update(c)
    return h.hexdigest()


def file_pinned(path,expected,label):
    p=Path(path)
    ensure(p.is_file() and not p.is_symlink(),f'{label}_MISSING_OR_SYMLINK')
    ensure(sha(p)==expected,f'{label}_SHA')


def load_module(path,name):
    spec=importlib.util.spec_from_file_location(name,str(path))
    ensure(spec is not None and spec.loader is not None,name+'_IMPORT')
    obj=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(obj)
    return obj


def atomic_json(path,obj,creation=False):
    path=Path(path)
    tmp=path.with_suffix(path.suffix+'.part')
    ensure(not tmp.exists() and not tmp.is_symlink(),'PART_EXISTS_'+path.name)
    if creation:ensure(not path.exists() and not path.is_symlink(),'OUTPUT_EXISTS_'+path.name)
    with tmp.open('x',encoding='utf-8') as f:
        json.dump(obj,f,indent=2,sort_keys=True,allow_nan=False)
        f.write('\n')
    os.replace(tmp,path)


def parser(text):
    ensure('R72_RECALL_EVAL_PASS' in text,'EVAL_MISSING_PASS')
    ensure('R72_RECALL_INPUT_PASS graph_nodes=1000000 queries=100000 gt_k=' in text,
           'EVAL_WRONG_DATA_SHAPE')
    found={}
    for m in PAT.finditer(text):
        b=int(m.group(1)); vals=[float(m.group(i)) for i in range(2,6)]
        ensure(b in BEAMS and b not in found, 'BEAM_DUPLICATE_OR_UNEXPECTED')
        r,q,cm,vi=vals
        ensure(all(math.isfinite(x) for x in vals) and 0<=r<=1 and q>0 and cm>0 and vi>0,
               'BAD_RECALL_QPS_WORK')
        found[b]={'recall_at10':r,'qps':q,'avg_cmps':cm,'avg_visited':vi,
                  'latency_us_proxy':1e6/q,'meets_099':r>=.99,'meets_0998':r>=.998}
    ensure(set(found)==set(BEAMS),'BEAM_MISSING')
    ensure(found[896]['recall_at10']+1e-9>=found[384]['recall_at10'], 'RECALL_DECREASE_WITH_BEAM')
    return {str(b):found[b] for b in BEAMS}


def native_state(full_sha=True):
    file_pinned(RUNNER,RUNNER_SHA,'ORIGINAL_P4_SCRIPT')
    file_pinned(RESCUE,RESCUE_SHA,'RESCUE_SCRIPT')
    rescue=load_module(RESCUE,'r90_p4q_verified_rescue')
    orig=rescue.load_original()
    st,cur,topo=rescue.verify_core(orig)
    ensure(st['status']=='NINE_4CPU_BUILDS_COMPLETE_QUALITY_PENDING','SOURCE_BUILD_STATE')
    ensure(len(st['runs'])==9,'NINE_BUILDS')
    if full_sha: rescue.verify_runs(orig,st)
    file_pinned(EVAL,EVAL_SHA,'NATIVE_EVAL_ELF')
    file_pinned(EVAL_SRC,EVAL_SRC_SHA,'NATIVE_EVAL_SRC')
    em=json.loads(EVAL_MANIFEST.read_text())
    ensure(em['binary_v4_sha256']==EVAL_SHA and em['source_v4_sha256']==EVAL_SRC_SHA
           and em['MAX_BEAM']>=896,'EVALUATOR_PROVENANCE')
    for k,p in [('base',BASE),('query',QUERY),('gt',GT)]:
        file_pinned(p,DATA_SHA[k],'DATA_'+k)
    recfile=RESCUE_ROOT/'audit_receipt_v1.json'
    repfile=RESCUE_ROOT/'build_summary_rescue_v1.json'
    ensure(recfile.is_file() and repfile.is_file() and not recfile.is_symlink()
           and not repfile.is_symlink(),'RESCUE_REPORT_MISSING')
    receipt=json.loads(recfile.read_text());report=json.loads(repfile.read_text())
    ensure(receipt['status']=='PASS_READONLY_RESCUE_AUDIT' and
           receipt['original_runner_sha']==RUNNER_SHA and
           receipt['original_build_manifest_sha']==sha(orig.OUT/'build_manifest.json') and
           receipt['recovered_report_sha']==sha(repfile), 'RESCUE_RECEIPT_MISMATCH')
    ensure(report['status']=='PASS_READONLY_RESCUE_AUDIT_9_P4_BUILDS__SEARCH_NOT_RUN' and
           report['quality_status']=='NATIVE_MS_TURING1M_100KQ_SEARCH_NOT_RUN' and
           len(report['graph_semantic'])==9, 'RESCUE_REPORT_STATE')
    expected_pairs={(i,a,b) for i in (1,2,3) for a,b in
                    (('stock','h17'),('h17','fast'),('stock','fast'))}
    ensure({(r['rep'],r['baseline_arm'],r['comparison_arm']) for r in report['graph_semantic']}
           ==expected_pairs,'NINE_SEMANTIC_PAIRS')
    for row in st['runs']:
        key=(row['arm'],row['rep'])
        ensure(key in GRAPH_SHA and row['graph_sha']==GRAPH_SHA[key],
               'FROZEN_GRAPH_SHA_'+str(key))
        if not full_sha:file_pinned(row['graph'],GRAPH_SHA[key],'GRAPH_'+str(key))
    ensure(os.sched_getaffinity(0).__contains__(0),'CPU0_UNAVAILABLE')
    return orig,st,receipt,report


def selftest():
    x='R72_RECALL_INPUT_PASS graph_nodes=1000000 queries=100000 gt_k=100\n'+\
      'R72_RECALL_ROW beam=384 recall=0.99102000 qps=1220.0 avg_cmps=4000.0 avg_visited=400.0\n'+\
      'R72_RECALL_ROW beam=896 recall=0.99817000 qps=559.7 avg_cmps=8000.0 avg_visited=700.0\nR72_RECALL_EVAL_PASS\n'
    d=parser(x)
    assert d['384']['meets_099'] and not d['384']['meets_0998'] and d['896']['meets_0998']
    assert abs(d['384']['latency_us_proxy']-819.6721311475409)<1e-8
    for x_bad in [x.replace('beam=896','beam=384'),x.replace('0.99817000','0.98000000'),x.replace('R72_RECALL_EVAL_PASS','')]:
        try:parser(x_bad);raise AssertionError('Invalid parser case was not rejected')
        except RuntimeError:pass
    with tempfile.TemporaryDirectory() as tmp:
        p=Path(tmp)/'x.json';atomic_json(p,{'status':'new'},creation=True)
        atomic_json(p,{'status':'next'})
        assert json.loads(p.read_text())=={'status':'next'}
    print(TAG+'_SELFTEST_PASS_2BEAMS_NATIVE_PARSER_SHA_STATE',flush=True)


def preflight():
    ensure(not OUT.exists() and not OUT.is_symlink(),'OUTPUT_ROOT_EXISTS')
    _,st,rec,report=native_state(full_sha=True)
    print(TAG+'_PREFLIGHT_P4_RESCUE_9GRAPH_100KQUERY_V4EVAL_SHA_PASS',
          'beams',list(BEAMS),'CPU0','all_9_graphs',len(st['runs']),flush=True)


def stage_records(state):
    return {(x['arm'],x['rep']):x for x in state['searches']}


def run_search(arm,rep,graph):
    tag=f'mst1m_{arm}_r{rep}'
    std=OUT/'logs'/(tag+'.stdout'); tfile=OUT/'logs'/(tag+'.time')
    ensure(not any(p.exists() or p.is_symlink() for p in [std,tfile]),'SEARCH_OUTPUT_EXISTS_'+tag)
    cmd=[str(EVAL),str(graph),str(BASE),str(QUERY),str(GT),','.join(map(str,BEAMS))]
    env=os.environ.copy();env.update({'LC_ALL':'C','PARLAY_NUM_THREADS':'1','OMP_NUM_THREADS':'1'})
    full=['/usr/bin/time','-v','-o',str(tfile),'taskset','-c','0',*cmd]
    print(TAG+'_SEARCH_START',arm,rep,'beams',list(BEAMS),'100000_queries',flush=True)
    start=time.monotonic()
    with std.open('x') as f:
        proc=subprocess.run(full,env=env,stdout=f,stderr=subprocess.STDOUT,timeout=3600,check=False)
    dur=time.monotonic()-start
    ensure(proc.returncode==0,'NATIVE_SEARCH_NONZERO_'+tag+'_'+str(proc.returncode))
    ensure(tfile.is_file() and not tfile.is_symlink(),'TIMEFILE_MISSING_'+tag)
    t=tfile.read_text(errors='replace')
    ensure('Exit status: 0' in t,'NATIVE_TIME_NONZERO_'+tag)
    d=parser(std.read_text(errors='replace'))
    ensure(d['384']['recall_at10']>=0 and d['896']['recall_at10']<=1,'BAD_RECALL')
    rec={'arm':arm,'rep':rep,'graph':str(graph),'graph_sha':GRAPH_SHA[(arm,rep)],
         'evaluator_sha':EVAL_SHA,'command':cmd,'cpu_search':0,'threads':1,
         'beams':list(BEAMS),'rows':d,'wall_s':dur,
         'stdout':str(std),'stdout_sha':sha(std),
         'timefile':str(tfile),'timefile_sha':sha(tfile),
         'run_status':'NATIVE_SEARCH_EXIT0_VALID_100KQ'}
    print(TAG+'_SEARCH_PASS',arm,rep,
          'recall384',d['384']['recall_at10'],'qps384',round(d['384']['qps'],2),
          'recall896',d['896']['recall_at10'],'qps896',round(d['896']['qps'],2),flush=True)
    return rec


def pilot():
    preflight()
    orig,st,receipt,_=native_state(full_sha=False)
    OUT.mkdir(mode=0o700);(OUT/'logs').mkdir(mode=0o700)
    state={'status':'PILOT_IN_PROGRESS','dataset':'MSTuring1M','n':1000000,'dim':100,
           'queries':100000,'beams':list(BEAMS),'evaluation_cpu':0,'threads':1,
           'original_runner_sha':RUNNER_SHA,
           'original_build_manifest_sha':sha(orig.OUT/'build_manifest.json'),
           'rescue_receipt_sha':sha(RESCUE_ROOT/'audit_receipt_v1.json'),
           'evaluator_sha':EVAL_SHA,'data_sha':DATA_SHA,'searches':[]}
    atomic_json(OUT/'progress.json',state,creation=True)
    for arm in ARMS:
        row=next(r for r in st['runs'] if r['arm']==arm and r['rep']==1)
        rec=run_search(arm,1,Path(row['graph']))
        state['searches'].append(rec);atomic_json(OUT/'progress.json',state)
    state['status']='PILOT_3_GRAPHS_DONE__FULL_SEARCH_NOT_RUN'
    atomic_json(OUT/'pilot_manifest.json',state,creation=True)
    print(TAG+'_PILOT_THREE_ARM_REP1_COMPLETE__AUDIT_REQUIRED',flush=True)


def verify_searches(state,expected):
    native_state(full_sha=True)
    ensure(state['beams']==list(BEAMS) and state['evaluator_sha']==EVAL_SHA and
           state['data_sha']==DATA_SHA and state['evaluation_cpu']==0 and state['threads']==1,
           'MANIFEST_PROVENANCE')
    ensure(len(state['searches'])==len(expected),'SEARCH_COUNT')
    ensure(set(stage_records(state))==expected,'SEARCH_ARM_REP_COVERAGE')
    for row in state['searches']:
        arm,rep=row['arm'],row['rep']
        tag=f'mst1m_{arm}_r{rep}'
        graph=R90/'r90_p4_msturing1m_stock_h17_fastv2_4cpu_build_v1'/'graphs'/(tag+'.graph')
        ensure(row['graph']==str(graph) and row['graph_sha']==GRAPH_SHA[(arm,rep)],'GRAPH_RECEIPT_'+tag)
        ensure(row['evaluator_sha']==EVAL_SHA and row['threads']==1 and row['cpu_search']==0,
               'SEARCH_EXECUTION_'+tag)
        std=OUT/'logs'/(tag+'.stdout');tim=OUT/'logs'/(tag+'.time')
        for field,p in [('stdout',std),('timefile',tim)]:
            ensure(row[field]==str(p) and p.is_file() and not p.is_symlink(),
                   'SEARCH_PATH_'+tag+'_'+field)
            ensure(row[field+'_sha']==sha(p),'SEARCH_SHA_'+tag+'_'+field)
        parsed=parser(std.read_text(errors='replace'))
        ensure(row['rows']==parsed,'PARSED_ROW_DRIFT_'+tag)
        ensure('Exit status: 0' in tim.read_text(errors='replace'),'NATIVE_EXIT_NONZERO_'+tag)
        cmd=[str(EVAL),str(graph),str(BASE),str(QUERY),str(GT),','.join(map(str,BEAMS))]
        ensure(row['command']==cmd and row['beams']==list(BEAMS),'SEARCH_COMMAND_'+tag)


def summarize(state,expected_all=False):
    grouped={arm:{} for arm in ARMS}
    for row in state['searches']:
        for b,detail in row['rows'].items():
            grouped[row['arm']].setdefault(b,[]).append({'rep':row['rep'],**detail})
    avg={}
    for arm,bdata in grouped.items():
        avg[arm]={}
        for beam,rr in bdata.items():
            avg[arm][beam]={'n_build_graphs':len(rr),
                            'mean_recall_at10':statistics.mean(v['recall_at10'] for v in rr),
                            'mean_qps':statistics.mean(v['qps'] for v in rr),
                            'recall_each_graph':[(v['rep'],v['recall_at10']) for v in rr],
                            'qps_each_graph':[(v['rep'],v['qps']) for v in rr],
                            'floor099_all':all(v['meets_099'] for v in rr),
                            'floor0998_all':all(v['meets_0998'] for v in rr)}
    comparisons={}
    for a,b in [('stock','h17'),('h17','fast'),('stock','fast')]:
        comparisons[a+'_to_'+b]={}
        for beam in map(str,BEAMS):
            ca=avg[a][beam];cb=avg[b][beam]
            comparisons[a+'_to_'+b][beam]={
                'mean_recall_delta':cb['mean_recall_at10']-ca['mean_recall_at10'],
                'qps_ratio_mean_b_over_a':cb['mean_qps']/ca['mean_qps'],
                'qps_pct_change':100*(cb['mean_qps']/ca['mean_qps']-1)}
    return {'status':'PILOT_QUALITY_SCREEN_ONLY' if not expected_all else 'FULL_NINE_GRAPH_FIXED_BEAM_SCREEN',
            'n_build_graphs_total':len(state['searches']),'search_calls':len(state['searches']),
            'beams':list(BEAMS),'query_count':100000,'per_graph':state['searches'],
            'per_arm':avg,'comparisons':comparisons,
            'notes':['This is a fixed-beam screening; 384,896 are not necessarily each method minimum qualifying beams.',
                     'Each graph run only once at two beams; QPS noise and no statistical equivalence test.',
                     'Stock ELF R86, H17/Fast ELF R90; provenance vintages differ.',
                     'P4 observed 78-99% Stock/H17 neighbor multiset vertex differences, so MS-Turing quality MUST be checked.',
                     'No new BUILD, no graph modifications.']}


def auditpilot():
    state=json.loads((OUT/'pilot_manifest.json').read_text())
    ensure(state['status']=='PILOT_3_GRAPHS_DONE__FULL_SEARCH_NOT_RUN','PILOT_STATE')
    expected={(arm,1) for arm in ARMS}
    verify_searches(state,expected)
    result=summarize(state)
    report=OUT/'pilot_quality_summary.json'
    atomic_json(report,result,creation=True)
    for arm in ARMS:
        d=result['per_arm'][arm]
        print(TAG+'_PILOT_RECALL',arm,'b384',d['384']['mean_recall_at10'],
              'b896',d['896']['mean_recall_at10'],flush=True)
    print(TAG+'_AUDIT_PILOT_PASS_3GRAPHS_100KQ_384_896__FULL_PENDING',flush=True)
    print(TAG+'_PILOT_REPORT',report,flush=True)


def full():
    ensure(not (OUT/'full_manifest.json').exists(),'FULL_ALREADY_EXISTS')
    st=json.loads((OUT/'pilot_manifest.json').read_text())
    ensure(st['status']=='PILOT_3_GRAPHS_DONE__FULL_SEARCH_NOT_RUN','PILOT_STATE')
    ensure((OUT/'pilot_quality_summary.json').is_file(),'PILOT_AUDIT_REQUIRED')
    verify_searches(st,{(a,1) for a in ARMS})
    orig,original,_,_=native_state(full_sha=True)
    ensure(not any((OUT/'logs'/(f'mst1m_{a}_r{rep}.{ext}')).exists() for a in ARMS for rep in (2,3) for ext in ('time','stdout')),'LATER_RUN_ALREADY_EXISTS')
    next_st={**st,'status':'FULL_IN_PROGRESS','searches':list(st['searches'])}
    atomic_json(OUT/'progress.json',next_st)
    for rep in (2,3):
        for arm in ARMS:
            row=next(r for r in original['runs'] if r['arm']==arm and r['rep']==rep)
            next_st['searches'].append(run_search(arm,rep,Path(row['graph'])))
            atomic_json(OUT/'progress.json',next_st)
    next_st['status']='FULL_NINE_SEARCHES_DONE__AUDIT_REQUIRED'
    atomic_json(OUT/'full_manifest.json',next_st,creation=True)
    print(TAG+'_FULL_NINE_SEARCHES_COMPLETE__AUDIT_REQUIRED',flush=True)


def audit():
    st=json.loads((OUT/'full_manifest.json').read_text())
    ensure(st['status']=='FULL_NINE_SEARCHES_DONE__AUDIT_REQUIRED','FULL_STATE')
    verify_searches(st,{(a,rep) for rep in (1,2,3) for a in ARMS})
    summary=summarize(st,expected_all=True)
    report=OUT/'full_quality_summary.json'
    atomic_json(report,summary,creation=True)
    print(TAG+'_AUDIT_FULL_PASS_9GRAPHS_100KQ_384_896',flush=True)
    print(TAG+'_FULL_REPORT',report,flush=True)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('phase',choices=('selftest','preflight','pilot','auditpilot','full','audit'))
    args=p.parse_args()
    globals()[args.phase]()

if __name__=='__main__':
    try:main()
    except Exception as ex:
        print(TAG+'_HOLD',type(ex).__name__,str(ex),file=sys.stderr,flush=True)
        raise SystemExit(2)
