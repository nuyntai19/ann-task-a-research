#!/usr/bin/env python3
"""R90-P3.9: pinned 4-CPU native BUILD comparison, H17 ctrl vs P3.8v2 FAST.

New independent output tree; all P3.8v2 source, binaries, and completed
1CPU evidence are read-only. Do not infer equal graph quality if native graph
bytes disagree at 4CPU. 100K 3-pair gate first, SIFT1M conditional.
"""
from __future__ import annotations
import argparse, hashlib, json, os, re, struct, subprocess, sys, time
from pathlib import Path

HOME=Path.home();ROOT=HOME/'ann-task-a';R90=ROOT/'experiments/R90'
P38=R90/'r90_p38_h17_top2_prefilter_native_v2'
P38_SCRIPT=HOME/'Downloads/r90_p38_h17_top2_prefilter_native_v2.py'
H17=ROOT/'experiments/H17/phase3_top2_e2e/PiPNN-top2'
OUT=R90/'r90_p39_h17_fastv2_4cpu_native_v1'
DATA={100000:(ROOT/'data/sift100k.fbin','e50ff1bc34bcc6d1c97dd001023c09a666971cde64605cc06671ed8a8ff1ed12'),
      1000000:(ROOT/'data/sift1m.fbin','8c7b3d999ba3133f865af72df078f77c2d248fdb80571d7ea1f1bb8e1750658e')}
P38_SCRIPT_SHA='6d4c8728fc7a4df449c2ffb68b6471c516270fd91b11fb7e18240c3e7a911515'
H17_UTILS_SHA='b4a7e39a1ddf6c9f41f136360773aa9aef50ae7d19921b0b49b6422408c4c520'
ELF_SHA={'ctrl':'92c22ad5d9d9022860725329ff097784e7c8a649460d03dd343cdb6adb90363e',
         'fast':'ab4a0c678b3a71b2896d6f4d4339131705a1758b0c5398ed8ac32dd656cd7e91'}
CPUS=(0,2,4,6);AFF=','.join(map(str,CPUS));THREADS=4
WALL_MIN_GAIN=1.;AVG_MIN_GAIN=2.

def ck(cond,name):
    if not cond:raise RuntimeError('R90_P39_HOLD_'+name)

def sha(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda:f.read(4<<20),b''):h.update(b)
    return h.hexdigest()

def elf(arm):
    return P38/'build'/arm/'algorithms/PipNN/neighbors-pipnn_FLOAT_T_EUCLIDEAN'

def provenance(full=False):
    ck(P38_SCRIPT.is_file() and sha(P38_SCRIPT)==P38_SCRIPT_SHA,'P38_SCRIPT_SHA')
    p=H17/'algorithms/PipNN/pipnn_utils.h'
    ck(p.is_file() and sha(p)==H17_UTILS_SHA,'H17_UTILS_SHA')
    for arm in ELF_SHA:
        e=elf(arm)
        ck(e.is_file() and os.access(e,os.X_OK) and sha(e)==ELF_SHA[arm],'ELF_'+arm)
    allowed=os.sched_getaffinity(0)
    ck(all(x in allowed for x in CPUS),'AFFINITY_0_2_4_6_NOT_FULLY_ALLOWED')
    cores=[]
    for cpu in CPUS:
        p=Path(f'/sys/devices/system/cpu/cpu{cpu}/topology')
        ck((p/'core_id').is_file() and (p/'physical_package_id').is_file(),'CPU_TOPOLOGY_UNREADABLE')
        cores.append((int((p/'physical_package_id').read_text()),int((p/'core_id').read_text())))
    ck(len(set(cores))==THREADS,'AFFINITY_SHARED_PHYSICAL_CORE')
    for n in ([100000,1000000] if full else [100000]):
        p,d=DATA[n]
        ck(p.is_file() and p.stat().st_size==8+n*128*4 and sha(p)==d,'BASE_SHA_'+str(n))
    prior=P38/'result_manifest_1m.json'
    ck(prior.is_file(),'P38_1CPU_1M_EVIDENCE_MISSING')
    old=json.loads(prior.read_text())
    ck(old.get('status')=='PASS_1M_3PAIRS' and len(old.get('runs',[]))==14,'P38_PRIOR_STATE')
    for arm in ELF_SHA:ck(old['elf_sha'].get(arm)==ELF_SHA[arm],'P38_PRIOR_ELF_SHA_'+arm)
    ck(old.get('script_sha')==P38_SCRIPT_SHA,'P38_PRIOR_SCRIPT_SHA')
    return {'scripts':{'P39':sha(Path(__file__).resolve()),'P38':P38_SCRIPT_SHA},
            'H17_utils_sha':H17_UTILS_SHA,'ELF':ELF_SHA,'affinity':AFF,'topology_cores':cores,
            'PARLAY_NUM_THREADS':THREADS,'OMP_NUM_THREADS':THREADS,
            'base_sha':{str(n):DATA[n][1] for n in ([100000,1000000] if full else [100000])},
            'P38_prior_manifest_sha':sha(prior)}

