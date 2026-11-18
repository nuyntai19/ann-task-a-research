#!/usr/bin/env python3
"""R90-P3.12 read-only 10,000-query native SEARCH on six P3.11 SIFT1M 4CPU graphs.

The 4CPU H17 BUILD is not byte-deterministic. Search is therefore evaluated on
three independently built graph realizations for each arm, not an impossible
cross-arm graph-SHA parity gate. Pinned existing native R72 evaluator, same
held-out queries and GT, 5 fixed beams, 2 single-CPU Search repetitions/graph.
This is a quality screen, NOT a formal noninferiority or matched-Recall proof.
All writes are confined to a fresh P3.12 output directory, never to P3.11.
"""
from __future__ import annotations
import argparse, hashlib, importlib.util, json, math, os, pathlib, re
import shutil, statistics, struct, subprocess, sys, tempfile

H=pathlib.Path.home(); ROOT=H/'ann-task-a'; R90=ROOT/'experiments/R90'
OLD=R90/'r90_p311_h17_fastv2_4cpu_sift1m_quality_gated_v1'
OLD_SCRIPT=H/'Downloads/r90_p311_h17_fastv2_4cpu_sift1m_quality_gated_v1.py'
OLD_SCRIPT_SHA='09a2399ffdb525905cb36e2c2ac8fbeabf13779e58ba844222e00ad0d9871af4'
OUT=R90/'r90_p312_sift1m_4cpu_six_graph_search_quality_v1'
BASE=ROOT/'data/sift1m.fbin'
QUERY=ROOT/'data/sift1m_queries.fbin'
GT=ROOT/'data/sift1m_gt.ibin'
EVAL=ROOT/'experiments/H70/build-r70/algorithms/PipNN/r72_graph_recall'
PINS={
 'base':'8c7b3d999ba3133f865af72df078f77c2d248fdb80571d7ea1f1bb8e1750658e',
 'query':'9b0082b67d0ac55b4c7d42216560344567ad87ce3e75a9d5214a0762f1c15d65',
 'gt':'047418d19f3981e4fc2dd28ae3b6f72fa7108f40d9336bd2d80b07829885ba13',
 'evaluator':'3c2294efa1d7fb5d89c79ca5bf9c1eaca86247f7246e6d6d7c6c94549d08ed57',
}
GRAPH_SHA={
 ('ctrl',1):'87b989b4229d0a36eaffba892a43a2fd06dfea227b4dde55f8351b4279348688',
 ('fast',1):'cdc1a475d02496900fe08eba2cd42f71c0496807b51e7ce95ffde2396bc6be3a',
 ('ctrl',2):'0ccdd72a8edb979d34816eb41b2b4db475249d972e631343a1da549a22d7f5e2',
 ('fast',2):'dad585a5825245db7206e679a9c6eb7c53d19e9180329f072b1bbcaa18d42e4d',
 ('ctrl',3):'c09bd769ea89d55a58a93fff68c72c644cf08aa2c654ffb2d5d5c61127588b3c',
 ('fast',3):'dec5769ac0b8ff929cdfe8820fa91897df0d87da4ab22af32ee3fbb9f27c73fd',
}
BEAMS=(10,20,40,80,160); REPS=(1,2); NQUERY=10000; K=10
METRICS=('recall_at10','qps','avg_cmps','avg_visited')
RX=re.compile(r'^R72_RECALL_ROW\s+beam=(\d+)\s+recall=([\deE.+-]+)\s+'
              r'qps=([\deE.+-]+)\s+avg_cmps=([\deE.+-]+)\s+'
              r'avg_visited=([\deE.+-]+)\s*$',re.M)

def check(ok,msg):
    if not ok:raise RuntimeError('R90_P312_HOLD_'+msg)

def sha(path):
    h=hashlib.sha256()
    with pathlib.Path(path).open('rb') as f:
        for b in iter(lambda:f.read(4*1024*1024),b''):h.update(b)
    return h.hexdigest()

def atomic(path,obj):
    tmp=path.with_suffix(path.suffix+'.part')
    check(not tmp.exists() and not tmp.is_symlink(),'OUTPUT_PART_EXISTS_'+path.name)
    with tmp.open('x',encoding='utf-8') as f:json.dump(obj,f,indent=2,sort_keys=True);f.write('\n')
    os.replace(tmp,path)

