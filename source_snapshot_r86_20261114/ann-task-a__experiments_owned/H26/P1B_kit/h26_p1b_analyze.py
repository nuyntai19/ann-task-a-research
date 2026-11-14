#!/usr/bin/env python3
"""Parse H26-P1b leaf-size histogram, fail closed on disagreement with P0/P1a counters."""
import argparse, re, sys, json, statistics
from pathlib import Path

BINS=['2-63','64-127','128-255','256-383','384-511','512-767','768-1023','1024-1535','1536+']
EXPECTED_LEAVES=85529
EXPECTED_ROWS=29995085

def parse(p):
    text=p.read_text(errors='replace')
    p1a=dict(re.findall(r'^H26P1A,([^,]+),([^\r\n]+)$',text,re.M))
    p0=dict(re.findall(r'^H26_PROFILE,([^,]+),([^\r\n]+)$',text,re.M))
    version=re.findall(r'^H26P1B,version,([^\r\n]+)$',text,re.M)
    if version != ['H26_P1B_v1']:raise ValueError(f'No unique P1b marker: {p}')
    if p1a.get('version')!='H26_P1A_v1':raise ValueError(f'P1a version missing: {p}')
    if p0.get('selector')!='top2':raise ValueError(f'Not top2: {p}')
    rows=[]
    for line in re.findall(r'^H26P1B,bin,[^\r\n]+$',text,re.M):
        parts=line.split(',')
        if len(parts)!=9:raise ValueError(f'Malformed P1b bin row: {line}')
        tag,typ,label,*values=parts
        if tag!='H26P1B' or typ!='bin': raise ValueError('Bad tag')
        rows.append({'bin':label,'leaves':int(values[0]), 'rows':int(values[1]),
                     'pairs':int(values[2]),'pair_dims':int(values[3]),
                     'rank_ns':int(values[4]), 'dist_ns':int(values[5])})
    if [r['bin'] for r in rows]!=BINS:
        raise ValueError(f'Histogram bins or ordering wrong: {[r["bin"] for r in rows]}')
    total=lambda key:sum(r[key] for r in rows)
    if total('leaves')!=EXPECTED_LEAVES or total('rows')!=EXPECTED_ROWS:
        raise ValueError(f'Unexpected leaf/row sums in {p}: {total("leaves")}, {total("rows")}')
    if total('leaves')!=int(p1a['calls']) or total('leaves')!=int(p0['leaf_count']):
        raise ValueError('P1a/P0 leaf counters disagree')
    if total('rows')!=int(p0['rows']):raise ValueError('P0 row counter disagrees')
    if abs(total('rank_ns')-int(p1a['rankupdate_worker_ns']))>1:
        raise ValueError(f'Rank histogram/P1a mismatch: {total("rank_ns")}, {p1a["rankupdate_worker_ns"]}')
    p1a_total=sum(int(p1a[k]) for k in ['buffers_worker_ns','copy_worker_ns','norm_zero_worker_ns','rankupdate_worker_ns','finalize_worker_ns'])
    if abs(total('dist_ns')-p1a_total)>100:
        raise ValueError(f'Distance histogram/P1a mismatch: {total("dist_ns")}, {p1a_total}')
    return {'log':p.name,'bins':rows,'rank_worker_ns':total('rank_ns'),
            'dist_worker_ns':total('dist_ns'),'leaves':total('leaves'),
            'rows':total('rows'), 'pair_dims_proxy':total('pair_dims')}

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--out',type=Path,required=True);args=ap.parse_args()
    files=sorted(args.out.glob('p1b_r*_top2.log'))
    if len(files)<2:raise ValueError('At least two P1b logs needed')
    runs=[parse(p) for p in files]
    median=[]
    for idx,label in enumerate(BINS):
        r={'bin':label}
        for key in ['leaves','rows','pairs','pair_dims','rank_ns','dist_ns']:
            r[key]=statistics.median(run['bins'][idx][key] for run in runs)
        median.append(r)
    total_rank=sum(r['rank_ns'] for r in median)
    total_leaves=sum(r['leaves'] for r in median)
    total_proxy=sum(r['pair_dims'] for r in median)
    if total_rank <= 0:raise ValueError('Zero rankUpdate work measured')
    lines=['H26-P1b — SIZE-STRATIFIED EIGEN rankUpdate DIAGNOSTIC',
           f'RUNS={len(runs)} | LEAVES_PER_RUN={runs[0]["leaves"]} | ROWS_PER_RUN={runs[0]["rows"]}',
           f'MEDIAN_TOTAL_RANK_WORKER_S={total_rank/1e9:.3f} (sum of per-bin medians)',
           'Worker elapsed sums only. Pair-dimension counts are FLOP PROXIES, not measured floating-point operations.',
           '',
           f'{"LEAF SIZE":<13}{"LEAVES":>10}{"LEAF %":>10}{"RANK s":>12}{"RANK %":>10}{"PAIR-DIM %":>13}{"US/LEAF":>12}']
    for r in median:
        lines.append(f'{r["bin"]:<13}{r["leaves"]:>10.0f}{100*r["leaves"]/total_leaves:>9.2f}%'
          f'{r["rank_ns"]/1e9:>12.3f}{100*r["rank_ns"]/total_rank:>9.2f}%'
          f'{100*r["pair_dims"]/total_proxy if total_proxy else 0:>12.2f}%'
          f'{r["rank_ns"]/r["leaves"]/1e3 if r["leaves"] else 0:>12.2f}')
    lines += ['', 'CONCLUSION RULE: find dominant size bins first; do not infer memory vs compute bound from this timing alone.',
              'NOT performance/quality/novelty evidence. P1b adds histogram atomics AFTER timed regions and does not write graphs.']
    (args.out/'h26_p1b_summary.txt').write_text('\n'.join(lines)+'\n')
    (args.out/'h26_p1b_summary.json').write_text(json.dumps({'runs':runs,'median_bins':median,
                  'median_rank_worker_s':total_rank/1e9,
                  'bin_median_warning':'These are medians per-bin; their sum is not the median per-run total.'},indent=2)+'\n')
    print('\n'.join(lines))

if __name__=='__main__':
    try:main()
    except Exception as e:print('H26P1B_FAIL_CLOSED:',e,file=sys.stderr);sys.exit(2)
