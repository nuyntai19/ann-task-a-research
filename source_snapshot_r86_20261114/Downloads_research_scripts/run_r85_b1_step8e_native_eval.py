#!/usr/bin/env python3
"""R85-B1 Step8E: minimal native 100K evaluator derived from existing A1c evaluator.

Preserve H70/R72/A1c original source, binary, build tree, P1/P2, base, queries,
GT. Reuse the pinned R72 CMake compile_commands and link command only to
build a single new evaluator object and executable in H85. No ANN BUILD.
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
import struct
import subprocess
import sys
import tempfile
from datetime import datetime, timezone

HOME = Path.home()
ROOT = HOME / 'ann-task-a'
H70 = ROOT / 'experiments/H70'
H85 = ROOT / 'experiments/H85'
B1 = H85 / 'r85_b1_controlled'
R72 = H70 / 'pipnn-clean-443a328/algorithms/PipNN/r72_graph_recall.cc'
R72_BIN = H70 / 'build-r70/algorithms/PipNN/r72_graph_recall'
PIN_R72_EVAL = '3c2294efa1d7fb5d89c79ca5bf9c1eaca86247f7246e6d6d7c6c94549d08ed57'
A1C = H85 / 'r85_a1c_matched_search/r85_a1c_graph_recall.cc'
CDB = H70 / 'build-r70/compile_commands.json'
LINK = H70 / 'build-r70/algorithms/PipNN/CMakeFiles/r72_graph_recall.dir/link.txt'
BUILD = H70 / 'build-r70'
OUT = B1 / 'step8e_native_eval'
CPP = OUT / 'r85_b1_100k_graph_recall.cc'
OBJ = OUT / 'r85_b1_100k_graph_recall.o'
BIN = OUT / 'r85_b1_100k_graph_recall'
MANIFEST = OUT / 'evaluator_manifest.json'
PAIR = B1 / 'paired_p1p2_sift100k/pair_20261111-233300_397552'
DATA = ROOT / 'data/sift100k.fbin'
QUERY = ROOT / 'data/sift1m_queries.fbin'
GT = B1 / 'step8e_gt10k/sift100k_sift1mqueries10k_exact100.ibin'
GT_MAN = GT.with_suffix('.manifest.json')
PIN = {
    'P1': '4174ae82ce34e94453fcdba0eeeefcc8a755f17ae26d08e532611af7665a926d',
    'P2': '6819b93fcccaded1cd0517e5490171a4ef4100b4768bf8d5e4197831627fec9c',
    'base': 'e50ff1bc34bcc6d1c97dd001023c09a666971cde64605cc06671ed8a8ff1ed12',
    'query': '9b0082b67d0ac55b4c7d42216560344567ad87ce3e75a9d5214a0762f1c15d65',
    'gt': '70d25b3fff9d68ee3571931cc28e36f03d77c8bb4eea089ca206e5e709be8e28',
}
SMOKE = (10, 20, 40, 80, 160)
DENSE = tuple(sorted(set(list(range(10, 41)) + list(range(42, 81, 2)) + list(range(84, 161, 4)) + list(range(168, 257, 8)))))
ROW = re.compile(r'R72_RECALL_ROW\s+beam=(\d+)\s+recall=([0-9.eE+-]+)\s+qps=([0-9.eE+-]+)\s+avg_cmps=([0-9.eE+-]+)\s+avg_visited=([0-9.eE+-]+)')


def fail(s):
    raise RuntimeError(s)


def hash_file(p):
    h = hashlib.sha256()
    with p.open('rb') as f:
        for chunk in iter(lambda: f.read(2 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def regular(p):
    if p.is_symlink() or not p.is_file():
        fail(f'REQUIRED_REGULAR_FILE_MISSING {p}')


def verify_file(p, sha, label):
    regular(p)
    seen = hash_file(p)
    if sha != seen:
        fail(f'{label}_SHA_DRIFT expected={sha} observed={seen}')


def check_fbin(p, n, d):
    regular(p)
    with p.open('rb') as f:
        hdr = f.read(8)
    if len(hdr) != 8 or struct.unpack('<II', hdr) != (n, d) or p.stat().st_size != 8 + n*d*4:
        fail(f'BAD_FBIN_SHAPE_OR_SIZE {p}')


def check_gt():
    regular(GT)
    with GT.open('rb') as f:
        h = f.read(8)
    if h != struct.pack('<II', 10_000, 100) or GT.stat().st_size != 8_000_008:
        fail('BAD_GT_FORMAT_OR_SIZE')
    verify_file(GT, PIN['gt'], 'GT')
    regular(GT_MAN)
    m = json.loads(GT_MAN.read_text())
    if (m.get('gt_sha256') != PIN['gt'] or m.get('base_sha256') != PIN['base'] or
        m.get('queries_sha256') != PIN['query'] or m.get('q') != 10_000 or m.get('k') != 100):
        fail('GT_MANIFEST_DRIFT')


def check_graph(name):
    p = PAIR / (name + '.graph')
    verify_file(p, PIN[name], name)
    with p.open('rb') as f:
        h = f.read(8)
        deg = f.read(400_000)
    if len(h) != 8 or struct.unpack('<II', h) != (100_000, 64) or len(deg) != 400_000:
        fail(f'GRAPH_HEADER_DRIFT {name}')
    # Degree sum independently certifies exact ParlayANN Graph<uint32> length.
    from array import array
    a = array('I'); a.frombytes(deg)
    if sys.byteorder != 'little' or a.itemsize != 4 or any(x > 64 for x in a):
        fail(f'GRAPH_BAD_DEGREES {name}')
    if p.stat().st_size != 8 + 400_000 + 4*sum(a):
        fail(f'GRAPH_LENGTH_DRIFT {name}')
    return p


def get_compile():
    regular(CDB); regular(LINK); regular(R72)
    entries = json.loads(CDB.read_text())
    matches = [e for e in entries if Path(e.get('file', '')).name == 'r72_graph_recall.cc']
    if len(matches) != 1:
        fail(f'R72_COMPILER_ENTRY_COUNT {len(matches)}')
    e = matches[0]
    cmd = list(e['arguments']) if 'arguments' in e else shlex.split(e['command'])
    if cmd.count('-o') != 1 or cmd.count('-c') != 1:
        fail('COMPILER_COMMAND_UNEXPECTED_FLAGS')
    orig_src = [i for i, a in enumerate(cmd) if a.endswith('/r72_graph_recall.cc') or a == 'r72_graph_recall.cc']
    if len(orig_src) != 1:
        fail('COMPILER_ORIGINAL_SOURCE_ANCHOR_MISSING')
    cmd[orig_src[0]] = str(CPP)
    cmd[cmd.index('-o')+1] = str(OBJ)
    cwd = Path(e['directory'])
    if not cwd.is_dir() or cwd.resolve() != BUILD.resolve():
        # Some CMake versions set a sub-build directory; allow only below pinned BUILD.
        if not cwd.resolve().is_relative_to(BUILD.resolve()):
            fail('COMPILER_CWD_NOT_UNDER_PINNED_BUILD')
    link = shlex.split(LINK.read_text().strip())
    object_idx = [i for i, a in enumerate(link) if a.endswith('/r72_graph_recall.cc.o') or a == 'r72_graph_recall.cc.o']
    if len(object_idx) != 1 or link.count('-o') != 1:
        fail('LINKER_COMMAND_OBJECT_ANCHOR_MISSING')
    link[object_idx[0]] = str(OBJ)
    link[link.index('-o')+1] = str(BIN)
    return cmd, cwd, link


def patched_source():
    regular(A1C)
    original = A1C.read_text()
    if original.count('R85_A1C_DYNAMIC_BEAMS count=') != 1 or 'R72_RECALL_EVAL_PASS' not in original:
        fail('A1C_SOURCE_NOT_DYNAMIC_OR_NOT_NATIVE')
    if original.count('checkRecall<') != 1:
        fail('A1C_NATIVE_SEARCH_ANCHOR_UNEXPECTED')
    pat = r'base\.size\(\)\s*!=\s*1000000'
    if len(re.findall(pat, original)) != 1:
        fail('A1C_HARDCODED_1M_ANCHOR_NOT_UNIQUE')
    changed = re.sub(pat, 'base.size() != 100000', original, count=1)
    if changed == original:
        fail('NO_PATCH_APPLIED')
    # Preserve A1c source exactly except one number. For relative utility includes,
    # resolve to the existing pinned H70 utility, not H85 B1 location.
    for inc in re.findall(r'^\s*#include\s+"([^"]+)"', changed, re.M):
        if inc.startswith('.'):
            orig = (A1C.parent / inc).resolve()
            r72 = (R72.parent / inc).resolve()
            if orig.is_file():
                target = orig
            elif r72.is_file():
                target = r72
            else:
                fail('CANNOT_RESOLVE_RELATIVE_INCLUDE '+inc)
            changed = changed.replace('"'+inc+'"', '"'+str(target)+'"')
        elif inc.startswith('/') and not Path(inc).is_file():
            fail('MISSING_ABSOLUTE_INCLUDE '+inc)
    if 'base.size() != 1000000' in changed or 'base.size() != 100000' not in changed:
        fail('PATCH_CHECK_FAILED')
    return changed, hash_file(A1C)


def preflight():
    if OUT.is_symlink() or not B1.is_dir():
        fail('UNSAFE_OUTPUT_DIR')
    for name in ('P1', 'P2'):
        p = check_graph(name)
        print(f'R85_B1_STEP8E_GRAPH_SHA_PASS {name} {PIN[name]} bytes={p.stat().st_size}', flush=True)
    check_fbin(DATA, 100_000, 128)
    check_fbin(QUERY, 10_000, 128)
    verify_file(DATA, PIN['base'], 'DATA')
    verify_file(QUERY, PIN['query'], 'QUERY')
    check_gt()
    verify_file(R72_BIN, PIN_R72_EVAL, 'H70_R72_BINARY')
    text, asha = patched_source()
    compiler, cwd, linker = get_compile()
    if not shutil.which('taskset') or 0 not in os.sched_getaffinity(0):
        fail('TASKSET_CPU0_UNAVAILABLE')
    if shutil.disk_usage(B1).free < 2*1024**3:
        fail('DISK_FREE_LT_2G')
    print('R85_B1_STEP8E_R72_ORIGINAL_EVAL_SHA_PASS '+PIN_R72_EVAL, flush=True)
    print('R85_B1_STEP8E_SOURCE_BASE A1C_DYNAMIC '+asha, flush=True)
    print('R85_B1_STEP8E_PATCH_DIFF only base.size() != 1000000 to 100000 (plus absolute include path resolution)', flush=True)
    print('R85_B1_STEP8E_COMPILER_CWD '+str(cwd), flush=True)
    print('R85_B1_STEP8E_GT_SHA_PASS '+PIN['gt'], flush=True)
    print('R85_B1_STEP8E_PREFLIGHT_PASS_READ_ONLY', flush=True)
    return text, asha, compiler, cwd, linker


def write_exclusive(p, text):
    with p.open('x') as f: f.write(text)


def stage(text):
    if OUT.exists() and not OUT.is_dir(): fail('OUTPUT_IS_NOT_DIRECTORY')
    OUT.mkdir(parents=True, exist_ok=True)
    if OUT.is_symlink(): fail('OUTPUT_IS_SYMLINK')
    if CPP.exists():
        regular(CPP)
        if CPP.read_text() != text: fail('STAGED_SOURCE_DRIFT')
    else:
        write_exclusive(CPP, text)
    return hash_file(CPP)


def build():
    text, asha, compiler, cwd, linker = preflight()
    code_sha = stage(text)
    if BIN.exists() or MANIFEST.exists():
        if not BIN.exists() or not MANIFEST.exists(): fail('PARTIAL_OUTPUT_ALREADY_EXISTS')
        m = json.loads(MANIFEST.read_text())
        if m.get('source_sha256') != code_sha or m.get('binary_sha256') != hash_file(BIN):
            fail('EXISTING_BUILD_DRIFT')
        print('R85_B1_STEP8E_EVALUATOR_EXISTING_VERIFIED '+str(BIN), flush=True)
        return
    if OBJ.exists():
        # On interrupted compilation, do not silently reuse stale object.
        fail('OBJECT_ALREADY_EXISTS_WITHOUT_COMPLETE_MANIFEST')
    for label, cmd, workdir in [('COMPILE', compiler, cwd), ('LINK', linker, BUILD)]:
        print('R85_B1_STEP8E_'+label+'_COMMAND '+shlex.join(cmd), flush=True)
        log = OUT / ('native_'+label.lower()+'.log')
        if log.exists(): fail('NATIVE_LOG_ALREADY_EXISTS '+str(log))
        with log.open('x') as f:
            pr = subprocess.run(cmd, cwd=workdir, stdout=f, stderr=subprocess.STDOUT)
        if pr.returncode != 0:
            tail='\n'.join(log.read_text(errors='replace').splitlines()[-24:])
            fail(f'{label}_FAILED rc={pr.returncode} log={log}\n'+tail)
    regular(BIN)
    bsha=hash_file(BIN)
    m={'role':'SIFT100K native A1c/R72 evaluator; only base size validation changed',
       'a1c_source':str(A1C),'a1c_source_sha256':asha,
       'r72_original':str(R72),'r72_sha256':hash_file(R72),
       'source':str(CPP),'source_sha256':code_sha,'binary':str(BIN),'binary_sha256':bsha,
       'dataset_sha256':PIN['base'],'query_sha256':PIN['query'],'gt_sha256':PIN['gt'],
       'graphs_sha256':{'P1':PIN['P1'],'P2':PIN['P2']},
       'created_utc':datetime.now(timezone.utc).isoformat()}
    write_exclusive(MANIFEST, json.dumps(m,indent=2,sort_keys=True)+'\n')
    print('R85_B1_STEP8E_EVAL_BINARY_SHA256 '+bsha, flush=True)
    print('R85_B1_STEP8E_NATIVE_EVALUATOR_COMPILE_PASS_NO_GRAPH_BUILD', flush=True)


def verify_binary():
    text, asha, compiler, cwd, linker = preflight()
    regular(CPP); regular(BIN); regular(MANIFEST)
    if CPP.read_text()!=text: fail('COMPILED_SOURCE_DRIFT')
    m=json.loads(MANIFEST.read_text())
    if (m.get('a1c_source_sha256')!=asha or
        m.get('source_sha256')!=hash_file(CPP) or
        m.get('binary_sha256')!=hash_file(BIN)):
        fail('NATIVE_BINARY_MANIFEST_DRIFT')


def parse(text, beams, name):
    if f'R85_A1C_DYNAMIC_BEAMS count={len(beams)}' not in text:
        fail('DYNAMIC_BEAM_MARKER_MISSING '+name)
    if 'R72_RECALL_INPUT_PASS graph_nodes=100000' not in text:
        fail('100K_INPUT_ACCEPTANCE_MISSING '+name)
    if 'R72_RECALL_EVAL_PASS' not in text:
        fail('NATIVE_RECALL_PASS_MARKER_MISSING '+name)
    rows=[]
    for m in ROW.finditer(text):
        beam=int(m.group(1)); vals=list(map(float,m.groups()[1:]))
        if not 0<=vals[0]<=1 or any(not 0<=v<float('inf') for v in vals):
            fail('NONFINITE_OR_INVALID_SEARCH_RESULT '+name)
        rows.append({'beam':beam,'recall':vals[0],'qps':vals[1],
                     'avg_cmps':vals[2],'avg_visited':vals[3]})
    if [x['beam'] for x in rows]!=list(beams):
        fail(f'BEAM_ROW_ORDER_OR_COUNT_MISMATCH {name} got={[x["beam"] for x in rows]}')
    return rows


def search(mode):
    verify_binary()
    beams = SMOKE if mode=='smoke' else DENSE
    outdir=OUT/mode
    if outdir.is_symlink(): fail('SEARCH_OUTPUT_SYMLINK')
    if outdir.exists(): fail('SEARCH_OUTPUT_ALREADY_EXISTS '+str(outdir))
    outdir.mkdir(parents=True,exist_ok=False)
    env=dict(os.environ,PARLAY_NUM_THREADS='1',OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',
             MKL_NUM_THREADS='1',VECLIB_MAXIMUM_THREADS='1',NUMEXPR_NUM_THREADS='1')
    saved={}
    for name in ('P1','P2'):
        cmd=['taskset','-c','0',str(BIN),str(PAIR/(name+'.graph')),
             str(DATA),str(QUERY),str(GT),','.join(map(str,beams))]
        print('R85_B1_STEP8E_'+mode.upper()+'_START '+name+' count='+str(len(beams)),flush=True)
        log=outdir/(name+'.log')
        with log.open('x') as f:
            pr=subprocess.run(cmd,env=env,cwd=OUT,stdout=f,stderr=subprocess.STDOUT)
        output=log.read_text(errors='replace')
        if pr.returncode!=0:
            fail(f'NATIVE_SEARCH_FAILED {name} code={pr.returncode} log={log}\n'+ '\n'.join(output.splitlines()[-15:]))
        rows=parse(output,beams,name)
        saved[name]=rows
        write_exclusive(outdir/(name+'.json'),json.dumps({'graph':name,'graph_sha256':PIN[name],
            'evaluator_sha256':hash_file(BIN),'base_sha256':PIN['base'],
            'query_sha256':PIN['query'],'gt_sha256':PIN['gt'],
            'beams':list(beams),'rows':rows},indent=2)+'\n')
        for row in rows if mode=='smoke' else rows[::max(1,len(rows)//8)]:
            print('R85_B1_STEP8E_SEARCH_ROW '+name+' '+json.dumps(row,sort_keys=True),flush=True)
        print('R85_B1_STEP8E_'+mode.upper()+'_PASS '+name,flush=True)
    print('R85_B1_STEP8E_'+mode.upper()+'_PAIR_PASS_RECALL_ONLY_LATENCY_PENDING',flush=True)


def selftest():
    toy='if (base.size() != 1000000 || base.dimension() != 128) {}'
    assert len(re.findall(r'base\.size\(\)\s*!=\s*1000000',toy))==1
    changed=re.sub(r'base\.size\(\)\s*!=\s*1000000','base.size() != 100000',toy)
    assert 'base.size() != 1000000' not in changed and 'base.size() != 100000' in changed
    assert len(DENSE)==len(set(DENSE)) and min(DENSE)==10 and max(DENSE)==256
    toylog='R85_A1C_DYNAMIC_BEAMS count=1\nR72_RECALL_INPUT_PASS graph_nodes=100000 queries=10000 gt_k=100\nR72_RECALL_ROW beam=10 recall=0.8 qps=5000 avg_cmps=700 avg_visited=50\nR72_RECALL_EVAL_PASS'
    assert len(parse(toylog,(10,),'toy'))==1
    print('R85_B1_STEP8E_NATIVE_SELFTEST_PASS_NO_PROJECT_IO',flush=True)


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    g=ap.add_mutually_exclusive_group(required=True)
    for mode in ('selftest','preflight','compile','smoke','quality'):
        g.add_argument('--'+mode,action='store_true')
    a=ap.parse_args()
    if a.selftest: selftest()
    elif a.preflight: preflight()
    elif a.compile: build()
    elif a.smoke: search('smoke')
    elif a.quality: search('quality')

if __name__=='__main__':
    try: main()
    except Exception as e:
        print('R85_B1_STEP8E_NATIVE_FAIL_CLOSED '+repr(e),file=sys.stderr,flush=True)
        sys.exit(2)