def parse(stdout):
    check(stdout.count('R72_RECALL_INPUT_PASS')==1,'NATIVE_INPUT_PASS_MARKER')
    check(stdout.count('R72_RECALL_EVAL_PASS')==1,'NATIVE_EVAL_PASS_MARKER')
    matches=RX.findall(stdout)
    check(len(matches)==5,'FIVE_BEAM_ROWS')
    out={}
    for v in matches:
        beam=int(v[0]);nums=list(map(float,v[1:]))
        check(beam in BEAMS and beam not in out,'BEAM_UNEXPECTED_OR_DUPLICATE')
        recall,qps,cmps,visited=nums
        check(all(math.isfinite(x) for x in nums) and 0<=recall<=1 and qps>0 and
              cmps>=0 and visited>=0,'NUMERIC_FIELD_INVALID')
        out[beam]=dict(zip(METRICS,nums))
    check(tuple(out)==BEAMS,'BEAMS_NOT_IN_EXPECTED_ORDER')
    return out

def shape(path,expected,bytes_per_element):
    with path.open('rb') as f:header=f.read(8)
    check(len(header)==8 and struct.unpack('<II',header)==expected,'SHAPE_HEADER_'+path.name)
    check(path.stat().st_size==8+expected[0]*expected[1]*bytes_per_element,
          'SHAPE_SIZE_'+path.name)

def check_graph_header_size(path):
    import array
    with path.open('rb') as f:
        n,deg=struct.unpack('<II',f.read(8))
        check((n,deg)==(1000000,64),'GRAPH_DIMENSIONS')
        arr=array.array('I');arr.frombytes(f.read(n*4))
    check(len(arr)==n and max(arr,default=0)<=deg,'GRAPH_DEGREES')
    arcs=sum(arr)
    check(path.stat().st_size==8+4*n+4*arcs,'GRAPH_LENGTH')
    return {'n':n,'max_degree':deg,'arcs':arcs,'bytes':path.stat().st_size}

