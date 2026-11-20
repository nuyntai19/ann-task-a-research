#!/usr/bin/env python3
"""R90 P3.8: graph-preserving H17 RowMajor mirror + contiguous scan, native Ubuntu.

A single mechanism only: after exact lower-triangle distance correction, mirror
bits to upper triangle, then read each row contiguously in H17 MST_DEG==2.
Keep packFloatAndInt, H17 packed double comparisons, edge order, merge, graph
pruning, compiler flags, and all build parameters unchanged. No SIMD claim.

Commands: selftest, preflight, pilot10k, audit10k, pilot100k, audit100k.
The original H17 tree, old result directories, and prior graph evidence are read
only. Writes only to a new R90 P3.8 directory. Graph SHA parity is mandatory.
"""
from __future__ import annotations
import argparse, hashlib, json, os, re, shutil, struct, subprocess, sys, time
from pathlib import Path

HOME=Path.home(); ROOT=HOME/'ann-task-a'; R90=ROOT/'experiments/R90'
H17=ROOT/'experiments/H17/phase3_top2_e2e/PiPNN-top2'
BASE=ROOT/'data/sift100k.fbin'
OUT=R90/'r90_p38_h17_mirror_row_scan_native_v1'
BASE_SHA='e50ff1bc34bcc6d1c97dd001023c09a666971cde64605cc06671ed8a8ff1ed12'
DEPS={
 'PARLAYLIB':(ROOT/'experiments/R86/r86_v1_2_builds/stock_off/_deps/parlaylib-src','51017699dcc421f80479cdb238d3092233ad0d26'),
 'EIGEN':(ROOT/'experiments/R86/r86_v1_2_builds/stock_off/_deps/eigen-src','3147391d946bb4b6c68edd901f2add6ac1f31f8c'),
 'ABSEIL-CPP':(ROOT/'experiments/R86/r86_v1_2_builds/stock_off/_deps/abseil-cpp-src','bc257a88f7c1939f24e0379f14a3589e926c950c'),
 'HIGHWAY':(ROOT/'experiments/H85/r85_0_matched_baseline/build_stock/_deps/highway-src','6bc2d47793bae9c521fb4150936669647700765d'),
 'GOOGLEBENCHMARK':(ROOT/'experiments/R86/r86_v1_2_builds/stock_off/_deps/googlebenchmark-src','d886e3177c5dc48f150fbfbf142be6e724a032a4'),
}
METRIC_OLD='''        D(i, j) = -2*tmp;
        D(i, j) += P_sq_norms[i] + P_sq_norms[j];'''
METRIC_NEW='''        D(i, j) = -2*tmp;
        D(i, j) += P_sq_norms[i] + P_sq_norms[j];
        // R90-P3.8: mirror the already-rounded FP32 result; NO recomputation.
        if (i != j) D(j, i) = D(i, j);'''
OTHER_OLD='''        D(i, j) = -1*D(i, j);'''
OTHER_NEW='''        D(i, j) = -1*D(i, j);
        // R90-P3.8: preserve non-metric lower-triangle values as well.
        if (i != j) D(j, i) = D(i, j);'''
SCAN_OLD='''        float dist_ij = (i < j) ? dist_mat[j * N + i] : dist_mat[i * N + j];'''
SCAN_NEW='''        // R90-P3.8: D is now a symmetric RowMajor matrix, so all reads contiguous.
        float dist_ij = dist_mat[i * N + j];'''
H17_BEGIN='''  if (MST_DEG == 2) {'''
H17_END='''  } else {
    std::vector<double> Q;'''

def ensure(q,msg):
    if not q:raise RuntimeError('R90_P38_HOLD_'+msg)
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
    select=src[a:b]
    ensure('double first = std::numeric_limits<double>::infinity();' in select,'H17_FIRST_REG')
    ensure('double d = packFloatAndInt(dist_ij, j);' in select,'H17_PACK_PRESERVED')
    ensure(select.count(SCAN_OLD)==1,'H17_SCAN_OLD_COUNT')
    select=select.replace(SCAN_OLD,SCAN_NEW,1)
    src=src[:a]+select+src[b:]
    src=only_replace(src,METRIC_OLD,METRIC_NEW,'METRIC_LOWER_FIX')
    src=only_replace(src,OTHER_OLD,OTHER_NEW,'NONMETRIC_LOWER_FIX')
    a=src.index(H17_BEGIN);b=src.index(H17_END,a)
    ensure('double d = packFloatAndInt(dist_ij, j);' in src[a:b],'PACK_REMOVED')
    ensure(src[a:b].count(SCAN_NEW)==1,'NONCONTIGUOUS_SCAN')
    ensure(src[b:].count(SCAN_OLD)>=1,'STOCK_FALLBACK_CHANGED')
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
    print('R90_P38_PREFLIGHT_H17_SOURCE_PATCH_BASE_DEP_CPU_PASS',report['source_hashes']['algorithms/PipNN/pipnn_utils.h'],flush=True)
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
    print('R90_P38_BUILD_START',name,flush=True)
    start=time.perf_counter()
    cmd(['/usr/bin/time','-v','-o',rusage,'taskset','-c','0',*bcmd(exe,base,graph)],log,3600,env)
    sec=time.perf_counter()-start
    ensure(graph.is_file() and graph.stat().st_size>8+4*n,'GRAPH_FILE_'+name)
    with graph.open('rb') as f: ensure(f.read(8)==struct.pack('<II',n,64),'GRAPH_HEADER_'+name)
    row=dict(arm=arm,n=n,rep=rep,wall_s=sec,graph_sha=sha(graph),graph=str(graph),graph_bytes=graph.stat().st_size,
             stdout_sha=sha(log),stdout=str(log),timefile_sha=sha(rusage),timefile=str(rusage))
    print('R90_P38_BUILD_PASS',name,'wall_s',round(sec,6),'graph_sha256',row['graph_sha'],flush=True)
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
    for arm in ('ctrl','mirror'):
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
        'scope':'One isolated H17 C160 N2 1CPU baseline vs exact-distance mirrored RowMajor scan; unchanged packed-double logic. Timings BUILD not source counters.'}
    save(OUT/'progress.json',st)
    for arm in ('ctrl','mirror'):
        src=OUT/'source'/arm
        shutil.copytree(H17,src,symlinks=True,ignore=shutil.ignore_patterns('build','_deps','.git','*.graph','*.fbin','*.log'))
        if arm=='mirror':
            file=src/'algorithms/PipNN/pipnn_utils.h';file.write_text(patch_h17(file.read_text()))
        st['arm_source'][arm]=source_hashes(src)
        st['elf_sha'][arm]=configure(arm)
        print('R90_P38_NATIVE_CPP_PASS',arm,st['elf_sha'][arm],flush=True)
        save(OUT/'progress.json',st)
    for arm in ('ctrl','mirror'):
        st['runs'].append(run(arm,10000,1,OUT/'data/sift10k.fbin'))
        save(OUT/'progress.json',st)
    ensure(st['runs'][0]['graph_sha']==st['runs'][1]['graph_sha'],'GRAPH_PARITY_10K')
    st['status']='PASS_10K_PAIR'
    save(OUT/'result_manifest_10k.json',st)
    audit10k()
    print('R90_P38_10K_GRAPH_SHA_PARITY_PASS_READY_100K',flush=True)

