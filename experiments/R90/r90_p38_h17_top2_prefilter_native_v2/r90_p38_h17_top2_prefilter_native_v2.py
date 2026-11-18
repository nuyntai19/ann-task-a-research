#!/usr/bin/env python3
"""R90 P3.8-v2: H17 Top2 Float Cutoff Rejection with packed fallback (BUILD).

A single mechanism only: skip packFloatAndInt and packed double comparisons
when current FP32 candidate is STRICTLY GREATER than second float cutoff.
Equal / negative zero / NaN / infinities fall back to exact original H17
packed comparison. No mirror, no SIMD, no graph-topology change.
Graph SHA parity checked on BOTH 10K and 100K; no speedup claim.

Commands: selftest, preflight, pilot10k, audit10k, pilot100k, audit100k, pilot1m, audit1m.
1M is automatically gated by paired graph parity and strong 100K speedup.
The original H17 tree, old result directories, and prior graph evidence are read
only. Writes only to a new R90 P3.8 directory. Graph SHA parity is mandatory.
"""
from __future__ import annotations
import argparse, hashlib, json, os, re, shutil, struct, subprocess, sys, time
from pathlib import Path

HOME=Path.home(); ROOT=HOME/'ann-task-a'; R90=ROOT/'experiments/R90'
H17=ROOT/'experiments/H17/phase3_top2_e2e/PiPNN-top2'
BASE=ROOT/'data/sift100k.fbin'
BASE1M=ROOT/'data/sift1m.fbin'
BASE1M_SHA='8c7b3d999ba3133f865af72df078f77c2d248fdb80571d7ea1f1bb8e1750658e'
OUT=R90/'r90_p38_h17_top2_prefilter_native_v2'
BASE_SHA='e50ff1bc34bcc6d1c97dd001023c09a666971cde64605cc06671ed8a8ff1ed12'
DEPS={
 'PARLAYLIB':(ROOT/'experiments/R86/r86_v1_2_builds/stock_off/_deps/parlaylib-src','51017699dcc421f80479cdb238d3092233ad0d26'),
 'EIGEN':(ROOT/'experiments/R86/r86_v1_2_builds/stock_off/_deps/eigen-src','3147391d946bb4b6c68edd901f2add6ac1f31f8c'),
 'ABSEIL-CPP':(ROOT/'experiments/R86/r86_v1_2_builds/stock_off/_deps/abseil-cpp-src','bc257a88f7c1939f24e0379f14a3589e926c950c'),
 'HIGHWAY':(ROOT/'experiments/H85/r85_0_matched_baseline/build_stock/_deps/highway-src','6bc2d47793bae9c521fb4150936669647700765d'),
 'GOOGLEBENCHMARK':(ROOT/'experiments/R86/r86_v1_2_builds/stock_off/_deps/googlebenchmark-src','d886e3177c5dc48f150fbfbf142be6e724a032a4'),
}
H17_UTILS_SHA='b4a7e39a1ddf6c9f41f136360773aa9aef50ae7d19921b0b49b6422408c4c520'
H17_BEGIN='''  if (MST_DEG == 2) {'''
H17_END='''  } else {
    std::vector<double> Q;'''
DECL_OLD='''      size_t count = 0;
      for (indexType j = 0; j < N; ++j) {'''
DECL_NEW='''      size_t count = 0;
      // R90-P3.8v2: cache raw FP32 value of second packed distance.
      float r90_second_cutoff = std::numeric_limits<float>::infinity();
      for (indexType j = 0; j < N; ++j) {'''
SELECT_OLD='''        float dist_ij = (i < j) ? dist_mat[j * N + i] : dist_mat[i * N + j];
        double d = packFloatAndInt(dist_ij, j);
        if (count == 0 || d < first) {
          second = first;
          first = d;
        } else if (count == 1 || d < second) {
          second = d;
        }
        if (count < 2) ++count;'''