def inspect(check_output=True):
    check(OLD_SCRIPT.is_file() and not OLD_SCRIPT.is_symlink() and
          sha(OLD_SCRIPT)==OLD_SCRIPT_SHA,'P311_SCRIPT_SHA')
    spec=importlib.util.spec_from_file_location('verified_p311',str(OLD_SCRIPT))
    check(spec is not None and spec.loader is not None,'OLD_MODULE_SPEC')
    p311=importlib.util.module_from_spec(spec);spec.loader.exec_module(p311)
    # Its locked gate verifies the exact completed P3.10/1CPU/H17/P39 input provenance.
    p311.read_previous(check_resources=False)
    manifest=OLD/'build_manifest_1m.json';audit=OLD/'build_1m_audit.json'
    check(manifest.is_file() and audit.is_file(),'P311_AUDIT_OR_MANIFEST_ABSENT')
    check(not manifest.is_symlink() and not audit.is_symlink(),'P311_AUDIT_SYMLINK')
    st=json.loads(manifest.read_text());a=json.loads(audit.read_text())
    check(st.get('status')=='SIX_1M_BUILDS_COMPLETE_QUALITY_PENDING'
          and st.get('script_sha')==OLD_SCRIPT_SHA and len(st.get('runs',[]))==6,
          'P311_BUILD_STATE')
    check(a.get('status')=='PASS_NATIVE_4CPU_1M_BUILD_EVIDENCE__SEARCH_QUALITY_UNTESTED'
          and a.get('source_manifest_sha')==sha(manifest)
          and len(a.get('pairs_graph_diff',[]))==3,'P311_AUDIT_STATE')
    for name,path in [('base',BASE),('query',QUERY),('gt',GT),('evaluator',EVAL)]:
        check(path.is_file() and not path.is_symlink() and sha(path)==PINS[name],
              'PINNED_'+name.upper())
    check(os.access(EVAL,os.X_OK),'EVALUATOR_NOT_EXECUTABLE')
    shape(BASE,(1000000,128),4);shape(QUERY,(10000,128),4);shape(GT,(10000,100),8)
    check(shutil.which('taskset') is not None and 0 in os.sched_getaffinity(0),
          'SEARCH_CPU0_UNAVAILABLE')
    rows={}
    for entry in st['runs']:
        key=(entry.get('arm'),entry.get('rep'))
        check(key in GRAPH_SHA and key not in rows and entry.get('n')==1000000,
              'BUILD_ROW_ID')
        check(entry['graph_sha']==GRAPH_SHA[key],'BUILD_GRAPH_SHA_VS_LOG')
        g=pathlib.Path(entry['graph'])
        check(g.is_file() and not g.is_symlink() and g.resolve().parent==(OLD/'graphs').resolve(),
              'GRAPH_PATH_'+str(key))
        check(sha(g)==GRAPH_SHA[key],'GRAPH_FILE_SHA_'+str(key))
        for f,h,sub in [('stdout','stdout_sha','logs'),('timefile','timefile_sha','logs')]:
            t=pathlib.Path(entry[f]);check(t.is_file() and not t.is_symlink() and
                t.resolve().parent==(OLD/sub).resolve() and sha(t)==entry[h],
                'BUILD_RECEIPT_SHA_'+f+str(key))
        rows[key]={**entry,'graph_meta':check_graph_header_size(g)}
    check(set(rows)==set(GRAPH_SHA),'SIX_GRAPH_KEYS')
    if check_output:
        check(not OUT.exists() and not OUT.is_symlink(),'OUTPUT_EXISTS')
        check(OUT.parent.is_dir(),'OUTPUT_PARENT')
    print('R90_P312_PREFLIGHT_PINNED_P311_6_GRAPHS_R72_EVAL_10KQ_GT_SHA_PASS',flush=True)
    return rows,{'p311_script':OLD_SCRIPT_SHA,'p311_manifest':sha(manifest),
                 'p311_build_audit':sha(audit),'data_sha':PINS,
                 'graph_sha':{f'{k[0]}_r{k[1]}':v for k,v in GRAPH_SHA.items()},
                 'beams':list(BEAMS),'nqueries':NQUERY,'k':K,'search_repeats':list(REPS)}

def selftest():
    with tempfile.TemporaryDirectory() as z:
        p=pathlib.Path(z)/'receipt.json';atomic(p,{'rows':1});atomic(p,{'rows':2})
        check(json.loads(p.read_text())['rows']==2,'JSON_ATOMIC')
        s='R72_RECALL_INPUT_PASS\n'+''.join(
            f'R72_RECALL_ROW beam={b} recall=0.998 qps=1250.1 avg_cmps=1300 avg_visited=90\n'
            for b in BEAMS)+'R72_RECALL_EVAL_PASS\n'
        v=parse(s)
        check(list(v)==list(BEAMS) and v[80]['qps']==1250.1,'NATIVE_PARSER')
        bad=s.replace('R72_RECALL_ROW beam=40 ','R72_RECALL_ROW beam=20 ')
        try:parse(bad)
        except RuntimeError:pass
        else:raise RuntimeError('SELFTEST_SHOULD_REJECT_DUPLICATE_BEAM')
    print('R90_P312_SELFTEST_PASS_ATOMIC_PARSER_AND_BEAM_GATE',flush=True)

def preflight():
    inspect(True)

