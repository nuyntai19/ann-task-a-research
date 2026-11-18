#!/usr/bin/env python3
"""R90-P4: matched 4-physical-core MS-Turing1M BUILD: Stock OFF, H17, Fast v2.

Preserves all R86/R90 sources, binaries, graphs and historic results. Uses exactly
one frozen Stock OFF ELF (R86) and the existing CTRL and Fast ELFs (R90 P3.8v2).
Each arm is built 3 times with Latin-square run order and identical C160 K1024 N2
arguments. The 4CPU graph is intrinsically nondeterministic; never require graph
SHA equality between different builds. A follow-up 100K-query native Search study
is required before claiming quality equivalence on this dataset.

Phases: selftest, preflight, pilot, audit. New output dir only; no resume/overwrite.
"""
from __future__ import annotations
import argparse, array, hashlib, importlib.util, json, math, os, pathlib, re
import shutil, statistics, struct, subprocess, sys, tempfile, time

HOME=pathlib.Path.home(); ROOT=HOME/'ann-task-a'; R90=ROOT/'experiments/R90'; R86=ROOT/'experiments/R86'
OUT=R90/'r90_p4_msturing1m_stock_h17_fastv2_4cpu_build_v1'
BASE=ROOT/'data/MSTuring_1M_v1/base.1M.fbin'
QUERY=ROOT/'data/MSTuring_1M_v1/query.public.100K.fbin'
GT=ROOT/'data/MSTuring_1M_v1/groundtruth.public.100K.ibin'
DATA_PIN={
 'base':('44e83e1dd4c65999b75873101adc5ac06ca900d259a2befd05c2c3aa28ff4042',400000008,(1000000,100)),
 'query':('48d087a17bec15a5ec9ea526fe9bd14ac31bbbb5cd200817b341adbb77695644',40000008,(100000,100)),
 'gt':('fa5acf5ab262b42355296e99f920e6aa863f48820ca6f70fa37ca7966634c344',80000008,(100000,100))}
P38=R90/'r90_p38_h17_top2_prefilter_native_v2'
ELF={
 'stock':R86/'gates/highway_r85_four_binary_jvYREW/build_stock_off/algorithms/PipNN/neighbors-pipnn_FLOAT_T_EUCLIDEAN',
 'h17':P38/'build/ctrl/algorithms/PipNN/neighbors-pipnn_FLOAT_T_EUCLIDEAN',
 'fast':P38/'build/fast/algorithms/PipNN/neighbors-pipnn_FLOAT_T_EUCLIDEAN'}
ELF_SHA={
 'stock':'aa2d174ed063070045f1fbbc8051b1d97b851168b2f3bf53ee32215a867583be',
 'h17':'92c22ad5d9d9022860725329ff097784e7c8a649460d03dd343cdb6adb90363e',
 'fast':'ab4a0c678b3a71b2896d6f4d4339131705a1758b0c5398ed8ac32dd656cd7e91'}
P38_SCRIPT=HOME/'Downloads/r90_p38_h17_top2_prefilter_native_v2.py'
P38_SHA='6d4c8728fc7a4df449c2ffb68b6471c516270fd91b11fb7e18240c3e7a911515'
H17_SOURCE=ROOT/'experiments/H17/phase3_top2_e2e/PiPNN-top2/algorithms/PipNN/pipnn_utils.h'
H17_SOURCE_SHA='b4a7e39a1ddf6c9f41f136360773aa9aef50ae7d19921b0b49b6422408c4c520'
DIFF_SCRIPT=HOME/'Downloads/r90_p39_graph_semantic_diff_v1.py'
DIFF_SHA='2756f4f059d73800e76c44ed7e3a84d1b4eaa8a69ec26fe7d0027edd91c77fe2'
R86_MANIFEST=R86/'gates/highway_r85_four_binary_jvYREW/four_binary_manifest.json'
R86_MST_MANIFEST=R86/'msturing_1m_sixarm/formal_mst1m_v1/campaign_manifest.json'
CPU=(0,2,4,6); AFF=','.join(map(str,CPU)); N=1000000; CAP=64
ORDERS={1:('stock','h17','fast'),2:('fast','stock','h17'),3:('h17','fast','stock')}
FLAGS=('-num_clusters','2','-cluster_size','1024','-table_size','160',
 '-top_level_leaders','100','-fanout_scheme','10,3,1','-mst_deg','2',
 '-prune','1','-prune_all','1','-prune_degree','64',
 '-hash_bits','12','-alpha','1.1','-k','0')


def ck(ok,msg):
    if not ok:raise RuntimeError('R90_P4_HOLD_'+msg)

