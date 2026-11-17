#!/usr/bin/env python3
"""H32-R20b: bounded, source-preserving targeted H19 memory-log audit.
Read-only input. New timestamped summary/json output. No ANN BUILD/SEARCH.
"""
from __future__ import annotations
import argparse, hashlib, json, os, re, statistics, tempfile
from pathlib import Path
from datetime import datetime

REL='experiments/H19/phase2_perf_scaling'
WORKERS=(1,2,4)
N_REP=3
LOGMAX=8*1024*1024
SUMMAX=12*1024*1024
RSS_RE=re.compile(r'(?i)^\s*(?:Maximum resident set size\s*\(\s*kbytes\s*\)|VmHWM|ru_maxrss|peak\s*RSS|max(?:imum)?\s*RSS)\s*[:=]\s*(\d[\d,]*)\s*(?:kB|KiB)?\s*$')
STAT_RE=re.compile(r'(?i)(maximum resident set size|VmHWM|ru_maxrss|peak[_ \-]?rss|page faults|swaps|swap[ _\-]?(?:in|out)|MemAvailable|MemTotal|RSS|minor faults|major faults)')
EXPECTED={1:1714432,2:1758336,4:1849076}

def safe_file(base:Path, p:Path, max_size:int):
    try:
        if p.is_symlink() or not p.is_file():return False,'NOT_REGULAR_FILE_OR_SYMLINK'
        st=p.stat()
        if st.st_size>max_size:return False,'TOO_LARGE'
        if not p.resolve().is_relative_to(base.resolve()):return False,'OUTSIDE_BASE'
        return True,''
    except (OSError,ValueError):return False,'INACCESSIBLE'

def parse_exact_log(base,p):
    good,problem=safe_file(base,p,LOGMAX)
    if not good:return {'path':str(p),'status':problem}
    content=p.read_text(encoding='utf-8',errors='replace').splitlines()
    lines=[];candidate=[]
    for k,line in enumerate(content,1):
        if len(line)>8000: continue
        if STAT_RE.search(line):
            lines.append({'line':k,'text':line.strip()[:280]})
            m=RSS_RE.fullmatch(line.strip())
            if m:
                candidate.append({'line':k,'rss_kib':int(m.group(1).replace(',','')),'raw':line.strip()})
    # A single exact per-repetition value is required. Two counters in one file are ambiguous.
    verified=candidate[0]['rss_kib'] if len(candidate)==1 else None
    return {'path':str(p),'status':'READ','sha256':hashlib.sha256(p.read_bytes()).hexdigest(),
            'n_matching_stat_lines':len(lines),'relevant_lines':lines[:100],
            'strict_rss_candidates':candidate,'unambiguous_peak_rss_kib':verified}

