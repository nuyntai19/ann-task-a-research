#!/usr/bin/env python3
"""R86 logging kit: create A-E, measure build wall/RSS, ingest counters/search, validate, export CSV.

No external Python dependencies. Does NOT modify PiPNN source, and does NOT invent measurements.
"""
from __future__ import annotations
import argparse
import csv
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import statistics
import subprocess
import sys
import tempfile
from typing import Any

from registry import SCHEMA_VERSION, RECALL_TARGETS, METRICS, DIAGNOSTIC_METRICS, SHEET_HEADERS, ARM_SPEC

FILES = {'A': 'A_system.json', 'B': 'B_search.json', 'C': 'C_work.json', 'D': 'D_diagnostics.json', 'E': 'E_manifest.json'}
_STATUS = ('NOT_MEASURED','PARTIAL','MEASURED','INVALID')


def iso_now():
    return dt.datetime.now().astimezone().isoformat(timespec='seconds')


def asjson(v):
    return json.dumps(v, ensure_ascii=False, indent=2, allow_nan=False) + '\n'


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def save(path, obj):
    dest=Path(path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile('w', dir=dest.parent, delete=False, encoding='utf-8') as out:
        out.write(asjson(obj)); tmp=out.name
    os.replace(tmp, dest)


def sha256_file(path):
    path=Path(path)
    h=hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda:f.read(8*1024*1024), b''):
            h.update(b)
    return h.hexdigest()


def die(msg):
    raise SystemExit('ERROR: '+str(msg))


def getfile(run, group):
    p=Path(run)/FILES[group]
    if not p.is_file():die(f'{p} is missing; init a run first.')
    return load(p)


def putfile(run, group, obj):
    save(Path(run)/FILES[group], obj)


def audit(run, action, details):
    f=Path(run)/'raw'/'audit.jsonl'
    f.parent.mkdir(parents=True, exist_ok=True)
    with f.open('a', encoding='utf-8') as w:
        w.write(json.dumps({'timestamp':iso_now(),'action':action,**details},ensure_ascii=False,allow_nan=False)+'\n')


def empty_run(args):
    arm=ARM_SPEC.get(args.arm_id)
    n=args.n
    run=Path(args.output)/args.run_id
    if run.exists() and any(run.iterdir()):die(f'{run} already exists. Never overwrite a previous run.')
    run.mkdir(parents=True,exist_ok=True)
    for d in ('raw','logs','sheet_csv'):(run/d).mkdir(exist_ok=True)
    graph_id=args.graph_id or f'{args.run_id}_{args.arm_id}_r{args.rep}'
    cap=args.C if args.C is not None else (arm or {}).get('C')
    leaf_K=args.K if args.K is not None else (arm or {}).get('K')
    passes=args.N if args.N is not None else (arm or {}).get('N')
    common=dict(schema_version=SCHEMA_VERSION,run_id=args.run_id,graph_id=graph_id,arm_id=args.arm_id,status='NOT_MEASURED')
    A={**common, 'n':n,'build_rep':args.rep,'storage_variant':args.storage_variant,
       'C':cap,'slot_bytes':args.slot_bytes,'T_build_s':None,'T_partition_s':None,
       'T_leaf_s':None,'T_prune_s':None,'T_phase_method':None,
       'M_reservoir_model_B':None,'M_alloc_B':None,'peak_rss_KiB':None,
       'index_bytes':None,'index_sha256':None,'cpu_user_s':None,'cpu_system_s':None,
       'notes':'No build yet; phase values must come from audited instrumentation.'}
    B={**common,'k':args.k,'results_by_recall_target':[
         dict(recall_target=t,actual_recall=None,recall_method=None,beam=None,
              latency_us=None,latency_p95_us=None,latency_p99_us=None,ndc_per_query=None,
              qps=None,qps_method=None,status='NOT_MEASURED') for t in RECALL_TARGETS],
       'directed_arcs':None,'degree_mean':None,'degree_max':None,
       'graph_sha256':None,'query_count':None,'evaluator_sha256':None,
       'notes':'Search metrics require a real evaluator and correct GT, not partition COMPARISONS.'}
    C={**common,'n':n,'instrumented':False,'counter_definitions':{k:{'unit':v[0],'meaning':v[1]} for k,v in METRICS.items()},
       'counters':[],'leaf_histogram':None,'leaf_size_records':None,
       'counter_imports':[],'notes':'Counters remain empty until the ON executable exports events.'}
    D={**common,'hypothesis_id':None,'metrics':[],'diagnostic_catalog':DIAGNOSTIC_METRICS,
       'notes':'Diagnostics are opt-in. Empty metrics means NOT_MEASURED.'}
    E={**common,'source_commit':None,'source_diff_sha':None,'source_paths_sha256':{},'source_git_status_porcelain':None,
       'binary_sha256':None,'binary_path':str(Path(args.binary).resolve()) if args.binary else None,
       'build_flags':[],'dataset_id':args.dataset_id,'base_sha256':None,
       'queries_sha256':None,'gt_sha256':None,'base_path':args.base,'queries_path':args.queries,
       'gt_path':args.gt,'n':n,'d':args.dim,'k':args.k,'C':cap,'K':leaf_K,'N':passes,'R':args.R,'h':args.h,
       'threads':args.threads,'affinity':args.affinity,'seed':args.seed,
       'random_source':args.random_source,'rep':args.rep,'timed_or_instrumented':args.mode,
       'graph_sha256':None,'graph_path':None,'search_evaluator_sha256':None,
       'timestamp_local':iso_now(),'hostname':None,'cpu_model':None,'compiler':None,
       'cwd':str(Path.cwd()),'actual_command':None,'exit_code':None,
       'notes':'Do not infer source snapshot from git HEAD if checkout is dirty.'}
    if args.storage_variant=='flat' and args.slot_bytes:
        A['M_reservoir_model_B']=n*(cap+1)*args.slot_bytes
    if args.binary and Path(args.binary).is_file():E['binary_sha256']=sha256_file(args.binary)
    if args.source:
        src=Path(args.source)
        if src.is_dir():
            p=subprocess.run(['git','-C',str(src),'rev-parse','HEAD'],text=True,capture_output=True)
            if p.returncode==0:E['source_commit']=p.stdout.strip()
            status=subprocess.run(['git','-C',str(src),'status','--porcelain'],text=True,capture_output=True)
            if status.returncode==0:E['source_git_status_porcelain']=status.stdout
            d=subprocess.run(['git','-C',str(src),'diff','--binary','HEAD'],capture_output=True)
            if d.returncode==0:E['source_diff_sha']=hashlib.sha256(d.stdout).hexdigest()
            for q in ('algorithms/PipNN/pipnn.h','algorithms/PipNN/pipnn_utils.h','algorithms/PipNN/neighbors.h','algorithms/utils/graph.h','algorithms/utils/r70_two_tier_lshgraph.h','algorithms/PipNN/CMakeLists.txt','CMakeLists.txt'):
                if (src/q).is_file():E['source_paths_sha256'][q]=sha256_file(src/q)
    if args.hash_inputs:
        for key,path in [('base_sha256',args.base),('queries_sha256',args.queries),('gt_sha256',args.gt)]:
            if path and Path(path).is_file():E[key]=sha256_file(path)
    if args.arm_id in ARM_SPEC and args.mode=='timed':
        E['build_flags']=[f'R71_USE_H17={"ON" if arm["H17"] else "OFF"}',f'R70_USE_TIER={"ON" if arm["TwoTier"] else "OFF"}']
        E['notes']+=' build_flags here are EXPECTED from arm, not verification of CMakeCache; verify before final claims.'
    for g, obj in [('A',A),('B',B),('C',C),('D',D),('E',E)]:putfile(run,g,obj)
    audit(run,'init',{'arm_id':args.arm_id,'n':n,'mode':args.mode,'inputs_hash':bool(args.hash_inputs)})
    emit_logs(run)
    print(f'CREATED {run} with A/B/C/D/E JSON; NO measurement has been fabricated.')


