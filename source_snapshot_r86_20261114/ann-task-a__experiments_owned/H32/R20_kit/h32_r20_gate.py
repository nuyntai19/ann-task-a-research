#!/usr/bin/env python3
"""H32-R20: safe local historical resource-log audit; no ANN build/search.

Only reads small text files within expected experiment directories. Does not
rewrite original files, invoke subprocesses, or claim to benchmark PiPNN II.
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
import os
import re
import tempfile
from collections import Counter
from datetime import datetime
from pathlib import Path

SUFFIXES={'.json','.txt','.log','.csv','.tsv','.out','.md'}
NAMED_DIRS=('H17','H19','H26')
MAX_FILE=5*1024*1024
MAX_FILES=3000
MAX_HITS=500
# No source file values are assumed to have the same meaning until classified.
KEYS=re.compile(r'(?i)(peak[ _-]?(?:rss|resident)|max(?:imum)?[ _-]?(?:rss|resident)|ru_maxrss|vmhwm|major[ _-]?page[ _-]?fault|minor[ _-]?page[ _-]?fault|swap(?:ped|ping)?|MemTotal|mem[_ -]?usage|peak[_ -]?memory|resident[ _-]?set)')
VALUE=re.compile(r'(?<![a-zA-Z0-9])([0-9]{1,3}(?:[,.][0-9]{3})+|[0-9]+(?:\.[0-9]+)?)\s*(KiB|kB|KB|MiB|MB|GiB|GB|bytes?)?',re.I)
H19_HISTORICAL_RSS_KIB={'1_worker':1714432,'2_workers':1758336,'4_workers':1849076}


def meminfo(path=Path('/proc/meminfo')):
    d={}
    if not path.exists():return d
    for l in path.read_text(errors='replace').splitlines():
        if ':' not in l:continue
        k,v=l.split(':',1)
        if k in {'MemTotal','MemAvailable','SwapTotal','SwapFree'}:
            m=re.search(r'(\d+)\s*kB',v)
            if m:d[k+'_KiB']=int(m.group(1))
    return d


def inventory(root):
    files=[]; stopped=[]
    for group in NAMED_DIRS:
        base=root/'experiments'/group
        if not base.is_dir():
            stopped.append(f'MISSING_DIRECTORY: {base}')
            continue
        for parent, dirs, fs in os.walk(base,followlinks=False):
            dirs[:]=sorted(x for x in dirs if not (Path(parent)/x).is_symlink())
            for fn in sorted(fs):
                p=Path(parent)/fn
                if p.suffix.lower() not in SUFFIXES or p.is_symlink(): continue
                try:
                    st=p.stat()
                except OSError:continue
                if not st.st_size or st.st_size>MAX_FILE: continue
                files.append((group,p))
                if len(files)>=MAX_FILES:
                    stopped.append('MAX_FILES_LIMIT_REACHED');return files,stopped
    return files,stopped


def read_hits(group,path):
    result=[]
    try:
        with path.open('r',encoding='utf-8',errors='replace') as f:
            for i,line in enumerate(f,1):
                if len(line)>20000:line=line[:20000]
                if not KEYS.search(line):continue
                # Each line can include multiple counters; preserve line context for audit.
                vals=[]
                for m in VALUE.finditer(line):
                    vals.append({'value':m.group(1),'unit':m.group(2) or 'unspecified'})
                result.append({'group':group,'file':str(path),'line':i,
                               'context':line.strip()[:320], 'numeric_tokens':vals[:10]})
                if len(result)>=40:break
    except (OSError,UnicodeError):pass
    return result


def report(root,output_root):
    files,warnings=inventory(root)
    hits=[]; bygroup=Counter()
    for group,path in files:
        h=read_hits(group,path)
        bygroup[group]+=len(h)
        hits.extend(h)
        if len(hits)>=MAX_HITS:
            warnings.append('MAX_MATCHES_LIMIT_REACHED');hits=hits[:MAX_HITS];break
    total=meminfo()
    memtotal=total.get('MemTotal_KiB')
    hist_peak=max(H19_HISTORICAL_RSS_KIB.values())
    # This fraction compares a past single process RSS to today's total RAM,
    # NOT historic availability or all processes' peak combined memory.
    ratio=(hist_peak/memtotal) if memtotal else None
    out=output_root/f'H32_R20_{datetime.now().strftime("%Y%m%d_%H%M%S_%f")}'
    out.mkdir(parents=True,exist_ok=False)
    payload={'status':'HISTORICAL_RESOURCE_INVENTORY_ONLY', 'root':str(root),
      'no_build_no_search':True,'no_pipnn_ii_binary_or_benchmark':True,
      'current_system_meminfo_KiB':total,
      'memory_comment':'Current MemAvailable is NOT historic free RAM during H19 build.',
      'h19_reported_from_existing_research_record_KiB':H19_HISTORICAL_RSS_KIB,
      'h19_source_caveat':'Historical R2/R2.1 profiler builds, not H26-P0, not paired against PiPNN II.',
      'h19_max_reported_peak_to_current_MemTotal_ratio':ratio,
      'scanned_text_files':len(files),'match_count':len(hits),
      'matched_groups':dict(bygroup),'warnings':warnings,'matches':hits,
      'pitfalls':['Do not infer no swap/OOM from this script.','Do not infer causal bottleneck from RSS/total ratio.',
                  'A closed DiskANN issue #1030 has maintainer comment that PiPNN memory now matches Vamana FP build.',
                  'No PiPNN II direct CPU comparison has been performed.']}
    (out/'h32_r20_report.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
    lines=['H32-R20 | HISTORICAL LOG MEMORY & PIPNN II BASELINE GATE',
      'OVERALL=PASS_READONLY_INVENTORY_NOT_NEW_BUILD',f'ROOT={root}',f'OUTPUT={out}',
      'BUILD=NO SEARCH=NO GRAPH_CHANGE=NO','PIPNN_II_EXECUTED=NO',
      f'SCANNED_SMALL_TEXT_FILES={len(files)}',f'LOG_MATCHING_LINES={len(hits)}',
      f'MATCHES_H17={bygroup["H17"]} H19={bygroup["H19"]} H26={bygroup["H26"]}',
      f'H19_HISTORICAL_MEDIAN_MAXRSS_KIB_1T={H19_HISTORICAL_RSS_KIB["1_worker"]} 2T={H19_HISTORICAL_RSS_KIB["2_workers"]} 4T={H19_HISTORICAL_RSS_KIB["4_workers"]}',
      f'CURRENT_MEMTOTAL_KIB={memtotal if memtotal else "UNAVAILABLE"}',
      f'CURRENT_MEMAVAILABLE_KIB={total.get("MemAvailable_KiB","UNAVAILABLE")}',
      f'H19_4T_RSS_TO_CURRENT_MEMTOTAL_RATIO={ratio:.5f}' if ratio is not None else 'H19_4T_RSS_TO_CURRENT_MEMTOTAL_RATIO=UNAVAILABLE',
      'RAM_PRESSURE_DURING_H19_BUILD=NOT_PROVEN_FROM_CURRENT_INPUT',
      'MEMORY_ALGORITHM_NOVELTY=NOT_ESTABLISHED (DiskANN issue #1030 reported fixed)',
      'PIPNN_II_FAIR_BENCHMARK=BLOCKED_UNTIL_MATCHED_REPRODUCIBLE_IMPLEMENTATION',
      'REMINDER=Read matches from report JSON; do not mistake a size in arbitrary logs for verified BUILD VmHWM.']
    lines.extend('WARNING='+w for w in warnings)
    (out/'h32_r20_summary.txt').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    return out,lines


def selftest():
    with tempfile.TemporaryDirectory() as td:
        p=Path(td);f=p/'experiments'/'H19'/'r2.log';f.parent.mkdir(parents=True)
        f.write_text('Maximum resident set size (kbytes): 1849076\nElapsed time (seconds): 44.13\nVmHWM: 1849076 kB\n')
        files,warn=inventory(p)
        assert len(files)==1 and len(warn)==2
        h=read_hits('H19',f)
        assert len(h)==2 and h[0]['numeric_tokens'][0]['value']=='1849076'
        m=p/'meminfo';m.write_text('MemTotal:      8080000 kB\nMemAvailable:  4000000 kB\n')
        assert meminfo(m)['MemTotal_KiB']==8080000
        out,_=report(p,p/'out')
        d=json.loads((out/'h32_r20_report.json').read_text())
        assert d['match_count']==2 and d['no_build_no_search']
    print('H32R20_SYNTHETIC_SELFTEST_PASS (NO REAL UBUNTU BUILD LOGS CHECKED)')


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--mode',required=True,choices=['selftest','audit'])
    parser.add_argument('--root',default=str(Path.home()/'ann-task-a'))
    args=parser.parse_args()
    if args.mode=='selftest':selftest();return
    root=Path(args.root).expanduser().resolve()
    if not root.is_dir() or not (root/'experiments').is_dir():
        raise SystemExit('H32R20_FAIL_CLOSED: root/experiments missing')
    out,lines=report(root,root/'experiments'/'H32')
    print('\n'.join(lines))
    print('H32R20_DONE='+str(out))

if __name__=='__main__':main()