def sha(path):
    h=hashlib.sha256()
    with pathlib.Path(path).open('rb') as f:
        for b in iter(lambda:f.read(4<<20),b''):h.update(b)
    return h.hexdigest()

def safe_file(p):
    return p.is_file() and not p.is_symlink()

def save(p,obj):
    tmp=p.with_suffix(p.suffix+'.part')
    ck(not tmp.exists() and not tmp.is_symlink(),'PART_ALREADY_EXISTS_'+p.name)
    with tmp.open('x') as f:json.dump(obj,f,indent=2,sort_keys=True);f.write('\n')
    os.replace(tmp,p)

def stable_topology():
    ck(all(c in os.sched_getaffinity(0) for c in CPU),'CPU_AFFINITY_UNAVAILABLE')
    pair=[]
    for c in CPU:
        d=pathlib.Path(f'/sys/devices/system/cpu/cpu{c}/topology')
        ck((d/'physical_package_id').is_file() and (d/'core_id').is_file(),'CPU_TOPOLOGY_MISSING')
        pair.append((int((d/'physical_package_id').read_text()),int((d/'core_id').read_text())))
    ck(len(set(pair))==4,'CPU_NOT_FOUR_PHYSICAL_CORES')
    return pair

def data_shape(p,expected):
    with p.open('rb') as f: header=f.read(8)
    ck(len(header)==8 and struct.unpack('<II',header)==expected,'DATA_SHAPE_'+p.name)

def provenance(check_resource=True):
    ck(R90.is_dir(),'R90_DIR_NOT_FOUND')
    ck(safe_file(P38_SCRIPT) and sha(P38_SCRIPT)==P38_SHA,'P38_SCRIPT_SHA')
    ck(safe_file(H17_SOURCE) and sha(H17_SOURCE)==H17_SOURCE_SHA,'H17_SOURCE_SHA')
    ck(safe_file(DIFF_SCRIPT) and sha(DIFF_SCRIPT)==DIFF_SHA,'SEMANTIC_DIFF_SCRIPT_SHA')
    for arm,p in ELF.items():
        ck(safe_file(p) and os.access(p,os.X_OK) and sha(p)==ELF_SHA[arm],
           'ELF_SHA_'+arm)
    for name,p in (('base',BASE),('query',QUERY),('gt',GT)):
        digest,size,shape=DATA_PIN[name]
        ck(safe_file(p) and p.stat().st_size==size and sha(p)==digest,
           'DATA_SHA_'+name)
        data_shape(p,shape)
    ck(safe_file(R86_MANIFEST) and safe_file(R86_MST_MANIFEST),'R86_PROVENANCE_MISSING')
    r86=json.loads(R86_MANIFEST.read_text());mst=json.loads(R86_MST_MANIFEST.read_text())
    ck(r86['binaries']['stock_off']['sha256']==ELF_SHA['stock'],'R86_STOCK_ELF_MANIFEST_SHA')
    ck(mst['campaign']=='R86_MSTURING1M_FORMAL_OFF_3X5_V1' and
       mst['dataset_sha256']=={k:DATA_PIN[k][0] for k in DATA_PIN} and
       mst['binary_sha256']['stock']==ELF_SHA['stock'],
       'R86_MSTURING_MANIFEST_MISMATCH')
    topology=stable_topology()
    ck(shutil.which('taskset') and pathlib.Path('/usr/bin/time').is_file(), 'TASKSET_OR_TIME_MISSING')
    disk=shutil.disk_usage(R90).free
    mem=pathlib.Path('/proc/meminfo').read_text()
    mm=re.search(r'^MemAvailable:\s*(\d+) kB$',mem,re.M)
    ck(mm is not None,'MEMAVAILABLE_NOT_FOUND')
    mem_kib=int(mm.group(1))
    if check_resource:
        ck(disk >= 4*1024**3,'DISK_FREE_LT_4GIB')
        ck(mem_kib>=5*1024**2,'MEMAVAILABLE_LT_5GIB')
    return {'data_sha':{k:v[0] for k,v in DATA_PIN.items()},
            'elf_sha':dict(ELF_SHA), 'p38_script_sha':P38_SHA,
            'h17_source_sha':H17_SOURCE_SHA,'semantic_diff_script_sha':DIFF_SHA,
            'r86_stock_manifest_sha':sha(R86_MANIFEST),
            'r86_mst_campaign_manifest_sha':sha(R86_MST_MANIFEST),
            'cpus':list(CPU),'physical_core_identifiers':topology,
            'threads':4,'flags':list(FLAGS),
            'disk_free_preflight_bytes':disk,'MemAvailable_preflight_KiB':mem_kib,
            'cross_campaign_elf_note':'Stock ELF from R86 vs H17/Fast ELFs from R90; same current hardware, data and flags, not identical source vintages.'}

