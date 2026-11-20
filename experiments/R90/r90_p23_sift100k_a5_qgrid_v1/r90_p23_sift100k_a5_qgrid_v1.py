#!/usr/bin/env python3
"""R90-P2.3 exploratory A5 fraction sweep on pinned SIFT100K (GT-free selector).

Produces NEW graphs for A5 gate q={0.005,0.02,0.05}. Reuses the pinned
R90-P2.1 Stock N1/N2 and A5 q=0.01 graphs as saved-graph controls.
All searches use 10,000 held-out public SIFT queries and the existing
H85/R72 native evaluator. No historical graph/source/result is modified.

This is ONE BUILD per new q, 3 SEARCH repetitions per graph by default.
It is only a quality-floor pilot, not exactly matched-Recall or a 3x5 claim.
"""
import argparse
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import statistics
import struct
import subprocess
import sys
import time

ROOT = Path.home() / 'ann-task-a'
P21 = ROOT / 'experiments/R90/r90_p2_sift100k_pass2_value_gate1_v1'
P22 = ROOT / 'experiments/R90/r90_p22_sift100k_10kq_floor_v1'
OUT = ROOT / 'experiments/R90/r90_p23_sift100k_a5_qgrid_v1'
A5 = ROOT / 'experiments/R90/r90_p0_stock_a5_compile_gate_v1/a5_build/algorithms/PipNN/neighbors-pipnn_FLOAT_T_EUCLIDEAN'
BASE = ROOT / 'data/sift100k.fbin'
QUERY = ROOT / 'data/sift1m_queries.fbin'
GT = ROOT / 'experiments/H85/r85_b1_controlled/step8e_gt10k/sift100k_sift1mqueries10k_exact100.ibin'
EVAL = ROOT / 'experiments/H85/r85_b1_controlled/step8e_native_eval/r85_b1_100k_graph_recall'
INPUTS = {
 'base':(BASE,'e50ff1bc34bcc6d1c97dd001023c09a666971cde64605cc06671ed8a8ff1ed12'),
 'query':(QUERY,'9b0082b67d0ac55b4c7d42216560344567ad87ce3e75a9d5214a0762f1c15d65'),
 'gt':(GT,'70d25b3fff9d68ee3571931cc28e36f03d77c8bb4eea089ca206e5e709be8e28'),
 'evaluator':(EVAL,'3698f915ef3b7369aee527b6bb126512c0e31eb677a46480a5526cf4f909c64a'),
 'a5_elf':(A5,'aebdae764f3e79ff709546787c22e3df910dbb1934851ce7ddfaf4927ff10fa2'),
}
PARENT_SHA = {
 'stock_N1':'67310319473693823c37bb441fdfb97ceb3c379f6da50f46e7623f8141559781',
 'stock_N2':'4998cb93784da92728f2f6bd02aee6d3006d44c2b80f7b8b5be2a7f85f27d3e1',
 'a5_dryrun_q001_N2':'4998cb93784da92728f2f6bd02aee6d3006d44c2b80f7b8b5be2a7f85f27d3e1',
 'a5_gate_q001_N2':'4cceb72e0dcb34f030f9cd447f2d7da2ed67a166f32188f7cfde20bcdd72e9c0',
}
# Start with ONLY a small sweep; 10% and 25% already showed nearly no headroom
# in SIFT10K dryrun. These new fractions are NOT claimed optimal.
NEW_Q = [
 ('a5_gate_q0p5_N2','0.005'),
 ('a5_gate_q2_N2','0.02'),
 ('a5_gate_q5_N2','0.05'),
]
CONTROL = ['stock_N1','stock_N2','a5_gate_q001_N2']
BEAMS = [40,48,56,64,72,80,88,96,104,112,128,144,160,176,192,224,256,320]
TARGETS = [0.99,0.998]
ROW = re.compile(r'^R72_RECALL_ROW beam=(\d+) recall=([0-9.]+) qps=([0-9.]+) avg_cmps=([0-9.]+) avg_visited=([0-9.]+)\s*$',re.M)
SCREEN = re.compile(r'R90_A5_LEAF_SCREEN total=(\d+) eligible=(\d+) WL_total=(\d+) WL_eligible=(\d+) gate=(\d+)')
SELECT = re.compile(r'R90_A5_PASS1 selected=(\d+) n=(\d+) sort_comparisons=(\d+) GT_free=1')

def ck(ok, label):
    if not ok:
        raise RuntimeError('R90_P23_HOLD_'+label)

