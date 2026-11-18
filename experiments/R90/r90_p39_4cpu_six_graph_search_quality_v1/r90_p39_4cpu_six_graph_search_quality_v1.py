#!/usr/bin/env python3
"""R90-P3.9: existing six 4CPU SIFT100K graphs; READ-ONLY native R70 Search screen.

Runs the pinned H70 r70_graph_recall native evaluator on the six existing
H17/Fast graphs, with the SAME pinned 300 SIFT100K heldout queries+exact GT.
Reports Recall@10, QPS, visited/comparisons at five fixed beams. Never BUILDs.
Three independent graph builds per arm; repeated SEARCH measures timing noise.
This is an exploratory 300-query screen, NOT formal Recall non-inferiority,
nor matched-recall latency evidence; do not conclude 4CPU quality equality.
"""
from __future__ import annotations
import argparse, csv, hashlib, importlib.util, json, math, os, pathlib, re, shutil, statistics, struct, subprocess, sys, tempfile

HOME=pathlib.Path.home()
ROOT=HOME/'ann-task-a'
P39=ROOT/'experiments/R90/r90_p39_h17_fastv2_4cpu_native_v1'
PROBE=ROOT/'experiments/R90/r90_p39_4cpu_within_arm_probe_v1'
OUT=ROOT/'experiments/R90/r90_p39_4cpu_six_graph_search_quality_v1'
PROBE_SRC=HOME/'Downloads/r90_p39_4cpu_within_arm_probe_v1.py'
PROBE_SHA='d3e352bef37cd8a5c1dcfe16a8d6cf4c8aaecf3903b072ee5c7d2805ab7bbd60'
BASE=ROOT/'data/sift100k.fbin'
QUERY=ROOT/'data/sift100k_queries_300.fbin'
GT=ROOT/'data/sift100k_gt300.ibin'
EVAL=ROOT/'experiments/H70/build-r70/algorithms/PipNN/r70_graph_recall'
SHA={
 'base':'e50ff1bc34bcc6d1c97dd001023c09a666971cde64605cc06671ed8a8ff1ed12',
 'query':'9e9328e3f0488840d3f12efcc3b0f6af940dd398fb7b6d178d72bd1e1c0f9d74',
 'gt':'e038aff5970977d0ee925b4357295bd81817b99b35e11bbab783fd64e0715e7f',
 'evaluator':'f3999051c6cc96434ea26d2faedd3ac632ed8d20be342e15c92fd4b905a33fe9',
}
BEAMS=(10,20,40,80,160)
ROW=re.compile(r'^R70_RECALL_ROW beam=(\d+) recall=([0-9.]+) qps=([0-9.]+) avg_cmps=([0-9.]+) avg_visited=([0-9.]+)\s*$',re.M)


def ck(cond,tag):
    if not cond:raise RuntimeError('R90_P39_SEARCH_HOLD_'+tag)

def sha(path):
    h=hashlib.sha256()
    with pathlib.Path(path).open('rb') as f:
        for b in iter(lambda:f.read(4<<20),b''):h.update(b)
    return h.hexdigest()

def module(path,name):
    spec=importlib.util.spec_from_file_location(name,str(path))
    ck(spec is not None and spec.loader is not None,'BAD_IMPORT_SPEC_'+name)
    v=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(v)
    return v

def parse(output):
    ck(output.count('R70_RECALL_EVAL_PASS')==1,'EVALUATOR_PASS_MARKER')
    matches=ROW.findall(output)
    ck(len(matches)==5,'EXPECTED_FIVE_BEAMS')
    out={}
    for exp,(beam,recall,qps,cmps,visited) in zip(BEAMS,matches):
        b=int(beam);r=float(recall);q=float(qps);c=float(cmps);v=float(visited)
        ck(b==exp and b not in out,'BEAM_ORDER')
        ck(all(map(math.isfinite,(r,q,c,v))) and 0<=r<=1 and q>0 and c>=0 and v>=0,'NONFINITE_OR_INVALID_METRIC')
        out[b]={'recall_at10':r,'qps':q,'avg_cmps':c,'avg_visited':v,'latency_proxy_us':1_000_000/q}
    return out

def atomic_json(path,body):
    tmp=path.with_suffix(path.suffix+'.part')
    ck(not (tmp.exists() or tmp.is_symlink()),'TEMP_FILE_EXISTS')
    with tmp.open('x') as f:json.dump(body,f,indent=2,sort_keys=True);f.write('\n')
    os.replace(tmp,path)