def save(path,obj):
    tmp=path.with_suffix(path.suffix+'.part')
    ck(not tmp.exists(),'JSON_TMP_ALREADY_EXISTS_'+str(tmp))
    with tmp.open('x') as f:json.dump(obj,f,indent=2,sort_keys=True);f.write('\n')
    tmp.replace(path)

def bcmd(arm,n,graph):
    return [str(elf(arm)),'-base_path',str(DATA[n][0]),'-graph_outfile',str(graph),
            '-num_clusters','2','-cluster_size','1024','-table_size','160',
            '-top_level_leaders','100','-fanout_scheme','10,3,1','-mst_deg','2',
            '-prune','1','-prune_all','1','-prune_degree','64',
            '-hash_bits','12','-alpha','1.1','-k','0']

def run(arm,n,rep):
    tag=f'{n}_{arm}_r{rep}'
    graph=OUT/'graphs'/(tag+'.graph');stdout=OUT/'logs'/(tag+'.stdout');timefile=OUT/'logs'/(tag+'.time')
    ck(not any(x.exists() or x.is_symlink() for x in (graph,stdout,timefile)),'RUN_OUTPUT_EXISTS_'+tag)
    env=os.environ.copy();env.update({'LC_ALL':'C','PARLAY_NUM_THREADS':'4','OMP_NUM_THREADS':'4'})
    args=['/usr/bin/time','-v','-o',str(timefile),'taskset','-c',AFF,*bcmd(arm,n,graph)]
    print('R90_P39_BUILD_START',tag,'affinity',AFF,flush=True)
    t0=time.perf_counter()
    with stdout.open('x') as f:
        x=subprocess.run(args,env=env,stdout=f,stderr=subprocess.STDOUT,check=False,timeout=3600)
    elapsed=time.perf_counter()-t0
    ck(x.returncode==0,'BUILD_EXIT_'+tag+'_'+str(x.returncode))
    ck(graph.is_file() and stdout.is_file() and timefile.is_file(),'MISSING_RUN_EVIDENCE_'+tag)
    with graph.open('rb') as f:ck(f.read(8)==struct.pack('<II',n,64),'GRAPH_HEADER_'+tag)
    timetext=timefile.read_text(errors='replace')
    def field(name):
        m=re.search(r'^\s*'+re.escape(name)+r':\s*([0-9.]+)',timetext,re.M)
        ck(m is not None,'RUSAGE_FIELD_'+name+'_'+tag)
        return float(m.group(1))
    ck('Exit status: 0' in timetext,'RUSAGE_EXIT_'+tag)
    row={'n':n,'arm':arm,'rep':rep,'wall_s':elapsed,'graph':str(graph),'graph_sha':sha(graph),
         'stdout':str(stdout),'stdout_sha':sha(stdout),'timefile':str(timefile),'timefile_sha':sha(timefile),
         'peak_rss_kib':int(field('Maximum resident set size (kbytes)')),
         'user_s':field('User time (seconds)'),'system_s':field('System time (seconds)'),
         'cpu_percent':field('Percent of CPU this job got'),
         'involuntary_context_switches':int(field('Involuntary context switches'))}
    print('R90_P39_BUILD_PASS',tag,'wall_s',round(elapsed,6),'graph_sha',row['graph_sha'],
          'rss_kib',row['peak_rss_kib'],'cpu_percent',row['cpu_percent'],flush=True)
    return row

def check_evidence(st,phase):
    ck(st['script_sha']==sha(Path(__file__).resolve()),'SCRIPT_DRIFT')
    ck(st['source']['H17_utils_sha']==H17_UTILS_SHA,'SOURCE_DRIFT')
    for arm in ELF_SHA:ck(sha(elf(arm))==ELF_SHA[arm],'ELF_DRIFT_'+arm)
    for row in st['runs']:
        for key,keyhash in [('graph','graph_sha'),('stdout','stdout_sha'),('timefile','timefile_sha')]:
            ck(sha(row[key])==row[keyhash],'EVIDENCE_DRIFT_'+row['arm']+'_'+key)
    for n in ([100000] if phase=='100k' else [100000,1000000]):
        for rep in (1,2,3):
            aa=[r for r in st['runs'] if r['n']==n and r['rep']==rep]
            ck(len(aa)==2 and {r['arm'] for r in aa}=={'ctrl','fast'},'MISSING_PAIR_'+str(n)+'_'+str(rep))
            ck(aa[0]['graph_sha']==aa[1]['graph_sha'],'GRAPH_PARITY_'+str(n)+'_'+str(rep))

def pairs(st,n):
    improvements=[]
    for rep in (1,2,3):
        c=next(r for r in st['runs'] if r['n']==n and r['rep']==rep and r['arm']=='ctrl')
        f=next(r for r in st['runs'] if r['n']==n and r['rep']==rep and r['arm']=='fast')
        g=(c['wall_s']-f['wall_s'])/c['wall_s']*100
        improvements.append(g)
        print('R90_P39_PAIR',n,rep,'ctrl_s',round(c['wall_s'],6),'fast_s',round(f['wall_s'],6),
              'pct_saving',round(g,4),'ctrl_rss',c['peak_rss_kib'],'fast_rss',f['peak_rss_kib'],flush=True)
    return improvements

