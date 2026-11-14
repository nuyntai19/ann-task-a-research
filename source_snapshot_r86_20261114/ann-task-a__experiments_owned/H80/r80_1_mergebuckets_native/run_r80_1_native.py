#!/usr/bin/env python3
"""R80.1 real PiPNN MergeBuckets native differential pilot, H80-only output.

Pins the existing H70 source and compilation metadata. Does not edit H70,
run CMake, build a full ANN index, read datasets or calculate Recall.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys

ROOT=Path.home()/'ann-task-a'/'experiments'
WORK=ROOT/'H70'/'pipnn-clean-443a328'
BUILD=ROOT/'H70'/'build-r70'
HERE=Path(__file__).resolve().parent
PINNED_HEAD='443a328dc71a3b7be753d52ca2b3c9a4ba77f3fd'
PINS={
    WORK/'algorithms/utils/graph.h':'17e51779f32db56c9c50b6d514a8ff68539fd19b734804df3abdb63f88dd443e',
    WORK/'algorithms/PipNN/pipnn.h':'f4391ad8712d7757423dca872f9042c3271660dffde384a85b93854b9692f288',
    WORK/'algorithms/PipNN/pipnn_utils.h':'7083e8183554a1cb586b70cdb4c57920f49ec5a50680096aecf6b873f596595d',
}

def fail(msg):
    print('R80_1_BLOCKED:', msg, flush=True)
    raise SystemExit(2)

def sha256(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda:f.read(1<<20),b''):
            h.update(b)
    return h.hexdigest()

def pin_check():
    v=subprocess.run(['git','-C',str(WORK),'rev-parse','HEAD'],capture_output=True,text=True)
    if v.returncode!=0 or v.stdout.strip()!=PINNED_HEAD:
        fail('original worktree git HEAD mismatch')
    for path,expected in PINS.items():
        if not path.is_file():fail('required source missing '+str(path))
        if sha256(path)!=expected:
            fail('pinned SHA256 mismatch for '+str(path))
    print('R80_1_SOURCE_PIN_GATE_PASS', flush=True)

def compiler():
    db=BUILD/'compile_commands.json'
    if not db.is_file():fail('existing H70 CMake compile_commands.json missing')
    obj=json.loads(db.read_text(encoding='utf-8'))
    tgt=(WORK/'algorithms/PipNN/r70_native_tests.cc').resolve()
    entries=[e for e in obj if Path(e['file']).resolve()==tgt]
    if len(entries)!=1:fail('expected exactly one R70 native compile spec')
    e=entries[0]
    args=e['arguments'] if 'arguments' in e else shlex.split(e['command'])
    return list(args),Path(e['directory'])

def linker():
    linkfile=BUILD/'algorithms/PipNN/CMakeFiles/r70_native_tests.dir/link.txt'
    if not linkfile.is_file():fail('existing H70 native link spec missing')
    args=shlex.split(linkfile.read_text(encoding='utf-8').strip())
    objs=[i for i,s in enumerate(args) if s.endswith('r70_native_tests.cc.o')]
    if len(objs)!=1:fail('expected exactly one R70 native test object')
    return args,objs[0],BUILD/'algorithms/PipNN'

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--buckets',type=int,default=1600)
    args=ap.parse_args()
    if not 64 <= args.buckets <= 5000:fail('--buckets must be in [64,5000]')
    print('========== R80.1 ORIGINAL PIPNN MERGEBUCKETS DIFFERENTIAL ==========',flush=True)
    pin_check()
    src=HERE/'r80_1_mergebuckets_native.cc'
    if not src.is_file():fail('native source missing')
    original,ccwd=compiler()
    if '-c' not in original or '-o' not in original:fail('unsupported compiler command')
    outfile=HERE/'r80_1_mergebuckets_native.o'
    executable=HERE/'r80_1_mergebuckets_native'
    original[original.index('-o')+1]=str(outfile)
    original[original.index('-c')+1]=str(src)
    # These are compiler options, NOT a patch to source files.
    original[1:1]=['-DR71_H17_TOP2=1']
    print('[R80.1] native compile original Parlay/PiPNN MergeBuckets',flush=True)
    subprocess.run(original,cwd=ccwd,check=True)
    link,obj_idx,lcwd=linker()
    link[link.index('-o')+1]=str(executable)
    link[obj_idx]=str(outfile)
    print('[R80.1] native link in isolated H80',flush=True)
    subprocess.run(link,cwd=lcwd,check=True)
    print('[R80.1] run 21 differential cases, using source-equivalent move-heap',flush=True)
    env=dict(os.environ,PARLAY_NUM_THREADS="1",OMP_NUM_THREADS="1")
    subprocess.run([str(executable),str(args.buckets)],cwd=HERE,env=env,check=True)
    print('R80_1_NATIVE_GATE_COMPLETE',flush=True)

if __name__=='__main__':
    try:main()
    except (OSError,subprocess.CalledProcessError,ValueError,KeyError,IndexError) as e:
        fail('compiler/linker/native test failed: '+str(e))
