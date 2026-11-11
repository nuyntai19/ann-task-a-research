#!/usr/bin/env python3
"""R85-A3.1: SIFT1M H17-only global reservoir capacity pilot.

New builds: flat C32, C48, C96; 2 independently built graphs per capacity,
4 P-cores, counterbalanced order; only -table_size differs.
New search: 6 new graphs + 3 archived B160 graphs, 25 real beams each.
Archived B64 (3 graphs x 25 beams) is read, never re-evaluated or overwritten.

Modes: --selftest, --dry-run, --run-build, --resume-build RUN,
       --run-quality RUN (resumable per graph), --summarize RUN.

All outputs are NEW under experiments/H85/r85_a3_1_capacity_sweep.
Prior H70-H85 source, binary, graphs, and result files are read-only.
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
import re
import shlex
import subprocess
import sys
from statistics import median

ROOT = Path.home() / 'ann-task-a'
DL = Path.home() / 'Downloads'
OUT = ROOT / 'experiments/H85/r85_a3_1_capacity_sweep'
A1_RUN = ROOT / 'experiments/H85/r85_a1_capacity_ablation/runs_20261109-215545'
A1C_RESULTS = A1_RUN / 'matched_quality/measured_B64_results.json'
A1_SCRIPT = DL / 'run_r85_a1_capacity_ablation.py'
A1_SHA = '843cacaffb0c16d0ab8f86a32546ca74cc3b4c59d47ac3fd724e5fffc2accdb9'
A1C_SCRIPT = DL / 'run_r85_a1c_matched_search.py'
A1C_SHA = 'a61c32764d4624800f8bbc8c7de62e9c2938ab7da5ab89adaef35f9c90d2c778'
CPUS = (0, 2, 4, 6)
NEW_ARMS = ('C32','C48','C96')
ALL_ARMS = ('C32','C48','C64','C96','C160')
CAP = {'C32':32,'C48':48,'C64':64,'C96':96,'C160':160}
REPS = (1,2)
TARGETS = (0.76, 0.89, 0.96, 0.99, 0.998)
TIME_RE = re.compile(r'R85A3_TIME wall_s=([0-9.]+) peak_rss_kib=(\d+)')
Q_RE = re.compile(r'R72_RECALL_ROW beam=(\d+) recall=([0-9.Ee+-]+) qps=([0-9.Ee+-]+) avg_cmps=([0-9.Ee+-]+) avg_visited=([0-9.Ee+-]+)')


def fail(s):
    raise RuntimeError('R85_A3_FAIL_CLOSED ' + str(s))


def sha(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda:f.read(1<<20),b''):
            h.update(b)
    return h.hexdigest()


def atomic(p,obj):
    p=Path(p)
    t=p.with_name(p.name+'.tmp')
    t.write_text(json.dumps(obj,indent=2,ensure_ascii=False,allow_nan=False)+'\n',encoding='utf-8')
    t.replace(p)


def load(p, name, sig):
    if not p.is_file() or sha(p)!=sig:fail('Pinned Python script missing/changed: '+str(p))
    spec=importlib.util.spec_from_file_location(name,p)
    if spec is None or spec.loader is None:fail('Could not import '+str(p))
    m=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def pins():
    a1=load(A1_SCRIPT,'r85_a3_a1_pin',A1_SHA)
    a1c=load(A1C_SCRIPT,'r85_a3_a1c_pin',A1C_SHA)
    old=a1.load_pinned_previous()
    old.check_inputs()
    a1.verify_b_manifest()
    a1c.check_evaluator()
    if not A1C_RESULTS.is_file():fail('A1c B64 25-beam quality missing')
    b64_rows=json.loads(A1C_RESULTS.read_text())
    if len(b64_rows)!=3*len(a1c.BEAMS) or {(r['arm'],r['rep'],r['beam']) for r in b64_rows}!={( 'B64',rep,b) for rep in (1,2,3) for b in a1c.BEAMS}:
        fail('Unexpected/duplicate A1c B64 quality rows')
    # Rename only in-memory: archived original quality rows use arm='B64'.
    b64_rows=[dict(r,arm='C64') for r in b64_rows]
    original_builds=json.loads((A1_RUN/'build_results.json').read_text())
    if len(original_builds)!=9:fail('A1 original BUILD count changed')
    old_b={}
    for r in original_builds:
        k=(r['arm'],r['rep'])
        if k in old_b or not Path(r['graph']).is_file() or sha(r['graph'])!=r['graph_sha256']:
            fail('A1 old graph changed: '+str(k))
        old_b[k]=r
    if set(old_b)!={(a,r) for a in ('B160','B64','D0') for r in (1,2,3)}:
        fail('A1 unexpected arm/rep')
    print('R85_A3_PINNED_H17_SOURCE_BASE_QUERIES_GT_A1C_EVALUATOR_GRAPHS_PASS',flush=True)
    return old,a1,a1c,old_b,b64_rows


def schedule():
    return [(1,'C32'),(1,'C48'),(1,'C96'),(2,'C96'),(2,'C32'),(2,'C48')]


def build_command(old,a1,arm,graph):
    if arm not in NEW_ARMS:fail('Unknown new capacity arm')
    cmd=old.build_cmd('D0',4,graph)
    cmd[0]=str(a1.H17_EXE)
    cmd[cmd.index('-table_size')+1]=str(CAP[arm])
    if str(cmd[cmd.index('-prune_degree')+1])!='64' or str(cmd[cmd.index('-alpha')+1])!='1.1':
        fail('R or alpha have drifted from protocol')
    return cmd


def checked_run(cmd,log,env):
    with Path(log).open('w',encoding='utf-8') as f:
        f.write('# COMMAND '+shlex.join([str(x) for x in cmd])+'\n')
        f.flush()
        p=subprocess.run([str(x) for x in cmd],cwd=str(ROOT),env=env,stdout=f,stderr=subprocess.STDOUT)
    if p.returncode:fail(f'Native command failed rc={p.returncode}; log: {log}')
    return Path(log).read_text(encoding='utf-8',errors='replace')


def check_run(run):
    run=Path(run).resolve()
    if run.parent!=OUT.resolve() or not run.name.startswith('runs_') or not (run/'manifest.json').is_file():
        fail('Invalid A3 run path: '+str(run))
    m=json.loads((run/'manifest.json').read_text())
    if m.get('schedule')!=[list(x) for x in schedule()] or m.get('arms')!=list(NEW_ARMS):
        fail('Invalid A3 manifest')
    return run,m


def previous_rows(run,a1):
    p=run/'build_results.json'
    rows=json.loads(p.read_text()) if p.is_file() else []
    if len(rows)>len(schedule()):fail('Too many saved BUILD records')
    for index,r in enumerate(rows):
        rep,arm=schedule()[index]
        if r['arm']!=arm or r['rep']!=rep or r['capacity']!=CAP[arm]:
            fail('Saved BUILD order mismatch')
        if r['binary_sha256']!=sha(a1.H17_EXE):fail('H17 binary changed')
        p=Path(r['graph'])
        if not p.is_file() or sha(p)!=r['graph_sha256']:
            fail('Saved graph missing/modified '+str(p))
    return rows


def do_build(old,a1,run=None):
    if run is None:
        stamp=dt.datetime.now().strftime('%Y%m%d-%H%M%S')
        OUT.mkdir(parents=True,exist_ok=True)
        run=OUT/('runs_'+stamp)
        run.mkdir(exist_ok=False)
        atomic(run/'manifest.json',{'schedule':schedule(),'arms':list(NEW_ARMS),
               'capacities':CAP,'threads':4,'cpus':list(CPUS),
               'h17_sha256':sha(a1.H17_EXE),
               'origin_a1':str(A1_RUN),'search_beams':'pinned A1c 25-beam list',
               'repetition_count_new':2,'protocol':'No D0, only table_size changes'})
    run,m=check_run(run)
    if sha(a1.H17_EXE)!=m['h17_sha256']:fail('Pinned executable mismatch')
    saved=previous_rows(run,a1)
    rows=saved[:]
    if len(rows)==len(schedule()):
        print('R85_A3_ALREADY_BUILT '+str(run),flush=True)
        return
    available=os.statvfs(run)
    gib=available.f_bavail*available.f_frsize/1024**3
    if gib<1.5:fail(f'Free disk too small for 6 graphs: {gib:.2f} GiB')
    for i,(rep,arm) in enumerate(schedule(),1):
        if i<=len(rows):
            print(f'R85_A3_BUILD_SKIP_VERIFIED {i}/6 t4_r{rep}_{arm}',flush=True)
            continue
        tag=f't4_r{rep}_{arm}'
        graph=run/(tag+'.graph')
        if graph.exists():fail('Incomplete graph exists, refuse to overwrite: '+str(graph))
        log=run/(tag+'.log')
        timelog=run/(tag+'.time')
        cmd=['taskset','-c',','.join(map(str,CPUS)),'/usr/bin/time','-f',
             'R85A3_TIME wall_s=%e peak_rss_kib=%M','-o',str(timelog)]+build_command(old,a1,arm,graph)
        print(f'R85_A3_BUILD_START {i}/6 tag={tag} C={CAP[arm]}',flush=True)
        txt=checked_run(cmd,log,dict(os.environ,PARLAY_NUM_THREADS='4'))
        if 'R71_SELECTION_VARIANT=H17_PACKED_TOP2' not in txt or f'R70_RESERVOIR_VARIANT=STOCK_FLAT_C{CAP[arm]}' not in txt:
            fail('Kernel/reservoir marker mismatch in '+str(log))
        mm=TIME_RE.search(timelog.read_text())
        if not mm:fail('No /usr/bin/time metrics: '+str(timelog))
        graph_stats=old.check_graph(graph)
        row={'rep':rep,'arm':arm,'tag':tag,'capacity':CAP[arm],
             'binary_sha256':sha(a1.H17_EXE),'graph':str(graph),
             'log':str(log),'time_log':str(timelog),
             'wall_s':float(mm[1]),'peak_rss_kib':int(mm[2]),**graph_stats}
        rows.append(row)
        atomic(run/'build_results.json',rows)
        print(f"R85_A3_BUILD_PASS tag={tag} wall_s={row['wall_s']:.3f} rss_kib={row['peak_rss_kib']} arcs={row['arcs']}",flush=True)
    summ={a:{'n':2,'median_wall_s':median(r['wall_s'] for r in rows if r['arm']==a),
             'median_rss_kib':median(r['peak_rss_kib'] for r in rows if r['arm']==a),
             'median_arcs':median(r['arcs'] for r in rows if r['arm']==a),
             'all_wall_s':[r['wall_s'] for r in rows if r['arm']==a],
             'all_rss_kib':[r['peak_rss_kib'] for r in rows if r['arm']==a]}
          for a in NEW_ARMS}
    atomic(run/'build_summary.json',{'new_arms':summ,'reference_old_a1_build_run':str(A1_RUN),
           'warning':'Old and new BUILD timings are separate sessions, comparison is exploratory'})
    print('R85_A3_ALL_6_BUILDS_AND_STRUCTURAL_SCREENS_PASS',flush=True)
    print('R85_A3_BUILD_SUMMARY '+json.dumps(summ),flush=True)
    print('R85_A3_RESULTS_DIR '+str(run),flush=True)


def parse_quality(txt, arm, rep, tag, beams):
    if 'R72_RECALL_INPUT_PASS' not in txt or 'R72_RECALL_EVAL_PASS' not in txt or \
        f'R85_A1C_DYNAMIC_BEAMS count={len(beams)}' not in txt:
        fail('Native evaluator did not pass on '+tag)
    found=Q_RE.findall(txt)
    if len(found)!=len(beams) or {int(m[0]) for m in found}!=set(beams):
        fail('Missing or duplicated beams on '+tag)
    rows=[]
    for b,rec,qps,cmps,vis in found:
        r={'tag':tag,'arm':arm,'rep':rep,'beam':int(b),'recall':float(rec),
           'qps':float(qps),'avg_cmps':float(cmps),'avg_visited':float(vis)}
        if not 0<=r['recall']<=1 or not all(math.isfinite(r[k]) and r[k]>0 for k in ('qps','avg_cmps','avg_visited')):
            fail('Invalid quality metric in '+tag)
        rows.append(r)
    return sorted(rows,key=lambda r:r['beam'])


def quality(old,a1,a1c,old_b,b64,run):
    run,m=check_run(run)
    builds=previous_rows(run,a1)
    if len(builds)!=6 or not (run/'build_summary.json').is_file():fail('6 complete BUILD required')
    if sha(a1c.EVAL)!=json.loads(a1c.MANIFEST.read_text())['dynamic_evaluator_sha256']:
        fail('A1c evaluator SHA mismatch')
    ref=[{'tag':f't4_r{rep}_C160','arm':'C160','rep':rep,
          'graph':old_b['B160',rep]['graph'],
          'graph_sha256':old_b['B160',rep]['graph_sha256']} for rep in (1,2,3)]
    tasks=builds+ref
    qdir=run/'quality'
    qdir.mkdir(exist_ok=True)
    beams=list(a1c.BEAMS)
    for i,r in enumerate(tasks,1):
        name=r['tag']; p=qdir/(name+'.json')
        srcsha=r['graph_sha256']
        if sha(r['graph'])!=srcsha:fail('Graph SHA changed: '+name)
        if p.is_file():
            record=json.loads(p.read_text())
            if record.get('graph_sha256')!=srcsha or record.get('evaluator_sha256')!=sha(a1c.EVAL) or \
               {(z['arm'],z['rep'],z['beam']) for z in record.get('rows',[])}!={(r['arm'],r['rep'],b) for b in beams}:
                fail('Existing per-graph SEARCH JSON invalid, refuse overwrite: '+str(p))
            print(f'R85_A3_QUALITY_SKIP_VERIFIED {i}/9 {name}',flush=True)
            continue
        print(f'R85_A3_QUALITY_START {i}/9 graph={name} beams={len(beams)}',flush=True)
        cmd=['taskset','-c',','.join(map(str,CPUS)),str(a1c.EVAL),str(r['graph']),
             str(old.DATA_FILES['base'][0]),str(old.DATA_FILES['query'][0]),
             str(old.DATA_FILES['gt'][0]),','.join(map(str,beams))]
        log=qdir/(name+'.log')
        txt=checked_run(cmd,log,dict(os.environ,PARLAY_NUM_THREADS='4'))
        results=parse_quality(txt,r['arm'],r['rep'],name,beams)
        atomic(p,{'graph_sha256':srcsha,'evaluator_sha256':sha(a1c.EVAL),'rows':results})
        print('R85_A3_QUALITY_PASS '+name,flush=True)
    summarize(old,a1,a1c,old_b,b64,run)


def frontier(qrows):
    points=sorted((float(r['avg_cmps']),float(r['recall']),int(r['beam'])) for r in qrows)
    output=[]; best=-1.
    for cmp,r,b in points:
        if r>best+1e-10:
            output.append((r,cmp,b)); best=r
    return output


def interpolated(fr,target):
    if not fr or target<fr[0][0]-1e-10 or target>fr[-1][0]+1e-10:return None
    for rec,cmp,b in fr:
        if abs(rec-target)<=1e-10:return {'comparisons':cmp,'beams':[b,b],'width_pp':0.,'status':'MEASURED'}
    for (rl,cl,bl),(rh,ch,bh) in zip(fr,fr[1:]):
        if rl<=target<=rh and rh>rl:
            frac=(target-rl)/(rh-rl)
            return {'comparisons':cl+frac*(ch-cl),'beams':[bl,bh],
                    'width_pp':100*(rh-rl),'status':'INTERPOLATED'}
    return None


def summarize(old,a1,a1c,old_b,b64,run):
    run,m=check_run(run)
    builds=previous_rows(run,a1)
    if len(builds)!=6 or not (run/'build_summary.json').is_file():fail('No complete BUILD')
    qdir=run/'quality'
    all_rows=list(b64)
    for arm in ('C32','C48','C96','C160'):
        reps=REPS if arm in NEW_ARMS else (1,2,3)
        for rep in reps:
            p=qdir/f't4_r{rep}_{arm}.json'
            if not p.is_file():fail('Missing quality row file '+str(p))
            rec=json.loads(p.read_text())
            source=next(r for r in builds if (r['arm'],r['rep'])==(arm,rep)) if arm in NEW_ARMS else old_b['B160',rep]
            if rec.get('graph_sha256')!=source['graph_sha256'] or rec.get('evaluator_sha256')!=sha(a1c.EVAL):
                fail('Per-graph quality SHA provenance mismatch '+str(p))
            rows=rec.get('rows',[])
            if len(rows)!=len(a1c.BEAMS) or {(x['arm'],x['rep'],x['beam']) for x in rows}!={(arm,rep,b) for b in a1c.BEAMS}:
                fail('Partial/duplicate quality rows '+str(p))
            all_rows.extend(rows)
    if len(all_rows)!=(6+3+3)*25:fail('Wrong full comparison quality row count')
    atomic(qdir/'all_quality_rows.json',all_rows)
    curve=[]
    for b in a1c.BEAMS:
        d={'beam':b}
        for arm in ALL_ARMS:
            x=[r for r in all_rows if r['arm']==arm and r['beam']==b]
            assert len(x)==(2 if arm in NEW_ARMS else 3)
            d[arm]={'n':len(x),'recall_median':median(r['recall'] for r in x),
                    'cmps_median':median(r['avg_cmps'] for r in x)}
        curve.append(d)
    atomic(qdir/'curve_medians.json',curve)
    analysis=[]
    for target in TARGETS:
        d={'target':target,'arms':{}}
        for arm in ALL_ARMS:
            reps=REPS if arm in NEW_ARMS else (1,2,3)
            byrep=[]
            for rep in reps:
                fr=frontier([r for r in all_rows if r['arm']==arm and r['rep']==rep])
                v=interpolated(fr,target)
                byrep.append({'rep':rep,**(v if v else {'status':'OUTSIDE_MEASURED_RANGE'})})
            good=[v['comparisons'] for v in byrep if 'comparisons' in v]
            d['arms'][arm]={'n_covered':len(good),'n_total':len(reps),
                'comparisons_min_med_max':[min(good),median(good),max(good)] if good else None,
                'per_rep':byrep}
        # Ratios must be computed only after C64 has been populated.
        base=d['arms']['C64']['comparisons_min_med_max']
        for arm in ALL_ARMS:
            if arm!='C64':
                a=d['arms'][arm]['comparisons_min_med_max']
                d['arms'][arm]['ratio_of_arm_median_to_C64']=a[1]/base[1] if (a and base) else None
        analysis.append(d)
        p={arm:(round(d['arms'][arm]['ratio_of_arm_median_to_C64'],4) if d['arms'][arm].get('ratio_of_arm_median_to_C64') is not None else None) for arm in ALL_ARMS if arm!='C64'}
        print('R85_A3_MATCHED_RECALL_INTERP_ROW '+json.dumps({'target':target,'ratios_vs_C64':p,'covered':{a:d['arms'][a]['n_covered'] for a in ALL_ARMS}}),flush=True)
    atomic(qdir/'matched_recall_interpolation.json',analysis)
    atomic(qdir/'protocol_summary.json',{'new_builds':6,'new_search_graphs':9,'reused_existing_B64_search_graphs':3,
         'quality_beams':list(a1c.BEAMS),'targets':list(TARGETS),'new_arm_reps':2,'historical_baselines_reps':3,
         'comparison_note':'INTERPOLATION, not measured exact matched recall; medians from unequal rep counts; build session confounding',
         'h17_exe_sha256':sha(a1.H17_EXE),'evaluator_sha256':sha(a1c.EVAL),
         'a1_reference':str(A1_RUN)})
    print('R85_A3_ALL_9_NEW_SEARCHES_PASS_AND_3_B64_SEARCHES_REUSED',flush=True)
    print('R85_A3_QUALITY_RESULTS '+str(qdir/'matched_recall_interpolation.json'),flush=True)
    print('R85_A3_RESULTS_DIR '+str(run),flush=True)


def selftest():
    assert len(schedule())==6 and {a for _,a in schedule()}==set(NEW_ARMS)
    assert all(len([x for x in schedule() if x[1]==a])==2 for a in NEW_ARMS)
    fr=frontier([{'beam':10,'avg_cmps':100,'recall':.6},
                 {'beam':11,'avg_cmps':110,'recall':.8},
                 {'beam':12,'avg_cmps':150,'recall':.79}])
    assert len(fr)==2
    r=interpolated(fr,.7)
    assert abs(r['comparisons']-105)<1.e-10 and r['status']=='INTERPOLATED'
    assert interpolated(fr,.9) is None
    print('R85_A3_SELFTEST_PASS',flush=True)


def main():
    p=argparse.ArgumentParser(description=__doc__,formatter_class=argparse.RawDescriptionHelpFormatter)
    g=p.add_mutually_exclusive_group(required=True)
    g.add_argument('--selftest',action='store_true')
    g.add_argument('--dry-run',action='store_true')
    g.add_argument('--run-build',action='store_true')
    g.add_argument('--resume-build',type=Path,metavar='RUN')
    g.add_argument('--run-quality',type=Path,metavar='RUN')
    g.add_argument('--summarize',type=Path,metavar='RUN')
    args=p.parse_args()
    if args.selftest:
        selftest();return
    old,a1,a1c,old_b,b64=pins()
    if args.dry_run:
        for i,(rep,arm) in enumerate(schedule(),1):
            cmd=['taskset','-c',','.join(map(str,CPUS)),'env','PARLAY_NUM_THREADS=4']+build_command(old,a1,arm,Path(f'<new_run>/t4_r{rep}_{arm}.graph'))
            print(f'R85_A3_DRY_RUN {i}/6 '+shlex.join(cmd),flush=True)
        print('R85_A3_DRY_RUN_PASS_NO_BUILD_NO_SEARCH');return
    if args.run_build:do_build(old,a1);return
    if args.resume_build:do_build(old,a1,args.resume_build);return
    if args.run_quality:quality(old,a1,a1c,old_b,b64,args.run_quality);return
    if args.summarize:summarize(old,a1,a1c,old_b,b64,args.summarize);return

if __name__=='__main__':
    try:main()
    except (OSError,RuntimeError,ValueError,AssertionError,KeyError,TypeError,IndexError) as e:
        print('R85_A3_FAIL_CLOSED '+repr(e),file=sys.stderr)
        sys.exit(1)