SELECT_NEW='''        float dist_ij = (i < j) ? dist_mat[j * N + i] : dist_mat[i * N + j];
        // Strict FP32 rejection is safe: distinct IEEE float values have
        // much wider spacing than 11 low mantissa bits of packed double.
        // Equality, negative/positive zero, NaN and inf use packed fallback.
        if (count == 2 && dist_ij > r90_second_cutoff) continue;
        double d = packFloatAndInt(dist_ij, j);
        if (count == 0 || d < first) {
          second = first;
          first = d;
          r90_second_cutoff = static_cast<float>(second);
        } else if (count == 1 || d < second) {
          second = d;
          r90_second_cutoff = static_cast<float>(second);
        }
        if (count < 2) ++count;'''
EXPECTED_10K_GRAPH_SHA='59dd18da46ebb88604de4aa0d253df36b65ca5965de80af2f616d5f119a637a9'
EXPECTED_100K_GRAPH_SHA='8e42cae1fd72ceb2dd626a69cdffdc53604636c1debf84c887b52de6e8a1cc0e'
def ensure(q,msg):
    if not q:raise RuntimeError('R90_P38V2_HOLD_'+msg)
def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda:f.read(4<<20),b''):h.update(chunk)
    return h.hexdigest()
def only_replace(src,old,new,label):
    ensure(src.count(old)==1,'ANCHOR_'+label+'_'+str(src.count(old)))
    return src.replace(old,new,1)
def patch_h17(src):
    ensure(src.count(H17_BEGIN)==1 and src.count(H17_END)==1,'H17_TOP2_BRANCH_ANCHOR')
    a=src.index(H17_BEGIN);b=src.index(H17_END,a)
    sel=src[a:b]
    ensure(sel.count(DECL_OLD)==1,'H17_TOP2_DECL_ANCHOR')
    ensure(sel.count(SELECT_OLD)==1,'H17_TOP2_SELECT_ANCHOR')
    sel=sel.replace(DECL_OLD,DECL_NEW,1).replace(SELECT_OLD,SELECT_NEW,1)
    src=src[:a]+sel+src[b:]
    ensure(src[b:].count('VQPartialSort(')>=1,'H17_FALLBACK_ALTERED')
    ensure(src.count('r90_second_cutoff')==4,'CUT_OFF_INSERT_COUNT')
    return src

def cmd(args,log,timeout=3600,env=None):
    ensure(not log.exists() and not log.is_symlink(),'LOG_EXIST_'+log.name)
    with log.open('x',encoding='utf8') as f:
        p=subprocess.run(list(map(str,args)),stdout=f,stderr=subprocess.STDOUT,check=False,timeout=timeout,env=env)
    ensure(p.returncode==0,'COMMAND_EXIT_'+log.name+'_'+str(p.returncode))

def source_hashes(src):
    r={}
    for p in ('algorithms/PipNN/pipnn_utils.h','algorithms/PipNN/pipnn.h','CMakeLists.txt'):
        f=src/p;ensure(f.is_file(),'SOURCE_MISSING_'+p);r[p]=sha(f)
    return r

def preflight(fresh):
    ensure(BASE.is_file() and sha(BASE)==BASE_SHA,'SIFT100K_SHA')
    ensure(H17.is_dir() and (H17/'algorithms/PipNN/pipnn_utils.h').is_file(),'H17_SOURCE_ROOT')
    ensure(source_hashes(H17)['algorithms/PipNN/pipnn_utils.h']==H17_UTILS_SHA,'H17_UTILS_SHA_PIN')
    h=(H17/'algorithms/PipNN/pipnn_utils.h').read_text()
    p=patch_h17(h)
    ensure(h!=p,'NO_PATCH_DIFF')
    for name,(dep,commit) in DEPS.items():
        ensure(dep.is_dir(),'DEPENDENCY_MISSING_'+name)
        ensure((dep/'.git').exists() or (dep/'CMakeLists.txt').exists(),'DEPENDENCY_BAD_'+name)
        # FetchContent snapshots sometimes omit .git; hash provenance captured in manifest.
        if (dep/'.git').exists():
            g=subprocess.run(['git','-C',str(dep),'rev-parse','HEAD'],capture_output=True,text=True)
            ensure(g.returncode==0 and g.stdout.strip()==commit,'DEPENDENCY_COMMIT_'+name)
    cpus=os.sched_getaffinity(0)
    ensure(0 in cpus,'CPU_0_NOT_ALLOWED')
    if fresh:ensure(not OUT.exists() and not OUT.is_symlink(),'OUT_EXISTS')
    report={'H17_root':str(H17),'source_hashes':source_hashes(H17),'patched_utils_sha':hashlib.sha256(p.encode()).hexdigest(),
            'base_sha':BASE_SHA,'deps':{k:v[1] for k,v in DEPS.items()},'cpu':0}
    print('R90_P38V2_PREFLIGHT_H17_SOURCE_PATCH_BASE_DEP_CPU_PASS',report['source_hashes']['algorithms/PipNN/pipnn_utils.h'],flush=True)
    return report