def take_build(args):
    run=Path(args.run)
    A=getfile(run,'A'); E=getfile(run,'E')
    if E.get('timed_or_instrumented')=='instrumented' and not args.allow_instrumented:
        die('This is an instrumented run; refusing to mark its time as clean BUILD. Use --allow-instrumented to capture ONLY as audit time.')
    cmd=args.command
    if cmd and cmd[0]=='--':cmd=cmd[1:]
    if not cmd:die('Missing command. Use: capture-build --run RUN_DIR -- /path/to/binary args...')
    if A['T_build_s'] is not None:die('Build already measured; create a new run/rep instead of overwriting.')
    time_binary=Path('/usr/bin/time')
    if not time_binary.is_file():die('/usr/bin/time is required on Ubuntu (package time).')
    if args.output_graph:
        E['graph_path']=str(Path(args.output_graph).resolve())
    E['actual_command']=cmd
    E['timestamp_local']=iso_now()
    putfile(run,'E',E)
    (run/'raw').mkdir(exist_ok=True)
    stats=(run/'raw'/'gnu_time.txt').resolve()
    with (run/'raw'/'stdout.log').open('w',encoding='utf-8') as fo, (run/'raw'/'stderr.log').open('w',encoding='utf-8') as fe:
        p=subprocess.run([str(time_binary),'-f','r86_elapsed_s=%e\nr86_rss_kib=%M\nr86_cpu_user_s=%U\nr86_cpu_system_s=%S','-o',str(stats),'--',*cmd],stdout=fo,stderr=fe,cwd=args.cwd or None,env=os.environ.copy())
    metrics={}
    if stats.exists():
        for line in stats.read_text(errors='replace').splitlines():
            if '=' in line:
                k,v=line.split('=',1)
                if k.startswith('r86_'):
                    try:metrics[k]=float(v)
                    except ValueError:pass
    E['exit_code']=p.returncode
    if p.returncode==0:
        A['T_build_s']=metrics.get('r86_elapsed_s')
        A['peak_rss_KiB']=int(metrics['r86_rss_kib']) if 'r86_rss_kib' in metrics else None
        A['cpu_user_s']=metrics.get('r86_cpu_user_s')
        A['cpu_system_s']=metrics.get('r86_cpu_system_s')
        if args.output_graph and Path(args.output_graph).is_file():
            A['index_bytes']=Path(args.output_graph).stat().st_size
            if args.hash_graph:
                gsha=sha256_file(args.output_graph)
                A['index_sha256']=gsha; E['graph_sha256']=gsha
        A['status']='PARTIAL' if any(x is None for x in [A['T_partition_s'],A['T_leaf_s'],A['T_prune_s']]) else 'MEASURED'
        E['status']='MEASURED'
    else:
        A['status']='INVALID'; E['status']='INVALID'
    putfile(run,'A',A);putfile(run,'E',E)
    audit(run,'capture-build',{'command':cmd,'exit_code':p.returncode,'time_s':A['T_build_s']})
    emit_logs(run)
    print('BUILD EXIT',p.returncode,'wall_s',A['T_build_s'],'rss_KiB',A['peak_rss_KiB'])
    print('Logs in', run/'raw')
    if p.returncode:raise SystemExit(p.returncode)


