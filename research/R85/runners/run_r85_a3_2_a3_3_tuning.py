#!/usr/bin/env python3
"""R85-A3.2 / R85-A3.3 SIFT1M baseline-tuning pilot (source unchanged).

Two independent sessions:
  alpha: C32 alpha=1.20, C48 alpha=1.20, C64 alpha=1.20,
         C48 alpha=1.05 (R64, cluster_size1024, num_clusters2).
  partition: C64, alpha=1.10, R64 with (size,rounds)=(512,2),(768,2),(1024,1).
Two BUILD repetitions per arm (counterbalanced), H17-only fixed binary.
25-beam real SEARCH with resume at graph granularity. Compare interpolated
Recall-vs-comparisons against archived unchanged-alpha/candidate baselines.
Read prior A1/A1c/A3.1 runners and graph/result files; NEVER modifies them.
Modes: --selftest, --dry-run {alpha,partition}, --run-build {alpha,partition},
       --resume-build RUN, --run-quality RUN, --summarize RUN.
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

HOME = Path.home()
ROOT = HOME/'ann-task-a'
DL = HOME/'Downloads'
OUT = ROOT/'experiments/H85/r85_a3_2_a3_3_tuning'
A3_FILE = DL/'run_r85_a3_1_capacity_sweep.py'
A3_SHA = 'ab30f4d0bdb4fe81cca6f8095e4b819900c91008344b0809ed000eb03504cf56'
A3_RUN = ROOT/'experiments/H85/r85_a3_1_capacity_sweep/runs_20261109-233756'
CPUS = (0,2,4,6)
TIME_RE = re.compile(r'R85A32_TIME wall_s=([0-9.]+) peak_rss_kib=(\d+)')
Q_RE = re.compile(r'R72_RECALL_ROW beam=(\d+) recall=([0-9.Ee+-]+) qps=([0-9.Ee+-]+) avg_cmps=([0-9.Ee+-]+) avg_visited=([0-9.Ee+-]+)')
TARGETS = (.76,.89,.96,.99,.998)
PARAMS = {
 'alpha': {
    'C32_A120': (32,64,1.20,1024,2),
    'C48_A120': (48,64,1.20,1024,2),
    'C64_A120': (64,64,1.20,1024,2),
    'C48_A105': (48,64,1.05,1024,2),
 },
 'partition': {
    'C64_K512_N2': (64,64,1.10,512,2),
    'C64_K768_N2': (64,64,1.10,768,2),
    'C64_K1024_N1': (64,64,1.10,1024,1),
 },
}


def fail(message):
    raise RuntimeError('R85_A32_FAIL_CLOSED '+str(message))


def sha(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda:f.read(1<<20),b''):
            h.update(b)
    return h.hexdigest()


def atomic(p,obj):
    p=Path(p)
    tmp=p.with_name(p.name+'.tmp')
    tmp.write_text(json.dumps(obj,indent=2,allow_nan=False,ensure_ascii=False)+'\n',encoding='utf8')
    tmp.replace(p)


def imported(path, name, digest):
    if not path.is_file() or sha(path)!=digest:
        fail('Pinned dependency missing/changed: '+str(path))
    spec=importlib.util.spec_from_file_location(name,path)
    if spec is None or spec.loader is None:
        fail('Cannot load '+str(path))
    m=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def deps():
    a3=imported(A3_FILE,'r85_a32_a3_pin',A3_SHA)
    old,a1,a1c,old_b,b64=a3.pins()
    # Required original A3.1 C32/C48 refs, to avoid rerunning alpha=1.1 graph build.
    p=A3_RUN/'build_results.json'
    if not p.is_file() or not (A3_RUN/'quality/matched_recall_interpolation.json').is_file():
        fail('Completed A3.1 capacity run missing: '+str(A3_RUN))
    entries=json.loads(p.read_text())
    if len(entries)!=6:
        fail('A3.1 unexpected BUILD rows')
    refs={}
    for r in entries:
        key=(r['arm'],r['rep'])
        if key in refs or not Path(r['graph']).is_file() or sha(r['graph'])!=r['graph_sha256']:
            fail('A3.1 graph missing/changed: '+str(key))
        refs[key]=r
    if set(refs)!={(arm,rep) for arm in ('C32','C48','C96') for rep in (1,2)}:
        fail('A3.1 BUILD keys incorrect')
    for arm in ('C32','C48'):
        for rep in (1,2):
            p=A3_RUN/'quality'/f't4_r{rep}_{arm}.json'
            if not p.is_file():fail('Missing A3.1 original quality: '+str(p))
            rec=json.loads(p.read_text())
            if rec.get('graph_sha256')!=refs[arm,rep]['graph_sha256'] or \
               rec.get('evaluator_sha256')!=sha(a1c.EVAL) or \
               len(rec.get('rows',[]))!=len(a1c.BEAMS):
                fail('A3.1 original quality provenance wrong: '+str(p))
    print('R85_A32_PINNED_H17_DATA_EVALUATOR_A1C_A3_INPUTS_PASS',flush=True)
    return a3,old,a1,a1c,b64,refs


def schedule(phase):
    arms=list(PARAMS[phase])
    # First pass in declared order, second pass in reverse order.
    return [(1,a) for a in arms]+[(2,a) for a in reversed(arms)]


def cmd_build(old,a1,phase,arm,graph):
    C,R,alpha,K,N=PARAMS[phase][arm]
    cmd=old.build_cmd('D0',4,graph)
    cmd[0]=str(a1.H17_EXE)
    repl={'-table_size':str(C),'-prune_degree':str(R),'-alpha':str(alpha),
          '-cluster_size':str(K),'-num_clusters':str(N)}
    for flag,value in repl.items():
        if cmd.count(flag)!=1:fail('Unexpected native flag count: '+flag)
        cmd[cmd.index(flag)+1]=value
    if '-prune' not in cmd or str(cmd[cmd.index('-prune')+1])!='1' or \
       '-prune_all' not in cmd or str(cmd[cmd.index('-prune_all')+1])!='1':
        fail('Unexpected native prune protocol')
    return cmd


def run_native(cmd,log,env):
    with Path(log).open('w',encoding='utf8') as f:
        f.write('# COMMAND '+shlex.join([str(t) for t in cmd])+'\n');f.flush()
        result=subprocess.run([str(t) for t in cmd],cwd=str(ROOT),env=env,stdout=f,stderr=subprocess.STDOUT)
    if result.returncode:
        fail(f'Native rc={result.returncode}; see {log}')
    return Path(log).read_text(errors='replace')


def require_run(path):
    run=Path(path).resolve()
    if run.parent!=OUT.resolve() or not run.name.startswith('runs_') or not (run/'manifest.json').is_file():
        fail('Invalid run directory: '+str(run))
    m=json.loads((run/'manifest.json').read_text())
    phase=m.get('phase')
    if phase not in PARAMS or m.get('schedule')!=[list(x) for x in schedule(phase)] or \
       m.get('params')!={a:list(x) for a,x in PARAMS[phase].items()} or \
       m.get('cpus')!=list(CPUS):
        fail('Manifest schedule/config changed')
    return run,m,phase


def saved_builds(run,m,phase,a1):
    p=run/'build_results.json'
    rows=json.loads(p.read_text()) if p.is_file() else []
    if len(rows)>len(schedule(phase)):
        fail('Too many saved build rows')
    if sha(a1.H17_EXE)!=m['h17_sha256']:
        fail('H17 binary drift')
    for i,r in enumerate(rows):
        rep,arm=schedule(phase)[i]
        if (r.get('rep'),r.get('arm'))!=(rep,arm) or tuple(r.get('params',()))!=PARAMS[phase][arm] or \
           r.get('binary_sha256')!=m['h17_sha256'] or not Path(r['graph']).is_file() or \
           sha(r['graph'])!=r['graph_sha256']:
            fail(f'Saved BUILD row {i+1} fails provenance check')
    return rows


def do_build(phase,a3,old,a1,run=None):
    if run is None:
        OUT.mkdir(parents=True,exist_ok=True)
        stamp=dt.datetime.now().strftime('%Y%m%d-%H%M%S')
        run=OUT/f'runs_{phase}_{stamp}'
        run.mkdir(exist_ok=False)
        atomic(run/'manifest.json',{'phase':phase,'schedule':schedule(phase),
           'params':{a:list(x) for a,x in PARAMS[phase].items()},
           'cpus':list(CPUS),'h17_sha256':sha(a1.H17_EXE),
           'a3_runner_sha256':A3_SHA,
           'reps':2,'protocol':'H17-only; 4 physical P cores; original source unmodified',
           'reference_a3_1':str(A3_RUN)})
    run,m,mode=require_run(run)
    if mode!=phase:fail('Phase mismatch')
    rows=saved_builds(run,m,mode,a1)
    if len(rows)==len(schedule(phase)):
        print('R85_A32_ALL_BUILDS_ALREADY_SAVED '+str(run),flush=True);return
    free=os.statvfs(run)
    if free.f_bavail*free.f_frsize<1_500_000_000:
        fail('Free disk under 1.5 GB')
    for i,(rep,arm) in enumerate(schedule(phase),1):
        if i<=len(rows):
            print(f'R85_A32_BUILD_SKIP_VERIFIED {i}/{len(schedule(phase))} {arm} r{rep}',flush=True)
            continue
        tag=f't4_r{rep}_{arm}'; graph=run/f'{tag}.graph'
        if graph.exists():
            fail('Unrecorded graph exists, refuse overwrite: '+str(graph))
        log=run/f'{tag}.log';tlog=run/f'{tag}.time'
        cmd=['taskset','-c',','.join(map(str,CPUS)),'/usr/bin/time','-f',
             'R85A32_TIME wall_s=%e peak_rss_kib=%M','-o',str(tlog)]+cmd_build(old,a1,phase,arm,graph)
        print(f'R85_A32_BUILD_START {i}/{len(schedule(phase))} phase={phase} tag={tag} params={PARAMS[phase][arm]}',flush=True)
        output=run_native(cmd,log,dict(os.environ,PARLAY_NUM_THREADS='4'))
        C,R,alpha,K,N=PARAMS[phase][arm]
        if 'R71_SELECTION_VARIANT=H17_PACKED_TOP2' not in output or \
           f'R70_RESERVOIR_VARIANT=STOCK_FLAT_C{C}' not in output:
            fail('Kernel/reservoir marker mismatch '+str(log))
        mtime=TIME_RE.search(tlog.read_text())
        if not mtime:
            fail('Missing /usr/bin/time metrics '+str(tlog))
        stat=old.check_graph(graph)
        if stat.get('degree_bound')!=R:
            fail('Native graph max degree unexpected: '+str(stat))
        row={'phase':phase,'rep':rep,'arm':arm,'tag':tag,'params':list(PARAMS[phase][arm]),
             'binary_sha256':sha(a1.H17_EXE),'graph':str(graph),'log':str(log),
             'time_log':str(tlog),'wall_s':float(mtime[1]),'peak_rss_kib':int(mtime[2]),**stat}
        rows.append(row)
        atomic(run/'build_results.json',rows)
        print(f'R85_A32_BUILD_PASS tag={tag} wall_s={row["wall_s"]:.3f} rss_kib={row["peak_rss_kib"]} arcs={row["arcs"]}',flush=True)
    report={arm:{'n':2,'median_wall_s':median(r['wall_s'] for r in rows if r['arm']==arm),
        'median_rss_kib':median(r['peak_rss_kib'] for r in rows if r['arm']==arm),
        'median_arcs':median(r['arcs'] for r in rows if r['arm']==arm),
        'all_wall_s':[r['wall_s'] for r in rows if r['arm']==arm],
        'all_rss_kib':[r['peak_rss_kib'] for r in rows if r['arm']==arm]}
        for arm in PARAMS[phase]}
    atomic(run/'build_summary.json',report)
    print('R85_A32_ALL_'+str(len(schedule(phase)))+'_BUILDS_PASS phase='+phase,flush=True)
    print('R85_A32_BUILD_SUMMARY '+json.dumps(report),flush=True)
    print('R85_A32_RESULTS_DIR '+str(run),flush=True)


def reference_quality(phase,a3,b64,refs,a1c):
    output={}
    # C64 is 3 independent A1c graphs and curves; C32/C48 are A3.1 originals.
    refs_names={'alpha': ('C32','C48','C64'), 'partition':('C64',)}[phase]
    for arm in refs_names:
        if arm=='C64':
            for rep in (1,2,3):
                subset=[dict(r,arm=arm) for r in b64 if r['rep']==rep]
                if len(subset)!=len(a1c.BEAMS):fail('C64 reference quality missing rep '+str(rep))
                output[arm,rep]=subset
        else:
            for rep in (1,2):
                p=A3_RUN/'quality'/f't4_r{rep}_{arm}.json'
                record=json.loads(p.read_text())
                if record.get('graph_sha256')!=refs[arm,rep]['graph_sha256'] or \
                   record.get('evaluator_sha256')!=sha(a1c.EVAL):
                    fail('Reference graph/evaluator SHA mismatch: '+str(p))
                subset=record['rows']
                if len(subset)!=len(a1c.BEAMS) or {(z['arm'],z['rep'],z['beam']) for z in subset} != \
                   {(arm,rep,b) for b in a1c.BEAMS}:
                    fail('Original reference quality rows invalid: '+str(p))
                output[arm,rep]=subset
    return output


def summarize(run,a3,a1c,b64,refs,a1):
    run,m,phase=require_run(run)
    builds=saved_builds(run,m,phase,a1)
    if len(builds)!=len(schedule(phase)) or not (run/'build_summary.json').is_file():
        fail('Not all BUILD complete')
    qdir=run/'quality'
    allrows={}
    for r in builds:
        p=qdir/(r['tag']+'.json')
        if not p.is_file():fail('Missing per-graph SEARCH: '+str(p))
        rec=json.loads(p.read_text())
        if rec.get('graph_sha256')!=r['graph_sha256'] or \
           rec.get('evaluator_sha256')!=sha(a1c.EVAL) or \
           {(x['arm'],x['rep'],x['beam']) for x in rec.get('rows',[])}!= \
           {(r['arm'],r['rep'],b) for b in a1c.BEAMS}:
            fail('Per-graph SEARCH provenance mismatch '+str(p))
        allrows[r['arm'],r['rep']]=rec['rows']
    allrows.update(reference_quality(phase,a3,b64,refs,a1c))
    report=[]
    for target in TARGETS:
        row={'target':target,'arms':{}}
        for arm in list(PARAMS[phase])+list({'alpha':['C32','C48','C64'],
                                                'partition':['C64']}[phase]):
            matches=[]
            for (keyarm,rep),quality in sorted(allrows.items()):
                if keyarm!=arm:continue
                fr=a3.frontier(quality)
                data=a3.interpolated(fr,target)
                matches.append({'rep':rep,**(data if data else {'status':'OUTSIDE_MEASURED_RANGE'})})
            good=[x['comparisons'] for x in matches if 'comparisons' in x]
            row['arms'][arm]={'n_covered':len(good),'n_total':len(matches),
                'comparisons_min_med_max':([min(good),median(good),max(good)] if good else None),
                'per_rep':matches}
        # Two specific controls for alpha: C32 and C64 each vs same C; C48 both A120,A105 vs C48.
        pairs=({'alpha':[('C32_A120','C32'),('C48_A120','C48'),('C64_A120','C64'),('C48_A105','C48')],
               'partition':[(a,'C64') for a in PARAMS['partition']]}[phase])
        ratios={}
        for arm,baseline in pairs:
            g=row['arms'][arm]['comparisons_min_med_max'];b=row['arms'][baseline]['comparisons_min_med_max']
            ratios[arm]={'baseline':baseline,'ratio_med_cmps':g[1]/b[1] if g and b else None,
               'coverage':f'{row["arms"][arm]["n_covered"]}/{row["arms"][arm]["n_total"]}'}
        row['ratios_to_control']=ratios
        report.append(row)
        print('R85_A32_MATCHED_RECALL_INTERP_ROW '+json.dumps({'phase':phase,'target':target,'ratios':ratios}),flush=True)
    atomic(qdir/'matched_recall_interpolation.json',report)
    atomic(qdir/'quality_provenance.json',{'phase':phase,'beams':list(a1c.BEAMS),
        'source':'25 observed beam points per graph; linear interpolation only within observed range',
        'baseline':'original 3x C64 A1c and original 2x C32/C48 A3.1',
        'warning':'Source runs are separate sessions, and new arms have 2 build repetitions; not proven noninferiority',
        'evaluator_sha256':sha(a1c.EVAL),'h17_sha256':sha(a1.H17_EXE)})
    print('R85_A32_MATCHED_RECALL_SUMMARY '+str(qdir/'matched_recall_interpolation.json'),flush=True)
    print('R85_A32_RESULTS_DIR '+str(run),flush=True)


def do_quality(run,a3,old,a1,a1c,b64,refs):
    run,m,phase=require_run(run)
    builds=saved_builds(run,m,phase,a1)
    if len(builds)!=len(schedule(phase)) or not (run/'build_summary.json').is_file():
        fail('No complete BUILD run')
    qdir=run/'quality';qdir.mkdir(exist_ok=True)
    for i,r in enumerate(builds,1):
        graph=Path(r['graph'])
        if sha(graph)!=r['graph_sha256']:fail('Graph SHA changed: '+r['tag'])
        dest=qdir/(r['tag']+'.json')
        if dest.is_file():
            z=json.loads(dest.read_text())
            expected={(r['arm'],r['rep'],b) for b in a1c.BEAMS}
            if z.get('graph_sha256')!=r['graph_sha256'] or \
               z.get('evaluator_sha256')!=sha(a1c.EVAL) or \
               {(p['arm'],p['rep'],p['beam']) for p in z.get('rows',[])}!=expected:
                fail('Previously saved quality JSON invalid '+str(dest))
            print(f'R85_A32_QUALITY_SKIP_VERIFIED {i}/{len(builds)} {r["tag"]}',flush=True)
            continue
        print(f'R85_A32_QUALITY_START {i}/{len(builds)} {r["tag"]} beams={len(a1c.BEAMS)}',flush=True)
        cmd=['taskset','-c',','.join(map(str,CPUS)),str(a1c.EVAL),str(graph),
             str(old.DATA_FILES['base'][0]),str(old.DATA_FILES['query'][0]),
             str(old.DATA_FILES['gt'][0]),','.join(map(str,a1c.BEAMS))]
        log=qdir/(r['tag']+'.log')
        txt=run_native(cmd,log,dict(os.environ,PARLAY_NUM_THREADS='4'))
        parsed=a3.parse_quality(txt,r['arm'],r['rep'],r['tag'],a1c.BEAMS)
        atomic(dest,{'graph_sha256':r['graph_sha256'],
                     'evaluator_sha256':sha(a1c.EVAL),'rows':parsed})
        print('R85_A32_QUALITY_PASS '+r['tag'],flush=True)
    print('R85_A32_ALL_'+str(len(builds))+'_SEARCHES_PASS phase='+phase,flush=True)
    summarize(run,a3,a1c,b64,refs,a1)


def test():
    assert set(PARAMS)=={'alpha','partition'}
    assert len(schedule('alpha'))==8 and len(schedule('partition'))==6
    for phase in PARAMS:
        for arm in PARAMS[phase]:
            assert len([1 for _,a in schedule(phase) if a==arm])==2
            C,R,a,K,N=PARAMS[phase][arm]
            assert R==64 and C>=32 and a>=1 and K in (512,768,1024) and N in (1,2)
    assert (PARAMS['alpha']['C48_A120'][0],PARAMS['alpha']['C48_A120'][2])==(48,1.2)
    assert (PARAMS['partition']['C64_K1024_N1'][3:])==(1024,1)
    class MockOld:
        def build_cmd(self, arm, threads, graph):
            assert arm=='D0' and threads==4
            return ['/tmp/pinned-stock','-graph_outfile',str(graph),'-prune','1',
                    '-prune_all','1','-table_size','160','-prune_degree','64',
                    '-alpha','1.1','-cluster_size','1024','-num_clusters','2']
    class MockA1:
        H17_EXE=Path('/tmp/pinned-h17')
    for phase in PARAMS:
        for arm,(C,R,a,K,N) in PARAMS[phase].items():
            cmd=cmd_build(MockOld(),MockA1(),phase,arm,Path('/tmp/output.graph'))
            assert cmd[0]=='/tmp/pinned-h17'
            for flag,val in [('-table_size',C),('-prune_degree',R),
                             ('-alpha',a),('-cluster_size',K),('-num_clusters',N)]:
                assert cmd.count(flag)==1 and cmd[cmd.index(flag)+1]==str(val)
    print('R85_A32_SELFTEST_PASS',flush=True)


def main():
    p=argparse.ArgumentParser(description=__doc__,formatter_class=argparse.RawDescriptionHelpFormatter)
    group=p.add_mutually_exclusive_group(required=True)
    group.add_argument('--selftest',action='store_true')
    group.add_argument('--dry-run',choices=PARAMS)
    group.add_argument('--run-build',choices=PARAMS)
    group.add_argument('--resume-build',type=Path,metavar='RUN')
    group.add_argument('--run-quality',type=Path,metavar='RUN')
    group.add_argument('--summarize',type=Path,metavar='RUN')
    args=p.parse_args()
    if args.selftest:test();return
    a3,old,a1,a1c,b64,refs=deps()
    if args.dry_run:
        mode=args.dry_run
        for i,(rep,arm) in enumerate(schedule(mode),1):
            cmd=['taskset','-c',','.join(map(str,CPUS)),'env','PARLAY_NUM_THREADS=4']+\
                cmd_build(old,a1,mode,arm,Path(f'<new_run>/t4_r{rep}_{arm}.graph'))
            print(f'R85_A32_DRY_RUN {i}/{len(schedule(mode))} phase={mode} '+shlex.join(cmd),flush=True)
        print('R85_A32_DRY_RUN_PASS_NO_BUILD_NO_SEARCH phase='+mode);return
    if args.run_build:do_build(args.run_build,a3,old,a1);return
    if args.resume_build:
        run,m,mode=require_run(args.resume_build)
        do_build(mode,a3,old,a1,run);return
    if args.run_quality:do_quality(args.run_quality,a3,old,a1,a1c,b64,refs);return
    if args.summarize:summarize(args.summarize,a3,a1c,b64,refs,a1);return

if __name__=='__main__':
    try:main()
    except (OSError,RuntimeError,ValueError,AssertionError,KeyError,TypeError,IndexError) as e:
        print('R85_A32_FAIL_CLOSED '+repr(e),file=sys.stderr)
        sys.exit(1)