def prefix(path):
    ensure(not path.exists(),'PREFIX_EXISTS')
    with BASE.open('rb') as f, path.open('xb') as o:
        ensure(len(f.read(8))==8,'BAD_INPUT_HEADER')
        o.write(struct.pack('<II',10000,128));n=10000*128*4
        while n:
            chunk=f.read(min(1<<20,n));ensure(bool(chunk),'PREFIX_EOF');o.write(chunk);n-=len(chunk)
    ensure(path.stat().st_size==8+10000*128*4,'PREFIX_SIZE')
    return sha(path)

def configure(arm):
    src=OUT/'source'/arm;bd=OUT/'build'/arm
    args=['cmake','-S',src,'-B',bd,'-DCMAKE_BUILD_TYPE=Release','-DCMAKE_CXX_FLAGS=-O3 -pthread',
          '-DCMAKE_EXPORT_COMPILE_COMMANDS=ON','-DFETCHCONTENT_FULLY_DISCONNECTED=ON']
    for k,(v,_) in DEPS.items():args.append('-DFETCHCONTENT_SOURCE_DIR_'+k+'='+str(v))
    cmd(args,OUT/'logs'/f'cmake_{arm}.log',1800)
    cmd(['cmake','--build',bd,'--target','neighbors-pipnn_FLOAT_T_EUCLIDEAN','--parallel','2'],OUT/'logs'/f'compile_{arm}.log',3600)
    exe=bd/'algorithms/PipNN/neighbors-pipnn_FLOAT_T_EUCLIDEAN'
    ensure(exe.is_file() and os.access(exe,os.X_OK),'ELF_'+arm)
    return sha(exe)

def bcmd(exe,base,graph):
    return [exe,'-base_path',base,'-graph_outfile',graph,'-num_clusters','2',
            '-cluster_size','1024','-table_size','160','-top_level_leaders','100',
            '-fanout_scheme','10,3,1','-mst_deg','2','-prune','1','-prune_all','1',
            '-prune_degree','64','-hash_bits','12','-alpha','1.1','-k','0']

def run(arm,n,rep,base):
    name=f'{n}_{arm}_r{rep}'
    exe=OUT/'build'/arm/'algorithms/PipNN/neighbors-pipnn_FLOAT_T_EUCLIDEAN'
    graph=OUT/'graphs'/f'{name}.graph';log=OUT/'logs'/f'{name}.stdout';rusage=OUT/'logs'/f'{name}.time'
    env=os.environ.copy();env.update({'LC_ALL':'C','PARLAY_NUM_THREADS':'1','OMP_NUM_THREADS':'1'})
    print('R90_P38V2_BUILD_START',name,flush=True)
    start=time.perf_counter()
    cmd(['/usr/bin/time','-v','-o',rusage,'taskset','-c','0',*bcmd(exe,base,graph)],log,3600,env)
    sec=time.perf_counter()-start
    ensure(graph.is_file() and graph.stat().st_size>8+4*n,'GRAPH_FILE_'+name)
    with graph.open('rb') as f: ensure(f.read(8)==struct.pack('<II',n,64),'GRAPH_HEADER_'+name)
    row=dict(arm=arm,n=n,rep=rep,wall_s=sec,graph_sha=sha(graph),graph=str(graph),graph_bytes=graph.stat().st_size,
             stdout_sha=sha(log),stdout=str(log),timefile_sha=sha(rusage),timefile=str(rusage))
    print('R90_P38V2_BUILD_PASS',name,'wall_s',round(sec,6),'graph_sha256',row['graph_sha'],flush=True)
    return row

