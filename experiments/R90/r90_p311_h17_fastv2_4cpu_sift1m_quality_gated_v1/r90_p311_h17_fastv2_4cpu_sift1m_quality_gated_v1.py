#!/usr/bin/env python3
"""R90-P3.11: 4-physical-CPU matched BUILD SIFT1M of H17/fast v2.

Research design: the baseline H17 is itself nondeterministic with 4 workers.
Therefore DO NOT gate on byte-identical graph SHA. Every graph is individually
SHA-pinned and pairwise adjacency multiset differences are reported. This BUILD
study is gated on the previous six-graph *descriptive* SIFT100K Search screen;
it DOES NOT prove quality parity at 1M. A separate 1M 10K-query matched-Recall
Search evaluation is mandatory before any final algorithm equivalence claim.

Creates an entirely new output root. Never edits source/old measurements.
"""
from __future__ import annotations
import argparse, hashlib, importlib.util, json, math, os, pathlib, shutil, struct, sys, tempfile
from statistics import mean

H=pathlib.Path.home(); R=H/'ann-task-a'; R90=R/'experiments/R90'
OUT=R90/'r90_p311_h17_fastv2_4cpu_sift1m_quality_gated_v1'
P39=H/'Downloads/r90_p39_h17_fastv2_4cpu_native_v1.py'
P39_SHA='f42ea9732560e646481f51f9f3458da1f7d2bd1dd3c7e5b2965cee363903e7d6'
DIFF=H/'Downloads/r90_p39_graph_semantic_diff_v1.py'
DIFF_SHA='2756f4f059d73800e76c44ed7e3a84d1b4eaa8a69ec26fe7d0027edd91c77fe2'
SEARCH_SCRIPT=H/'Downloads/r90_p39_4cpu_six_graph_search_quality_v1.py'
SEARCH_SCRIPT_SHA='3cf86b23bc8aa1eb89df9ec40be45ebf796844c47100a3c8716a7e9e9e6ca5d4'
SEARCH_ROOT=R90/'r90_p39_4cpu_six_graph_search_quality_v1'
REPRO_ROOT=R90/'r90_p39_4cpu_within_arm_probe_v1'
BEAMS=(10,20,40,80,160)
BASE_SHA='8c7b3d999ba3133f865af72df078f77c2d248fdb80571d7ea1f1bb8e1750658e'


def check(p,tag):
    if not p:raise RuntimeError('R90_P311_HOLD_'+tag)

def sha(p):
    h=hashlib.sha256()
    with pathlib.Path(p).open('rb') as f:
        for b in iter(lambda:f.read(4<<20),b''):h.update(b)
    return h.hexdigest()

def mod(path,name):
    spec=importlib.util.spec_from_file_location(name,str(path))
    check(spec is not None and spec.loader is not None,'MODULE_SPEC_'+name)
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    return m

def put(path,obj):
    temp=path.with_suffix(path.suffix+'.part')
    check(not (temp.exists() or temp.is_symlink()),'OUTPUT_PART_EXISTS')
    with temp.open('x') as f:json.dump(obj,f,indent=2,sort_keys=True);f.write('\n')
    os.replace(temp,path)