def pilot():
    rows,source=inspect(True)
    OUT.mkdir(mode=0o755);(OUT/'logs').mkdir()
    state={'phase':'RUNNING','script_sha':sha(pathlib.Path(__file__).resolve()),
           'sources':source,'search_affinity':'CPU0','PARLAY_NUM_THREADS':1,
           'native_evaluator':'R72 graph recall: 10000 heldout SIFT1M queries, GT top10',
           'not_matched_recall':True,'runs':[]}
    atomic(OUT/'progress.json',state)
    env=os.environ.copy();env.update({'LC_ALL':'C','PARLAY_NUM_THREADS':'1','OMP_NUM_THREADS':'1'})
    for search_rep in REPS:
        for build_rep in (1,2,3):
            arms=('ctrl','fast') if (search_rep+build_rep)%2==0 else ('fast','ctrl')
            for arm in arms:
                tag=f'{arm}_build{build_rep}_search{search_rep}'
                log=OUT/'logs'/(tag+'.stdout')
                check(not log.exists() and not log.is_symlink(),'LOG_ALREADY_EXISTS_'+tag)
                cmd=['taskset','-c','0',str(EVAL),str(rows[(arm,build_rep)]['graph']),
                     str(BASE),str(QUERY),str(GT)]
                print('R90_P312_SEARCH_START',tag,flush=True)
                with log.open('x') as f:
                    res=subprocess.run(cmd,env=env,stdout=f,stderr=subprocess.STDOUT,
                                       check=False,timeout=1800)
                check(res.returncode==0,'NATIVE_SEARCH_EXIT_'+tag+'_'+str(res.returncode))
                metrics=parse(log.read_text(errors='replace'))
                state['runs'].append({'arm':arm,'build_rep':build_rep,'search_rep':search_rep,
                                      'graph_sha':rows[(arm,build_rep)]['graph_sha'],
                                      'log':str(log),'log_sha':sha(log),
                                      'beams':{str(k):v for k,v in metrics.items()}})
                atomic(OUT/'progress.json',state)
                print('R90_P312_SEARCH_PASS',tag,'beam160_recall',metrics[160]['recall_at10'],flush=True)
    check(len(state['runs'])==12,'RUNS_12_REQUIRED')
    state['phase']='COMPLETE_12_SEARCH_RUNS';atomic(OUT/'search_manifest.json',state)
    print('R90_P312_PILOT_PASS_12_SEARCH_RUNS_5_BEAMS_10000_QUERIES',flush=True)

