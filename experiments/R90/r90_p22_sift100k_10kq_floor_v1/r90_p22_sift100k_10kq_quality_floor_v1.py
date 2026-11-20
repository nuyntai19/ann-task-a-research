#!/usr/bin/env python3
"""R90 P2.2: read-only 10K-query quality-floor evaluation of FOUR saved P2.1 graphs.

The runner NEVER builds or modifies graphs, C++ source, or historical artifacts.
It requires the exact 4 existing R90 P2.1 graph SHA256 values, 10K-query/GT SHA,
and the previously compiled H85/R72 native search evaluator SHA.

Usage: python3 r90_p22_sift100k_10kq_quality_floor_v1.py {selftest,preflight,pilot,audit}

PILOT = 1 independent graph / arm, one 10K-query dense beam sweep / arm,
then 5 repeated native search evaluations at smallest tested beam meeting each
Recall quality floor (.990 or .998). These are quality-FLOOR comparisons, not
exact matched Recall, and there are no new independent graph BUILD repetitions.
"""
import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import statistics
import struct
import subprocess
import sys
import time

ROOT=Path.home()/'ann-task-a'
P2=ROOT/'experiments/R90/r90_p2_sift100k_pass2_value_gate1_v1'
OUT=ROOT/'experiments/R90/r90_p22_sift100k_10kq_floor_v1'
BASE=ROOT/'data/sift100k.fbin'
QUERY=ROOT/'data/sift1m_queries.fbin'
GT=ROOT/'experiments/H85/r85_b1_controlled/step8e_gt10k/sift100k_sift1mqueries10k_exact100.ibin'
EVAL=ROOT/'experiments/H85/r85_b1_controlled/step8e_native_eval/r85_b1_100k_graph_recall'
INPUTS={
 'base':(BASE,'e50ff1bc34bcc6d1c97dd001023c09a666971cde64605cc06671ed8a8ff1ed12'),
 'query':(QUERY,'9b0082b67d0ac55b4c7d42216560344567ad87ce3e75a9d5214a0762f1c15d65'),
 'gt':(GT,'70d25b3fff9d68ee3571931cc28e36f03d77c8bb4eea089ca206e5e709be8e28'),
 'evaluator':(EVAL,'3698f915ef3b7369aee527b6bb126512c0e31eb677a46480a5526cf4f909c64a'),
}
GRAPHS={
 'stock_N1':'67310319473693823c37bb441fdfb97ceb3c379f6da50f46e7623f8141559781',
 'stock_N2':'4998cb93784da92728f2f6bd02aee6d3006d44c2b80f7b8b5be2a7f85f27d3e1',
 'a5_dryrun_q001_N2':'4998cb93784da92728f2f6bd02aee6d3006d44c2b80f7b8b5be2a7f85f27d3e1',
 'a5_gate_q001_N2':'4cceb72e0dcb34f030f9cd447f2d7da2ed67a166f32188f7cfde20bcdd72e9c0',
}
BEAMS=[40,48,56,64,72,80,88,96,104,112,128,144,160,176,192,224,256,320]
TARGETS=[0.990,0.998]
REPS=5
ROW=re.compile(r'^R72_RECALL_ROW beam=(\d+) recall=([0-9.]+) qps=([0-9.]+) avg_cmps=([0-9.]+) avg_visited=([0-9.]+)\s*$',re.M)


def ck(cond,msg):
    if not cond: raise RuntimeError('R90_P22_HOLD_'+msg)

def sha(p):
    h=hashlib.sha256()
    with open(p,'rb') as f:
        for buf in iter(lambda:f.read(4*1024*1024),b''):h.update(buf)
    return h.hexdigest()

def shape(p,entry_bytes):
    with p.open('rb') as f: head=f.read(8)
    ck(len(head)==8,'SHORT_HEADER_'+p.name)
    n,d=struct.unpack('<II',head)
    ck(p.stat().st_size==8+n*d*entry_bytes,'WRONG_SIZE_'+p.name)
    return n,d

def progress_write(path,data):
    temp=path.with_suffix('.json.part')
    with temp.open('w',encoding='utf-8') as f:json.dump(data,f,indent=2);f.write('\n')
    os.replace(temp,path)

