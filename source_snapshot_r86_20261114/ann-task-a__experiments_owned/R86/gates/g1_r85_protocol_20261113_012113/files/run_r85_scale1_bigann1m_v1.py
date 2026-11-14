#!/usr/bin/env python3
"""R85-SCALE1: independent BIGANN1M 6-arm BUILD + native QUALITY pilot.

Reuses the pinned A4 build command generator and A1c native evaluator WITHOUT
modifying historical source, binary or SIFT1M artifacts. Fail-closed.

Phases:
 --selftest                       synthetic; no project access
 --preflight                      read-only, hashes full inputs
 --dry-run                        read-only; show 18 exact BUILD commands
 --run-build --reps 1             new session, first 6 BUILDS only
 --resume-build RUN --reps 3      grow pinned session to 18 BUILDS
 --run-quality RUN                25-beam native SEARCH on finished BUILDS

No BIGANN2M build here. Does NOT claim matched-Recall latency.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import shlex
import shutil
import struct
import subprocess
import sys
import time
from statistics import median

HOME = Path.home()
ROOT = HOME / 'ann-task-a'
DL = HOME / 'Downloads'
OUT = ROOT / 'experiments/H85/r85_scale1_bigann1m'
A4_FILE = DL / 'run_r85_a4_paired_sift1m.py'
A4_SHA = 'b9db158b022d9df9633817031282d68e45f7c0ee9236d2b7059aa184d73e3106'
DATA = {
    'base': ROOT / 'data/bigann1m_prefix.fbin',
    'query': ROOT / 'experiments/H85/r85_scale0_public_eval/query.public.10K.fbin',
    'gt': ROOT / 'experiments/H85/r85_scale1_2_exact_gt/bigann1m_public10k_exact100.ibin',
}
BIGANN10M = ROOT / 'data/sift10m.fbin'
EVAL_SHA_EXPECTED = '3c2294efa1d7fb5d89c79ca5bf9c1eaca86247f7246e6d6d7c6c94549d08ed57'
GT_SHA_EXPECTED = 'f8287eaedb4fb7d77ddbcddcc144ebb284d2a241bf71c1b9a3fdf1238d44b7ac'
QUERY_SHA_EXPECTED = 'a2cb2d182b19db70240ebd4bce3b75b8994ea9927a112d4bf0e955815bdac548'
TIME_RE = re.compile(r'^R85_SCALE1_TIME wall_s=([0-9.]+) peak_rss_kib=(\d+)$', re.M)
CPUS = (0, 2, 4, 6)
BEAM_REPS = 1
MIN_DISK_GIB = 15.0


def fail(s):
    raise RuntimeError('R85_SCALE1_FAIL_CLOSED ' + str(s))


def sha(p):
    h = hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda: f.read(4 << 20), b''):
            h.update(b)
    return h.hexdigest()


def jwrite_exclusive(path, data):
    with Path(path).open('x', encoding='utf8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False, allow_nan=False)
        f.write('\n')


def jload(p):
    return json.loads(Path(p).read_text(encoding='utf8'))


def module_from_file(p, digest):
    p=Path(p)
    if not p.is_file() or sha(p) != digest:
        fail('A4_RUNNER_SHA_OR_FILE_MISMATCH '+str(p))
    sys.dont_write_bytecode = True  # no __pycache__ writes during audit/import
    spec=importlib.util.spec_from_file_location('r85scale1_a4',p)
    if spec is None or spec.loader is None:
        fail('A4_IMPORT_SPEC_MISSING')
    mod=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def header(path):
    with path.open('rb') as f:
        b=f.read(8)
    if len(b)!=8:
        fail('SHORT_FILE_HEADER '+str(path))
    return struct.unpack('<II',b)


def require_regular(p):
    p=Path(p)
    if p.is_symlink() or not p.is_file():
        fail('EXPECTED_REGULAR_FILE '+str(p))
    return p


def check_dataset():
    # Includes exact byte comparison of 1M *data* to BIGANN10M prefix, not
    # just a sample or filename. fbin headers necessarily differ by n.
    base=require_regular(DATA['base']); query=require_regular(DATA['query'])
    gt=require_regular(DATA['gt']); big=require_regular(BIGANN10M)
    expected={
        'base':((1_000_000,128),8+1_000_000*128*4),
        'query':((10_000,128),8+10_000*128*4),
        'gt':((10_000,100),8+10_000*100*8),
    }
    for k,(h,nbytes) in expected.items():
        p=DATA[k]
        if header(p)!=h or p.stat().st_size!=nbytes:
            fail('DATA_HEADER_SIZE_MISMATCH '+k+' '+str(header(p)))
    if header(big)!=(10_000_000,128) or big.stat().st_size!=8+10_000_000*128*4:
        fail('BIGANN10M_HEADER_SIZE_MISMATCH')
    with base.open('rb') as f, big.open('rb') as g:
        f.seek(8);g.seek(8)
        left=1_000_000*128*4
        while left:
            n=min(left,4<<20)
            if f.read(n)!=g.read(n):
                fail('BIGANN1M_NOT_EXACT_PREFIX_OF_BIGANN10M')
            left-=n
    hashes={k:sha(p) for k,p in DATA.items()}
    if hashes['query']!=QUERY_SHA_EXPECTED or hashes['gt']!=GT_SHA_EXPECTED:
        fail('QUERY_OR_GT_SHA_PIN_MISMATCH')
    print('R85_SCALE1_DATA_INPUTS_PASS '+json.dumps(hashes,sort_keys=True),flush=True)
    return hashes


def check_resources():
    if shutil.which('taskset') is None or not Path('/usr/bin/time').is_file():
        fail('NEED_TASKSET_AND_USR_BIN_TIME')
    avail=set(os.sched_getaffinity(0))
    if not set(CPUS).issubset(avail):
        fail('CPU_AFFINITY_MISMATCH '+str(sorted(avail)))
    st=os.statvfs(ROOT)
    free=st.f_bavail*st.f_frsize/(1024**3)
    if free < MIN_DISK_GIB:
        fail('DISK_BELOW_SAFETY_RESERVE freeGiB='+str(round(free,2)))
    # Refuse to start a native graph BUILD when current available RAM is low.
    info={}
    with Path('/proc/meminfo').open('r',encoding='utf8') as f:
        for line in f:
            name, _, value=line.partition(':')
            if name in ('MemAvailable','SwapFree'):
                info[name]=int(value.strip().split()[0])
    avail_gib=info.get('MemAvailable',0)/(1024**2)
    if avail_gib < 8:
        fail('MEMAVAILABLE_BELOW_8_GIB currently='+str(round(avail_gib,2)))
    print(f'R85_SCALE1_RESOURCES_PASS cpus={list(CPUS)} freeGiB={free:.2f} memAvailableGiB={avail_gib:.2f} swapFreeKiB={info.get("SwapFree",-1)}',flush=True)
    return free


def load_context():
    a4=module_from_file(A4_FILE,A4_SHA)
    if len(a4.ARMS)!=6 or a4.REPS!=3 or tuple(a4.BUILD_CPUS)!=CPUS:
        fail('A4_PROTOCOL_DRIFT')
    old,a1,a1c,base,b,evaluator = a4.dep()
    if not a1c.EVAL.is_file():
        fail('A1C_EVAL_MISSING')
    # A1C is 1M-only but BIGANN1M has the same shape as SIFT1M.
    if getattr(old,'DATA_FILES',None) is None:
        fail('A4_OLD_DATA_FILES_MISSING')
    if len(a4.schedule())!=18 or len(a4.ARM_ORDER)!=6:
        fail('A4_SCHEDULE_DRIFT')
    return a4,old,a1,a1c


def replace_inputs(cmd,old,graph):
    """Only substitute EXACT pinned data-file tokens from A4's command.

    Never text-edit A4 script/binaries. Fail if base is not present exactly once,
    if old SIFT data remain, or if graph destination did not propagate.
    """
    src={key:str(old.DATA_FILES[key][0]) for key in DATA}
    dst={key:str(p) for key,p in DATA.items()}
    counts={key:0 for key in DATA}; result=[]
    for item in cmd:
        s=str(item)
        for key in DATA:
            if s==src[key]:
                s=dst[key];counts[key]+=1
            elif s.endswith('='+src[key]) and s.startswith('-'):
                s=s[:-len(src[key])]+dst[key];counts[key]+=1
        result.append(s)
    if counts['base']!=1 or any(v>1 for v in counts.values()):
        fail('BUILD_COMMAND_DATA_REPLACEMENT_COUNTS '+str(counts))
    for key,path in src.items():
        if any(path in s for s in result):
            fail('ORIGINAL_SIFT_DATA_REMAIN_IN_COMMAND '+key)
    if sum(str(graph) in s for s in result)!=1:
        fail('BUILD_OUTPUT_GRAPH_PATH_MISMATCH '+str(graph))
    if not result or not Path(result[0]).is_file():
        fail('BUILD_BINARY_MISSING '+(result[0] if result else 'EMPTY'))
    return result,counts


def command_for(a4,old,a1,arm,graph):
    native=a4.cmd_build(old,a1,arm,graph)
    if not isinstance(native,(list,tuple)):
        fail('UNEXPECTED_A4_COMMAND_TYPE')
    return replace_inputs(native,old,graph)


def identity(a4,old,a1,a1c,hashes):
    names={}
    for arm in a4.ARM_ORDER:
        cmd,_=command_for(a4,old,a1,arm,Path('/R85_SCALE1_DRY_RUN_GRAPH.graph'))
        names[arm]={"cmd":cmd,"binary_sha256":sha(cmd[0]),"variant":list(a4.ARMS[arm])}
    eval_path=Path(a1c.EVAL)
    return {
        'protocol':'R85_SCALE1_BIGANN1M_NATIVE_SIX_ARM_V1',
        'a4_runner_sha256':A4_SHA,
        'a4_old_sha256':a4.OLD_SHA,
        'a4_a1_sha256':a4.A1_SHA,
        'a4_a1c_sha256':a4.A1C_SHA,
        'input_sha256':hashes,
        'binary_and_flags':names,
        'evaluator_path':str(eval_path),
        'evaluator_sha256':sha(eval_path),
        'build_cpus':list(CPUS),
        'quality_cpus':list(CPUS),
        'quality_beams':list(a1c.BEAMS),
        'schedule':[[r,arm] for r,arm in a4.schedule()],
        'arms':list(a4.ARM_ORDER),
        'note':'Independent BIGANN1M; never combine with historical SIFT1M A4 graph metrics',
    }


def preflight(do_commands=False):
    check_resources()
    hashes=check_dataset()
    a4,old,a1,a1c=load_context()
    ident=identity(a4,old,a1,a1c,hashes)
    if do_commands:
        for i,(r,arm) in enumerate(a4.schedule(),1):
            tag=f't4_r{r}_{arm}'
            cmd,counts=command_for(a4,old,a1,arm,Path('/NEW_SESSION/'+tag+'.graph'))
            print(f'R85_SCALE1_DRY_RUN {i}/18 '+shlex.join(['taskset','-c',','.join(map(str,CPUS)),'/usr/bin/time','-f','R85_SCALE1_TIME wall_s=%e peak_rss_kib=%M']+cmd),flush=True)
            print(f'R85_SCALE1_INPUT_SUBSTITUTIONS {tag} '+json.dumps(counts),flush=True)
    print('R85_SCALE1_PREFLIGHT_PASS_READ_ONLY six_arms=6 graph_builds_planned=18',flush=True)
    return a4,old,a1,a1c,ident


def graph_audit(path):
    import numpy as np
    p=require_regular(path)
    with p.open('rb') as f:
        n,bound=struct.unpack('<II',f.read(8))
    if n!=1_000_000 or bound!=64:
        fail('GRAPH_HEADER_MISMATCH '+str((n,bound)))
    sizes=np.memmap(p,dtype='<u4',mode='r',offset=8,shape=(n,))
    if int(sizes.max())>bound:
        fail('GRAPH_DEGREE_BOUND_EXCEEDED')
    arcs=int(np.sum(sizes,dtype=np.uint64))
    expected=8+4*n+4*arcs
    if p.stat().st_size!=expected:
        fail('GRAPH_ARC_BYTES_MISMATCH '+str((p.stat().st_size,expected)))
    edges=np.memmap(p,dtype='<u4',mode='r',offset=8+4*n,shape=(arcs,))
    # Bound checks vectorized; per-row self-loop, duplicate neighbor checks.
    if arcs and int(edges.max())>=n:
        fail('GRAPH_NEIGHBOR_OUT_OF_RANGE')
    start=0
    for i in range(n):
        deg=int(sizes[i]);stop=start+deg
        row=edges[start:stop]
        if deg and (bool(np.any(row==i)) or len(set(map(int,row)))!=deg):
            fail('GRAPH_SELFLOOP_OR_DUPLICATE node='+str(i))
        start=stop
    if start!=arcs:
        fail('GRAPH_SCAN_COUNT_MISMATCH')
    return {'n':n,'max_degree_bound':bound,'arcs':arcs,'graph_sha256':sha(p),'bytes':p.stat().st_size}


def completed_records(run):
    p=run/'build_results.json'
    return jload(p) if p.exists() else []


def verify_session(run,ident,a4,old,a1):
    run=Path(run).resolve()
    if not run.is_dir() or not run.is_relative_to(OUT.resolve()):
        fail('RUN_NOT_UNDER_SCALE1_OUTPUT '+str(run))
    manifest=require_regular(run/'manifest.json')
    existing=jload(manifest)
    if existing.get('identity')!=ident:
        fail('RUN_MANIFEST_IDENTITY_DRIFT')
    rows=completed_records(run)
    schedule=a4.schedule()
    if len(rows)>len(schedule):fail('TOO_MANY_BUILD_ROWS')
    for i,row in enumerate(rows):
        rep,arm=schedule[i]
        tag=f't4_r{rep}_{arm}'
        if row.get('tag')!=tag or row.get('rep')!=rep or row.get('arm')!=arm:
            fail('BUILD_ROW_SCHEDULE_DRIFT '+str(i))
        graph=run/(tag+'.graph')
        if not graph.is_file() or graph.is_symlink() or sha(graph)!=row.get('graph_sha256'):
            fail('BUILD_GRAPH_SHA_DRIFT '+tag)
        if graph.stat().st_size!=row.get('graph_bytes'):
            fail('BUILD_GRAPH_BYTES_DRIFT '+tag)
    return rows


def new_session(ident):
    OUT.mkdir(parents=True,exist_ok=True)
    stamp=dt.datetime.now().strftime('%Y%m%d-%H%M%S')
    run=OUT/f'bigann1m_{stamp}_{os.getpid()}'
    run.mkdir(exist_ok=False)
    jwrite_exclusive(run/'manifest.json',{'identity':ident,'created_at_local':dt.datetime.now().isoformat(timespec='seconds'),'requested_initial_reps':'pilot then optional extension'})
    print('R85_SCALE1_BUILD_SESSION '+str(run),flush=True)
    return run


def run_build(run,reps,a4,old,a1,ident):
    if reps not in (1,3):fail('REPS_ONLY_1_OR_3')
    run=Path(run).resolve()
    rows=verify_session(run,ident,a4,old,a1)
    all_schedule=a4.schedule()
    todo=[(r,a) for r,a in all_schedule if r<=reps]
    if len(rows)>len(todo):
        fail('SESSION_ALREADY_BEYOND_REQUESTED_REPS')
    if [(r['rep'],r['arm']) for r in rows]!=todo[:len(rows)]:
        fail('RESUME_NONPREFIX_ROWS')
    for ix,(rep,arm) in enumerate(todo[len(rows):],len(rows)+1):
        check_resources()
        tag=f't4_r{rep}_{arm}'
        tmp=run/(tag+'.graph.tmp')
        graph=run/(tag+'.graph')
        log=run/(tag+'.build.log')
        timefile=run/(tag+'.time')
        for path in (tmp,graph,log,timefile):
            if path.exists() or path.is_symlink():
                fail('UNRECORDED_ARTIFACT_NO_OVERWRITE '+str(path))
        cmd,_=command_for(a4,old,a1,arm,tmp)
        command=['taskset','-c',','.join(map(str,CPUS)),
                 '/usr/bin/time','-f','R85_SCALE1_TIME wall_s=%e peak_rss_kib=%M',
                 '-o',str(timefile)]+cmd
        env=dict(os.environ,PARLAY_NUM_THREADS='4',OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='1',VECLIB_MAXIMUM_THREADS='1')
        print(f'R85_SCALE1_BUILD_START {ix}/{len(todo)} tag={tag}',flush=True)
        # No shell; only cloned native command; file output is confined to run.
        with log.open('x',encoding='utf8') as f:
            f.write('COMMAND '+shlex.join(command)+'\n')
            f.flush()
            proc=subprocess.run(command,cwd=str(ROOT),env=env,stdout=f,stderr=subprocess.STDOUT,check=False)
        if proc.returncode:
            fail('BUILD_FAILED tag='+tag+' rc='+str(proc.returncode)+' log='+str(log))
        if not timefile.is_file():
            fail('MISSING_TIMEFILE '+tag)
        match=TIME_RE.search(timefile.read_text(errors='replace'))
        if not match:
            fail('TIME_METRICS_MISSING '+tag)
        stat=graph_audit(tmp)
        tmp.rename(graph)  # same directory; graph never overwritten
        row={'tag':tag,'rep':rep,'arm':arm,'wall_s':float(match[1]),'peak_rss_kib':int(match[2]),
             'graph_sha256':stat['graph_sha256'],'arcs':stat['arcs'],'graph_bytes':stat['bytes'],
             'graph_path':str(graph)}
        rows.append(row)
        jwrite_exclusive(run/(tag+'.record.json'),row)
        # build_results is append-only via exclusive numbered snap and replace
        # pointer: if interrupted before the update, recover from row records.
        f=run/'build_results.json';scratch=run/'build_results.json.tmp'
        if scratch.exists():fail('BUILD_RESULT_TMP_EXISTS')
        scratch.write_text(json.dumps(rows,indent=2,allow_nan=False)+'\n',encoding='utf8')
        os.replace(scratch,f)
        print(f'R85_SCALE1_BUILD_PASS {tag} wall_s={row["wall_s"]:.3f} peakRSS_KiB={row["peak_rss_kib"]} arcs={row["arcs"]} sha256={row["graph_sha256"]}',flush=True)
    summary={}
    for arm in a4.ARM_ORDER:
        armrows=[r for r in rows if r['arm']==arm]
        summary[arm]={'graphs':len(armrows),'median_wall_s':median(r['wall_s'] for r in armrows) if armrows else None,
                      'median_peak_rss_kib':median(r['peak_rss_kib'] for r in armrows) if armrows else None}
    print('R85_SCALE1_BUILD_SUMMARY '+json.dumps(summary,sort_keys=True),flush=True)
    print(f'R85_SCALE1_BUILD_{len(rows)}_GRAPHS_PASS_NO_SOURCE_CHANGES '+str(run),flush=True)


def run_quality(run,a4,old,a1,a1c,ident):
    rows=verify_session(run,ident,a4,old,a1)
    if not rows or len(rows)%6:
        fail('QUALITY_REQUIRES_COMPLETE_6_ARM_REPS')
    run=Path(run)
    qdir=run/'quality'
    qdir.mkdir(exist_ok=True)
    beams=list(a1c.BEAMS)
    for idx,r in enumerate(rows,1):
        tag=r['tag']
        jf=qdir/(tag+'.json'); lf=qdir/(tag+'.log')
        if jf.is_file():
            record=jload(jf)
            if record.get('graph_sha256')!=r['graph_sha256'] or record.get('data_sha256')!=ident['input_sha256'] or record.get('evaluator_sha256')!=ident['evaluator_sha256'] or [z['beam'] for z in record.get('rows',[])]!=beams:
                fail('EXISTING_QUALITY_DRIFT '+tag)
            print('R85_SCALE1_QUALITY_SKIP_VERIFIED '+tag,flush=True)
            continue
        if jf.exists() or lf.exists():
            fail('UNRECORDED_QUALITY_FILES '+tag)
        cmd=['taskset','-c',','.join(map(str,CPUS)),str(a1c.EVAL),r['graph_path'],
             str(DATA['base']),str(DATA['query']),str(DATA['gt']),','.join(map(str,beams))]
        env=dict(os.environ,PARLAY_NUM_THREADS='4',OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1')
        print(f'R85_SCALE1_QUALITY_START {idx}/{len(rows)} {tag} beams={len(beams)}',flush=True)
        with lf.open('x',encoding='utf8') as f:
            f.write('COMMAND '+shlex.join(cmd)+'\n');f.flush()
            res=subprocess.run(cmd,cwd=str(ROOT),env=env,stdout=f,stderr=subprocess.STDOUT)
        output=lf.read_text(errors='replace')
        if res.returncode or 'R72_RECALL_EVAL_PASS' not in output or f'R85_A1C_DYNAMIC_BEAMS count={len(beams)}' not in output:
            fail('QUALITY_NATIVE_FAILED tag='+tag+' rc='+str(res.returncode)+' log='+str(lf))
        parsed=a4.parsed(output,beams)
        if len(parsed)!=len(beams):fail('QUALITY_BEAM_COUNT_MISMATCH '+tag)
        record={'tag':tag,'graph_sha256':r['graph_sha256'],'evaluator_sha256':ident['evaluator_sha256'],
                'data_sha256':ident['input_sha256'],'rows':parsed}
        jwrite_exclusive(jf,record)
        print('R85_SCALE1_QUALITY_PASS '+tag,flush=True)
    print(f'R85_SCALE1_QUALITY_{len(rows)}_GRAPHS_PASS_MATCHED_LATENCY_PENDING '+str(run),flush=True)


def selftest():
    import tempfile
    # Exact substitution; no project access or repository import.
    class Old:
        DATA_FILES={'base':(Path('/old/sift1m.fbin'),),
                    'query':(Path('/old/query.fbin'),),
                    'gt':(Path('/old/gt.ibin'),)}
    with tempfile.TemporaryDirectory() as d:
        binary=Path(d)/'bin';binary.write_text('synthetic')
        graph=Path(d)/'graph.tmp'
        cmd=[str(binary),'-base_path','/old/sift1m.fbin','-query_path','/old/query.fbin',
             '-gt_path','/old/gt.ibin','-graph_outfile',str(graph)]
        replaced,counts=replace_inputs(cmd,Old(),graph)
        assert counts=={'base':1,'query':1,'gt':1}
        assert replaced[2]==str(DATA['base']) and replaced[4]==str(DATA['query']) and replaced[6]==str(DATA['gt'])
        try:
            replace_inputs([str(binary),'-base_path','/other/sift1m.fbin','-graph_outfile',str(graph)],Old(),graph)
        except RuntimeError:
            pass
        else:
            assert False,'missing base must be rejected'
        # 5-node graph with two arcs; native graph header and degree-array layout.
        from array import array
        small=Path(d)/'sample.graph'
        with small.open('wb') as f:
            f.write(struct.pack('<II',5,64));f.write(struct.pack('<5I',1,0,1,0,0));f.write(struct.pack('<2I',2,3))
        assert small.stat().st_size==8+5*4+2*4
    print('R85_SCALE1_SELFTEST_PASS_NO_PROJECT_IO',flush=True)


def main():
    p=argparse.ArgumentParser(description=__doc__,formatter_class=argparse.RawDescriptionHelpFormatter)
    z=p.add_mutually_exclusive_group(required=True)
    z.add_argument('--selftest',action='store_true')
    z.add_argument('--preflight',action='store_true')
    z.add_argument('--dry-run',action='store_true')
    z.add_argument('--run-build',action='store_true')
    z.add_argument('--resume-build',type=Path,metavar='RUN')
    z.add_argument('--run-quality',type=Path,metavar='RUN')
    p.add_argument('--reps',type=int,default=1,choices=(1,3))
    args=p.parse_args()
    if args.selftest:
        selftest();return
    a4,old,a1,a1c,ident=preflight(do_commands=args.dry_run)
    if args.preflight or args.dry_run:return
    if args.run_build:
        run=new_session(ident)
        run_build(run,args.reps,a4,old,a1,ident)
    elif args.resume_build:
        run_build(args.resume_build,args.reps,a4,old,a1,ident)
    elif args.run_quality:
        run_quality(args.run_quality,a4,old,a1,a1c,ident)


if __name__=='__main__':
    try:
        main()
    except Exception as e:
        print('R85_SCALE1_FAIL_CLOSED '+repr(e),file=sys.stderr,flush=True)
        sys.exit(2)
