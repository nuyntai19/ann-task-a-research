#!/usr/bin/env python3
"""Analyze sampled selection subphase counters, warn about selection timing overhead."""
from pathlib import Path
import argparse,json,re,statistics,sys

STAGES=['pack_ns','selector_ns','emit_ns']
NEED=['sample_mod','sampled_leaves','sampled_rows','sampled_candidates','outer_select_ns']+STAGES

def parse(path):
    src=path.read_text(errors='replace')
    p=dict(re.findall(r'^H26P3A,([^,]+),(.+)$',src,re.M))
    outer=dict(re.findall(r'^H26_PROFILE,([^,]+),(.+)$',src,re.M))
    if p.get('version')!='H26_P3A_v1':raise RuntimeError(f'Missing P3A version: {path}')
    if outer.get('selector')!='top2':raise RuntimeError(f'Wrong selector: {path}')
    result={k:int(p[k]) for k in NEED}
    result.update({'leaf_count':int(outer['leaf_count']), 'all_rows':int(outer['rows']),
                   'all_selection_ns':int(outer['select_worker_ns']),
                   'all_dist_ns':int(outer['dist_worker_ns']),
                   'all_merge_ns':int(outer['merge_worker_ns']),
                   'all_proposals':int(outer['proposals'])})
    if result['leaf_count']!=85529 or result['all_rows']!=29995085 or result['all_proposals']!=59990170:
        raise RuntimeError(f'Unexpected SIFT1M shape: {path}')
    if result['sampled_leaves']<200 or result['sampled_rows']<40000:
        raise RuntimeError(f'Sample too small: {path}')
    if result['sampled_candidates']<=result['sampled_rows']:
        raise RuntimeError('Invalid sampled candidate count')
    times=re.findall(r'Elapsed \(wall clock\) time \(h:mm:ss or m:ss\):\s*(\S+)',src)
    if times:
        parts=list(map(float,times[-1].split(':')))
        wall=0
        for part in parts:wall=wall*60+part
        result['process_wall_no_graph_s']=wall
    return result

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--out',required=True,type=Path);a=ap.parse_args()
    files=sorted(a.out.glob('p3a_r*_top2.log'))
    if len(files)<2:raise RuntimeError('Need 2 or more runs')
    runs=[parse(f) for f in files]
    mods={r['sample_mod'] for r in runs}
    if len(mods)!=1:raise RuntimeError('Mixed sample mods cannot be pooled')
    med={k:statistics.median(r[k] for r in runs) for k in runs[0]}
    ss=sum(med[k] for k in STAGES)
    outer=med['outer_select_ns']
    if ss <=0 or outer <=0:raise RuntimeError('Invalid timing sum')
    names=['Q assembly (clear + pack)','Top-2 scan','Proposal materialization']
    report=[
      'H26-P3a — SAMPLED TOP-2 SELECTION SUBPHASES — DIAGNOSTIC',
      'All stage durations are SAMPLE worker elapsed sums (NOT BUILD wall).',
      f'RUNS={len(runs)} MOD={int(med["sample_mod"])} SAMPLE_LEAVES={int(med["sampled_leaves"])} / {int(med["leaf_count"])}',
      f'SAMPLE_ROWS={int(med["sampled_rows"])} / {int(med["all_rows"])}',
      f'SAMPLED_CANDIDATES={int(med["sampled_candidates"])}',
      f'SAMPLED_OUTER_SELECTION={outer/1e9:.5f}s  SUM_COMPONENT_TIMERS={ss/1e9:.5f}s',
      f'TIMER_AND_NONSTAGE_GAP={(outer-ss)/1e9:.5f}s ({(outer-ss)/outer*100:.2f}% of sampled outer selection)',
    ]
    for name,k in zip(names,STAGES):
        report.append(f'{name:<31} {med[k]/1e9:>10.5f}s {100*med[k]/ss:>7.2f}% (sample share)')
    report.extend([
      f'P0_WHOLE_SELECTION_WORKER={med["all_selection_ns"]/1e9:.3f}s (this instrumented run)',
      f'PROCESS_WALL_NO_GRAPH={med.get("process_wall_no_graph_s",0):.3f}s',
      'CAVEATS: only sampled leaves have detailed timers; sampling based on leaf content, not random repeated execution.',
      'Per-row timer overhead may inflate stage durations. No speedup or graph-quality claim.',
      'Do not extrapolate sample percentages to whole BUILD unless validated across sampling mods/seeds.',
    ])
    (a.out/'h26_p3a_summary.txt').write_text('\n'.join(report)+'\n')
    data={'runs':runs,'median':med, 'sample_stage_share':{k: med[k]/ss for k in STAGES},
          'instrumentation_gap_fraction':(outer-ss)/outer}
    (a.out/'h26_p3a_summary.json').write_text(json.dumps(data,indent=2)+'\n')
    print('\n'.join(report))

if __name__=='__main__':
    try:main()
    except Exception as exc:print('H26P3A_FAIL_CLOSED:',exc,file=sys.stderr);sys.exit(2)