def parse(log,expected_beams):
    ck(log.count('R72_RECALL_INPUT_PASS')==1,'EVAL_INPUT_MARKER')
    ck(log.count('R72_RECALL_EVAL_PASS')==1,'EVAL_PASS_MARKER')
    found=ROW.findall(log)
    ck(len(found)==len(expected_beams),'ROW_COUNT')
    result=[]
    for t,b in enumerate(found):
        beam=int(b[0]); recall,qps,cmps,visited=map(float,b[1:])
        ck(beam==expected_beams[t],'BEAM_ORDER')
        ck(0<=recall<=1 and qps>0 and cmps>=0 and visited>=0,'NONFINITE_OR_BAD_ROW')
        result.append({'beam':beam,'recall':recall,'qps':qps,'avg_cmps':cmps,'avg_visited':visited})
    return result

def p2_parent_check():
    manifest=P2/'result_manifest.json'
    ck(manifest.is_file(),'P2_PARENT_MANIFEST_MISSING')
    parent=json.loads(manifest.read_text())
    ck(parent.get('status')=='NATIVE_SCREEN_COMPLETED','P2_NOT_COMPLETE')
    builds=parent.get('builds',[])
    ck(len(builds)==4 and {x['arm'] for x in builds}==set(GRAPHS),'P2_ARM_SET')
    ck(parent.get('build_reps_per_arm')==1,'P2_BUILD_REPS_NOT_ONE')
    for entry in builds:
        tag=entry['arm']
        expected=P2/'graphs'/f'{tag}.graph'
        # Verify no graph path is redirected outside the parent experiment.
        ck(Path(entry['graph_path']).resolve()==expected.resolve(),'P2_GRAPH_LOCATION_'+tag)
        ck(expected.is_file(),'P2_GRAPH_MISSING_'+tag)
        with expected.open('rb') as f: head=f.read(8)
        ck(head==struct.pack('<II',100000,64),'P2_GRAPH_HEADER_'+tag)
        digest=sha(expected)
        ck(digest==GRAPHS[tag] and digest==entry['graph_sha256'],'P2_GRAPH_SHA_'+tag)
        for suffix in [('build_log','build_log_sha256'),('time_log','time_log_sha256')]:
            log=Path(entry[suffix[0]])
            ck(log.is_file() and sha(log)==entry[suffix[1]],'P2_BUILD_RECEIPT_'+tag)
    ck(GRAPHS['stock_N2']==GRAPHS['a5_dryrun_q001_N2'],'P2_DRYRUN_PARITY')
    print('R90_P22_PARENT_4_GRAPH_SHA_BUILD_RECEIPT_AND_DRYRUN_PARITY_PASS',flush=True)
    return parent

def preflight(out,cpu,output_new):
    ck(shutil.which('taskset') is not None,'TASKSET_MISSING')
    ck(cpu in os.sched_getaffinity(0),'CPU_NOT_ALLOWED')
    ck(out.parent.is_dir(),'OUTPUT_PARENT_MISSING')
    if output_new: ck(not out.exists() and not out.is_symlink(),'OUTPUT_EXISTS')
    p2_parent_check()
    for name,(p,digest) in INPUTS.items():
        ck(p.is_file(),'INPUT_MISSING_'+name)
        found=sha(p);ck(found==digest,'INPUT_SHA_'+name)
        print('R90_P22_INPUT_SHA_PASS',name,found,flush=True)
    ck(shape(BASE,4)==(100000,128),'BASE_SHAPE')
    ck(shape(QUERY,4)==(10000,128),'QUERY_SHAPE')
    ck(shape(GT,8)==(10000,100),'GT_SHAPE')
    ck(os.access(EVAL,os.X_OK),'EVAL_NOT_EXECUTABLE')
    # Ground-truth exactness provenance is from the pinned H85 manifest;
    # the SHA check above validates the complete GT file.
    print('R90_P22_PREFLIGHT_PASS_SIFT100K_10000QUERY_100GT_READONLY',flush=True)

def env_native():
    env=os.environ.copy()
    env['PARLAY_NUM_THREADS']='1';env['OMP_NUM_THREADS']='1';env['LC_ALL']='C'
    env.pop('R90_A5_MODE',None);env.pop('R90_A5_FRACTION',None)
    return env

