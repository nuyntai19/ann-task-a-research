#!/usr/bin/env python3
"""H32-R8: read-only provenance audit for existing H31 runs.

NEVER calls ANN BUILD, SEARCH, compilers, or graph mutation.
Writes only new JSON/TXT reports under experiments/H32/R8_*.
"""
import argparse
import datetime as dt
import hashlib
import json
import math
import os
from pathlib import Path
import re
import statistics
import struct
import subprocess
import sys
import tempfile

ROLES = ('VAMANA', 'STOCK', 'TOP2')
EXPECTED = {
    'VAMANA': {'sha256': '84b2935cb9f25e9ad53044099901c8c1e6cb4de059975882e8d91bca66aa5259', 'bytes': 114573392, 'edges': 27643346},
    'STOCK': {'sha256': 'ce1cd7c5ae97b79972df2b30235a0844b88a6c8a983ce731ca3afca494d7095d', 'bytes': 95174232, 'edges': 22793556},
    'TOP2': {'sha256': '73646a2b5655e16939ca804c598818460152803c20f6932e6e9286acd334c5c6', 'bytes': 95176264, 'edges': 22794064},
}
EXPECTED_BIN = 'ee6b9c0bec2f32fe00607f3facc73691d2dca2d5158e84e69c226b3cd219c9a8'
EXPECTED_HEAD = 'a48c6a34e5f959190992aa531cc18454cfcc3dd3'
R2_DIRS = {
    'R2_INITIAL': 'H31_R2_20261029_101943_596045',
    'R2B_1': 'H31_R2_20261029_104205_116336',
    'R2B_2': 'H31_R2_20261029_104324_359107',
    'R2B_3': 'H31_R2_20261029_104440_070228',
}
R2_Q = {'R2_INITIAL': {100,120,160}, 'R2B_1': {120}, 'R2B_2': {120}, 'R2B_3': {120}}
EXPECTED_Q120_ORDER = {
    'R2B_1': ('VAMANA','STOCK','TOP2'),
    'R2B_2': ('STOCK','TOP2','VAMANA'),
    'R2B_3': ('TOP2','VAMANA','STOCK'),
}
FIELD = r'([-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)'
SEARCH_RE = re.compile(r'search:\s*Q=(\d+),\s*k=(\d+),\s*limit=(\d+),\s*recall=' + FIELD + r',\s*visited=' + FIELD + r',\s*comparisons=' + FIELD + r',\s*QPS=' + FIELD, re.I)


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(4 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def status(label, state, details='', **extra):
    return {'name': label, 'status': state, 'details': str(details), **extra}


def graph_audit(role, item):
    expected = EXPECTED[role]
    p = Path(item['path']).expanduser()
    if not p.is_file():
        return status('GRAPH_' + role, 'MISSING', str(p))
    sz = p.stat().st_size
    if sz != expected['bytes'] or sz != item.get('bytes'):
        return status('GRAPH_' + role, 'FAIL', f'file bytes={sz}, expected={expected["bytes"]}, inventory={item.get("bytes")}')
    with p.open('rb') as f:
        header = f.read(8)
        if len(header) != 8:
            return status('GRAPH_' + role, 'FAIL', 'truncated header')
        n, maxdeg = struct.unpack('<II', header)
        if n != 1_000_000 or not (1 <= maxdeg <= 65536):
            return status('GRAPH_' + role, 'FAIL', f'bad header n={n} maxdeg={maxdeg}')
        degree_bytes = f.read(n * 4)
        if len(degree_bytes) != n * 4:
            return status('GRAPH_' + role, 'FAIL', 'truncated degree array')
    count = 0
    for (deg,) in struct.iter_unpack('<I', degree_bytes):
        if deg > maxdeg:
            return status('GRAPH_' + role, 'FAIL', f'degree {deg} > declared maxdeg {maxdeg}')
        count += deg
    if count != expected['edges'] or count != item.get('directed_edge_occurrences'):
        return status('GRAPH_' + role, 'FAIL', f'edge count={count}, expected={expected["edges"]}, inventory={item.get("directed_edge_occurrences")}')
    if sz != 8 + 4*n + 4*count:
        return status('GRAPH_' + role, 'FAIL', 'graph length inconsistent with degrees')
    got_sha = digest(p)
    if got_sha != expected['sha256'] or got_sha != item.get('sha256'):
        return status('GRAPH_' + role, 'FAIL', f'SHA mismatch actual={got_sha}, pinned={expected["sha256"]}, inventory={item.get("sha256")}')
    return status('GRAPH_' + role, 'PASS', 'pinned SHA, byte length, degree sum, header and inventory match', path=str(p.resolve()), sha256=got_sha, bytes=sz, directed_edges=count, max_degree=maxdeg)


def dataset_audit(root, label, rel, n0, d0, blocks):
    p=root/rel
    if not p.is_file(): return status('DATA_' + label, 'MISSING', str(p))
    sz=p.stat().st_size
    expected_sz=8+n0*d0*4*blocks
    with p.open('rb') as f: header=f.read(8)
    if len(header)!=8:return status('DATA_'+label,'FAIL','truncated header')
    n,d=struct.unpack('<II',header)
    if (n,d,sz)!=(n0,d0,expected_sz):
        return status('DATA_'+label,'FAIL',f'n={n},d={d},bytes={sz}; expected n={n0},d={d0},bytes={expected_sz}')
    return status('DATA_'+label,'PASS_HEADER_SIZE_ONLY',f'n={n},d={d},bytes={sz}; NO exact GT correctness claim',path=str(p.resolve()),bytes=sz)


def gt_sample(root):
    path=root/'data/sift1m_gt.ibin'
    if not path.is_file() or path.stat().st_size != 8000008:
        return status('GT_SAMPLE','BLOCKED','GT file missing or wrong length')
    # ParlayANN format: header + 10k*100 uint32 IDs + 10k*100 float32 distances.
    sampled=0
    with path.open('rb') as f:
        for row in range(0,10000,100):
            f.seek(8+row*100*4)
            ids=struct.unpack('<100I', f.read(400))
            f.seek(8+10000*100*4+row*100*4)
            distances=struct.unpack('<100f',f.read(400))
            if any(i>=1000000 for i in ids):
                return status('GT_SAMPLE','FAIL',f'row={row} has out-of-range neighbor id')
            if any(not math.isfinite(x) or x<0 for x in distances):
                return status('GT_SAMPLE','FAIL',f'row={row} has invalid distance')
            sampled+=1
    return status('GT_SAMPLE','PASS_SAMPLE_ONLY',f'{sampled} spaced rows; not exact GT validation')


def binary_audit(root):
    p=root/'src/ParlayANN/algorithms/vamana/neighbors'
    if not p.is_file(): return status('SEARCH_BINARY','MISSING',str(p))
    h=digest(p)
    mode='PASS' if h==EXPECTED_BIN else 'FAIL'
    return status('SEARCH_BINARY',mode,f'actual_sha256={h}, expected={EXPECTED_BIN}',path=str(p.resolve()),sha256=h)


def git_audit(root):
    p=root/'src/ParlayANN'
    if not p.is_dir(): return status('PARLAYANN_HEAD','MISSING',str(p))
    try:
        proc=subprocess.run(['git','-C',str(p),'rev-parse','HEAD'],capture_output=True,text=True,timeout=8,check=False)
        head=proc.stdout.strip() if proc.returncode==0 else 'UNKNOWN'
    except (OSError,subprocess.TimeoutExpired):head='UNKNOWN'
    return status('PARLAYANN_HEAD','PASS' if head==EXPECTED_HEAD else 'UNVERIFIED',f'actual={head}, expected={EXPECTED_HEAD}',head=head)


def process_session(path, kind):
    result_path=path/'h31_r2_results.json';run_path=path/'h31_r2_runs.json'
    if not result_path.is_file() or not run_path.is_file():
        return status('SESSION_'+kind,'MISSING',f'{result_path} or {run_path} missing')
    try:
        result=json.loads(result_path.read_text(encoding='utf-8'))
        runs=json.loads(run_path.read_text(encoding='utf-8'))
    except (ValueError,OSError) as e:
        return status('SESSION_'+kind,'FAIL','JSON not readable: '+str(e))
    if not isinstance(runs,list) or not isinstance(result,dict):
        return status('SESSION_'+kind,'FAIL','bad JSON root')
    expected_pairs={(role,q) for q in R2_Q[kind] for role in ROLES}
    actual_pairs={(x.get('role'),x.get('Q')) for x in runs if isinstance(x,dict)}
    if actual_pairs != expected_pairs or len(runs) != len(expected_pairs):
        return status('SESSION_'+kind,'FAIL',f'wrong role-Q combinations expected={sorted(expected_pairs)} actual={sorted(actual_pairs)}')
    if kind in EXPECTED_Q120_ORDER and tuple(x['role'] for x in runs)!=EXPECTED_Q120_ORDER[kind]:
        return status('SESSION_'+kind,'FAIL','role processing order differs from reported balanced round')
    param=result.get('parameters') or {}
    if param.get('workers')!=1 or param.get('k')!=10 or set(param.get('qs',[]))!=R2_Q[kind]:
        return status('SESSION_'+kind,'FAIL','unexpected workers/k/Q grid')
    pre=(result.get('preflight') or {})
    for role in ROLES:
        item=(pre.get('graphs') or {}).get(role) or {}
        if item.get('sha256')!=EXPECTED[role]['sha256']:
            return status('SESSION_'+kind,'FAIL',f'provenance sha mismatch for {role}')
    if pre.get('binary_sha256')!=EXPECTED_BIN:
        return status('SESSION_'+kind,'FAIL','historical searcher binary SHA mismatch')
    rows={(x.get('role'),x.get('Q')):x for x in result.get('rows',[]) if isinstance(x,dict)}
    if set(rows)!=expected_pairs:return status('SESSION_'+kind,'FAIL','result rows mismatch')
    medians={}
    for rec in runs:
        role,q=rec['role'],rec['Q']
        if rec.get('returncode')!=0 or len(rec.get('metrics') or [])!=5:
            return status('SESSION_'+kind,'FAIL',f'nonzero or fewer than 5 raw metric records: {role} Q{q}')
        values=[]
        for x in rec['metrics']:
            if x.get('q')!=q or x.get('k')!=10 or not (0<=x.get('recall',-1)<=1) or not (x.get('qps',0)>0):
                return status('SESSION_'+kind,'FAIL',f'bad metric: {role} Q{q}')
            values.append(float(x['qps']))
        med=statistics.median(values)
        summary=rows[(role,q)]
        if abs(med-summary.get('qps_median',-1))>0.03:
            return status('SESSION_'+kind,'FAIL',f'median mismatch: {role} Q{q} {med} vs {summary.get("qps_median")}')
        log_path=path/f'{role.lower()}_Q{q}.log'
        if not log_path.is_file():
            return status('SESSION_'+kind,'PARTIAL',f'missing raw log {log_path}; JSON cross-check only')
        text=log_path.read_text(encoding='utf-8',errors='replace')
        found=list(SEARCH_RE.finditer(text))
        if len(found)!=5:
            return status('SESSION_'+kind,'FAIL',f'{log_path.name} has {len(found)} search lines rather than 5')
        vals=[float(m.group(7)) for m in found]
        if any(int(m.group(1))!=q or int(m.group(2))!=10 for m in found):
            return status('SESSION_'+kind,'FAIL','raw log Q/k does not match')
        if any(abs(a-b)>0.02 for a,b in zip(vals,values)):
            return status('SESSION_'+kind,'FAIL','raw log QPS different from JSON')
        medians[f'{role}_Q{q}']=round(med,2)
    return status('SESSION_'+kind,'PASS',f'{len(runs)} role×Q records, 5 raw search repetitions each, JSON/log/graph+binary SHA consistent; no new search',dir=str(path),qps_medians=medians)


def cpu_info():
    p=Path('/sys/devices/system/cpu/online')
    return {'sched_affinity': sorted(os.sched_getaffinity(0)) if hasattr(os,'sched_getaffinity') else 'UNKNOWN',
            'online_cpus':p.read_text().strip() if p.is_file() else 'UNKNOWN',
            'note':'CPU physical mapping / governor / thermal not measured; run lscpu -e=CPU,CORE,SOCKET separately if required.'}


def report(root):
    items=[]
    invpath=root/'experiments/H31/H31_R0_20261028_003956/h31_r0_inventory.json'
    if not invpath.is_file():
        items.append(status('INVENTORY','MISSING',str(invpath)))
    else:
        try:
            inv=json.loads(invpath.read_text(encoding='utf-8'))
            graph_roles=inv.get('graph_roles') or {}
            if set(ROLES) - set(graph_roles):
                items.append(status('INVENTORY','FAIL','missing required graph role'))
            else:
                items.append(status('INVENTORY','PASS','original H31-R0 inventory found'))
                for role in ROLES:items.append(graph_audit(role,graph_roles[role]))
        except (ValueError,OSError,KeyError,TypeError) as e:
            items.append(status('INVENTORY','FAIL',str(e)))
    datasets=[('BASE','data/sift1m.fbin',1000000,128,1),('QUERIES','data/sift1m_queries.fbin',10000,128,1),('GT','data/sift1m_gt.ibin',10000,100,2)]
    for args in datasets:items.append(dataset_audit(root,*args))
    items.append(gt_sample(root))
    items.append(binary_audit(root));items.append(git_audit(root))
    for name,folder in R2_DIRS.items():items.append(process_session(root/'experiments/H31'/folder,name))
    relevant=[x for x in items if x['name']!='PARLAYANN_HEAD']
    any_hard_fail=any(x['status']=='FAIL' for x in relevant)
    missing=any(x['status'] in ('MISSING','PARTIAL','BLOCKED') for x in relevant)
    all_critical_pass=all(x['status'] in ('PASS','PASS_HEADER_SIZE_ONLY','PASS_SAMPLE_ONLY') for x in relevant)
    overall='FAIL_INPUT_INTEGRITY' if any_hard_fail else ('PASS_LOCAL_AUDIT' if all_critical_pass else 'PARTIAL_LOCAL_AUDIT')
    return {'study':'H32_R8_LOCAL_READ_ONLY_AUDIT','mode':'NO_BUILD_NO_SEARCH_NO_GRAPH_MUTATION','root':str(root),
            'timestamp_utc':dt.datetime.now(dt.timezone.utc).isoformat(), 'overall':overall,
            'status_items':items,'cpu_information':cpu_info(),
            'scientific_gates':{'Q01_existing_graph_provenance':'PASS' if all(x['status']=='PASS' for x in items if x['name'].startswith('GRAPH_')) and any(x['name']=='GRAPH_VAMANA' for x in items) else 'NOT_CONFIRMED',
                                'Q01_equal_graph_budget':'BLOCKED_KNOWN_DIFFERENT_BYTES',
                                'Q01_equal_recall_pareto':'NOT_DETERMINED',
                                'Q02_intraquery_binary':'NOT_VERIFIED_INTERQUERY_ONLY_CURRENT_PARLAYANN',
                                'H17_engineering_build_speedup':'HISTORIC_RESULT_NOT_REMEASURED',
                                'H33_new_algorithm':'NOT_AUTHORIZED_OR_EVALUATED'},
            'notes':['Graph input files are NEVER written to; only output report files are created.',
                     'GT sample checks 100 spaced rows for range and non-negative finite scores; not exact oracle correctness.',
                     'R2b 3 process rounds with 5 internal repetitions each are not 15 independent graph builds.',
                     'Matched graph bytes and matched recall are not established.',
                     'No ANN build/search workload or CPU profiling was invoked.']}


def format_txt(rep, outdir):
    lines=['H32-R8 LOCAL READ-ONLY AUDIT (NO BUILD / NO SEARCH / NO GRAPH MUTATION)',
           f'ROOT={rep["root"]}', f'OVERALL={rep["overall"]}',
           'CHECKS:']
    for item in rep['status_items']:
        lines.append(f'  {item["name"]:<22} {item["status"]:<23} {item["details"]}')
        if item.get('qps_medians'):
            lines.append('    '+str(item['qps_medians']))
    lines += ['SCIENTIFIC GATES:']+[f'  {k}={v}' for k,v in rep['scientific_gates'].items()]
    lines += ['NO NEW BUILD, NO SEARCH, NO GRAPH MODIFICATION.',
              'NO EQUAL-BUDGET CLAIM, NO INTRA-QUERY-PARALLEL CLAIM, NO NOVELTY CLAIM.',
              'NEXT: share h32_r8_summary.txt and h32_r8_report.json; avoid uploading original large datasets/graphs.',
              'H32R8_DONE='+str(outdir)]
    return '\n'.join(lines)+'\n'


def selftest():
    with tempfile.TemporaryDirectory() as td:
        root=Path(td)
        a=root/'file'; a.write_bytes(b'hello')
        assert digest(a)==hashlib.sha256(b'hello').hexdigest()
        (root/'data').mkdir()
        f=root/'data/sift1m_gt.ibin'
        f.write_bytes(b'not a valid GT')
        assert gt_sample(root)['status']=='BLOCKED'
        (root/'data/sift1m.fbin').write_bytes(struct.pack('<II',2,3)+b'\0'*24)
        assert dataset_audit(root,'TINY','data/sift1m.fbin',2,3,1)['status']=='PASS_HEADER_SIZE_ONLY'
        fake={'role':'STOCK','Q':120, 'metrics':[{'q':120,'k':10,'qps':2.0,'recall':0.99}] * 5}
        assert statistics.median(x['qps'] for x in fake['metrics'])==2.0
        assert len(list(SEARCH_RE.finditer('search: Q=120, k=10, limit=0, recall=0.99, visited=2, comparisons=10, QPS=2300.7'))) == 1
    print('H32R8_READONLY_SYNTHETIC_SELFTEST_PASS (no real Ubuntu data checked)')


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--mode',required=True,choices=('selftest','audit'))
    ap.add_argument('--root',type=Path,default=Path('~/ann-task-a'))
    ap.add_argument('--out',type=Path,help='New output dir; if omitted, create experiments/H32/H32_R8_<timestamp>')
    args=ap.parse_args()
    if args.mode=='selftest':return selftest()
    root=args.root.expanduser().resolve()
    if not root.is_dir():raise SystemExit(f'ROOT_MISSING: {root}')
    out=args.out.expanduser().resolve() if args.out else root/'experiments/H32'/('H32_R8_'+dt.datetime.now().strftime('%Y%m%d_%H%M%S'))
    # Never overwrite an older report. User source inputs should remain untouched.
    out.mkdir(parents=True,exist_ok=False)
    rep=report(root)
    (out/'h32_r8_report.json').write_text(json.dumps(rep,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    summary=format_txt(rep,out)
    (out/'h32_r8_summary.txt').write_text(summary,encoding='utf-8')
    print(summary,end='')


if __name__=='__main__':
    try:main()
    except Exception as e:
        print('H32R8_SCRIPT_ERROR: '+type(e).__name__+': '+str(e),file=sys.stderr)
        raise SystemExit(2)
