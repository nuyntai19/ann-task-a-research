#!/usr/bin/env python3
"""R85-B1 Step8E: fail-closed LINK-ONLY recovery of a compiled native evaluator.

Fix one CWD bug in run_r85_b1_step8e_native_eval.py: the original script
compiled a valid object from build-r70/algorithms/PipNN but linked from
build-r70; link.txt paths ../../_deps are relative to the former. Only
reuse the existing object, then create a verified executable and manifest
in H85. Does not modify source, old logs, existing graphs or H70.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ORIG_NAME = 'run_r85_b1_step8e_native_eval.py'
ORIG_SHA = '1ce98cfe4adea2b9192e681b8442b7747c61e5a658e1ecb5a68d92094875b625'
A1C_SHA = 'a2b4f27e8dd9f7cd428c5568b1691eb6dc810d2cb7813a4e421ea238c13fb2c0'


def fail(msg):
    raise RuntimeError(msg)


def sha(p):
    h = hashlib.sha256()
    with p.open('rb') as f:
        for part in iter(lambda: f.read(2 << 20), b''):
            h.update(part)
    return h.hexdigest()


def regular(p):
    if p.is_symlink() or not p.is_file():
        fail('REQUIRED_UNSYMLINKED_FILE_MISSING ' + str(p))


def module():
    p = Path.home() / 'Downloads' / ORIG_NAME
    regular(p)
    if sha(p) != ORIG_SHA:
        fail('ORIGINAL_RUNNER_SHA_DRIFT')
    spec = importlib.util.spec_from_file_location('r85_b1_step8e_original', p)
    if spec is None or spec.loader is None:
        fail('COULD_NOT_IMPORT_ORIGINAL_RUNNER')
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def validate_link(link, cwd, build):
    cwd = cwd.resolve()
    build = build.resolve()
    if not cwd.is_relative_to(build) or cwd == build:
        fail('LINK_CWD_NOT_PINNED_SUBDIRECTORY')
    libs = []
    for tok in link:
        if tok.endswith('.a'):
            p = Path(tok)
            p = p if p.is_absolute() else cwd / p
            resolved = p.resolve()
            if not resolved.is_relative_to(build) or not p.is_file():
                fail('LINK_ARCHIVE_NOT_IN_PINNED_BUILD '+str(tok)+' cwd='+str(cwd))
            libs.append(resolved)
    if len(libs) < 5:
        fail('UNEXPECTED_FEW_STATIC_ARCHIVES')
    return sorted(set(libs))


def audit():
    m = module()
    text, a1c_sha, comp, compile_cwd, link = m.preflight()
    if a1c_sha != A1C_SHA:
        fail('A1C_EVALUATOR_SOURCE_SHA_DRIFT')
    regular(m.CPP)
    if m.CPP.read_text() != text:
        fail('STAGED_CPP_SOURCE_DRIFT')
    regular(m.OBJ)
    if m.OBJ.stat().st_size < 100 or m.OBJ.open('rb').read(4) != b'\x7fELF':
        fail('OBJECT_NOT_ELF')
    if m.OBJ.stat().st_mtime_ns < m.CPP.stat().st_mtime_ns:
        fail('OBJECT_OLDER_THAN_STAGED_SOURCE')
    regular(m.OUT / 'native_compile.log')
    regular(m.OUT / 'native_link.log')
    prev_log = (m.OUT / 'native_link.log').read_text(errors='replace')
    if '/usr/bin/ld:' not in prev_log or '_deps/' not in prev_log:
        fail('PREVIOUS_LINK_FAILURE_NOT_RECOGNIZED')
    if m.BIN.exists() or m.BIN.is_symlink() or m.MANIFEST.exists() or m.MANIFEST.is_symlink():
        fail('EXISTING_BINARY_OR_MANIFEST_REFUSE_OVERWRITE')
    link_cwd = m.LINK.parents[2]
    if link_cwd.resolve() != compile_cwd.resolve():
        fail('CMAKE_LINK_AND_COMPILE_CWD_DISAGREE')
    if link_cwd.resolve() != (m.BUILD / 'algorithms/PipNN').resolve():
        fail('UNEXPECTED_PINNED_LINK_CWD')
    if not m.OBJ.resolve().is_relative_to(m.OUT.resolve()):
        fail('OBJECT_OUTSIDE_H85_OUTPUT')
    if len(link) < 6 or link.count('-o') != 1 or link[link.index('-o')+1] != str(m.BIN):
        fail('LINK_OUTPUT_ANCHOR_MISMATCH')
    if link.count(str(m.OBJ)) != 1:
        fail('LINK_OBJECT_ANCHOR_MISMATCH')
    libs = validate_link(link, link_cwd, m.BUILD)
    print('R85_B1_STEP8E_LINK_RECOVERY_AUDIT_PASS_NO_WRITE', flush=True)
    print('R85_B1_STEP8E_LINK_RECOVERY_ORIGINAL_RUNNER_SHA '+ORIG_SHA, flush=True)
    print('R85_B1_STEP8E_LINK_RECOVERY_OBJECT_SHA '+sha(m.OBJ), flush=True)
    print('R85_B1_STEP8E_LINK_RECOVERY_CWD '+str(link_cwd), flush=True)
    print('R85_B1_STEP8E_LINK_RECOVERY_STATIC_ARCHIVES_VERIFIED '+str(len(libs)), flush=True)
    return m, text, a1c_sha, link, link_cwd, libs


def recover():
    m, text, a1c_sha, link, cwd, libs = audit()
    tmpbin = m.OUT / 'r85_b1_100k_graph_recall.link_recovery_tmp'
    recovery_log = m.OUT / 'native_link_recovery_v1.log'
    if tmpbin.exists() or tmpbin.is_symlink() or recovery_log.exists() or recovery_log.is_symlink():
        fail('PREVIOUS_LINK_RECOVERY_ARTIFACTS_REFUSE_OVERWRITE')
    cmd = list(link)
    cmd[cmd.index('-o')+1] = str(tmpbin)
    print('R85_B1_STEP8E_LINK_RECOVERY_START cwd='+str(cwd),flush=True)
    with recovery_log.open('x') as f:
        result = subprocess.run(cmd, cwd=cwd, stdout=f, stderr=subprocess.STDOUT)
    if result.returncode != 0:
        tail='\n'.join(recovery_log.read_text(errors='replace').splitlines()[-25:])
        fail(f'LINK_RECOVERY_FAILED rc={result.returncode} log={recovery_log}\n{tail}')
    regular(tmpbin)
    if not os.access(tmpbin, os.X_OK) or tmpbin.open('rb').read(4) != b'\x7fELF':
        fail('LINK_OUTPUT_NOT_EXECUTABLE_ELF')
    if m.BIN.exists() or m.MANIFEST.exists():
        fail('RACE_EXISTING_BINARY_OR_MANIFEST')
    tmpbin.rename(m.BIN)
    bsha = sha(m.BIN)
    metadata = {
        'role': 'SIFT100K native A1c/R72 evaluator; only base size validation changed',
        'a1c_source': str(m.A1C), 'a1c_source_sha256': a1c_sha,
        'r72_original': str(m.R72), 'r72_sha256': sha(m.R72),
        'source': str(m.CPP), 'source_sha256': sha(m.CPP),
        'binary': str(m.BIN), 'binary_sha256': bsha,
        'dataset_sha256': m.PIN['base'], 'query_sha256': m.PIN['query'],
        'gt_sha256': m.PIN['gt'],
        'graphs_sha256': {'P1': m.PIN['P1'], 'P2': m.PIN['P2']},
        'created_utc': datetime.now(timezone.utc).isoformat(),
        'link_recovery': {
            'reason': 'Original runner linked from H70/build-r70 instead of H70/build-r70/algorithms/PipNN',
            'original_runner_sha256': ORIG_SHA, 'object_sha256': sha(m.OBJ),
            'link_cwd': str(cwd), 'static_archive_count': len(libs),
            'old_link_failure_log': str(m.OUT / 'native_link.log'),
            'recovery_link_log': str(recovery_log),
        },
    }
    m.write_exclusive(m.MANIFEST, json.dumps(metadata, indent=2, sort_keys=True)+'\n')
    m.verify_binary()
    print('R85_B1_STEP8E_LINK_RECOVERY_EVAL_SHA256 '+bsha, flush=True)
    print('R85_B1_STEP8E_LINK_RECOVERY_PASS_NO_GRAPH_BUILD', flush=True)


def selftest():
    # A miniature C++ link with the same ../../_deps relationship as R72.
    cxx = shutil.which('c++')
    ar = shutil.which('ar')
    if not cxx or not ar:
        fail('SELFTEST_REQUIRES_CXX_AND_AR')
    with tempfile.TemporaryDirectory(prefix='r85_b1_link_mock_') as td:
        root = Path(td)
        build = root / 'cmake-build'
        cwd = build / 'algorithms' / 'PipNN'
        deps = build / '_deps'
        cwd.mkdir(parents=True)
        deps.mkdir(parents=True)
        (root / 'helper.cc').write_text('extern "C" int answer() { return 42; }\n')
        (root / 'main.cc').write_text('extern "C" int answer(); int main() { return answer() == 42 ? 0 : 1; }\n')
        helper_obj = root / 'helper.o'
        main_obj = root / 'main.o'
        for source, dest in ((root/'helper.cc', helper_obj), (root/'main.cc', main_obj)):
            subprocess.run([cxx,'-c',str(source),'-o',str(dest)],check=True,capture_output=True)
        archives=[]
        for i in range(5):
            archive=deps / f'libtest{i}.a'
            subprocess.run([ar,'rcs',str(archive),str(helper_obj)],check=True,capture_output=True)
            archives.append(f'../../_deps/libtest{i}.a')
        cmd = [cxx,str(main_obj),'-o',str(cwd/'app')]+archives
        resolved=validate_link(cmd,cwd,build)
        assert len(resolved)==5
        wrong = subprocess.run(cmd,cwd=build,capture_output=True)
        if wrong.returncode == 0:
            fail('MOCK_WRONG_CWD_UNEXPECTEDLY_LINKED')
        good = subprocess.run(cmd,cwd=cwd,capture_output=True)
        if good.returncode != 0:
            fail('MOCK_CORRECT_CWD_LINK_FAILED '+good.stderr.decode(errors='replace')[:500])
        subprocess.run([str(cwd/'app')],check=True,capture_output=True)
    print('R85_B1_STEP8E_LINK_RECOVERY_SELFTEST_PASS_NO_ANN_WRITE', flush=True)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    g=p.add_mutually_exclusive_group(required=True)
    for x in ('selftest','audit','recover'):
        g.add_argument('--'+x, action='store_true')
    args=p.parse_args()
    if args.selftest: selftest()
    elif args.audit: audit()
    elif args.recover: recover()

if __name__=='__main__':
    try: main()
    except Exception as e:
        print('R85_B1_STEP8E_LINK_RECOVERY_FAIL_CLOSED '+repr(e), file=sys.stderr, flush=True)
        sys.exit(2)
