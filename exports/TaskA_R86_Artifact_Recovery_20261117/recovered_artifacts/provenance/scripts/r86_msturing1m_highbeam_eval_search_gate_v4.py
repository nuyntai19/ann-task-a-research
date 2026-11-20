#!/usr/bin/env python3
"""R86 MS-Turing1M high-beam evaluator, independent of pinned v3.

Modes:
 --preflight: READ ONLY, verify pinned v3 source/binary/native compile manifest,
              dataset/native binaries and exactly one CLI upper-beam guard.
 --compile: produce NEW source and NEW binary v4 (max accepted beam 4096),
            reuse exact v3 compile/link arguments; preserve all v3 artifacts.
 --search --arm A2 --beams 768,1024: full 100K-query Search on previously
            BUILT, SHA-pinned pilot graph; no graph rebuilding; write new log.

This changes only the C++ input validation bound from 512 to 4096. It does NOT
change Search/Recall, graph, GT, base, and query semantics. Upper-bound approval
is software/functional only, not matched-recall evidence. All outputs are
exclusive, no overwrite; preflight fails closed on provenance mismatches.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
sys.dont_write_bytecode = True  # --preflight must not create __pycache__

ROOT = Path.home() / 'ann-task-a'
HOME = Path.home()
E = ROOT / 'experiments/R86/msturing_1m_eval'
SRC3 = E / 'r86_msturing1m_graph_recall.cc'
BIN3 = E / 'r86_msturing1m_graph_recall_v3'
MAN3 = E / 'r86_msturing1m_eval_native_link_v3.json'
SRC4 = E / 'r86_msturing1m_graph_recall_v4_highbeam.cc'
BIN4 = E / 'r86_msturing1m_graph_recall_v4_highbeam'
LOG4 = E / 'r86_msturing1m_highbeam_v4_compile.log'
MAN4 = E / 'r86_msturing1m_highbeam_v4_manifest.json'
PILOT_PY = HOME / 'Downloads/r86_msturing1m_sixarm_pilot_v1.py'
V3_PY = HOME / 'Downloads/r86_msturing1m_eval_native_link_gate_v3.py'
PILOT_HOME = ROOT / 'experiments/R86/msturing_1m_sixarm/pilot_mst1m_v1'
MAX_BEAM = 4096
PINS = {
    SRC3: '91078479eb7fdb05a6070526797c4feaf01d6e994c13f699108e497ea0609b7e',
    BIN3: 'ea6c757b47b1267b7009ff0a1a80a3fdeaaf59740c4c2036712accf9ba0d0af5',
    PILOT_PY: '92a4abb8e66d1b0692a3ff8cee7a4e2ea9bff315036dd05cdb0ab7acda695bff',
    V3_PY: 'b56ac9958a6f18e0439049006c70168ee8a4ed6b68a79e67427cc45181350cec',
}
ARMS = ('A0','A1','A2','A3','A4','D0')
GUARD = re.compile(r'(?P<variable>\b[A-Za-z_]\w*\s*>\s*)512\b')


def hold(reason: str) -> None:
    raise RuntimeError('R86_MST1M_HIGHBEAM_V4_HOLD ' + reason)


def sha256(path: Path) -> str:
    h=hashlib.sha256()
    with path.open('rb') as f:
        for part in iter(lambda:f.read(1<<20),b''):
            h.update(part)
    return h.hexdigest()


def read_json(path: Path) -> dict:
    if not path.is_file():
        hold('JSON_MISSING '+str(path))
    value=json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(value,dict):
        hold('JSON_NOT_OBJECT '+str(path))
    return value


def verify_pins() -> None:
    for path,want in PINS.items():
        if not path.is_file():
            hold('PIN_MISSING '+str(path))
        got=sha256(path)
        if got!=want:
            hold(f'PIN_SHA_MISMATCH {path} expected={want} got={got}')
        print('R86_MST1M_HIGHBEAM_V4_PIN_PASS '+path.name+' sha256='+got,flush=True)


def derive_source(original: str) -> str:
    """Exactly one explicit >512 CLI numeric bound. Do not modify other 512 uses."""
    matches=list(GUARD.finditer(original))
    if len(matches)!=1:
        contexts=[original[max(0,m.start()-65):m.end()+65].replace('\n',' ') for m in re.finditer(r'\b512\b', original)]
        hold(f'EXPECTED_EXACTLY_ONE_GREATER_THAN_512_GUARD got={len(matches)} contexts={contexts[:6]}')
    m=matches[0]
    var=m.group('variable').split('>')[0].strip()
    if var.lower() not in {'beam','b','v','value','parsed','beam_value','beamval','beam_size','beamwidth','x','n'}:
        hold(f'BEAM_GUARD_VARIABLE_UNRECOGNIZED {var} near={original[max(0,m.start()-70):m.end()+70]!r}')
    if 'QueryParams qp(10L, beam, 1.35' not in original or 'checkRecall<' not in original:
        hold('PINNED_EVALUATOR_SEMANTIC_MARKERS_MISSING')
    replacement=m.group('variable')+str(MAX_BEAM)
    updated=original[:m.start()]+replacement+original[m.end():]
    if updated==original or updated.count('R72_RECALL_ROW')!=original.count('R72_RECALL_ROW'):
        hold('SOURCE_EDIT_EQUIVALENCE_FAILED')
    return updated


def native_compiler_plan() -> tuple[list[str],dict]:
    verify_pins()
    original=SRC3.read_text(encoding='utf-8')
    derived=derive_source(original)
    if SRC4.exists():
        if not SRC4.is_file() or SRC4.read_text(encoding='utf-8')!=derived:
            hold('V4_SOURCE_ALREADY_EXISTS_BUT_DIFFERS')
        print('R86_MST1M_HIGHBEAM_V4_SOURCE_ALREADY_IDENTICAL',flush=True)
    man=read_json(MAN3)
    if man.get('derived_evaluator_source_sha256') != PINS[SRC3] or man.get('new_evaluator_binary_sha256')!=PINS[BIN3]:
        hold('V3_MANIFEST_SOURCE_OR_BINARY_SHA_MISMATCH')
    stock=Path(man.get('native_stock_build',''))
    flags=stock/'algorithms/PipNN/CMakeFiles/neighbors-pipnn_FLOAT_T_EUCLIDEAN.dir/flags.make'
    link=stock/'algorithms/PipNN/CMakeFiles/neighbors-pipnn_FLOAT_T_EUCLIDEAN.dir/link.txt'
    if not flags.is_file() or not link.is_file():
        hold('V3_NATIVE_BUILD_METADATA_MISSING')
    if sha256(flags)!=man.get('native_flags_sha256') or sha256(link)!=man.get('native_link_sha256'):
        hold('V3_NATIVE_BUILD_FLAGS_LINK_SHA_CHANGED')
    raw=man.get('compile_command')
    if not isinstance(raw,list) or not all(isinstance(x,str) for x in raw):
        hold('V3_COMPILE_COMMAND_BAD_SHAPE')
    if len(raw)<20 or raw.count(str(SRC3))!=1 or raw.count(str(BIN3))!=1 or raw.count('-o')!=1:
        hold('V3_COMPILE_COMMAND_SOURCE_OUTPUT_UNEXPECTED')
    if raw[0] not in ('/usr/bin/c++','/usr/bin/g++') or not Path(raw[0]).is_file():
        hold('V3_COMPILER_UNEXPECTED '+raw[0])
    if raw[raw.index('-o')+1]!=str(BIN3):
        hold('V3_COMPILE_COMMAND_BAD_OUTPUT_ORDER')
    for name in ('native_library_files',):
        if not isinstance(man.get(name),list) or not man[name]:
            hold('V3_MANIFEST_LIBRARIES_MISSING')
    for f in man['native_library_files']:
        if not Path(f).is_file():
            hold('V3_STATIC_LIBRARY_MISSING '+f)
    command=[str(SRC4) if x==str(SRC3) else str(BIN4) if x==str(BIN3) else x for x in raw]
    print('R86_MST1M_HIGHBEAM_V4_SOURCE_ONLY_ONE_GUARD_512_TO_4096_PASS',flush=True)
    print('R86_MST1M_HIGHBEAM_V4_NATIVE_LINK_SHA_PIN_PASS '+sha256(link),flush=True)
    print('R86_MST1M_HIGHBEAM_V4_SOURCE_DERIVED_SHA256 '+hashlib.sha256(derived.encode('utf-8')).hexdigest(),flush=True)
    return command,man


def verify_pilot_inputs():
    import importlib.util
    spec=importlib.util.spec_from_file_location('r86_mst_pilot_pinned',PILOT_PY)
    if spec is None or spec.loader is None:
        hold('PINNED_PILOT_IMPORT_FAILED')
    mod=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.preflight(need_resource=False)
    return mod


def preflight() -> None:
    cmd,_=native_compiler_plan()
    if not os.access(cmd[0],os.X_OK):
        hold('COMPILER_NOT_EXECUTABLE')
    for exe in ('taskset','/usr/bin/time'):
        if not shutil.which(exe):
            hold('EXTERNAL_TOOL_MISSING '+exe)
    if hasattr(os,'sched_getaffinity') and 0 not in os.sched_getaffinity(0):
        hold('SEARCH_CPU0_NOT_ALLOWED')
    verify_pilot_inputs()
    print('R86_MST1M_HIGHBEAM_V4_PREFLIGHT_PASS_NO_WRITES',flush=True)


def compile_new() -> None:
    cmd,man3=native_compiler_plan()
    if BIN4.exists() or LOG4.exists() or MAN4.exists():
        hold('NEW_COMPILE_DEST_EXISTS_NO_OVERWRITE '+str([str(p) for p in (BIN4,LOG4,MAN4) if p.exists()]))
    if SRC4.exists():
        # Original SHA and new-source derived text were checked in plan.
        pass
    else:
        content=derive_source(SRC3.read_text(encoding='utf-8'))
        with SRC4.open('x',encoding='utf-8') as f:
            f.write(content)
    outpart=E/(BIN4.name+'.part.'+str(os.getpid()))
    if outpart.exists():
        hold('TMP_OUTPUT_ALREADY_EXISTS')
    final=[str(outpart) if x==str(BIN4) else x for x in cmd]
    print('R86_MST1M_HIGHBEAM_V4_COMPILE_START '+shlex.join(final[:20])+' ...',flush=True)
    try:
        with LOG4.open('x',encoding='utf-8') as f:
            run=subprocess.run(final,stdout=f,stderr=subprocess.STDOUT,check=False)
        print('R86_MST1M_HIGHBEAM_V4_COMPILE_EXIT_CODE '+str(run.returncode),flush=True)
        if run.returncode:
            print('--- COMPILER LOG TAIL ---')
            print('\n'.join(LOG4.read_text(errors='replace').splitlines()[-55:]))
            hold('COMPILER_FAILED_LOG_PRESERVED_NO_NEW_BINARY')
        smoke=subprocess.run([str(outpart)],capture_output=True,text=True,timeout=20,check=False)
        if smoke.returncode!=2 or 'Usage:' not in smoke.stderr:
            hold('NO_ARG_USAGE_SMOKE_HOLD rc='+str(smoke.returncode))
        native_compiler_plan()  # reverify before committing output
        os.link(outpart,BIN4) # fails rather than overwrites
        info={
            'status':'COMPILE_AND_USAGE_PASS_SEARCH_PENDING',
            'MAX_BEAM':MAX_BEAM,
            'v3_source_sha256':PINS[SRC3],
            'v3_binary_sha256':PINS[BIN3],
            'source_v4':str(SRC4),'source_v4_sha256':sha256(SRC4),
            'binary_v4':str(BIN4),'binary_v4_sha256':sha256(BIN4),
            'v3_native_flags_sha256':man3['native_flags_sha256'],
            'v3_native_link_sha256':man3['native_link_sha256'],
            'compile_command':cmd,'compile_log_sha256':sha256(LOG4),
            'note':'One C++ beam guard changed 512->4096. No Search measured. Full 100K queries on same pilot graphs required.'
        }
        with MAN4.open('x',encoding='utf-8') as f:
            json.dump(info,f,indent=2,sort_keys=True)
            f.write('\n')
        print('R86_MST1M_HIGHBEAM_V4_NEW_BINARY_SHA256 '+info['binary_v4_sha256'],flush=True)
        print('R86_MST1M_HIGHBEAM_V4_COMPILE_USAGE_PASS_SEARCH_NOT_RUN',flush=True)
    finally:
        if outpart.is_file():
            outpart.unlink()


def search(arm: str, beams_arg: str) -> None:
    native_compiler_plan()
    manifest=read_json(MAN4)
    if manifest.get('status')!='COMPILE_AND_USAGE_PASS_SEARCH_PENDING' or manifest.get('MAX_BEAM')!=MAX_BEAM:
        hold('V4_MANIFEST_STATUS_OR_BOUND_BAD')
    for p,key in ((SRC4,'source_v4_sha256'),(BIN4,'binary_v4_sha256')):
        if not p.is_file() or sha256(p)!=manifest.get(key):
            hold('V4_SOURCE_OR_BINARY_PIN_MISMATCH '+str(p))
    pilot=verify_pilot_inputs()
    if arm not in ARMS:
        hold('INVALID_ARM')
    try:
        beams=[int(x) for x in beams_arg.split(',')]
    except ValueError:
        hold('BEAMS_NOT_INTEGERS')
    if not (1<=len(beams)<=6) or len(set(beams))!=len(beams) or any(b<=512 or b>MAX_BEAM for b in beams) or beams!=sorted(beams):
        hold('BEAMS_REQUIRE_ASCENDING_UNIQUE_INTEGER_IN_513_4096_UP_TO_SIX')
    run_dir=PILOT_HOME/arm
    graph=run_dir/'index.graph'
    receipt=read_json(run_dir/'build_result.json')
    source_base, source_query, source_gt=(pilot.PINS[k][0] for k in ('base','query','gt'))
    key=pilot.ARMS[arm][0]
    if receipt.get('arm')!=arm or receipt.get('input_sha256')!=pilot.PINS['base'][1] or receipt.get('native_binary_sha256')!=pilot.PINS[key][1]:
        hold('PILOT_GRAPH_BUILD_RECEIPT_PIN_MISMATCH')
    if not graph.is_file() or sha256(graph)!=receipt.get('graph_sha256') or graph.stat().st_size!=receipt.get('graph_bytes'):
        hold('PILOT_GRAPH_SHA_OR_SIZE_CHANGED')
    name='_'.join(map(str,beams))
    log=run_dir/('search_v4_beams_'+name+'.log')
    command_json=run_dir/('search_v4_beams_'+name+'_command.json')
    if log.exists() or command_json.exists():
        hold('SEARCH_LOG_OR_RECEIPT_ALREADY_EXISTS_NO_OVERWRITE')
    if not shutil.which('taskset') or not shutil.which('/usr/bin/time'):
        hold('SEARCH_TOOL_MISSING')
    cmd=['taskset','-c','0','/usr/bin/time','-f',
         'R86_MST1M_HIGHBEAM_V4_SEARCH_TIME wall_s=%e peak_rss_kib=%M',
         str(BIN4),str(graph),str(source_base),str(source_query),str(source_gt),','.join(map(str,beams))]
    data={'dataset':'MS-Turing-1M','arm':arm,'beams':beams,'command':cmd,
          'graph_sha256':receipt['graph_sha256'],'evaluator_v4_sha256':sha256(BIN4),
          'status':'SEARCH_START_PILOT_ONLY','queries':100000}
    with command_json.open('x',encoding='utf-8') as f:
        json.dump(data,f,indent=2,sort_keys=True)
        f.write('\n')
    print('R86_MST1M_HIGHBEAM_V4_SEARCH_START arm='+arm+' beams='+name+' q=100000',flush=True)
    with log.open('x',encoding='utf-8') as f:
        res=subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT,env=dict(os.environ,PARLAY_NUM_THREADS='1'),check=False)
    print('R86_MST1M_HIGHBEAM_V4_SEARCH_EXIT_CODE '+str(res.returncode)+' log='+str(log),flush=True)
    if res.returncode:
        print('\n'.join(log.read_text(errors='replace').splitlines()[-50:]))
        hold('NATIVE_SEARCH_EXIT_NONZERO')
    txt=log.read_text(errors='replace')
    if 'R72_RECALL_INPUT_PASS' not in txt or 'R72_RECALL_EVAL_PASS' not in txt:
        hold('NATIVE_EVALUATOR_PASS_MARKERS_MISSING')
    matches=re.findall(r'R72_RECALL_ROW\s+beam=(\d+)\s+recall=([^\s]+)\s+qps=([^\s]+)',txt)
    if len(matches)!=len(beams) or [int(a) for a,_,_ in matches]!=beams:
        hold('SEARCH_BEAM_ROW_COUNT_OR_ORDER_MISMATCH')
    for beam,rec,qps in matches:
        rv=float(rec); qv=float(qps)
        if not (0<=rv<=1) or not (qv>0):
            hold('SEARCH_RECALL_OR_QPS_OUT_OF_RANGE')
        print(f'R86_MST1M_HIGHBEAM_V4_SEARCH_ROW arm={arm} beam={beam} recall={rv:.8f} qps={qv:.6f}',flush=True)
    print('R86_MST1M_HIGHBEAM_V4_SEARCH_FUNCTIONAL_PASS_PILOT_ONLY_NOT_MATCHED',flush=True)


def main() -> int:
    ap=argparse.ArgumentParser(description=__doc__)
    modes=ap.add_mutually_exclusive_group(required=True)
    modes.add_argument('--preflight',action='store_true')
    modes.add_argument('--compile',action='store_true')
    modes.add_argument('--search',action='store_true')
    ap.add_argument('--arm',choices=ARMS)
    ap.add_argument('--beams')
    a=ap.parse_args()
    try:
        if a.preflight:
            if a.arm or a.beams:
                hold('NO_ARM_BEAMS_WITH_PREFLIGHT')
            preflight()
        elif a.compile:
            if a.arm or a.beams:
                hold('NO_ARM_BEAMS_WITH_COMPILE')
            preflight()
            compile_new()
        else:
            if not a.arm or not a.beams:
                hold('SEARCH_REQUIRES_ARM_AND_BEAMS')
            search(a.arm,a.beams)
        return 0
    except (OSError,ValueError,UnicodeError,RuntimeError,subprocess.TimeoutExpired,KeyError) as exc:
        print(str(exc),file=sys.stderr,flush=True)
        return 2


if __name__=='__main__':
    raise SystemExit(main())