def graph_info(p):
    ck(safe_file(p) and p.stat().st_size>=8+4*N,'GRAPH_MISSING_OR_SHORT')
    with p.open('rb') as f:
        header=f.read(8);n,cap=struct.unpack('<II',header)
        ck((n,cap)==(N,CAP),'GRAPH_HEADER')
        deg=array.array('I');deg.frombytes(f.read(4*N))
    ck(len(deg)==N and max(deg,default=0)<=CAP,'GRAPH_DEGREES')
    arcs=sum(deg)
    ck(p.stat().st_size==8+4*N+4*arcs,'GRAPH_LENGTH_INVALID')
    return {'nodes':n,'max_degree':cap,'arcs':arcs,'bytes':p.stat().st_size,
            'max_observed_degree':max(deg,default=0)}

def run_build(arm,rep):
    tag=f'mst1m_{arm}_r{rep}';graph=OUT/'graphs'/(tag+'.graph');log=OUT/'logs'/(tag+'.stdout');tfile=OUT/'logs'/(tag+'.time')
    ck(not any(p.exists() or p.is_symlink() for p in (graph,log,tfile)),
       'RUN_OUTPUT_ALREADY_EXISTS_'+tag)
    command=[str(ELF[arm]),'-base_path',str(BASE),'-graph_outfile',str(graph),*FLAGS]
    env=os.environ.copy();env.update({'LC_ALL':'C','PARLAY_NUM_THREADS':'4','OMP_NUM_THREADS':'4'})
    full=['/usr/bin/time','-v','-o',str(tfile),'taskset','-c',AFF,*command]
    print('R90_P4_BUILD_START',tag,'cpus',AFF,flush=True)
    t0=time.perf_counter()
    with log.open('x') as f:
        proc=subprocess.run(full,env=env,stdout=f,stderr=subprocess.STDOUT,check=False,timeout=3600)
    elapsed=time.perf_counter()-t0
    ck(proc.returncode==0,'BUILD_FAILED_'+tag+'_'+str(proc.returncode))
    ck(safe_file(log) and safe_file(tfile),'RUN_LOG_MISSING_'+tag)
    t=tfile.read_text(errors='replace')
    def field(k):
        m=re.search(r'^\s*'+re.escape(k)+r':\s*([\d.]+)',t,re.M)
        ck(m is not None,'RUSAGE_'+k+'_'+tag)
        return float(m.group(1))
    ck('Exit status: 0' in t,'RUSAGE_EXIT_NONZERO_'+tag)
    gi=graph_info(graph)
    cpu=field('Percent of CPU this job got')
    ck(cpu>=300,'CPU_UTIL_BELOW_3_CORES_'+tag)
    rec={'arm':arm,'rep':rep,'dataset':'MSTuring1M','wall_s':elapsed,'cpu_pct':cpu,
         'peak_rss_kib':int(field('Maximum resident set size (kbytes)')),
         'user_s':field('User time (seconds)'),'sys_s':field('System time (seconds)'),
         'involuntary_context_switches':int(field('Involuntary context switches')),
         'graph':str(graph),'graph_sha':sha(graph),'graph_info':gi,
         'stdout':str(log),'stdout_sha':sha(log),
         'timefile':str(tfile),'timefile_sha':sha(tfile),
         'args':command,'env_threads':{'PARLAY_NUM_THREADS':'4','OMP_NUM_THREADS':'4'},
         'builder_sha':ELF_SHA[arm]}
    print('R90_P4_BUILD_PASS',tag,'wall_s',round(elapsed,6),
          'rss_kib',rec['peak_rss_kib'],'cpu_pct',cpu,
          'arcs',gi['arcs'],'graph_sha',rec['graph_sha'],flush=True)
    return rec

def load_manifest():
    p=OUT/'build_manifest.json'
    ck(safe_file(p),'BUILD_MANIFEST_MISSING')
    obj=json.loads(p.read_text())
    ck(obj.get('status')=='NINE_4CPU_BUILDS_COMPLETE_QUALITY_PENDING' and
       obj.get('script_sha')==sha(pathlib.Path(__file__).resolve()) and
       len(obj.get('runs',[]))==9,'MANIFEST_STATE')
    return obj

def load_diff():
    spec=importlib.util.spec_from_file_location('pinned_semantic_diff',str(DIFF_SCRIPT))
    ck(spec is not None and spec.loader is not None,'SEMANTIC_DIFF_IMPORT_SPEC')
    obj=importlib.util.module_from_spec(spec);spec.loader.exec_module(obj)
    return obj

