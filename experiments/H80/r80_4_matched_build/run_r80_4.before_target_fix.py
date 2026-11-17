#!/usr/bin/env python3
"""R80.4: isolate native PiPNN D0/E build and matched SIFT100K comparison.

All filesystem writes are under ~/ann-task-a/experiments/H80/r80_4_matched_build.
H70, R80.3 shadow source, baseline binaries, and all datasets are read-only.
No attempt at SIFT1M.  Compile/locate/pilot/quality phases are explicit.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import resource
import shlex
import shutil
import statistics
import struct
import subprocess
import sys
import time

ROOT = Path.home() / 'ann-task-a'
EXPS = ROOT / 'experiments'
H70 = EXPS / 'H70'
WORK = H70 / 'pipnn-clean-443a328'
BUILD = H70 / 'build-r70'
H80 = EXPS / 'H80'
R803 = H80 / 'r80_3_compile_gate'
SHADOW = R803 / 'shadow_algorithms'
HERE = Path(__file__).resolve().parent
E_SHADOW = HERE / 'shadow_algorithms'
BINARY_DIR = HERE / 'bin'
RUNS = HERE / 'runs'
MANIFEST = HERE / 'r80_4_binaries.json'
PINNED_HEAD = '443a328dc71a3b7be753d52ca2b3c9a4ba77f3fd'
PINS = {
  'algorithms/PipNN/pipnn.h': 'f4391ad8712d7757423dca872f9042c3271660dffde384a85b93854b9692f288',
  'algorithms/PipNN/pipnn_utils.h': '7083e8183554a1cb586b70cdb4c57920f49ec5a50680096aecf6b873f596595d',
  'algorithms/utils/graph.h': '17e51779f32db56c9c50b6d514a8ff68539fd19b734804df3abdb63f88dd443e',
  'algorithms/utils/r70_two_tier_lshgraph.h': 'ac0bece4804c7bc552b30db0df57ee92492033065cef62330ddb58a19d470af1',
}
SHADOW_PIN = 'b837de4d91673825c25c5ba0cf0e03f2ce36e21bc60b712f7b444a4cecdd705f'
D_HISTORICAL_PIN = '8f3e9a4659ede27739b34eb8b270d0d0b8b8e4457aa741f97c3998d0ee18d964'
TARGET = 'neighbors-pipnn_FLOAT_T_EUCLIDEAN'
WRAPPER = '''// R80.4: explicitly include the target PiPNN header (NO historic PCH),
// followed by the ORIGINAL benchmark's main function.
// Exactly the same wrapper is used to build D0 and E with differing -I roots.
#include "PipNN/neighbors.h"
#include "bench/neighborsTime.C"
'''
FLAGS = ['-num_clusters','2','-cluster_size','1024','-top_level_leaders','100',
         '-fanout_scheme','10,3,1','-mst_deg','2','-prune_degree','64',
         '-table_size','160','-hash_bits','12','-alpha','1.1']


def stop(msg: str):
    print('R80_4_BLOCKED:', msg, flush=True)
    raise SystemExit(2)


def checksum(path: Path) -> str:
    h=hashlib.sha256()
    with path.open('rb') as f:
        for part in iter(lambda:f.read(1<<20),b''):
            h.update(part)
    return h.hexdigest()


def source_gate():
    if not HERE.resolve().is_relative_to(H80.resolve()):
        stop('refusing to run outside H80')
    if HERE.is_symlink() or RUNS.is_symlink() or BINARY_DIR.is_symlink() or E_SHADOW.is_symlink():
        stop('symlink in output path is forbidden')
    r=subprocess.run(['git','-C',str(WORK),'rev-parse','HEAD'],capture_output=True,text=True)
    if r.returncode or r.stdout.strip()!=PINNED_HEAD:
        stop('H70 HEAD changed')
    for name, expected in PINS.items():
        f=WORK/name
        if not f.is_file() or checksum(f)!=expected:
            stop('H70 source pin mismatch '+name)
    shp=SHADOW/'PipNN/pipnn.h'
    if not shp.is_file() or checksum(shp)!=SHADOW_PIN:
        stop('R80.3 shadow hash mismatch; R80.3 must be run successfully first')
    for name in ['pipnn_utils.h']:
        if checksum(SHADOW/'PipNN'/name)!=PINS['algorithms/PipNN/'+name]:
            stop('R80.3 shadow shared source mismatch')
    for k in ['utils','bench']:
        link=SHADOW/k
        if not link.is_symlink() or link.resolve()!=(WORK/'algorithms'/k).resolve():
            stop('R80.3 shadow symlink unexpected '+k)
    print('R80_4_PINNED_SOURCE_GATE_PASS', flush=True)


def sources_snapshot():
    x={k:checksum(WORK/k) for k in PINS}
    x['shadow_pipnn_h']=checksum(SHADOW/'PipNN/pipnn.h')
    x['neighbors_h']=checksum(WORK/'algorithms/PipNN/neighbors.h')
    x['bench_main']=checksum(WORK/'algorithms/bench/neighborsTime.C')
    x['r80_4_shadow_neighbors_h']=checksum(E_SHADOW/'PipNN/neighbors.h')
    x['r80_4_shadow_pipnn_h']=checksum(E_SHADOW/'PipNN/pipnn.h')
    x['r80_4_shadow_pipnn_utils_h']=checksum(E_SHADOW/'PipNN/pipnn_utils.h')
    return x


def compile_spec():
    path=BUILD/'compile_commands.json'
    if not path.is_file():stop('missing H70 compile_commands.json')
    entries=json.loads(path.read_text())
    benchmark=(WORK/'algorithms/bench/neighborsTime.C').resolve()
    choices=[]
    for entry in entries:
        try: fp=Path(entry['file']).resolve()
        except KeyError: continue
        if fp!=benchmark: continue
        args=list(entry.get('arguments') or shlex.split(entry['command']))
        if any('USE_DATATYPE_FLOAT_T' in s for s in args) and any('USE_DISTANCE_EUCLIDEAN' in s for s in args):
            choices.append((args, Path(entry['directory'])))
    if len(choices)!=1:
        stop(f'expected exactly one FLOAT_T EUCLIDEAN compile command, found {len(choices)}')
    args,cwd=choices[0]
    for needed in ('-c','-o'):
        if needed not in args:stop('unexpected benchmark compile command: missing '+needed)
    return args,cwd


def link_spec():
    cwd=BUILD/'algorithms/PipNN'
    f=cwd/'CMakeFiles'/f'{TARGET}.dir'/'link.txt'
    if not f.is_file():stop('missing H70 benchmark link.txt '+str(f))
    argv=shlex.split(f.read_text().strip())
    indexes=[i for i,a in enumerate(argv) if a.endswith('neighborsTime.C.o')]
    if len(indexes)!=1:stop('expected one benchmark object in link command')
    if '-o' not in argv:stop('expected -o in link command')
    return argv,indexes[0],cwd


def transform_compile(argv,variant,source,dest):
    args=argv.copy()
    # Remove ONLY CMake's existing PCH inclusion, which points to the H70 header.
    # Keeping it would silently compile the OLD H70 pipnn.h even for E.
    i=0
    while i<len(args):
        if args[i]=='-include':
            if i+1>=len(args) or 'cmake_pch' not in args[i+1]:
                stop('unrecognized -include; refusing to alter PCH configuration')
            del args[i:i+2];continue
        if args[i].startswith('-include') and 'cmake_pch' in args[i]:
            del args[i];continue
        if args[i] in ('-MD','-MMD','-MP'):
            del args[i];continue
        if args[i] in ('-MF','-MT','-MQ'):
            if i+1>=len(args):stop('malformed dependency option')
            del args[i:i+2];continue
        i+=1
    for option,newarg in (('-o',str(dest)),('-c',str(source))):
        idx=args.index(option)
        if idx+1>=len(args):stop('malformed compiler args '+option)
        args[idx+1]=newarg
    if any('cmake_pch' in a for a in args):stop('CMake PCH flags remain; source selection unsafe')
    # Do not let pre-existing macro variants silently disagree with our arm.
    for macro in ('R70_TWO_TIER','R71_H17_TOP2'):
        definitions=[a for a in args if a.startswith('-D'+macro)]
        if any(a not in ('-D'+macro,'-D'+macro+'=1') for a in definitions):
            stop('conflicting pre-existing macro for '+macro)
        if not definitions:args.insert(1,'-D'+macro+'=1')
    inc=E_SHADOW if variant=='E' else WORK/'algorithms'
    args.insert(1,'-I'+str(inc))
    if '-DUSE_DATATYPE_FLOAT_T' not in args or '-DUSE_DISTANCE_EUCLIDEAN' not in args:
        stop('FLOAT_T/EUCLIDEAN definitions changed unexpectedly')
    if any(a.endswith('neighborsTime.C') for a in args):
        stop('original compile input remains instead of H80 wrapper')
    return args


def write_new(path:Path,text:str):
    if path.is_symlink():stop('output file is a symlink '+str(path))
    if path.exists():
        if not path.is_file() or path.read_text()!=text:
            stop('H80 file already exists with different content '+str(path))
        return
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('x',encoding='utf-8') as f:f.write(text)


def stage_shadow():
    """Build a wholly new H80 shadow without modifying the R80.3 artifact."""
    (E_SHADOW/'PipNN').mkdir(parents=True,exist_ok=True)
    for name in ('utils','bench'):
        link=E_SHADOW/name
        target=WORK/'algorithms'/name
        if not link.exists() and not link.is_symlink():
            link.symlink_to(target,target_is_directory=True)
        if not link.is_symlink() or link.resolve()!=target.resolve():
            stop('unsafe E shadow symlink '+name)
    for name,original in [
        ('pipnn.h',SHADOW/'PipNN/pipnn.h'),
        ('pipnn_utils.h',WORK/'algorithms/PipNN/pipnn_utils.h'),
        ('neighbors.h',WORK/'algorithms/PipNN/neighbors.h'),
    ]:
        write_new(E_SHADOW/'PipNN'/name, original.read_text())
    print('R80_4_OWN_SHADOW_SOURCE_READY',flush=True)

def verify_shadow():
    for name,source in [('pipnn.h',SHADOW/'PipNN/pipnn.h'),
                        ('pipnn_utils.h',WORK/'algorithms/PipNN/pipnn_utils.h'),
                        ('neighbors.h',WORK/'algorithms/PipNN/neighbors.h')]:
        dst=E_SHADOW/'PipNN'/name
        if not dst.is_file() or dst.is_symlink() or checksum(dst)!=checksum(source):
            stop('R80.4 own shadow source changed '+name)
    for name in ('utils','bench'):
        link=E_SHADOW/name
        if not link.is_symlink() or link.resolve()!=(WORK/'algorithms'/name).resolve():
            stop('R80.4 shadow link changed '+name)

def dependency_gate(cargs, cwd, variant):
    # Fail closed if g++ silently resolves an old H70 PCH/header for arm E.
    deps=cargs.copy()
    compile_source=deps[deps.index('-c')+1]
    for option in ('-o','-c'):
        idx=deps.index(option)
        del deps[idx:idx+2]
    deps.extend(['-MM',compile_source])
    r=subprocess.run(deps,cwd=cwd,capture_output=True,text=True,check=False)
    if r.returncode:
        stop(f'{variant} header dependency scan failed: {r.stderr[-1800:]}')
    root=(E_SHADOW if variant=='E' else WORK/'algorithms')
    for name in ('PipNN/neighbors.h','PipNN/pipnn.h','PipNN/pipnn_utils.h'):
        expected=str(root/name)
        if expected not in r.stdout:
            stop(f'{variant} expected source header NOT in dependency trace: {expected}')
    wrong=(WORK/'algorithms' if variant=='E' else E_SHADOW)
    if str(wrong/'PipNN/pipnn.h') in r.stdout:
        stop(f'{variant} accidentally includes wrong PiPNN header')
    print(f'R80_4_HEADER_PROVENANCE_GATE_PASS arm={variant}',flush=True)

def compile_binary():
    source_gate()
    stage_shadow()
    if MANIFEST.exists():
        data=json.loads(MANIFEST.read_text())
        if (data.get('source_sha256')==sources_snapshot() and
            all((BINARY_DIR/(a+'.bin')).is_file() and
                checksum(BINARY_DIR/(a+'.bin'))==data['binary_sha256'][a]
                for a in ('D0','E'))):
            print('R80_4_BINARIES_ALREADY_VERIFIED',flush=True)
            return
        stop('previous H80 R80.4 manifest/binary mismatch; refusing overwrite')
    if BINARY_DIR.exists() and list(BINARY_DIR.iterdir()):
        stop('H80 binary output folder nonempty without manifest; refuse overwrites')
    BINARY_DIR.mkdir(parents=True,exist_ok=True)
    source=HERE/'r80_4_wrapper.cc'
    write_new(source,WRAPPER)
    comp,compcwd=compile_spec()
    link,index,linkcwd=link_spec()
    manifest={'source_sha256':sources_snapshot(),'wrapper_sha256':checksum(source),
              'binary_sha256':{},'compilation':{},'flags':FLAGS,
              'build_macro_config':{'R70_TWO_TIER':1,'R71_H17_TOP2':1,
                                    'USE_DATATYPE_FLOAT_T':1,'USE_DISTANCE_EUCLIDEAN':1},
              'note':'D0 and E no-PCH paired reconstruction, not identical binary to historic D'}
    for variant in ('D0','E'):
        obj=BINARY_DIR/(variant+'.o')
        exe=BINARY_DIR/(variant+'.bin')
        cargs=transform_compile(comp,variant,source,obj)
        largs=link.copy()
        largs[index]=str(obj)
        largs[largs.index('-o')+1]=str(exe)
        dependency_gate(cargs,compcwd,variant)
        print(f'[R80.4] compile {variant} using matching no-PCH flags',flush=True)
        cp=subprocess.run(cargs,cwd=compcwd,check=False)
        if cp.returncode:stop(f'C++ {variant} compile returned {cp.returncode}')
        print(f'[R80.4] link {variant}',flush=True)
        lp=subprocess.run(largs,cwd=linkcwd,check=False)
        if lp.returncode:stop(f'C++ {variant} link returned {lp.returncode}')
        if not exe.is_file() or not os.access(exe,os.X_OK):stop('compiled binary absent')
        manifest['binary_sha256'][variant]=checksum(exe)
        manifest['compilation'][variant]={'source_root':str(E_SHADOW if variant=='E' else WORK/'algorithms'),
             'command':shlex.join(cargs),'link':shlex.join(largs)}
        print(f'R80_4_BINARY_{variant}_COMPILE_LINK_PASS sha256={manifest["binary_sha256"][variant]}',flush=True)
    write_new(MANIFEST,json.dumps(manifest,indent=2,ensure_ascii=False)+'\n')
    print('R80_4_PAIRED_BINARIES_VERIFIED_PASS',flush=True)
    print('R80_4_COMPILE_ONLY_NO_ANN_BUILD',flush=True)


def validate_binaries():
    source_gate()
    verify_shadow()
    if not MANIFEST.is_file():stop('run --phase compile first')
    data=json.loads(MANIFEST.read_text())
    if data.get('source_sha256')!=sources_snapshot():stop('underlying source SHA changed')
    if checksum(HERE/'r80_4_wrapper.cc')!=data.get('wrapper_sha256'):
        stop('wrapper changed')
    for v in ('D0','E'):
        f=BINARY_DIR/(v+'.bin')
        if not f.is_file() or checksum(f)!=data['binary_sha256'][v]:
            stop('binary changed '+v)
    print('R80_4_PAIRED_BINARY_SHA_GATE_PASS',flush=True)
    return data


def file_header(path:Path):
    if not path.is_file():return None
    with path.open('rb') as f:data=f.read(8)
    if len(data)!=8:return None
    try:n,d=struct.unpack('<II',data)
    except struct.error:return None
    return n,d,path.stat().st_size


def base_is_100k(path:Path):
    head=file_header(path)
    return head is not None and head==(100000,128,8+100000*128*4)


def candidates():
    # Cheap bounded discovery, explicitly never traverses worktrees/build caches.
    roots=[ROOT/'data',ROOT/'datasets',ROOT/'sift',H70/'data',H70/'datasets',
           EXPS/'data',ROOT]
    got=[]; seen=set();count=0
    for root in roots:
        if not root.is_dir():continue
        for p in root.glob('*.fbin'):
            if p in seen:continue
            seen.add(p);count+=1
            if base_is_100k(p):got.append(p)
    # Include common nested ANN data directories only, avoid expensive full recursive scan.
    for parent in [ROOT/'data',ROOT/'datasets',H70/'data',ROOT/'sift']:
        if not parent.is_dir():continue
        for p in parent.glob('*/*.fbin'):
            if p in seen:continue
            seen.add(p);count+=1
            if base_is_100k(p):got.append(p)
    return got,count


def locate():
    x,n=candidates()
    print('========== R80.4 DATASET READ-ONLY LOCATOR ==========',flush=True)
    for p in x:print('R80_4_SIFT100K_CANDIDATE',str(p),flush=True)
    print(f'R80_4_DATA_DISCOVERY_COMPLETE examined={n} matching={len(x)}',flush=True)
    print('R80_4_LOCATOR_NO_DATASET_WRITE_NO_BUILD',flush=True)


def graph_validate(path:Path):
    if not path.is_file() or path.is_symlink():stop('graph absent or symlink '+str(path))
    with path.open('rb') as f:
        hdr=f.read(8)
        if len(hdr)!=8:stop('graph file too short')
        n,deg=struct.unpack('<II',hdr)
        if (n,deg)!=(100000,64):stop(f'graph header unexpected n={n} max_degree={deg}')
        degrees=f.read(4*n)
        if len(degrees)!=4*n:stop('graph degrees truncated')
        arcs=0
        for (v,) in struct.iter_unpack('<I',degrees):
            if v>64:stop('graph degree overflow')
            arcs+=v
    wanted=8+4*n+4*arcs
    if path.stat().st_size!=wanted:
        stop(f'graph file length mismatch actual={path.stat().st_size} expected={wanted}')
    return {'n':n,'max_degree':deg,'arcs':arcs,'size_bytes':wanted,'sha256':checksum(path)}


def parse_time_file(p:Path):
    result={}
    for line in p.read_text().splitlines():
        if line.startswith('R80_4_TIME '):
            _, elapsed, rss=line.split()
            result={'wall_s':float(elapsed),'peak_RSS_KiB':int(rss)}
    if not result:stop('timing file missing expected marker: '+str(p))
    return result


def pilot(base:Path|None, reps:int):
    manifest=validate_binaries()
    if base is None:
        x,_=candidates()
        if len(x)!=1:stop(f'found {len(x)} valid SIFT100K bases; pass --base /absolute/path/to/sift100k.fbin')
        base=x[0]
    base=base.resolve()
    if base.is_relative_to(H80.resolve()):stop('do not use H80 output as dataset input')
    if not base_is_100k(base):stop('base must be native SIFT100K fbin shape 100000x128 float32 and exact file size')
    if not 1<=reps<=3:stop('--reps must be 1..3')
    if not Path('/usr/bin/time').is_file():stop('GNU /usr/bin/time required for peak RSS')
    RUNS.mkdir(exist_ok=True)
    label=time.strftime('r80_4_sift100k_%Y%m%d_%H%M%S',time.localtime())
    run_dir=RUNS/label
    try:run_dir.mkdir(exist_ok=False)
    except FileExistsError:stop('run directory exists; retry with a unique name after 1 second')
    base_meta={'path':str(base),'sha256':checksum(base),'dims':[100000,128]}
    run_info={'run':label,'base':base_meta,'paired_binaries':manifest['binary_sha256'],
              'provenance':manifest['source_sha256'],'thread_env':{},
              'fixed_flags':FLAGS,'rows':[],
              'warning':'source uses random_device per BUILD; different independent runs not guaranteed graph-byte-identical'}
    env=os.environ.copy()
    env.update(PARLAY_NUM_THREADS='4',OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='1')
    run_info['thread_env']={k:env[k] for k in ['PARLAY_NUM_THREADS','OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS']}
    for k in range(reps):
        order=['D0','E'] if k%2==0 else ['E','D0']
        for variant in order:
            key=f'r{k+1}_{variant}'
            graph=run_dir/(key+'.graph')
            log=run_dir/(key+'.log')
            tm=run_dir/(key+'.time')
            if any(x.exists() or x.is_symlink() for x in [graph,log,tm]):
                stop('refusing to overwrite pilot output '+key)
            argv=[str(BINARY_DIR/(variant+'.bin')),'-base_path',str(base),
                  '-graph_outfile',str(graph)]+FLAGS
            print('R80_4_BUILD_START',key,'threads=4',flush=True)
            t0=time.perf_counter()
            with log.open('x',encoding='utf-8') as fp:
                proc=subprocess.run(['/usr/bin/time','-f','R80_4_TIME %e %M','-o',str(tm)]+argv,
                    stdout=fp,stderr=subprocess.STDOUT,cwd=run_dir,env=env,check=False)
            if proc.returncode:
                stop(f'PiPNN {key} exited {proc.returncode}; see {log}')
            text=log.read_text(errors='replace')
            for line in ['R70_RESERVOIR_VARIANT=TIER_B64_C160','R71_SELECTION_VARIANT=H17_PACKED_TOP2']:
                if line not in text:stop('binary provenance banner absent '+line+' log '+key)
            row={'rep':k+1,'variant':variant,'key':key,**parse_time_file(tm),
                 'graph':str(graph),**graph_validate(graph),'elapsed_host_s':time.perf_counter()-t0,
                 'log':str(log),'time_file':str(tm)}
            run_info['rows'].append(row)
            with (run_dir/'summary.json').open('w',encoding='utf8') as f:
                json.dump(run_info,f,indent=2,ensure_ascii=False)
            print(f'R80_4_BUILD_RESULT variant={variant} rep={k+1} wall_s={row["wall_s"]:.4f} peakRSS_KiB={row["peak_RSS_KiB"]} arcs={row["arcs"]} graph_sha256={row["sha256"]}',flush=True)
    for variant in ('D0','E'):
        vals=[r for r in run_info['rows'] if r['variant']==variant]
        mw=statistics.median([r['wall_s'] for r in vals])
        mr=statistics.median([r['peak_RSS_KiB'] for r in vals])
        print(f'R80_4_BUILD_MEDIAN variant={variant} reps={len(vals)} wall_s={mw:.4f} peakRSS_KiB={mr}',flush=True)
    print('R80_4_SIFT100K_BUILD_ONLY_COMPLETE',str(run_dir),flush=True)
    print('R80_4_NO_RECALL_EVALUATED_NO_SIFT1M',flush=True)


def quality(run_dir:Path|None,query:Path|None,gt:Path|None):
    """Evaluate existing H80 BUILD graphs using the original search-only evaluator."""
    validate_binaries()
    if run_dir is None or query is None or gt is None:
        stop('quality requires --run-dir, --query, and --gt')
    run_dir=run_dir.resolve()
    if not run_dir.is_relative_to(RUNS.resolve()) or not (run_dir/'summary.json').is_file():
        stop('quality run-dir must be a completed R80.4 pilot under H80')
    data=json.loads((run_dir/'summary.json').read_text())
    rows=data.get('rows',[])
    if len(rows)<2 or len([r for r in rows if r['variant']=='D0'])!=len([r for r in rows if r['variant']=='E']):
        stop('matched D0/E graph BUILD rows incomplete')
    query=query.resolve();gt=gt.resolve()
    if file_header(query)!=(300,128,8+300*128*4):
        stop('R70 SIFT100K recall requires queries fbin shape 300x128 float32')
    gtmeta=file_header(gt)
    if not gtmeta or gtmeta[0]!=300 or gtmeta[1]<10 or gtmeta[2]<8+300*gtmeta[1]*4:
        stop('ground truth needs 300 query rows, >=10 neighbours and valid data size')
    recall_bin=BUILD/'algorithms/PipNN/r70_graph_recall'
    if not recall_bin.is_file() or not os.access(recall_bin,os.X_OK):
        stop('existing H70 r70_graph_recall binary missing; do not compile into H70')
    result_dir=run_dir/'quality'
    if result_dir.exists():stop('quality output exists, refusing overwrite')
    result_dir.mkdir(mode=0o755)
    report={'evaluator_sha256':checksum(recall_bin),'query_sha256':checksum(query),'gt_sha256':checksum(gt),
            'rows':[], 'note':'search-only evaluator, reported QPS not an isolated build-time measure'}
    for row in rows:
        graph=Path(row['graph'])
        if not graph.is_relative_to(run_dir):stop('graph path outside run-dir')
        if graph_validate(graph)['sha256']!=row['sha256']:stop('graph changed since BUILD')
        log=result_dir/(row['key']+'.recall.log')
        with log.open('x') as fp:
            pr=subprocess.run([str(recall_bin),str(graph),str(data['base']['path']),str(query),str(gt)],
                              stdout=fp,stderr=subprocess.STDOUT,check=False,cwd=result_dir)
        if pr.returncode:stop(f'R70 recall evaluator exited {pr.returncode}: {log}')
        out=log.read_text(errors='replace')
        if 'R70_RECALL_EVAL_PASS' not in out:stop('R70 recall PASS marker missing')
        vals=[]
        for ln in out.splitlines():
            if not ln.startswith('R70_RECALL_ROW '):continue
            pairs=dict(re.findall(r'(\w+)=([0-9.eE+\-]+)',ln))
            vals.append({k:float(v) for k,v in pairs.items()})
        if len(vals)!=5:stop('expected 5 beam recall rows')
        report['rows'].append({'variant':row['variant'],'rep':row['rep'],'key':row['key'],'beams':vals,'log':str(log)})
        print(f'R80_4_SEARCH_RECALL_PASS variant={row["variant"]} rep={row["rep"]} beams=5',flush=True)
    with (result_dir/'recall_summary.json').open('x') as fp:json.dump(report,fp,indent=2)
    print('R80_4_QUALITY_EVALUATION_COMPLETE',str(result_dir),flush=True)
    print('R80_4_RECALL_VARIABILITY_NOT_STATISTICAL_NONINFERIORITY',flush=True)


def selftest():
    import tempfile
    with tempfile.TemporaryDirectory() as p:
        p=Path(p)
        t=p/'base.fbin'
        with t.open('wb') as f:
            f.write(struct.pack('<II',100000,128));f.truncate(8+100000*128*4)
        assert base_is_100k(t)
        assert not base_is_100k(p/'notthere.fbin')
        g=p/'good.graph'
        with g.open('wb') as f:
            f.write(struct.pack('<II',100000,64)); f.write(struct.pack('<I',0)*100000)
        z=graph_validate(g)
        assert z['n']==100000 and z['arcs']==0
        src=['/usr/bin/c++','-DR70_TWO_TIER=1','-DUSE_DATATYPE_FLOAT_T','-DUSE_DISTANCE_EUCLIDEAN',
             '-include','/tmp/cmake_pch.hxx','-o','old.o','-c','neighborsTime.C']
        y=transform_compile(src,'E',p/'wrapper.cc',p/'obj.o')
        assert not any('cmake_pch' in x for x in y)
        assert y[y.index('-c')+1].endswith('wrapper.cc')
    print('R80_4_SELFTEST_PASS',flush=True)


def main():
    a=argparse.ArgumentParser(description=__doc__)
    a.add_argument('--phase',choices=['selftest','compile','locate','pilot','quality'],required=True)
    a.add_argument('--base',type=Path,default=None)
    a.add_argument('--reps',type=int,default=3)
    a.add_argument('--query',type=Path,default=None)
    a.add_argument('--gt',type=Path,default=None)
    a.add_argument('--run-dir',type=Path,default=None)
    opt=a.parse_args()
    if opt.phase=='selftest':selftest()
    elif opt.phase=='compile':compile_binary()
    elif opt.phase=='locate':locate()
    elif opt.phase=='pilot':pilot(opt.base,opt.reps)
    elif opt.phase=='quality':quality(opt.run_dir,opt.query,opt.gt)


if __name__=='__main__':
    try:main()
    except (OSError,ValueError,KeyError,IndexError,json.JSONDecodeError) as e:
        stop(str(e))