def audit():
    rows,source=inspect(False)
    manifest=OUT/'search_manifest.json';check(manifest.is_file(),'SEARCH_MANIFEST_NOT_FOUND')
    st=json.loads(manifest.read_text())
    check(st.get('phase')=='COMPLETE_12_SEARCH_RUNS' and
          st.get('script_sha')==sha(pathlib.Path(__file__).resolve()) and
          st.get('sources')==source and len(st.get('runs',[]))==12,'SEARCH_MANIFEST_STATE')
    results={}
    for entry in st['runs']:
        key=(entry['arm'],entry['build_rep'],entry['search_rep'])
        check(key not in results and key[0] in ('ctrl','fast') and key[1] in (1,2,3)
              and key[2] in REPS,'SEARCH_KEY')
        check(entry['graph_sha']==rows[key[:2]]['graph_sha'],'SEARCH_GRAPH_ID_SHA')
        log=pathlib.Path(entry['log'])
        check(log.is_file() and not log.is_symlink() and
              log.resolve().parent==(OUT/'logs').resolve() and
              sha(log)==entry['log_sha'],'SEARCH_LOG_SHA')
        parsed=parse(log.read_text(errors='replace'))
        for beam in BEAMS:
            for field in METRICS:
                check(abs(parsed[beam][field]-entry['beams'][str(beam)][field])<1e-8,
                      'SEARCH_LOG_METRIC_CHANGED')
        results[key]=parsed
    check(len(results)==12,'TWELVE_DISTINCT_SEARCH_RUNS')
    bybeam=[];pergraph=[]
    for beam in BEAMS:
        rollup={}
        for arm in ('ctrl','fast'):
            onebuild=[]
            for brep in (1,2,3):
                x=[results[(arm,brep,s)][beam] for s in REPS]
                recalls=[q['recall_at10'] for q in x]
                check(max(recalls)-min(recalls)<=1e-7,
                      'RECALL_NONDETERMINISM_SAME_GRAPH_'+arm+str(brep)+str(beam))
                pergraph_metrics={'arm':arm,'build_rep':brep,'beam':beam,
                   'graph_sha':rows[(arm,brep)]['graph_sha'],
                   'recall_at10':statistics.mean(recalls),
                   'qps_median_repeated_search':statistics.median(q['qps'] for q in x),
                   'avg_cmps':statistics.mean(q['avg_cmps'] for q in x),
                   'avg_visited':statistics.mean(q['avg_visited'] for q in x)}
                pergraph.append(pergraph_metrics);onebuild.append(pergraph_metrics)
            rollup[arm]={
                'mean_recall':statistics.mean(q['recall_at10'] for q in onebuild),
                'recall_min':min(q['recall_at10'] for q in onebuild),
                'recall_max':max(q['recall_at10'] for q in onebuild),
                'mean_qps':statistics.mean(q['qps_median_repeated_search'] for q in onebuild),
                'mean_latency_proxy_us':statistics.mean(1e6/q['qps_median_repeated_search'] for q in onebuild),
                'mean_cmps':statistics.mean(q['avg_cmps'] for q in onebuild),
                'mean_visited':statistics.mean(q['avg_visited'] for q in onebuild)}
        delta=rollup['fast']['mean_recall']-rollup['ctrl']['mean_recall']
        paired=[next(x for x in pergraph if x['beam']==beam and x['arm']=='fast' and x['build_rep']==rep)['recall_at10']-
                next(x for x in pergraph if x['beam']==beam and x['arm']=='ctrl' and x['build_rep']==rep)['recall_at10']
                for rep in (1,2,3)]
        bybeam.append({'beam':beam,'ctrl':rollup['ctrl'],'fast':rollup['fast'],
                       'fast_minus_ctrl_mean_recall':delta,
                       'fast_minus_ctrl_mean_recall_pp':100*delta,
                       'paired_graph_build_recall_deltas':paired,
                       'fast_over_ctrl_mean_qps_ratio':rollup['fast']['mean_qps']/rollup['ctrl']['mean_qps']})
        print('R90_P312_COMPARE',beam,'ctrl_recall',round(rollup['ctrl']['mean_recall'],7),
              'fast_recall',round(rollup['fast']['mean_recall'],7),
              'delta',round(delta,7),'ctrl_qps',round(rollup['ctrl']['mean_qps'],2),
              'fast_qps',round(rollup['fast']['mean_qps'],2),flush=True)
    # 0.001 absolute Recall is a conservative *descriptive warning* not a test of equality.
    alert=any(q['fast_minus_ctrl_mean_recall']<-.001 for q in bybeam)
    report={'status':'QUALITY_SCREEN_ALERT_RECALL_DROP' if alert else 'QUALITY_SCREEN_NO_LARGE_RECALL_DROP',
            'audit':'PASS_12_NATIVE_SEARCH_RUNS_10KQ_5_BEAMS',
            'dataset':'SIFT1M','search_query_count':10000,'k':10,
            'graph_build_threads':4,'search_threads':1,'search_cpu_affinity':'0',
            'beams':list(BEAMS),'search_reps_per_graph':2,'independent_graphs_per_arm':3,
            'source_search_manifest_sha':sha(manifest),'sources':source,
            'recall_screen_margin_absolute':.001,'not_formal_noninferiority':True,
            'not_matched_recall_latency':True,'by_beam':bybeam,'per_graph_beam':pergraph,
            'limitations':['Graph H17 itself changes with four BUILD threads; do not demand byte SHA parity',
                           'Do not count two SEARCH repeats as six independent graph builds',
                           'Fixed beam is not matched-Recall latency; QPS is workload/CPU/cache sensitive',
                           'An exploratory 0.001 Recall warning threshold is NOT a formal equivalence test',
                           'No computation/assignment D6 counters; no claim about 10M or dataset generality']}
    out=OUT/'search_quality_summary.json'
    check(not out.exists() and not out.is_symlink(),'AUDIT_OUTPUT_ALREADY_EXISTS')
    with out.open('x',encoding='utf-8') as f:json.dump(report,f,indent=2,sort_keys=True);f.write('\n')
    print('R90_P312_AUDIT_PASS_12SEARCH_10KQ',report['status'],flush=True)
    print('R90_P312_REPORT',out,flush=True)

def main():
    a=argparse.ArgumentParser(description=__doc__)
    a.add_argument('phase',choices=('selftest','preflight','pilot','audit'))
    args=a.parse_args()
    {'selftest':selftest,'preflight':preflight,'pilot':pilot,'audit':audit}[args.phase]()

if __name__=='__main__':
    try:main()
    except Exception as e:
        print('R90_P312_HOLD',repr(e),file=sys.stderr,flush=True)
        sys.exit(2)
