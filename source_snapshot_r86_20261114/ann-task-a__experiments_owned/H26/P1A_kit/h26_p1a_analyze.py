#!/usr/bin/env python3
"""Summarize H26-P1a distance subphase profiling without mixing worker sums and wall."""
import argparse
import pathlib
import statistics
import json
import re
import sys
KEYS=['buffers_worker_ns','copy_worker_ns','norm_zero_worker_ns','rankupdate_worker_ns','finalize_worker_ns']
NAMES=['Buffer setup','Point copy','Norm + zero','Eigen rankUpdate','Distance finalize']
def parse(p):
    raw=p.read_text(errors='replace')
    m=dict(re.findall(r'^H26P1A,([^,]+),(.+)$',raw,re.M))
    h=dict(re.findall(r'^H26_PROFILE,([^,]+),(.+)$',raw,re.M))
    if m.get('version')!='H26_P1A_v1':raise RuntimeError(f'no P1a report in {p}')
    if h.get('selector')!='top2':raise RuntimeError(f'not Top-2 run in {p}')
    values={k:int(m[k])/1e9 for k in KEYS}
    values['calls']=int(m['calls'])
    values['p0_dist_worker_s']=int(h['dist_worker_ns'])/1e9
    values['p0_select_worker_s']=int(h['select_worker_ns'])/1e9
    values['p0_merge_worker_s']=int(h['merge_worker_ns'])/1e9
    values['leaves']=int(h['leaf_count'])
    # Read GNU time elapsed in numeric m:ss / h:mm:ss format; from end
    times=re.findall(r'Elapsed \(wall clock\) time \(h:mm:ss or m:ss\):\s*(\S+)',raw)
    values['process_wall_s_no_graph_output']=None
    if times:
        ns=[float(x) for x in times[-1].split(':')]
        val=0
        for x in ns:val=val*60+x
        values['process_wall_s_no_graph_output']=val
    return values

def main():
    p=argparse.ArgumentParser();p.add_argument('--out',type=pathlib.Path,required=True); a=p.parse_args()
    files=sorted(a.out.glob('p1a_r*_top2.log'))
    if len(files)<2:raise RuntimeError('Need two or more Top-2 P1a logs')
    rows=[parse(f) for f in files]
    for r in rows:
        if r['calls']!=r['leaves'] or r['leaves']!=85529:
            raise RuntimeError(f'Bad leaf count {r["calls"]}, {r["leaves"]}; expected 85529 for this SIFT1M run')
    med={k:statistics.median(x[k] for x in rows) for k in rows[0] if k != 'process_wall_s_no_graph_output'}
    med['process_wall_s_no_graph_output']=statistics.median(x['process_wall_s_no_graph_output'] for x in rows)
    total=sum(med[k] for k in KEYS)
    report=['H26-P1a DISTANCE SUBPHASES: worker elapsed sum (not BUILD wall)',f'RUNS={len(rows)} LEAVES_PER_RUN={rows[0]["leaves"]}',f'P1A_SAMPLED_DIST_WORKER_SUM={total:.3f}s vs P0_OUTER_DIST={med["p0_dist_worker_s"]:.3f}s',f'PROCESS_WALL_MEDIAN_NO_GRAPH_OUTPUT={med["process_wall_s_no_graph_output"]:.3f}s']
    report.extend(f'{name:<22} {med[k]:>9.3f}s {med[k]/total*100:>6.2f}%' for name,k in zip(NAMES,KEYS))
    report+=['P0 selection and merge still measured separately (not subphase split):',f'P0_SELECT_WORKER_S={med["p0_select_worker_s"]:.3f} P0_MERGE_WORKER_S={med["p0_merge_worker_s"]:.3f}', 'DIAGNOSTIC ONLY; P1a timestamps introduce instrumentation overhead; graph output intentionally disabled.', 'NO performance/Pareto/novelty claim from P1a data.']
    (a.out/'h26_p1a_summary.txt').write_text('\n'.join(report)+'\n')
    (a.out/'h26_p1a_summary.json').write_text(json.dumps({'runs':rows,'median':med,'worker_dist_subphase_sum_s':total},indent=2)+'\n')
    print('\n'.join(report))

if __name__=='__main__':
    try:main()
    except Exception as exc:print('H26P1A_FAIL_CLOSED:',exc,file=sys.stderr);sys.exit(2)
