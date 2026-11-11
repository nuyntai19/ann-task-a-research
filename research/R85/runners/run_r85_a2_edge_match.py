#!/usr/bin/env python3
"""R85-A2: H17 flat C160 with matched-edges final-prune controls.

Modes:
  --selftest               pure Python protocol self test
  --prepare                compile an isolated dynamic-beam native recall evaluator
  --inspect                read-only graph degree distribution / predicted R selection
  --calibrate              one-build pilots to match B64 edge count with R and alpha
  --dry-run                print planned 9 BUILD commands (after calibration)
  --run-build              3 reps each: B64, C160/R*, C160/alpha*
  --run-quality RUN_DIR    run native 25-beam recall for all 9 saved graphs

All results live in experiments/H85/r85_a2_edge_match. The pinned H17-only
binary and prior H85 scripts are reused. H70-H84 and R85-A1/A1c are untouched.
"""
from __future__ import annotations

import argparse
import array
import datetime as dt
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import shlex
import struct
import subprocess
import sys
import time
from statistics import median

ROOT = Path.home() / 'ann-task-a'
DL = Path.home() / 'Downloads'
OUT = ROOT / 'experiments/H85/r85_a2_edge_match'
A1_RUN = ROOT / 'experiments/H85/r85_a1_capacity_ablation/runs_20261109-215545'
A1_SCRIPT = DL / 'run_r85_a1_capacity_ablation.py'
A1_SHA = '843cacaffb0c16d0ab8f86a32546ca74cc3b4c59d47ac3fd724e5fffc2accdb9'
A1C_SCRIPT = DL / 'run_r85_a1c_matched_search.py'
A1C_SHA = 'a61c32764d4624800f8bbc8c7de62e9c2938ab7da5ab89adaef35f9c90d2c778'
EVAL_CPP = OUT / 'r85_a2_dynamic_recall.cc'
EVAL_OBJ = OUT / 'r85_a2_dynamic_recall.o'
EVAL_BIN = OUT / 'r85_a2_dynamic_recall'
EVAL_MANIFEST = OUT / 'evaluator_manifest.json'
SEL = OUT / 'calibration_selection.json'
CALIB = OUT / 'calibration'
ARMS = ('B64', 'EDGE_R', 'EDGE_ALPHA')
CPUS = (0, 2, 4, 6)
TOLERANCE = 0.01  # +/-1% total graph arcs in calibration; NOT proof of topology equivalence
T_PATTERN = re.compile(r'R85A2_TIME wall_s=([0-9.]+) peak_rss_kib=(\d+)')
Q_PATTERN = re.compile(r'R72_RECALL_ROW beam=(\d+) recall=([0-9.Ee+-]+) qps=([0-9.Ee+-]+) avg_cmps=([0-9.Ee+-]+) avg_visited=([0-9.Ee+-]+)')


def fail(msg):
    raise RuntimeError('R85_A2_FAIL_CLOSED ' + msg)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def jwrite(p, data):
    p = Path(p)
    tmp = p.with_name(p.name + '.tmp')
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + '\n', encoding='utf8')
    tmp.replace(p)


def load_module(path, name, pin):
    if not path.is_file() or sha(path) != pin:
        fail('Missing/changed pinned script ' + str(path))
    spec = importlib.util.spec_from_file_location(name, path)
    if not spec or not spec.loader:
        fail('Cannot load ' + str(path))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def pin_inputs(require_eval=False):
    a1 = load_module(A1_SCRIPT, 'r85_a1_pin', A1_SHA)
    old = a1.load_pinned_previous()
    old.check_inputs()
    a1.verify_b_manifest()
    a1.audit_h17_compiler()
    a1c = load_module(A1C_SCRIPT, 'r85_a1c_pin', A1C_SHA)
    a1c.check_evaluator()
    builds_p = A1_RUN / 'build_results.json'
    quality_p = A1_RUN / 'quality/quality_results.json'
    if not builds_p.is_file() or not quality_p.is_file():
        fail('R85-A1 graph or quality manifest missing')
    builds = json.loads(builds_p.read_text())
    qualities = json.loads(quality_p.read_text())
    if len(builds) != 9 or len(qualities) != 45:
        fail('Unexpected original R85-A1 result count')
    bykey = {}
    for b in builds:
        key = (b['arm'], b['rep'])
        if key in bykey:
            fail('Duplicate original R85-A1 graph')
        bykey[key] = b
    if set(bykey) != {(arm, rep) for arm in ('B64','B160','D0') for rep in (1,2,3)}:
        fail('Missing original R85-A1 arm/rep')
    if len({(q['arm'],q['rep'],q['beam']) for q in qualities}) != 45:
        fail('Duplicated original R85-A1 search results')
    for b in builds:
        p = Path(b['graph'])
        if not p.is_file() or sha(p) != b['graph_sha256']:
            fail('Pinned original graph mismatch: ' + str(p))
    if require_eval:
        pin_evaluator(a1c)
    return old, a1, a1c, builds