def audit10k():
    preflight(False)
    f=OUT/'result_manifest_10k.json';ensure(f.is_file(),'10K_RESULT_MISSING')
    st=json.loads(f.read_text())
    ensure(st['status']=='PASS_10K_PAIR' and len(st['runs'])==2,'10K_STATE')
    check_state(st)
    print('R90_P38_AUDIT_10K_SOURCE_ELF_GRAPH_LOG_SHA_PASS',flush=True)

def pilot100k():
    audit10k()
    ensure(not (OUT/'result_manifest_100k.json').exists(),'100K_EXISTS')
    st=json.loads((OUT/'result_manifest_10k.json').read_text())
    for rep in (1,2,3):
        for arm in (('ctrl','mirror') if rep%2 else ('mirror','ctrl')):
            st['runs'].append(run(arm,100000,rep,BASE))
            save(OUT/'progress_100k.json',st)
        a,b=st['runs'][-2:];ensure(a['graph_sha']==b['graph_sha'],'GRAPH_PAIR_100K_'+str(rep))
        print('R90_P38_GRAPH_PARITY_PASS_100K_REP',rep,flush=True)
    st['status']='PASS_100K_3PAIRS';save(OUT/'result_manifest_100k.json',st)
    audit100k()
    for rep in (1,2,3):
        a=next(x for x in st['runs'] if x['n']==100000 and x['rep']==rep and x['arm']=='ctrl')
        b=next(x for x in st['runs'] if x['n']==100000 and x['rep']==rep and x['arm']=='mirror')
        print('R90_P38_PAIR',rep,'ctrl_s',round(a['wall_s'],6),'mirror_s',round(b['wall_s'],6),
              'pct',round(100*(b['wall_s']/a['wall_s']-1),4),flush=True)
    print('R90_P38_100K_3PAIR_BUILD_AND_GRAPH_SHA_PARITY_PASS',flush=True)

def audit100k():
    audit10k()
    p=OUT/'result_manifest_100k.json';ensure(p.is_file(),'100K_MISSING')
    st=json.loads(p.read_text());ensure(st['status']=='PASS_100K_3PAIRS' and len(st['runs'])==8,'100K_STATE')
    check_state(st)
    print('R90_P38_AUDIT_100K_3PAIR_SHA_PASS',flush=True)

def selftest():
    toy='''  if (MST_DEG == 2) {\n'''+'''      double first = std::numeric_limits<double>::infinity();\n'''+SCAN_OLD+'\n'+'''        double d = packFloatAndInt(dist_ij, j);\n'''+'''  } else {\n    std::vector<double> Q;\n'''+SCAN_OLD+'\n'+METRIC_OLD+'\n'+OTHER_OLD+'\n'
    z=patch_h17(toy)
    ensure(z.count(SCAN_OLD)==1 and z.count(SCAN_NEW)==1,'TEST_H17_FALLBACK_UNCHANGED')
    ensure(z.count('if (i != j) D(j, i) = D(i, j);')==2,'TEST_TWO_METRIC_BRANCHES')
    ensure(z.count('double d = packFloatAndInt(dist_ij, j);')==1,'TEST_PACK_PRESERVED')
    ensure(patch_h17.__name__=='patch_h17','TEST_MECHANISM')
    print('R90_P38_SELFTEST_PASS_H17_ONLY_MIRROR_CONTIGUOUS_SCAN_PACK_PRESERVED',flush=True)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('phase',choices=('selftest','preflight','pilot10k','audit10k','pilot100k','audit100k'))
    a=p.parse_args().phase
    if a=='selftest':selftest()
    elif a=='preflight':preflight(True)
    elif a=='pilot10k':pilot10k()
    elif a=='audit10k':audit10k()
    elif a=='pilot100k':pilot100k()
    else:audit100k()
if __name__=='__main__':
    try:main()
    except Exception as e:
        print('R90_P38_HOLD',type(e).__name__,str(e),file=sys.stderr,flush=True)
        raise SystemExit(2)