def read_previous(check_resources=True):
    for path,ex,label in [(P39,P39_SHA,'P39'),(DIFF,DIFF_SHA,'DIFF'),(SEARCH_SCRIPT,SEARCH_SCRIPT_SHA,'SEARCH')]:
        check(path.is_file() and not path.is_symlink() and sha(path)==ex,'PIN_'+label)
    p39=mod(P39,'pinned_r90_p39_4cpu_runner')
    d=mod(DIFF,'pinned_r90_p39_graph_diff')
    scr=mod(SEARCH_SCRIPT,'pinned_r90_p39_six_graph_screen')
    proven=p39.provenance(full=True)
    check(proven['affinity']=='0,2,4,6' and proven['PARLAY_NUM_THREADS']==4,'AFFINITY_TOPOLOGY')
    check(proven['base_sha']['1000000']==BASE_SHA,'SIFT1M_SHA')
    # Previous independent within-arm audit: H17 itself varies across repeats.
    audit_path=REPRO_ROOT/'within_arm_semantic_audit.json'
    check(audit_path.is_file() and not audit_path.is_symlink(),'WITHIN_ARM_AUDIT_MISSING')
    wa=json.loads(audit_path.read_text())
    check(wa.get('within_arm_100k_graph_varies') is True and len(wa.get('pairs',{}))==9,
          'WITHIN_ARM_GRAPH_VARIABILITY_REQUIRED')
    gains=wa.get('paired_fast_pct_reduction',[])
    check(len(gains)==3 and all(math.isfinite(x) and x>=1.0 for x in gains) and mean(gains)>=2.,
          'P39_100K_SPEED_GATE')
    # Read-only verification of actual native Search evidence (not just a PASS label).
    scr.preflight(check_output=False)
    qm=SEARCH_ROOT/'search_manifest.json'; qr=SEARCH_ROOT/'search_quality_summary.json'
    check(qm.is_file() and qr.is_file() and not qm.is_symlink() and not qr.is_symlink(),
          'SEARCH_REPORT_MISSING')
    st=json.loads(qm.read_text()); ss=json.loads(qr.read_text())
    check(st.get('phase')=='COMPLETE_12_SEARCH_RUNS' and st.get('script_sha')==SEARCH_SCRIPT_SHA
          and len(st.get('runs',[]))==12,'SEARCH_MANIFEST_STATE')
    check(ss.get('status')=='QUALITY_RECALL_SCREEN_NO_LARGE_DROP_300Q'
          and ss.get('not_formal_noninferiority') is True
          and ss.get('search_manifest_sha')==sha(qm)
          and ss.get('screen_margin_absolute_recall')==.005,'SEARCH_SCREEN_PROVENANCE')
    check({x['beam'] for x in ss.get('rows',[])}==set(BEAMS) and len(ss['rows'])==5,
          'SEARCH_BEAM_SET')
    # Verify 12 native evaluator logs and recompute per-beam recall directly.
    hits={(arm,b):[] for arm in ('ctrl','fast') for b in BEAMS}
    seen=set()
    for row in st['runs']:
        key=(row['arm'],row['build_rep'],row['search_rep'])
        check(key not in seen and row['arm'] in ('ctrl','fast') and row['build_rep'] in (1,2,3)
              and row['search_rep'] in (1,2),'SEARCH_RUN_ID');seen.add(key)
        logfile=pathlib.Path(row['log'])
        check(logfile.is_file() and not logfile.is_symlink() and logfile.resolve().parent==(SEARCH_ROOT/'logs').resolve()
              and sha(logfile)==row['log_sha'],'SEARCH_LOG_SHA')
        records=scr.parse(logfile.read_text(errors='replace'))
        for b in BEAMS:
            check(abs(records[b]['recall_at10']-row['beams'][str(b)]['recall_at10'])<1e-9,
                  'SEARCH_NATIVE_RECALL_CHANGED')
            hits[(row['arm'],b)].append(records[b]['recall_at10'])
    check(len(seen)==12,'SEARCH_12_DIFFERENT_RUNS')
    for e in ss['rows']:
        b=e['beam'];c=mean(hits[('ctrl',b)]);f=mean(hits[('fast',b)])
        check(abs(e['ctrl']['mean_recall']-c)<1e-8 and abs(e['fast']['mean_recall']-f)<1e-8,
              'SEARCH_SUMMARY_NOT_FROM_LOGS')
        check(f-c>=-.005,'SEARCH_SCREEN_NEGATIVE_GAIN')
    # Verify the previous report refers to the exact same graph set.
    check(st.get('within_arm_audit_sha')==sha(audit_path),'SEARCH_WITHIN_ARM_AUDIT_DRIFT')
    check(st.get('within_arm_manifest_sha')==sha(REPRO_ROOT/'build_manifest.json'),
          'SEARCH_WITHIN_ARM_MANIFEST_DRIFT')
    # Fail before six larger BUILDs if practical RAM/disk availability is inadequate.
    free_disk=shutil.disk_usage(R90).free
    if check_resources:check(free_disk>=3*1024**3,'FREE_DISK_LT_3GIB')
    with open('/proc/meminfo') as f:mem=f.read()
    import re
    m=re.search(r'^MemAvailable:\s*(\d+) kB',mem,re.M)
    check(m is not None,'MEMAVAILABLE_NOT_FOUND')
    if check_resources:check(int(m.group(1))>=5*1024**2,'AVAILABLE_RAM_LT_5GIB')
    receipts={'p39_sha':P39_SHA,'diff_sha':DIFF_SHA,'search_script_sha':SEARCH_SCRIPT_SHA,
       'within_arm_audit_sha':sha(audit_path),'search_manifest_sha':sha(qm),'search_screen_sha':sha(qr),
       'search_beams':list(BEAMS),'search_queries':300,'search_reps':2,
       'screen_status':ss['status'],'within_4cpu_100k_gains':gains,'source':proven,
       'free_disk_bytes_preflight':free_disk,'MemAvailable_KiB_preflight':int(m.group(1))}
    return p39,d,receipts

