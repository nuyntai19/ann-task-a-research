#!/usr/bin/env python3
"""R85-SCALE1 matched-Recall CPU0 native QPS, 18 pinned BIGANN1M graphs.

--selftest: no project I/O.  --preflight RUN: read-only source/manifest/graph/
quality audit and target coverage.  --run RUN: new exclusive QPS session; five
interleaved temporal passes over 18 graph builds (3 independent graphs/arm).
--resume SESSION: continue exclusively missing graph-pass jobs (verify completed
ones).  --summarize SESSION: reconstruct summary from completed jobs, no SEARCH.

No source changes, BUILD, benchmark data changes or graph regeneration. Native
C++ A1c evaluator and native checkRecall. Match within measured Recall brackets.
Graph-level (n=3) and temporal (n=5) replication remain distinct.
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
PARENT=DL/'run_r85_scale1_bigann1m_v1.py'
PIN_PARENT='55a193b9d033491c646965d3ffd3d8e1a00eeef7c3b303b79a3b8f49f983e988'
TARGETS=(0.89,0.96,0.99,0.998)
REPEATS=5
CPU=0
RECALL_TOL=0.00011
CMPS_TOL=2.0
PROTO='R85_SCALE1_BIGANN1M_MATCHED_RECALL_CPU0_V1'
SESSION_ROOT_NAME='matched_qps_cpu0_v1'


def fail(msg):
    raise RuntimeError('R85_SCALE1_QPS_FAIL_CLOSED '+str(msg))


def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(4<<20),b''):
            h.update(block)
    return h.hexdigest()


def regular(path):
    p=Path(path)
    if not p.is_file() or p.is_symlink():fail('REGULAR_FILE_REQUIRED '+str(p))
    return p


def json_read(path):
    return json.loads(regular(path).read_text(encoding='utf8'))


def json_exclusive(path, obj):
    path=Path(path)
    if path.exists() or path.is_symlink():fail('NO_OVERWRITE '+str(path))
    with path.open('x',encoding='utf8') as f:
        json.dump(obj,f,indent=2,sort_keys=True,ensure_ascii=False,allow_nan=False)
        f.write('\n')
        f.flush()
        os.fsync(f.fileno())


def load_parent():
    if sha(regular(PARENT))!=PIN_PARENT:fail('SCALE1_PARENT_SHA_DRIFT')
    sys.dont_write_bytecode=True
    spec=importlib.util.spec_from_file_location('r85_scale1_matched_parent',PARENT)
    if spec is None or spec.loader is None:fail('PARENT_IMPORT_SPEC')
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def normalize_rows(rows, expected_beams, name):
    if not isinstance(rows,list) or len(rows)!=len(expected_beams):
        fail('BAD_QUALITY_ROW_COUNT '+name)
    if [z.get('beam') for z in rows]!=list(expected_beams):
        fail('BAD_QUALITY_BEAMS '+name)
    for x in rows:
        if not (isinstance(x.get('beam'),int) and x['beam']>0):
            fail('INVALID_BEAM '+name)
        for field in ('recall','qps','avg_cmps','avg_visited'):
            val=x.get(field)
            if isinstance(val,bool) or not isinstance(val,(int,float)) or not math.isfinite(val):
                fail('BAD_NUMERIC '+name+' '+field)
        if not (0<=x['recall']<=1 and x['qps']>0 and x['avg_cmps']>=0 and x['avg_visited']>=0):
            fail('BAD_QUALITY_VALUES '+name)
    return rows


def bracket(rows, target):
    # True measured neighboring points; no extrapolation or below-min assumption.
    if target<rows[0]['recall'] or target>max(r['recall'] for r in rows):
        return None
    for k,row in enumerate(rows):
        if row['recall']>=target:
            if k==0:return None  # cannot interpolate below first tested beam
            low=rows[k-1]
            if not (low['recall']<=target<=row['recall'] and row['recall']>low['recall']):
                fail('NONMONOTONIC_LOCAL_RECALL_BRACKET '+str(target))
            return [low['beam'],row['beam']]
    return None


def interpolate(rows_by_beam, pair, target):
    a=rows_by_beam[pair[0]];b=rows_by_beam[pair[1]]
    if not (a['recall']<=target<=b['recall'] and b['recall']>a['recall']):
        fail('TARGET_NOT_BRACKETED_AT_REPEAT '+str((target,pair)))
    w=(target-a['recall'])/(b['recall']-a['recall'])
    lat=(1-w)*1_000_000/a['qps']+w*1_000_000/b['qps']
    cmps=(1-w)*a['avg_cmps']+w*b['avg_cmps']
    return {'latency_us':lat,'avg_cmps':cmps,'bracket_beams':pair,'interpolation_weight':w}


def schedule(rows):
    tags=[x['tag'] for x in rows]
    if len(tags)!=18 or len(set(tags))!=18:fail('SCHEDULE_REQUIRES_18_UNIQUE_GRAPHS')
    # Graphs rotate between passes; reverse alternating passes to limit order bias.
    ans=[]
    for rep in range(1,REPEATS+1):
        offset=(rep-1)*7%len(tags)
        current=tags[offset:]+tags[:offset]
        if rep%2==0:current=list(reversed(current))
        for tag in current:ans.append((rep,tag))
    if len(ans)!=REPEATS*18:fail('QPS_SCHEDULE_LENGTH')
    return ans


def audit(build_run, verbose=True):
    sc=load_parent()
    a4,old,a1,a1c,ident=sc.preflight()
    run=Path(build_run).resolve(strict=True)
    records=sc.verify_session(run,ident,a4,old,a1)
    expected=a4.schedule()
    if len(records)!=18 or [(r['rep'],r['arm']) for r in records]!=expected:
        fail('SESSION_NOT_COMPLETE_18_GRAPHS')
    if CPU not in os.sched_getaffinity(0) or not shutil.which('taskset'):
        fail('CPU0_UNAVAILABLE')
    if ident.get('evaluator_sha256')!=sha(regular(a1c.EVAL)):
        fail('EVAL_SHA_DRIFT')
    beams=list(a1c.BEAMS)
    entries={}
    missing={str(t):[] for t in TARGETS}
    for r in records:
        tag=r['tag'];p=run/'quality'/(tag+'.json')
        q=json_read(p)
        if q.get('tag')!=tag or q.get('graph_sha256')!=r['graph_sha256'] or \
           q.get('evaluator_sha256')!=ident['evaluator_sha256'] or \
           q.get('data_sha256')!=ident['input_sha256']:
            fail('QUALITY_PROVENANCE_MISMATCH '+tag)
        quality=normalize_rows(q.get('rows'),beams,tag)
        pairs={}
        for t in TARGETS:
            pp=bracket(quality,t)
            if pp is not None:pairs[str(t)]=pp
            else:missing[str(t)].append(tag)
        entries[tag]={'tag':tag,'rep':r['rep'],'arm':r['arm'],
            'graph_path':str(run/(tag+'.graph')),'graph_sha256':r['graph_sha256'],
            'quality_sha256':sha(p),'pairs':pairs,
            'quality_rows':quality}
    used=[t for t in TARGETS if not missing[str(t)]]
    if not used:fail('NO_FULL_18_GRAPH_TARGET_COVERAGE')
    for tag,entry in entries.items():
        entry['selected_beams']=sorted({bb for t in used for bb in entry['pairs'][str(t)]})
        if not entry['selected_beams']:
            fail('EMPTY_QPS_BEAMS '+tag)
    if verbose:
        for t in TARGETS:
            if missing[str(t)]:
                print('R85_SCALE1_QPS_TARGET_EXCLUDED_NO_18_GRAPH_COVERAGE '+json.dumps({'target':t,'missing':missing[str(t)]},sort_keys=True),flush=True)
            else:
                print(f'R85_SCALE1_QPS_TARGET_INCLUDED target={t} graphs=18',flush=True)
        for tag in entries:
            e=entries[tag]
            print('R85_SCALE1_QPS_PLAN '+json.dumps({'tag':tag,'beams':e['selected_beams'],
                'target_brackets':{str(t):e['pairs'][str(t)] for t in used}},sort_keys=True),flush=True)
        print(f'R85_SCALE1_QPS_PREFLIGHT_PASS_READ_ONLY graphs=18 repeats={REPEATS} calls={18*REPEATS} targets={used}',flush=True)
    return sc,a4,a1c,ident,run,records,entries,used


def plan_manifest(sc,a4,a1c,ident,run,records,entries,used):
    return {
        'protocol':PROTO,'original_scale1_runner_sha256':PIN_PARENT,
        'build_run':str(run),'build_session_manifest_sha256':sha(run/'manifest.json'),
        'build_results_sha256':sha(run/'build_results.json'),
        'evaluator_sha256':ident['evaluator_sha256'],
        'input_sha256':ident['input_sha256'],
        'native_cores':{'qps_cpu':CPU,'parlay_num_threads':1,'openblas_num_threads':1,'omp_num_threads':1},
        'target_recall_requested':list(TARGETS),'targets_covered_all_18':list(used),
        'quality_beams':list(a1c.BEAMS),'repeats':REPEATS,
        'graph_count':18,'graph_reps_per_arm':3,'qps_schedule':[list(x) for x in schedule(records)],
        'graphs':{k:{'graph_sha256':v['graph_sha256'],
                     'quality_sha256':v['quality_sha256'],
                     'rep':v['rep'],'arm':v['arm'],
                     'beams':v['selected_beams'],
                     'pairs':{str(t):v['pairs'][str(t)] for t in used}}
                   for k,v in entries.items()},
        'measurement_note':'latency interpolation between direct-quality Recall brackets; CPU0, single worker; 5 temporal repeats per independent graph and 3 graph builds per arm; no extrapolation'
    }


def session_context(qps_session):
    qdir=Path(qps_session).resolve(strict=True)
    if not qdir.is_dir() or qdir.is_symlink():fail('QPS_SESSION_NOT_DIRECTORY')
    manifest=json_read(qdir/'manifest.json')
    if manifest.get('protocol')!=PROTO or not isinstance(manifest.get('build_run'),str):
        fail('QPS_SESSION_MANIFEST_PROTOCOL')
    state=audit(manifest['build_run'],verbose=False)
    sc,a4,a1c,ident,run,records,entries,used=state
    output_root=run/SESSION_ROOT_NAME
    if not qdir.is_relative_to(output_root.resolve(strict=True)):
        fail('QPS_SESSION_NOT_UNDER_BUILD_RUN')
    expected=plan_manifest(*state)
    if expected!=manifest:fail('QPS_SESSION_MANIFEST_DRIFT')
    return qdir,state,manifest


def read_job_log(qdir, rep, tag, beams, a4, quality_rows):
    path=regular(qdir/f'pass{rep:02d}_{tag}.log')
    blob=path.read_text(encoding='utf8',errors='replace')
    if 'R72_RECALL_EVAL_PASS' not in blob or f'R85_A1C_DYNAMIC_BEAMS count={len(beams)}' not in blob:
        fail('NATIVE_QPS_MARKERS_MISSING '+tag+' rep='+str(rep))
    parsed=a4.parsed(blob,beams)
    if len(parsed)!=len(beams) or [z['beam'] for z in parsed]!=list(beams):
        fail('NATIVE_QPS_ROWS_MISMATCH '+tag+' rep='+str(rep))
    qmap={z['beam']:z for z in quality_rows}
    for row in parsed:
        ref=qmap[row['beam']]
        if abs(row['recall']-ref['recall'])>RECALL_TOL or abs(row['avg_cmps']-ref['avg_cmps'])>CMPS_TOL:
            fail('RECALL_OR_CMPS_DRIFT '+json.dumps({'tag':tag,'rep':rep,'beam':row['beam'],'quality':ref,'measured':row}))
    return parsed,sha(path)


def job_payload(qdir, rep, tag, a4, entry, used):
    beams=entry['selected_beams'] if rep%2 else list(reversed(entry['selected_beams']))
    data,logsha=read_job_log(qdir,rep,tag,beams,a4,entry['quality_rows'])
    lookup={z['beam']:z for z in data}
    matched={str(t):interpolate(lookup,entry['pairs'][str(t)],t) for t in used}
    return {'rep':rep,'tag':tag,'arm':entry['arm'],'graph_sha256':entry['graph_sha256'],
        'log_sha256':logsha,'beam_order':list(beams),'rows':data,'matched':matched}


def execute(qdir,state,manifest,search):
    sc,a4,a1c,ident,run,records,entries,used=state
    for j,(rep,tag) in enumerate(schedule(records),1):
        entry=entries[tag]
        path=qdir/f'pass{rep:02d}_{tag}.log'
        result_path=qdir/f'pass{rep:02d}_{tag}.json'
        if result_path.exists():
            saved=json_read(result_path)
            expect=job_payload(qdir,rep,tag,a4,entry,used)
            if saved!=expect:fail('COMPLETED_QPS_JOB_DRIFT '+str(result_path))
            if search:print(f'R85_SCALE1_QPS_SKIP_VERIFIED {j}/{18*REPEATS} rep={rep} tag={tag}',flush=True)
            continue
        if path.exists():
            # If interrupted after native subprocess finished, recover from its
            # complete, validated log rather than repeating the native SEARCH.
            expect=job_payload(qdir,rep,tag,a4,entry,used)
            json_exclusive(result_path,expect)
            if search:print(f'R85_SCALE1_QPS_RECOVER_LOG {j}/{18*REPEATS} rep={rep} tag={tag}',flush=True)
            continue
        if not search:fail('MISSING_QPS_JOB '+str(result_path))
        beams=entry['selected_beams'] if rep%2 else list(reversed(entry['selected_beams']))
        cmd=['taskset','-c',str(CPU),str(a1c.EVAL),entry['graph_path'],
            str(sc.DATA['base']),str(sc.DATA['query']),str(sc.DATA['gt']),','.join(map(str,beams))]
        env=dict(os.environ,PARLAY_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',
                 MKL_NUM_THREADS='1',VECLIB_MAXIMUM_THREADS='1',NUMEXPR_NUM_THREADS='1')
        print(f'R85_SCALE1_QPS_START {j}/{18*REPEATS} rep={rep}/{REPEATS} tag={tag} beams={len(beams)}',flush=True)
        with path.open('x',encoding='utf8') as f:
            f.write('COMMAND '+shlex.join(cmd)+'\n');f.flush()
            process=subprocess.run(cmd,cwd=str(ROOT),env=env,stdout=f,stderr=subprocess.STDOUT,check=False)
        if process.returncode:
            fail('NATIVE_QPS_FAILED '+str({'tag':tag,'rep':rep,'rc':process.returncode,'log':str(path)}))
        payload=job_payload(qdir,rep,tag,a4,entry,used)
        json_exclusive(result_path,payload)
        print(f'R85_SCALE1_QPS_PASS rep={rep} tag={tag}',flush=True)
    return summarize(qdir,state,manifest)


def summarize(qdir,state,manifest):
    sc,a4,a1c,ident,run,records,entries,used=state
    job={}
    for rep,tag in schedule(records):
        path=qdir/f'pass{rep:02d}_{tag}.json'
        result=json_read(path)
        if result!=job_payload(qdir,rep,tag,a4,entries[tag],used):
            fail('SUMMARY_JOB_DRIFT '+str(path))
        job[(rep,tag)]=result
    out={'protocol':PROTO,'build_run':str(run),'qps_session':str(qdir),
         'independent_graphs_per_arm':3,'temporal_qps_repeats_per_graph':REPEATS,
         'target_results':{},'limits':'Three different BUILD graphs per arm, no independent dataset/seed replication across scale; the 5 CPU0 repeats are timing replicates, not n=15 independent graphs.'}
    by_arm={arm:{rep:f't4_r{rep}_{arm}' for rep in (1,2,3)} for arm in a4.ARM_ORDER}
    for target in used:
        t=str(target)
        graphs={}
        for tag,e in entries.items():
            lat=[job[(rep,tag)]['matched'][t]['latency_us'] for rep in range(1,REPEATS+1)]
            cmps=[job[(rep,tag)]['matched'][t]['avg_cmps'] for rep in range(1,REPEATS+1)]
            graphs[tag]={'arm':e['arm'],'graph_rep':e['rep'],'latency_us_temporal_samples':lat,
                'latency_us_median':median(lat),'latency_us_min':min(lat),'latency_us_max':max(lat),
                'avg_cmps_median':median(cmps),'bracket_beams':e['pairs'][t]}
        arms={}
        for arm in a4.ARM_ORDER:
            samples=[graphs[by_arm[arm][rep]]['latency_us_median'] for rep in (1,2,3)]
            cmps=[graphs[by_arm[arm][rep]]['avg_cmps_median'] for rep in (1,2,3)]
            arms[arm]={'latency_us_graph_medians':samples,
                'latency_us_median_of_three_graphs':median(samples),
                'latency_us_range_across_graphs':[min(samples),max(samples)],
                'avg_cmps_median_of_three_graphs':median(cmps)}
            if arm!='STOCK':
                change=[100*(samples[rep-1]/arms['STOCK']['latency_us_graph_medians'][rep-1]-1) for rep in (1,2,3)]
                arms[arm]['latency_change_percent_by_rep_vs_stock']=change
                arms[arm]['median_latency_change_percent_vs_stock']=median(change)
        out['target_results'][t]={'target_recall':target,'arms':arms,'graphs':graphs}
        print('R85_SCALE1_QPS_TARGET '+json.dumps({'target':target,'arms':{
            arm:{'median_us':v['latency_us_median_of_three_graphs'],
                 'change_percent_vs_stock':v.get('median_latency_change_percent_vs_stock')}
            for arm,v in arms.items()}},sort_keys=True),flush=True)
    summary_path=qdir/'matched_recall_qps_summary.json'
    if summary_path.exists():
        if json_read(summary_path)!=out:fail('EXISTING_SUMMARY_DRIFT')
        print('R85_SCALE1_QPS_SUMMARY_SKIP_VERIFIED',flush=True)
    else:json_exclusive(summary_path,out)
    print('R85_SCALE1_MATCHED_QPS_18_GRAPHS_PASS n_graph_per_arm=3 temporal_repeats=5 '+str(qdir),flush=True)
    return out


def do_run(build_run):
    state=audit(build_run)
    sc,a4,a1c,ident,run,records,entries,used=state
    out_root=run/SESSION_ROOT_NAME
    if out_root.is_symlink():fail('QPS_OUTPUT_ROOT_SYMLINK')
    out_root.mkdir(exist_ok=True)
    session=out_root/('qps_'+dt.datetime.now().strftime('%Y%m%d-%H%M%S')+'_'+str(os.getpid()))
    session.mkdir(exist_ok=False)
    manifest=plan_manifest(*state)
    json_exclusive(session/'manifest.json',manifest)
    print('R85_SCALE1_QPS_SESSION '+str(session),flush=True)
    return execute(session,state,manifest,search=True)


def do_existing(qps_session,search):
    qdir,state,manifest=session_context(qps_session)
    return execute(qdir,state,manifest,search=search)


def selftest():
    rows=[{'beam':10,'recall':.7},{'beam':20,'recall':.90},{'beam':30,'recall':.97},
          {'beam':40,'recall':.99}]
    assert bracket(rows,.89)==[10,20]
    assert bracket(rows,.96)==[20,30]
    assert bracket(rows,.7) is None
    assert bracket(rows,.999) is None
    trial={10:{'recall':.7,'qps':10000,'avg_cmps':200},20:{'recall':.90,'qps':5000,'avg_cmps':300}}
    z=interpolate(trial,[10,20],.8)
    assert abs(z['latency_us']-150)<1e-8 and abs(z['avg_cmps']-250)<1e-8
    try:
        interpolate(trial,[10,20],.95)
    except RuntimeError:pass
    else:raise AssertionError('unbracketed target must fail')
    sample=[{'tag':f't4_r{rep}_{arm}'} for rep in (1,2,3) for arm in ('STOCK','D0','K1024N2','K512N2','K1024N1','K512N1')]
    jobs=schedule(sample)
    assert len(jobs)==90 and len(set(jobs))==90
    for rep in range(1,6):
        assert {tag for j,tag in jobs if j==rep}=={x['tag'] for x in sample}
    print('R85_SCALE1_QPS_SELFTEST_PASS_NO_PROJECT_IO',flush=True)


def main():
    ap=argparse.ArgumentParser(description=__doc__,formatter_class=argparse.RawDescriptionHelpFormatter)
    grp=ap.add_mutually_exclusive_group(required=True)
    grp.add_argument('--selftest',action='store_true')
    grp.add_argument('--preflight',type=Path,metavar='BUILD_RUN')
    grp.add_argument('--run',type=Path,metavar='BUILD_RUN')
    grp.add_argument('--resume',type=Path,metavar='QPS_SESSION')
    grp.add_argument('--summarize',type=Path,metavar='QPS_SESSION')
    args=ap.parse_args()
    if args.selftest:selftest()
    elif args.preflight:audit(args.preflight)
    elif args.run:do_run(args.run)
    elif args.resume:do_existing(args.resume,search=True)
    elif args.summarize:do_existing(args.summarize,search=False)


if __name__=='__main__':
    try:main()
    except Exception as e:
        print('R85_SCALE1_QPS_FAIL_CLOSED '+repr(e),file=sys.stderr,flush=True)
        sys.exit(2)
