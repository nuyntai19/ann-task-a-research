#!/usr/bin/env python3
"""Copy already validated H26-P0 source into independent pinned worktree and patch P4a."""
import pathlib, subprocess, shutil, shlex, argparse, sys, hashlib
from h26_p4a_patch import instrument_p0, instrument_cluster, instrument_cmake

ROOT=pathlib.Path.home()/'ann-task-a'
REPO=ROOT/'src/PiPNN'
P0=ROOT/'experiments/H26/PiPNN-H26-src'
DEST=ROOT/'experiments/H26/PiPNN-H26-P4A-src'
CONF=ROOT/'experiments/H26/configure_H26_P4A.sh'
FETCH=['parlaylib','eigen','abseil-cpp','highway','googlebenchmark']
PIN='443a328dc71a3b7be753d52ca2b3c9a4ba77f3fd'

def run(*argv):
    print('+',shlex.join(map(str,argv)),flush=True)
    subprocess.run(list(map(str,argv)),check=True)

def preflight():
    if DEST.exists():raise RuntimeError(f'P4a workspace already exists; refusing overwrite: {DEST}')
    if CONF.exists():raise RuntimeError(f'configure script already exists; refusing overwrite: {CONF}')
    if not (P0/'algorithms/PipNN/pipnn_utils.h').is_file(): raise RuntimeError('H26-P0 source missing')
    commit=subprocess.check_output(['git','-C',str(REPO),'rev-parse',PIN],text=True).strip()
    if commit!=PIN:raise RuntimeError(f'Pinned commit mismatch: {commit}')
    for name in FETCH:
        if not (REPO/'build/_deps'/(name+'-src')/'CMakeLists.txt').exists():
            raise RuntimeError(f'Cached source missing: {name}')
    if not (REPO/'external/mirage/CMakeLists.txt').exists():raise RuntimeError('Original mirage missing')
    # Dry-run all patch substitutions before any writes.
    p0=(P0/'algorithms/PipNN/pipnn_utils.h').read_text()
    patched_utils=instrument_p0(p0)
    original_h=(P0/'algorithms/PipNN/pipnn.h').read_text()
    patched_h=instrument_cluster(original_h)
    pinned_cmake=subprocess.check_output(['git','-C',str(REPO),'show',PIN+':CMakeLists.txt'],text=True)
    patched_cmake=instrument_cmake(pinned_cmake)
    print('H26P4A_PREFLIGHT_PASS original_p0_sha256='+hashlib.sha256(p0.encode()).hexdigest())
    return patched_utils,patched_h,patched_cmake

def main():
    p=argparse.ArgumentParser();p.add_argument('--mode',choices=['check','create'],default='check');a=p.parse_args()
    utils,h,cmake=preflight()
    if a.mode=='check':return
    DEST.parent.mkdir(parents=True,exist_ok=True)
    run('git','-C',REPO,'worktree','add','--detach',DEST,PIN)
    for sub in ['external/mirage','external/hnswlib']:
        src=REPO/sub; dst=DEST/sub
        if src.is_dir() and dst.is_dir() and not any(dst.iterdir()):
            dst.rmdir();dst.symlink_to(src.resolve(),target_is_directory=True)
            print('H26P4A_SYMLINK',dst,'->',src)
    (DEST/'algorithms/PipNN/pipnn_utils.h').write_text(utils)
    (DEST/'algorithms/PipNN/pipnn.h').write_text(h)
    (DEST/'CMakeLists.txt').write_text(cmake)
    cfg=['cmake','-S',str(DEST),'-B',str(DEST/'build'),'-DCMAKE_BUILD_TYPE=Release','-DFETCHCONTENT_FULLY_DISCONNECTED=ON']
    for lib in FETCH:
        cfg.append('-DFETCHCONTENT_SOURCE_DIR_'+lib.upper()+'='+str((REPO/'build/_deps'/(lib+'-src')).resolve()))
    cmds=['#!/usr/bin/env bash','set -euo pipefail',shlex.join(cfg),shlex.join(['cmake','--build',str(DEST/'build'),'--target','neighbors-pipnn_FLOAT_T_EUCLIDEAN','-j','4'])]
    CONF.write_text('\n'.join(cmds)+'\n');CONF.chmod(0o755)
    print('H26P4A_PREPARED',DEST)
    print('H26P4A_CONFIGURE',CONF)
    print('NOTE: Original H26-P0, H25, source repo and graph artifacts remain unchanged.')

if __name__=='__main__':
    try:main()
    except Exception as exc: print('H26P4A_FAIL_CLOSED:',exc,file=sys.stderr);sys.exit(2)