def set_field(args):
    group=args.group.upper();run=Path(args.run)
    obj=getfile(run,group)
    if args.field not in obj:die('Unknown field '+args.field+' for '+group)
    if args.field in ('run_id','graph_id','arm_id','schema_version'):
        die('Identity fields are immutable; create another run.')
    value=args.value
    try:value=json.loads(value)
    except json.JSONDecodeError:pass
    prev=obj.get(args.field)
    obj[args.field]=value
    if group=='A' and args.field in ('C','slot_bytes','n','storage_variant'):
        if obj.get('storage_variant')=='flat' and all(isinstance(obj.get(z),int) for z in ('n','C','slot_bytes')):
            obj['M_reservoir_model_B']=obj['n']*(obj['C']+1)*obj['slot_bytes']
        else:
            obj['M_reservoir_model_B']=None
    if group!='E' and obj.get('status')=='NOT_MEASURED':obj['status']='PARTIAL'
    putfile(run,group,obj)
    audit(run,'set-field',{'group':group,'field':args.field,'old':prev,'new':value,'source':args.source})
    print('SET',group,args.field,'=',value)


def _counter_row(metric,pass_id,depth,obs,n,pred=None,phase_time_s=None,method='instrumented_jsonl',notes=None):
    return dict(metric_code=metric,pass_id=pass_id,depth=depth,observed=obs,unit=METRICS[metric][0],
                predicted=pred,obs_to_pred=(obs/pred if pred not in (None,0) else None),
                per_n=(obs/n if n else None),phase_time_s=phase_time_s,
                ns_per_work=(phase_time_s*1e9/obs if phase_time_s is not None and obs else None),
                source_method=method,status='MEASURED',notes=notes)


def import_counters(args):
    run=Path(args.run);C=getfile(run,'C');E=getfile(run,'E')
    source=Path(args.events)
    fingerprint=sha256_file(source)
    if fingerprint in C['counter_imports']:
        die('That exact event stream was already imported; refusing double count.')
    collected={}
    with source.open(encoding='utf-8') as f:
        for line_no,line in enumerate(f,1):
            if not line.strip():continue
            try:ev=json.loads(line)
            except json.JSONDecodeError as ex:die(f'Invalid JSONL line {line_no}: {ex}')
            mc=ev.get('metric_code'); val=ev.get('observed')
            if mc not in METRICS:die(f'Unknown metric_code {mc} in line {line_no}')
            if not isinstance(val,int) or isinstance(val,bool) or val<0:die(f'Counter observed must be unsigned integer on line {line_no}')
            ps=ev.get('pass_id')
            depth=ev.get('depth')
            if not isinstance(ps,int) or ps<0:die('pass_id must be 0 (global prune) or positive integer')
            if depth is not None and (not isinstance(depth,int) or depth<0):die('depth must be null or non-negative integer')
            if E.get('N') is not None and ps>E['N'] and ps!=0:
                die(f'pass_id={ps} exceeds configured N={E["N"]}')
            key=(ps,depth,mc)
            collected[key]=collected.get(key,0)+val
    if not collected:die('No valid counter rows in stream.')
    # An instrumented session can produce multiple streams; never overwrite same metric tuple invisibly.
    old={(r['pass_id'],r.get('depth'),r['metric_code']) for r in C['counters']}
    if any(k in old for k in collected):die('Overlapping metric/pass/depth already present. Use a new run or merge your raw streams before import.')
    for (ps,depth,mc),val in sorted(collected.items(),key=lambda kv:(kv[0][0], -1 if kv[0][1] is None else kv[0][1],kv[0][2])):
        C['counters'].append(_counter_row(mc,ps,depth,val,C['n']))
    C['counter_imports'].append(fingerprint)
    C['status']='PARTIAL'
    C['instrumented']=True
    putfile(run,'C',C)
    rawdest=run/'raw'/f'counter_events_{len(C["counter_imports"]):02d}.jsonl'
    shutil.copyfile(source,rawdest) if source.resolve()!=rawdest.resolve() else None
    audit(run,'import-counters',{'sha256':fingerprint,'rows':len(collected),'source':str(source)})
    emit_logs(run)
    print('IMPORTED',len(collected),'distinct metric/pass/depth rows. Every recorded value is from supplied event stream.')