def time_run(cmd, log, env=None):
    log = Path(log)
    with log.open('w', encoding='utf8') as f:
        f.write('# COMMAND ' + shlex.join(map(str,cmd)) + '\n')
        f.flush()
        proc = subprocess.run([str(x) for x in cmd], cwd=str(ROOT), env=env,
                              stdout=f, stderr=subprocess.STDOUT)
    if proc.returncode:
        fail(f'Command rc={proc.returncode}; inspect {log}')
    return log.read_text(encoding='utf8', errors='replace')


def native_graph_info(graph, expected_degree=None, read_degrees=False):
    # Graph save layout: [n:u32, maxdegree:u32][n * u32 degrees][sum(degrees) * u32 IDs]
    graph = Path(graph)
    with graph.open('rb') as f:
        header = f.read(8)
        if len(header) != 8:
            fail('Truncated graph header')
        n, maxdeg = struct.unpack('<II', header)
        if n != 1000000 or not 1 <= maxdeg <= 64:
            fail(f'Graph n/max_degree invalid: {n}/{maxdeg}')
        if expected_degree is not None and maxdeg != expected_degree:
            fail(f'Wrong maxdegree: expected={expected_degree} got={maxdeg}')
        degrees = array.array('I')
        degrees.fromfile(f, n)
        if sys.byteorder != 'little':
            degrees.byteswap()
        if any(d > maxdeg for d in degrees):
            fail('A degree exceeds graph maxdegree')
        arcs = sum(degrees)
        if not 1000000 <= arcs <= n*maxdeg:
            fail('Graph arc count outside safe bounds')
        if graph.stat().st_size != 8 + 4*n + 4*arcs:
            fail('Graph file length mismatch')
        edges = array.array('I')
        edges.fromfile(f, arcs)
        if sys.byteorder != 'little':
            edges.byteswap()
        if edges and max(edges) >= n:
            fail('Edge destination outside dataset')
    result = {'nodes': n, 'degree_bound': maxdeg, 'arcs': arcs,
              'bytes': graph.stat().st_size, 'graph_sha256': sha(graph)}
    if read_degrees:
        histogram = [0]*(maxdeg+1)
        for d in degrees:
            histogram[d] += 1
        result['degree_histogram'] = histogram
        result['zero_degree_nodes'] = histogram[0]
    return result


def reference(old, builds):
    b64 = [r for r in builds if r['arm'] == 'B64']
    b160 = [r for r in builds if r['arm'] == 'B160']
    return {'target_arcs': median(r['arcs'] for r in b64),
            'B160_arcs': median(r['arcs'] for r in b160),
            'source': str(A1_RUN),
            'original_graph_shas': {r['tag']: r['graph_sha256'] for r in builds}}


def predicted_r(old, builds, target):
    b = next(b for b in builds if b['arm'] == 'B160' and b['rep'] == 1)
    graph = native_graph_info(Path(b['graph']), expected_degree=64, read_degrees=True)
    hist = graph['degree_histogram']
    estimates = [(r, sum(min(k,r)*v for k,v in enumerate(hist))) for r in range(16,65)]
    best = min(estimates, key=lambda x: (abs(x[1]-target), x[0]))
    return best, estimates


