#!/usr/bin/env python3
"""Create isolated H26-P1b worktree copying the already compiled P1a source."""
from pathlib import Path
import subprocess, shlex, sys
from h26_p1b_patch import patch
ROOT=Path.home()/'ann-task-a/experiments/H26'
ORIGINAL=Path.home()/'ann-task-a/src/PiPNN'
P1A=ROOT/'PiPNN-H26-P1A-src'
P1B=ROOT/'PiPNN-H26-P1B-src'
PIN='443a328dc71a3b7be753d52ca2b3c9a4ba77f3fd'
FETCH=['parlaylib','eigen','abseil-cpp','highway','googlebenchmark']

def run(args):
    print('+',shlex.join(str(a) for a in args),flush=True)
    subprocess.run([str(a) for a in args],check=True)

def main():
    if P1B.exists(): raise RuntimeError(f'Refuse overwrite of existing workspace {P1B}')
    if not (P1A/'algorithms/PipNN/pipnn_utils.h').is_file(): raise RuntimeError('P1a source missing')
    if subprocess.check_output(['git','-C',str(P1A),'rev-parse','HEAD'],text=True).strip()!=PIN:
        raise RuntimeError('P1a pinned commit mismatch')
    old=(P1A/'algorithms/PipNN/pipnn_utils.h').read_text()
    new=patch(old)
    cmake=(P1A/'CMakeLists.txt').read_text()
    anchor='add_subdirectory(${parlaylib_SOURCE_DIR} ${parlaylib_BINARY_DIR} EXCLUDE_FROM_ALL)'
    if cmake.count(anchor)!=1: raise RuntimeError('CMake cross-tree fix missing')
    for lib in FETCH:
        dep=ORIGINAL/'build/_deps'/(lib+'-src')
        if not (dep/'CMakeLists.txt').is_file(): raise RuntimeError(f'Missing cached dep: {dep}')
    for ext in ['mirage','hnswlib']:
        if not (ORIGINAL/'external'/ext).exists(): raise RuntimeError(f'Missing submodule: {ext}')
    print('H26P1B_PREFLIGHT_PASS')
    run(['git','-C',ORIGINAL,'worktree','add','--detach',P1B,PIN])
    for ext in ['mirage','hnswlib']:
        dst=P1B/'external'/ext
        src=ORIGINAL/'external'/ext
        if dst.is_dir() and not any(dst.iterdir()):
            dst.rmdir(); dst.symlink_to(src.resolve(),target_is_directory=True)
        if not dst.exists(): raise RuntimeError(f'Submodule missing after worktree creation: {dst}')
    (P1B/'CMakeLists.txt').write_text(cmake)
    (P1B/'algorithms/PipNN/pipnn_utils.h').write_text(new)
    args=['cmake','-S',P1B,'-B',P1B/'build','-DCMAKE_BUILD_TYPE=Release','-DFETCHCONTENT_FULLY_DISCONNECTED=ON']
    for lib in FETCH:
        args.append('-DFETCHCONTENT_SOURCE_DIR_'+lib.upper()+'='+str((ORIGINAL/'build/_deps'/(lib+'-src')).resolve()))
    config=ROOT/'configure_H26_P1B.sh'
    config.write_text('#!/usr/bin/env bash\nset -euo pipefail\n'+shlex.join(str(a) for a in args)+'\n'+shlex.join(str(a) for a in ['cmake','--build',P1B/'build','--target','neighbors-pipnn_FLOAT_T_EUCLIDEAN','-j','4'])+'\n')
    config.chmod(0o755)
    print('H26P1B_PREPARED',P1B)
    print('NEXT_CONFIGURE',config)
    print('P1A_AND_P0_PRESERVED')

if __name__=='__main__':
    try:main()
    except Exception as e:
        print('H26P1B_FAIL_CLOSED:',e,file=sys.stderr);sys.exit(2)
