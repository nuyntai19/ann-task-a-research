#!/usr/bin/env python3
"""R85-A4b: targeted dense-beam SEARCH-only matched-Recall latency/QPS audit.

- No BUILD, no graph modification, no source compilation, no network.
- Reuses and SHA-verifies all 18 original A4 graphs, evaluator, inputs, runners.
- 18 dense-beam QUALITY scans on four pinned physical P-cores.
- 90 interleaved 1-P-core QPS passes; selects bracketing beams and neighbors
  for each target (instead of wastefully rerunning all dense beams five times).
- Reports latency interpolated at a common Recall target per graph, then
  arm median over 3 independent graphs. Temporal repeats are nested within
  graphs and NEVER treated as 15 independent graphs.
- Resumable; writes only under experiments/H85/r85_a4b_searchonly/.
"""
from __future__ import annotations
import argparse
import datetime as dt
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
from statistics import median

HOME=Path.home()
ROOT=HOME/'ann-task-a'
DL=HOME/'Downloads'
A4_SCRIPT=DL/'run_r85_a4_paired_sift1m.py'
A4_SHA='b9db158b022d9df9633817031282d68e45f7c0ee9236d2b7059aa184d73e3106'
A4_RUN=ROOT/'experiments/H85/r85_a4_paired_sift1m/runs_20261111-162423'
OUT=ROOT/'experiments/H85/r85_a4b_searchonly'
TARGETS=(.80,.89,.96,.99,.998)
# 10..40 every integer, 42..80 every 2, 84..160 every 4, 168..256 every 8.
BEAMS=tuple(sorted(set(list(range(10,41))+list(range(42,81,2))+
                       list(range(84,161,4))+list(range(168,257,8)))))
REPEATS=5
QPS_CPU=0
QUALITY_CPUS=(0,2,4,6)


def fail(s):raise RuntimeError('R85_A4B_FAIL_CLOSED '+str(s))

def sha(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda:f.read(1<<20),b''):h.update(b)
    return h.hexdigest()

