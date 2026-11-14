#!/usr/bin/env python3
"""Clone the validated H26-P0 worktree to a separate pinned H26-P1a Git worktree.
Uses the already local CMake dependency cache. Does not touch original source.
"""
import pathlib
import subprocess
import sys
import shlex
from h26_p1a_patch import patch

HOME=pathlib.Path.home()
ROOT=HOME/'ann-task-a/experiments/H26'
ORIGINAL=HOME/'ann-task-a/src/PiPNN'
P0=ROOT/'PiPNN-H26-src'
P1=ROOT/'PiPNN-H26-P1A-src'
PIN='443a328dc71a3b7be753d52ca2b3c9a4ba77f3fd'
FETCH=['parlaylib','eigen','abseil-cpp','highway','googlebenchmark']

def run(*args):
    print('+',shlex.join([str(a) for a in args]),flush=True)
    subprocess.run([str(a) for a in args],check=True)

def main():
    if P1.exists():raise RuntimeError(f'Refuse overwrite: {P1}')
    if not (P0/'algorithms/PipNN/pipnn_utils.h').is_file():raise RuntimeError('Missing H26-P0 source')
    if subprocess.check_output(['git','-C',str(P0),'rev-parse','HEAD'],text=True).strip()!=PIN:
        raise RuntimeError('H26-P0 commit mismatch')
    source=(P0/'algorithms/PipNN/pipnn_utils.h').read_text(encoding='utf8')
    updated=patch(source)  # verify anchors before writing anything
    cmake=(P0/'CMakeLists.txt').read_text(encoding='utf8')
    fixed='add_subdirectory(${parlaylib_SOURCE_DIR} ${parlaylib_BINARY_DIR} EXCLUDE_FROM_ALL)'
    if cmake.count(fixed)!=1:raise RuntimeError('P0 CMake fix not found. Refuse to create workspace')
    for lib in FETCH:
        p=ORIGINAL/'build'/'_deps'/(lib+'-src')
        if not (p/'CMakeLists.txt').is_file():raise RuntimeError(f'Cached dependency not found: {p}')
    for ext in ['mirage','hnswlib']:
        if not (ORIGINAL/'external'/ext).exists():raise RuntimeError(f'Original submodule missing {ext}')
    print('H26P1A_PREFLIGHT_PASS')
    run('git','-C',ORIGINAL,'worktree','add','--detach',P1,PIN)
    # hnswlib or mirage can be gitlinks in the new worktree; symlink only if empty.
    for ext in ['mirage','hnswlib']:
        dst=P1/'external'/ext
        src=ORIGINAL/'external'/ext
        if dst.is_dir() and not any(dst.iterdir()):
            dst.rmdir(); dst.symlink_to(src.resolve(),target_is_directory=True)
            print('H26P1A_SUBMODULE_LINK',dst)
        if not dst.exists(): raise RuntimeError(f'Submodule unavailable: {dst}')
    (P1/'CMakeLists.txt').write_text(cmake,encoding='utf8')
    (P1/'algorithms/PipNN/pipnn_utils.h').write_text(updated,encoding='utf8')
    args=['cmake','-S',str(P1),'-B',str(P1/'build'),'-DCMAKE_BUILD_TYPE=Release', '-DFETCHCONTENT_FULLY_DISCONNECTED=ON']
    for lib in FETCH:
        args.append('-DFETCHCONTENT_SOURCE_DIR_'+lib.upper()+'='+str((ORIGINAL/'build'/'_deps'/(lib+'-src')).resolve()))
    config=ROOT/'configure_H26_P1A.sh'
    config.write_text('#!/usr/bin/env bash\nset -euo pipefail\n'+shlex.join(args)+'\n'+shlex.join(['cmake','--build',str(P1/'build'),'--target','neighbors-pipnn_FLOAT_T_EUCLIDEAN','-j','4'])+'\n',encoding='utf8')
    config.chmod(0o755)
    print('H26P1A_PREPARED',P1)
    print('NEXT_CONFIGURE',config)
    print('P0_PRESERVED',P0)

if __name__=='__main__':
    try:main()
    except Exception as e:
        print('H26P1A_FAIL_CLOSED:',e,file=sys.stderr)
        sys.exit(2)