def prepare(old, a1c):
    pin_inputs()
    OUT.mkdir(parents=True, exist_ok=True)
    if EVAL_MANIFEST.exists():
        pin_evaluator(a1c)
        print('R85_A2_EVALUATOR_ALREADY_PREPARED sha256='+sha(EVAL_BIN), flush=True)
        return
    if any(p.exists() for p in (EVAL_CPP, EVAL_OBJ, EVAL_BIN)):
        fail('Partial evaluator artifacts already present; refuse overwrite')
    # Only change from pinned A1c evaluator: accept graph.max_degree 1..64.
    # Its native checkRecall() and QueryParams still use actual graph.max_degree().
    src = a1c.CPP.read_text(encoding='utf8')
    needle = 'graph.max_degree() != 64'
    if src.count(needle) != 1:
        fail('Unexpected original max_degree guard; cannot patch safely')
    patched = src.replace(needle, '(graph.max_degree() < 1 || graph.max_degree() > 64)', 1)
    EVAL_CPP.write_text(patched, encoding='utf8')
    # Reuse the exact original compiler + linker command, substitute isolated outputs.
    a1c.NEW, a1c.CPP, a1c.OBJECT, a1c.EVAL = OUT, EVAL_CPP, EVAL_OBJ, EVAL_BIN
    print('R85_A2_EVALUATOR_COMPILE_START', flush=True)
    cmds = a1c.compile_eval()
    manifest = {'parent_a1c_sha256': A1C_SHA,
                'parent_a1c_evaluator_sha256': sha(ROOT / 'experiments/H85/r85_a1c_matched_search/r85_a1c_graph_recall'),
                'cpp_sha256': sha(EVAL_CPP), 'evaluator_sha256': sha(EVAL_BIN),
                'changed_guard': 'max_degree ==64 -> 1..64',
                'beam_list': list(a1c.BEAMS),
                'compiler_command': cmds['compiler_command'],
                'linker_command': cmds['linker_command']}
    jwrite(EVAL_MANIFEST, manifest)
    print('R85_A2_EVALUATOR_PREPARED sha256='+manifest['evaluator_sha256'], flush=True)


def pin_evaluator(a1c):
    if not all(p.is_file() for p in (EVAL_CPP,EVAL_BIN,EVAL_MANIFEST)):
        fail('A2 native evaluator missing: run --prepare')
    m = json.loads(EVAL_MANIFEST.read_text())
    if sha(EVAL_CPP) != m['cpp_sha256'] or sha(EVAL_BIN) != m['evaluator_sha256']:
        fail('A2 native evaluator/source SHA mismatch')
    if m['beam_list'] != list(a1c.BEAMS):
        fail('A2 beam protocol changed')
    return m


def build_params(old, a1, arm, graph, sel):
    exe = a1.H17_EXE
    cmd = old.build_cmd('D0', 4, graph)
    cmd[0] = str(exe)
    def replace(flag, value):
        cmd[cmd.index(flag)+1] = str(value)
    if arm == 'B64':
        cap, R, alpha = 64, 64, 1.1
    elif arm == 'EDGE_R':
        cap, R, alpha = 160, sel['R']['value'], 1.1
    elif arm == 'EDGE_ALPHA':
        cap, R, alpha = 160, 64, sel['alpha']['value']
    else:
        fail('Unknown arm '+str(arm))
    replace('-table_size', cap)
    replace('-prune_degree', R)
    replace('-alpha', alpha)
    return cmd, {'C': cap, 'R': R, 'alpha': alpha, 'expected_maxdegree': R}


def run_one(old, a1, label, arm, graph, log, tlog, sel):
    cmd, conf = build_params(old, a1, arm, graph, sel)
    timed_cmd = ['taskset', '-c', ','.join(map(str,CPUS)), '/usr/bin/time',
                 '-f', 'R85A2_TIME wall_s=%e peak_rss_kib=%M', '-o', str(tlog)] + cmd
    env = dict(os.environ, PARLAY_NUM_THREADS='4')
    start = time.perf_counter()
    txt = time_run(timed_cmd, log, env=env)
    elapsed_host = time.perf_counter()-start
    if 'R71_SELECTION_VARIANT=H17_PACKED_TOP2' not in txt:
        fail('Missing H17 marker in '+str(log))
    if f"R70_RESERVOIR_VARIANT=STOCK_FLAT_C{conf['C']}" not in txt:
        fail('Missing Flat C provenance marker in '+str(log))
    match = T_PATTERN.search(Path(tlog).read_text())
    if not match:
        fail('Missing /usr/bin/time metrics '+str(tlog))
    graph_stats = native_graph_info(graph, expected_degree=conf['expected_maxdegree'], read_degrees=True)
    return {'tag':label,'arm':arm,'wall_s':float(match[1]),
            'peak_rss_kib':int(match[2]),'host_wall_s':round(elapsed_host,3),
            'graph':str(graph),'log':str(log),'time_log':str(tlog),
            'binary_sha256':sha(a1.H17_EXE),**conf,**graph_stats}