def native(out,tag,phase,rep,beams,cpu):
    stem=f'{tag}.{phase}.r{rep}'
    logfile=out/'logs'/f'{stem}.stdout'
    ck(not logfile.exists(),'LOG_EXISTS_'+stem)
    graph=P2/'graphs'/f'{tag}.graph'
    args=['taskset','-c',str(cpu),str(EVAL),str(graph),str(BASE),str(QUERY),str(GT),','.join(map(str,beams))]
    start=time.perf_counter()
    with logfile.open('x',encoding='utf-8') as f:
        ret=subprocess.run(args,env=env_native(),stdout=f,stderr=subprocess.STDOUT,timeout=1200,check=False)
    wall=time.perf_counter()-start
    ck(ret.returncode==0,'NATIVE_EXIT_'+stem)
    rows=parse(logfile.read_text(errors='replace'),beams)
    return {'arm':tag,'phase':phase,'rep':rep,'beams':beams,'rows':rows,'cmd':args,
            'wall_s':wall,'log_path':str(logfile),'log_sha256':sha(logfile),
            'graph_sha256':GRAPHS[tag]}

def pilot(out,cpu):
    preflight(out,cpu,True)
    out.mkdir();(out/'logs').mkdir()
    meta={'status':'RUNNING','source':'R90 P2.1 4 saved verified graphs','source_manifest':str(P2/'result_manifest.json'),
          'script_sha256':sha(Path(__file__).resolve()),'cpu':cpu,'query_count':10000,
          'dataset':'SIFT100K','beams':BEAMS,'targets':TARGETS,'repeats_per_graph':REPS,
          'inputs_sha256':{k:v[1] for k,v in INPUTS.items()},'graphs_sha256':GRAPHS,
          'caveats':['ONLY one independently built graph per arm; NOT a 3x5 formal study',
                     'Quality-FLOOR at smallest TESTED beam; NOT exact matched Recall',
                     'Probe sweep QPS is exploratory; use independent 5-repeat median at calibrated beams',
                     'All 10K queries and GT share pinned SHA; no graph or C++ source modification',
                     'No native p50/p95/p99, Build-W_P/W_L, or new selector test'],
          'runs':[],'calibrations':{}}
    progress_write(out/'progress.json',meta)
    sweep_order=list(GRAPHS)
    for tag in sweep_order:
        print('R90_P22_SWEEP_START',tag,'beams',BEAMS,flush=True)
        record=native(out,tag,'sweep',1,BEAMS,cpu)
        meta['runs'].append(record)
        cal={}
        for target in TARGETS:
            qualifying=[r for r in record['rows'] if r['recall']>=target]
            ck(qualifying,'TARGET_NOT_REACHED_'+tag+'_'+str(target))
            best=qualifying[0]
            cal[str(target)]={'beam':best['beam'],'sweep_recall':best['recall']}
        meta['calibrations'][tag]=cal
        progress_write(out/'progress.json',meta)
        print('R90_P22_SWEEP_PASS',tag,'calibration',json.dumps(cal,sort_keys=True),flush=True)
    # Alternate tag order across repetitions to mitigate order-related QPS variation.
    for rep in range(1,REPS+1):
        tags=sweep_order[rep%len(sweep_order):]+sweep_order[:rep%len(sweep_order)]
        if rep%2==0:tags.reverse()
        for tag in tags:
            cal=meta['calibrations'][tag]
            beams=sorted({x['beam'] for x in cal.values()})
            print('R90_P22_REPEAT_START',tag,'rep',rep,'beams',beams,flush=True)
            rec=native(out,tag,'repeat',rep,beams,cpu)
            for target in TARGETS:
                beam=cal[str(target)]['beam']
                matching=next(z for z in rec['rows'] if z['beam']==beam)
                ck(matching['recall']>=target,'TARGET_RECALL_REP_FAIL_'+tag)
                ck(abs(matching['recall']-cal[str(target)]['sweep_recall'])<2e-6,
                   'RECALL_PARITY_'+tag)
            meta['runs'].append(rec)
            progress_write(out/'progress.json',meta)
            print('R90_P22_REPEAT_PASS',tag,'rep',rep,flush=True)
    output=[]
    for tag in sweep_order:
        for target in TARGETS:
            selection=meta['calibrations'][tag][str(target)]
            beam=selection['beam']
            matching=[next(row for row in entry['rows'] if row['beam']==beam)
                      for entry in meta['runs'] if entry['arm']==tag and entry['phase']=='repeat']
            ck(len(matching)==REPS,'REPEAT_COUNT_'+tag)
            output.append({'arm':tag,'target':target,'beam':beam,'recall_at10':matching[0]['recall'],
               'qps_median5':statistics.median(r['qps'] for r in matching),
               'qps_min':min(r['qps'] for r in matching),'qps_max':max(r['qps'] for r in matching),
               'avg_cmps_median5':statistics.median(r['avg_cmps'] for r in matching),
               'avg_visited_median5':statistics.median(r['avg_visited'] for r in matching),
               'search_reps':REPS,'build_reps':1})
    with (out/'floor_summary.csv').open('x',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=list(output[0]));w.writeheader();w.writerows(output)
    meta['summary']=output
    meta['status']='COMPLETE'
    progress_write(out/'result_manifest.json',meta)
    print('R90_P22_10K_QUERY_FLOOR_SUMMARY_BEGIN',flush=True)
    for e in output:
        print('R90_P22_FLOOR',json.dumps(e,sort_keys=True),flush=True)
    print('R90_P22_10K_QUERY_FLOOR_SUMMARY_END',flush=True)
    print('R90_P22_ONE_GRAPH_PER_ARM_FIVE_SEARCH_REPS_PILOT_PASS_NO_MATCHED_RECALL_CLAIM',flush=True)

