#!/usr/bin/env python3
"""Aggregate H26-P0 native BUILD phase traces; do not infer ANN novelty or Pareto."""
import argparse, csv, json, pathlib, re, statistics, sys

EXPECTED = ['version','selector','dist_worker_ns','select_worker_ns','merge_worker_ns','leaf_count','rows','proposals','top2_checks','scope']

def parse_time(s):
    parts=s.strip().split(':')
    try:
        if len(parts)==3: h,m,secs=parts;return int(h)*3600+int(m)*60+float(secs)
        if len(parts)==2: m,secs=parts;return int(m)*60+float(secs)
        return float(parts[0])
    except ValueError: return None

def parse(p):
    s=p.read_text(errors='replace')
    d={}
    for key,value in re.findall(r'^H26_PROFILE,([^,\n]+),([^\n]+)',s,re.M):
        if key in d:raise ValueError('duplicated H26 metric '+key+' in '+str(p))
        d[key]=value.strip()
    missing=[key for key in EXPECTED if key not in d]
    if missing:raise ValueError('missing H26 profiler lines '+str(missing)+' in '+str(p))
    if d['scope']!='worker_elapsed_sum_NOT_build_wall':raise ValueError('unexpected timing scope')
    time=re.search(r'Elapsed \(wall clock\) time \(h:mm:ss or m:ss\):\s*([^\n]+)',s)
    rss=re.search(r'Maximum resident set size \(kbytes\):\s*(\d+)',s)
    if not time: raise ValueError('missing GNU time in '+str(p))
    secs=parse_time(time.group(1));assert secs is not None
    stages={i: int(d[i]) / 1e9 for i in ('dist_worker_ns','select_worker_ns','merge_worker_ns')}
    stage_sum=sum(stages.values())
    result={
      'file':p.name, 'selector':d['selector'], 'total_process_wall_s_includes_graph_output':secs,
      'max_rss_kb': int(rss.group(1)) if rss else None,
      'dist_worker_s':stages['dist_worker_ns'],
      'select_worker_s':stages['select_worker_ns'],
      'merge_worker_s':stages['merge_worker_ns'],
      'instrumented_worker_sum_s':stage_sum,
      'dist_share_of_instrumented_worker':stages['dist_worker_ns']/stage_sum if stage_sum else None,
      'select_share_of_instrumented_worker':stages['select_worker_ns']/stage_sum if stage_sum else None,
      'merge_share_of_instrumented_worker':stages['merge_worker_ns']/stage_sum if stage_sum else None,
      'leaf_count':int(d['leaf_count']), 'rows':int(d['rows']), 'directed_proposals':int(d['proposals']),
      'top2_checks_in_timed_run':int(d['top2_checks']),
    }
    return result

def main():
    p=argparse.ArgumentParser();p.add_argument('--dir',required=True);a=p.parse_args()
    folder=pathlib.Path(a.dir)
    logs=sorted(folder.glob('r*_*.log'))
    if not logs:raise ValueError('no r*_*.log in '+str(folder))
    records=[parse(p) for p in logs]
    modes={r['selector'] for r in records}
    if modes!={'stock','top2'}:raise ValueError('need both stock and top2; found '+str(modes))
    report={
      'study':'H26_P0_PIPNN_PHASE_DIAGNOSIS_NOT_PARETO',
      'caution':'worker-stage time sums are NOT overall BUILD wall; total process wall includes graph writing; stock/top2 comparison is a reimplementation, not independently verified user H17 binary',
      'records':records,
      'summary_by_mode':{},
    }
    metrics=['total_process_wall_s_includes_graph_output','dist_worker_s','select_worker_s','merge_worker_s','instrumented_worker_sum_s','dist_share_of_instrumented_worker','select_share_of_instrumented_worker','merge_share_of_instrumented_worker','max_rss_kb']
    for mode in ['stock','top2']:
        rr=[r for r in records if r['selector']==mode]
        report['summary_by_mode'][mode]={
          'n_builds':len(rr),
          'medians':{k:statistics.median([r[k] for r in rr if r[k] is not None]) for k in metrics},
          'leaf_counts':sorted(set(r['leaf_count'] for r in rr)),
          'rows':sorted(set(r['rows'] for r in rr)),
          'directed_proposals':sorted(set(r['directed_proposals'] for r in rr))}
    a0=report['summary_by_mode']['stock']['medians']
    b0=report['summary_by_mode']['top2']['medians']
    delta={}
    for k in metrics:
        if a0[k] != 0:delta[k]=100*(b0[k]/a0[k]-1)
    report['top2_minus_stock_percent_of_medians']=delta
    report['hypotheses_not_proved']=['quality equivalence of independent native builds', 'novelty', 'Pareto', 'parallel overhead costs of any new design', 'CPU cycle-level stage attribution', 'statistical significance with few builds']
    (folder/'h26_summary.json').write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n')
    with (folder/'h26_runs.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(records[0].keys()));w.writeheader();w.writerows(records)
    lines=['H26-P0 BUILD profiling — DIAGNOSTIC ONLY',
           'worker stage durations are summed across parallel leaves, not additive BUILD wall.',
           'total process wall includes graph-writing and any harness overhead.',
           'mode          n       process_wall_s     dist_worker_s  select_worker_s  merge_worker_s  select_share',]
    for mode in ['stock','top2']:
        m=report['summary_by_mode'][mode];v=m['medians'];lines.append(f'{mode:8s} {m["n_builds"]:4d} {v["total_process_wall_s_includes_graph_output"]:19.3f} {v["dist_worker_s"]:17.3f} {v["select_worker_s"]:16.3f} {v["merge_worker_s"]:15.3f} {v["select_share_of_instrumented_worker"]*100:11.2f}%')
    lines.append(f'Top2 vs stock median process wall change: {delta.get("total_process_wall_s_includes_graph_output",float("nan")):+.2f}%')
    lines.append(f'Top2 vs stock median selection worker change: {delta.get("select_worker_s",float("nan")):+.2f}%')
    lines.append('NO claim about H17 equivalence, graph quality or Pareto before independent graph/search verification.')
    (folder/'h26_summary.txt').write_text('\n'.join(lines)+'\n')
    print('\n'.join(lines))
    print('OUTPUT:', folder/'h26_summary.json')

if __name__=='__main__':
    try:main()
    except Exception as e:print('H26_FAIL_CLOSED:',e,file=sys.stderr);sys.exit(2)