def import_leaf_sizes(args):
    """Audit leaf histogram, W_L and W_pairs independently from per-leaf size events."""
    run=Path(args.run);C=getfile(run,'C');E=getfile(run,'E')
    if C.get('leaf_histogram') is not None:
        die('Leaf histogram already imported; create new run for another measurement.')
    hist={};checks={};count=0
    with Path(args.events).open(encoding='utf-8') as f:
        for line_no,line in enumerate(f,1):
            if not line.strip():continue
            try:r=json.loads(line)
            except json.JSONDecodeError as e:die(f'Leaf JSONL parse error line {line_no}: {e}')
            ps, dep, size = r.get('pass_id'),r.get('depth'),r.get('size')
            if not isinstance(ps,int) or ps<1 or (E.get('N') is not None and ps>E['N']):die('Invalid leaf pass_id')
            # A final leaf after MergeBuckets/SplitDuplicates has no reliable
            # recursion depth in the PiPNN bucket list: null is the truthful scope.
            if dep is not None and (not isinstance(dep,int) or dep<0):
                die('Invalid leaf depth; use null if not tracked by PiPNN')
            if not isinstance(size,int) or size<0:die('Invalid leaf size')
            key=(ps,dep)
            bins=hist.setdefault(key,{})
            bins[size]=bins.get(size,0)+1
            q=checks.setdefault(key,{'leaf_count':0,'leaf_size_sum':0,'W_L':0,'W_pairs':0})
            q['leaf_count']+=1;q['leaf_size_sum']+=size;q['W_L']+=size*size;q['W_pairs']+=size*(size-1)//2
            count+=1
    if not count:die('Empty leaf records')
    C['leaf_histogram']=[{'pass_id':ps,'depth':dep,'bins':{str(k):v for k,v in sorted(bins.items())}}
                         for (ps,dep),bins in sorted(hist.items())]
    C['leaf_size_records']=count
    existing={(r['pass_id'],r.get('depth'),r['metric_code']):r for r in C['counters']}
    faults=[];missing=[]
    for (ps,dep),rows in checks.items():
        for metric,val in rows.items():
            k=(ps,dep,metric)
            if k not in existing:
                missing.append(f'COUNTER_MISSING {k}')
            elif existing[k]['observed']!=val:
                faults.append(f'COUNTER_MISMATCH {k} C++={existing[k]["observed"]} independent_leaf_dump={val}')
    C['leaf_size_check']={'source_sha256':sha256_file(args.events),'scoped_totals':[
        {'pass_id':ps,'depth':dep,**d} for (ps,dep),d in sorted(checks.items())],
        'mismatches':faults,'missing':missing}
    C['status']='INVALID' if faults or missing else 'PARTIAL'
    putfile(run,'C',C)
    target=run/'raw'/'leaf_sizes.jsonl'
    if Path(args.events).resolve()!=target.resolve():shutil.copyfile(args.events,target)
    audit(run,'import-leaf-sizes',{'records':count,'mismatch_count':len(faults),'missing_count':len(missing),'source':str(args.events)})
    emit_logs(run)
    print('LEAF_SIZES records',count,'histogram cells',len(hist),'counter mismatches',len(faults),'missing',len(missing))
    for f in faults+missing:print('ERROR',f)
    if faults or missing:raise SystemExit(2)


def import_phases(args):
    """Add strictly labeled phase-wall timing from an audited profiler, never from worker-sum silently."""
    run=Path(args.run);A=getfile(run,'A');obj=load(args.events)
    if obj.get('method') not in ('exclusive_wall','inclusive_wall','worker_seconds','external_profile'):
        die('phase timings must declare method exclusive_wall/inclusive_wall/worker_seconds/external_profile')
    if obj['method']=='worker_seconds' and not args.allow_worker_seconds:
        die('Worker-seconds are NOT wall-time: pass --allow-worker-seconds to store them with explicit method and no phase wall claim')
    for name in ('T_partition_s','T_leaf_s','T_prune_s'):
        val=obj.get(name)
        if val is not None and (not isinstance(val,(float,int)) or val<0):die('Invalid '+name)
        if A[name] is not None and val is not None:die(name+' already populated')
        if name in obj:A[name]=val
    A['T_phase_method']=obj['method']
    A['status']='PARTIAL' if A['T_build_s'] is None else 'MEASURED'
    A['notes']+=' Phase times imported with method '+obj['method']+'; review nested/overlap semantics.'
    putfile(run,'A',A)
    audit(run,'import-phases',{'source':str(args.events),'sha256':sha256_file(args.events),'method':obj['method']})
    emit_logs(run)
    print('IMPORTED PHASES',obj['method'])


def _quartiles(vals):
    if len(vals)<4:return None
    a=statistics.quantiles(vals,n=4,method='inclusive')
    return a[2]-a[0]


def summarize(args):
    """Across real independent graph runs: median/min/max/IQR by arm/n/dataset/mode."""
    root=Path(args.root)
    samples={};excluded=[]
    for manifest in sorted(root.glob('*/E_manifest.json')):
        run=manifest.parent
        try:
            E=getfile(run,'E');A=getfile(run,'A');B=getfile(run,'B')
        except Exception as ex:
            excluded.append((str(run),str(ex)));continue
        key=(E.get('arm_id'),E.get('n'),E.get('dataset_id'),E.get('timed_or_instrumented'))
        samples.setdefault(key,[]).append((E,A,B))
    if not samples:die('No completed or initialized runs found')
    summary=[]
    for (arm,n,dataset,mode),row in sorted(samples.items(),key=lambda x:tuple(str(z) for z in x[0])):
        # n_graph counts unique graph_id, not number of per-query rows
        graph_ids=set(E['graph_id'] for E,_,_ in row)
        timed=[A['T_build_s'] for E,A,_ in row if mode=='timed' and isinstance(A.get('T_build_s'),(int,float))]
        rss=[A['peak_rss_KiB'] for E,A,_ in row if mode=='timed' and isinstance(A.get('peak_rss_KiB'),(int,float))]
        res={'arm_id':arm,'n':n,'dataset':dataset,'mode':mode,'run_count':len(row),'independent_graph_ids':len(graph_ids),
             'T_build_n':len(timed),'T_build_median_s':statistics.median(timed) if timed else None,
             'T_build_min_s':min(timed) if timed else None,'T_build_max_s':max(timed) if timed else None,
             'T_build_IQR_s':_quartiles(timed),
             'rss_n':len(rss),'rss_median_KiB':statistics.median(rss) if rss else None,
             'rss_min_KiB':min(rss) if rss else None,'rss_max_KiB':max(rss) if rss else None,
             'rss_IQR_KiB':_quartiles(rss),
             'graph_sha_distinct':len({E.get('graph_sha256') for E,_,_ in row if E.get('graph_sha256')}),
             'search_at_recall':{}}
        for t in RECALL_TARGETS:
            measures={k:[] for k in ('latency_us','ndc_per_query','qps')}
            for E,A,B in row:
                q=next((q for q in B.get('results_by_recall_target',[]) if q.get('recall_target')==t),None)
                if q:
                    for k in measures:
                        if isinstance(q.get(k),(float,int)):measures[k].append(q[k])
            res['search_at_recall'][str(t)]={k:{'n':len(v),'median':statistics.median(v) if v else None,
                                               'min':min(v) if v else None,'max':max(v) if v else None,
                                               'IQR':_quartiles(v)} for k,v in measures.items()}
        summary.append(res)
    dest=Path(args.output or root/'R86_summary.json')
    save(dest,{'schema_version':SCHEMA_VERSION,'generated_at':iso_now(),'summary':summary,
               'warnings':['No standard error is estimated from a single instrumented run; at least 3 independent builds for final claim.',
                          'Keep matching dataset, evaluator, CPU/threads and source protocol before cross-arm comparison.'],
               'excluded':excluded})
    print('SUMMARY',dest,'groups',len(summary))