def save(path,state):
    tmp=path.with_name(path.name+'.part')
    ensure(not tmp.exists(),'JSON_TMP_EXISTS')
    with tmp.open('x',encoding='utf8') as f:json.dump(state,f,sort_keys=True,indent=2);f.write('\n')
    tmp.replace(path)

def check_state(st):
    ensure(st['script_sha']==sha(Path(__file__).resolve()),'SCRIPT_CHANGED')
    ensure(st['source']['source_hashes']==source_hashes(H17),'H17_SOURCE_CHANGED')
    ensure(st['prefix_sha']==sha(OUT/'data/sift10k.fbin'),'PREFIX_CHANGED')
    for arm in ('ctrl','fast'):
        sh=source_hashes(OUT/'source'/arm)
        ensure(sh==st['arm_source'][arm],'ARM_SOURCE_CHANGED_'+arm)
        e=OUT/'build'/arm/'algorithms/PipNN/neighbors-pipnn_FLOAT_T_EUCLIDEAN'
        ensure(sha(e)==st['elf_sha'][arm],'ELF_CHANGED_'+arm)
    for row in st['runs']:
        ensure(sha(row['graph'])==row['graph_sha'],'GRAPH_SHA_DRIFT')
        ensure(sha(row['stdout'])==row['stdout_sha'],'STDOUT_DRIFT')
        ensure(sha(row['timefile'])==row['timefile_sha'],'TIMEFILE_DRIFT')
        partner=next((r for r in st['runs'] if r['n']==row['n'] and r['rep']==row['rep'] and r['arm']!=row['arm']),None)
        ensure(partner is not None and row['graph_sha']==partner['graph_sha'],'PARITY_'+str(row['n'])+'_'+str(row['rep']))

def pilot10k():
    source=preflight(True)
    OUT.mkdir();
    for x in ('logs','source','build','graphs','data'):(OUT/x).mkdir()
    st={'status':'RUNNING_10K','script_sha':sha(Path(__file__).resolve()),'source':source,
        'prefix_sha':prefix(OUT/'data/sift10k.fbin'),'arm_source':{},'elf_sha':{},'runs':[],
        'scope':'H17 C160 N2 1CPU, strict float cutoff rejection only (no matrix mirroring). Packed-double exact fallback, no dynamic D6 counters yet.'}
    save(OUT/'progress.json',st)
    for arm in ('ctrl','fast'):
        src=OUT/'source'/arm
        shutil.copytree(H17,src,symlinks=True,ignore=shutil.ignore_patterns('build','_deps','.git','*.graph','*.fbin','*.log'))
        if arm=='fast':
            file=src/'algorithms/PipNN/pipnn_utils.h';file.write_text(patch_h17(file.read_text()))
        st['arm_source'][arm]=source_hashes(src)
        st['elf_sha'][arm]=configure(arm)
        print('R90_P38V2_NATIVE_CPP_PASS',arm,st['elf_sha'][arm],flush=True)
        save(OUT/'progress.json',st)
    for arm in ('ctrl','fast'):
        st['runs'].append(run(arm,10000,1,OUT/'data/sift10k.fbin'))
        save(OUT/'progress.json',st)
    ensure(st['runs'][0]['graph_sha']==st['runs'][1]['graph_sha']==EXPECTED_10K_GRAPH_SHA,'GRAPH_PARITY_10K')
    st['status']='PASS_10K_PAIR'
    save(OUT/'result_manifest_10k.json',st)
    audit10k()
    print('R90_P38V2_10K_GRAPH_SHA_PARITY_PASS_READY_100K',flush=True)

def audit10k():
    preflight(False)
    f=OUT/'result_manifest_10k.json';ensure(f.is_file(),'10K_RESULT_MISSING')
    st=json.loads(f.read_text())
    ensure(st['status']=='PASS_10K_PAIR' and len(st['runs'])==2,'10K_STATE')
    check_state(st)
    print('R90_P38V2_AUDIT_10K_SOURCE_ELF_GRAPH_LOG_SHA_PASS',flush=True)

