#!/usr/bin/env python3
"""R85-A4 six-arm SIFT1M paired confirmation, pinned, fail-closed.

Arms: Stock C160; H17+TwoTier D0 C160; H17 Flat C64 at
(K,N)=(1024,2),(512,2),(1024,1),(512,1).

Phases:
  --selftest
  --dry-run
  --run-build
  --resume-build RUN_DIR
  --run-quality RUN_DIR      (25 measured beams; all new graphs)
  --run-qps RUN_DIR          (one P-core, 5 interleaved repeats, target beams)
  --summarize RUN_DIR

No source modifications, no recompile, no dataset download. Original runners
and native binaries are checked by SHA256. All outputs are new. Native graph
screens include header, degree bound, IDs, file size, SHA256. QPS is a
secondary measurement, not a latency/throughput noninferiority proof.
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
import shutil
import subprocess
import sys
from statistics import median

HOME = Path.home()
ROOT = HOME / 'ann-task-a'
DL = HOME / 'Downloads'
OUT = ROOT / 'experiments/H85/r85_a4_paired_sift1m'
OLD_FILE = DL / 'run_r85_0f_matched_sift1m.py'
OLD_SHA = '1e76bef61f16a15516d88c6249a3e07e5f47f0f54b1be31c00ac8942382f2d59'
A1_FILE = DL / 'run_r85_a1_capacity_ablation.py'
A1_SHA = '843cacaffb0c16d0ab8f86a32546ca74cc3b4c59d47ac3fd724e5fffc2accdb9'
A1C_FILE = DL / 'run_r85_a1c_matched_search.py'
A1C_SHA = 'a61c32764d4624800f8bbc8c7de62e9c2938ab7da5ab89adaef35f9c90d2c778'
ARMS = {
    'STOCK':       ('A', 160, 1024, 2, 'STOCK_HIGHWAY', 'STOCK_FLAT_C160'),
    'D0':          ('D0',160, 1024, 2, 'H17_PACKED_TOP2', 'TIER_B64_C160'),
    'C64_K1024_N2':('H17',64,1024,2,'H17_PACKED_TOP2','STOCK_FLAT_C64'),
    'C64_K512_N2': ('H17',64, 512,2,'H17_PACKED_TOP2','STOCK_FLAT_C64'),
    'C64_K1024_N1':('H17',64,1024,1,'H17_PACKED_TOP2','STOCK_FLAT_C64'),
    'C64_K512_N1': ('H17',64, 512,1,'H17_PACKED_TOP2','STOCK_FLAT_C64'),
}
ARM_ORDER = tuple(ARMS)
REPS = 3
BUILD_CPUS = (0,2,4,6)
QPS_CPU = 0
QPS_REPS = 5
TARGETS = (0.76, 0.89, 0.96, 0.99, 0.998)
TIME_RE = re.compile(r'R85_A4_TIME wall_s=([0-9.]+) peak_rss_kib=(\d+)')
ROW_RE = re.compile(r'R72_RECALL_ROW beam=(\d+) recall=([0-9.Ee+-]+) qps=([0-9.Ee+-]+) avg_cmps=([0-9.Ee+-]+) avg_visited=([0-9.Ee+-]+)')


def fail(msg):
    raise RuntimeError('R85_A4_FAIL_CLOSED: ' + str(msg))


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for buf in iter(lambda:f.read(1<<20),b''):
            h.update(buf)
    return h.hexdigest()


def atomic(path, val):
    p=Path(path)
    tmp=p.with_name(p.name+'.tmp')
    tmp.write_text(json.dumps(val,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf8')
    tmp.replace(p)


def imp(path, name, digest):
    if not path.is_file() or sha(path)!=digest:
        fail('Pinned Python dependency missing/changed: '+str(path))
    spec=importlib.util.spec_from_file_location(name,path)
    if spec is None or spec.loader is None:fail('Cannot import '+str(path))
    m=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def dep(require_eval=True):
    old=imp(OLD_FILE,'r85a4_old',OLD_SHA)
    a1=imp(A1_FILE,'r85a4_a1',A1_SHA)
    a1c=imp(A1C_FILE,'r85a4_a1c',A1C_SHA)
    base=old.check_inputs()          # source, binaries, datasets, graph format, affinity
    b=a1.verify_b_manifest()        # C64 binary and compile flags vs D0
    ev=a1c.check_evaluator() if require_eval else None
    # Guard dynamic evaluator SHA even if current mode doesn't need it.
    return old,a1,a1c,base,b,ev


def schedule():
    # Each arm appears once per rep; cyclically rotate starting arm by two slots.
    seq=[]
    for rep,offset in ((1,0),(2,2),(3,4)):
        order=ARM_ORDER[offset:]+ARM_ORDER[:offset]
        seq += [(rep,arm) for arm in order]
    return seq


def qps_schedule():
    # Rotate all 18 graph cases, not just arm labels. Each rep sees each graph.
    plan=schedule()
    for r in range(1,QPS_REPS+1):
        shift=(r-1)*5%len(plan)
        yield r,plan[shift:]+plan[:shift]


def executables(old,a1):
    return {'A':old.BINARIES['A'],'D0':old.BINARIES['D0'],'H17':a1.H17_EXE}


def cmd_build(old,a1,arm,path):
    kind,C,K,N,_,_=ARMS[arm]
    cmd=old.build_cmd('D0',4,path)
    cmd[0]=str(executables(old,a1)[kind])
    replacements={'-table_size':C,'-cluster_size':K,'-num_clusters':N}
    for flag,v in replacements.items():
        if cmd.count(flag)!=1:fail('Incorrect native CLI: '+flag)
        cmd[cmd.index(flag)+1]=str(v)
    for flag,value in {'-prune_degree':'64','-alpha':'1.1','-mst_deg':'2',
                       '-prune':'1','-prune_all':'1','-hash_bits':'12'}.items():
        if cmd.count(flag)!=1 or cmd[cmd.index(flag)+1]!=value:
            fail('Unexpected native CLI '+flag)
    return cmd


def check_environment():
    if not shutil.which('taskset') or not Path('/usr/bin/time').is_file():
        fail('taskset or /usr/bin/time unavailable')
    avail={int(s) for s in os.sched_getaffinity(0)}
    if not set(BUILD_CPUS).issubset(avail):
        fail('Required P-core CPU IDs not available')
    free=os.statvfs(ROOT)
    free_gib=free.f_bavail*free.f_frsize/(1024**3)
    if free_gib<5:fail(f'Free disk {free_gib:.2f} GiB < 5 GiB')
    return round(free_gib,3)


def identity(old,a1,a1c,phase):
    ex=executables(old,a1)
    return {'source_head':old.EXPECTED_GIT,
            'source_sha256':{n:sha(old.SRC/n) for n in old.EXPECTED_SOURCE},
            'binary_sha256':{n:sha(path) for n,path in ex.items()},
            'evaluator_sha256':sha(a1c.EVAL),
            'data_sha256':{n:sha(p[0]) for n,p in old.DATA_FILES.items()},
            'runner_dependencies':{'old':OLD_SHA,'a1':A1_SHA,'a1c':A1C_SHA},
            'schedule':schedule(), 'arms':{a:list(v) for a,v in ARMS.items()},
            'build_cpus':list(BUILD_CPUS),'qps_cpu':QPS_CPU,
            'targets':list(TARGETS),'quality_beams':list(a1c.BEAMS),
            'qps_repetitions':QPS_REPS,
            'protocol':'New paired SIFT1M graph builds: 4 P-cores, no overlap; 25-beam 4P graph quality; 1P repeated QPS, graph-interleaved.',
            'created_at_local':dt.datetime.now().isoformat(timespec='seconds'),
            'phase_created':phase}


def open_run(path,old,a1,a1c):
    run=Path(path).resolve()
    if run.parent!=OUT.resolve() or not run.name.startswith('runs_'):
        fail('Refuse external/invalid output path '+str(run))
    mfile=run/'manifest.json'
    if not mfile.is_file():fail('Run manifest absent')
    m=json.loads(mfile.read_text())
    if m.get('schedule')!=[list(x) for x in schedule()] or \
       m.get('arms')!={a:list(v) for a,v in ARMS.items()} or \
       m.get('targets')!=list(TARGETS) or m.get('quality_beams')!=list(a1c.BEAMS) or \
       m.get('build_cpus')!=list(BUILD_CPUS) or m.get('qps_cpu')!=QPS_CPU or \
       m.get('qps_repetitions')!=QPS_REPS:
        fail('Run manifest protocol changed')
    current=identity(old,a1,a1c,'check')
    for k in ('source_head','source_sha256','binary_sha256','evaluator_sha256',
              'data_sha256','runner_dependencies'):
        if m.get(k)!=current[k]:fail('Pinned input drift: '+k)
    return run,m


def build_rows(run,m,old,a1):
    p=run/'build_results.json'
    rows=json.loads(p.read_text()) if p.exists() else []
    if len(rows)>len(schedule()):fail('Too many recorded BUILD rows')
    for index,r in enumerate(rows):
        rep,arm=schedule()[index]
        key=(r.get('rep'),r.get('arm'))
        kind,C,K,N,_,_=ARMS[arm]
        if key!=(rep,arm) or r.get('tag')!=f't4_r{rep}_{arm}' or \
           r.get('binary_sha256')!=m['binary_sha256'][kind] or \
           (r.get('capacity'),r.get('cluster_size'),r.get('num_clusters'))!=(C,K,N):
            fail('BUILD provenance/membership mismatch at row '+str(index))
        g=Path(r['graph'])
        if not g.is_file() or sha(g)!=r.get('graph_sha256'):
            fail('Graph SHA missing/changed '+str(g))
    return rows


def native(args,path,env):
    with Path(path).open('w',encoding='utf8') as f:
        f.write('# CMD '+shlex.join([str(x) for x in args])+'\n');f.flush()
        result=subprocess.run([str(x) for x in args],stdout=f,stderr=subprocess.STDOUT,
                              env=env,cwd=str(ROOT))
    output=Path(path).read_text(errors='replace')
    if result.returncode:fail(f'rc={result.returncode} see {path}; tail={output[-1500:]}')
    return output


def build(old,a1,a1c,run=None):
    check_environment()
    if run is None:
        OUT.mkdir(parents=True,exist_ok=True)
        run=OUT/('runs_'+dt.datetime.now().strftime('%Y%m%d-%H%M%S'))
        run.mkdir(exist_ok=False)
        atomic(run/'manifest.json',identity(old,a1,a1c,'build'))
    run,m=open_run(run,old,a1,a1c)
    rows=build_rows(run,m,old,a1)
    if (run/'quality').exists() or (run/'qps').exists():
        if len(rows)!=len(schedule()):fail('Refuse BUILD after QUALITY/QPS started')
    for index,(rep,arm) in enumerate(schedule()[len(rows):],len(rows)+1):
        tag=f't4_r{rep}_{arm}'
        graph=run/(tag+'.graph')
        if graph.exists():fail('Unrecorded graph exists; refuse overwrite '+str(graph))
        kind,C,K,N,select,reservoir=ARMS[arm]
        cmd=['taskset','-c',','.join(map(str,BUILD_CPUS)),
             '/usr/bin/time','-f','R85_A4_TIME wall_s=%e peak_rss_kib=%M',
             '-o',str(run/(tag+'.time'))]+cmd_build(old,a1,arm,graph)
        print(f'R85_A4_BUILD_START {index}/{len(schedule())} tag={tag} C={C} K={K} N={N}',flush=True)
        output=native(cmd,run/(tag+'.log'),dict(os.environ,PARLAY_NUM_THREADS='4',
                                               OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1'))
        for marker in ('R71_SELECTION_VARIANT='+select,'R70_RESERVOIR_VARIANT='+reservoir):
            if marker not in output:fail('Wrong native marker '+marker+' tag='+tag)
        times=(run/(tag+'.time')).read_text()
        match=TIME_RE.search(times)
        if not match:fail('Missing BUILD time '+tag)
        stats=old.check_graph(graph)
        row={'rep':rep,'arm':arm,'tag':tag,'capacity':C,'cluster_size':K,
             'num_clusters':N,'binary_sha256':m['binary_sha256'][kind],
             'wall_s':float(match.group(1)),'peak_rss_kib':int(match.group(2)),
             'graph':str(graph),**stats}
        rows.append(row)
        atomic(run/'build_results.json',rows)
        print(f'R85_A4_BUILD_PASS {tag} wall_s={row["wall_s"]:.3f} rss_kib={row["peak_rss_kib"]} arcs={row["arcs"]}',flush=True)
    table={}
    for arm in ARM_ORDER:
        subset=[x for x in rows if x['arm']==arm]
        table[arm]={'n':len(subset),'wall_s':list(x['wall_s'] for x in subset),
                    'rss_kib':list(x['peak_rss_kib'] for x in subset),
                    'arcs':list(x['arcs'] for x in subset),
                    'median_wall_s':median(x['wall_s'] for x in subset),
                    'median_rss_kib':median(x['peak_rss_kib'] for x in subset),
                    'median_arcs':median(x['arcs'] for x in subset)}
    atomic(run/'build_summary.json',table)
    print('R85_A4_ALL_18_BUILDS_PASS',flush=True)
    print('R85_A4_BUILD_SUMMARY '+json.dumps({a:{'wall':d['median_wall_s'],'rss':d['median_rss_kib'],
                                                   'arcs':d['median_arcs']} for a,d in table.items()}),flush=True)
    print('R85_A4_RESULTS_DIR '+str(run),flush=True)


def parsed(output,expected):
    rows=[]
    for beam,recall,qps,cmps,visited in ROW_RE.findall(output):
        row={'beam':int(beam),'recall':float(recall),'qps':float(qps),
             'avg_cmps':float(cmps),'avg_visited':float(visited)}
        if row['beam'] not in expected or not 0<=row['recall']<=1 or \
           not all(math.isfinite(row[k]) and row[k]>0 for k in ('qps','avg_cmps','avg_visited')):
            fail('Invalid evaluator output '+str(row))
        rows.append(row)
    if len(rows)!=len(expected) or [r['beam'] for r in rows]!=list(expected):
        fail('Evaluator beam count/order unexpected, expected '+str(expected))
    return rows


def require_complete_builds(run,m,old,a1):
    rows=build_rows(run,m,old,a1)
    if len(rows)!=len(schedule()) or not (run/'build_summary.json').is_file():
        fail('All 18 BUILDs required before SEARCH')
    return rows


def quality(old,a1,a1c,run):
    check_environment()
    run,m=open_run(run,old,a1,a1c)
    builds=require_complete_builds(run,m,old,a1)
    qdir=run/'quality'
    qdir.mkdir(exist_ok=True)
    for i,r in enumerate(builds,1):
        dest=qdir/(r['tag']+'.json')
        if dest.exists():
            z=json.loads(dest.read_text())
            if z.get('graph_sha256')!=r['graph_sha256'] or z.get('evaluator_sha256')!=m['evaluator_sha256'] or \
               [x['beam'] for x in z.get('rows',[])]!=list(a1c.BEAMS):
                fail('Saved QUALITY invalid '+r['tag'])
            print('R85_A4_QUALITY_SKIP_VERIFIED '+r['tag'],flush=True);continue
        print(f'R85_A4_QUALITY_START {i}/{len(builds)} {r["tag"]} beams={len(a1c.BEAMS)}',flush=True)
        cmd=['taskset','-c',','.join(map(str,BUILD_CPUS)),str(a1c.EVAL),
             r['graph'],str(old.DATA_FILES['base'][0]),str(old.DATA_FILES['query'][0]),
             str(old.DATA_FILES['gt'][0]),','.join(map(str,a1c.BEAMS))]
        output=native(cmd,qdir/(r['tag']+'.log'),dict(os.environ,PARLAY_NUM_THREADS='4',
                    OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1'))
        if 'R72_RECALL_EVAL_PASS' not in output or \
           'R85_A1C_DYNAMIC_BEAMS count='+str(len(a1c.BEAMS)) not in output:
            fail('QUALITY native markers missing '+r['tag'])
        rows=parsed(output,a1c.BEAMS)
        atomic(dest,{'tag':r['tag'],'arm':r['arm'],'rep':r['rep'],
                     'graph_sha256':r['graph_sha256'],
                     'evaluator_sha256':m['evaluator_sha256'],'rows':rows})
        print('R85_A4_QUALITY_PASS '+r['tag'],flush=True)
    print('R85_A4_ALL_18_QUALITY_PASS',flush=True)
    summarize(old,a1,a1c,run,require_qps=False)


def quality_rows(run,builds,m,a1c):
    qr={}
    for r in builds:
        file=run/'quality'/(r['tag']+'.json')
        if not file.exists():fail('QUALITY missing '+r['tag'])
        rec=json.loads(file.read_text())
        if rec.get('graph_sha256')!=r['graph_sha256'] or rec.get('evaluator_sha256')!=m['evaluator_sha256']:
            fail('QUALITY provenance mismatch '+r['tag'])
        rows=rec.get('rows',[])
        if [x['beam'] for x in rows]!=list(a1c.BEAMS):
            fail('QUALITY beams mismatch '+r['tag'])
        qr[(r['rep'],r['arm'])]=rows
    return qr


def interpolation(rows,target):
    # Exact same lower-envelope algorithm as the pinned R85-A3.1 runner.
    # Sorting by comparisons first avoids choosing non-Pareto points when
    # empirical Recall varies slightly non-monotonically across beam widths.
    points=sorted((float(r['avg_cmps']),float(r['recall']),int(r['beam']))
                  for r in rows)
    fr=[]
    best=-1.0
    for cmps,recall,beam in points:
        if recall>best+1e-10:
            fr.append((recall,cmps,beam));best=recall
    if not fr or target<fr[0][0]-1e-10 or target>fr[-1][0]+1e-10:
        return None
    for rec,cmps,beam in fr:
        if abs(rec-target)<=1e-10:return cmps
    for (rl,cl,_),(rh,ch,_) in zip(fr,fr[1:]):
        if rl<=target<=rh and rh>rl:
            return cl+(target-rl)/(rh-rl)*(ch-cl)
    return None


def measured_beam(rows,target):
    feasible=[r for r in rows if r['recall']+1e-10>=target]
    if not feasible:return None
    best=min(feasible,key=lambda r:(r['avg_cmps'],r['beam']))
    return best['beam']


def get_qps_records(run,builds,m):
    file=run/'qps'/'qps_results.json'
    return json.loads(file.read_text()) if file.exists() else []


def qps(old,a1,a1c,run):
    check_environment()
    run,m=open_run(run,old,a1,a1c)
    builds=require_complete_builds(run,m,old,a1)
    quality_by_key=quality_rows(run,builds,m,a1c)
    by_key={(r['rep'],r['arm']):r for r in builds}
    qdir=run/'qps';qdir.mkdir(exist_ok=True)
    previous=get_qps_records(run,builds,m)
    plan=[(repeat,rep,arm) for repeat,group in qps_schedule() for rep,arm in group]
    if len(previous)>len(plan):fail('QPS records exceed schedule')
    for i,record in enumerate(previous):
        repeat,rep,arm=plan[i]
        r=by_key[rep,arm]
        if (record.get('repeat'),record.get('rep'),record.get('arm'))!=(repeat,rep,arm) or \
           record.get('graph_sha256')!=r['graph_sha256'] or \
           record.get('evaluator_sha256')!=m['evaluator_sha256'] or \
           record.get('qps_cpu')!=QPS_CPU:
            fail('QPS saved record provenance wrong at position '+str(i))
    for i,(repeat,rep,arm) in enumerate(plan[len(previous):],len(previous)+1):
        r=by_key[rep,arm]
        rows=quality_by_key[rep,arm]
        chosen={str(target):measured_beam(rows,target) for target in TARGETS}
        beams=tuple(sorted({b for b in chosen.values() if b is not None}))
        if not beams:
            fail('No target reachable by measured beam in '+r['tag'])
        cmd=['taskset','-c',str(QPS_CPU),str(a1c.EVAL),
             r['graph'],str(old.DATA_FILES['base'][0]),str(old.DATA_FILES['query'][0]),
             str(old.DATA_FILES['gt'][0]),','.join(map(str,beams))]
        env=dict(os.environ,PARLAY_NUM_THREADS='1',OMP_NUM_THREADS='1',
                 OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='1',VECLIB_MAXIMUM_THREADS='1')
        tag=f'pass{repeat}_r{rep}_{arm}'
        print(f'R85_A4_QPS_START {i}/{len(plan)} {tag} beams={beams}',flush=True)
        out=native(cmd,qdir/(tag+'.log'),env)
        if 'R72_RECALL_EVAL_PASS' not in out or \
           'R85_A1C_DYNAMIC_BEAMS count='+str(len(beams)) not in out:
            fail('Native QPS marker missing '+tag)
        actual=parsed(out,beams)
        original={row['beam']:row for row in rows}
        for x in actual:
            y=original[x['beam']]
            if abs(x['recall']-y['recall'])>0.0001 or abs(x['avg_cmps']-y['avg_cmps'])>2:
                fail('QPS recall/comparisons drift against QUALITY at '+tag)
        record={'repeat':repeat,'rep':rep,'arm':arm,'tag':r['tag'],
                'graph_sha256':r['graph_sha256'],
                'evaluator_sha256':m['evaluator_sha256'],'qps_cpu':QPS_CPU,
                'target_beam':chosen,'rows':actual}
        previous.append(record)
        atomic(qdir/'qps_results.json',previous)
        print('R85_A4_QPS_PASS '+tag,flush=True)
    print(f'R85_A4_ALL_{len(plan)}_QPS_GRAPH_PASSES_PASS',flush=True)
    summarize(old,a1,a1c,run,require_qps=True)


def summarize(old,a1,a1c,run,require_qps=False):
    run,m=open_run(run,old,a1,a1c)
    builds=require_complete_builds(run,m,old,a1)
    qualities=quality_rows(run,builds,m,a1c)
    build_summary=json.loads((run/'build_summary.json').read_text())
    rows=[]
    for t in TARGETS:
        r={'target':t,'arms':{}}
        for arm in ARM_ORDER:
            vals=[interpolation(qualities[rep,arm],t) for rep in range(1,REPS+1)]
            valid=[v for v in vals if v is not None]
            r['arms'][arm]={'coverage':f'{len(valid)}/{REPS}',
                            'median_interpolated_cmps':median(valid) if valid else None,
                            'per_rep_cmps':vals}
        rows.append(r)
    atomic(run/'matched_recall_interpolation.json',rows)
    qfile=run/'qps'/'qps_results.json'
    qrecords=get_qps_records(run,builds,m) if qfile.exists() else []
    summary={'build':build_summary,'matched_recall':rows,
        'qps_protocol':'single P-core, PARLAY_NUM_THREADS=1, 5 temporal repeats/graph; beams are smallest measured-comparisons feasible recall; QPS not equal to interpolated comparisons',
        'qps':{},'qps_completed_graph_passes':len(qrecords),
        'qps_expected_graph_passes':REPS*len(ARM_ORDER)*QPS_REPS}
    for t in TARGETS:
        summary['qps'][str(t)]={}
        for arm in ARM_ORDER:
            vals=[]; recalls=[];beams=[]
            for record in qrecords:
                if record['arm']!=arm:continue
                beam=record['target_beam'][str(t)]
                if beam is None:continue
                matched=[x for x in record['rows'] if x['beam']==beam]
                if len(matched)!=1:fail('QPS target missing row')
                vals.append(matched[0]['qps']);recalls.append(matched[0]['recall']);beams.append(beam)
            summary['qps'][str(t)][arm]={
                'qps_n':len(vals),'qps_median':median(vals) if vals else None,
                'qps_min':min(vals) if vals else None,'qps_max':max(vals) if vals else None,
                'recall_min':min(recalls) if recalls else None,
                'recall_max':max(recalls) if recalls else None,
                'beams':beams}
    atomic(run/'summary.json',summary)
    print('R85_A4_INTERPOLATED_MATCHED_RECALL_SUMMARY '+str(run/'matched_recall_interpolation.json'),flush=True)
    print('R85_A4_QPS_REPEATS_DONE '+str(len(qrecords)),flush=True)
    print('R85_A4_RESULTS_DIR '+str(run),flush=True)
    if require_qps and len(qrecords)!=summary['qps_expected_graph_passes']:
        fail('QPS incomplete')


def selftest():
    assert len(ARMS)==6 and len(schedule())==18
    assert len({(r,a) for r,a in schedule()})==18
    assert all(sum(1 for r,a in schedule() if a==arm)==3 for arm in ARM_ORDER)
    assert len(list(qps_schedule()))==QPS_REPS
    for rep,seq in qps_schedule():
        assert len(seq)==18 and set(seq)==set(schedule())
    class Old:
        BINARIES={'A':Path('/stock'),'D0':Path('/d0')}
        def build_cmd(self,arm,threads,path):
            assert (arm,threads)==('D0',4)
            return ['/tmp/bin','-graph_outfile',str(path),'-table_size','160',
                    '-cluster_size','1024','-num_clusters','2','-prune_degree','64',
                    '-alpha','1.1','-mst_deg','2','-prune','1','-prune_all','1','-hash_bits','12']
    class A1:H17_EXE=Path('/h17')
    for arm,(_,C,K,N,*_) in ARMS.items():
        c=cmd_build(Old(),A1(),arm,Path('/graph'))
        assert c[c.index('-table_size')+1]==str(C)
        assert c[c.index('-cluster_size')+1]==str(K)
        assert c[c.index('-num_clusters')+1]==str(N)
    assert abs(interpolation([{'recall':.8,'avg_cmps':100,'beam':10},
                               {'recall':.9,'avg_cmps':200,'beam':20}],.85)-150)<1e-6
    assert measured_beam([{'recall':.8,'avg_cmps':100,'beam':10},
                         {'recall':.9,'avg_cmps':200,'beam':20}],.82)==20
    assert interpolation([{'recall':.8,'avg_cmps':100,'beam':10},
                          {'recall':.9,'avg_cmps':200,'beam':20}],.75) is None
    print('R85_A4_SELFTEST_PASS',flush=True)


def main():
    p=argparse.ArgumentParser(description=__doc__,formatter_class=argparse.RawDescriptionHelpFormatter)
    g=p.add_mutually_exclusive_group(required=True)
    g.add_argument('--selftest',action='store_true')
    g.add_argument('--dry-run',action='store_true')
    g.add_argument('--run-build',action='store_true')
    g.add_argument('--resume-build',type=Path,metavar='RUN')
    g.add_argument('--run-quality',type=Path,metavar='RUN')
    g.add_argument('--run-qps',type=Path,metavar='RUN')
    g.add_argument('--summarize',type=Path,metavar='RUN')
    args=p.parse_args()
    if args.selftest:return selftest()
    old,a1,a1c,_,_,_=dep(require_eval=True)
    check_environment()
    if args.dry_run:
        for i,(rep,arm) in enumerate(schedule(),1):
            cmd=['taskset','-c',','.join(map(str,BUILD_CPUS)),
                 'env','PARLAY_NUM_THREADS=4']+cmd_build(old,a1,arm,
                    Path(f'<new_run>/t4_r{rep}_{arm}.graph'))
            print(f'R85_A4_DRY_RUN {i}/18 '+shlex.join(cmd),flush=True)
        print('R85_A4_DRY_RUN_PASS_NO_BUILD_NO_SEARCH',flush=True);return
    if args.run_build:return build(old,a1,a1c)
    if args.resume_build:return build(old,a1,a1c,args.resume_build)
    if args.run_quality:return quality(old,a1,a1c,args.run_quality)
    if args.run_qps:return qps(old,a1,a1c,args.run_qps)
    if args.summarize:return summarize(old,a1,a1c,args.summarize)

if __name__=='__main__':
    try:main()
    except (OSError,RuntimeError,ValueError,KeyError,AssertionError,TypeError,IndexError,ZeroDivisionError) as e:
        print('R85_A4_FAIL_CLOSED '+repr(e),file=sys.stderr)
        sys.exit(1)