def import_search(args):
    run=Path(args.run);B=getfile(run,'B')
    obj=load(args.results)
    rows=obj.get('rows') if isinstance(obj,dict) else obj
    if not isinstance(rows,list):die('Search input must be JSON list or {"rows": [...]}')
    seen=set()
    for r in rows:
        target=r.get('recall_target')
        try:target=float(target)
        except(TypeError,ValueError):die('recall_target must be numeric')
        if target not in RECALL_TARGETS or target in seen:die('recall_target must be one unique value from 0.89,0.96,0.99,0.998')
        seen.add(target)
        method=r.get('recall_method')
        if method not in ('direct','interpolated'):
            die('recall_method must be direct or interpolated; no extrapolation.')
        idx=RECALL_TARGETS.index(target)
        dest=B['results_by_recall_target'][idx]
        keys=('actual_recall','recall_method','beam','latency_us','latency_p95_us','latency_p99_us','ndc_per_query','qps','qps_method')
        for key in keys:
            if key in r:dest[key]=r[key]
        dest['status']='PARTIAL' if dest['latency_us'] is None or dest['ndc_per_query'] is None else 'MEASURED'
    B['status']='PARTIAL'
    for k in ('directed_arcs','degree_mean','degree_max','graph_sha256','query_count','evaluator_sha256'):
        if isinstance(obj,dict) and k in obj:B[k]=obj[k]
    putfile(run,'B',B)
    audit(run,'import-search',{'source':str(args.results),'sha256':sha256_file(args.results),'targets':sorted(seen)})
    emit_logs(run)
    print('IMPORTED SEARCH',len(seen),'targets. Direct/interpolated method retained.')



def import_predictions(args):
    """Join a model's predictions to actual C counter scopes (never silently infer a prediction)."""
    run=Path(args.run);C=getfile(run,'C')
    obj=load(args.results)
    rows=obj.get('predictions') if isinstance(obj,dict) else obj
    if not isinstance(rows,list):die('predictions input must be a list or {"predictions": [...]}')
    bykey={(x['pass_id'],x.get('depth'),x['metric_code']):x for x in C['counters']}
    matched=0
    for r in rows:
        key=(r.get('pass_id'),r.get('depth'),r.get('metric_code'))
        if key not in bykey:die(f'Missing measured counter scope for prediction {key}; do not create phantom work')
        value=r.get('predicted')
        if value is not None and (not isinstance(value,(int,float)) or value<0):die('Predicted must be nonnegative numeric or null')
        if bykey[key].get('predicted') is not None:die(f'Prediction already defined for {key}')
        bykey[key]['predicted']=value
        bykey[key]['prediction_model']=r.get('model')
        t=r.get('phase_time_s')
        if t is not None and (not isinstance(t,(int,float)) or t<0):die('phase_time_s invalid')
        if t is not None:
            bykey[key]['phase_time_s']=t
            bykey[key]['phase_time_method']=r.get('phase_time_method')
        matched+=1
    putfile(run,'C',C)
    audit(run,'import-predictions',{'count':matched,'source':str(args.results),'sha256':sha256_file(args.results)})
    emit_logs(run)
    print('JOINED predicted values',matched,'Only if source calculations were explicitly supplied.')


def import_diagnostics(args):
    run=Path(args.run);D=getfile(run,'D')
    if D['metrics']:die('Diagnostics already supplied; start a separate hypothesis/run or replace offline with audit.')
    obj=load(args.results)
    if not isinstance(obj,dict) or not isinstance(obj.get('metrics'),list) or not obj.get('hypothesis_id'):
        die('Diagnostics require {"hypothesis_id":"H...","metrics":[...]}')
    for r in obj['metrics']:
        if r.get('metric_code') not in DIAGNOSTIC_METRICS:
            die('Unregistered diagnostic metric '+str(r.get('metric_code')))
        if not r.get('method') or r.get('value') is None:
            die('Each diagnostic requires observed value and a measurement method')
        if r.get('unit')!=DIAGNOSTIC_METRICS[r['metric_code']]:
            die('Diagnostic unit mismatch for '+r['metric_code'])
        r['hypothesis_id']=obj['hypothesis_id'];r['status']='MEASURED'
    D['hypothesis_id']=obj['hypothesis_id'];D['metrics']=obj['metrics'];D['status']='MEASURED'
    putfile(run,'D',D)
    audit(run,'import-diagnostics',{'source':str(args.results),'sha256':sha256_file(args.results),'hypothesis_id':obj['hypothesis_id']})
    emit_logs(run)
    print('IMPORTED diagnostic metrics',len(obj['metrics']))