def pilot100k():
    audit10k()
    ensure(not (OUT/'result_manifest_100k.json').exists(),'100K_EXISTS')
    st=json.loads((OUT/'result_manifest_10k.json').read_text())
    for rep in (1,2,3):
        for arm in (('ctrl','fast') if rep%2 else ('fast','ctrl')):
            st['runs'].append(run(arm,100000,rep,BASE))
            save(OUT/'progress_100k.json',st)
        a,b=st['runs'][-2:];ensure(a['graph_sha']==b['graph_sha']==EXPECTED_100K_GRAPH_SHA,'GRAPH_PAIR_100K_'+str(rep))
        print('R90_P38V2_GRAPH_PARITY_PASS_100K_REP',rep,flush=True)
    st['status']='PASS_100K_3PAIRS';save(OUT/'result_manifest_100k.json',st)
    audit100k()
    for rep in (1,2,3):
        a=next(x for x in st['runs'] if x['n']==100000 and x['rep']==rep and x['arm']=='ctrl')
        b=next(x for x in st['runs'] if x['n']==100000 and x['rep']==rep and x['arm']=='fast')
        print('R90_P38V2_PAIR',rep,'ctrl_s',round(a['wall_s'],6),'fast_s',round(b['wall_s'],6),
              'pct',round(100*(b['wall_s']/a['wall_s']-1),4),flush=True)
    print('R90_P38V2_100K_3PAIR_BUILD_AND_GRAPH_SHA_PARITY_PASS',flush=True)

def audit100k():
    audit10k()
    p=OUT/'result_manifest_100k.json';ensure(p.is_file(),'100K_MISSING')
    st=json.loads(p.read_text());ensure(st['status']=='PASS_100K_3PAIRS' and len(st['runs'])==8,'100K_STATE')
    check_state(st)
    print('R90_P38V2_AUDIT_100K_3PAIR_SHA_PASS',flush=True)

def speedup_gate_1m(st):
    xs=[]
    for rep in (1,2,3):
        a=next(x for x in st['runs'] if x['n']==100000 and x['rep']==rep and x['arm']=='ctrl')
        b=next(x for x in st['runs'] if x['n']==100000 and x['rep']==rep and x['arm']=='fast')
        ensure(a['graph_sha']==b['graph_sha']==EXPECTED_100K_GRAPH_SHA,'SIFT100K_PINNED_GRAPH')
        xs.append(100.0*(a['wall_s']-b['wall_s'])/a['wall_s'])
    mean=sum(xs)/len(xs)
    ensure(min(xs)>=1.0 and mean>=2.0,'1M_GO_REQUIRES_ALL_3_PAIRS_GE_1PCT_AND_MEAN_GE_2PCT_'+str([round(x,4) for x in xs]))
    return xs

def pilot1m():
    audit100k()
    st=json.loads((OUT/'result_manifest_100k.json').read_text())
    improvements=speedup_gate_1m(st)
    ensure(BASE1M.is_file() and sha(BASE1M)==BASE1M_SHA,'SIFT1M_PINNED_SHA')
    ensure(BASE1M.stat().st_size==8+1000000*128*4,'SIFT1M_SIZE')
    ensure(not (OUT/'result_manifest_1m.json').exists(),'1M_RESULT_EXISTS')
    ensure(not (OUT/'progress_1m.json').exists(),'1M_PROGRESS_EXISTS')
    print('R90_P38V2_SIFT1M_GO_GATE_PASS', [round(x,4) for x in improvements],flush=True)
    for rep in (1,2,3):
        for arm in (('ctrl','fast') if rep%2 else ('fast','ctrl')):
            st['runs'].append(run(arm,1000000,rep,BASE1M))
            save(OUT/'progress_1m.json',st)
        a,b=st['runs'][-2:]
        ensure(a['graph_sha']==b['graph_sha'],'GRAPH_PAIR_1M_'+str(rep))
        print('R90_P38V2_GRAPH_PARITY_PASS_1M_REP',rep,flush=True)
    st['status']='PASS_1M_3PAIRS';save(OUT/'result_manifest_1m.json',st)
    audit1m()
    for rep in (1,2,3):
        a=next(x for x in st['runs'] if x['n']==1000000 and x['rep']==rep and x['arm']=='ctrl')
        b=next(x for x in st['runs'] if x['n']==1000000 and x['rep']==rep and x['arm']=='fast')
        print('R90_P38V2_1M_PAIR',rep,'ctrl_s',round(a['wall_s'],6),'fast_s',round(b['wall_s'],6),
              'pct',round(100*(b['wall_s']/a['wall_s']-1),4),flush=True)
    print('R90_P38V2_1M_3PAIR_BUILD_AND_GRAPH_SHA_PARITY_PASS',flush=True)