def sha(p):
    h = hashlib.sha256()
    with Path(p).open('rb') as f:
        for chunk in iter(lambda:f.read(4*1024*1024),b''):h.update(chunk)
    return h.hexdigest()

def store_json(p,doc):
    tmp = p.with_name(p.name+'.part')
    with tmp.open('x',encoding='utf-8') as f:json.dump(doc,f,indent=2);f.write('\n')
    os.replace(tmp,p)

def overwrite_json(p,doc):
    tmp=p.with_name(p.name+'.part')
    with tmp.open('w',encoding='utf-8') as f:json.dump(doc,f,indent=2);f.write('\n')
    os.replace(tmp,p)

def shape(path,element_bytes):
    with path.open('rb') as f:h=f.read(8)
    ck(len(h)==8,'HEADER_'+path.name)
    n,d=struct.unpack('<II',h)
    ck(path.stat().st_size==8+n*d*element_bytes,'SHAPE_'+path.name)
    return n,d

def graph(path):
    with path.open('rb') as f:h=f.read(8)
    ck(h==struct.pack('<II',100000,64),'GRAPH_HEADER_'+path.name)
    ck(path.stat().st_size>400008,'GRAPH_TRUNCATED_'+path.name)
    return path

def native_env(mode=None,fraction=None):
    env=os.environ.copy();env['PARLAY_NUM_THREADS']='1';env['OMP_NUM_THREADS']='1';env['LC_ALL']='C'
    env.pop('R90_A5_MODE',None);env.pop('R90_A5_FRACTION',None)
    if mode is not None:env['R90_A5_MODE']=mode
    if fraction is not None:env['R90_A5_FRACTION']=str(fraction)
    return env

def parse_eval(text,expected_beams):
    ck(text.count('R72_RECALL_INPUT_PASS')==1 and text.count('R72_RECALL_EVAL_PASS')==1,'EVAL_MARKERS')
    rows=ROW.findall(text)
    ck(len(rows)==len(expected_beams),'EVAL_ROW_COUNT')
    ans=[]
    for i,r in enumerate(rows):
        b=int(r[0]);rec,qps,cmps,visited=map(float,r[1:])
        ck(b==expected_beams[i] and all(math.isfinite(x) for x in (rec,qps,cmps,visited)) and
           0<=rec<=1 and qps>0 and cmps>=0 and visited>=0,'EVAL_ROW_'+str(i))
        ans.append({'beam':b,'recall':rec,'qps':qps,'avg_cmps':cmps,'avg_visited':visited})
    return ans

def parse_build(s,q):
    sel=SELECT.findall(s);cov=SCREEN.findall(s)
    ck(len(sel)==1 and len(cov)==1,'BUILD_MARKERS')
    selected,n,sort_cmps=map(int,sel[0])
    t,e,wt,we,gate=map(int,cov[0])
    ck(n==100000 and selected==int(n*float(q)),'SELECTED_COUNT')
    ck(t>0 and 0<=e<=t and wt>0 and 0<=we<=wt and gate==1,'COVERAGE_VALUES')
    ck('R90_A5_MODE=gate' in s,'GATE_MODE_NOT_ACTIVE')
    return {'fraction':float(q),'selected_points':selected,'sort_comparisons':sort_cmps,
            'total_leaves':t,'eligible_leaves':e,'eligible_leaf_pct':100*e/t,
            'wl_total':wt,'wl_eligible':we,'retained_wl_pct':100*we/wt,
            'skipped_wl_pct':100*(wt-we)/wt,'gate':gate}

def parent_check():
    p21=P21/'result_manifest.json';p22=P22/'result_manifest.json'
    ck(p21.is_file() and p22.is_file(),'PARENT_MANIFEST_MISSING')
    a=json.loads(p21.read_text());b=json.loads(p22.read_text())
    ck(a.get('status')=='NATIVE_SCREEN_COMPLETED' and b.get('status')=='COMPLETE','PARENT_INCOMPLETE')
    ck(len(a.get('builds',[]))==4 and a.get('build_reps_per_arm')==1,'P21_REP_AND_COUNT')
    ck(b.get('graphs_sha256')==PARENT_SHA and len(b.get('summary',[]))==8,'P22_GRAPH_SUMMARY')
    for tag,digest in PARENT_SHA.items():
        file=P21/'graphs'/f'{tag}.graph'
        ck(file.is_file() and sha(graph(file))==digest,'PARENT_GRAPH_'+tag)
    built={x['arm']:x for x in a['builds']}
    ck(set(built)==set(PARENT_SHA),'P21_BUILD_ARMS')
    for tag in built:
        ck(built[tag]['graph_sha256']==PARENT_SHA[tag],'P21_RECEIPT_'+tag)
    return a,b