def calibrate(old, a1, builds):
    OUT.mkdir(parents=True,exist_ok=True)
    if CALIB.exists() or SEL.exists():
        fail('Calibration exists; refuse overwrite: '+str(CALIB))
    CALIB.mkdir()
    ref = reference(old, builds)
    target = ref['target_arcs']
    pred, estimates = predicted_r(old, builds, target)
    jwrite(CALIB/'reference.json', {'reference':ref,'initial_r_prediction':pred,
                                    'predicted_r_arcs':estimates,'tolerance':TOLERANCE})
    print(f'R85_A2_CALIBRATE_TARGET B64_median_arcs={target} predicted_R={pred[0]}', flush=True)
    runs=[]
    def pilot(arm, value):
        tag=f'{arm}_{str(value).replace(".","p")}'
        g=CALIB/(tag+'.graph')
        if g.exists():
            fail('Pilot output collision '+str(g))
        s={'R':{'value':int(value) if arm=='EDGE_R' else 64},
           'alpha':{'value':float(value) if arm=='EDGE_ALPHA' else 1.1}}
        print(f'R85_A2_CALIBRATION_START arm={arm} value={value}',flush=True)
        row=run_one(old,a1,tag,arm,g,CALIB/(tag+'.log'),CALIB/(tag+'.time'),s)
        row['edge_delta_pct']=100*(row['arcs']/target-1)
        runs.append(row)
        jwrite(CALIB/'pilots.json',runs)
        print(f"R85_A2_CALIBRATION_PASS arm={arm} value={value} arcs={row['arcs']} edge_delta_pct={row['edge_delta_pct']:+.3f}", flush=True)
        return row
    # R search: one prediction from actual B160 degree histogram; probe neighbors only as needed.
    chosen_r=None
    r0=pred[0]
    candidates=[r0]+[r0+d for d in (-1,1,-2,2,-3,3) if 16<=r0+d<=63]
    for r in dict.fromkeys(candidates):
        row=pilot('EDGE_R',r)
        if chosen_r is None or abs(row['edge_delta_pct'])<abs(chosen_r['edge_delta_pct']):
            chosen_r=row
        if abs(row['edge_delta_pct'])<=100*TOLERANCE:
            break
    # alpha monotonic in this pinned RobustPrune implementation, but measure it.
    # alpha=1.1 was measured in A1 B160 at ~26m edges; alpha=1.0 is maximal pruning.
    chosen_alpha=pilot('EDGE_ALPHA',1.0)
    if chosen_alpha['arcs'] <= target and abs(chosen_alpha['edge_delta_pct'])>100*TOLERANCE:
        lo,hi=1.0,1.1
        for i in range(7):
            m=round((lo+hi)/2,6)
            row=pilot('EDGE_ALPHA',m)
            if abs(row['edge_delta_pct'])<abs(chosen_alpha['edge_delta_pct']):
                chosen_alpha=row
            if abs(row['edge_delta_pct'])<=100*TOLERANCE:
                break
            if row['arcs']<target:
                lo=m
            else:
                hi=m
    report={'target_arcs':target,'tolerance':TOLERANCE,
            'R':{'value':int(chosen_r['R']),'arcs':chosen_r['arcs'],
                 'edge_delta_pct':chosen_r['edge_delta_pct'],'pilot_tag':chosen_r['tag']},
            'alpha':{'value':chosen_alpha['alpha'],'arcs':chosen_alpha['arcs'],
                     'edge_delta_pct':chosen_alpha['edge_delta_pct'],'pilot_tag':chosen_alpha['tag']},
            'source':str(A1_RUN), 'calibration_pilot_count':len(runs),
            'status':'READY' if all(abs(row['edge_delta_pct']) <= 100*TOLERANCE for row in (chosen_r,chosen_alpha)) else 'CANNOT_MATCH_WITH_TESTED_RANGE'}
    jwrite(CALIB/'calibration_summary.json',report)
    print('R85_A2_CALIBRATION_SUMMARY '+json.dumps(report,ensure_ascii=False),flush=True)
    if report['status']!='READY':
        print('R85_A2_CALIBRATION_NOT_MATCHED_DO_NOT_CLAIM_CAUSAL_EFFECT',flush=True)
        return
    jwrite(SEL,report)
    print('R85_A2_EDGE_COUNT_CALIBRATION_PASS '+str(SEL),flush=True)


