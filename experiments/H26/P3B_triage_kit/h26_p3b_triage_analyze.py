#!/usr/bin/env python3
"""Strict three-arm comparison: H26 P0 top2 vs P3b top2 vs P3b fused."""
import argparse, json, re, statistics as st, sys
from pathlib import Path
ARMS=['p0_top2','p3b_top2','p3b_fused']
METRICS=['wall_s','leaf_wall_s','dist_worker_s','select_worker_s','merge_worker_s']
COUNTS={'leaf_count':85529, 'rows':29995085, 'proposals':59990170}

def parse(p,arm):
    s=p.read_text(errors='replace')
    d={}
    for line in s.splitlines():
        if line.startswith('H26_PROFILE,'):
            z=line.split(',',2)
            if len(z)==3:d[z[1]]=z[2]
        if line.startswith('H26P3B,'):
            z=line.split(',',2)
            if len(z)==3:d['p3b_'+z[1]]=z[2]
    expected='fused' if arm=='p3b_fused' else 'top2'
    if d.get('selector')!=expected:raise ValueError(f'{p.name}: selector mismatch')
    if d.get('version')!='H26_P0_v1':raise ValueError(f'{p.name}: instrumentation mismatch')
    for k,val in COUNTS.items():
        if int(d.get(k,'-1'))!=val:raise ValueError(f'{p.name}: {k} mismatch')
    if int(d.get('top2_checks','-1'))!=0:raise ValueError(f'{p.name}: timed validation enabled')
    if arm=='p3b_fused':
        if int(d.get('p3b_fused_leaves','-1'))!=85529 or int(d.get('p3b_fused_rows','-1'))!=29995085:
            raise ValueError(f'{p.name}: incomplete fused coverage')
    elif arm=='p3b_top2':
        if int(d.get('p3b_fused_rows','0'))!=0:raise ValueError(f'{p.name}: top2 unexpectedly fused')
    m=re.search(r'Elapsed \(wall clock\) time \(h:mm:ss or m:ss\):\s*(\d+):([\d.]+)',s)
    if not m:raise ValueError(f'{p.name}: no wall time')
    out={'wall_s':int(m.group(1))*60+float(m.group(2))}
    leaf=re.search(r'Parlay time: build leaf time:\s*([\d.]+)',s)
    if leaf is None:raise ValueError(f'{p.name}: no leaf phase time')
    out['leaf_wall_s']=float(leaf.group(1))
    for k in ('dist','select','merge'):
        out[k+'_worker_s']=int(d[k+'_worker_ns'])/1e9
    return out

def analyze(out):
    data={}
    for rd in (1,2,3):
        data[str(rd)]={}
        for arm in ARMS:
            path=out/f'r{rd}_{arm}.log'
            if not path.is_file():raise ValueError(f'missing {path}')
            data[str(rd)][arm]=parse(path,arm)
    comparisons=[]
    for other,base in [('p3b_top2','p0_top2'),('p3b_fused','p0_top2'),('p3b_fused','p3b_top2')]:
        tab={}
        for metric in METRICS:
            seq=[100*(data[str(rd)][other][metric]/data[str(rd)][base][metric]-1) for rd in (1,2,3)]
            tab[metric]={'pct_by_round':seq,'median_paired_pct':st.median(seq)}
        comparisons.append({'other':other,'base':base,'values':tab})
    med={arm:{metric:st.median([data[str(rd)][arm][metric] for rd in (1,2,3)]) for metric in METRICS} for arm in ARMS}
    lines=[
      'H26-P3b CONTROL TRIAGE — SAME SIFT1M, NO GRAPH OUTPUT, BALANCED ORDER',
      'Preflight: sampled Fused-vs-Highway only. Not complete equivalence, no graph quality gate.',
      '3 arms: P0-original top2 / P3b binary top2 / P3b binary fused.',
      'Instrumented worker sums NOT BUILD wall. Do not claim novelty.', '',
      f'{"ARM":<16}{"wall(s)":>10}{"leaf(s)":>11}{"dist-worker":>14}{"select-worker":>16}{"merge-worker":>15}',
    ]
    for arm in ARMS:
        v=med[arm]
        lines.append(f'{arm:<16}{v["wall_s"]:>10.3f}{v["leaf_wall_s"]:>11.3f}{v["dist_worker_s"]:>14.3f}{v["select_worker_s"]:>16.3f}{v["merge_worker_s"]:>15.3f}')
    lines.append('')
    for comp in comparisons:
        lines.append(f'{comp["other"]} vs {comp["base"]}:')
        for metric in ('wall_s','leaf_wall_s','select_worker_s','dist_worker_s'):
            v=comp['values'][metric]
            by=', '.join(f'{x:+.2f}%' for x in v['pct_by_round'])
            lines.append(f'  {metric:<18} round gains [{by}] ; median paired {v["median_paired_pct"]:+.2f}%')
    lines += ['',
       'DECISION RULE: If P3b-top2 slows materially vs P0-top2, original P3b fused-vs-top2 gain is confounded by control-path regression.',
       'If fused ~= P0 on wall+selection, H26-P3b has no validated benefit over optimized baseline.',
       'Different binaries/compiler codegen: triangulation, not proof of exact causal attribution.',
       'Graph/Recall/QPS NOT checked. Full semantic identity NOT proven.']
    (out/'triage_summary.txt').write_text('\n'.join(lines)+'\n')
    (out/'triage_summary.json').write_text(json.dumps({'runs':data,'arm_medians':med,'comparisons':comparisons},indent=2)+'\n')
    print('\n'.join(lines))

if __name__=='__main__':
    try:
        ap=argparse.ArgumentParser();ap.add_argument('--out',type=Path,required=True)
        analyze(ap.parse_args().out)
    except Exception as e:
        print('H26TRIAGE_FAIL_CLOSED',repr(e),file=sys.stderr);sys.exit(2)
