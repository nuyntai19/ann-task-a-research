#!/usr/bin/env python3
"""R86 G1: exact BIGANN1M OFF-equivalence builds against pinned R85 SCALE1.

--preflight and --dry-run are read-only. --run-build creates a NEW R86-only
session, builds two graphs sequentially, audits graphs and historic partition
counters. --run-quality uses the pinned R85 native evaluator on those graphs.

Never modifies H70/H85. Does NOT make matched-Recall latency claims.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import mmap
import os
from pathlib import Path
import re
import shlex
import shutil
import struct
import subprocess
import sys

HOME = Path.home()
ROOT = HOME / "ann-task-a"
R86_ROOT = ROOT / "experiments/R86"
OUTPUT_ROOT = R86_ROOT / "gates/g1_off_bigann1m"
R85_MANIFEST = ROOT / "experiments/H85/r85_scale1_bigann1m/bigann1m_20261112-022002_494222/manifest.json"
R85_RUNNER = HOME / "Downloads/run_r85_scale1_bigann1m_v1.py"
G0_MANIFEST = R86_ROOT / "gates/g0_20261113_011256/g0_manifest.json"
BUILD_ROOT = R86_ROOT / "r86_v1_2_builds"
BASE = ROOT / "data/bigann1m_prefix.fbin"
QUERY = ROOT / "experiments/H85/r85_scale0_public_eval/query.public.10K.fbin"
GT = ROOT / "experiments/H85/r85_scale1_2_exact_gt/bigann1m_public10k_exact100.ibin"
EVAL = ROOT / "experiments/H85/r85_a1c_matched_search/r85_a1c_graph_recall"

EXPECTED = {
 "r85_manifest": "95c011ee008b46df3588bb7980ceb9413a6ec79ed99d1bde4ef89651c890aa07",
 "r85_runner": "55a193b9d033491c646965d3ffd3d8e1a00eeef7c3b303b79a3b8f49f983e988",
 "g0_manifest": "4e5e671ed6bf9ab67273982d942154901c330e136ce6c5d6ec0dd589dced3ac9",
 "base": "69fb0e488b999c79c0d3919378bb03485fa421434bf9634d385b485a6431eb1e",
 "query": "a2cb2d182b19db70240ebd4bce3b75b8994ea9927a112d4bf0e955815bdac548",
 "gt": "f8287eaedb4fb7d77ddbcddcc144ebb284d2a241bf71c1b9a3fdf1238d44b7ac",
 "evaluator": "11587916ffd70143d6d5246bf8d2e26c1927b81bf8b3298fbc2014bfb6c64a4e",
 "stock_off": "ba8e621fdcbf1649f101b2a0f63d13791061847e14608907ecbe601c4269b681",
 "h17_off": "dd3829b1734b39fa175091fe0decdbb1cddf2f87795c9a0048df7a1e4e03eeb2",
}
PINS = Path(__file__).resolve().parent / "pins"
CPUS = (0, 2, 4, 6)
ARMS = {
 "stock_c160_k1024_n2": {
    "r85_arm": "STOCK", "r86_arm": "stock_off", "table": 160, "cluster": 1024,
    "buckets": [85028, 86507], "wp_cumulative": [4728316379, 9478487005],
    "occupancy_floor": 55, "selection": "STOCK_HIGHWAY", "reservoir": "STOCK_FLAT_C160",
 },
 "h17_c64_k512_n2": {
    "r85_arm": "C64_K512_N2", "r86_arm": "h17_off", "table": 64, "cluster": 512,
    "buckets": [133819, 134385], "wp_cumulative": [4774626648, 9569579308],
    "occupancy_floor": 56, "selection": "H17_PACKED_TOP2", "reservoir": "STOCK_FLAT_C64",
 },
}


def fail(message):
    raise RuntimeError("R86_G1_FAIL_CLOSED " + str(message))


def sha256(p):
    h = hashlib.sha256()
    with Path(p).open('rb') as f:
        for chunk in iter(lambda: f.read(4 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def regular(p):
    p = Path(p)
    if not p.is_file() or p.is_symlink():
        fail("FILE_MISSING_OR_SYMLINK " + str(p))
    return p


def check_sha(p, want, label):
    p = regular(p)
    got = sha256(p)
    if got != want:
        fail("SHA_MISMATCH " + label + " got=" + got + " wanted=" + want)
    return got


def read_json(p):
    return json.loads(regular(p).read_text(encoding='utf-8'))


def write_exclusive(p, value):
    p = Path(p)
    with p.open('x', encoding='utf-8') as f:
        json.dump(value, f, indent=2, ensure_ascii=False, allow_nan=False)
        f.write('\n')


def fbin_header(p, expected_pair, length):
    p = regular(p)
    if p.stat().st_size != length:
        fail("DATA_BYTES_MISMATCH " + str(p))
    with p.open('rb') as f:
        hdr = f.read(8)
    if len(hdr) != 8 or struct.unpack('<II',hdr) != expected_pair:
        fail("DATA_HEADER_MISMATCH " + str(p))


def check_resources():
    if not shutil.which('taskset') or not Path('/usr/bin/time').is_file():
        fail('REQUIRES_TASKSET_AND_GNU_TIME')
    if not set(CPUS).issubset(os.sched_getaffinity(0)):
        fail('CPU_AFFINITY_MISSING ' + str(CPUS))
    if not ROOT.is_dir():
        fail('REPO_NOT_FOUND')
    disk = shutil.disk_usage(ROOT)
    free_gib = disk.free/(1024**3)
    if free_gib < 15:
        fail(f'FREE_DISK_BELOW_15GiB actual={free_gib:.2f}')
    mem = {}
    for line in Path('/proc/meminfo').read_text().splitlines():
        if line.startswith(('MemAvailable:', 'SwapFree:')):
            name, tail = line.split(':',1)
            mem[name] = int(tail.strip().split()[0])
    mem_gib = mem.get('MemAvailable',0)/1024**2
    if mem_gib < 8:
        fail(f'MEMAVAILABLE_BELOW_8GiB actual={mem_gib:.2f}')
    print(f'G1_RESOURCE_PASS freeGiB={free_gib:.2f} availableRAMGiB={mem_gib:.2f} cpu={CPUS}',flush=True)


def cmake_cache(p):
    raw = regular(p).read_text(encoding='utf8', errors='replace')
    result = {}
    for line in raw.splitlines():
        if not line or line.startswith(('#','//')) or '=' not in line:
            continue
        key,_type_value = line.split(':',1) if ':' in line.split('=',1)[0] else (None,None)
        if key:
            result[key] = line.split('=',1)[1]
    return result


def validate_pins():
    check_sha(PINS/'r85_manifest.json',EXPECTED['r85_manifest'],'BUNDLED_R85_MANIFEST')
    check_sha(PINS/'r86_g0_manifest.json',EXPECTED['g0_manifest'],'BUNDLED_G0_MANIFEST')
    check_sha(R85_MANIFEST,EXPECTED['r85_manifest'],'ORIGINAL_R85_MANIFEST')
    check_sha(R85_RUNNER,EXPECTED['r85_runner'],'ORIGINAL_R85_RUNNER_READONLY')
    check_sha(G0_MANIFEST,EXPECTED['g0_manifest'],'ORIGINAL_G0_MANIFEST')
    r85=read_json(PINS/'r85_manifest.json')['identity']
    g0=read_json(PINS/'r86_g0_manifest.json')
    if g0.get('result')!='R86_G0_NATIVE_BINARY_AUDIT_PASS':fail('G0_RESULT_NOT_PASS')
    if r85.get('protocol')!='R85_SCALE1_BIGANN1M_NATIVE_SIX_ARM_V1':fail('WRONG_R85_PROTOCOL')
    if r85.get('build_cpus')!=list(CPUS) or r85.get('quality_cpus')!=list(CPUS):fail('R85_CPU_DRIFT')
    if len(r85.get('quality_beams',[]))!=25:fail('R85_QUALITY_BEAMS_NOT_25')
    if r85.get('evaluator_path')!=str(EVAL) or r85.get('evaluator_sha256')!=EXPECTED['evaluator']:
        fail('EVAL_PROTOCOL_MISMATCH')
    for k in ('base','query','gt'):
        if r85.get('input_sha256',{}).get(k)!=EXPECTED[k]:fail('R85_DATA_SHA_DRIFT_'+k)
    for k in ('stock_off','h17_off'):
        v=g0['variants'][k]
        if v['sha256']!=EXPECTED[k]:fail('G0_BINARY_PIN_MISMATCH_'+k)
        want_flags={'R70_USE_TIER':'OFF','R71_USE_H17':'ON' if k.startswith('h17') else 'OFF','R86_USE_COUNTERS':'OFF'}
        if v['expected_flags']!=want_flags:fail('G0_EXPECTED_FLAGS_DRIFT_'+k)
        if Path(v['binary']) != BUILD_ROOT/k/'algorithms/PipNN/neighbors-pipnn_FLOAT_T_EUCLIDEAN':
            fail('UNEXPECTED_BINARY_PATH_'+k)
        check_sha(v['binary'],EXPECTED[k],k)
        cache=cmake_cache(BUILD_ROOT/k/'CMakeCache.txt')
        for key,value in {**want_flags,'CMAKE_BUILD_TYPE':'Release','CMAKE_CXX_COMPILER':'/usr/bin/c++',
                          'CMAKE_CXX_FLAGS':'','CMAKE_CXX_FLAGS_RELEASE':'-O3 -DNDEBUG',
                          'CMAKE_HOME_DIRECTORY':str(R86_ROOT/'r86_v1_2_source')}.items():
            if cache.get(key)!=value:fail(f'CMAKE_DRIFT_{k}_{key} got={cache.get(key)}')
        print(f'G1_BINARY_PIN_PASS {k} {EXPECTED[k]}',flush=True)
    # Check ALL expected data lengths and full SHA (no silent source swap).
    fbin_header(BASE,(1_000_000,128),8+1_000_000*128*4)
    fbin_header(QUERY,(10_000,128),8+10_000*128*4)
    fbin_header(GT,(10_000,100),8+10_000*100*8)
    for p,k in [(BASE,'base'),(QUERY,'query'),(GT,'gt'),(EVAL,'evaluator')]:
        check_sha(p,EXPECTED[k],k)
        if p==EVAL and not os.access(p,os.X_OK):fail('EVALUATOR_NOT_EXECUTABLE')
        print(f'G1_INPUT_PIN_PASS {k} {EXPECTED[k]}',flush=True)
    check_resources()
    return r85,g0


def make_build_cmd(r85,arm,output):
    cfg=ARMS[arm]
    src = list(r85['binary_and_flags'][cfg['r85_arm']]['cmd'])
    b0 = r85['binary_and_flags'][cfg['r85_arm']]['binary_sha256']
    if b0!=('e07853b3e1832e2d9a95d6ed8ed6660bf34bc719dffcfd78789f6f672c6a05a5' if cfg['r85_arm']=='STOCK' else '8757b9be9fa3ae1f90febe082001fa60ba22c71ba6b6cdd899e013f6c0bcd500'):
        fail('R85_BINARY_SHA_DRIFT')
    if not src or src[0] == str(BUILD_ROOT/cfg['r86_arm']):fail('SOURCE_BINARY_UNEXPECTED')
    # Only change executable and graph path. Verify the entire R85 CLI is pinned.
    if src[1:] != [
        '-base_path',str(BASE),'-graph_outfile','/R85_SCALE1_DRY_RUN_GRAPH.graph',
        '-num_clusters','2','-cluster_size',str(cfg['cluster']),
        '-top_level_leaders','100','-fanout_scheme','10,3,1',
        '-mst_deg','2','-prune','1','-prune_all','1',
        '-prune_degree','64','-table_size',str(cfg['table']),'-hash_bits','12',
        '-alpha','1.1','-k','0']:
        fail('R85_CLI_DRIFT_'+arm)
    src[0]=str(BUILD_ROOT/cfg['r86_arm']/'algorithms/PipNN/neighbors-pipnn_FLOAT_T_EUCLIDEAN')
    src[4]=str(output)  # index 4 is graph_outfile value after -base_path value
    if src.count(str(output))!=1 or src.count(str(BASE))!=1:
        fail('OUTPUT_OR_BASE_SUBSTITUTION_FAILED')
    return ['taskset','-c',','.join(map(str,CPUS)), '/usr/bin/time',
            '-f','R86_G1_TIME wall_s=%e peak_rss_kib=%M']+src


def partition_extract(log, cfg):
    buckets = [int(x) for x in re.findall(r'^Total buckets:\s*(\d+)\s*$',log,re.M)]
    cumulative = [int(x) for x in re.findall(r'^# of comparisons during clustering:\s*(\d+)\s*$',log,re.M)]
    occ = [int(x) for x in re.findall(r'^Average table size:\s*(\d+)\s*$',log,re.M)]
    output={"buckets":buckets,"wp_cumulative":cumulative,"occupancy_printed":occ}
    errors=[]
    if buckets!=cfg['buckets']: errors.append('BUCKETS_MISMATCH')
    if cumulative!=cfg['wp_cumulative']: errors.append('COMPARISONS_MISMATCH')
    if occ!=[cfg['occupancy_floor']]: errors.append('OCCUPANCY_FLOOR_MISMATCH')
    if f"R70_RESERVOIR_VARIANT={cfg['reservoir']}" not in log:errors.append('RESERVOIR_VARIANT_MISMATCH')
    if f"R71_SELECTION_VARIANT={cfg['selection']}" not in log:errors.append('H17_SELECTION_VARIANT_MISMATCH')
    if 'Data: detected 1000000 points with dimension 128' not in log:errors.append('DATA_SHAPE_MISMATCH')
    return output,errors


def graph_audit(path):
    """Checks the original R85 binary graph layout; stdlib streaming/mmap."""
    p=regular(path)
    size=p.stat().st_size
    with p.open('rb') as f:
        hdr=f.read(8)
        if len(hdr)!=8:fail('GRAPH_HEADER_SHORT')
        n,bound=struct.unpack('<II',hdr)
        if (n,bound)!=(1_000_000,64):fail('GRAPH_HEADER_MISMATCH')
        raw=f.read(4*n)
        if len(raw)!=4*n:fail('GRAPH_DEGREES_TRUNCATED')
        from array import array
        degrees=array('I'); degrees.frombytes(raw)
        if degrees.itemsize!=4:fail('GRAPH_U32_UNSUPPORTED')
        if sys.byteorder!='little':degrees.byteswap()
        arcs=sum(degrees)
        if arcs<=0:fail('GRAPH_NO_ARCS')
        if max(degrees)>bound:fail('GRAPH_MAX_DEGREE_EXCEEDED')
        expected=8+4*n+4*arcs
        if size!=expected:fail(f'GRAPH_BYTES_INVALID got={size} want={expected}')
        with mmap.mmap(f.fileno(),0,access=mmap.ACCESS_READ) as mm:
            off=8+4*n
            for i,d in enumerate(degrees):
                if d:
                    row=struct.unpack_from('<'+str(d)+'I',mm,off)
                    if max(row)>=n or i in row or len(set(row))!=d:
                        fail('GRAPH_INVALID_NEIGHBORS_NODE_'+str(i))
                off+=4*d
            if off!=size:fail('GRAPH_SCAN_END_DRIFT')
    return {"n":n,"max_degree_bound":bound,"arcs":arcs,"graph_bytes":size,"graph_sha256":sha256(p)}


def create_session(r85):
    # Refuse any path outside R86, unique exclusive dir, never reuse R85 session.
    OUTPUT_ROOT.mkdir(parents=True,exist_ok=True)
    stamp=dt.datetime.now().strftime('%Y%m%d-%H%M%S')
    run=OUTPUT_ROOT/f'g1_{stamp}_{os.getpid()}'
    run.mkdir(exist_ok=False)
    write_exclusive(run/'manifest.json',{
        'protocol':'R86_G1_BIGANN1M_OFF_EQUIVALENCE_V1',
        'source_r85_manifest_sha256':EXPECTED['r85_manifest'],
        'source_g0_manifest_sha256':EXPECTED['g0_manifest'],
        'runner_sha256':sha256(Path(__file__)),
        'created_local':dt.datetime.now().astimezone().isoformat(),
        'cpus':list(CPUS),'beams':r85['quality_beams'],
        'input_sha256':{k:EXPECTED[k] for k in ('base','query','gt')},
        'evaluator_sha256':EXPECTED['evaluator'],
        'variants':{arm:{'binary_sha256':EXPECTED[cfg['r86_arm']], 'historical_expected_buckets':cfg['buckets'],
                         'historical_expected_wp_cumulative':cfg['wp_cumulative']}
                    for arm,cfg in ARMS.items()},
        'status':'BUILD_IN_PROGRESS',
        'note':'C++ OFF variants only; two-factor composite comparison not one-factor causal estimate; no R85 artifact writes.'
    })
    return run


def build(r85):
    run=create_session(r85)
    print('R86_G1_SESSION '+str(run),flush=True)
    outcomes=[]
    for arm,cfg in ARMS.items():
        check_resources()
        tmp=run/(arm+'.graph.tmp')
        graph=run/(arm+'.graph')
        log=run/(arm+'.build.log')
        tf=run/(arm+'.time')
        for p in (tmp,graph,log,tf):
            if p.exists() or p.is_symlink():fail('UNEXPECTED_OUTPUT_EXISTS '+str(p))
        cmd=make_build_cmd(r85,arm,tmp)
        cmd[cmd.index('R86_G1_TIME wall_s=%e peak_rss_kib=%M')+1:cmd.index('R86_G1_TIME wall_s=%e peak_rss_kib=%M')+1]=['-o',str(tf)]
        env=dict(os.environ,PARLAY_NUM_THREADS='4',OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='1',VECLIB_MAXIMUM_THREADS='1')
        print('R86_G1_BUILD_START '+arm,flush=True)
        with log.open('x',encoding='utf8') as f:
            f.write('COMMAND '+shlex.join(cmd)+'\n');f.flush()
            rc=subprocess.run(cmd,cwd=str(ROOT),env=env,stdout=f,stderr=subprocess.STDOUT,check=False).returncode
        if rc:fail('BUILD_EXIT_NONZERO '+arm+' rc='+str(rc)+' log='+str(log))
        text=log.read_text(errors='replace')
        extracted,errors=partition_extract(text,cfg)
        if not tf.is_file():fail('TIMEFILE_MISSING_'+arm)
        match=re.search(r'^R86_G1_TIME wall_s=([0-9.]+) peak_rss_kib=(\d+)\s*$',tf.read_text(errors='replace'),re.M)
        if not match:fail('TIMEFILE_PARSE_FAIL_'+arm)
        audited=graph_audit(tmp)
        tmp.rename(graph)
        record={"arm":arm,"r86_binary_sha256":EXPECTED[cfg['r86_arm']],"graph_path":str(graph),
                "log_path":str(log),"time_path":str(tf),"wall_s":float(match[1]),"peak_rss_kib":int(match[2]),
                "graph":audited,"partition":extracted,"historical_partition_errors":errors,
                "status":"GRAPH_VALID_PARTITION_MATCH" if not errors else "GRAPH_VALID_PARTITION_MISMATCH_HOLD"}
        write_exclusive(run/(arm+'.record.json'),record)
        outcomes.append(record)
        print('R86_G1_GRAPH_VALID '+arm+' arcs='+str(audited['arcs'])+' sha256='+audited['graph_sha256'],flush=True)
        print('R86_G1_PARTITION_'+('MATCH' if not errors else 'HOLD')+' '+arm+' '+json.dumps(extracted,sort_keys=True),flush=True)
        if errors:
            fail('PARTITION_HOLD '+arm+' errors='+','.join(errors)+'; source/CLI/data audit before continuing; session='+str(run))
    write_exclusive(run/'build_results.json',outcomes)
    print('R86_G1_OFF_BUILD_2_GRAPHS_PARTITION_PASS_QUALITY_NOT_YET_EVALUATED '+str(run),flush=True)


def quality(r85,run):
    run=Path(run).resolve()
    root=OUTPUT_ROOT.resolve()
    if not run.is_dir() or not run.is_relative_to(root) or run==root:
        fail('QUALITY_SESSION_NOT_R86_G1 '+str(run))
    man=read_json(run/'manifest.json')
    if man.get('protocol')!='R86_G1_BIGANN1M_OFF_EQUIVALENCE_V1':fail('QUALITY_MANIFEST_WRONG_PROTOCOL')
    if man.get('input_sha256')!={k:EXPECTED[k] for k in ('base','query','gt')}:
        fail('QUALITY_INPUT_SHA_DRIFT')
    rows=read_json(run/'build_results.json')
    if len(rows)!=2 or [r['arm'] for r in rows]!=list(ARMS):fail('QUALITY_BUILD_RESULTS_INCOMPLETE')
    for row in rows:
        if sha256(row['graph_path'])!=row['graph']['graph_sha256']:
            fail('GRAPH_SHA_CHANGED_'+row['arm'])
        if row['historical_partition_errors']:fail('QUALITY_PARTITION_HOLD_'+row['arm'])
    for row in rows:
        arm=row['arm']
        log=run/(arm+'.quality.log')
        if log.exists() or log.is_symlink():fail('QUALITY_WOULD_OVERWRITE_'+arm)
        cmd=['taskset','-c',','.join(map(str,CPUS)),str(EVAL),row['graph_path'],str(BASE),str(QUERY),str(GT),','.join(map(str,r85['quality_beams']))]
        env=dict(os.environ,PARLAY_NUM_THREADS='4',OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1')
        print('R86_G1_QUALITY_START '+arm,flush=True)
        with log.open('x',encoding='utf8') as f:
            f.write('COMMAND '+shlex.join(cmd)+'\n');f.flush()
            rc=subprocess.run(cmd,cwd=str(ROOT),env=env,stdout=f,stderr=subprocess.STDOUT,check=False).returncode
        output=log.read_text(errors='replace')
        if rc or 'R72_RECALL_EVAL_PASS' not in output or 'R85_A1C_DYNAMIC_BEAMS count=25' not in output:
            fail('QUALITY_NATIVE_EXECUTION_FAILED_OR_UNVERIFIED '+arm+' log='+str(log))
        write_exclusive(run/(arm+'.quality_record.json'),{
            'arm':arm,'graph_sha256':row['graph']['graph_sha256'],
            'evaluator_sha256':EXPECTED['evaluator'], 'quality_log_sha256':sha256(log),
            'quality_beams':r85['quality_beams'], 'native_eval_markers_pass':True,
            'recall_latency_comparison_status':'PENDING_NUMERIC_REVIEW',
            'note':'Native evaluator success does not establish matched Recall or R85-equivalent search metrics.'
        })
        print('R86_G1_QUALITY_NATIVE_EXEC_PASS_RECALL_COMPARISON_PENDING '+arm,flush=True)
    print('R86_G1_QUALITY_2_LOGS_COLLECTED_NUMERIC_RECALL_REVIEW_REQUIRED '+str(run),flush=True)


def main():
    ap=argparse.ArgumentParser(description=__doc__,formatter_class=argparse.RawDescriptionHelpFormatter)
    z=ap.add_mutually_exclusive_group(required=True)
    z.add_argument('--preflight',action='store_true',help='Read-only, checks full input hashes and flags')
    z.add_argument('--dry-run',action='store_true',help='Read-only, display exact two future build commands')
    z.add_argument('--run-build',action='store_true',help='Build exactly two new BIGANN1M graphs in new R86 directory')
    z.add_argument('--run-quality',metavar='R86_G1_SESSION',type=Path,help='Evaluate two built R86 graphs using pinned native evaluator')
    args=ap.parse_args()
    r85,_g0=validate_pins()
    if args.preflight:
        print('R86_G1_PREFLIGHT_PASS_READ_ONLY_NO_GRAPH_BUILD',flush=True)
    elif args.dry_run:
        for arm in ARMS:
            cmd=make_build_cmd(r85,arm,Path('/R86_G1_NEW_SESSION')/(arm+'.graph.tmp'))
            print('R86_G1_DRY_RUN '+arm+' '+shlex.join(cmd),flush=True)
        print('R86_G1_DRY_RUN_PASS_NO_WRITES',flush=True)
    elif args.run_build:
        build(r85)
    else:
        quality(r85,args.run_quality)


if __name__=='__main__':
    try:main()
    except Exception as e:
        print('R86_G1_FAIL_CLOSED '+repr(e),file=sys.stderr,flush=True)
        sys.exit(2)
