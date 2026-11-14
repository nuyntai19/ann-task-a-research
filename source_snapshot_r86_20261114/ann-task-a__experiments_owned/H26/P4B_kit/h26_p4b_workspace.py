#!/usr/bin/env python3
"""Fail closed before writes; isolated worktree at pinned PiPNN commit + exact H26-P0 Top2 code."""
import argparse, hashlib, pathlib, subprocess, shlex, sys
from h26_p4b_patch import patch_graph, patch_cluster, patch_cmake
ROOT=pathlib.Path.home()/'ann-task-a'
REPO=ROOT/'src/PiPNN'
P0=ROOT/'experiments/H26/PiPNN-H26-src'
DEST=ROOT/'experiments/H26/PiPNN-H26-P4B-src'
CONF=ROOT/'experiments/H26/configure_H26_P4B.sh'
PIN='443a328dc71a3b7be753d52ca2b3c9a4ba77f3fd'
DEPS=['parlaylib','eigen','abseil-cpp','highway','googlebenchmark']
def run(*args):
    print('+',shlex.join(map(str,args)),flush=True)
    subprocess.run(list(map(str,args)),check=True)
def main():
    p=argparse.ArgumentParser();p.add_argument('--mode',choices=['check','create'],default='check');a=p.parse_args()
    if DEST.exists() or CONF.exists():raise RuntimeError('P4b source/config already exists: no overwrite allowed')
    if subprocess.check_output(['git','-C',str(REPO),'rev-parse',PIN],text=True).strip()!=PIN:raise RuntimeError('Wrong pin')
    for name in DEPS:
        if not (REPO/'build/_deps'/(name+'-src')/'CMakeLists.txt').exists():raise RuntimeError('Missing cached dependency '+name)
    for f in ('algorithms/PipNN/pipnn_utils.h','algorithms/PipNN/pipnn.h','algorithms/utils/graph.h'):
        if not (P0/f).is_file(): raise RuntimeError('Missing P0 source: '+f)
    utils=(P0/'algorithms/PipNN/pipnn_utils.h').read_text()
    if 'H26_PROFILE,version,H26_P0_v1' not in utils or 'H26_SELECTOR' not in utils: raise RuntimeError('P0 Top2 profiler source not verified')
    # Only instrument pinned graph and cluster source; P0 changes must be confined to utility code.
    mods={}
    for f in ('algorithms/PipNN/pipnn.h','algorithms/utils/graph.h'):
        p0=(P0/f).read_bytes()
        pinned=subprocess.check_output(['git','-C',str(REPO),'show',PIN+':'+f])
        if p0!=pinned:raise RuntimeError('P0 '+f+' differs from pinned source; fail-closed')
        mods[f]=patch_cluster(p0.decode()) if f.endswith('/pipnn.h') else patch_graph(p0.decode())
    cm=subprocess.check_output(['git','-C',str(REPO),'show',PIN+':CMakeLists.txt'],text=True)
    mods['CMakeLists.txt']=patch_cmake(cm)
    print('H26P4B_PREFLIGHT_PASS H26P0_UTILS_SHA256='+hashlib.sha256(utils.encode()).hexdigest())
    if a.mode=='check':return
    run('git','-C',REPO,'worktree','add','--detach',DEST,PIN)
    for sub in ('external/mirage','external/hnswlib'):
        src=REPO/sub;dst=DEST/sub
        if src.is_dir() and dst.is_dir() and not any(dst.iterdir()):
            dst.rmdir();dst.symlink_to(src.resolve(),target_is_directory=True)
    (DEST/'algorithms/PipNN/pipnn_utils.h').write_text(utils)
    for f,s in mods.items(): (DEST/f).write_text(s)
    cmake=['cmake','-S',str(DEST),'-B',str(DEST/'build'),'-DCMAKE_BUILD_TYPE=Release','-DFETCHCONTENT_FULLY_DISCONNECTED=ON']
    for dep in DEPS:cmake.append('-DFETCHCONTENT_SOURCE_DIR_'+dep.upper()+'='+str((REPO/'build/_deps'/(dep+'-src')).resolve()))
    cmds=['#!/usr/bin/env bash','set -euo pipefail',shlex.join(cmake),shlex.join(['cmake','--build',str(DEST/'build'),'--target','neighbors-pipnn_FLOAT_T_EUCLIDEAN','-j','4'])]
    CONF.write_text('\n'.join(cmds)+'\n');CONF.chmod(0o755)
    print('H26P4B_PREPARED',DEST,'config',CONF)
if __name__=='__main__':
    try:main()
    except Exception as e:print('H26P4B_FAIL_CLOSED:',e,file=sys.stderr);sys.exit(2)
