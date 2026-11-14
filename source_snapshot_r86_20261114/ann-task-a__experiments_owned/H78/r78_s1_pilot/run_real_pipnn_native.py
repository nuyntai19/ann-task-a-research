#!/usr/bin/env python3
"""Build a separate R78 native test using existing H70 CMake compile/link specs.

This script never calls cmake, never edits H70 sources/build/CMake or reuses
output targets; it writes only r78_native.o and r78_real_native_tests within
this script's directory, and uses the already available H70 dependencies.
No data and no ANN graph BUILD are involved.
"""
from __future__ import annotations
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import hashlib

PINNED_HEAD='443a328dc71a3b7be753d52ca2b3c9a4ba77f3fd'
PINNED_GRAPH_SHA256='17e51779f32db56c9c50b6d514a8ff68539fd19b734804df3abdb63f88dd443e'
HERE=Path(__file__).resolve().parent
HOME=Path.home()
H70=HOME/'ann-task-a'/'experiments'/'H70'
WORK=H70/'pipnn-clean-443a328'
BUILD=H70/'build-r70'


def fail(reason: str) -> None:
    print('R78_NATIVE_BLOCKED:', reason)
    sys.exit(2)


def run(command: list[str], cwd: Path, name: str) -> None:
    print('[R78]', name, 'cwd=', cwd)
    print('[R78] argv:', shlex.join(command))
    subprocess.run(command, cwd=str(cwd), check=True)


def compile_commands(entry: dict) -> list[str]:
    if 'arguments' in entry:
        return entry['arguments'][:]
    return shlex.split(entry['command'])


def find_original_compile_spec() -> tuple[list[str], Path]:
    db=BUILD/'compile_commands.json'
    if not db.is_file():
        fail(f'missing {db} (CMake export_compile_commands may need enabling)')
    commands=json.loads(db.read_text())
    matches=[e for e in commands if Path(e.get('file', '')).name=='r70_native_tests.cc'
             and 'r70_native_tests.dir' in (e.get('command','')+' '.join(e.get('arguments',[])))]
    if len(matches)!=1:
        fail(f'expected one r70 native compiler spec, found {len(matches)}')
    e=matches[0]
    original_source=Path(e['file']).resolve()
    expected=(WORK/'algorithms/PipNN/r70_native_tests.cc').resolve()
    if original_source != expected:
        fail(f'compile spec points to DIFFERENT source {original_source}, expected {expected}')
    cmd=compile_commands(e)
    if '-o' not in cmd or '-c' not in cmd:
        fail('expected compiler command with -o and -c')
    out_pos=cmd.index('-o')
    src_pos=cmd.index('-c')
    cmd[out_pos+1]=str(HERE/'r78_native.o')
    cmd[src_pos+1]=str(HERE/'r78_native_pipnn_tests.cc')
    # These flags are added to the compiler without modifying the original CMake files.
    cmd.insert(1, '-I'+str(HERE))
    return cmd, Path(e['directory'])


def find_original_link_spec() -> tuple[list[str], Path]:
    target_dir=BUILD/'algorithms'/'PipNN'
    link=target_dir/'CMakeFiles'/'r70_native_tests.dir'/'link.txt'
    if not link.is_file():
        fail(f'missing {link} (Makefiles generator expected)')
    command=shlex.split(link.read_text().strip())
    if '-o' not in command:
        fail('link command missing -o')
    out=command.index('-o')
    command[out+1]=str(HERE/'r78_real_native_tests')
    original_objects=[i for i,x in enumerate(command) if x.endswith('r70_native_tests.cc.o')]
    if len(original_objects)!=1:
        fail('expected exactly one r70 native test object in link command')
    command[original_objects[0]]=str(HERE/'r78_native.o')
    return command,target_dir


def main():
    print('========== R78 REAL PIPNN NATIVE TEST ==========',flush=True)
    src=WORK/'algorithms'/'utils'/'graph.h'
    if not src.is_file():fail(f'missing original graph.h: {src}')
    actual=hashlib.sha256(src.read_bytes()).hexdigest()
    if actual!=PINNED_GRAPH_SHA256:
        fail(f'graph.h checksum changed: {actual} != {PINNED_GRAPH_SHA256}')
    githead=subprocess.check_output(['git','-C',str(WORK),'rev-parse','HEAD'],text=True).strip()
    if githead!=PINNED_HEAD:fail('PiPNN worktree HEAD differs from pinned baseline')
    print('[R78] pinned stock graph.h SHA256:', actual)
    cc,cwd=find_original_compile_spec()
    link,linkcwd=find_original_link_spec()
    # No BUILD of ANN graph; only the R78 tiny native-test executable.
    run(cc,cwd,'compile isolated differential test')
    run(link,linkcwd,'link isolated differential test')
    run([str(HERE/'r78_real_native_tests'),'correctness'],HERE,'execute real PiPNN Stock vs S1 parity')
    print('R78_REAL_NATIVE_SCRIPT_COMPLETE')


if __name__=='__main__':
    try:
        main()
    except subprocess.CalledProcessError as e:
        fail(f'compiler/linker/native test returned {e.returncode}; see output above')
