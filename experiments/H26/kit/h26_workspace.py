#!/usr/bin/env python3
"""Prepare an independent, pinned PiPNN worktree and instrument it. No internet fetches."""
import argparse, os, pathlib, subprocess, sys
from h26_instrument import transform

PIN='443a328'
FETCH=['parlaylib','eigen','abseil-cpp','highway','googlebenchmark']
SUBMODULES=['external/mirage','external/hnswlib']

def cmd(*a, cwd=None):
    print('+',' '.join(map(str,a)),flush=True)
    subprocess.run(list(map(str,a)),cwd=cwd,check=True)

def git_output(repo,*args):
    return subprocess.check_output(['git','-C',str(repo),*args],text=True).strip()

def preflight(orig,dest):
    if not (orig/'build'/'CMakeCache.txt').is_file(): raise RuntimeError(f'existing CMake build unavailable: {orig}/build/CMakeCache.txt')
    if not (orig/'.git').exists(): raise RuntimeError(f'git repository missing: {orig}')
    if not git_output(orig,'cat-file','-t',PIN).startswith('commit'): raise RuntimeError('Pinned commit missing locally')
    for lib in FETCH:
        p=orig/'build'/'_deps'/(lib+'-src')
        if not p.exists() or not (p/'CMakeLists.txt').exists():
            raise RuntimeError(f'{lib} cached source missing: {p} (do not silently fetch a new version)')
    if not (orig/'external'/'mirage'/'CMakeLists.txt').exists():
        raise RuntimeError('external/mirage submodule missing in original repo; cannot setup offline worktree')
    if dest.exists(): raise RuntimeError(f'destination exists; refusing overwrite: {dest}')
    print('H26_PREP_CHECK_PASS pinned='+git_output(orig,'rev-parse',PIN))

def prepare(orig,dest):
    preflight(orig,dest)
    dest.parent.mkdir(parents=True,exist_ok=True)
    cmd('git','-C',orig,'worktree','add','--detach',dest,PIN)
    # Only original working checkout may contain populated submodules.
    for sub in SUBMODULES:
        source=orig/sub
        target=dest/sub
        if (source/'CMakeLists.txt').exists() or (sub.endswith('hnswlib') and (source/'hnswlib.h').exists()):
            if target.exists() and target.is_dir() and not any(target.iterdir()):
                target.rmdir()
                target.symlink_to(source.resolve(),target_is_directory=True)
                print('H26_LOCAL_SUBMODULE_LINK',target,'->',source.resolve())
    infile=dest/'algorithms'/'PipNN'/'pipnn_utils.h'
    if not infile.is_file():raise RuntimeError(f'Pinned file missing: {infile}')
    old=infile.read_text(encoding='utf-8'); patched=transform(old)
    backup=infile.with_suffix('.h.H26_UNMODIFIED')
    backup.write_text(old,encoding='utf-8')
    infile.write_text(patched,encoding='utf-8')
    conf=['cmake','-S',str(dest),'-B',str(dest/'build'),'-DCMAKE_BUILD_TYPE=Release',
          '-DFETCHCONTENT_FULLY_DISCONNECTED=ON']
    for lib in FETCH:
        conf.append('-DFETCHCONTENT_SOURCE_DIR_'+lib.upper()+'='+str((orig/'build'/'_deps'/(lib+'-src')).resolve()))
    cfg=dest.parent/'configure_H26.sh'
    import shlex
    cfg.write_text('#!/usr/bin/env bash\nset -euo pipefail\n'+shlex.join(conf)+'\n'+shlex.join(['cmake','--build',str(dest/'build'),'--target','neighbors-pipnn_FLOAT_T_EUCLIDEAN','-j','4'])+'\n')
    cfg.chmod(0o755)
    print('H26_PREPARED',dest)
    print('NEXT_CONFIGURE',cfg)
    print('NOTE: Reuse cached dependency sources from original build, do not modify H25 repo.')

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--repo',default=str(pathlib.Path.home()/'ann-task-a/src/PiPNN'))
    p.add_argument('--dest',default=str(pathlib.Path.home()/'ann-task-a/experiments/H26/PiPNN-H26-src'))
    p.add_argument('--mode',choices=['check','create'],default='check')
    a=p.parse_args();orig=pathlib.Path(a.repo).expanduser().resolve();dest=pathlib.Path(a.dest).expanduser().absolute()
    if a.mode=='create':prepare(orig,dest)
    else:preflight(orig,dest)
if __name__=='__main__':
    try:main()
    except Exception as e:print('H26_FAIL_CLOSED:',e,file=sys.stderr);sys.exit(2)
