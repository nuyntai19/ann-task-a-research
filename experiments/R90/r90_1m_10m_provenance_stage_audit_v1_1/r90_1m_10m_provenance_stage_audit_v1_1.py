#!/usr/bin/env python3
"""R90 v1.1: read-only local 10M dataset audit and 9 SHA-pinned P4 BUILD logs.

Never builds, searches, edits dataset/source/graphs/previous logs, or changes sysctl.
Only writes a fresh report directory under experiments/R90.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
import os
import re
import shutil
import struct
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

VERSION = 'R90_1M_10M_PROVENANCE_STAGE_AUDIT_V1_1'
HOME = Path.home()
ROOT = HOME / 'ann-task-a'
P4 = ROOT / 'experiments/R90/r90_p4_msturing1m_stock_h17_fastv2_4cpu_build_v1'
DATA = ROOT / 'data'
OUT = ROOT / 'experiments/R90/r90_1m_10m_provenance_stage_audit_v1_1'
SHA_PATTERN = re.compile(r'^[a-f0-9]{64}$')
STAGES = ('buckets time', 'build leaf time', 'Final prune time')


def must(ok, code):
    if not ok:
        raise RuntimeError(VERSION + '_HOLD_' + code)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(8 * 1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def read_json(path):
    must(path.is_file() and not path.is_symlink(), 'JSON_MISSING_OR_LINK_' + path.name)
    return json.loads(path.read_text(encoding='utf8'))


def header(path: Path, kind: str):
    result = {'path': str(path), 'kind': kind, 'status': 'NOT_CHECKED'}
    if not path.is_file() or path.is_symlink():
        result['status'] = 'MISSING_OR_SYMLINK_HOLD'
        return result
    size = path.stat().st_size
    with path.open('rb') as f:
        raw = f.read(8)
    if len(raw) != 8:
        result['status'] = 'BAD_HEADER_HOLD'
        return result
    n, d = struct.unpack('<II', raw)
    must(n > 0 and d > 0, 'INVALID_DIMS_' + kind)
    if kind in ('fbin', 'ibin_gt_ids_dist', 'ibin_ids_only'):
        row_bytes = 4 * d if kind in ('fbin', 'ibin_ids_only') else 8 * d
    elif kind == 'u8bin':
        row_bytes = d
    else:
        raise ValueError('UNKNOWN_KIND')
    expected = 8 + n * row_bytes
    result.update(n=n, d=d, observed_bytes=size, expected_bytes=expected,
                  status='HEADER_SIZE_PASS' if size == expected else 'BAD_SIZE_HOLD')
    return result


def line_number(line, label):
    """Extract seconds adjacent to known Parlay timer labels; never guess an unrelated number."""
    key = re.escape(label)
    numeric = r'([0-9]+(?:\.[0-9]+)?)'
    patterns = [
        rf'(?i)\b{key}\b\s*(?:[:=]|\s+)?\s*{numeric}\s*(?:s|sec|seconds)?\b',
        rf'(?i){numeric}\s*(?:s|sec|seconds)?\s*(?:[:=]|\s+)?\b{key}\b',
        rf'(?i)\b{key}\b\s*(?:[:=]|\s+)?\s*{numeric}\s*$',
    ]
    for pat in patterns:
        m = re.search(pat, line)
        if m:
            return float(m.group(1))
    return None


def graph_built_seconds(line):
    if 'Graph built in' not in line:
        return None
    m = re.search(r'(?i)Graph built in\s*[:=]?\s*([0-9]+(?:\.[0-9]+)?)', line)
    return float(m.group(1)) if m else None


def parse_p4_stdout(text):
    """Return raw exact lines plus separately typed values, never interpolate absent timers."""
    out = {'stage_timer_lines': [], 'stages': {s: [] for s in STAGES},
           'cluster_comparisons_cumulative': [], 'graph_built_s': None,
           'graph_built_raw_lines': [], 'leaf_profiles': [], 'labels_without_numeric': []}
    for idx, line in enumerate(text.splitlines(), 1):
        for label in STAGES:
            if label.lower() in line.lower():
                val = line_number(line, label)
                out['stage_timer_lines'].append({'line': idx, 'label': label, 'text': line[:600], 'seconds': val})
                if val is None:
                    out['labels_without_numeric'].append({'line': idx, 'label': label})
                else:
                    out['stages'][label].append(val)
        if '# of comparisons during clustering' in line:
            m = re.search(r'# of comparisons during clustering\s*:\s*([0-9]+)', line)
            if m:
                out['cluster_comparisons_cumulative'].append(int(m.group(1)))
        if 'Graph built in' in line:
            out['graph_built_raw_lines'].append({'line': idx, 'text': line[:600]})
            sec = graph_built_seconds(line)
            if sec is not None:
                out['graph_built_s'] = sec
        if 'H17_LEAF_PROFILE' in line:
            out['leaf_profiles'].append({'line': idx, 'text': line[:800]})
    out['stage_sums'] = {k: (sum(v) if v else None) for k, v in out['stages'].items()}
    parts = [out['stage_sums'][s] for s in STAGES]
    out['stage_sum_total_s'] = sum(parts) if all(x is not None for x in parts) else None
    out['stage_status'] = 'STAGE_LINES_COMPLETE' if len(out['stages']['buckets time']) == 2 and \
        len(out['stages']['build leaf time']) == 2 and len(out['stages']['Final prune time']) == 1 else 'STAGE_COUNT_NOT_AS_EXPECTED'
    if out['stage_sum_total_s'] is not None and out['graph_built_s'] is not None:
        out['stage_sum_vs_graph_built_s'] = out['stage_sum_total_s'] - out['graph_built_s']
    return out


def audit_p4():
    mani = read_json(P4/'build_manifest.json')
    runs = mani.get('runs', [])
    must(len(runs) == 9, 'P4_EXPECT_NINE_RUNS')
    got = []
    for z in runs:
        arm, rep, exp = z.get('arm'), z.get('rep'), z.get('stdout_sha')
        must(arm in ('stock','h17','fast') and rep in (1,2,3), 'P4_ARM_REP')
        must(isinstance(exp,str) and SHA_PATTERN.fullmatch(exp), 'P4_SHA_MISSING')
        p = Path(z['stdout'])
        must(str(p).startswith(str(P4/'logs') + os.sep), 'P4_LOG_OUTSIDE_PINNED_DIR')
        must(p.is_file() and not p.is_symlink(), 'P4_LOG_MISSING_'+arm+str(rep))
        actual = sha256_file(p)
        must(actual == exp, 'P4_STDOUT_SHA_'+arm+str(rep))
        parsed = parse_p4_stdout(p.read_text(errors='replace'))
        got.append({'arm': arm, 'rep': rep, 'stdout_sha256': actual,
                    'wall_s_from_native_manifest': z.get('wall_s'),
                    'status': 'STDOUT_SHA_VERIFIED', **parsed})
    got.sort(key=lambda x:(x['rep'], ('stock','h17','fast').index(x['arm'])))
    return {'status': 'NINE_NATIVE_SHA_PASS', 'runs': got,
            'caveat': 'Timer labels are measured wall intervals within source stages; H17_LEAF_PROFILE matrix/selection/merge are cumulative thread-time, not additive to BUILD wall.'}


def meminfo():
    d={}
    p=Path('/proc/meminfo')
    if p.is_file():
        for l in p.read_text().splitlines():
            if l.startswith(('MemTotal:','MemAvailable:','SwapTotal:','SwapFree:')):
                parts=l.replace(':','').split()
                d[parts[0]+'_KiB']=int(parts[1])
    return d


def gtc_ids_bounds(gt_path: Path, n_base: int, n_queries: int, k: int):
    """Streaming IDs-only scan; skip float distances, never load entire GT into RAM."""
    total=n_queries*k
    min_id=2**32-1
    max_id=-1
    nonzero=0
    with gt_path.open('rb') as f:
        f.seek(8)
        for _ in range((total+16383)//16384):
            block=f.read(min(total,16384)*4)
            must(len(block)%4==0, 'GT_ID_CHUNK_TRUNC')
            for (x,) in struct.iter_unpack('<I',block):
                if x < min_id:min_id=x
                if x > max_id:max_id=x
                if x >= n_base:nonzero+=1
            total-=len(block)//4
    must(total==0, 'GT_IDS_INCOMPLETE')
    return {'id_min': min_id,'id_max':max_id,'id_out_of_bounds':nonzero,
            'gt_id_bounds_status': 'PASS' if nonzero==0 else 'HOLD_GT_ID_OUT_OF_BOUNDS'}


def compare_prefix(p1: Path, p10: Path):
    n1=header(p1,'fbin');n10=header(p10,'fbin')
    must(n1['status']=='HEADER_SIZE_PASS' and n10['status']=='HEADER_SIZE_PASS', 'PREFIX_SOURCE_FORMAT')
    must(n1['d']==n10['d'] and n1['n'] < n10['n'], 'PREFIX_DIM_OR_COUNT')
    remaining=n1['n']*n1['d']*4
    h=hashlib.sha256()
    match=True
    with p1.open('rb') as a, p10.open('rb') as b:
        a.seek(8);b.seek(8)
        while remaining:
            take=min(8*1024*1024,remaining)
            x,y=a.read(take),b.read(take)
            must(len(x)==take and len(y)==take,'PREFIX_TRUNC')
            match &= (x==y)
            h.update(x)
            remaining-=take
    return {'prefix_rows':n1['n'],'bytes_compared':n1['n']*n1['d']*4,
            'exact_prefix_match':match,'first_1m_payload_sha256':h.hexdigest()}


def audit_10m(hash_files=False,check_prefix=True,check_gt_ids=True):
    base=DATA/'MSTuring_10M_v1'
    manifest=read_json(base/'dataset_manifest.json')
    must(manifest.get('n')==10_000_000 and manifest.get('d')==100 and
         manifest.get('query_count')==100_000 and manifest.get('gt_k')==100,
         'MSTURING10M_DATASET_MANIFEST_SHAPE')
    paths={'base':base/'base.10M.fbin',
           'query':base/'query.public.100K.fbin',
           'gt':base/'groundtruth.public.100K.ibin'}
    formats={'base':'fbin','query':'fbin','gt':'ibin_gt_ids_dist'}
    metadata={k:header(p,formats[k]) for k,p in paths.items()}
    for k, expect in [('base',(10000000,100)),('query',(100000,100)),('gt',(100000,100))]:
        item=metadata[k]
        must(item['status']=='HEADER_SIZE_PASS' and (item['n'],item['d'])==expect,
             'MSTURING10M_'+k.upper()+'_FORMAT')
    out={'dataset_manifest_path':str(base/'dataset_manifest.json'),
         'manifest_source':'LOCAL_USER_DATASET_MANIFEST_NOT_AUTOMATICALLY_TRUSTED',
         'manifest':manifest,'files':metadata,'integrity':{}}
    sha_keys={'base':'base_sha256','query':'query_sha256','gt':'gt_sha256'}
    for k,p in paths.items():
        exp=manifest.get(sha_keys[k]);must(isinstance(exp,str) and SHA_PATTERN.fullmatch(exp),'MANIFEST_SHA_'+k)
        out['integrity'][k]={'expected_sha256_from_manifest':exp,
                             'status':'MANIFEST_DECLARED_NOT_REHASHED'}
        if hash_files:
            actual=sha256_file(p)
            out['integrity'][k]['actual_sha256']=actual
            out['integrity'][k]['status']='FILE_SHA_PASS' if actual==exp else 'FILE_SHA_MISMATCH_HOLD'
    if check_prefix:
        p1=DATA/'MSTuring_1M_v1/base.1M.fbin'
        out['prefix_check'] = compare_prefix(p1,paths['base'])
    if check_gt_ids:
        out['gt_ids']=gtc_ids_bounds(paths['gt'],10000000,100000,100)
    return out


def selftest():
    with tempfile.TemporaryDirectory() as d:
        root=Path(d)
        base=root/'base.fbin';gt=root/'groundtruth.ibin'
        base.write_bytes(struct.pack('<II',2,3)+24*b'\0')
        must(header(base,'fbin')['status']=='HEADER_SIZE_PASS','SELF_FBIN')
        gt.write_bytes(struct.pack('<II',2,3)+struct.pack('<6I',0,1,2,3,4,5)+struct.pack('<6f',0,1,2,3,4,5))
        must(header(gt,'ibin_gt_ids_dist')['expected_bytes']==56,'SELF_GT_FORMULA')
        must(header(gt,'ibin_gt_ids_dist')['status']=='HEADER_SIZE_PASS','SELF_GT_PASS')
        must(header(gt,'ibin_ids_only')['status']=='BAD_SIZE_HOLD','SELF_GT_DISTINGUISH_IDS')
        gt.write_bytes(gt.read_bytes()[:-4])
        must(header(gt,'ibin_gt_ids_dist')['status']=='BAD_SIZE_HOLD','SELF_GT_TRUNC')
        t=('[i] buckets time: 4.01\n'
           'build leaf time: 12.34\n# of comparisons during clustering: 120\n'
           'buckets time: 5.02\nbuild leaf time: 13.11\n'
           '# of comparisons during clustering: 240\nFinal prune time: 5.48\n'
           'Graph built in 40.12 seconds\n')
        a=parse_p4_stdout(t)
        must(a['stage_status']=='STAGE_LINES_COMPLETE','SELF_STAGE')
        must(abs(a['stage_sum_total_s']-(4.01+12.34+5.02+13.11+5.48))<1e-9,'SELF_TIMER_SUM')
        must(a['cluster_comparisons_cumulative']==[120,240],'SELF_COMPS')
    print(VERSION+'_SELFTEST_PASS')


def run(args):
    must(OUT.parent.is_dir() and not OUT.exists() and not OUT.is_symlink(),'OUTPUT_ALREADY_EXISTS')
    p4=audit_p4()
    tenm=audit_10m(args.hash_files,not args.no_prefix_check,not args.no_gt_id_scan)
    memory=meminfo()
    du=shutil.disk_usage(ROOT)
    available=memory.get('MemAvailable_KiB',0)*1024
    # The memory model is a scenario, NOT an allocation-level upper/lower proof.
    model={'rough_10m_high_C160_GiB_scenario':[25,30],
           'current_MemAvailable_GiB':round(available/2**30,3),
           'suggestion':'NO_10M_BUILD_AUTHORIZED; independent guarded pilot only after same-source 1M gates and memory headroom review',
           'warning':'Memory available fluctuates; no peak-RSS or swap proof from a read-only pass.'}
    anysha=any(x['status']!='FILE_SHA_PASS' for x in tenm['integrity'].values())
    resourcehold=available<30*2**30
    status='PROVENANCE_DECLARED_ONLY' if anysha else 'FILE_SHA_VERIFIED'
    if 'prefix_check' in tenm and not tenm['prefix_check']['exact_prefix_match']:
        status='HOLD_PREFIX_MISMATCH'
    if 'gt_ids' in tenm and tenm['gt_ids']['id_out_of_bounds']:
        status='HOLD_GT_IDS_OUT_OF_BOUNDS'
    if resourcehold:status+='__C160_MEMORY_HEADROOM_HOLD'
    record={'version':VERSION,'utc':datetime.now(timezone.utc).isoformat(),
            'p4_stage_evidence':p4,'dataset_10m':tenm,
            'memory':memory,'disk_free_bytes':du.free,'resource_model':model,
            'status':status,'NO_BUILD_NO_SEARCH':True}
    OUT.mkdir(mode=0o700)
    target=OUT/'read_only_audit.json'
    with target.open('x',encoding='utf8') as f:json.dump(record,f,indent=2,ensure_ascii=False,sort_keys=True);f.write('\n')
    print(VERSION+'_P4_LOG_SHA_PASS',len(p4['runs']))
    for z in p4['runs']:
        stages=z['stage_sums']
        print('P4_STAGE',z['arm'],'rep',z['rep'], 'buckets_s',stages['buckets time'],
              'leaf_s',stages['build leaf time'],'prune_s',stages['Final prune time'],
              'graph_built_s',z['graph_built_s'],'wall_s',z['wall_s_from_native_manifest'],
              'stage_status',z['stage_status'],'clustering_cmps_final',
              z['cluster_comparisons_cumulative'][-1] if z['cluster_comparisons_cumulative'] else 'NOT_PARSED')
    print('MSTURING10M_DATA_GATES',[(k,x['status']) for k,x in tenm['integrity'].items()],
          'prefix',tenm.get('prefix_check',{}).get('exact_prefix_match','NOT_TESTED'),
          'gt_bounds',tenm.get('gt_ids',{}).get('gt_id_bounds_status','NOT_TESTED'))
    print(VERSION+'_REPORT',target,'status',status)
    print(VERSION+'_NO_BUILD_NO_SEARCH_NO_DATASET_MODIFICATION')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('phase',choices=['selftest','audit'])
    p.add_argument('--hash-files',action='store_true',help='Rehash entire base (~4GB), query and groundtruth against source manifest (read-only).')
    p.add_argument('--no-prefix-check',action='store_true',help='Skip exact 1M payload-prefix comparison (default: check).')
    p.add_argument('--no-gt-id-scan',action='store_true',help='Skip all 10M GT index-bound checks (default: scan).')
    a=p.parse_args()
    try:
        if a.phase=='selftest':selftest()
        else:run(a)
    except Exception as e:
        print(VERSION+'_HOLD',type(e).__name__,str(e),file=sys.stderr)
        sys.exit(2)
