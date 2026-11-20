#!/usr/bin/env python3
"""Read-only, graph-SHA-reverified, compact R90-P0A-v1.2 evidence bundle.

This script neither BUILDs nor SEARCHes. It never modifies source/binaries/graphs
or existing experiment files. It only creates one new .tar.gz under $HOME.
Graph bytes are SHA-rehashed (NOT archived). Includes exact 24 run records,
24 stdout, 24 /usr/bin/time -v, and six ON R86 counter JSONL files.
"""
from __future__ import annotations
import argparse, collections, hashlib, io, json, os, re, statistics, sys, tarfile
from pathlib import Path

HOME=Path.home()
ROOT=HOME/'ann-task-a/experiments/R90/r90_p0a_v12_pinned_six_elf_full1m_buildonly'
LOG=HOME/'R90_P0A_V12_PINNED_SIX_ELF_BUILDONLY.log'
OUTPUT=HOME/'R90_P0A_V12_NATIVE_EVIDENCE_EXPORT_v1.tar.gz'
EXPECTED_AUDIT='dd90ce5c892e88235c1b611809ca9d2b43801ecd6d887ccb0f0ae75c49718f97'
EXPECTED_RUNNER='cd696087b03135699b4272357964f840f6148d9fe818b65c31a37064d122fabc'
EXPECTED_LOG='720d04ecb5ab00ad25a05f449c65468a84b743db4a5f2257ed741d6404c9d43d'
TAG='R90_P0A_V12_EVIDENCE_EXPORT_V1'

def need(cond,msg):
    if not cond:raise RuntimeError(TAG+'_HOLD_'+msg)

def sha(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda:f.read(4*1024*1024),b''):h.update(b)
    return h.hexdigest()

def source(p,limit=64*1024*1024):
    p=Path(p)
    need(p.is_file() and not p.is_symlink(),'MISSING_OR_SYMLINK_'+p.name)
    need(p.stat().st_size<=limit,'INPUT_TOO_LARGE_'+p.name)
    return p

def jread(p):return json.loads(source(p).read_text())

def name(j):return f"{j['dataset']}_{j['arm']}_{j['mode']}_r{j['rep']}"

def expected_names():
    return {f'{d}_{a}_{m}_r{r}' for d in ('SIFT1M','MS-Turing1M')
       for a in ('stock','h17','fast') for m in ('off','on')
       for r in ((1,2,3) if m=='off' else (1,))}

def parse_elapsed(t):
    m=re.search(r'^\s*Elapsed \(wall clock\) time \(h:mm:ss or m:ss\):\s*(\S+)',t,re.M)
    if not m:return None
    vals=m.group(1).split(':')
    try:
        need(len(vals) in (2,3),'INVALID_ELAPSED_SHAPE')
        vals=[float(x) for x in vals]
        if len(vals)==2:return vals[0]*60+vals[1]
        return vals[0]*3600+vals[1]*60+vals[2]
    except (ValueError,OverflowError):return None

def metric(t,key):
    pat=r'^\s*'+re.escape(key)+r':\s*(\d+)\s*$'
    m=re.search(pat,t,re.M)
    return int(m.group(1)) if m else None

def time_metrics(t):
    return {'elapsed_wall_seconds':parse_elapsed(t),
        'maxrss_KiB':metric(t,'Maximum resident set size (kbytes)'),
        'major_page_faults':metric(t,'Major (requiring I/O) page faults'),
        'minor_page_faults':metric(t,'Minor (reclaiming a frame) page faults'),
        'involuntary_context_switches':metric(t,'Involuntary context switches'),
        'voluntary_context_switches':metric(t,'Voluntary context switches'),
        'user_cpu_s':_float(t,'User time (seconds)'),
        'system_cpu_s':_float(t,'System time (seconds)')}

def _float(t,key):
    m=re.search(r'^\s*'+re.escape(key)+r':\s*([0-9.]+)\s*$',t,re.M)
    return float(m.group(1)) if m else None

def parse_stages(txt):
    res={}
    for key,lab in [('buckets','buckets time'),('leaf','build leaf time'),('prune','Final prune time')]:
        vals=[]
        for ln in txt.splitlines():
            if lab.lower() not in ln.lower():continue
            m=re.search(r'(?i)'+re.escape(lab)+r'\s*[:=]?\s*([0-9]+(?:\.[0-9]+)?)',ln)
            if not m:m=re.search(r'([0-9]+(?:\.[0-9]+)?)\s*(?:s\s*)?'+re.escape(lab),ln,re.I)
            if m:vals.append(float(m.group(1)))
        res[key+'_stage_seconds']=sum(vals) if len(vals)==(1 if key=='prune' else 2) else None
        res[key+'_stage_line_count']=len(vals)
    vals=[int(x) for x in re.findall(r'^\s*# of comparisons during clustering:\s*(\d+)\s*$',txt,re.M)]
    res['clustering_comparisons_final']=vals[-1] if len(vals)==2 else None
    return res