def audit(out):
    ck(out.is_dir(),'AUDIT_ROOT_MISSING')
    meta=json.loads((out/'result_manifest.json').read_text())
    ck(meta['status']=='COMPLETE','INCOMPLETE')
    ck(meta['script_sha256']==sha(Path(__file__).resolve()),'SCRIPT_SHA_CHANGED')
    ck(meta['graphs_sha256']==GRAPHS,'GRAPH_LIST_CHANGED')
    p2_parent_check()
    ck(len(meta['runs'])==len(GRAPHS)*(1+REPS),'RUN_COUNT')
    ck(len(meta['summary'])==len(GRAPHS)*len(TARGETS),'SUMMARY_COUNT')
    ck(all(GRAPHS[a]==sha(P2/'graphs'/f'{a}.graph') for a in GRAPHS),'SOURCE_GRAPH_CHANGED')
    for x in meta['runs']:
        p=Path(x['log_path'])
        ck(p.is_file() and p.parent.resolve()==(out/'logs').resolve(),'LOG_LOCATION')
        ck(sha(p)==x['log_sha256'],'LOG_SHA_'+p.name)
        ck(parse(p.read_text(errors='replace'),x['beams'])==x['rows'],'LOG_PARSE_'+p.name)
    print('R90_P22_AUDIT_ALL_24_NATIVE_LOGS_SOURCE_GRAPH_SHA_AND_FLOOR_ROWS_PASS',flush=True)

def selftest():
    beams=[40,80]
    synthetic='R72_RECALL_INPUT_PASS graph_nodes=100000 queries=10000 gt_k=100\n' + \
      ''.join(f'R72_RECALL_ROW beam={b} recall=0.998 qps=1000 avg_cmps=200 avg_visited=100\n' for b in beams) + \
      'R72_RECALL_EVAL_PASS\n'
    assert len(parse(synthetic,beams))==2
    assert len(GRAPHS)==4 and len(BEAMS)==len(set(BEAMS)) and all(b<=512 for b in BEAMS)
    assert TARGETS==[0.99,0.998]
    print('R90_P22_LOCAL_SELFTEST_PASS_10K_EVALUATOR_PARSER_AND_FLOOR_CONTRACT',flush=True)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode',choices=['selftest','preflight','pilot','audit'])
    p.add_argument('--cpu',type=int,default=0)
    p.add_argument('--out',type=Path,default=OUT)
    args=p.parse_args()
    out=args.out.expanduser().resolve(strict=False)
    if args.mode=='selftest':selftest()
    elif args.mode=='preflight':preflight(out,args.cpu,True)
    elif args.mode=='pilot':pilot(out,args.cpu)
    else:audit(out)

if __name__=='__main__':
    try:main()
    except Exception as e:
        print('R90_P22_HOLD',type(e).__name__,str(e),file=sys.stderr,flush=True)
        sys.exit(2)
