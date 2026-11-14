#!/usr/bin/env python3
"""H24-R1a: OFFLINE counterfactual row-transplant feasibility test.

Does NOT implement STH, true oracle-optimal selection, harvest or real repair.
Uses existing R0f Dense LOW/HIGH graphs; runs common R0f searcher for each hybrid.
Never builds Dense graphs or writes to H17-H23; no overwrite of existing artifacts.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import statistics
import subprocess
import sys

BASE=Path.home()/"ann-task-a"
PCTS=(1,2,5,10)
POLICIES=("hindsight","random","degree_matched_random")
EFS=(60,100,140,200,300)
EVAL_RE=re.compile(r'^RESULT\s+(.*)$',re.M)
GENERATE_RE=re.compile(r'^RESULT\s+(.*)$',re.M)

def sha256(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for ch in iter(lambda:f.read(4*1024*1024),b''):h.update(ch)
    return h.hexdigest()

def decode(line):
    obj={}
    for tok in line.strip().split():
        if '=' not in tok:continue
        k,v=tok.split('=',1)
        try: obj[k]=float(v) if '.' in v else int(v)
        except ValueError:obj[k]=v
    return obj

def parse_eval(path,efs=EFS):
    raw=path.read_text(errors="replace")
    rows=[decode(x) for x in EVAL_RE.findall(raw)]
    if len(rows)!=len(efs)*2:raise RuntimeError(f"Wrong row count in {path}: {len(rows)}")
    out={}
    for ef in efs:
        part=[x for x in rows if x.get('ef')==ef]
        if len(part)!=2 or part[0]['hits']!=part[1]['hits'] or part[0]['distances']!=part[1]['distances']:
            raise RuntimeError(f"Nondeterministic/missing search at ef={ef} in {path}")
        out[str(ef)]={'recall10':part[0]['recall10'], 'qps_median':round(statistics.median(x['qps'] for x in part),2),'dist_per_query':part[0]['dist_per_query']}
    return out

def do_cmd(cmd,log):
    if log.exists():raise RuntimeError(f"Refuse to overwrite log: {log}")
    with log.open('w') as f:
        f.write('# CMD '+ ' '.join(map(str,cmd))+'\n');f.flush()
        ret=subprocess.run(list(map(str,cmd)),stdout=f,stderr=subprocess.STDOUT)
    if ret.returncode:raise RuntimeError(f"Command failed; inspect: {log}")

def check_sources(out):
    comp=json.loads((out/'comparison.json').read_text())
    assert comp['n']==1000000 and comp['nq']==1000
    for name in ('low','high'):
        p=out/f'{name}.graph'
        if not p.exists():raise RuntimeError(f"Missing R0f graph: {p}")
        got=sha256(p);expected=comp['graph'][name]['sha256']
        if got!=expected:raise RuntimeError(f"R0f {name} graph SHA mismatch, STOP")
    for f in ('gold10.rawi32','entries_1.rawu32','search_low_entry1.log','search_high_entry1.log','h24_r0f_common_search'):
        if not (out/f).exists():raise RuntimeError(f"Missing R0f artifact: {f}")
    return comp

def report(base,out,comp):
    low=parse_eval(base/'search_low_entry1.log', efs=(60,100,140,200,300,400))
    high=parse_eval(base/'search_high_entry1.log', efs=(60,100,140,200,300,400))
    metrics=[]
    for policy in POLICIES:
        for pct in PCTS:
            stem=f'{policy}_p{pct}'
            meta=out/f'{stem}.generator.log';loge=out/f'{stem}.search.log'
            if not meta.exists() or not loge.exists():continue
            m=GENERATE_RE.findall(meta.read_text())
            if len(m)!=1:raise RuntimeError(f"Malformed generator log: {meta}")
            mm=decode(m[0]);vals=parse_eval(loge)
            rec={"policy":policy,"percent":pct,"selected":mm['selected'],"edges":mm['edges'],"reach_entry0":mm['reach_entry0'],"zero_indeg":mm['zero_indeg'],"high_only_edges_in_selected":mm['high_only_edges_in_selected'],"metrics":{}}
            for ef in EFS:
                key=str(ef);L=low[key];H=high[key];V=vals[key];d=H['recall10']-L['recall10']
                rec['metrics'][key]={'recall':V['recall10'],'qps':V['qps_median'],'dist_per_query':V['dist_per_query'],'recovery_fraction':round((V['recall10']-L['recall10'])/d,4) if d>0 else None,'baseline_low':L['recall10'],'baseline_high':H['recall10']}
            metrics.append(rec)
    obj={"study":"H24_R1A_ROW_TRANSPLANT_NOT_REAL_STH_OR_TRUE_OPTIMAL_ORACLE","date":"2026-10-26","input_graphs":{a:comp['graph'][a]['sha256'] for a in ('low','high')},"baseline_low":low,"baseline_high":high,"results":metrics,
         "limitations":["Hindsight policy reads both LOW/HIGH graphs; not an online cheap predictor.","Ranks by number of high-only outgoing neighbors, NOT true per-node causal contribution or optimal oracle.","Row replacements can delete LOW edges and need not preserve symmetrization, cap/spine or actual BUILD provenance.","Search quality can decrease non-monotonically; no causality attribution to a specific replacement edge.","Only one SIFT1M seed and 1000 external queries, no held-out cross-corpus validation.","Query QPS results are from R0f independent 1-thread search, not native paper searcher; discrete ef, unmatched index size.","No BUILD time for transplant included: this is a diagnostic, not construction algorithm."]}
    dest=out/'report.json'
    if dest.exists():
        old=json.loads(dest.read_text())
        if old['input_graphs']!=obj['input_graphs']:raise RuntimeError("Existing report refers to different graph inputs")
    dest.write_text(json.dumps(obj,indent=2,ensure_ascii=False))
    print('\n===== H24 R1a recovered Recall-gap fraction (entry1) =====')
    print('Policy              p%    Reachability   ef100          ef140           ef200')
    for r in metrics:
        f=lambda ef: ('%.1f%%'%(100*r['metrics'][str(ef)]['recovery_fraction'])) if r['metrics'][str(ef)]['recovery_fraction'] is not None else 'n/a'
        print(f"{r['policy']:<21}{r['percent']:>2}   {r['reach_entry0']}/{1000000}    {f(100):>8}       {f(140):>8}       {f(200):>8}")
    print('\nNo GO claim: these are diagnostic row transplants, not STH harvest.')
    print('Saved:',dest)

def main():
    a=argparse.ArgumentParser(description=__doc__)
    a.add_argument('--mode', choices=['plan','run','inspect','selftest'],default='plan')
    a.add_argument('--project-dir',type=Path,default=BASE)
    a.add_argument('--phase', choices=['pilot','full'], default='pilot', help='pilot: 5%%/10%% hindsight+random, full: all 12 configurations')
    args=a.parse_args()
    project=args.project_dir.resolve()
    kit=project/'experiments/H24/kit'
    base=project/'experiments/H24/r0f_common_search_sift1m_seed42'
    out=project/'experiments/H24/r1a_row_transplant_sift1m_seed42'
    print(f'Mode={args.mode}\nR0f baseline={base}\nNew output={out}')
    if args.mode=='selftest':
        assert round((151.53/1.15-91.39),4)==40.3752
        assert decode('RESULT policy=random percent=1 selected=10000 reach_entry0=999999')['reach_entry0']==999999
        print('Python selftest PASS');return
    if not base.exists():raise RuntimeError('Missing R0f study directory')
    comp=check_sources(base)
    if args.mode=='plan':
        print('Verified SHA of BOTH R0f graphs. No BUILD, no output. Baseline search retained.')
        for p in POLICIES:print(p,':',','.join(str(x)+'%' for x in PCTS))
        return
    if args.mode=='inspect':
        if not out.exists():raise RuntimeError('No R1a output')
        report(base,out,comp);return
    # run; strict source guard, independent output, memory+disk check.
    from shutil import disk_usage
    if disk_usage(out.parent).free < 3*1024**3:raise RuntimeError('Require >=3GiB free output disk space')
    if Path('/proc/meminfo').exists():
        mm=re.search(r'^MemAvailable:\s+(\d+)\s+kB',Path('/proc/meminfo').read_text(),re.M)
        if mm and int(mm.group(1))<3*1024*1024:raise RuntimeError('Need >=3GiB available RAM')
    source=kit/'h24_r1_generate.cpp';binary=out/'h24_r1_generate'
    if not source.exists():raise RuntimeError('Missing generator C++ source. Re-extract ZIP')
    out.mkdir(parents=True,exist_ok=True)
    if not binary.exists():
        subprocess.run(['g++','-O3','-std=c++17','-march=native',str(source),'-o',str(binary)],check=True)
    elif binary.stat().st_mtime < source.stat().st_mtime:
        raise RuntimeError('Generator source newer than existing binary. Stop, inspect before changing outputs.')
    policies=('hindsight','random') if args.phase=='pilot' else POLICIES
    pcts=(5,10) if args.phase=='pilot' else PCTS
    for p in policies:
      for pct in pcts:
        stem=f'{p}_p{pct}'
        graph=out/f'{stem}.graph'
        loggen=out/f'{stem}.generator.log'
        logeval=out/f'{stem}.search.log'
        if not graph.exists():
            if loggen.exists():raise RuntimeError(f'Generation log exists but graph absent: {loggen}; inspect partial output first')
            print('Generate hybrid',stem,flush=True)
            do_cmd([binary,'--low',base/'low.graph','--high',base/'high.graph','--policy',p,'--percent',pct,'--prefix',out/stem,'--seed',20261026],loggen)
        else:
            if not loggen.exists() or not (out/f'{stem}.selected.u32').exists():raise RuntimeError(f'Graph exists but provenance incomplete: {graph}')
            print('Reusing graph',graph)
        if not logeval.exists():
            print('Evaluate common-search',stem,flush=True)
            do_cmd([base/'h24_r0f_common_search','--graph',graph,'--base',project/'data/sift1m.fbin',
                    '--queries',project/'data/sift1m_queries.fbin','--gold',base/'gold10.rawi32',
                    '--entries',base/'entries_1.rawu32','--nq',1000,'--k',10,'--repeats',2,
                    '--tag',stem,'--efs',*EFS],logeval)
        else:print('Reusing eval',logeval)
    report(base,out,comp)

if __name__=='__main__':
    try:main()
    except Exception as exc:
        print('H24-R1a STOP:',exc,file=sys.stderr);sys.exit(2)