def preflight(out,cpu,fresh=True):
    ck(out.parent.is_dir(),'OUT_PARENT_MISSING')
    if fresh:ck(not out.exists() and not out.is_symlink(),'OUT_EXISTS')
    ck(shutil.which('taskset') is not None and Path('/usr/bin/time').is_file(),'NATIVE_UTIL_MISSING')
    ck(cpu in os.sched_getaffinity(0),'CPU_NOT_ALLOWED')
    for name,(path,digest) in INPUTS.items():
        ck(path.is_file() and sha(path)==digest,'INPUT_SHA_'+name)
        print('R90_P23_INPUT_SHA_PASS',name,digest,flush=True)
    ck(shape(BASE,4)==(100000,128),'BASE_SHAPE')
    ck(shape(QUERY,4)==(10000,128),'QUERY_SHAPE')
    ck(shape(GT,8)==(10000,100),'GT_SHAPE')
    ck(os.access(A5,os.X_OK) and os.access(EVAL,os.X_OK),'ELF_NOT_EXECUTABLE')
    parent_check()
    print('R90_P23_PREFLIGHT_PASS_PINNED_SIFT100K_10KQ_GT_PARENT_SHA',flush=True)

def build_command(destination):
    return [str(A5),'-base_path',str(BASE),'-graph_outfile',str(destination),
            '-num_clusters','2','-cluster_size','1024','-table_size','160',
            '-top_level_leaders','100','-fanout_scheme','10,3,1','-mst_deg','2',
            '-prune','1','-prune_all','1','-prune_degree','64','-hash_bits','12',
            '-alpha','1.1','-k','0']

def build(out,tag,q,cpu):
    path=out/'graphs'/f'{tag}.graph'
    ck(not path.exists(),'GRAPH_ALREADY_EXISTS_'+tag)
    cmd=['taskset','-c',str(cpu),*build_command(path)]
    log=out/'logs'/f'{tag}.build.stdout'
    timer=out/'logs'/f'{tag}.build.time'
    print('R90_P23_BUILD_START',tag,'fraction',q,flush=True)
    start=time.perf_counter()
    with log.open('x',encoding='utf-8') as f:
        ret=subprocess.run(['/usr/bin/time','-v','-o',str(timer),*cmd],env=native_env('gate',q),
                           stdout=f,stderr=subprocess.STDOUT,check=False,timeout=1500)
    elapsed=time.perf_counter()-start
    ck(ret.returncode==0,'BUILD_EXIT_'+tag)
    graph(path)
    coverage=parse_build(log.read_text(errors='replace'),q)
    data={'arm':tag,'fraction':float(q),'build_wall_s':elapsed,'graph_path':str(path),
          'graph_sha256':sha(path),'graph_bytes':path.stat().st_size,
          'coverage':coverage,'command':cmd,'stdout_path':str(log),
          'stdout_sha256':sha(log),'time_path':str(timer),'time_sha256':sha(timer)}
    print('R90_P23_BUILD_PASS',tag,'wall_s',round(elapsed,3),'coverage',json.dumps(coverage,sort_keys=True),flush=True)
    return data

def eval_saved(out,tag,graphpath,phase,rep,beams,cpu):
    log=out/'logs'/f'{tag}.{phase}.r{rep}.stdout'
    ck(not log.exists(),'EVAL_LOG_EXISTS_'+log.name)
    cmd=['taskset','-c',str(cpu),str(EVAL),str(graphpath),str(BASE),str(QUERY),str(GT),','.join(map(str,beams))]
    with log.open('x',encoding='utf-8') as f:
        ret=subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT,env=native_env(),check=False,timeout=1500)
    ck(ret.returncode==0,'EVAL_EXIT_'+log.name)
    rows=parse_eval(log.read_text(errors='replace'),beams)
    return {'arm':tag,'phase':phase,'rep':rep,'beams':beams,'rows':rows,
            'log_path':str(log),'log_sha256':sha(log),'command':cmd,
            'graph_sha256':sha(graphpath)}

