#!/usr/bin/env python3
"""R86 G0 post-compilation audit. Read-only for R85/H70/R86 sources and binaries.

Writes a new evidence directory only. No build, benchmark, patch application,
source file mutation, or Google Sheet upload.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

VARIANTS = {
    'stock_off': {'R70_USE_TIER': 'OFF', 'R71_USE_H17': 'OFF', 'R86_USE_COUNTERS': 'OFF'},
    'stock_on':  {'R70_USE_TIER': 'OFF', 'R71_USE_H17': 'OFF', 'R86_USE_COUNTERS': 'ON'},
    'h17_off':   {'R70_USE_TIER': 'OFF', 'R71_USE_H17': 'ON', 'R86_USE_COUNTERS': 'OFF'},
    'h17_on':    {'R70_USE_TIER': 'OFF', 'R71_USE_H17': 'ON', 'R86_USE_COUNTERS': 'ON'},
}
EXECUTABLE = 'algorithms/PipNN/neighbors-pipnn_FLOAT_T_EUCLIDEAN'
EXPECTED_COMPILER = '/usr/bin/c++'
EXPECTED_FLAGS = {
    'CMAKE_BUILD_TYPE': 'Release',
    'CMAKE_CXX_FLAGS': '',
    'CMAKE_CXX_FLAGS_RELEASE': '-O3 -DNDEBUG',
}


def sha256(path: Path) -> str:
    dig = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            dig.update(chunk)
    return dig.hexdigest()


def parse_cmake(path: Path) -> dict[str, str]:
    result = {}
    for line in path.read_text(errors='replace').splitlines():
        if not line or line.startswith(('#', '//')) or '=' not in line:
            continue
        key, _, value = line.partition('=')
        result[key.split(':')[0]] = value
    return result


def safe_rel(path: Path) -> str:
    return str(path.expanduser().resolve())


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--root', type=Path, default=Path.home()/'ann-task-a/experiments')
    ap.add_argument('--out', type=Path, default=None,
                    help='A brand NEW evidence directory (never overwrites any directory)')
    args = ap.parse_args()
    root = args.root.expanduser().resolve()
    now = dt.datetime.now().astimezone().isoformat(timespec='seconds')
    out = args.out or root/'R86/gates'/('g0_'+dt.datetime.now().strftime('%Y%m%d_%H%M%S'))
    out = out.expanduser().absolute()
    if out.exists():
        raise SystemExit(f'FAIL: output already exists, refusing overwrite: {out}')
    out.mkdir(parents=True, exist_ok=False)
    evidence = {'schema_version':'R86_G0_native_audit_v1', 'date_local':now,
                'root':str(root), 'checks':[], 'variants':{}, 'gates':{'G1':'NOT_RUN','G2':'NOT_RUN','G3':'NOT_RUN'}}
    lines = []
    failed = False

    def check(key: str, passed: bool, info: str = '', *, warning=False):
        nonlocal failed
        state = 'PASS' if passed else ('WARN' if warning else 'FAIL')
        evidence['checks'].append({'check':key,'status':state,'detail':info})
        lines.append(f'{state:4}  {key}: {info}')
        if not passed and not warning:
            failed = True

    source = root/'R86/r86_v1_2_source'
    h70 = root/'H70/pipnn-clean-443a328'
    patch = root/'R86_patch_v1_2/R86_Day2_Counter_Patch_v1_2'
    build_root = root/'R86/r86_v1_2_builds'
    provenance = source/'R86_STAGING_PROVENANCE.json'
    evidence['paths'] = {k:str(v) for k,v in {'source':source,'h70':h70,'patch':patch,'build_root':build_root,'staging_provenance':provenance}.items()}
    check('G0_STAGED_SOURCE_PRESENT',source.is_dir(),str(source))
    check('G0_STAGING_PROVENANCE_PRESENT',provenance.is_file(),str(provenance))
    if provenance.is_file():
        try:
            data=json.loads(provenance.read_text())
            evidence['staging']={k:data.get(k) for k in ('source','staged','patch_sha256','omitted_dangling_symlinks')}
            check('G0_STAGING_PATH_MATCH',Path(data.get('staged','/nonexistent')).resolve()==source.resolve(),str(data.get('staged')))
            check('G0_BASELINE_PATH_MATCH',Path(data.get('source','/nonexistent')).resolve()==h70.resolve(),str(data.get('source')))
        except (ValueError,TypeError,KeyError,OSError) as exc:
            check('G0_STAGING_PARSE',False,str(exc))

    verify=patch/'scripts/verify_g0.py'
    check('G0_VERIFIER_PRESENT',verify.is_file(),str(verify))
    if verify.is_file() and source.is_dir() and h70.is_dir():
        run=subprocess.run([sys.executable,str(verify),'--baseline',str(h70),'--patched',str(source)],capture_output=True,text=True,check=False)
        (out/'g0_source_verifier.log').write_text(run.stdout+run.stderr)
        check('G0_SOURCE_OFF_BYTE_IDENTITY',run.returncode==0 and 'R86_G0_SOURCE_OFF_BYTE_IDENTITY_PASS' in run.stdout,
              f'rc={run.returncode} / see g0_source_verifier.log')

    pin=patch/'EXPECTED_SOURCE_SHA256.txt'
    check('G0_PIN_FILE_PRESENT',pin.is_file(),str(pin))
    if pin.is_file():
        for lineno,line in enumerate(pin.read_text().splitlines(),1):
            if not line.strip() or line.startswith('#'):
                continue
            fields=line.split(maxsplit=1)
            if len(fields)!=2:
                check('G0_PIN_SYNTAX',False,f'line {lineno}');continue
            want,relative=fields
            f=h70/relative.strip().lstrip('*')
            if not f.is_file():
                check('G0_BASELINE_SHA_'+relative,False,'not found')
            else:
                actual=sha256(f)
                check('G0_BASELINE_SHA_'+relative,actual==want,f'{actual} (want {want})')

    binary_shas={}
    for variant,expected in VARIANTS.items():
        build_dir=build_root/variant
        binary=build_dir/EXECUTABLE
        cmakefile=build_dir/'CMakeCache.txt'
        v={'binary':str(binary),'cmake_cache':str(cmakefile),'expected_flags':expected}
        evidence['variants'][variant]=v
        exists=binary.is_file() and os.access(binary,os.X_OK)
        check(f'{variant}_EXECUTABLE',exists,str(binary))
        if exists:
            digest=sha256(binary)
            v['sha256']=digest;v['bytes']=binary.stat().st_size
            binary_shas[variant]=digest
            check(f'{variant}_SHA256',True,digest)
            receipt=build_dir/'R86_EXECUTABLE_SHA256.txt'
            if receipt.is_file():
                tokens=receipt.read_text().split()
                check(f'{variant}_RECEIPT_MATCH',bool(tokens) and tokens[0]==digest,str(receipt))
            else:
                check(f'{variant}_RECEIPT_MATCH',False,'R86_EXECUTABLE_SHA256.txt absent')
        check(f'{variant}_CMAKE_CACHE_PRESENT',cmakefile.is_file(),str(cmakefile))
        if not cmakefile.is_file():
            continue
        c=parse_cmake(cmakefile)
        keys=sorted(set(expected)|set(EXPECTED_FLAGS)|{'CMAKE_CXX_COMPILER','CMAKE_HOME_DIRECTORY'})
        v['cmake']={k:c.get(k) for k in keys}
        for key,want in expected.items():
            check(f'{variant}_{key}',c.get(key)==want,f'{c.get(key)!r} (want {want!r})')
        for key,want in EXPECTED_FLAGS.items():
            check(f'{variant}_{key}',c.get(key)==want,f'{c.get(key)!r} (want {want!r})')
        check(f'{variant}_CMAKE_CXX_COMPILER',c.get('CMAKE_CXX_COMPILER')==EXPECTED_COMPILER,
              f"{c.get('CMAKE_CXX_COMPILER')!r} (R85 {EXPECTED_COMPILER!r})")
        home=c.get('CMAKE_HOME_DIRECTORY')
        check(f'{variant}_CMAKE_SOURCE',bool(home) and Path(home).resolve()==source.resolve(),str(home))
    if len(binary_shas)==len(VARIANTS):
        check('G0_ON_OFF_BINARY_DISTINCT_STOCK',binary_shas['stock_off']!=binary_shas['stock_on'],
              'ON/OFF binary SHA must differ after instrumentation')
        check('G0_ON_OFF_BINARY_DISTINCT_H17',binary_shas['h17_off']!=binary_shas['h17_on'],
              'ON/OFF binary SHA must differ after instrumentation')
        check('G0_STOCK_H17_BINARY_DISTINCT_OFF',binary_shas['stock_off']!=binary_shas['h17_off'],
              'Stock and H17 OFF binaries should differ')

    g0log=Path.home()/'r86_step2_g0_staging.log'
    if g0log.is_file():
        s=g0log.read_text(errors='replace')
        evidence['prior_g0_log']=str(g0log)
        check('G0_PREVIOUS_STAGING_MARKER','R86_ISOLATED_STAGING_AND_G0_PASS' in s,
              f'marker in {g0log}',warning=True)
    else:
        check('G0_PREVIOUS_STAGING_LOG',False,f'optional audit log missing: {g0log}',warning=True)

    state='PASS' if not failed else 'FAIL'
    evidence['result']=f'R86_G0_NATIVE_BINARY_AUDIT_{state}'
    (out/'g0_manifest.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2)+'\n')
    (out/'g0_readable.log').write_text('\n'.join(lines+[evidence['result']])+'\n')
    print('\n'.join(lines))
    print(evidence['result'])
    print('EVIDENCE_DIRECTORY',out)
    print('JSON',out/'g0_manifest.json')
    print('LOG',out/'g0_readable.log')
    return 0 if not failed else 1

if __name__ == '__main__':
    sys.exit(main())