def paired_stats(st):
    d={}
    for arm in ELF:
        x=[next(v for v in st['runs'] if v['arm']==arm and v['rep']==rep) for rep in (1,2,3)]
        times=[v['wall_s'] for v in x]
        d[arm]={'wall_s':times,'mean_wall_s':statistics.mean(times),
                'median_wall_s':statistics.median(times),
                'sample_sd_wall_s':statistics.stdev(times),
                'rss_kib':[v['peak_rss_kib'] for v in x],
                'mean_rss_kib':statistics.mean(v['peak_rss_kib'] for v in x),
                'graph_sha':[v['graph_sha'] for v in x],
                'arcs':[v['graph_info']['arcs'] for v in x]}
    pairs={}
    for a,b in (('stock','h17'),('h17','fast'),('stock','fast')):
        x=[]
        for rep in (1,2,3):
            ca=next(v for v in st['runs'] if v['arm']==a and v['rep']==rep)
            cb=next(v for v in st['runs'] if v['arm']==b and v['rep']==rep)
            x.append({'rep':rep,'baseline_s':ca['wall_s'],'comparison_s':cb['wall_s'],
                      'time_saved_s':ca['wall_s']-cb['wall_s'],
                      'pct_saving':100*(1-cb['wall_s']/ca['wall_s'])})
        pairs[f'{a}_to_{b}']={'per_pair':x,
                            'mean_pair_pct_saving':statistics.mean(z['pct_saving'] for z in x),
                            'ratio_of_mean_wall_pct_saving':100*(1-d[b]['mean_wall_s']/d[a]['mean_wall_s'])}
    return d,pairs

def selftest():
    assert {a for order in ORDERS.values() for a in order}==set(ELF)
    assert all(len(set(x))==3 for x in ORDERS.values())
    assert {tuple(x[i] for x in ORDERS.values()) for i in range(3)}=={('stock','fast','h17'),('h17','stock','fast'),('fast','h17','stock')}
    assert len(FLAGS)==24
    with tempfile.TemporaryDirectory() as temp:
        p=pathlib.Path(temp)/'x.json';save(p,{'phase':'first'});save(p,{'phase':'second'})
        assert json.loads(p.read_text())=={'phase':'second'}
        old={'runs':[]}
        for rep in (1,2,3):
            for a,time_val in zip(ORDERS[rep],(12.,10.,9.)):
                old['runs'].append({'arm':a,'rep':rep,'wall_s':time_val,
                                    'peak_rss_kib':10000+rep,'graph_sha':f'{a}_{rep}',
                                    'graph_info':{'arcs':55}})
        stat,pairs=paired_stats(old)
        assert len(stat)==3 and len(pairs)==3
        assert math.isfinite(pairs['stock_to_fast']['ratio_of_mean_wall_pct_saving'])
    print('R90_P4_SELFTEST_PASS_LATIN_SQUARE_TIMES_AND_ATOMIC',flush=True)

def preflight():
    ck(not OUT.exists() and not OUT.is_symlink(),'OUTPUT_EXISTS')
    src=provenance(check_resource=True)
    print('R90_P4_PREFLIGHT_PINNED_MST1M_DATA_STOCK_H17_FAST_SHA_4_PHYSICAL_CORES_PASS',
          'cpus',AFF,'physical_cores',src['physical_core_identifiers'],flush=True)

def pilot():
    preflight()
    src=provenance(check_resource=True)
    OUT.mkdir(mode=0o755);(OUT/'graphs').mkdir();(OUT/'logs').mkdir()
    state={'status':'RUNNING','script_sha':sha(pathlib.Path(__file__).resolve()),
           'campaign':'R90_P4_MSTURING1M_THREE_ARM_4CPU_BUILD',
           'provenance':src,'Latin_square_orders':{str(k):v for k,v in ORDERS.items()},
           'quality_status':'NATIVE_MST1M_SEARCH_NOT_RUN','runs':[]}
    save(OUT/'progress.json',state)
    for rep in (1,2,3):
        for arm in ORDERS[rep]:
            row=run_build(arm,rep)
            state['runs'].append(row)
            save(OUT/'progress.json',state)
        print('R90_P4_REP_COMPLETE',rep,'arms',ORDERS[rep],flush=True)
    ck(len(state['runs'])==9,'NINE_RUNS_REQUIRED')
    state['status']='NINE_4CPU_BUILDS_COMPLETE_QUALITY_PENDING'
    save(OUT/'build_manifest.json',state)
    print('R90_P4_PILOT_NINE_BUILDS_COMPLETE__MST1M_SEARCH_PENDING',flush=True)