def graph_shape(p):
    s=p.stat().st_size
    ck(s>=8+4*100000 and (s-8)%4==0,'GRAPH_SIZE')
    with p.open('rb') as f:
        n,cap=struct.unpack('<II',f.read(8))
        ck(n==100000 and cap==64,'GRAPH_HEADER')
        total=0
        for b in iter(lambda:f.read(4*8192),b''):
            # degree portion only, stops cleanly at n entries
            want=min(100000-total, len(b)//4)
            if want:
                vals=struct.unpack('<'+'I'*want,b[:4*want]);ck(max(vals)<=cap,'GRAPH_DEGREE_GT_CAP')
                total+=want
            if total>=100000:break
    # full graph format length is asserted by audit of the original graphs
    ck(total==100000,'GRAPH_DEGREE_COUNT')

def preflight(check_output=True):
    ck(PROBE_SRC.is_file() and sha(PROBE_SRC)==PROBE_SHA,'PINNED_WITHIN_PROBE_SCRIPT_SHA')
    probemod=module(PROBE_SRC,'r90_within_probe_pinned')
    p39,d,prov,orig,old=probemod.load_inputs()
    manifest=PROBE/'build_manifest.json'
    report=PROBE/'within_arm_semantic_audit.json'
    ck(manifest.is_file() and report.is_file(),'PROBE_MANIFEST_OR_AUDIT_MISSING')
    st=json.loads(manifest.read_text()); audit=json.loads(report.read_text())
    ck(st.get('phase')=='COMPLETE_4_BUILDS_PENDING_SEMANTIC_AUDIT' and
       st.get('script_sha')==PROBE_SHA and st.get('original_progress_sha')==sha(P39/'progress_100k.json'),
       'WITHIN_PROBE_PROVENANCE')
    ck(audit.get('within_arm_100k_graph_varies') is True and len(audit.get('pairs',{}))==9,
       'SIX_GRAPH_SEMANTIC_AUDIT_STATE')
    ck(audit.get('input_graph_sha',{}) and len(audit['input_graph_sha'])==6,
       'MISSING_ALL_SIX_GRAPH_SHA')
    ck(len(st.get('runs',[]))==4,'NEW_FOUR_GRAPH_RUNS')
    for name,path in [('base',BASE),('query',QUERY),('gt',GT),('evaluator',EVAL)]:
        ck(path.is_file() and not path.is_symlink() and sha(path)==SHA[name],'INPUT_SHA_'+name)
    ck(os.access(EVAL,os.X_OK),'EVALUATOR_NOT_EXECUTABLE')
    ck(BASE.stat().st_size==8+100000*128*4 and QUERY.stat().st_size==8+300*128*4,
       'BASE_OR_QUERY_SHAPE')
    with QUERY.open('rb') as f:ck(struct.unpack('<II',f.read(8))==(300,128),'QUERY_HEADER')
    with GT.open('rb') as f:
        n,k=struct.unpack('<II',f.read(8))
    ck(n==300 and k>=10 and GT.stat().st_size>=8+n*k*4,'GT_SIZE')
    ck(shutil.which('taskset') is not None and 0 in os.sched_getaffinity(0),'CPU0_TASKSET_UNAVAILABLE')
    rows={('ctrl',1):orig['ctrl'],('fast',1):orig['fast']}
    for item in st['runs']:
        k=(item['arm'],item['rep'])
        ck(k not in rows and k[0] in ('ctrl','fast') and k[1] in (2,3),'BAD_BUILD_ID')
        rows[k]=item
    ck(len(rows)==6,'SIX_GRAPHS_REQUIRED')
    for (arm,rep),row in rows.items():
        path=pathlib.Path(row['graph'])
        ck(path.is_file() and not path.is_symlink() and sha(path)==row['graph_sha'],
           'GRAPH_SHA_'+arm+str(rep))
        ck(row['graph_sha']==audit['input_graph_sha'][f'{arm}_r{rep}'],
           'GRAPH_AUDIT_SHA_'+arm+str(rep))
        graph_shape(path)
    if check_output:
        ck(not (OUT.exists() or OUT.is_symlink()),'OUTPUT_EXISTS')
        ck(OUT.parent.is_dir(),'OUTPUT_PARENT')
    print('R90_P39_SEARCH_PREFLIGHT_SOURCE_6GRAPHS_BASE_QUERY_GT_EVAL_SHA_PASS',flush=True)
    return rows

def selftest():
    s='header\n'+''.join(f'R70_RECALL_ROW beam={b} recall=0.998000 qps=1234.5 avg_cmps=99 avg_visited=22\n' for b in BEAMS)+'R70_RECALL_EVAL_PASS\n'
    p=parse(s)
    ck(tuple(p)==BEAMS and p[10]['recall_at10']==.998 and p[160]['qps']==1234.5,'SELFTEST_PARSE')
    with tempfile.TemporaryDirectory() as d:
        q=pathlib.Path(d)/'q.json';atomic_json(q,{'a':1});ck(json.loads(q.read_text())=={'a':1},'SELFTEST_JSON')
    print('R90_P39_SEARCH_SELFTEST_PASS_BEAM_PARSER_AND_ATOMIC_OUTPUT',flush=True)

def pilot():
    rows=preflight()
    OUT.mkdir(mode=0o755)
    logs=OUT/'logs';logs.mkdir()
    state={'phase':'RUNNING','script_sha':sha(pathlib.Path(__file__).resolve()),
           'within_arm_audit_sha':sha(PROBE/'within_arm_semantic_audit.json'),
           'within_arm_manifest_sha':sha(PROBE/'build_manifest.json'),
           'data_sha':SHA,'search_affinity':'0','search_threads':1,'search_reps':2,
           'beams':list(BEAMS),'query_count':300,'k':10,'runs':[]}
    atomic_json(OUT/'progress.json',state)
    # Reverse arm order on second pass to reduce systematic order/caching effects.
    order=[(arm,rep,srep) for srep in (1,2) for rep in (1,2,3)
           for arm in (('ctrl','fast') if (rep+srep)%2==0 else ('fast','ctrl'))]
    env=os.environ.copy();env.update({'LC_ALL':'C','PARLAY_NUM_THREADS':'1','OMP_NUM_THREADS':'1'})
    for arm,rep,srep in order:
        tag=f'{arm}_build{rep}_search{srep}'
        log=logs/(tag+'.stdout')
        ck(not log.exists() and not log.is_symlink(),'SEARCH_LOG_EXISTS_'+tag)
        cmd=['taskset','-c','0',str(EVAL),str(rows[(arm,rep)]['graph']),str(BASE),str(QUERY),str(GT)]
        print('R90_P39_SEARCH_START',tag,flush=True)
        with log.open('x') as f:
            done=subprocess.run(cmd,env=env,stdout=f,stderr=subprocess.STDOUT,timeout=600,check=False)
        ck(done.returncode==0,'EVALUATOR_EXIT_'+tag+'_'+str(done.returncode))
        parsed=parse(log.read_text(errors='replace'))
        state['runs'].append({'arm':arm,'build_rep':rep,'search_rep':srep,
                              'graph_sha':rows[(arm,rep)]['graph_sha'],
                              'log':str(log),'log_sha':sha(log),'beams':parsed})
        atomic_json(OUT/'progress.json',state)
        print('R90_P39_SEARCH_PASS',tag,'beam160_recall',parsed[160]['recall_at10'],flush=True)
    ck(len(state['runs'])==12,'RUNS_12_REQUIRED')
    state['phase']='COMPLETE_12_SEARCH_RUNS'
    atomic_json(OUT/'search_manifest.json',state)
    print('R90_P39_SEARCH_PILOT_PASS_12_RUNS_5_BEAMS',flush=True)

def audit():
    rows=preflight(check_output=False)
    m=OUT/'search_manifest.json';ck(m.is_file(),'SEARCH_MANIFEST_MISSING')
    st=json.loads(m.read_text())
    ck(st.get('phase')=='COMPLETE_12_SEARCH_RUNS' and st.get('script_sha')==sha(pathlib.Path(__file__).resolve()) and
       st.get('within_arm_audit_sha')==sha(PROBE/'within_arm_semantic_audit.json') and
       st.get('within_arm_manifest_sha')==sha(PROBE/'build_manifest.json') and len(st.get('runs',[]))==12,
       'MANIFEST_DRIFT')
    seen=set(); rec={}
    for row in st['runs']:
        key=(row['arm'],row['build_rep'],row['search_rep'])
        ck(key not in seen and key[0] in ('ctrl','fast') and key[1] in (1,2,3) and key[2] in (1,2),'RUN_ID')
        seen.add(key)
        p=pathlib.Path(row['log'])
        ck(p.is_file() and not p.is_symlink() and p.resolve().parent==(OUT/'logs').resolve() and sha(p)==row['log_sha'],
           'SEARCH_LOG_SHA')
        ck(rows[(key[0],key[1])]['graph_sha']==row['graph_sha'],'GRAPH_SHA_RUN_BINDING')
        parsed=parse(p.read_text(errors='replace'))
        for beam in BEAMS:
            for field in ('recall_at10','qps','avg_cmps','avg_visited'):
                ck(abs(parsed[beam][field]-row['beams'][str(beam)][field])<1e-8,'EVAL_LOG_METRIC_DRIFT')
        rec[key]=parsed
    ck(len(seen)==12,'MISSING_RUNS')
    summary=[]; details=[]
    for b in BEAMS:
        stats={}
        for arm in ('ctrl','fast'):
            build_recalls=[]; build_qps=[]
            for rep in (1,2,3):
                recalls=[rec[(arm,rep,s)][b]['recall_at10'] for s in (1,2)]
                qps=[rec[(arm,rep,s)][b]['qps'] for s in (1,2)]
                ck(max(recalls)-min(recalls)<=1e-7,'RECALL_CHANGED_WITHIN_SAME_GRAPH')
                build_recalls.append(statistics.mean(recalls));build_qps.append(statistics.mean(qps))
                details.append({'arm':arm,'build_rep':rep,'beam':b,'recall_at10':build_recalls[-1],
                                'qps_mean_2_search':build_qps[-1]})
            stats[arm]={'mean_recall':statistics.mean(build_recalls),'recall_min':min(build_recalls),
                        'recall_max':max(build_recalls),'mean_qps':statistics.mean(build_qps),
                        'mean_latency_proxy_us':statistics.mean([1_000_000/q for q in build_qps])}
        diff=stats['fast']['mean_recall']-stats['ctrl']['mean_recall']
        summary.append({'beam':b,'ctrl':stats['ctrl'],'fast':stats['fast'],
                        'fast_minus_ctrl_mean_recall':diff,
                        'note':'Recall comparison SAME 300 queries, three independently built graphs each arm; not formal equivalence.'})
        print('R90_P39_SEARCH_COMPARE_BEAM',b,'ctrl_mean_recall',round(stats['ctrl']['mean_recall'],6),
              'fast_mean_recall',round(stats['fast']['mean_recall'],6),'difference',round(diff,6),flush=True)
    # Conservative descriptive 0.005 screen only, NOT a proof of quality equivalence.
    alert=any(x['fast_minus_ctrl_mean_recall'] < -.005 for x in summary)
    report={'status':'QUALITY_RECALL_SCREEN_ALERT' if alert else 'QUALITY_RECALL_SCREEN_NO_LARGE_DROP_300Q',
            'not_formal_noninferiority':True,'scope':'SIFT100K; 300 queries; GT10; 5 fixed beams; 3 independent 4CPU build graphs per arm; 2 1CPU search repeats each',
            'sources_sha':st['data_sha'],'search_manifest_sha':sha(m),'rows':summary,
            'build_details':details,'screen_margin_absolute_recall':.005,
            'limitations':['300 queries do not establish noninferiority at 1M or 10M',
                           'Five fixed beams are not matched-Recall latency interpolation',
                           'QPS depends on search worker/CPU and cache. Same-graph repeated search estimates noise.',
                           'Native ANN Search quality and QPS are NOT the same as graph multiset parity.']}
    out=OUT/'search_quality_summary.json';ck(not out.exists() and not out.is_symlink(),'AUDIT_EXISTS')
    with out.open('x') as f:json.dump(report,f,indent=2,sort_keys=True);f.write('\n')
    fields=['arm','build_rep','beam','recall_at10','qps_mean_2_search']
    with (OUT/'per_graph_beam.csv').open('x',newline='') as f:
        wr=csv.DictWriter(f,fieldnames=fields);wr.writeheader();wr.writerows(details)
    print('R90_P39_SEARCH_AUDIT_PASS_6_GRAPHS_12_SEARCH_RUNS',report['status'],flush=True)
    print('R90_P39_SEARCH_REPORT',out,flush=True)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('phase',choices=('selftest','preflight','pilot','audit'))
    phase=p.parse_args().phase
    {'selftest':selftest,'preflight':preflight,'pilot':pilot,'audit':audit}[phase]()

if __name__=='__main__':
    try:main()
    except Exception as e:
        print('R90_P39_SEARCH_HOLD',repr(e),file=sys.stderr,flush=True)
        sys.exit(2)
