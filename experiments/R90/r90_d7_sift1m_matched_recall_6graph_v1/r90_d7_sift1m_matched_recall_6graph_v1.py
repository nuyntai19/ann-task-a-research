#!/usr/bin/env python3
"""R90-D7: SHA-pinned, read-only native matched-Recall *quality-floor* study.

Uses existing H85 native dynamic-beam evaluator and six existing P3.11 graphs.
No ANN BUILD, no recompilation, no changes to frozen sources/binaries/graphs.
Three independent BUILD graphs/arm; 2 Search repeats/graph; dense fixed beams.
Discrete minimum-beam quality-floor comparisons are measured; interpolation to
exact Recall is reported separately as an *estimate*, never a direct measurement.
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
import shutil
import statistics
import subprocess
import sys
import tempfile

HOME = Path.home()
ROOT = HOME / 'ann-task-a'
H85 = ROOT/'experiments/H85/r85_a2_edge_match'
EVAL = H85/'r85_a2_dynamic_recall'
EVAL_CPP = H85/'r85_a2_dynamic_recall.cc'
EVAL_MANIFEST = H85/'evaluator_manifest.json'
EVAL_SHA = '93bf07d585def40d3cd1723476964a5d6ddfa85b99081f42a43a05b61063dc73'
CPP_SHA = '1b87d0b6d102463d7f26b69eb19e2207a9e6684029225dc0c9638b46df74fc4f'
P312_SCRIPT = HOME/'Downloads/r90_p312_sift1m_4cpu_six_graph_search_quality_v1.py'
P312_SHA = '6ed9c4d4c869feff6de4c38fe02f3df59b3e63c770aae7f24c10e94341e31671'
P312_DIR = ROOT/'experiments/R90/r90_p312_sift1m_4cpu_six_graph_search_quality_v1'
D6_SCRIPT = HOME/'Downloads/r90_d6_h17_fastv2_top2_exact_counters_v1.py'
D6_SHA = 'c8fbb9e2dc531cdb6cffb755ab98db558df8b5633c03a38dda0f2c1da4af1c8b'
D6_DIR = ROOT/'experiments/R90/r90_d6_h17_fastv2_top2_exact_counters_v1'
OUT = ROOT/'experiments/R90/r90_d7_sift1m_matched_recall_6graph_v1'
BEAMS = (10,20,40,64,68,72,76,80,84,88,92,96,104,112,120,128,132,136,140,144,148,152,156,160)
ANCHORS = (10,20,40,80,160)
TARGETS = (0.99,0.998)
METRICS = ('recall','qps','avg_cmps','avg_visited')
RX = re.compile(r'^R72_RECALL_ROW\s+beam=(\d+)\s+recall=([\deE.+-]+)\s+'
                r'qps=([\deE.+-]+)\s+avg_cmps=([\deE.+-]+)\s+'
                r'avg_visited=([\deE.+-]+)\s*$', re.M)


def gate(cond, why):
    if not cond:
        raise RuntimeError('R90_D7_HOLD_'+why)


def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as fd:
        for block in iter(lambda:fd.read(4*1024*1024),b''):
            h.update(block)
    return h.hexdigest()


def atomic(path, data):
    temp=path.with_suffix(path.suffix+'.part')
    gate(not temp.exists() and not temp.is_symlink(),'PART_FILE_EXISTS_'+path.name)
    with temp.open('x',encoding='utf8') as fd:
        json.dump(data,fd,sort_keys=True,indent=2);fd.write('\n')
    os.replace(temp,path)


def read_module(path,name):
    spec=importlib.util.spec_from_file_location(name,str(path))
    gate(spec is not None and spec.loader is not None,'MODULE_SPEC_'+name)
    obj=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(obj)
    return obj


def parse_log(text):
    gate(text.count('R72_RECALL_INPUT_PASS')==1 and
         text.count('R72_RECALL_EVAL_PASS')==1,'EVALUATOR_PASS_MARKERS')
    count_line=f'R85_A1C_DYNAMIC_BEAMS count={len(BEAMS)}'
    gate(text.count(count_line)==1,'EVALUATOR_DYNAMIC_BEAMS_MARKER')
    matches=RX.findall(text)
    gate(len(matches)==len(BEAMS),'BEAM_ROWS_COUNT')
    metrics={}
    for item in matches:
        beam=int(item[0]);values=list(map(float,item[1:]))
        gate(beam in BEAMS and beam not in metrics,'BEAM_ORDER_DUPLICATE')
        gate(all(math.isfinite(v) for v in values),'NONFINITE')
        gate(0<=values[0]<=1 and values[1]>0 and values[2]>=0 and values[3]>=0,
             'METRIC_RANGE')
        metrics[beam]=dict(zip(METRICS,values))
    gate(tuple(metrics)==BEAMS,'BEAMS_NOT_EXACTLY_PINNED')
    return metrics


def first_crossing(series,target):
    """Minimum measured beam satisfying Recall floor; optional local interpolation."""
    assert 0 < target < 1
    for i,beam in enumerate(BEAMS):
        if series[beam]['recall']>=target:
            hi=series[beam]
            out={'target':target,'selected_beam':beam,'observed_recall':hi['recall'],
                 'observed_qps':hi['qps'],'observed_us_per_query':1e6/hi['qps'],
                 'observed_cmps':hi['avg_cmps'],'observed_visited':hi['avg_visited'],
                 'quality_overshoot':hi['recall']-target}
            if i>0:
                lo_beam=BEAMS[i-1];lo=series[lo_beam]
                gate(lo['recall']<target,'CROSSING_FIRST_LOWER')
                if hi['recall']>lo['recall']:
                    w=(target-lo['recall'])/(hi['recall']-lo['recall'])
                    latency=((1-w)*(1e6/lo['qps'])+w*(1e6/hi['qps']))
                    out['interpolation_estimate']={
                        'lower_beam':lo_beam,'upper_beam':beam,
                        'lower_recall':lo['recall'],'upper_recall':hi['recall'],
                        'weight':w,'estimated_us_per_query':latency,
                        'estimated_qps_equivalent':1e6/latency,
                        'not_directly_measured_at_target':True}
            return out
    return None


def verify_previous():
    gate(P312_SCRIPT.is_file() and not P312_SCRIPT.is_symlink() and
         digest(P312_SCRIPT)==P312_SHA,'P312_SCRIPT_SHA')
    p312=read_module(P312_SCRIPT,'r90_p312_frozen')
    graphs, provenance=p312.inspect(False)  # Inherited pinned SIFT1M/graph/GT gates.
    base=P312_DIR/'search_manifest.json';summary=P312_DIR/'search_quality_summary.json'
    gate(base.is_file() and summary.is_file() and
         not base.is_symlink() and not summary.is_symlink(),'P312_SEARCH_EVIDENCE_MISSING')
    st=json.loads(base.read_text());sm=json.loads(summary.read_text())
    gate(st.get('phase')=='COMPLETE_12_SEARCH_RUNS' and st.get('script_sha')==P312_SHA
         and st.get('sources')==provenance and len(st.get('runs',[]))==12,
         'P312_SEARCH_MANIFEST')
    gate(sm.get('audit')=='PASS_12_NATIVE_SEARCH_RUNS_10KQ_5_BEAMS' and
         sm.get('status')=='QUALITY_SCREEN_NO_LARGE_RECALL_DROP' and
         sm.get('source_search_manifest_sha')==digest(base) and
         len(sm.get('per_graph_beam',[]))==30,'P312_SEARCH_SUMMARY')
    prior={}
    for z in st['runs']:
        key=(z['arm'],z['build_rep'],z['search_rep'])
        gate(key not in prior and z['graph_sha']==graphs[key[:2]]['graph_sha'],
             'P312_GRAPH_RECEIPT')
        log=Path(z['log']);gate(log.is_file() and not log.is_symlink() and
                            log.resolve().parent==(P312_DIR/'logs').resolve() and
                            digest(log)==z['log_sha'],'P312_SEARCH_LOG_SHA')
        old=p312.parse(log.read_text(errors='replace'))
        for b in p312.BEAMS:
            for k in p312.METRICS:
                gate(abs(old[b][k]-z['beams'][str(b)][k])<=1e-8,
                     'P312_SEARCH_LOG_DRIFT')
        prior[key]=old
    gate(len(prior)==12,'P312_12_DISTINCT_EVALUATIONS')
    gate(D6_SCRIPT.is_file() and not D6_SCRIPT.is_symlink() and
         digest(D6_SCRIPT)==D6_SHA,'D6_SCRIPT_SHA')
    d6=read_module(D6_SCRIPT,'r90_d6_frozen')
    d6.audit1m()  # checks previous D6 counts, source/ELF/graphs/csv without writing.
    d6_manifest=D6_DIR/'manifest_1m.json';d6_summary=D6_DIR/'work_summary_1m.json'
    gate(json.loads(d6_manifest.read_text()).get('status')=='PASS_1M',
         'D6_MANIFEST_STATUS')
    for path,sha,name in ((EVAL,EVAL_SHA,'EVAL_ELF'),
                          (EVAL_CPP,CPP_SHA,'EVAL_CPP')):
        gate(path.is_file() and not path.is_symlink() and digest(path)==sha,
             name+'_SHA')
    gate(os.access(EVAL,os.X_OK),'EVAL_NOT_EXECUTABLE')
    gate(EVAL_MANIFEST.is_file() and not EVAL_MANIFEST.is_symlink(),
         'EVAL_MANIFEST_NOT_FOUND')
    m=json.loads(EVAL_MANIFEST.read_text())
    gate(m.get('evaluator_sha256')==EVAL_SHA and m.get('cpp_sha256')==CPP_SHA,
         'EVAL_MANIFEST_SHA_FIELDS')
    gate(shutil.which('taskset') is not None and 0 in os.sched_getaffinity(0),
         'AFFINITY_CPU0_UNAVAILABLE')
    receipt={
        'p312_script_sha':P312_SHA,'p312_manifest_sha':digest(base),
        'p312_summary_sha':digest(summary),
        'd6_script_sha':D6_SHA,'d6_manifest_sha':digest(d6_manifest),
        'd6_work_summary_sha':digest(d6_summary),
        'dynamic_evaluator_elf_sha':EVAL_SHA,'dynamic_evaluator_cpp_sha':CPP_SHA,
        'dynamic_evaluator_manifest_sha':digest(EVAL_MANIFEST),
        'p312_sources':provenance,
        'beams':list(BEAMS),'targets':list(TARGETS),
        'graph_sha':{f'{k[0]}_r{k[1]}':v['graph_sha'] for k,v in sorted(graphs.items())}}
    return graphs,prior,receipt


def selftest():
    fake='R85_A1C_DYNAMIC_BEAMS count='+str(len(BEAMS))+'\nR72_RECALL_INPUT_PASS\n'
    fake+=''.join(f'R72_RECALL_ROW beam={b} recall={min(1,0.75+.0018*b):.8f} qps={30000/(1+b/25):.8f} avg_cmps=1337 avg_visited=88\n' for b in BEAMS)
    fake+='R72_RECALL_EVAL_PASS\n'
    items=parse_log(fake)
    gate(len(items)==len(BEAMS) and items[10]['avg_cmps']==1337,'SELFTEST_PARSE')
    for target in TARGETS:
        x=first_crossing(items,target)
        gate((x is None) if items[160]['recall']<target else (x is not None),
             'SELFTEST_CROSSING')
    # deliberately constructed target in between consecutive values
    fake_series={b:dict(recall=(.95 if b<=72 else .999),qps=10000/(1+b/100),avg_cmps=1,avg_visited=1) for b in BEAMS}
    s=first_crossing(fake_series,.99)
    gate(s['selected_beam']==76 and
         s['interpolation_estimate']['lower_beam']==72 and
         0<s['interpolation_estimate']['weight']<1,'SELFTEST_INTERPOLATION')
    try:parse_log(fake.replace('beam=72 ','beam=68 '))
    except RuntimeError:pass
    else:raise RuntimeError('SELFTEST_DUPLICATE_BEAM_ACCEPTED')
    with tempfile.TemporaryDirectory() as td:
        path=Path(td)/'receipt.json';atomic(path,{'x':1});atomic(path,{'x':2})
        gate(json.loads(path.read_text())['x']==2,'SELFTEST_ATOMIC')
    print('R90_D7_SELFTEST_PASS_24_BEAMS_NATIVE_PARSER_DISCRETE_FLOOR_INTERPOLATION',flush=True)


def preflight():
    graphs,old,rec=verify_previous()
    gate(not OUT.exists() and not OUT.is_symlink(),'OUTPUT_EXISTS')
    gate(OUT.parent.is_dir(),'OUTPUT_PARENT')
    gate(set(graphs)=={(a,i) for a in ('ctrl','fast') for i in (1,2,3)} and
         len(old)==12,'OLD_SIX_GRAPH_KEYS')
    print('R90_D7_PREFLIGHT_PINNED_H85_DYNAMIC_EVAL_P312_SIXGRAPH_10KQ_D6_SHA_PASS',flush=True)


def pilot():
    graphs,old,source=verify_previous()
    gate(not OUT.exists() and not OUT.is_symlink(),'OUTPUT_EXISTS')
    OUT.mkdir();(OUT/'logs').mkdir()
    manifest={'status':'RUNNING','script_sha':digest(Path(__file__).resolve()),
              'source':source,'nqueries':10000,'k':10,'reps_per_graph':2,
              'beam_csv':','.join(map(str,BEAMS)),
              'search':{'cpu':'0','PARLAY_NUM_THREADS':'1','OMP_NUM_THREADS':'1'},
              'not_graph_build':True,'runs':[]}
    atomic(OUT/'progress.json',manifest)
    env=os.environ.copy();env.update({'LC_ALL':'C','OMP_NUM_THREADS':'1','PARLAY_NUM_THREADS':'1'})
    for rep in (1,2):
        for b in (1,2,3):
            for arm in (('ctrl','fast') if (rep+b)%2==0 else ('fast','ctrl')):
                label=f'{arm}_build{b}_search{rep}'
                path=OUT/'logs'/(label+'.stdout')
                gate(not path.exists() and not path.is_symlink(),'SEARCH_LOG_EXISTS_'+label)
                cmd=['taskset','-c','0',str(EVAL),str(graphs[(arm,b)]['graph']),
                     str(ROOT/'data/sift1m.fbin'),str(ROOT/'data/sift1m_queries.fbin'),
                     str(ROOT/'data/sift1m_gt.ibin'),','.join(map(str,BEAMS))]
                print('R90_D7_SEARCH_START',label,'beams',len(BEAMS),flush=True)
                with path.open('x') as fd:
                    proc=subprocess.run(cmd,env=env,stdout=fd,stderr=subprocess.STDOUT,
                                        check=False,timeout=2400)
                gate(proc.returncode==0,'NATIVE_EVAL_EXIT_'+label+'_'+str(proc.returncode))
                parsed=parse_log(path.read_text(errors='replace'))
                # Source parity with R72's original evaluator at five anchor beams.
                max_delta=max(abs(parsed[beam]['recall']-old[(arm,b,rep)][beam]['recall_at10'])
                              for beam in ANCHORS)
                gate(max_delta<=.00005,'R72_REFERENCE_RECALL_DISAGREEMENT_'+label)
                manifest['runs'].append({'arm':arm,'build_rep':b,'search_rep':rep,
                    'graph_sha':graphs[(arm,b)]['graph_sha'],
                    'log':str(path),'log_sha':digest(path),
                    'max_anchor_recall_delta':max_delta,
                    'metrics':{str(k):v for k,v in parsed.items()}})
                atomic(OUT/'progress.json',manifest)
                print('R90_D7_SEARCH_PASS',label,'max_anchor_recall_delta',max_delta,
                      'recall_b80',parsed[80]['recall'],'recall_b160',parsed[160]['recall'],flush=True)
    gate(len(manifest['runs'])==12,'PILOT_RUNS_12')
    manifest['status']='COMPLETE_NATIVE_12_SEARCH_RUNS_24_BEAMS'
    atomic(OUT/'search_manifest.json',manifest)
    print('R90_D7_PILOT_PASS_12_NATIVE_SEARCH_RUNS_24_BEAMS',flush=True)


def audit():
    graphs,old,source=verify_previous()
    p=OUT/'search_manifest.json'
    gate(p.is_file() and not p.is_symlink(),'PILOT_MANIFEST_MISSING')
    st=json.loads(p.read_text())
    gate(st.get('status')=='COMPLETE_NATIVE_12_SEARCH_RUNS_24_BEAMS' and
         st.get('script_sha')==digest(Path(__file__).resolve()) and
         st.get('source')==source and len(st.get('runs',[]))==12,
         'PILOT_MANIFEST_STATE')
    results={}
    for item in st['runs']:
        key=(item['arm'],item['build_rep'],item['search_rep'])
        gate(key not in results and key[0] in ('ctrl','fast') and
             key[1] in (1,2,3) and key[2] in (1,2),'RUN_KEY')
        gate(item['graph_sha']==graphs[key[:2]]['graph_sha'],'GRAPH_SHA_'+str(key))
        path=Path(item['log']);gate(path.is_file() and not path.is_symlink() and
             path.resolve().parent==(OUT/'logs').resolve() and digest(path)==item['log_sha'],
             'EVALUATOR_LOG_SHA_'+str(key))
        data=parse_log(path.read_text(errors='replace'))
        gate(max(abs(data[b]['recall']-old[key][b]['recall_at10']) for b in ANCHORS)<=.00005,
             'REFERENCE_FIVE_BEAM_PARITY_'+str(key))
        for b in BEAMS:
            for metric in METRICS:
                gate(abs(data[b][metric]-item['metrics'][str(b)][metric])<1e-8,
                     'SOURCE_LOG_METRIC_CHANGED')
        results[key]=data
    gate(len(results)==12,'TWELVE_SEARCH_RUNS')
    grouped={}
    per_graph=[]
    for arm in ('ctrl','fast'):
        grouped[arm]={}
        for build in (1,2,3):
            key=(arm,build)
            series={}
            for beam in BEAMS:
                a,b=results[(arm,build,1)][beam],results[(arm,build,2)][beam]
                gate(abs(a['recall']-b['recall'])<=1e-7,
                     'SAME_GRAPH_RECALL_NONDETERMINISM_'+str(key)+'_b'+str(beam))
                series[beam]={'recall':statistics.mean((a['recall'],b['recall'])),
                              'qps':statistics.median((a['qps'],b['qps'])),
                              'avg_cmps':statistics.mean((a['avg_cmps'],b['avg_cmps'])),
                              'avg_visited':statistics.mean((a['avg_visited'],b['avg_visited']))}
            grouped[arm][build]=series
            per_graph.append({'arm':arm,'build_rep':build,
                              'graph_sha':graphs[key]['graph_sha'],
                              'targets':{str(t):first_crossing(series,t) for t in TARGETS},
                              'beam_curve':{str(k):v for k,v in series.items()}})
    targets=[]
    all_crossed=True
    for t in TARGETS:
        each={arm:[first_crossing(grouped[arm][rep],t) for rep in (1,2,3)]
              for arm in ('ctrl','fast')}
        if any(x is None for arm in each for x in each[arm]):
            all_crossed=False
            targets.append({'target':t,'status':'TARGET_NOT_REACHED_BY_ALL_SIX_GRAPHS',
                            'missing':[(arm,idx+1) for arm in each for idx,x in enumerate(each[arm]) if x is None]})
            continue
        report={'target':t,'status':'ALL_SIX_GRAPHS_REACHED_FLOOR',
                'per_arm':{},'paired_build_floor_qps_deltas_pct':[],
                'paired_build_floor_recall_deltas':[]}
        for arm in ('ctrl','fast'):
            x=each[arm]
            summary={'mean_selected_beam':statistics.mean(z['selected_beam'] for z in x),
                     'selected_beams':[z['selected_beam'] for z in x],
                     'mean_observed_recall':statistics.mean(z['observed_recall'] for z in x),
                     'mean_observed_qps':statistics.mean(z['observed_qps'] for z in x),
                     'mean_observed_latency_us':statistics.mean(z['observed_us_per_query'] for z in x),
                     'mean_overshoot':statistics.mean(z['quality_overshoot'] for z in x)}
            interp=[z.get('interpolation_estimate') for z in x]
            if all(z is not None for z in interp):
                summary['mean_INTERPOLATED_latency_us_at_exact_target']=statistics.mean(z['estimated_us_per_query'] for z in interp)
                summary['interpolation_not_directly_measured']=True
            report['per_arm'][arm]=summary
        for rep in (0,1,2):
            ctl=each['ctrl'][rep];fst=each['fast'][rep]
            report['paired_build_floor_qps_deltas_pct'].append(100*(fst['observed_qps']/ctl['observed_qps']-1))
            report['paired_build_floor_recall_deltas'].append(fst['observed_recall']-ctl['observed_recall'])
        report['mean_fast_over_ctrl_observed_qps_ratio']=(
            report['per_arm']['fast']['mean_observed_qps']/report['per_arm']['ctrl']['mean_observed_qps'])
        report['mean_fast_over_ctrl_observed_latency_ratio']=(
            report['per_arm']['fast']['mean_observed_latency_us']/report['per_arm']['ctrl']['mean_observed_latency_us'])
        if all('mean_INTERPOLATED_latency_us_at_exact_target' in report['per_arm'][arm] for arm in ('ctrl','fast')):
            report['fast_over_ctrl_INTERPOLATED_latency_ratio_at_exact_target']=(
                report['per_arm']['fast']['mean_INTERPOLATED_latency_us_at_exact_target']/
                report['per_arm']['ctrl']['mean_INTERPOLATED_latency_us_at_exact_target'])
        targets.append(report)
        print('R90_D7_MATCHED_FLOOR target',t,
              'ctrl_beams',report['per_arm']['ctrl']['selected_beams'],
              'fast_beams',report['per_arm']['fast']['selected_beams'],
              'qps_ratio',round(report['mean_fast_over_ctrl_observed_qps_ratio'],6),
              'latency_ratio',round(report['mean_fast_over_ctrl_observed_latency_ratio'],6),flush=True)
    summary={'status':'MATCHED_FLOORS_PASS_ALL_6' if all_crossed else 'QUALITY_FLOOR_RANGE_HOLD',
             'not_formal_equivalence_or_noninferiority':True,
             'not_directly_measured_latency_at_exact_recall_target':True,
             'description':'Minimum measured beam whose Recall@10 meets quality floor; graphs may overshoot target. Interpolated latency at target is a descriptive estimate.',
             'n_query':10000,'dataset':'SIFT1M','k':10,'build_cpu_count':4,'search_cpu_count':1,
             'n_build_graphs_per_arm':3,'search_reps_per_graph':2,'beams':list(BEAMS),
             'targets':targets,'per_graph':per_graph,'source_manifest_sha':digest(p),
             'limitations':['Recall equivalence not proven by closeness: three graph builds per arm',
               'Discrete beam minimum meeting a floor may overshoot, so QPS is at matched quality floor, not exactly equal Recall',
               'Interpolated time from bracketing beam points is not a directly measured exact-target latency',
               'QPS is native evaluator single-thread throughput, not p95/p99 query latency',
               'Do not count two searches per graph as two independent graph builds',
               'This script does not rebuild PiPNN graphs, does not measure D6 BUILD counters']}
    f=OUT/'matched_recall_summary.json'
    gate(not f.exists() and not f.is_symlink(),'SUMMARY_EXISTS')
    with f.open('x') as fd:json.dump(summary,fd,sort_keys=True,indent=2);fd.write('\n')
    print('R90_D7_AUDIT_PASS_12SEARCH_24BEAMS',summary['status'],flush=True)
    print('R90_D7_REPORT',f,flush=True)


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('phase',choices=('selftest','preflight','pilot','audit'))
    action=ap.parse_args().phase
    {'selftest':selftest,'preflight':preflight,'pilot':pilot,'audit':audit}[action]()


if __name__=='__main__':
    try:main()
    except Exception as error:
        print('R90_D7_HOLD',repr(error),file=sys.stderr,flush=True)
        raise SystemExit(2)