def selection():
    if not SEL.is_file():
        fail('Missing successful calibration. Run --calibrate before BUILD')
    s=json.loads(SEL.read_text())
    if s['status']!='READY' or any(abs(s[x]['edge_delta_pct'])>100*TOLERANCE for x in ('R','alpha')):
        fail('Calibration was not successful')
    if not 16 <= s['R']['value'] <= 63 or not 1.0 <= s['alpha']['value'] <= 1.1:
        fail('Selected parameters are out of bounds')
    return s


def schedule():
    orders=(('B64','EDGE_R','EDGE_ALPHA'),
            ('EDGE_R','EDGE_ALPHA','B64'),
            ('EDGE_ALPHA','B64','EDGE_R'))
    return [(rep, arm) for rep,order in enumerate(orders,1) for arm in order]


def build(old,a1,sel):
    stamp=dt.datetime.now().strftime('%Y%m%d-%H%M%S')
    out=OUT/('runs_'+stamp)
    out.mkdir(parents=True,exist_ok=False)
    jwrite(out/'manifest.json',{'selection':sel,'schedule':schedule(),
                               'H17_sha256':sha(a1.H17_EXE),'run_started_utc':dt.datetime.now(dt.timezone.utc).isoformat(),
                               'source_a1':str(A1_RUN),'note':'R and alpha controls each calibrated to B64 edge count in separate single-run pilots'})
    rows=[]
    for i,(rep,arm) in enumerate(schedule(),1):
        tag=f't4_r{rep}_{arm}'
        print(f'R85_A2_BUILD_START {i}/9 tag={tag}',flush=True)
        row=run_one(old,a1,tag,arm,out/(tag+'.graph'),out/(tag+'.log'),out/(tag+'.time'),sel)
        row['rep']=rep
        rows.append(row)
        jwrite(out/'build_results.json',rows)
        print(f"R85_A2_BUILD_PASS tag={tag} wall_s={row['wall_s']:.2f} rss_kib={row['peak_rss_kib']} arcs={row['arcs']}",flush=True)
    summary={}
    for arm in ARMS:
        part=[r for r in rows if r['arm']==arm]
        summary[arm]={k:median(r[k] for r in part) for k in ('wall_s','peak_rss_kib','arcs')}
        summary[arm]['all_arcs']=[r['arcs'] for r in part]
    target=summary['B64']['arcs']
    # Equal total arc counts do NOT imply equal degree distributions.
    def median_hist(arm):
        parts=[r for r in rows if r['arm']==arm]
        return [median(x['degree_histogram'][i] if i<len(x['degree_histogram']) else 0
                       for x in parts) for i in range(65)]
    b64_hist=median_hist('B64')
    for arm in ('EDGE_R','EDGE_ALPHA'):
        arm_hist=median_hist(arm)
        summary[arm]['degree_distribution_tv_vs_B64']=0.5*sum(
            abs(a-b) for a,b in zip(arm_hist,b64_hist))/1000000
        summary[arm]['delta_arcs_pct_vs_B64']=100*(summary[arm]['arcs']/target-1)
        summary[arm]['matched_edges_within_1pct']=abs(summary[arm]['delta_arcs_pct_vs_B64'])<=100*TOLERANCE
    summary['status']='EDGE_MATCHED_PENDING_RECALL' if all(summary[a]['matched_edges_within_1pct'] for a in ('EDGE_R','EDGE_ALPHA')) else 'EDGE_MATCH_FAILED_INTERPRET_AS_UNMATCHED_CONTROLS'
    jwrite(out/'build_summary.json',summary)
    print('R85_A2_ALL_9_BUILDS_AND_GRAPH_SCREENS_PASS',flush=True)
    print('R85_A2_BUILD_SUMMARY '+json.dumps(summary),flush=True)
    print('R85_A2_RESULTS_DIR '+str(out),flush=True)


