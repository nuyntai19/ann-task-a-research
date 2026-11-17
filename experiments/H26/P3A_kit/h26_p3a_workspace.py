#!/usr/bin/env python3
"""Isolated worktree based on verified H26-P0; cached dependencies; no changes to P0/H25."""
from pathlib import Path
import subprocess,shlex,sys
from h26_p3a_patch import patch

ROOT=Path.home()/'ann-task-a/experiments/H26'
ORIGINAL=Path.home()/'ann-task-a/src/PiPNN'
P0=ROOT/'PiPNN-H26-src'
P3=ROOT/'PiPNN-H26-P3A-src'
PIN='443a328dc71a3b7be753d52ca2b3c9a4ba77f3fd'
FETCH=['parlaylib','eigen','abseil-cpp','highway','googlebenchmark']

def run(args):
    print('+',shlex.join(map(str,args)),flush=True)
    subprocess.run(list(map(str,args)),check=True)

def main():
    if P3.exists():raise RuntimeError(f'Refuse to overwrite worktree {P3}')
    src=P0/'algorithms/PipNN/pipnn_utils.h'
    if not src.is_file():raise RuntimeError('H26-P0 source not found')
    if subprocess.check_output(['git','-C',str(P0),'rev-parse','HEAD'],text=True).strip()!=PIN:
        raise RuntimeError('H26-P0 commit changed')
    updated=patch(src.read_text(encoding='utf8'))
    cmake=(P0/'CMakeLists.txt').read_text(encoding='utf8')
    if cmake.count('add_subdirectory(${parlaylib_SOURCE_DIR} ${parlaylib_BINARY_DIR} EXCLUDE_FROM_ALL)')!=1:
        raise RuntimeError('H26-P0 does not have correct out-of-tree CMake fix')
    for lib in FETCH:
        p=ORIGINAL/'build/_deps'/(lib+'-src')
        if not (p/'CMakeLists.txt').is_file():raise RuntimeError(f'Missing cached dep {p}')
    for ext in ('mirage','hnswlib'):
        if not (ORIGINAL/'external'/ext).exists():raise RuntimeError(f'Missing {ext} submodule')
    print('H26P3A_PREFLIGHT_PASS')
    run(['git','-C',ORIGINAL,'worktree','add','--detach',P3,PIN])
    for ext in ('mirage','hnswlib'):
        dest=P3/'external'/ext
        if dest.is_dir() and not any(dest.iterdir()):
            dest.rmdir()
            dest.symlink_to((ORIGINAL/'external'/ext).resolve(),target_is_directory=True)
        if not dest.exists():raise RuntimeError(f'Submodule link failed {dest}')
    (P3/'CMakeLists.txt').write_text(cmake,encoding='utf8')
    (P3/'algorithms/PipNN/pipnn_utils.h').write_text(updated,encoding='utf8')
    config=['cmake','-S',P3,'-B',P3/'build','-DCMAKE_BUILD_TYPE=Release','-DFETCHCONTENT_FULLY_DISCONNECTED=ON']
    for lib in FETCH:
        config.append('-DFETCHCONTENT_SOURCE_DIR_'+lib.upper()+'='+str((ORIGINAL/'build/_deps'/(lib+'-src')).resolve()))
    target=['cmake','--build',P3/'build','--target','neighbors-pipnn_FLOAT_T_EUCLIDEAN','-j','4']
    script=ROOT/'configure_H26_P3A.sh'
    script.write_text('#!/usr/bin/env bash\nset -euo pipefail\n'+shlex.join(map(str,config))+'\n'+shlex.join(map(str,target))+'\n',encoding='utf8')
    script.chmod(0o755)
    print('H26P3A_PREPARED',P3)
    print('NEXT_CONFIGURE',script)
    print('H26_P0_P1A_P1B_AND_H25_PRESERVED')

if __name__=='__main__':
    try: main()
    except Exception as e:
        print('H26P3A_FAIL_CLOSED:',e,file=sys.stderr)
        sys.exit(2)
