#!/usr/bin/env python3
"""Paired BUILD-only diagnostics, no quality or novelty claims."""
from pathlib import Path
import argparse, re, statistics as st, json, sys
FIELDS=('dist_worker_ns','select_worker_ns','merge_worker_ns','leaf_count','rows','proposals','top2_checks')

def parse(path):
    s=path.read_text()
    o={}
    for line in s.splitlines():
        if line.startswith('H26_PROFILE,'):
            t=line.split(',',2)
            if len(t)==3:o[t[1]]=t[2]
        if line.startswith('H26P3B,'):
            t=line.split(',',2)
            if len(t)==3:o['p3b_'+t[1]]=t[2]
    if 'Elapsed (wall clock) time (h:mm:ss or m:ss):' not in s:raise RuntimeError(f'{path}: process wall missing')
    wall=re.search(r'Elapsed \(wall clock\) time \(h:mm:ss or m:ss\):\s*(\d+):(\d+(?:\.\d+)?)',s)
    if not wall:raise RuntimeError(f'{path}: wall format unexpected')
    o['wall_s']=60*int(wall.group(1))+float(wall.group(2))
    for k in FIELDS:
        if k not in o:raise RuntimeError(f'{path}: missing counter {k}')
        o[k]=int(o[k])
    if o['leaf_count']!=85529 or o['rows']!=29995085 or o['proposals']!=59990170:
        raise RuntimeError(f'{path}: build work-count mismatch')
    if o.get('selector') not in ('top2','fused'):raise RuntimeError(f'{path}: unknown selector')
    if o['selector']=='fused':
        if o.get('p3b_version')!='H26_P3B_v1' or int(o.get('p3b_fused_rows','0'))!=29995085:
            raise RuntimeError(f'{path}: expected complete fused coverage')
    else:
        if int(o.get('p3b_fused_rows','0'))!=0:raise RuntimeError(f'{path}: top2 used fused path')
    for field in ['buckets time','build leaf time','Final prune time']:
        a=re.search(r'Parlay time: '+re.escape(field)+r':\s*([\d.]+)',s)
        o[field.replace(' ','_')+'_s']=float(a.group(1)) if a else None
    for k in ('dist_worker_ns','select_worker_ns','merge_worker_ns'):
        o[k.replace('_ns','_s')]=o[k]/1e9
    o['log']=path.name
    return o

def analyze(out):
    logs=sorted(out.glob('r*_*.log'))
    if not logs:raise RuntimeError('No run logs')
    values=[parse(p) for p in logs]
    rounds={}
    for v in values:
        m=re.fullmatch(r'r(\d+)_(top2|fused)\.log',v['log'])
        if m is None:raise RuntimeError(f'unexpected log name {v["log"]}')
        r=int(m.group(1));policy=m.group(2)
        rounds.setdefault(r,{})
        if policy in rounds[r]:raise RuntimeError(f'duplicate run {v["log"]}')
        rounds[r][policy]=v
    for r,both in rounds.items():
        if set(both)!=set(('top2','fused')):raise RuntimeError(f'round {r} incomplete')
    if len(rounds)<2:raise RuntimeError('at least 2 rounds required')
    metrics=['wall_s','build_leaf_time_s','buckets_time_s','Final_prune_time_s','dist_worker_s','select_worker_s','merge_worker_s']
    medians={}
    paired={}
    for k in metrics:
        ordered=[[r[k] for r in rounds[rd].values()] for rd in sorted(rounds)]
        if any(v is None for l in ordered for v in l):continue
        x=[rounds[rd]['top2'][k] for rd in sorted(rounds)]
        y=[rounds[rd]['fused'][k] for rd in sorted(rounds)]
        medians[k]={'top2':st.median(x),'fused':st.median(y),'change_pct':100*(st.median(y)/st.median(x)-1)}
        paired[k]=[100*(b/a-1) for a,b in zip(x,y)]
    lines=[
        'H26-P3b FUSED PACK+TOP2 — CONTROLLED PILOT (NOT novelty)',
        f'ROUNDS={len(rounds)} | 4-thread SIFT1M | same instrumented binary, alternating order',
        'No graph output; graph/Recall/QPS correctness NOT established here.',
        'Distances, leaf counts, rows and directed proposals verified unchanged.',
        '',
        f'{"METRIC":<24}{"TOP2 median":>16}{"FUSED median":>16}{"change":>12}   paired changes by round'
    ]
    for k in metrics:
        if k not in medians:continue
        d=medians[k]
        lines.append(f'{k:<24}{d["top2"]:>16.3f}{d["fused"]:>16.3f}{d["change_pct"]:>+11.2f}%   '+', '.join(f'{v:+.2f}%' for v in paired[k]))
    lines.extend(['','CAVEATS: only BUILD-process profile (no graph output), no 10k-query quality or topology equivalence yet.',
                  'A streaming packed Top2 loop is a standard implementation optimization, not an ANN contribution.',
                  'Cross-round noise, P0 source instrumentation and sampled preflight semantics limit conclusions.'])
    text='\n'.join(lines)+'\n'
    (out/'h26_p3b_summary.txt').write_text(text)
    (out/'h26_p3b_summary.json').write_text(json.dumps({'study':'H26_P3B_FUSED_IMPLEMENTATION_PILOT','rounds':rounds,'medians':medians,'paired_changes_pct':paired,'runs':values},indent=2))
    print(text,end='')

if __name__=='__main__':
    try:
        p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True)
        args=p.parse_args();analyze(args.out)
    except Exception as e:
        print('H26P3B_FAIL_CLOSED:',e,file=sys.stderr)
        sys.exit(2)
