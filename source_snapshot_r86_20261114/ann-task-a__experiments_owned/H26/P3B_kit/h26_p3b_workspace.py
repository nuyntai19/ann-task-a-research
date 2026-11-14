#!/usr/bin/env python3
"""New independent P3B worktree; read-only H26-P0/P3A and H25."""
from pathlib import Path
import subprocess, shlex, sys
from h26_p3b_patch import patch

ROOT=Path.home()/'ann-task-a/experiments/H26'
ORIGINAL=Path.home()/'ann-task-a/src/PiPNN'
P0=ROOT/'PiPNN-H26-src'
P3B=ROOT/'PiPNN-H26-P3B-src'
PIN='443a328dc71a3b7be753d52ca2b3c9a4ba77f3fd'
FETCH=['parlaylib','eigen','abseil-cpp','highway','googlebenchmark']

def call(args):
    print('+',shlex.join(map(str,args)),flush=True)
    subprocess.run(list(map(str,args)),check=True)

def main():
    if P3B.exists():raise RuntimeError(f'worktree already exists, refuse overwrite: {P3B}')
    src=P0/'algorithms/PipNN/pipnn_utils.h'
    if not src.exists():raise RuntimeError(f'Missing H26-P0 source: {src}')
    if subprocess.check_output(['git','-C',str(P0),'rev-parse','HEAD'],text=True).strip()!=PIN:
        raise RuntimeError('H26-P0 pin mismatch')
    new_src=patch(src.read_text(encoding='utf8'))
    cmake=(P0/'CMakeLists.txt').read_text(encoding='utf8')
    if cmake.count('add_subdirectory(${parlaylib_SOURCE_DIR} ${parlaylib_BINARY_DIR} EXCLUDE_FROM_ALL)')!=1:
        raise RuntimeError('Expected P0 out-of-tree ParlayLib CMake fix not found')
    for lib in FETCH:
        dep=ORIGINAL/'build/_deps'/(lib+'-src')
        if not (dep/'CMakeLists.txt').is_file(): raise RuntimeError(f'Missing cached dep: {dep}')
    for ext in ('mirage','hnswlib'):
        if not (ORIGINAL/'external'/ext).exists():raise RuntimeError(f'Missing submodule {ext}')
    print('H26P3B_PREFLIGHT_PASS')
    call(['git','-C',ORIGINAL,'worktree','add','--detach',P3B,PIN])
    for ext in ('mirage','hnswlib'):
        dst=P3B/'external'/ext
        if dst.is_dir() and not any(dst.iterdir()):
            dst.rmdir()
            dst.symlink_to((ORIGINAL/'external'/ext).resolve(),target_is_directory=True)
        if not dst.exists():raise RuntimeError(f'Cannot link submodule {dst}')
    (P3B/'CMakeLists.txt').write_text(cmake,encoding='utf8')
    (P3B/'algorithms/PipNN/pipnn_utils.h').write_text(new_src,encoding='utf8')
    config=['cmake','-S',P3B,'-B',P3B/'build','-DCMAKE_BUILD_TYPE=Release','-DFETCHCONTENT_FULLY_DISCONNECTED=ON']
    for lib in FETCH:
        config.append('-DFETCHCONTENT_SOURCE_DIR_'+lib.upper()+'='+str((ORIGINAL/'build/_deps'/(lib+'-src')).resolve()))
    build=['cmake','--build',P3B/'build','--target','neighbors-pipnn_FLOAT_T_EUCLIDEAN','-j','4']
    script=ROOT/'configure_H26_P3B.sh'
    script.write_text('#!/usr/bin/env bash\nset -euo pipefail\n'+shlex.join(map(str,config))+'\n'+shlex.join(map(str,build))+'\n',encoding='utf8')
    script.chmod(0o755)
    print('H26P3B_PREPARED',P3B)
    print('NEXT_CONFIGURE',script)
    print('H26_P0_P3A_H25_PRESERVED')

if __name__=='__main__':
    try:main()
    except Exception as e:
        print('H26P3B_FAIL_CLOSED:',e,file=sys.stderr)
        sys.exit(2)