def audit1m():
    audit100k()
    p=OUT/'result_manifest_1m.json';ensure(p.is_file(),'1M_RESULT_MISSING')
    st=json.loads(p.read_text())
    ensure(st['status']=='PASS_1M_3PAIRS' and len(st['runs'])==14,'1M_STATE')
    ensure(BASE1M.is_file() and sha(BASE1M)==BASE1M_SHA,'1M_BASE_DRIFT')
    check_state(st)
    print('R90_P38V2_AUDIT_1M_3PAIR_SHA_PASS',flush=True)

def _packed(x,j):
    import struct
    bits=struct.unpack('<Q',struct.pack('<d',float(x)))[0]
    return struct.unpack('<d',struct.pack('<Q',(bits & ~2047)|(j&2047)))[0]

def _float32(x):
    import struct
    return struct.unpack('<f',struct.pack('<f',x))[0]

def _selection(xs,fast):
    import struct
    first=float('inf'); second=float('inf'); count=0;cutoff=float('inf')
    for j,x in enumerate(xs):
        if j==0: continue  # mimics i=0, j=0 self-exclusion
        if fast and count==2 and x>cutoff:continue
        d=_packed(x,j)
        if count==0 or d<first:
            second=first;first=d;cutoff=_float32(second)
        elif count==1 or d<second:
            second=d;cutoff=_float32(second)
        if count<2:count+=1
    return (struct.pack('<d',first),struct.pack('<d',second),count)

def selftest():
    import random,struct,math
    toy=(H17_BEGIN+'\n'+DECL_OLD+'\n'+SELECT_OLD+'\n'+H17_END+'\n  VQPartialSort(x,y,z);\n')
    p=patch_h17(toy)
    ensure(p.count('r90_second_cutoff')==4,'TEST_CODE_PATCH_COUNT')
    ensure(p.count('if (count == 2 && dist_ij > r90_second_cutoff) continue;')==1,'TEST_SKIP_ANCHOR')
    ensure(p.count('double d = packFloatAndInt(dist_ij, j);')==1,'TEST_PACK_FALLBACK')
    special=[0.0,-0.0,math.inf,-math.inf,math.nan,1.0,-1.0,1.0000001192092896,-1.0000001192092896,1e-40,-1e-40,1e-20,-1e-20,3.4028234663852886e38]
    rng=random.Random(555)
    for rep in range(1000):
        xs=[rng.choice(special) if rng.random()<.3 else _float32(rng.uniform(-200.,200.)) for i in range(192)]
        if rep%10==0:xs=[rng.choice(special)]*192
        a=_selection(xs,False);b=_selection(xs,True)
        ensure(a==b,'SELFTEST_PACKED_ORDER_SPECIAL_'+str(rep))
    print('R90_P38V2_SELFTEST_PASS_STRICT_FLOAT_REJECT_PACKED_FALLBACK_1000_SYNTHETIC_ROWS',flush=True)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('phase',choices=('selftest','preflight','pilot10k','audit10k','pilot100k','audit100k','pilot1m','audit1m'))
    a=p.parse_args().phase
    if a=='selftest':selftest()
    elif a=='preflight':preflight(True)
    elif a=='pilot10k':pilot10k()
    elif a=='audit10k':audit10k()
    elif a=='pilot100k':pilot100k()
    elif a=='audit100k':audit100k()
    elif a=='pilot1m':pilot1m()
    else:audit1m()
if __name__=='__main__':
    try:main()
    except Exception as e:
        print('R90_P38V2_HOLD',type(e).__name__,str(e),file=sys.stderr,flush=True)
        raise SystemExit(2)