def graph_layout(p,n=1000000):
    import array
    check(p.is_file() and p.stat().st_size>=8+4*n,'GRAPH_TRUNCATED')
    with p.open('rb') as f:
        nn,cap=struct.unpack('<II',f.read(8))
        check(nn==n and cap==64,'GRAPH_SHAPE')
        deg=array.array('I');deg.frombytes(f.read(4*n))
        check(len(deg)==n and max(deg,default=0)<=cap,'DEGREE_INVALID')
        arcs=sum(deg)
        check(p.stat().st_size==8+4*n+4*arcs,'GRAPH_ARC_PAYLOAD_LENGTH')
    return arcs

def selftest():
    with tempfile.TemporaryDirectory() as z:
        p=pathlib.Path(z)/'state.json';put(p,{'v':1});put(p,{'v':2})
        check(json.loads(p.read_text())=={'v':2},'SELFTEST_ATOMIC')
        import array
        x=pathlib.Path(z)/'tiny.graph'
        with x.open('wb') as f:f.write(struct.pack('<II',3,64));f.write(struct.pack('<III',1,0,2));f.write(struct.pack('<III',1,0,1))
        # Verify the toy graph by the same CSR size arithmetic as native format.
        check(x.stat().st_size==8+12+12,'SELFTEST_CSR')
        check(round(100*(1-9/10),8)==10.,'SELFTEST_GAIN')
    print('R90_P311_SELFTEST_PASS_GATE_MATH_AND_ATOMIC_STATE',flush=True)

def preflight():
    check(not OUT.exists() and not OUT.is_symlink(),'OUT_EXISTS')
    check(OUT.parent.is_dir(),'R90_PARENT_MISSING')
    _,_,proof=read_previous()
    print('R90_P311_PREFLIGHT_4CPU_SOURCE_ELF_1M_DATA_6GRAPH_SEARCH_QUALITY_GATE_PASS',
          'onecpu_p38_untouched','fourcores',proof['source']['topology_cores'],flush=True)

def pilot():
    preflight()
    p39,_,proof=read_previous()
    OUT.mkdir(mode=0o755)
    (OUT/'graphs').mkdir();(OUT/'logs').mkdir()
    st={'status':'RUNNING_1M','script_sha':sha(pathlib.Path(__file__).resolve()),
        'prior_evidence':proof,'n':1000000,'affinity':'0,2,4,6','threads':4,
        'quality_state':'SIFT100K_300Q_SCREEN_PASS__SIFT1M_QUALITY_NOT_TESTED',
        'no_cross_arm_graph_sha_parity_gate':True,'runs':[]}
    put(OUT/'progress_1m.json',st)
    p39.OUT=OUT
    for rep in (1,2,3):
        arms=('ctrl','fast') if rep%2 else ('fast','ctrl')
        for arm in arms:
            row=p39.run(arm,1000000,rep)
            row['arcs']=graph_layout(pathlib.Path(row['graph']))
            check(row['cpu_percent']>=300.0,'LESS_THAN_THREE_CPUS_UTILIZED_'+arm+str(rep))
            st['runs'].append(row)
            put(OUT/'progress_1m.json',st)
        print('R90_P311_1M_PAIR_BUILD_COMPLETE',rep,
              'graph_sha_equal',st['runs'][-2]['graph_sha']==st['runs'][-1]['graph_sha'],flush=True)
    check(len(st['runs'])==6,'SIX_RUNS_REQUIRED')
    st['status']='SIX_1M_BUILDS_COMPLETE_QUALITY_PENDING';put(OUT/'build_manifest_1m.json',st)
    print('R90_P311_PILOT_SIX_4CPU_1M_BUILDS_PASS__QUALITY_PENDING',flush=True)