def import_graph_stats(args):
    run=Path(args.run);B=getfile(run,'B');E=getfile(run,'E')
    obj=load(args.results)
    for k in ('directed_arcs','degree_mean','degree_max','graph_sha256'):
        if obj.get(k) is not None and B.get(k) is not None:
            die('Already has value for '+k+'; avoid silent overwrite')
        if k in obj:B[k]=obj[k]
    if E.get('graph_sha256') and B.get('graph_sha256') and E['graph_sha256']!=B['graph_sha256']:
        die('Graph SHA mismatch! Cannot attach topology of unrelated graph')
    B['status']='PARTIAL'
    putfile(run,'B',B)
    audit(run,'import-graph-stats',{'source':str(args.results),'sha256':sha256_file(args.results)})
    emit_logs(run)
    print('IMPORTED graph stats with graph consistency check')

def show(args):
    obj=getfile(args.run,args.group.upper())
    if args.metric:
        if args.group.upper()=='C':
            obj['counters']=[r for r in obj['counters'] if r['metric_code']==args.metric]
        elif args.group.upper()=='D':
            obj['metrics']=[r for r in obj['metrics'] if r['metric_code']==args.metric]
        else:die('--metric is supported only for C/D')
    print(asjson(obj))


def _render(obj,group):
    lines=[f'R86 {group} | run_id={obj["run_id"]} | graph_id={obj["graph_id"]} | status={obj["status"]}',
           f'SCHEMA v{obj["schema_version"]} | Null means NOT_MEASURED','-'*85]
    if group=='C':
        index={(x['pass_id'],x.get('depth'),x['metric_code']):x for x in obj['counters']}
        for k,(unit,meaning) in METRICS.items():
            matches=[(t,r) for t,r in index.items() if t[2]==k]
            if not matches:lines.append(f'{k:28} NOT_MEASURED   [{unit}] — {meaning}')
            else:
                for (ps,dep,_),r in sorted(matches,key=lambda x:(x[0][0],-1 if x[0][1] is None else x[0][1])):
                    lines.append(f'{k:28} pass={ps} depth={dep} observed={r["observed"]} {unit} | per_n={r["per_n"]} | pred={r["predicted"]} | obs/pred={r["obs_to_pred"]} | ns/work={r["ns_per_work"]}')
        lines.append(f'leaf_histogram={obj.get("leaf_histogram") if obj.get("leaf_histogram") is not None else "NOT_MEASURED"}')
    elif group=='B':
        for key,val in obj.items():
            if key=='results_by_recall_target':
                for x in val:lines.append('recall_target='+str(x['recall_target'])+' '+json.dumps(x,ensure_ascii=False))
            elif key not in ('schema_version', 'run_id','graph_id','status'):lines.append(f'{key}: {json.dumps(val,ensure_ascii=False)}')
    elif group=='D':
        lines.append('Diagnostic catalogue (all unmeasured unless explicitly listed):')
        for mc, unit in DIAGNOSTIC_METRICS.items():
            rec=[r for r in obj['metrics'] if r.get('metric_code')==mc]
            lines.append(f'  {mc:30} '+(json.dumps(rec,ensure_ascii=False) if rec else f'NOT_MEASURED [{unit}]'))
    else:
        for k,v in obj.items():
            if k not in ('schema_version','run_id','graph_id','status'):
                lines.append(f'{k}: {"NOT_MEASURED" if v is None else json.dumps(v,ensure_ascii=False)}')
    return '\n'.join(lines)+'\n'


def emit_logs(run):
    run=Path(run);(run/'logs').mkdir(exist_ok=True)
    for g in FILES:
        obj=getfile(run,g)
        (run/'logs'/(FILES[g].replace('.json','.log'))).write_text(_render(obj,g),encoding='utf-8')


def derive_c_rows(C):
    for r in C['counters']:
        x=dict(r)
        obs=x.get('observed');pred=x.get('predicted');n=C.get('n')
        x['per_n']=obs/n if obs is not None and n else None
        x['obs_to_pred']=obs/pred if obs is not None and pred not in (None,0) else None
        x['ns_per_work']=x['phase_time_s']*1e9/obs if x.get('phase_time_s') is not None and obs else None
        yield x