def quality(old,a1,a1c,run):
    if run.resolve().parent!=OUT.resolve():
        fail('Quality run must be a direct child of H85/r85_a2_edge_match')
    summary_p=run/'build_summary.json'
    result_p=run/'build_results.json'
    manifest_p=run/'manifest.json'
    if not all(p.is_file() for p in (summary_p,result_p,manifest_p)):
        fail('Missing A2 BUILD artifacts')
    rows=json.loads(result_p.read_text())
    if len(rows)!=9 or [(r['rep'],r['arm']) for r in rows]!=schedule():
        fail('Invalid run build schedule')
    for r in rows:
        if r['binary_sha256']!=sha(a1.H17_EXE) or sha(Path(r['graph']))!=r['graph_sha256']:
            fail('A2 graph or binary changed: '+r['tag'])
        native_graph_info(Path(r['graph']),expected_degree=r['R'])
    qdir=run/'quality'
    if qdir.exists():
        fail('Quality folder already exists, no overwrite')
    qdir.mkdir()
    data=[]
    csv_beams=','.join(map(str,a1c.BEAMS))
    for i,r in enumerate(rows,1):
        cmd=['taskset','-c',','.join(map(str,CPUS)),str(EVAL_BIN),
             r['graph'],str(old.DATA_FILES['base'][0]),str(old.DATA_FILES['query'][0]),
             str(old.DATA_FILES['gt'][0]),csv_beams]
        log=qdir/(r['tag']+'.log')
        print(f"R85_A2_QUALITY_START {i}/9 {r['tag']} beams={len(a1c.BEAMS)}",flush=True)
        txt=time_run(cmd,log,env=dict(os.environ,PARLAY_NUM_THREADS='4'))
        if 'R72_RECALL_INPUT_PASS' not in txt or 'R72_RECALL_EVAL_PASS' not in txt or \
           f'R85_A1C_DYNAMIC_BEAMS count={len(a1c.BEAMS)}' not in txt:
            fail('Native quality marker missing '+str(log))
        matches=Q_PATTERN.findall(txt)
        if len(matches)!=len(a1c.BEAMS) or {int(m[0]) for m in matches}!=set(a1c.BEAMS):
            fail('Wrong quality beam count '+str(log))
        for beam,rec,qps,cmps,visited in matches:
            d={'tag':r['tag'],'arm':r['arm'],'rep':r['rep'],'beam':int(beam),
               'recall':float(rec),'qps':float(qps),'avg_cmps':float(cmps),'avg_visited':float(visited)}
            if not 0<=d['recall']<=1 or not all(math.isfinite(d[k]) and d[k]>0 for k in ('qps','avg_cmps','avg_visited')):
                fail('Non-finite metric '+str(d))
            data.append(d)
        jwrite(qdir/'quality_results.json',data)
        print('R85_A2_QUALITY_PASS '+r['tag'],flush=True)
    med=[]
    for beam in a1c.BEAMS:
        b={'beam':beam}
        for arm in ARMS:
            x=[q for q in data if q['arm']==arm and q['beam']==beam]
            if len(x)!=3:
                fail('Quality missing arm/beam '+arm+str(beam))
            for key in ('recall','qps','avg_cmps','avg_visited'):
                b[arm+'_'+key]=median(z[key] for z in x)
        med.append(b)
    jwrite(qdir/'curves_median.json',med)
    targets=[]
    for target_beam in (10,20,40,80,160):
        target_row=next(x for x in med if x['beam']==target_beam)
        target_rec=target_row['B64_recall']
        target_cmps=target_row['B64_avg_cmps']
        item={'B64_beam':target_beam,'B64_recall':target_rec,'B64_cmps':target_cmps}
        for arm in ('EDGE_R','EDGE_ALPHA'):
            passing=[x for x in med if x[arm+'_recall']>=target_rec]
            if not passing:
                item[arm]={'status':'NOT_REACHED_IN_MEASURED_BEAMS'}
            else:
                v=min(passing,key=lambda x:(x[arm+'_avg_cmps'],x['beam']))
                item[arm]={'status':'RECALL_AT_LEAST_TARGET','beam':v['beam'],
                           'recall':v[arm+'_recall'],'avg_cmps':v[arm+'_avg_cmps'],
                           'comparisons_ratio_vs_B64':v[arm+'_avg_cmps']/target_cmps,
                           'excess_recall_pp':100*(v[arm+'_recall']-target_rec)}
        targets.append(item)
    jwrite(qdir/'matched_recall.json',targets)
    jwrite(qdir/'manifest.json',{'source_build_run':str(run),'dynamic_evaluator_sha256':sha(EVAL_BIN),
                                'beams':list(a1c.BEAMS),'comparison':'median across three separately built graphs',
                                'note':'Matched TOTAL arcs does not match degree distributions, adjacency, or isolate causality'})
    print('R85_A2_ALL_9_SEARCHES_PASS',flush=True)
    for item in targets:
        print('R85_A2_MATCHED_RECALL_ROW '+json.dumps(item),flush=True)
    print('R85_A2_QUALITY_RESULTS '+str(qdir/'matched_recall.json'),flush=True)