def run(root, out_root):
    base=root/REL
    if not base.is_dir():raise SystemExit('H32R20B_FAIL_CLOSED: Missing '+str(base))
    manifest=[]; observed={}; counts={}
    for w in WORKERS:
        rss=[];status=[]
        for rep in range(1,N_REP+1):
            p=base/f'w{w}_rep{rep}.log'
            item=parse_exact_log(base,p)
            item.update({'worker':w,'rep':rep})
            manifest.append(item);status.append(item['status'])
            if item.get('unambiguous_peak_rss_kib') is not None:rss.append(item['unambiguous_peak_rss_kib'])
        counts[w]={'strict_rss_parsed':len(rss),'file_status':status}
        observed[w]=int(statistics.median(rss)) if len(rss)==3 else None
    summary=base/'summary.json'
    s_ok,s_err=safe_file(base,summary,SUMMAX)
    sj={'path':str(summary),'status': 'READ' if s_ok else s_err}
    if s_ok:
        content=summary.read_text(encoding='utf-8',errors='replace')
        sj['sha256']=hashlib.sha256(summary.read_bytes()).hexdigest()
        try:
            data=json.loads(content)
            sj['json_root_type']=type(data).__name__
            sj['top_keys']=(list(data)[:75] if isinstance(data,dict) else [])
            sj['content_excerpt']=content[:4000]
        except json.JSONDecodeError:
            sj['json_invalid']=True
            sj['content_excerpt']=content[:2000]
    info={
       'status':'TARGETED_H19_R20B_READONLY', 'root':str(root),'focus':str(base),
       'no_build_no_search_no_graph_change':True,'no_pipnn_ii_run':True,
       'historical_doc_medians_kib':EXPECTED,'strict_log_medians_kib':observed,
       'all_nine_logs_strict_single_rss':all(counts[w]['strict_rss_parsed']==3 for w in WORKERS),
       'strict_median_match_existing_doc':all(observed[w]==EXPECTED[w] for w in WORKERS),
       'per_worker_completeness':counts,'exact_nine_logs':manifest,'summary_json':sj,
       'interpretation': 'Historical RSS source line check only; historical MemAvailable/swap/OOM cannot be inferred from current meminfo. Blank/unparsed counters do not establish zero usage.'
    }
    out=out_root/f'H32_R20b_{datetime.now().strftime("%Y%m%d_%H%M%S_%f")}'
    out.mkdir(parents=True,exist_ok=False)
    (out/'h32_r20b_report.json').write_text(json.dumps(info,ensure_ascii=False,indent=2),encoding='utf-8')
    lines=['H32-R20b | TARGETED H19 MEMORY EVIDENCE AUDIT',
       'OVERALL=PASS_TARGETED_READONLY_AUDIT', 'NO BUILD / NO ANN SEARCH / NO GRAPH CHANGE',
       'H19_LOG_DIR='+str(base),'READ_SUMMARY_JSON='+str(sj['status']),
       'R20_PREVIOUS_SCAN_3000_FILES_WARNING=AVOIDED_BY_EXACT_9_LOG_PATHS']
    for w in WORKERS:
        lines += [f'H19_{w}T_STRICT_LOGS_READ={counts[w]["strict_rss_parsed"]}/3',
                  f'H19_{w}T_STRICT_MEDIAN_MAXRSS_KIB={observed[w] if observed[w] is not None else "UNVERIFIED_FROM_LOG_LINES"}',
                  f'H19_{w}T_DOC_HISTORICAL_MEDIAN_KIB={EXPECTED[w]}']
    lines += ['STRICT_LOG_MEDIANS_ALL_MATCH_DOC='+('YES' if info['strict_median_match_existing_doc'] else 'NOT_VERIFIED'),
     'MEMORY_PRESSURE_DURING_BUILD=NOT_PROVEN_BY_RSS_ONLY',
     'NO_PIPNN_II_FAIR_BENCHMARK_DONE',
     'REPORT_JSON='+str(out/'h32_r20b_report.json'),
     'R20B_DONE='+str(out)]
    (out/'h32_r20b_summary.txt').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    return '\n'.join(lines)

def selftest():
    with tempfile.TemporaryDirectory() as td:
        root=Path(td)/'proj';base=root/REL;base.mkdir(parents=True)
        fake={1:[1714431,1714432,1714433],2:[1758335,1758336,1758337],4:[1849075,1849076,1849077]}
        for w in WORKERS:
            for i,v in enumerate(fake[w],1):
                (base/f'w{w}_rep{i}.log').write_text(f'Maximum resident set size (kbytes): {v}\nMajor page faults: 0\n',encoding='utf-8')
        (base/'summary.json').write_text('{"workload":"synthetic"}',encoding='utf-8')
        # Populate the H17 dir to prove that H19 is not hidden by a global scan cap.
        h17=root/'experiments/H17';h17.mkdir()
        for i in range(3010):(h17/f'fake_{i}.txt').write_text('noise')
        res=run(root,root/'experiments/H32')
        assert 'STRICT_LOG_MEDIANS_ALL_MATCH_DOC=YES' in res
        assert 'READ_SUMMARY_JSON=READ' in res
        (base/'w1_rep1.log').write_text('VmHWM: 1 kB\nVmHWM: 2 kB\n')
        again=run(root,root/'experiments/H32')
        assert 'STRICT_LOG_MEDIANS_ALL_MATCH_DOC=NOT_VERIFIED' in again
    print('H32R20B_SYNTHETIC_SELFTEST_PASS (NO REAL UBUNTU LOGS READ)')

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--mode',required=True,choices=['selftest','audit']);ap.add_argument('--root',default=str(Path.home()/'ann-task-a'))
    a=ap.parse_args()
    if a.mode=='selftest':selftest();return
    root=Path(a.root).expanduser().resolve()
    if not (root/'experiments').is_dir():raise SystemExit('H32R20B_FAIL_CLOSED: experiments missing')
    print(run(root,root/'experiments/H32'))
if __name__=='__main__':main()
