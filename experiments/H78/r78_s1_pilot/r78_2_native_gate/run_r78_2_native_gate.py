#!/usr/bin/env python3
"""R78.2: isolated native Export graph parity and optional reservoir microbench.

- Never modifies H70 and existing R78 sources/binaries; operates only in
  the directory containing this script.
- Reuses CMake's already-existing R70 native compile/link argument lists.
- Pins the original H70 graph/pipnn code and R78 S1 header.
- Export phase is a small deterministic IN-MEMORY graph finalization test;
  it does not build the ANN index from a dataset.
- Bench phase runs 3 arms in separate processes with a small synthetic workload.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import os
import shlex
import statistics
import subprocess
import sys

ROOT=Path.home()/'ann-task-a'/'experiments'
WORK=ROOT/'H70'/'pipnn-clean-443a328'
BUILD=ROOT/'H70'/'build-r70'
HERE=Path(__file__).resolve().parent
PARENT=HERE.parent
PINNED_HEAD='443a328dc71a3b7be753d52ca2b3c9a4ba77f3fd'
PINS={
    WORK/'algorithms/utils/graph.h':'17e51779f32db56c9c50b6d514a8ff68539fd19b734804df3abdb63f88dd443e',
    WORK/'algorithms/PipNN/pipnn.h':'f4391ad8712d7757423dca872f9042c3271660dffde384a85b93854b9692f288',
    WORK/'algorithms/PipNN/pipnn_utils.h':'7083e8183554a1cb586b70cdb4c57920f49ec5a50680096aecf6b873f596595d',
    PARENT/'r78_segmented_lshgraph.h':'8e2d16feda61644eab4fe730d1f78c43130f2a1d466523ed7712e68e423e41b7',
}

def fail(message):
    print('R78_2_BLOCKED:',message,flush=True)
    raise SystemExit(2)

def sha256(path):
    h=hashlib.sha256()
    with path.open('rb') as fh:
        for b in iter(lambda:fh.read(1048576),b''):h.update(b)
    return h.hexdigest()

def pin_check():
    check=subprocess.run(['git','-C',str(WORK),'rev-parse','HEAD'],capture_output=True,text=True)
    if check.returncode or check.stdout.strip()!=PINNED_HEAD:
        fail('H70 worktree HEAD does not match pinned commit')
    for file,want in PINS.items():
        if not file.exists():fail('required source absent: '+str(file))
        got=sha256(file)
        if got!=want:fail('source SHA256 differs: '+str(file)+' got '+got)
    print('R78_2_SOURCE_PIN_GATE_PASS',flush=True)

def original_compile():
    db=BUILD/'compile_commands.json'
    if not db.is_file():fail('missing existing H70 build-r70/compile_commands.json')
    entries=json.loads(db.read_text())
    expect=(WORK/'algorithms/PipNN/r70_native_tests.cc').resolve()
    hits=[x for x in entries if Path(x.get('file','')).resolve()==expect]
    if len(hits)!=1:fail(f'expected one R70 compiler entry, found {len(hits)}')
    e=hits[0]
    cmd=(list(e['arguments']) if 'arguments' in e else shlex.split(e['command']))
    if '-o' not in cmd or '-c' not in cmd:fail('unexpected compile spec')
    return cmd,Path(e['directory'])

def original_link():
    path=BUILD/'algorithms/PipNN/CMakeFiles/r70_native_tests.dir/link.txt'
    if not path.is_file():fail('missing R70 link.txt')
    cmd=shlex.split(path.read_text().strip())
    if '-o' not in cmd:fail('unexpected link.txt')
    inds=[i for i,v in enumerate(cmd) if v.endswith('r70_native_tests.cc.o')]
    if len(inds)!=1:fail('unexpected object references in link.txt')
    return cmd,inds[0],BUILD/'algorithms/PipNN'

def compile_and_link(name):
    src=HERE/(name+'.cc')
    if not src.is_file():fail('missing test source '+str(src))
    obj=HERE/(name+'.o')
    binpath=HERE/name
    if binpath.exists() and not binpath.is_file():fail('executable path occupied')
    cmd,cwd=original_compile()
    cmd[cmd.index('-o')+1]=str(obj)
    cmd[cmd.index('-c')+1]=str(src)
    cmd[1:1]=['-I'+str(PARENT),'-I'+str(HERE),'-DR71_H17_TOP2=1']
    print('[R78.2] compile test:',name,flush=True)
    subprocess.run(cmd,cwd=cwd,check=True)
    link,at,linkcwd=original_link()
    link[link.index('-o')+1]=str(binpath)
    link[at]=str(obj)
    print('[R78.2] link test:',name,flush=True)
    subprocess.run(link,cwd=linkcwd,check=True)
    return binpath

def run_export():
    path=compile_and_link('r78_2_export_native')
    print('[R78.2] execute real PiPNN ExportToGraph on synthetic 257-node fixture',flush=True)
    subprocess.run([str(path)],cwd=HERE,check=True)
    print('R78_2_EXPORT_GATE_COMPLETE',flush=True)

def extract(line):
    if not line.startswith('R78_2_MICROBENCH_RESULT '):return None
    out={}
    for item in line.strip().split()[1:]:
        if '=' not in item:continue
        k,v=item.split('=',1)
        out[k]=v
    return out

def run_bench(n,reps):
    # A benchmark that processes no ANN queries, doesn't construct ANN graph,
    # and never modifies the dataset/graph provenance from earlier experiments.
    path=compile_and_link('r78_2_microbench_native')
    orders=[('stock','tier','s1'),('s1','tier','stock'),('tier','stock','s1')]
    data={arm:[] for arm in ('stock','tier','s1')}
    env=dict(os.environ,PARLAY_NUM_THREADS='1')
    for j in range(reps):
        print('[R78.2] microbench round',j+1,'variant order',orders[j],flush=True)
        same={}
        for arm in orders[j]:
            p=subprocess.run([str(path),arm,str(n)],cwd=HERE,env=env,
                  text=True,capture_output=True,check=False)
            print(p.stdout,end='',flush=True)
            if p.returncode or 'R78_2_NOT_REAL_ANN_BUILD_OR_RECALL' not in p.stdout:
                print(p.stderr,file=sys.stderr)
                fail(f'microbench {arm} exited {p.returncode}')
            recs=[extract(x) for x in p.stdout.splitlines()]
            recs=[r for r in recs if r]
            if len(recs)!=1:fail(f'unexpected benchmark output from {arm}')
            r=recs[0]
            if r.get('variant')!=arm or int(r.get('nodes','-1'))!=n:
                fail('incorrect benchmark provenance in '+arm)
            same[arm]=r['checksum']
            data[arm].append(r)
        if len(set(same.values()))!=1:
            fail(f'degree checksum parity failed in round {j+1}: {same}')
        print('R78_2_MICROBENCH_CHECKSUM_PARITY_PASS round='+str(j+1),flush=True)
    print('R78_2_MICROBENCH_MEDIANS_START')
    for arm in ('stock','tier','s1'):
        secs=statistics.median(float(x['elapsed_s']) for x in data[arm])
        rss=statistics.median(int(x['VmHWM_KiB']) for x in data[arm])
        print(f'variant={arm} median_elapsed_s={secs:.6f} median_VmHWM_KiB={rss}')
    print('R78_2_MICROBENCH_SYNTHETIC_ONLY_NOT_SIFT_NOT_BUILD')
    print('R78_2_MICROBENCH_GATE_COMPLETE')


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--phase',choices=('export','bench'),default='export')
    parser.add_argument('--nodes',type=int,default=100000)
    parser.add_argument('--reps',type=int,choices=(1,2,3),default=3)
    args=parser.parse_args()
    print('========== R78.2 REAL-PIPNN ISOLATED GATE ==========',flush=True)
    pin_check()
    if args.phase=='export':run_export()
    else:
        if not 4096<=args.nodes<=100000:fail('limit synthetic benchmark to at most 100k nodes')
        run_bench(args.nodes,args.reps)

if __name__=='__main__':
    try:main()
    except (subprocess.CalledProcessError,FileNotFoundError,ValueError) as e:
        fail(f'compiler/link/native program failed: {e}')