def sheet_rows(run):
    obj={g:getfile(run,g) for g in FILES}
    A,B,C,D,E=(obj[g] for g in FILES)
    common={'run_id':E['run_id'],'graph_id':E['graph_id'],'arm_id':E['arm_id']}
    r={'RUN_INDEX':[{'run_id':E['run_id'],'campaign':'R86','arm_id':E['arm_id'],'n':E['n'],'dataset':E['dataset_id'],'graph_id':E['graph_id'],'run_type':E['timed_or_instrumented'],'status':E['status'],'source_commit':E['source_commit'],'binary_sha256':E['binary_sha256'],'folder_or_uri':str(Path(run).resolve()),'date_local':E['timestamp_local'],'notes':E['notes']}],
      'A_SYSTEM':[{**common,'n':A['n'],'C':A['C'],'slot_bytes':A['slot_bytes'],'storage_variant':A['storage_variant'],'build_rep':A['build_rep'],'T_build_s':A['T_build_s'],'T_partition_s':A['T_partition_s'],'T_leaf_s':A['T_leaf_s'],'T_prune_s':A['T_prune_s'],'M_reservoir_model_B':A['M_reservoir_model_B'],'M_alloc_B':A['M_alloc_B'],'peak_rss_KiB':A['peak_rss_KiB'],'index_bytes':A['index_bytes'],'measurement_status':A['status'],'notes':A['notes']}],
      'B_SEARCH':[], 'C_WORK':[], 'D_DIAGNOSTICS':[],
      'E_PROTOCOL':[{**common, 'source_commit':E['source_commit'],'source_diff_sha':E['source_diff_sha'],'binary_sha256':E['binary_sha256'],'build_flags':','.join(E['build_flags']),'dataset_id':E['dataset_id'],'base_sha256':E['base_sha256'],'queries_sha256':E['queries_sha256'],'gt_sha256':E['gt_sha256'],'n':E['n'],'d':E['d'],'k':E['k'],'C':E['C'],'K':E['K'],'N':E['N'],'R':E['R'],'h':E['h'],'threads':E['threads'],'affinity':E['affinity'],'seed':E['seed'],'random_source':E['random_source'],'rep':E['rep'],'timed_or_instrumented':E['timed_or_instrumented'],'status':E['status'],'notes':E['notes']}]
    }
    for q in B['results_by_recall_target']:
        r['B_SEARCH'].append({**common,'recall_target':q['recall_target'],'recall_at10':q['actual_recall'],
                              'recall_method':q['recall_method'],'k':B['k'],'beam':q['beam'],'latency_us':q['latency_us'],
                              'latency_p95_us':q['latency_p95_us'],'latency_p99_us':q['latency_p99_us'],
                              'ndc_per_query':q['ndc_per_query'],'qps':q['qps'],'qps_method':q['qps_method'],
                              'directed_arcs':B['directed_arcs'],'degree_mean':B['degree_mean'],
                              'degree_max':B['degree_max'],'status':q['status'],'notes':B['notes']})
    for x in derive_c_rows(C):
        r['C_WORK'].append({**common,'n':C['n'],**{k:x.get(k) for k in SHEET_HEADERS['C_WORK'] if k not in common},'status':x['status']})
    for x in D['metrics']:
        r['D_DIAGNOSTICS'].append({**common,'hypothesis_id':x.get('hypothesis_id'),'metric_code':x.get('metric_code'),
                                   'value':x.get('value'),'unit':x.get('unit'),'method':x.get('method'),
                                   'status':x.get('status'),'notes':x.get('notes')})
    return r


def export_csv(args):
    run=Path(args.run);out=Path(args.output) if args.output else run/'sheet_csv'
    out.mkdir(parents=True,exist_ok=True)
    data=sheet_rows(run)
    for name,headers in SHEET_HEADERS.items():
        with (out/(name+'.csv')).open('w',encoding='utf-8-sig',newline='') as f:
            w=csv.DictWriter(f,fieldnames=headers,extrasaction='ignore')
            w.writeheader()
            for row in data[name]:w.writerow({k:('' if row.get(k) is None else row.get(k)) for k in headers})
    print('EXPORTED exact Google Sheet header order:',out)


def validate(args):
    run=Path(args.run);errors=[];warnings=[]
    a={g:getfile(run,g) for g in FILES}
    ids={(o['run_id'],o['graph_id'],o['arm_id']) for o in a.values()}
    if len(ids)!=1:errors.append('A–E identity mismatch')
    E=a['E']; A=a['A'];C=a['C'];B=a['B']
    if E['N'] is None:errors.append('N missing in E')
    if A['storage_variant']=='flat' and A['slot_bytes'] is not None and E['C'] is not None:
        expect=E['n']*(E['C']+1)*A['slot_bytes']
        if A['M_reservoir_model_B']!=expect:errors.append('Incorrect flat storage model')
    if E['source_commit'] is None:warnings.append('source_commit not verified')
    if E['binary_sha256'] is None:warnings.append('binary SHA256 missing')
    if E['source_paths_sha256']=={}:warnings.append('patched source path hashes missing')
    if E['random_source'] is None:warnings.append('randomness source not recorded')
    if E['base_sha256'] is None:warnings.append('base SHA256 absent; supply --hash-inputs or verified manifest')
    if E['seed'] is None:warnings.append('seed not pinned (may be intentional with random_device)')
    if E['actual_command'] is None:warnings.append('no actual run command recorded')
    if E['timed_or_instrumented']=='instrumented' and A['T_build_s'] is not None:warnings.append('time from instrumented build; do NOT compare as clean timed wall')
    if C['counter_imports'] and E['timed_or_instrumented']=='timed':warnings.append('counter stream ingested into timed run: check for mixed protocol')
    seen=set()
    for x in C['counters']:
        k=(x['pass_id'],x.get('depth'),x['metric_code'])
        if k in seen:errors.append('duplicate counter scope: '+str(k))
        seen.add(k)
        if x['metric_code']=='W_L' and x['observed']<0:errors.append('negative leaf work')
    if B['status']!='NOT_MEASURED' and E['gt_sha256'] is None:warnings.append('Search results with no GT checksum')
    if B['graph_sha256'] and E['graph_sha256'] and B['graph_sha256']!=E['graph_sha256']:
        errors.append('Graph SHA mismatch between B and E')
    if C.get('leaf_size_check',{}).get('mismatches'):errors.append('Independent leaf-size dump did not agree with C counters')
    if C.get('leaf_size_check',{}).get('missing'):errors.append('Independent leaf-size check lacks required scoped counters')
    if a['D']['metrics'] and a['D']['hypothesis_id'] is None:warnings.append('D metrics without hypothesis ID')
    print('VALIDATE', 'FAIL' if errors else 'PASS_WITH_WARNINGS' if warnings else 'PASS')
    for m in errors:print(' ERROR',m)
    for m in warnings:print(' WARNING',m)
    if errors:raise SystemExit(2)