def inspect(old,builds):
    ref=reference(old,builds)
    target=ref['target_arcs']
    prediction, estimates=predicted_r(old,builds,target)
    print('R85_A2_EDGE_REFERENCE '+json.dumps({'target_B64_median_arcs':target,
          'B160_median_arcs':ref['B160_arcs'],'prediction_R':prediction,
          'neighbors':sorted(estimates,key=lambda x:abs(x[1]-target))[:7]}),flush=True)
    print('R85_A2_INSPECT_READ_ONLY_PASS')


def selftest():
    assert len(schedule())==9
    assert all(sorted(x for rep,x in schedule() if rep==r)==sorted(ARMS) for r in (1,2,3))
    # Mocked monotone degree-clip target, no external files required.
    hist=[0]*65
    hist[20]=2;hist[40]=3;hist[64]=5
    sums=[sum(min(i,r)*v for i,v in enumerate(hist)) for r in (16,32,48,64)]
    assert sums==sorted(sums) and sums[-1]==480
    assert 0.7637 <= 0.7722
    print('R85_A2_SELFTEST_PASS')


def main():
    p=argparse.ArgumentParser(description=__doc__,formatter_class=argparse.RawDescriptionHelpFormatter)
    g=p.add_mutually_exclusive_group(required=True)
    for x in ('selftest','prepare','inspect','calibrate','dry-run','run-build'):
        g.add_argument('--'+x,action='store_true')
    g.add_argument('--run-quality',type=Path,metavar='R85_A2_RUN_DIR')
    args=p.parse_args()
    if args.selftest:
        selftest();return
    old,a1,a1c,builds=pin_inputs(require_eval=args.calibrate or args.dry_run or args.run_build or args.run_quality is not None)
    if args.prepare:
        prepare(old,a1c);return
    if args.inspect:
        inspect(old,builds);return
    if args.calibrate:
        calibrate(old,a1,builds);return
    sel=selection()
    if args.dry_run:
        print('R85_A2_SELECTION '+json.dumps(sel,ensure_ascii=False))
        for i,(rep,arm) in enumerate(schedule(),1):
            cmd,conf=build_params(old,a1,arm,Path(f'<new_run>/t4_r{rep}_{arm}.graph'),sel)
            print(f'R85_A2_DRY_RUN {i}/9 arm={arm} '+shlex.join(cmd))
        print('R85_A2_DRY_RUN_PASS_NO_BUILD_NO_SEARCH');return
    if args.run_build:
        build(old,a1,sel);return
    if args.run_quality:
        quality(old,a1,a1c,args.run_quality);return


if __name__=='__main__':
    try:
        main()
    except Exception as e:
        print('R85_A2_ERROR '+str(e),file=sys.stderr)
        sys.exit(1)