def selftest():
    assert AFF=='0,2,4,6' and set(ELF_SHA)=={'ctrl','fast'}
    x=[{'n':100000,'arm':'ctrl','rep':i,'wall_s':10.0} for i in (1,2,3)]
    x+=[{'n':100000,'arm':'fast','rep':i,'wall_s':9.5} for i in (1,2,3)]
    for i in (1,2,3):
        a=next(q for q in x if q['arm']=='ctrl' and q['rep']==i)
        b=next(q for q in x if q['arm']=='fast' and q['rep']==i)
        assert (a['wall_s']-b['wall_s'])/a['wall_s']*100==5.0
    assert len(bcmd('fast',100000,Path('/tmp/graph')))>20
    print('R90_P39_SELFTEST_PASS_FLAGS_PARITY_PAIR_FORMULAE',flush=True)

def preflight():
    ck(not OUT.exists() and not OUT.is_symlink(),'OUT_EXISTS')
    m=provenance()
    print('R90_P39_PREFLIGHT_PINNED_SOURCE_ELF_DATA_AND_4_PHYSICAL_CORES_PASS',AFF,m['topology_cores'],flush=True)

def pilot100k():
    preflight()
    OUT.mkdir()
    for d in ('logs','graphs'):(OUT/d).mkdir()
    st={'phase':'RUNNING_100K','script_sha':sha(Path(__file__).resolve()),
        'source':provenance(),'scope':'4 threads CPU0,2,4,6; graph parity per pair required',
        'runs':[]}
    save(OUT/'progress_100k.json',st)
    for rep in (1,2,3):
        for arm in (('ctrl','fast') if rep%2 else ('fast','ctrl')):
            st['runs'].append(run(arm,100000,rep))
            save(OUT/'progress_100k.json',st)
        p=st['runs'][-2:]
        ck(p[0]['graph_sha']==p[1]['graph_sha'],'GRAPH_PARITY_100K_REP_'+str(rep))
        print('R90_P39_GRAPH_PARITY_PASS_100K_REP',rep,flush=True)
    st['phase']='PASS_100K_3PAIRS';save(OUT/'result_manifest_100k.json',st)
    audit100k()
    improvements=pairs(st,100000)
    print('R90_P39_100K_3PAIR_SHA_AND_GRAPH_PARITY_PASS',
          'mean_pct',round(sum(improvements)/3,4),flush=True)

def audit100k():
    st=json.loads((OUT/'result_manifest_100k.json').read_text())
    ck(st['phase']=='PASS_100K_3PAIRS' and len(st['runs'])==6,'100K_STATE')
    provenance()
    check_evidence(st,'100k')
    print('R90_P39_AUDIT_100K_SOURCE_ELF_GRAPH_RUSAGE_SHA_PASS',flush=True)

def pilot1m():
    audit100k()
    st=json.loads((OUT/'result_manifest_100k.json').read_text())
    improvements=pairs(st,100000)
    ck(min(improvements)>=WALL_MIN_GAIN and sum(improvements)/3>=AVG_MIN_GAIN,
       '1M_GATE_REQUIRES_ALL_100K_PAIRS_GE_1PCT_MEAN_GE_2PCT')
    ck(not (OUT/'progress_1m.json').exists() and not (OUT/'result_manifest_1m.json').exists(),
       '1M_OUTPUT_EXISTS')
    provenance(True)
    print('R90_P39_GO_SIFT1M_4CPU',improvements,flush=True)
    for rep in (1,2,3):
        for arm in (('ctrl','fast') if rep%2 else ('fast','ctrl')):
            st['runs'].append(run(arm,1000000,rep))
            save(OUT/'progress_1m.json',st)
        p=st['runs'][-2:]
        ck(p[0]['graph_sha']==p[1]['graph_sha'],'GRAPH_PARITY_1M_REP_'+str(rep))
        print('R90_P39_GRAPH_PARITY_PASS_1M_REP',rep,flush=True)
    st['phase']='PASS_1M_3PAIRS';save(OUT/'result_manifest_1m.json',st)
    audit1m()
    pairs(st,1000000)
    print('R90_P39_1M_3PAIR_BUILD_AND_GRAPH_SHA_PARITY_PASS',flush=True)

def audit1m():
    st=json.loads((OUT/'result_manifest_1m.json').read_text())
    ck(st['phase']=='PASS_1M_3PAIRS' and len(st['runs'])==12,'1M_STATE')
    provenance(True)
    check_evidence(st,'1m')
    print('R90_P39_AUDIT_1M_SOURCE_ELF_GRAPH_RUSAGE_SHA_PASS',flush=True)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('phase',choices=['selftest','preflight','pilot100k','audit100k','pilot1m','audit1m'])
    a=p.parse_args().phase
    {'selftest':selftest,'preflight':preflight,'pilot100k':pilot100k,'audit100k':audit100k,
     'pilot1m':pilot1m,'audit1m':audit1m}[a]()
if __name__=='__main__':
    try:main()
    except Exception as e:
        print('R90_P39_HOLD',type(e).__name__,str(e),file=sys.stderr,flush=True)
        sys.exit(2)