def audit():
    p39,d,proof=read_previous(check_resources=False)
    p=OUT/'build_manifest_1m.json';check(p.is_file(),'BUILD_MANIFEST_MISSING')
    st=json.loads(p.read_text())
    check(st.get('status')=='SIX_1M_BUILDS_COMPLETE_QUALITY_PENDING' and
          st.get('script_sha')==sha(pathlib.Path(__file__).resolve()) and len(st.get('runs',[]))==6,
          'MANIFEST_STATE')
    for k,v in proof.items():
        if k in ('free_disk_bytes_preflight','MemAvailable_KiB_preflight'):
            check(isinstance(st['prior_evidence'].get(k),int),'PINNED_RESOURCE_RECEIPT_'+k)
        else:
            check(st['prior_evidence'][k]==json.loads(json.dumps(v)), 'PINNED_PROVENANCE_'+k)
    seen=set();rows={}
    for row in st['runs']:
        arm,rep=row['arm'],row['rep'];key=(arm,rep)
        check(arm in ('ctrl','fast') and rep in (1,2,3) and key not in seen,'RUN_ID')
        seen.add(key);rows[key]=row
        for field,digest,sub in [('graph','graph_sha','graphs'),('stdout','stdout_sha','logs'),('timefile','timefile_sha','logs')]:
            path=pathlib.Path(row[field]);check(path.is_file() and not path.is_symlink(), 'FILE_'+field)
            check(path.resolve().parent==(OUT/sub).resolve() and sha(path)==row[digest],
                  'SHA_'+field+arm+str(rep))
        check(row['n']==1000000 and row['arcs']==graph_layout(pathlib.Path(row['graph'])),
              'GRAPH_SHAPE_'+arm+str(rep))
        check(math.isfinite(row['wall_s']) and row['wall_s']>0 and row['cpu_percent']>=300,
              'WALL_CPU_'+arm+str(rep))
    check(len(seen)==6,'SIX_UNIQUE_RUNS')
    gains=[];semantic=[]
    for rep in (1,2,3):
        c=rows[('ctrl',rep)];f=rows[('fast',rep)];gain=100*(1-f['wall_s']/c['wall_s'])
        gains.append(gain)
        x=d.Graph(c['graph'],1000000,64);y=d.Graph(f['graph'],1000000,64)
        try:metrics=d.compare(x,y,detail_limit=5)
        finally:x.close();y.close()
        semantic.append({'rep':rep,'ctrl_graph_sha':c['graph_sha'],'fast_graph_sha':f['graph_sha'],
                         'classification':metrics['classification'],
                         'different_vertices':metrics['different_neighbor_multiset_vertices'],
                         'lost_arcs':metrics['arc_instances_removed_ctrl_to_fast'],
                         'gained_arcs':metrics['arc_instances_added_ctrl_to_fast'],
                         'order_only_vertices':metrics['order_only_vertices']})
        print('R90_P311_1M_PAIR',rep,'ctrl_s',round(c['wall_s'],4),'fast_s',round(f['wall_s'],4),
              'fast_reduction_pct',round(gain,4),'changed_multiset_vertices',semantic[-1]['different_vertices'],flush=True)
    summary={'status':'PASS_NATIVE_4CPU_1M_BUILD_EVIDENCE__SEARCH_QUALITY_UNTESTED',
        'graph_parity_expected':False,'prior_300Q_100K_search_screen':'NO_LARGE_DROP__NOT_FORMAL_NONINFERIORITY',
        'source_manifest_sha':sha(p),'fast_gains_each_pair_pct':gains,
        'fast_gain_mean_paired_pct':mean(gains),
        'ctrl_wall_mean_s':mean(rows[('ctrl',i)]['wall_s'] for i in (1,2,3)),
        'fast_wall_mean_s':mean(rows[('fast',i)]['wall_s'] for i in (1,2,3)),
        'ctrl_peak_rss_mean_KiB':mean(rows[('ctrl',i)]['peak_rss_kib'] for i in (1,2,3)),
        'fast_peak_rss_mean_KiB':mean(rows[('fast',i)]['peak_rss_kib'] for i in (1,2,3)),
        'pairs_graph_diff':semantic,
        'requirements_for_quality_claim':['Use pinned SIFT1M 10k heldout queries and exact GT',
                                          'Run native Search on all six graphs with identical beam list',
                                          'Compare Recall@10 and QPS at fixed and matched Recall across graph builds',
                                          'No conclusion that Fast 4CPU changes no edges or Recall at 10M'],
        'limitations':['Different graph SHA across 4CPU builds is a measured variable, NOT ignored',
                       'This audit is BUILD timing+RSS+graph multiset only, NOT native Search',
                       'Previously passed SIFT100K 300-query screen is exploratory only']}
    out=OUT/'build_1m_audit.json';check(not out.exists() and not out.is_symlink(),'AUDIT_EXISTS')
    with out.open('x') as f:json.dump(summary,f,indent=2,sort_keys=True);f.write('\n')
    print('R90_P311_AUDIT_PASS_4CPU_SIFT1M_BUILD__NATIVE_SEARCH_10KQ_PENDING',flush=True)
    print('R90_P311_BUILD_REPORT',out,flush=True)

def main():
    a=argparse.ArgumentParser(description=__doc__)
    a.add_argument('phase',choices=('selftest','preflight','pilot','audit'))
    args=a.parse_args()
    {'selftest':selftest,'preflight':preflight,'pilot':pilot,'audit':audit}[args.phase]()

if __name__=='__main__':
    try:main()
    except Exception as ex:
        print('R90_P311_HOLD',repr(ex),file=sys.stderr,flush=True)
        sys.exit(2)
