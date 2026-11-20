#!/usr/bin/env python3
"""R90 evidence inventory and MS-Turing10M discovery. No BUILD/SEARCH.

Reads only existing P4 BUILD stdout whose SHA matches frozen build_manifest.json,
identifies plausible 10M base/query/GT files, reads 8-byte headers and actual file
sizes, and reports RAM/disk resource estimates. Nothing in prior experiments,
source, graph, or dataset files is modified.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import re
import shutil
import struct
import sys
from datetime import datetime, timezone
from pathlib import Path

HOME = Path.home()
ROOT = HOME / 'ann-task-a'
OUT = ROOT / 'experiments/R90/r90_1m_evidence_10m_readonly_preflight_v1'
P4 = ROOT / 'experiments/R90/r90_p4_msturing1m_stock_h17_fastv2_4cpu_build_v1'
MANIFEST = P4 / 'build_manifest.json'
VERSION='R90_1M_10M_READONLY_PREFLIGHT_V1'
EXT={'.fbin':4,'.ibin':4,'.u8bin':1,'.i8bin':1}
INTERESTING=re.compile(r'(turing|mstur|10m|10000000|base|query|groundtruth|gt)',re.I)
PROFILE=re.compile(r'(H17_LEAF_PROFILE|leaf_calls|matrix_sum|selection_sum|merge_sum|Total buckets|Total points)',re.I)
SKIP={'.git','.venv','node_modules','_deps','build','build_debug','build_release','graphs','logs'}

def check(cond,reason):
    if not cond:
        raise RuntimeError(VERSION+'_HOLD_'+reason)

def sha256(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(4*1024*1024),b''): h.update(b)
    return h.hexdigest()

def inspect_header(path):
    d={'path':str(path),'filename':path.name,'bytes':path.stat().st_size,'suffix':path.suffix.lower()}
    if path.is_symlink() or not path.is_file():
        d['status']='SKIPPED_SYMLINK_OR_NONFILE';return d
    if d['suffix'] not in EXT:
        d['status']='UNKNOWN_FORMAT_NOT_PARSED';return d
    with path.open('rb') as f:
        h=f.read(8)
    if len(h)!=8:
        d['status']='INVALID_HEADER';return d
    n,dim=struct.unpack('<II',h)
    width=EXT[d['suffix']]
    size=8+int(n)*int(dim)*width
    d.update({'n':n,'dimension':dim,'element_bytes':width,'expected_bytes':size,
              'size_match':size==d['bytes'],
              'status':'HEADER_SIZE_PASS' if size==d['bytes'] else 'BAD_HEADER_OR_SIZE'})
    return d

def discover(roots, hash_all=False,max_files=15000):
    found=[];scanned=0;blocked=[]
    for root in roots:
        if not root.is_dir() or root.is_symlink():
            blocked.append({'root':str(root),'status':'NOT_DIRECTORY_OR_SYMLINK'});continue
        for dirname,dirs,files in os.walk(root,followlinks=False):
            dirs[:]=sorted(d for d in dirs if d not in SKIP and not (Path(dirname)/d).is_symlink())
            for f in sorted(files):
                scanned+=1
                check(scanned<=max_files,'MAX_FILE_COUNT_EXCEEDED')
                p=Path(dirname)/f
                if p.suffix.lower() not in EXT or p.is_symlink():continue
                item=inspect_header(p)
                if item.get('n')==10_000_000 or INTERESTING.search(str(p)):
                    if hash_all and item['status']=='HEADER_SIZE_PASS':item['sha256']=sha256(p)
                    found.append(item)
    return {'scanned_file_names':scanned,'matching_candidates':found,'blocked_roots':blocked,
            'full_sha_requested':hash_all}

def p4_profiles():
    if not MANIFEST.is_file() or MANIFEST.is_symlink():
        return {'status':'MISSING_P4_MANIFEST','expected_path':str(MANIFEST)}
    try: j=json.loads(MANIFEST.read_text())
    except (OSError,ValueError) as e:
        return {'status':'BAD_P4_MANIFEST','error':str(e)}
    out=[]
    for entry in j.get('runs',[]):
        if entry.get('arm') not in ('stock','h17','fast') or entry.get('rep') not in (1,2,3):continue
        log=Path(entry.get('stdout',''))
        item={'arm':entry['arm'],'rep':entry['rep'],'stdout_path':str(log),
              'expected_sha':entry.get('stdout_sha')}
        if not log.is_file() or log.is_symlink():
            item['status']='MISSING_LOG';out.append(item);continue
        actual=sha256(log)
        item['actual_sha']=actual
        if actual!=entry.get('stdout_sha'):
            item['status']='LOG_SHA_HOLD';out.append(item);continue
        lines=[]
        for line in log.read_text(errors='replace').splitlines():
            if PROFILE.search(line):lines.append(line[:1200])
        item.update({'status':'LOG_SHA_PASS','profile_lines':lines[:80],
                     'profile_lines_truncated':len(lines)>80})
        out.append(item)
    return {'status':'INVENTORY_COMPLETE','runs':out,
            'note':'Thread-summed profile times are not additive to global 4CPU wall time.'}

def meminfo():
    p=Path('/proc/meminfo');vals={}
    if p.is_file():
        for l in p.read_text().splitlines():
            if l.startswith(('MemTotal:','MemAvailable:','SwapTotal:','SwapFree:')):
                name,val,*_=l.replace(':','').split();vals[name+'_KiB']=int(val)
    return vals

def selftest():
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        p=Path(td)/'base.10M.fbin'
        p.write_bytes(struct.pack('<II',2,3)+24*b'\0')
        x=inspect_header(p)
        check(x['status']=='HEADER_SIZE_PASS' and x['n']==2 and x['dimension']==3,'SELFTEST_FBIN')
        p.write_bytes(p.read_bytes()[:-1])
        check(inspect_header(p)['status']=='BAD_HEADER_OR_SIZE','SELFTEST_SIZE_HOLD')
    print(VERSION+'_SELFTEST_PASS')

def preflight(args):
    check(OUT.parent.is_dir() and not OUT.exists() and not OUT.is_symlink(),'OUTPUT_EXISTS_OR_PARENT_MISSING')
    roots=[Path(s).expanduser().resolve() for s in args.data_root]
    result=discover(roots,args.hash_all,args.max_files)
    tenm=[x for x in result['matching_candidates'] if x.get('n')==10_000_000 and x.get('status')=='HEADER_SIZE_PASS']
    base=[x for x in tenm if 'base' in x['filename'].lower() and x['suffix']=='.fbin']
    mem=meminfo();disk=shutil.disk_usage(ROOT)
    # Only lower bounds / coarse planning; NOT a measured peak-RSS prediction.
    n=10_000_000;dim=100;C=160;arc_per_point=52.85
    sizing={'base_10m_100d_f32_nominal_bytes':n*dim*4,
            'candidate_C160_slot_lower_model_bytes':n*(C+1)*8,
            'graph_52_85_arcs_per_point_x_uint32_bytes_rough':round(n*arc_per_point*4),
            'warning':'These do not sum to a proven peak RSS. Multiple transients, copies, build buffers, HashPrune, concurrency can increase peak.'}
    summary={'version':VERSION,'timestamp_utc':datetime.now(timezone.utc).isoformat(),
             'data_scan':result,'verified_10m_header_file_count':len(tenm),
             'plausible_float32_base_10m_count':len(base),
             'p4_native_log_profile':p4_profiles(),'memory':mem,
             'disk_available_bytes':disk.free,'disk_total_bytes':disk.total,
             'sizing_reference':sizing,
             'status':'10M_HEADER_FOUND__PROVENANCE_GT_AND_RESOURCES_UNVERIFIED' if base else 'HOLD_NO_VERIFIED_10M_FBIN_BASE',
             'important':'Header/size alone do NOT prove dataset identity, exact 10M GT, feasible RAM/disk, or BUILD equivalence. 10M GT must match 10M base.'}
    OUT.mkdir(mode=0o700)
    p=OUT/'preflight_report.json'
    with p.open('x',encoding='utf8') as f:json.dump(summary,f,indent=2,ensure_ascii=False,sort_keys=True);f.write('\n')
    print(VERSION+'_REPORT',p,'status',summary['status'],'10m_candidates',len(tenm),'base_fbin10m',len(base))
    for item in tenm:print('CANDIDATE_10M',item['path'], 'n',item['n'],'d',item['dimension'],'size_ok',item['size_match'],'sha256',item.get('sha256','NOT_HASHED'))
    print(VERSION+'_NO_BUILD_NO_SEARCH_NO_SOURCE_MODIFICATION')

if __name__=='__main__':
    cli=argparse.ArgumentParser(description=__doc__)
    cli.add_argument('phase',choices=['selftest','preflight'])
    cli.add_argument('--data-root',action='append',default=None,
                     help='Repeatable directory to scan; default ~/ann-task-a/data and ~/Downloads')
    cli.add_argument('--hash-all',action='store_true',help='SHA256 all candidate files including multi-GB files (slower read-only)')
    cli.add_argument('--max-files',type=int,default=15000)
    a=cli.parse_args()
    if a.data_root is None:a.data_root=[str(ROOT/'data'),str(HOME/'Downloads')]
    try:
        if a.phase=='selftest':selftest()
        else:preflight(a)
    except Exception as e:
        print(VERSION+'_HOLD',type(e).__name__,str(e),file=sys.stderr)
        sys.exit(2)
