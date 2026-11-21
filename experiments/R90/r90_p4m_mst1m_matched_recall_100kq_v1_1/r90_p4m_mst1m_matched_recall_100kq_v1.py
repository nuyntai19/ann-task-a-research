#!/usr/bin/env python3
"""R90-P4M v1: read-only MS-Turing1M matched-quality-floor grid, 100K queries.

Stages selftest -> preflight -> pilot -> auditpilot [then full -> audit].
Three prebuilt 4CPU Stock/H17/Fast graphs per arm; historical P4Q full 9graph
fixed-beam audit is SHA-verified before any new Search. The native R86 v4
highbeam evaluator is unchanged. Pilot only: r1 Stock/H17/Fast, 8 selected
bracketing beams. All measurements are on a fixed grid, and selected beam
is the first *tested* beam to meet quality floor; it is not the global true
minimum beam or exact-Recall matched latency. No BUILD, no recompilation,
no writes to frozen historical evidence, no p95/p99 or valid highbeam avg_cmps.
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
OUT=ROOT/'experiments/R90/r90_p4m_mst1m_matched_recall_100kq_v1'
P4Q_SCRIPT=HOME/'Downloads/r90_p4q_mst1m_three_arm_100kq_search_v1.py'
P4Q_SHA='d2a9dffc8ed1e9e2b51a228270c67252773e2414829d40254acf2074e0a1fa16'
P4Q_OUT=ROOT/'experiments/R90/r90_p4q_mst1m_three_arm_100kq_search_v1'
ARMS=('stock','h17','fast')
BEAMS_099=(320,352,368,384)
BEAMS_0998=(800,848,880,896)
BEAMS=BEAMS_099+BEAMS_0998
TARGETS=(0.99,0.998)
TAG='R90_P4M'
PAT=re.compile(r'^R72_RECALL_ROW\s+beam=(\d+)\s+recall=([\deE.+-]+)\s+'
               r'qps=([\deE.+-]+)\s+avg_cmps=([\deE.+-]+)\s+'
               r'avg_visited=([\deE.+-]+)\s*$',re.M)


def ensure(condition, label):
    if not condition: raise RuntimeError(TAG+'_HOLD_'+label)


def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for buf in iter(lambda:f.read(4<<20),b''):h.update(buf)
    return h.hexdigest()


def safe_file(p):
    p=Path(p)
    return p.is_file() and not p.is_symlink()


def atomic(path, obj, first=False):
    path=Path(path)
    temp=path.with_suffix(path.suffix+'.part')
    ensure(not temp.exists() and not temp.is_symlink(),'TEMP_EXISTS_'+path.name)
    if first:ensure(not path.exists() and not path.is_symlink(),'OUTPUT_EXISTS_'+path.name)
    with temp.open('x',encoding='utf8') as f:
        json.dump(obj,f,sort_keys=True,indent=2,allow_nan=False)
        f.write('\n')
    os.replace(temp,path)


def parse(text):
    ensure(f'R85_A1C_DYNAMIC_BEAMS count={len(BEAMS)}' in text,'COUNT_HEADER')
    ensure('R72_RECALL_INPUT_PASS graph_nodes=1000000 queries=100000 gt_k=' in text,'INPUT_HEADER')
    ensure('R72_RECALL_EVAL_PASS' in text,'EVAL_PASS_MARKER')
    rows={}
    for m in PAT.finditer(text):
        beam=int(m.group(1));vals=tuple(float(m.group(i)) for i in (2,3,4,5))
        ensure(beam in BEAMS and beam not in rows,'BEAM_DUPLICATED_OR_UNKNOWN')
        recall,qps,cmps,visited=vals
        ensure(all(math.isfinite(v) for v in vals) and
               0<=recall<=1 and qps>0 and cmps>0 and visited>0,'BAD_METRICS')
        rows[beam]={
            'recall_at10':recall,'qps':qps,'latency_us_proxy':1e6/qps,
            'avg_visited':visited,
            'legacy_avg_cmps_raw_UNTRUSTED':cmps,
            'legacy_avg_cmps_status':('INVALID_R86_V4_32BIT_HIGHBEAM' if beam>=800
                                       else 'LEGACY_RAW_UNVERIFIED'),
            'meets_099':recall>=.99,'meets_0998':recall>=.998}
    ensure(set(rows)==set(BEAMS),'EIGHT_BEAMS_REQUIRED')
    for group in (BEAMS_099,BEAMS_0998):
        for low,high in zip(group,group[1:]):
            ensure(rows[high]['recall_at10']+0.00005>=rows[low]['recall_at10'],
                   'RECALL_GRID_NONMONOTONIC')
    return {str(b):rows[b] for b in BEAMS}


def crossing(rows, target):
    grid=BEAMS_099 if target==.99 else BEAMS_0998
    for i,beam in enumerate(grid):
        hi=rows[str(beam)]
        if hi['recall_at10']>=target:
            if i==0:
                return {'status':'LEFT_UNBRACKETED_NEEDS_LOWER_BEAM','tested_beam':beam,
                        'observed_recall':hi['recall_at10']}
            lb=grid[i-1];lo=rows[str(lb)]
            ensure(lo['recall_at10']<target,'BRACKET_LOGIC')
            out={'status':'BRACKETED_MEASURED_QUALITY_FLOOR',
                 'target':target,'selected_beam_in_tested_grid':beam,
                 'observed_recall':hi['recall_at10'],'observed_qps':hi['qps'],
                 'observed_latency_us_proxy':hi['latency_us_proxy'],
                 'overshoot':hi['recall_at10']-target,
                 'lower_beam':lb,'lower_recall':lo['recall_at10'],
                 'upper_beam':beam,'upper_recall':hi['recall_at10'],
                 'not_global_minimum_beam':True}
            if hi['recall_at10']>lo['recall_at10']:
                alpha=(target-lo['recall_at10'])/(hi['recall_at10']-lo['recall_at10'])
                estimated_us=(1-alpha)*lo['latency_us_proxy']+alpha*hi['latency_us_proxy']
                out['interpolation_estimate']={'weight':alpha,
                    'estimated_latency_us_at_exact_target':estimated_us,
                    'not_direct_native_measurement':True}
            return out
    return {'status':'RIGHT_UNBRACKETED_NEEDS_HIGHER_BEAM',
            'tested_max_beam':grid[-1],'observed_recall':rows[str(grid[-1])]['recall_at10']}


def p4q_source():
    ensure(safe_file(P4Q_SCRIPT) and digest(P4Q_SCRIPT)==P4Q_SHA,'FROZEN_P4Q_RUNNER_SHA')
    spec=importlib.util.spec_from_file_location('r90_p4m_frozen_p4q',str(P4Q_SCRIPT))
    ensure(spec is not None and spec.loader is not None,'IMPORT_FROZEN_P4Q')
    obj=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(obj)
    ensure(obj.OUT==P4Q_OUT and tuple(obj.BEAMS)==(384,896),'FROZEN_P4Q_MODEL')
    return obj


def prior_verified():
    p=p4q_source()
    fm=P4Q_OUT/'full_manifest.json'
    fs=P4Q_OUT/'full_quality_summary.json'
    ensure(safe_file(fm) and safe_file(fs),'P4Q_FULL_EVIDENCE_MISSING')
    state=json.loads(fm.read_text())
    ensure(state.get('status')=='FULL_NINE_SEARCHES_DONE__AUDIT_REQUIRED','P4Q_FULL_STATE')
    expected={(a,i) for a in ARMS for i in (1,2,3)}
    p.verify_searches(state,expected)  # all 9 frozen log, graph/data/ELF SHA, CPU, parser checks
    summary=json.loads(fs.read_text())
    ensure(summary==p.summarize(state,expected_all=True) and
           summary.get('status')=='FULL_NINE_GRAPH_FIXED_BEAM_SCREEN',
           'P4Q_FULL_SUMMARY_DRIFT')
    prior={(r['arm'],r['rep']):r['rows'] for r in state['searches']}
    ensure(set(prior)==expected,'P4Q_RUN_COVERAGE')
    receipt={'prior_p4q_script_sha':P4Q_SHA,
             'prior_p4q_manifest_sha':digest(fm),
             'prior_p4q_summary_sha':digest(fs),
             'evaluator_elf_sha':p.EVAL_SHA,
             'evaluator_source_sha':p.EVAL_SRC_SHA,
             'graph_sha':{f'{a}_r{i}':p.GRAPH_SHA[(a,i)] for a,i in sorted(expected)},
             'data_sha':p.DATA_SHA,
             'beams':list(BEAMS),'targets':list(TARGETS)}
    return p,prior,receipt


def selftest():
    vals={320:.9875,352:.9897,368:.9903,384:.9910,
          800:.9971,848:.99778,880:.99796,896:.99817}
    s='R85_A1C_DYNAMIC_BEAMS count=8\nR72_RECALL_INPUT_PASS graph_nodes=1000000 queries=100000 gt_k=100\n'
    s+=''.join(f'R72_RECALL_ROW beam={b} recall={vals[b]:.8f} qps={12000/b:.8f} avg_cmps=4294955362 avg_visited=371\n' for b in BEAMS)
    s+='R72_RECALL_EVAL_PASS\n'
    p=parse(s)
    a=crossing(p,.99);b=crossing(p,.998)
    ensure(a['selected_beam_in_tested_grid']==368 and
           b['selected_beam_in_tested_grid']==896 and
           a['interpolation_estimate']['not_direct_native_measurement'], 'SELFTEST_BRACKET')
    ensure(p['896']['legacy_avg_cmps_status'].startswith('INVALID'),'SELFTEST_OVERFLOW_FLAG')
    for bad in (s.replace('beam=896','beam=880'),s.replace('R72_RECALL_EVAL_PASS','')):
        try: parse(bad)
        except RuntimeError: pass
        else: raise AssertionError('bad native evaluator text was accepted')
    with tempfile.TemporaryDirectory() as td:
        x=Path(td)/'x.json'
        atomic(x,{'a':1},first=True);atomic(x,{'b':2})
        ensure(json.loads(x.read_text())=={'b':2},'SELFTEST_ATOMIC')
    print('R90_P4M_SELFTEST_PASS_EIGHTBEAMS_BRACKET_PARSER_LEGACY_COUNTER_GATES',flush=True)


def preflight():
    ensure(not OUT.exists() and not OUT.is_symlink(),'OUTPUT_ROOT_EXISTS')
    prior_verified()
    ensure(OUT.parent.is_dir(),'OUTPUT_PARENT_MISSING')
    print('R90_P4M_PREFLIGHT_P4Q_FULL_9GRAPH_SHA_R86_V4_100K_GT_PASS',
          'beams',list(BEAMS),'cpu0',flush=True)


def execute_one(p,arm,rep):
    tag=f'mst1m_{arm}_r{rep}'
    graph=p.R90/'r90_p4_msturing1m_stock_h17_fastv2_4cpu_build_v1'/'graphs'/(tag+'.graph')
    ensure(safe_file(graph) and digest(graph)==p.GRAPH_SHA[(arm,rep)],'GRAPH_SHA_'+tag)
    std=OUT/'logs'/(tag+'.stdout')
    tm=OUT/'logs'/(tag+'.time')
    ensure(not std.exists() and not std.is_symlink() and not tm.exists() and not tm.is_symlink(),
           'SEARCH_OUTPUT_EXISTS_'+tag)
    cmd=[str(p.EVAL),str(graph),str(p.BASE),str(p.QUERY),str(p.GT),','.join(map(str,BEAMS))]
    env=os.environ.copy();env.update({'LC_ALL':'C','PARLAY_NUM_THREADS':'1','OMP_NUM_THREADS':'1'})
    full=['/usr/bin/time','-v','-o',str(tm),'taskset','-c','0',*cmd]
    print(TAG+'_SEARCH_START',arm,rep,'beams',len(BEAMS),'queries',100000,flush=True)
    start=time.monotonic()
    with std.open('x') as f:
        proc=subprocess.run(full,env=env,stdout=f,stderr=subprocess.STDOUT,
                            timeout=5400,check=False)
    elapsed=time.monotonic()-start
    ensure(proc.returncode==0,'EVAL_NONZERO_'+tag+'_'+str(proc.returncode))
    ensure(safe_file(tm) and 'Exit status: 0' in tm.read_text(errors='replace'),
           'TIME_NONZERO_'+tag)
    rows=parse(std.read_text(errors='replace'))
    rec={'arm':arm,'rep':rep,'graph':str(graph),'graph_sha':p.GRAPH_SHA[(arm,rep)],
         'cpu':0,'threads':1,'nqueries':100000,'command':cmd,'beams':list(BEAMS),
         'evaluator_sha':p.EVAL_SHA,
         'stdout':str(std),'stdout_sha':digest(std),
         'timefile':str(tm),'timefile_sha':digest(tm),
         'wall_s_diagnostic_not_qps_comparison':elapsed,
         'rows':rows,'status':'NATIVE_100KQ_EIGHT_BEAM_EVAL_PASS'}
    m99=crossing(rows,.99);m998=crossing(rows,.998)
    print(TAG+'_SEARCH_PASS',arm,rep,'max_anchor_recall_delta_pending_audit',
          'beam_floor099',m99.get('selected_beam_in_tested_grid','NOT_BRACKETED'),
          'beam_floor0998',m998.get('selected_beam_in_tested_grid','NOT_BRACKETED'),flush=True)
    return rec


def verify_one(rec,p,prior):
    arm,rep=rec['arm'],rec['rep']
    ensure(arm in ARMS and rep in (1,2,3),'RUN_ID')
    tag=f'mst1m_{arm}_r{rep}'
    graph=p.R90/'r90_p4_msturing1m_stock_h17_fastv2_4cpu_build_v1'/'graphs'/(tag+'.graph')
    std=OUT/'logs'/(tag+'.stdout');tm=OUT/'logs'/(tag+'.time')
    ensure(rec['graph']==str(graph) and rec['graph_sha']==p.GRAPH_SHA[(arm,rep)],'GRAPH_RECEIPT_'+tag)
    ensure(rec['cpu']==0 and rec['threads']==1 and rec['nqueries']==100000
           and rec['evaluator_sha']==p.EVAL_SHA and rec['beams']==list(BEAMS),
           'EXECUTION_STATE_'+tag)
    ensure(rec['command']==[str(p.EVAL),str(graph),str(p.BASE),str(p.QUERY),str(p.GT),
                            ','.join(map(str,BEAMS))],'NATIVE_COMMAND_'+tag)
    for path,name in ((std,'stdout'),(tm,'timefile')):
        ensure(safe_file(path) and rec[name]==str(path) and
               rec[name+'_sha']==digest(path),'LOG_SHA_'+tag+'_'+name)
    ensure('Exit status: 0' in tm.read_text(errors='replace'),'EXIT_STATUS_'+tag)
    rows=parse(std.read_text(errors='replace'))
    ensure(rec['rows']==rows,'LOG_PARSER_DRIFT_'+tag)
    for b in (384,896):
        old=prior[(arm,rep)][str(b)]['recall_at10'];new=rows[str(b)]['recall_at10']
        ensure(abs(new-old)<=0.00005,'P4Q_RECALL_ANCHOR_DRIFT_'+tag+'_b'+str(b))
    return rows


def expected_report(st,prior):
    records=[];byarm={a:{'0.99':[],'0.998':[]} for a in ARMS}
    for rec in st['searches']:
        arm,rep=rec['arm'],rec['rep']
        x={str(t):crossing(rec['rows'],t) for t in TARGETS}
        records.append({'arm':arm,'build_rep':rep,'graph_sha':rec['graph_sha'],
                        'max_recall_anchor_delta':max(abs(rec['rows'][str(b)]['recall_at10']-prior[(arm,rep)][str(b)]['recall_at10']) for b in (384,896)),
                        'targets':x})
        for k,v in x.items():
            if v['status']=='BRACKETED_MEASURED_QUALITY_FLOOR':
                byarm[arm][k].append({'build_rep':rep,**v})
    grouped={}
    for arm,targetdata in byarm.items():
        grouped[arm]={}
        for t in TARGETS:
            x=targetdata[str(t)]
            grouped[arm][str(t)]={'n_bracketed_graphs':len(x),
                 'selected_beams':[r['selected_beam_in_tested_grid'] for r in x],
                 'mean_observed_recall':statistics.mean(r['observed_recall'] for r in x) if x else None,
                 'mean_observed_qps':statistics.mean(r['observed_qps'] for r in x) if x else None,
                 'mean_observed_latency_us_proxy':statistics.mean(r['observed_latency_us_proxy'] for r in x) if x else None,
                 'per_graph':x}
    comparisons={}
    for aa,bb in (('stock','h17'),('h17','fast'),('stock','fast')):
        comparisons[aa+'_to_'+bb]={}
        for t in TARGETS:
            x,y=grouped[aa][str(t)],grouped[bb][str(t)]
            if x['n_bracketed_graphs']>0 and y['n_bracketed_graphs']>0:
                comparisons[aa+'_to_'+bb][str(t)]={
                    'qps_ratio_means_b_over_a':y['mean_observed_qps']/x['mean_observed_qps'],
                    'qps_change_pct':100*(y['mean_observed_qps']/x['mean_observed_qps']-1),
                    'recall_delta_pp':100*(y['mean_observed_recall']-x['mean_observed_recall'])}
    n_expected=len(st['searches'])
    complete=all(grouped[arm][str(t)]['n_bracketed_graphs']==n_expected//3 for arm in ARMS for t in TARGETS)
    return {'status':('BRACKETED_QUALITY_FLOORS_ON_TESTED_GRID' if complete else
                      'BRACKET_INCOMPLETE_NEEDS_EXTEND_BEAM_GRID'),
            'independent_build_graphs_per_arm':n_expected//3,
            'native_search_calls':n_expected,'queries_per_search':100000,
            'beams_tested':list(BEAMS),'targets':list(TARGETS),
            'per_graph':records,'per_arm':grouped,'comparisons':comparisons,
            'not_exact_matched_recall':True,'not_global_minimum_beam':True,
            'not_formal_equivalence_or_noninferiority':True,
            'qps_one_search_call_per_graph':True,
            'no_tail_latency_p95_p99':True,
            'legacy_avg_cmps_highbeam_invalid':True,
            'source_vintage_note':'Stock ELF from R86, H17/Fast from R90; code/compiler vintage confound.',
            'guidance':'Selected beam is first satisfying sampled grid quality floor. Interpolated exact-target latency, where available, is NOT measured. Further fine-grid sweep and repeated QPS required.'}


def audit_stage(stage):
    p,prior,receipt=prior_verified()
    path=OUT/('pilot_manifest.json' if stage=='pilot' else 'full_manifest.json')
    report=OUT/('pilot_matched_summary.json' if stage=='pilot' else 'full_matched_summary.json')
    ensure(safe_file(path),'STAGE_MANIFEST_MISSING_'+stage)
    st=json.loads(path.read_text())
    want='PILOT_3_GRAPH_COMPLETE' if stage=='pilot' else 'FULL_9_GRAPH_COMPLETE'
    expected={(a,1) for a in ARMS} if stage=='pilot' else {(a,i) for a in ARMS for i in (1,2,3)}
    ensure(st.get('status')==want and st.get('script_sha')==digest(Path(__file__)) and
           st.get('p4q_frozen_source')==receipt and
           st.get('beams')==list(BEAMS) and len(st.get('searches',[]))==len(expected),
           'STAGE_MANIFEST_STATE')
    seen=set()
    for rec in st['searches']:
        k=(rec['arm'],rec['rep'])
        ensure(k in expected and k not in seen,'RUN_COVERAGE_'+str(k))
        seen.add(k);verify_one(rec,p,prior)
    ensure(seen==expected,'STAGE_KEYS')
    output=expected_report(st,prior)
    atomic(report,output,first=True)
    print(TAG+'_AUDIT_'+stage.upper()+'_PASS_NATIVE_SHA_ANCHOR_AND_GRID',
          'bracket_status',output['status'],flush=True)
    print(TAG+'_REPORT',str(report),flush=True)
    return output


def pilot():
    preflight()
    p,prior,receipt=prior_verified()
    OUT.mkdir(mode=0o700)
    (OUT/'logs').mkdir(mode=0o700)
    st={'status':'PILOT_RUNNING','script_sha':digest(Path(__file__)),
        'p4q_frozen_source':receipt,'beams':list(BEAMS),'searches':[],
        'no_build':True,'source_quality_floor_grid':True}
    atomic(OUT/'progress.json',st,first=True)
    for arm in ARMS:
        st['searches'].append(execute_one(p,arm,1))
        atomic(OUT/'progress.json',st)
    st['status']='PILOT_3_GRAPH_COMPLETE'
    atomic(OUT/'pilot_manifest.json',st,first=True)
    print(TAG+'_PILOT_COMPLETE_3_NATIVE_100KQ_EIGHTBEAM_SEARCHES__AUDIT_REQUIRED',flush=True)


def auditpilot():
    return audit_stage('pilot')


def full():
    p,prior,receipt=prior_verified()
    prior_report=OUT/'pilot_matched_summary.json'
    ensure(safe_file(prior_report),'PILOT_AUDIT_REQUIRED')
    pilotm=OUT/'pilot_manifest.json'
    ensure(safe_file(pilotm),'PILOT_MANIFEST_REQUIRED')
    old=json.loads(pilotm.read_text())
    ensure(old.get('status')=='PILOT_3_GRAPH_COMPLETE' and
           old.get('script_sha')==digest(Path(__file__)) and
           old.get('p4q_frozen_source')==receipt,
           'PILOT_FROZEN_STATE')
    verify={ (r['arm'],r['rep']) for r in old['searches']}
    ensure(verify=={(a,1) for a in ARMS},'PILOT_COVERAGE')
    for r in old['searches']:verify_one(r,p,prior)
    report=json.loads(prior_report.read_text())
    ensure(report==expected_report(old,prior) and
           report['status']=='BRACKETED_QUALITY_FLOORS_ON_TESTED_GRID',
           'PILOT_BRACKET_INCOMPLETE_HOLD')
    for arm in ARMS:
        for rep in (2,3):
            for ext in ('stdout','time'):
                target=OUT/'logs'/(f'mst1m_{arm}_r{rep}.{ext}')
                ensure(not target.exists() and not target.is_symlink(),'FULL_ALREADY_PARTIAL_'+str(target))
    ensure(not (OUT/'full_manifest.json').exists() and not
           (OUT/'full_manifest.json').is_symlink(),'FULL_MANIFEST_EXISTS')
    st={**old,'status':'FULL_RUNNING','searches':list(old['searches'])}
    atomic(OUT/'progress.json',st)
    for rep in (2,3):
        for arm in ARMS:
            st['searches'].append(execute_one(p,arm,rep))
            atomic(OUT/'progress.json',st)
    st['status']='FULL_9_GRAPH_COMPLETE'
    atomic(OUT/'full_manifest.json',st,first=True)
    print(TAG+'_FULL_COMPLETE_9_NATIVE_100KQ_SEARCHES__AUDIT_REQUIRED',flush=True)


def audit():
    return audit_stage('full')


def main():
    q=argparse.ArgumentParser(description=__doc__)
    q.add_argument('phase',choices=('selftest','preflight','pilot','auditpilot','full','audit'))
    phase=q.parse_args().phase
    globals()[phase]()

if __name__=='__main__':
    try: main()
    except Exception as e:
        print(TAG+'_HOLD',type(e).__name__,str(e),file=sys.stderr,flush=True)
        sys.exit(2)