def atomic(p,obj):
    p=Path(p); tmp=p.with_name(p.name+'.tmp')
    tmp.write_text(json.dumps(obj,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf8')
    tmp.replace(p)

def a4_load():
    if not A4_SCRIPT.is_file() or sha(A4_SCRIPT)!=A4_SHA:fail('A4 runner absent/changed: '+str(A4_SCRIPT))
    spec=importlib.util.spec_from_file_location('r85_a4b_pinned_a4',A4_SCRIPT)
    a4=importlib.util.module_from_spec(spec);spec.loader.exec_module(a4)
    return a4

def validated():
    a4=a4_load()
    old,a1,a1c,_,_,_=a4.dep(require_eval=True)
    run,manifest=a4.open_run(A4_RUN,old,a1,a1c)
    builds=a4.require_complete_builds(run,manifest,old,a1)
    a4.quality_rows(run,builds,manifest,a1c)
    if len(builds)!=18:fail('A4 requires 18 verified graphs')
    if not shutil.which('taskset') or QPS_CPU not in os.sched_getaffinity(0):fail('CPU0/taskset unavailable')
    if not set(QUALITY_CPUS).issubset(os.sched_getaffinity(0)):fail('4 physical P cores unavailable')
    return a4,old,a1c,manifest,builds

def graph_plan(a4,builds):
    if [(r['rep'],r['arm']) for r in builds]!=a4.schedule():fail('A4 BUILD order drift')
    return builds

def manifest_payload(a4,old,a1c,oldmanifest,builds):
    return {
       'kind':'R85-A4b dense QUALITY + targeted matched-Recall latency QPS',
       'parent_run':str(A4_RUN), 'a4_manifest_sha256':sha(A4_RUN/'manifest.json'),
       'a4_summary_sha256':sha(A4_RUN/'summary.json'),
       'a4_runner_sha256':A4_SHA,
       'a4b_runner_sha256':sha(Path(__file__)),
       'input_graphs':{r['tag']:r['graph_sha256'] for r in builds},
       'binary_sha256':oldmanifest['binary_sha256'],
       'evaluator_sha256':oldmanifest['evaluator_sha256'],
       'data_sha256':oldmanifest['data_sha256'],
       'beams':list(BEAMS),'targets':list(TARGETS),'temporal_repeats_per_graph':REPEATS,
       'quality_cpus':list(QUALITY_CPUS),'qps_cpu':QPS_CPU,
       'schedule':a4.schedule(),
       'qps_schedule':[[rep,arm] for _,group in a4.qps_schedule() for rep,arm in group],
       'created_at_local':dt.datetime.now().isoformat(timespec='seconds')
    }

def run_check(path,m,builds):
    run=Path(path).resolve()
    if run.parent!=OUT.resolve() or not run.name.startswith('runs_'):fail('Invalid output path '+str(run))
    if not (run/'manifest.json').exists():fail('Missing A4b manifest')
    got=json.loads((run/'manifest.json').read_text())
    for k in ('parent_run','a4_manifest_sha256','a4_summary_sha256',
              'a4_runner_sha256','a4b_runner_sha256','input_graphs','binary_sha256','evaluator_sha256','data_sha256',
              'beams','targets','temporal_repeats_per_graph','quality_cpus','qps_cpu','schedule','qps_schedule'):
        if got.get(k)!=m[k]:fail('Manifest provenance mismatch '+k)
    return run

def prepare(a4,old,a1c,oldmanifest,builds):
    OUT.mkdir(parents=True,exist_ok=True)
    run=OUT/('runs_'+dt.datetime.now().strftime('%Y%m%d-%H%M%S'))
    run.mkdir(exist_ok=False)
    atomic(run/'manifest.json',manifest_payload(a4,old,a1c,oldmanifest,builds))
    print(str(run),flush=True)

def native(a4,cmd,log,env):return a4.native(cmd,log,env)

def quality_records(run,builds,m):
    rows={}
    for r in builds:
        path=run/'quality'/(r['tag']+'.json')
        if not path.exists():fail('Missing dense QUALITY '+r['tag'])
        rec=json.loads(path.read_text())
        if rec.get('graph_sha256')!=r['graph_sha256'] or rec.get('evaluator_sha256')!=m['evaluator_sha256'] or rec.get('beams')!=list(BEAMS):
            fail('Quality provenance mismatch '+r['tag'])
        if [z['beam'] for z in rec['rows']]!=list(BEAMS):fail('Unexpected beams '+r['tag'])
        rows[r['tag']]=rec['rows']
    return rows

def do_quality(a4,old,a1c,manifest,builds,run):
    run=run_check(run,manifest,builds)
    qdir=run/'quality';qdir.mkdir(exist_ok=True)
    for i,r in enumerate(builds,1):
        file=qdir/(r['tag']+'.json')
        if file.exists():
            data=json.loads(file.read_text())
            if data.get('graph_sha256')!=r['graph_sha256'] or data.get('evaluator_sha256')!=manifest['evaluator_sha256'] or [z['beam'] for z in data.get('rows',[])]!=list(BEAMS):
                fail('Existing QUALITY invalid '+r['tag'])
            print('R85_A4B_QUALITY_SKIP_VERIFIED '+r['tag'],flush=True)
            continue
        cmd=['taskset','-c',','.join(map(str,QUALITY_CPUS)),str(a1c.EVAL),
             r['graph'],str(old.DATA_FILES['base'][0]),str(old.DATA_FILES['query'][0]),
             str(old.DATA_FILES['gt'][0]),','.join(map(str,BEAMS))]
        env=dict(os.environ,PARLAY_NUM_THREADS='4',OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1')
        print(f'R85_A4B_QUALITY_START {i}/18 {r["tag"]} beams={len(BEAMS)}',flush=True)
        out=native(a4,cmd,qdir/(r['tag']+'.log'),env)
        if f'R85_A1C_DYNAMIC_BEAMS count={len(BEAMS)}' not in out or 'R72_RECALL_EVAL_PASS' not in out:fail('Missing evaluator quality marker '+r['tag'])
        data={'rep':r['rep'],'arm':r['arm'],'tag':r['tag'],'graph_sha256':r['graph_sha256'],
              'evaluator_sha256':manifest['evaluator_sha256'],'beams':list(BEAMS),
              'rows':a4.parsed(out,BEAMS)}
        atomic(file,data)
        print('R85_A4B_QUALITY_PASS '+r['tag'],flush=True)
    quality_records(run,builds,manifest)
    print('R85_A4B_ALL_18_DENSE_QUALITY_PASS',flush=True)


def bracket(rows,t):
    # Compute the monotone increasing Recall envelope by beam.
    seq=sorted(rows,key=lambda x:x['beam'])
    envelope=[]; best=-1.
    for x in seq:
        if x['recall']>best+1e-10:
            envelope.append(x);best=x['recall']
    if not envelope or t < envelope[0]['recall']-1e-10 or t>envelope[-1]['recall']+1e-10:return None
    for j,x in enumerate(envelope):
        if abs(x['recall']-t)<=1e-10:return (x['beam'],x['beam'])
        if x['recall']>=t:
            if j==0:return None
            return (envelope[j-1]['beam'],x['beam'])
    return None

def beam_selection(rows):
    lookup={x['beam']:x for x in rows};seq=list(BEAMS); chosen=set();pairs={}
    for target in TARGETS:
        br=bracket(rows,target);pairs[str(target)]=list(br) if br else None
        if br:
            for beam in br:
                j=seq.index(beam)
                for d in (-1,0,1):
                    if 0<=j+d<len(seq):chosen.add(seq[j+d])
    # Local neighborhood for curve validation; no more than about 20 beams.
    return sorted(chosen),pairs

def qps_plan(a4):
    return [(r,rep,arm) for r,group in a4.qps_schedule() for rep,arm in group]

def qps_rows(run):
    f=run/'qps/qps_results.json'
    return json.loads(f.read_text()) if f.exists() else []

def do_qps(a4,old,a1c,manifest,builds,run):
    run=run_check(run,manifest,builds)
    qualities=quality_records(run,builds,manifest)
    bmap={(r['rep'],r['arm']):r for r in builds}
    plan=qps_plan(a4)
    qdir=run/'qps';qdir.mkdir(exist_ok=True)
    saved=qps_rows(run)
    if len(saved)>len(plan):fail('Too many QPS records')
    for i,z in enumerate(saved):
        repeat,rep,arm=plan[i]
        row=bmap[rep,arm]
        selected,pairs=beam_selection(qualities[row['tag']])
        expected=beam_order(selected,repeat,i)
        if (z.get('repeat'),z.get('rep'),z.get('arm'))!=(repeat,rep,arm) or \
           z.get('graph_sha256')!=row['graph_sha256'] or \
           z.get('evaluator_sha256')!=manifest['evaluator_sha256'] or \
           z.get('qps_cpu')!=QPS_CPU or z.get('selected_beams')!=selected or \
           z.get('target_brackets')!=pairs or [x['beam'] for x in z['rows']]!=expected:
            fail('QPS saved provenance/order invalid at '+str(i+1))
    for i,(repeat,rep,arm) in enumerate(plan[len(saved):],len(saved)+1):
        r=bmap[rep,arm]; quality=qualities[r['tag']]
        selected,pairs=beam_selection(quality)
        if not selected:fail('No matched target bracket for '+r['tag'])
        order=beam_order(selected,repeat,i-1)
        cmd=['taskset','-c',str(QPS_CPU),str(a1c.EVAL),
             r['graph'],str(old.DATA_FILES['base'][0]),str(old.DATA_FILES['query'][0]),
             str(old.DATA_FILES['gt'][0]),','.join(map(str,order))]
        env=dict(os.environ,PARLAY_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',VECLIB_MAXIMUM_THREADS='1')
        tag=f'pass{repeat}_r{rep}_{arm}'
        print(f'R85_A4B_QPS_START {i}/{len(plan)} {tag} beams={len(order)}',flush=True)
        out=native(a4,cmd,qdir/(tag+'.log'),env)
        if f'R85_A1C_DYNAMIC_BEAMS count={len(order)}' not in out or 'R72_RECALL_EVAL_PASS' not in out:fail('Evaluator QPS marker missing '+tag)
        actual=a4.parsed(out,order)
        ref={x['beam']:x for x in quality}
        for x in actual:
            o=ref[x['beam']]
            if abs(x['recall']-o['recall'])>0.00011 or abs(x['avg_cmps']-o['avg_cmps'])>2:
                fail('Recall/comparisons drift '+tag+' beam='+str(x['beam']))
        z={'repeat':repeat,'rep':rep,'arm':arm,'tag':r['tag'],
           'graph_sha256':r['graph_sha256'],'evaluator_sha256':manifest['evaluator_sha256'],
           'qps_cpu':QPS_CPU,'selected_beams':selected,'target_brackets':pairs,'rows':actual}
        saved.append(z);atomic(qdir/'qps_results.json',saved)
        print('R85_A4B_QPS_PASS '+tag,flush=True)
    print(f'R85_A4B_ALL_{len(plan)}_QPS_PASSES_PASS',flush=True)

def beam_order(selected,repeat,plan_index):
    if not selected:return []
    # Cyclic permutation combats systematic cold-cache bias tied to beam size.
    rot=(plan_index+repeat)%len(selected)
    seq=list(selected[rot:]+selected[:rot])
    if repeat%2==0:seq.reverse()
    return seq

def interp(qlo,qhi,rlo,rhi,target):
    if rlo==rhi:return qlo
    return qlo+(target-rlo)/(rhi-rlo)*(qhi-qlo)

def summarize(a4,manifest,builds,run):
    run=run_check(run,manifest,builds)
    qual=quality_records(run,builds,manifest)
    rec=qps_rows(run)
    if len(rec)!=90:fail('Expected 90 complete QPS graph-passes, got '+str(len(rec)))
    keyed={}
    for z in rec:
        keyed.setdefault(z['tag'],[]).append(z)
    if len(keyed)!=18 or any(len(x)!=REPEATS for x in keyed.values()):fail('Missing temporal repeats by graph')
    out={'protocol':'interpolate latency (microseconds per query) against measured Recall per graph and temporal pass, aggregate five passes within graph, then 3 graph medians per arm; no extrapolation',
         'targets':{},'input_A4_builds':18,'qps_graph_passes':len(rec),
         'beams_quality':len(BEAMS),'beam_selection':'bracketing beams and nearest neighbors per target'}
    for t in TARGETS:
        arms={}
        for arm in a4.ARM_ORDER:
            per=[]
            for rep in range(1,4):
                tag=f't4_r{rep}_{arm}';rows=qual[tag];pair=bracket(rows,t)
                if not pair:
                    per.append({'rep':rep,'coverage':False});continue
                quality={x['beam']:x for x in rows}
                b0,b1=pair;r0=quality[b0]['recall'];r1=quality[b1]['recall']
                rep_lat=[]
                for z in keyed[tag]:
                    bybeam={x['beam']:x for x in z['rows']}
                    if b0 not in bybeam or b1 not in bybeam:fail('Missing bracket QPS '+tag+' '+str(pair))
                    lo,hi=bybeam[b0],bybeam[b1]
                    l0=1e6/lo['qps'];l1=1e6/hi['qps']
                    rep_lat.append(interp(l0,l1,r0,r1,t))
                ml=median(rep_lat)
                per.append({'rep':rep,'coverage':True,'beam_bracket':[b0,b1],
                            'recall_bracket':[r0,r1],'bracket_recall_width':r1-r0,
                            'interpolated_latency_us':ml,'interpolated_qps':1e6/ml,
                            'temporal_latency_us':rep_lat,
                            'temporal_min_us':min(rep_lat),'temporal_max_us':max(rep_lat),
                            'interpolated_cmps':a4.interpolation(rows,t)})
            valid=[x for x in per if x['coverage']]
            medlat=median(x['interpolated_latency_us'] for x in valid) if valid else None
            medcmps=median(x['interpolated_cmps'] for x in valid) if valid else None
            arms[arm]={'coverage':f'{len(valid)}/3','matched_recall_qps':1e6/medlat if medlat else None,
                       'matched_recall_latency_us':medlat,'matched_recall_cmps':medcmps,
                       'max_bracket_recall_width':max(x['bracket_recall_width'] for x in valid) if valid else None,
                       'per_graph':per}
        out['targets'][str(t)]=arms
    atomic(run/'matched_recall_latency_summary.json',out)
    print('R85_A4B_SUMMARY '+str(run/'matched_recall_latency_summary.json'),flush=True)
    print(f"{'TARGET':>8} {'ARM':23} {'COVER':>6} {'QPS':>11} {'LATENCY_US':>12} {'CMPS':>10} {'MAX_BRACKET':>12}")
    for t in TARGETS:
        for arm,row in out['targets'][str(t)].items():
            fmt=lambda v,n:f'{v:{n}.3f}' if v is not None else 'NA'
            print(f"{t:8.3f} {arm:23} {row['coverage']:>6} {fmt(row['matched_recall_qps'],11):>11} {fmt(row['matched_recall_latency_us'],12):>12} {fmt(row['matched_recall_cmps'],10):>10} {fmt(row['max_bracket_recall_width'],12):>12}")
    print('R85_A4B_SEARCH_ONLY_COMPLETE',flush=True)

def selftest():
    assert len(BEAMS)==len(set(BEAMS)) and min(BEAMS)==10 and max(BEAMS)==256
    assert len(TARGETS)==5 and len(set(TARGETS))==5
    rr=[{'beam':10,'recall':.80},{'beam':20,'recall':.89},{'beam':30,'recall':.96}]
    assert bracket(rr,.80)==(10,10)
    assert bracket(rr,.85)==(10,20)
    assert bracket(rr,.97) is None
    selected,pairs=beam_selection([{'beam':b,'recall':.7+(b-10)*.002} for b in BEAMS])
    assert selected and len(selected)==len(set(selected))
    assert beam_order(selected,2,3)==beam_order(selected,2,3)
    assert abs(interp(100,200,.8,.9,.85)-150)<1e-8
    assert abs((1e6/(1e6/1000))-1000)<1e-8
    print('R85_A4B_SELFTEST_PASS')

def main():
    p=argparse.ArgumentParser(description=__doc__,formatter_class=argparse.RawDescriptionHelpFormatter)
    g=p.add_mutually_exclusive_group(required=True)
    g.add_argument('--selftest',action='store_true');g.add_argument('--dry-run',action='store_true')
    g.add_argument('--prepare',action='store_true');g.add_argument('--quality',type=Path,metavar='A4B_RUN')
    g.add_argument('--qps',type=Path,metavar='A4B_RUN');g.add_argument('--summary',type=Path,metavar='A4B_RUN')
    args=p.parse_args()
    if args.selftest:return selftest()
    a4,old,a1c,oldmanifest,builds=validated()
    graph_plan(a4,builds)
    m=manifest_payload(a4,old,a1c,oldmanifest,builds)
    if args.dry_run:
        print('R85_A4B_DRY_RUN_GRAPH_COUNT',len(builds))
        print('R85_A4B_DRY_RUN_QUALITY_BEAMS',len(BEAMS),list(BEAMS))
        print('R85_A4B_DRY_RUN_QPS_GRAPH_PASSES',len(qps_plan(a4)))
        print('R85_A4B_DRY_RUN_PASS_NO_BUILD_NO_SEARCH_NO_WRITES')
        return
    if args.prepare:return prepare(a4,old,a1c,oldmanifest,builds)
    if args.quality:return do_quality(a4,old,a1c,m,builds,args.quality)
    if args.qps:return do_qps(a4,old,a1c,m,builds,args.qps)
    if args.summary:return summarize(a4,m,builds,args.summary)

if __name__=='__main__':
    try:main()
    except (OSError,RuntimeError,ValueError,KeyError,AssertionError,TypeError,IndexError,ZeroDivisionError) as e:
        print('R85_A4B_FAIL_CLOSED '+repr(e),file=sys.stderr)
        sys.exit(1)