def audit():
    source=provenance(check_resource=False)
    st=load_manifest()
    frozen=st['provenance']
    # Resource observations differ with time, but hardware and hashes may not.
    for key in ('data_sha','elf_sha','p38_script_sha','h17_source_sha','semantic_diff_script_sha',
                'r86_stock_manifest_sha','r86_mst_campaign_manifest_sha',
                'cpus','physical_core_identifiers','threads','flags'):
        ck(frozen[key]==source[key],'PROVENANCE_DRIFT_'+key)
    seen=set()
    for row in st['runs']:
        k=(row['arm'],row['rep'])
        ck(row['arm'] in ELF and row['rep'] in (1,2,3) and k not in seen,
           'RUN_ID_DUPLICATE');seen.add(k)
        ck(row['builder_sha']==ELF_SHA[row['arm']] and row['cpu_pct']>=300,
           'RUSAGE_OR_ELF_'+str(k))
        for field,hashfield,directory in [('graph','graph_sha','graphs'),
                                         ('stdout','stdout_sha','logs'),
                                         ('timefile','timefile_sha','logs')]:
            p=pathlib.Path(row[field])
            ck(safe_file(p) and p.resolve().parent==(OUT/directory).resolve() and
               sha(p)==row[hashfield], 'EVIDENCE_SHA_'+str(k)+'_'+field)
        ck(graph_info(pathlib.Path(row['graph']))==row['graph_info'],
           'GRAPH_STRUCTURE_'+str(k))
    ck(seen=={(a,r) for a in ELF for r in (1,2,3)},'NINE_UNIQUE_ARMS_REPS')
    stats,pairs=paired_stats(st)
    diffmod=load_diff()
    comparisons=[]
    for rep in (1,2,3):
        by={r['arm']:r for r in st['runs'] if r['rep']==rep}
        for a,b in (('stock','h17'),('h17','fast'),('stock','fast')):
            ga=diffmod.Graph(pathlib.Path(by[a]['graph']),N,CAP)
            gb=diffmod.Graph(pathlib.Path(by[b]['graph']),N,CAP)
            try: result=diffmod.compare(ga,gb,detail_limit=3)
            finally:ga.close();gb.close()
            comparisons.append({'rep':rep,'baseline_arm':a,'comparison_arm':b,
                                'baseline_graph_sha':by[a]['graph_sha'],
                                'comparison_graph_sha':by[b]['graph_sha'],
                                'semantic':result})
            print('R90_P4_GRAPH_COMPARE',rep,a,'vs',b,result['classification'],
                  'changed_vertices',result['different_neighbor_multiset_vertices'],flush=True)
    out={'status':'PASS_9_NATIVE_4CPU_BUILDS__MST1M_SEARCH_NOT_EVALUATED',
         'dataset':'MSTuring1M','n':N,'d':100,
         'source_manifest_sha':sha(OUT/'build_manifest.json'),
         'script_sha':sha(pathlib.Path(__file__).resolve()),
         'arms':stats,'comparisons':pairs,'graph_semantic':comparisons,
         'quality_claim':'NONE: 100K-query native Search and matched Recall are pending',
         'limitations':['Stock ELF R86 vintage differs from H17/Fast ELF R90 vintage; same hardware, flags, data; record this explicitly.',
                        '4CPU graphs are nondeterministic; graph SHA differs may be due to build scheduling.',
                        'Instrumented D6 not used for timing.',
                        'Search quality, matched Recall and tail latency are not measured by this runner.']}
    save(OUT/'build_summary.json',out)
    for name,p in pairs.items():
        print('R90_P4_SPEED',name,'mean_paired_saving_pct',round(p['mean_pair_pct_saving'],4),
              'ratio_of_means_pct',round(p['ratio_of_mean_wall_pct_saving'],4),flush=True)
    print('R90_P4_AUDIT_PASS_9_BUILDS_SOURCE_ELF_DATA_GRAPH_AND_RUSAGE_SHA',flush=True)
    print('R90_P4_BUILD_SUMMARY',OUT/'build_summary.json',flush=True)

def main():
    a=argparse.ArgumentParser(description=__doc__)
    a.add_argument('phase',choices=('selftest','preflight','pilot','audit'))
    mode=a.parse_args().phase
    {'selftest':selftest,'preflight':preflight,'pilot':pilot,'audit':audit}[mode]()

if __name__=='__main__':
    try:main()
    except Exception as err:
        print('R90_P4_HOLD',type(err).__name__,str(err),file=sys.stderr,flush=True)
        sys.exit(2)