def pilot(out,cpu,reps):
    preflight(out,cpu,True)
    _,old=parent_check()
    out.mkdir();(out/'graphs').mkdir();(out/'logs').mkdir()
    meta={'status':'RUNNING','script_sha256':sha(Path(__file__).resolve()),'cpu':cpu,'reps':reps,
          'inputs_sha256':{k:d for k,(_,d) in INPUTS.items()},'new_fractions':NEW_Q,
          'old_sha':PARENT_SHA,'old_p22_manifest_path':str(P22/'result_manifest.json'),
          'builds':[],'runs':[],'calibrations':{},'summary':[],
          'limits':['ONE new BUILD per fraction, no independent BUILD repetitions',
                    'Quality floor from fixed 18-point beam grid, NOT exact matched Recall',
                    'Search QPS comparison only as pilot; 10K public queries and 3/5 rep Search',
                    'Selected set ranks by PASS1 degree and breaks ties by ID, NOT verified optimal',
                    'No change to source, old results, or historical graph files']}
    overwrite_json(out/'progress.json',meta)
    for tag,q in NEW_Q:
        x=build(out,tag,q,cpu);meta['builds'].append(x)
        overwrite_json(out/'progress.json',meta)
    # reuse controls without rebuilding; calibration from completed pinned P2.2
    for tag in CONTROL:
        meta['calibrations'][tag]=old['calibrations'][tag]
    for build_rec in meta['builds']:
        tag=build_rec['arm']
        print('R90_P23_SWEEP_START',tag,flush=True)
        run=eval_saved(out,tag,Path(build_rec['graph_path']),'sweep',1,BEAMS,cpu)
        meta['runs'].append(run)
        cal={}
        for target in TARGETS:
            ok=[r for r in run['rows'] if r['recall']>=target]
            if ok:cal[str(target)]={'beam':ok[0]['beam'],'sweep_recall':ok[0]['recall']}
            else:cal[str(target)]={'beam':None,'sweep_recall':None,'status':'NOT_REACHED_UP_TO_320'}
        meta['calibrations'][tag]=cal
        overwrite_json(out/'progress.json',meta)
        print('R90_P23_SWEEP_PASS',tag,json.dumps(cal,sort_keys=True),flush=True)
    # Run repeated measurements of OLD and NEW graphs in a single campaign,
    # interleaving order to reduce cache/load confounding.
    tags=CONTROL+[t for t,_ in NEW_Q]
    for rep in range(1,reps+1):
        order=tags[(rep-1)%len(tags):]+tags[:(rep-1)%len(tags)]
        if rep%2==0:order.reverse()
        for tag in order:
            c=meta['calibrations'][tag]
            beams=sorted({x['beam'] for x in c.values() if x['beam'] is not None})
            if not beams:continue
            gp= P21/'graphs'/f'{tag}.graph' if tag in CONTROL else out/'graphs'/f'{tag}.graph'
            run=eval_saved(out,tag,gp,'repeat',rep,beams,cpu)
            for target in TARGETS:
                b=c[str(target)]['beam']
                if b is None:continue
                x=next(t for t in run['rows'] if t['beam']==b)
                ck(x['recall']>=target and abs(x['recall']-c[str(target)]['sweep_recall'])<2e-6,
                   'QUALITY_PARITY_'+tag+'_'+str(target))
            meta['runs'].append(run)
            overwrite_json(out/'progress.json',meta)
            print('R90_P23_SEARCH_PASS',tag,'rep',rep,flush=True)
    for tag in tags:
        for target in TARGETS:
            c=meta['calibrations'][tag][str(target)]
            if c['beam'] is None:
                meta['summary'].append({'arm':tag,'target':target,'beam':None,'status':'TARGET_NOT_REACHED',
                                        'qps_median':None,'recall':None,'avg_cmps_median':None})
                continue
            rows=[next(x for x in r['rows'] if x['beam']==c['beam']) for r in meta['runs']
                  if r['phase']=='repeat' and r['arm']==tag]
            ck(len(rows)==reps,'REPEATS_MISSING_'+tag)
            meta['summary'].append({'arm':tag,'target':target,'beam':c['beam'],
                                    'recall':rows[0]['recall'],'qps_median':statistics.median(r['qps'] for r in rows),
                                    'avg_cmps_median':statistics.median(r['avg_cmps'] for r in rows),
                                    'avg_visited_median':statistics.median(r['avg_visited'] for r in rows),
                                    'status':'QUALITY_FLOOR_PASS'})
    with (out/'floor_summary.csv').open('x',newline='',encoding='utf-8') as f:
        cols=['arm','target','beam','status','recall','qps_median','avg_cmps_median','avg_visited_median']
        writer=csv.DictWriter(f,fieldnames=cols);writer.writeheader();writer.writerows(meta['summary'])
    meta['status']='COMPLETE'
    overwrite_json(out/'result_manifest.json',meta)
    for x in meta['summary']:print('R90_P23_QUALITY_FLOOR',json.dumps(x,sort_keys=True),flush=True)
    print('R90_P23_NATIVE_PILOT_COMPLETE_ONE_BUILD_PER_NEW_Q_NOT_FORMAL',flush=True)