def _parser():
    p=argparse.ArgumentParser(description='ANN Task A R86 modular logger v1.2')
    sub=p.add_subparsers(dest='cmd',required=True)
    x=sub.add_parser('init',help='Create A–E templates and logs for one run')
    x.add_argument('--output',default='./runs');x.add_argument('--run-id',required=True)
    x.add_argument('--graph-id');x.add_argument('--arm-id',required=True)
    x.add_argument('--n',type=int,required=True);x.add_argument('--dim',type=int)
    x.add_argument('--C',type=int);x.add_argument('--K',type=int);x.add_argument('--N',type=int)
    x.add_argument('--R',type=int,default=64);x.add_argument('--h',type=int)
    x.add_argument('--k',type=int,default=10);x.add_argument('--threads',type=int)
    x.add_argument('--affinity');x.add_argument('--seed');x.add_argument('--random-source')
    x.add_argument('--rep',type=int,default=1);x.add_argument('--dataset-id');x.add_argument('--base');x.add_argument('--queries');x.add_argument('--gt')
    x.add_argument('--source');x.add_argument('--binary');x.add_argument('--storage-variant',choices=['flat','two_tier','other'],default='flat')
    x.add_argument('--slot-bytes',type=int,help='Actual sizeof(LSHCandidate) from THIS binary, not assumed; e.g. 8')
    x.add_argument('--mode',choices=['timed','instrumented'],default='instrumented');x.add_argument('--hash-inputs',action='store_true')
    x.set_defaults(func=empty_run)
    x=sub.add_parser('capture-build',help='Run real BUILD, save A/E timing and raw command logs')
    x.add_argument('--run',required=True);x.add_argument('--cwd');x.add_argument('--output-graph')
    x.add_argument('--hash-graph',action='store_true');x.add_argument('--allow-instrumented',action='store_true')
    x.add_argument('command',nargs=argparse.REMAINDER)
    x.set_defaults(func=take_build)
    x=sub.add_parser('import-counters',help='Ingest actual C++ JSONL counter events')
    x.add_argument('--run',required=True);x.add_argument('--events',required=True);x.set_defaults(func=import_counters)
    x=sub.add_parser('import-leaf-sizes',help='Independent per-leaf size JSONL for histogram/counter gate')
    x.add_argument('--run',required=True);x.add_argument('--events',required=True);x.set_defaults(func=import_leaf_sizes)
    x=sub.add_parser('import-phases',help='Import labeled phase timing JSON from an actual source')
    x.add_argument('--run',required=True);x.add_argument('--events',required=True);x.add_argument('--allow-worker-seconds',action='store_true');x.set_defaults(func=import_phases)
    x=sub.add_parser('import-search',help='Ingest external search evaluator JSON in specified schema')
    x.add_argument('--run',required=True);x.add_argument('--results',required=True);x.set_defaults(func=import_search)
    x=sub.add_parser('import-predictions',help='Join model predictions to scoped C counters, no new observations')
    x.add_argument('--run',required=True);x.add_argument('--results',required=True);x.set_defaults(func=import_predictions)
    x=sub.add_parser('import-diagnostics',help='Import hypothesis-tagged D metrics from explicit recorded input')
    x.add_argument('--run',required=True);x.add_argument('--results',required=True);x.set_defaults(func=import_diagnostics)
    x=sub.add_parser('import-graph-stats',help='Import independent edge/degree/graph SHA summary into B')
    x.add_argument('--run',required=True);x.add_argument('--results',required=True);x.set_defaults(func=import_graph_stats)
    x=sub.add_parser('set',help='Set an audited explicit field (e.g. verified graph_sha256); never invent values')
    x.add_argument('--run',required=True);x.add_argument('--group',choices=list(FILES));x.add_argument('--field',required=True)
    x.add_argument('--value',required=True);x.add_argument('--source',required=True);x.set_defaults(func=set_field)
    x=sub.add_parser('show',help='Print one group only, optionally filter by metric')
    x.add_argument('--run',required=True);x.add_argument('--group',choices=list(FILES));x.add_argument('--metric');x.set_defaults(func=show)
    x=sub.add_parser('render-logs',help='Generate A–E printable .log text files')
    x.add_argument('--run',required=True);x.set_defaults(func=lambda args:(emit_logs(args.run),print('RENDERED',Path(args.run)/'logs')))
    x=sub.add_parser('export-csv',help='Export exact headers and rows for native Google Sheet upload')
    x.add_argument('--run',required=True);x.add_argument('--output');x.set_defaults(func=export_csv)
    x=sub.add_parser('summarize',help='Across independent runs, produce median/min/max/IQR and graph-hash variance')
    x.add_argument('--root',required=True);x.add_argument('--output');x.set_defaults(func=summarize)
    x=sub.add_parser('validate',help='Check consistency, provenance and unmeasured data')
    x.add_argument('--run',required=True);x.set_defaults(func=validate)
    return p


def main():
    args=_parser().parse_args();args.func(args)

if __name__=='__main__': main()