def selftest():
    assert len(expected_names())==24
    t='Elapsed (wall clock) time (h:mm:ss or m:ss): 0:35.45\n\tMaximum resident set size (kbytes): 123456\n\tMajor (requiring I/O) page faults: 0\n'
    assert time_metrics(t)['elapsed_wall_seconds']==35.45
    assert time_metrics(t)['maxrss_KiB']==123456
    assert time_metrics(t)['major_page_faults']==0
    assert parse_stages('buckets time: 3\nbuckets time: 4\nbuild leaf time: 5\nbuild leaf time: 6\nFinal prune time: 2\n')['leaf_stage_seconds']==11
    print(TAG+'_SELFTEST_PASS_24_JOBS_TIME_STAGE_PARSER_NO_BUILD_NO_SEARCH',flush=True)

def add(tf,p,alias):
    p=source(p)
    need(p.stat().st_size<=32*1024*1024,'ARCHIVE_MEMBER_OVER32M_'+p.name)
    tf.add(str(p),arcname=alias,recursive=False)

def main_export():
    need(ROOT.is_dir() and not ROOT.is_symlink(),'PROJECT_ROOT_MISSING_OR_SYMLINK')
    need(not OUTPUT.exists() and not OUTPUT.is_symlink(),'OUTPUT_EXISTS_NO_OVERWRITE')
    tmp=OUTPUT.with_suffix(OUTPUT.suffix+'.part')
    need(not tmp.exists() and not tmp.is_symlink(),'PART_EXISTS_NO_OVERWRITE')
    prereg=jread(ROOT/'preregister.json')
    full=jread(ROOT/'full1m_manifest.json')
    audit=jread(ROOT/'audit1m_buildonly.json')
    need(sha(ROOT/'audit1m_buildonly.json')==EXPECTED_AUDIT,'AUDIT_SHA_DIVERGED')
    need(prereg['runner_sha256']==EXPECTED_RUNNER,'RUNNER_SHA_DIVERGED')
    need(audit['full_manifest_sha256']==sha(ROOT/'full1m_manifest.json'),'MANIFEST_SHA_DIVERGED')
    need(audit['status']=='NATIVE_24_GRAPH_SHA_STRUCTURE_PASS__SEARCH_RECALL_QPS_NOT_MEASURED','AUDIT_STATUS_DRIFT')
    need(full['status']=='OFF18_ON6_BUILT_PENDING_GRAPH_STRUCTURE_AND_QUERY_QUALITY','FULL_STATUS_DRIFT')
    need(len(prereg['jobs'])==len(full['runs'])==len(audit['runs'])==24,'NOT_24_ENTRIES')
    need(sha(source(LOG))==EXPECTED_LOG,'ORIGINAL_LOG_SHA_DRIFT')
    indexes={}
    for j in audit['runs']:
        n=j['name'];need(n not in indexes,'AUDIT_DUPLICATE_NAME');indexes[n]=j
    need(set(indexes)==expected_names(),'AUDIT_JOB_SET_NOT_EXPECTED')
    members=[(ROOT/'preregister.json','preregister.json'),
             (ROOT/'full1m_manifest.json','full1m_manifest.json'),
             (ROOT/'audit1m_buildonly.json','audit1m_buildonly.json'),
             (ROOT/'compile_manifest.json','compile_manifest.json'),
             (LOG,'original_native.log')]
    output=[]
    for spec,rec in zip(prereg['jobs'],full['runs']):
        n=name(spec);need(n in indexes,'MISSING_RUN_'+n)
        au=indexes[n]
        need((rec['dataset'],rec['arm'],rec['mode'],rec['rep'],rec['threads'])==(spec['dataset'],spec['arm'],spec['mode'],spec['rep'],spec['cpu']),'FIELDS_'+n)
        need((au['arm'],au['mode'],au['dataset'])==(rec['arm'],rec['mode'],rec['dataset']),'AUDIT_FIELDS_'+n)
        need(au['graph']['sha256']==rec['graph_sha'] and rec['elf_sha']==au['original_elf_sha'],'GRAPH_ELF_AUDIT_SHA_'+n)
        # Exact graph byte hash: separate independent rehash for all 24 NEW graphs.
        graph=Path(rec['graph']);need(graph.parent==ROOT/'graphs' and graph.name==n+'.graph','GRAPH_PATH_'+n)
        need(graph.is_file() and not graph.is_symlink(),'GRAPH_MISSING_OR_SYMLINK_'+n)
        need(sha(graph)==rec['graph_sha'],'GRAPH_BYTES_SHA_'+n)
        rp=ROOT/(n+'.json')
        need(jread(rp)==rec,'SINGLE_RUN_RECORD_'+n)
        members.append((rp,'runs/'+n+'.json'))
        for typ,suffix in [('stdout','.stdout'),('timefile','.time')]:
            p=Path(rec[typ]);need(p.parent==ROOT/'logs' and p.name==n+suffix,'LOG_PATH_'+typ+'_'+n)
            source(p);need(sha(p)==rec[typ+'_sha'],'LOG_SHA_'+typ+'_'+n)
            members.append((p,'logs/'+p.name))
        st=Path(rec['stdout']).read_text(errors='replace')
        tt=Path(rec['timefile']).read_text(errors='replace')
        metrics=time_metrics(tt)
        need(metrics['elapsed_wall_seconds'] is not None and metrics['maxrss_KiB'] is not None,'TIMEFILE_REQUIRED_METRICS_'+n)
        need(rec['NOT_A_TIMING_COMPARISON']==(rec['mode']=='on'),'ON_TIMING_FLAG_'+n)
        if rec['mode']=='on':
            p=ROOT/'logs'/(n+'.counters.jsonl')
            source(p)
            need(sha(p)==rec['r86_work_jsonl_sha'],'COUNTER_SHA_'+n)
            members.append((p,'counters/'+p.name))
        work={k:v for k,v in rec.items() if k.startswith('stock_') or k=='d6_counter_line'}
        output.append({'name':n,'dataset':rec['dataset'],'arm':rec['arm'],
            'mode':rec['mode'],'rep':rec['rep'],'threads':rec['threads'],
            'graph_sha256':rec['graph_sha'],'arcs':au['graph']['arcs'],
            'time':metrics,'stages':parse_stages(st),'work_from_original_record':work,
            'not_valid_for_timing':rec['NOT_A_TIMING_COMPARISON']})
    need(len(output)==24,'OUTPUT_COUNT')
    summary={'status':'INDEPENDENT_REHASH_24_GRAPH_AND_24_STDOUT_TIME_6_ON_COUNTERS_PASS__SEARCH_NOT_RUN',
             'source_audit_sha256':EXPECTED_AUDIT,'original_native_log_sha256':EXPECTED_LOG,
             'full_manifest_sha256':sha(ROOT/'full1m_manifest.json'),
             'all_graphs_rehashed':True,'runs':output,
             'limitations':['OFF wall and RSS are native /usr/bin/time values, not CPU-instruction counts.',
                            'ON timing diagnostic only; never compare ON to OFF for speed.',
                            'Stock Highway comparator and move counts NOT_MEASURED.',
                            'Graph audit native duplicates tested on 1024 sampled rows, not full 1M.',
                            'No per-graph Recall/QPS measured on newly built 1M graphs.']}
    blob=(json.dumps(summary,indent=2,sort_keys=True,ensure_ascii=False)+'\n').encode()
    members.sort(key=lambda x:x[1])
    need(len(members)==5+24+48+6,'MEMBER_COUNT')
    try:
        with tarfile.open(tmp,'w:gz',compresslevel=6) as tf:
            for p,arc in members:add(tf,p,'R90_P0A_V12_EVIDENCE/'+arc)
            info=tarfile.TarInfo('R90_P0A_V12_EVIDENCE/derived_summary.json')
            info.size=len(blob);info.mode=0o644;info.mtime=0
            tf.addfile(info,io.BytesIO(blob))
        os.replace(tmp,OUTPUT)
    except BaseException:
        if tmp.exists():tmp.unlink()
        raise
    print(TAG+'_PASS_24_GRAPH_ORIGINAL_BYTES_24_TIMES_24_STDOUT_SIX_COUNTER_SHA',flush=True)
    for ds in ('SIFT1M','MS-Turing1M'):
        for arm in ('stock','h17','fast'):
            vals=[x for x in output if x['dataset']==ds and x['arm']==arm and x['mode']=='off']
            ms=[x['time']['elapsed_wall_seconds'] for x in vals]
            rss=[x['time']['maxrss_KiB'] for x in vals]
            faults=[x['time']['major_page_faults'] for x in vals]
            print('EVIDENCE_MEAN_OFF',ds,arm,'wall_s',round(statistics.mean(ms),4),
                'maxRSS_KiB_mean',round(statistics.mean(rss),1),
                'major_faults_per_rep',faults,flush=True)
    print(TAG+'_OUTPUT',OUTPUT,'sha256',sha(OUTPUT),'bytes',OUTPUT.stat().st_size,flush=True)
    print(TAG+'_NO_BUILD_NO_SEARCH_NO_ORIGINAL_INPUT_WRITE',flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('phase',choices=['selftest','export']);arg=parser.parse_args()
    try:
        if arg.phase=='selftest':selftest()
        else:main_export()
    except Exception as ex:
        print(TAG+'_ERROR',repr(ex),file=sys.stderr,flush=True)
        raise SystemExit(2)