def audit(out):
    ck(out.is_dir(),'OUT_MISSING')
    m=out/'result_manifest.json'
    ck(m.is_file(),'RESULT_MISSING')
    x=json.loads(m.read_text());ck(x.get('status')=='COMPLETE','INCOMPLETE')
    ck(x.get('script_sha256')==sha(Path(__file__).resolve()),'SCRIPT_CHANGED')
    preflight(out,x['cpu'],False)
    ck(len(x['builds'])==len(NEW_Q),'BUILD_COUNT')
    ck(len(x['summary'])==2*(len(NEW_Q)+len(CONTROL)),'SUMMARY_COUNT')
    for a in x['builds']:
        p=Path(a['graph_path']);graph(p)
        ck(p.parent.resolve()==(out/'graphs').resolve() and sha(p)==a['graph_sha256'],'GRAPH_SHA_'+a['arm'])
        for path_key,sha_key in [('stdout_path','stdout_sha256'),('time_path','time_sha256')]:
            q=Path(a[path_key]);ck(q.is_file() and sha(q)==a[sha_key],'BUILD_LOG_SHA_'+a['arm'])
        ck(parse_build(Path(a['stdout_path']).read_text(errors='replace'),a['fraction'])==a['coverage'],
           'COVERAGE_CHANGED_'+a['arm'])
    for r in x['runs']:
        q=Path(r['log_path'])
        ck(q.is_file() and q.parent.resolve()==(out/'logs').resolve() and sha(q)==r['log_sha256'],'SEARCH_LOG_SHA_'+q.name)
        ck(parse_eval(q.read_text(errors='replace'),r['beams'])==r['rows'],'SEARCH_LOG_PARSE_'+q.name)
        expected=PARENT_SHA[r['arm']] if r['arm'] in CONTROL else next(z['graph_sha256'] for z in x['builds'] if z['arm']==r['arm'])
        ck(expected==r['graph_sha256'],'SEARCH_GRAPH_SHA_'+r['arm'])
    print('R90_P23_AUDIT_PASS_BUILDS_AND_REPEATED_SEARCH_SHA',flush=True)

def selftest():
    s='R90_A5_MODE=gate\nR90_A5_PASS1 selected=500 n=100000 sort_comparisons=1200000 GT_free=1\n' \
      'R90_A5_LEAF_SCREEN total=12 eligible=7 WL_total=1000 WL_eligible=650 gate=1\n'
    k=parse_build(s,'0.005')
    ck(k['selected_points']==500 and k['eligible_leaves']==7 and k['skipped_wl_pct']==35,'TEST_BUILD_PARSE')
    t='R72_RECALL_INPUT_PASS graph_nodes=100000 queries=10000 gt_k=100\n' + \
       ''.join(f'R72_RECALL_ROW beam={b} recall=0.9985 qps=1000 avg_cmps=200 avg_visited=100\n' for b in (64,128)) + \
       'R72_RECALL_EVAL_PASS\n'
    ck(len(parse_eval(t,[64,128]))==2,'TEST_EVAL_PARSE')
    ck(len({q for _,q in NEW_Q})==len(NEW_Q),'DUPLICATE_FRACTION')
    print('R90_P23_LOCAL_SELFTEST_PASS_QGRID_BUILD_EVAL_AND_SHA_CONTRACT',flush=True)

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('mode',choices=('selftest','preflight','pilot','audit'))
    ap.add_argument('--cpu',type=int,default=0)
    ap.add_argument('--reps',type=int,default=3)
    ap.add_argument('--out',type=Path,default=OUT)
    args=ap.parse_args()
    ck(args.reps in (3,5),'REPS_MUST_BE_3_OR_5')
    out=args.out.expanduser().resolve(strict=False)
    if args.mode=='selftest':selftest()
    elif args.mode=='preflight':preflight(out,args.cpu,True)
    elif args.mode=='pilot':pilot(out,args.cpu,args.reps)
    else:audit(out)

if __name__=='__main__':
    try:main()
    except Exception as e:
        print('R90_P23_HOLD',type(e).__name__,str(e),file=sys.stderr,flush=True)
        sys.exit(2)
