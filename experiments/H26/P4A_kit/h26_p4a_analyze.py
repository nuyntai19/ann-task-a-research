#!/usr/bin/env python3
"""Analyze H26-P4a LEAF EXECUTION ENVELOPES, not true critical-path causality."""
import argparse, collections, csv, json, math, pathlib, re, statistics, sys

FIELDS=['start_ns','end_ns','dist_ns','select_ns','merge_ns','leaf_size','worker_token']

def percentile(v,p):
    if not v:return None
    s=sorted(v); f=(len(s)-1)*p/100; i=int(f); j=min(i+1,len(s)-1)
    return s[i]+(s[j]-s[i])*(f-i)

def gini(v):
    if not v or sum(v)==0:return None
    s=sorted(v);n=len(v);return sum((2*i-n-1)*x for i,x in enumerate(s,1))/(n*sum(s))

def parse_log(p):
    s=p.read_text(errors='replace')
    def metric(name):
        m=re.findall(r'^H26_PROFILE,'+re.escape(name)+r',([^\n]+)',s,re.M)
        if len(m)!=1:raise ValueError(f'{p}: missing/duplicated H26_PROFILE {name}')
        return int(m[0])
    d={k:metric(k) for k in ['leaf_count','rows','proposals','dist_worker_ns','select_worker_ns','merge_worker_ns']}
    mt=re.search(r'Parlay time: build leaf time: ([0-9.]+)',s)
    mb=re.search(r'Parlay time: buckets time: ([0-9.]+)',s)
    mp=re.search(r'Parlay time: Final prune time: ([0-9.]+)',s)
    wall=re.search(r'Elapsed \(wall clock\) time \(h:mm:ss or m:ss\):\s*([^\n]+)',s)
    if not all([mt,mb,mp,wall]):raise ValueError(f'{p}: phase timer or GNU time missing')
    x=wall.group(1).strip().split(':')
    wt=sum(float(v)*60**i for i,v in enumerate(x[::-1]))
    trace=re.findall(r'^H26P4_TRACE,enabled,([01])$',s,re.M)
    if len(trace)!=1:raise ValueError(f'{p}: missing trace enabled status')
    return {**d,'trace':int(trace[0]),'leaf_phase_wall_s':float(mt.group(1)),
            'buckets_wall_s':float(mb.group(1)),'final_prune_wall_s':float(mp.group(1)),
            'process_wall_s_includes_csv_flush':wt}

def parse_csv(p, log):
    ev=[]
    with p.open(newline='') as f:
        r=csv.DictReader(f)
        if r.fieldnames!=FIELDS:raise ValueError(f'{p}: unexpected CSV fields {r.fieldnames}')
        for row in r:
            z={k:int(row[k]) for k in FIELDS}
            if z['start_ns']<=0 or z['end_ns']<=z['start_ns'] or z['leaf_size']<2:
                raise ValueError('Invalid event interval or size')
            measured=z['dist_ns']+z['select_ns']+z['merge_ns']
            if abs(z['end_ns']-z['start_ns']-measured)>3:
                raise ValueError('Event interval does not match component timers')
            ev.append(z)
    if len(ev)!=log['leaf_count']:raise ValueError(f'Event count mismatch {len(ev)} vs {log["leaf_count"]}')
    if sum(e['leaf_size'] for e in ev)!=log['rows']:raise ValueError('Row total mismatch')
    for key,source in [('dist_ns','dist_worker_ns'),('select_ns','select_worker_ns'),('merge_ns','merge_worker_ns')]:
        if sum(e[key] for e in ev)!=log[source]:
            raise ValueError(f'Counter mismatch {key} vs {source}; check trace completeness')
    start=min(e['start_ns'] for e in ev);end=max(e['end_ns'] for e in ev)
    span=(end-start)/1e9
    durations=[(e['end_ns']-e['start_ns'])/1e6 for e in ev]
    worker=collections.defaultdict(list)
    points=[]
    for e in ev:
        worker[e['worker_token']].append(e)
        points.append((e['start_ns'],1)); points.append((e['end_ns'],-1))
    # End events before start on exact timestamps to avoid false maximum concurrency.
    points.sort(key=lambda p:(p[0],p[1]))
    active=0;peak=0;last=points[0][0];covered=collections.defaultdict(int)
    for t,inc in points:
        if t>last:covered[active]+=t-last
        active+=inc
        if active<0:raise ValueError('Negative active event count')
        peak=max(peak,active);last=t
    if active!=0:raise ValueError('Events not closed')
    assert sum(covered.values())==end-start
    workers=[]
    for tid,ss in sorted(worker.items()):
        ss.sort(key=lambda a:a['start_ns'])
        if any(a['end_ns']>b['start_ns'] for a,b in zip(ss,ss[1:])):
            raise ValueError(f'Overlapping leaf calls on same thread token {tid}')
        workers.append({'token':tid,'leaf_count':len(ss),
          'elapsed_sum_s':sum(e['end_ns']-e['start_ns'] for e in ss)/1e9,
          'first_start_offset_s':(ss[0]['start_ns']-start)/1e9,
          'last_end_offset_s':(ss[-1]['end_ns']-start)/1e9})
    total=sum(durations)/1000
    counts={str(k):round(v/(end-start)*100,3) for k,v in sorted(covered.items())}
    tailn=max(1,math.ceil(len(ev)*0.01));largest=sorted(durations,reverse=True)[:tailn]
    return {
        'events':len(ev),'worker_thread_tokens_observed':len(workers),
        'leaf_envelope_span_s':span,'leaf_elapsed_sum_s':total,
        'average_concurrent_leaf_calls':total/span,
        'maximum_concurrent_leaf_calls':peak,
        'concurrency_time_pct_by_active_leaf_count':counts,
        'leaf_duration_ms_quantiles':{f'p{p}':round(percentile(durations,p),5) for p in (50,90,95,99,99.9)},
        'max_leaf_elapsed_ms':max(durations),
        'longest_one_percent_leaf_share_of_elapsed_sum_pct':100*sum(largest)/(1000*total),
        'worker_leaf_elapsed_gini':gini([w['elapsed_sum_s'] for w in workers]),
        'workers':workers,
        'WARNING':'Observed leaf execution envelope and thread tokens, not CPU busy time, true DAG critical path or graph-lock wait. A high concurrency count may include blocked threads.'
    }

def analyze(directory):
    files=sorted(directory.glob('r*.log'))
    if not files:raise ValueError('No logs found')
    runs=[]
    for log in files:
        m=re.fullmatch(r'r([12])_([124])t_(on|off)\.log',log.name)
        if not m:raise ValueError('Unexpected log name '+log.name)
        round_,threads,enabled=int(m[1]),int(m[2]),m[3]=='on'
        d=parse_log(log)
        if d['trace']!=int(enabled):raise ValueError('trace mismatch '+str(log))
        if d['leaf_count']!=85529 or d['rows']!=29995085 or d['proposals']!=59990170:
            raise ValueError('Unexpected per-build counts in '+str(log))
        result={'run':log.stem,'round':round_,'threads':threads,'trace':enabled,'metrics':d}
        if enabled:result['trace_summary']=parse_csv(log.with_suffix('.csv'),d)
        runs.append(result)
    groups={}
    for r in runs:groups[(r['threads'],r['trace'],r['round'])]=r
    for round_ in (1,2):
        if (4,False,round_) not in groups or (4,True,round_) not in groups:
            raise ValueError('Missing 4t on/off paired control for round '+str(round_))
    diffs=[]
    for round_ in (1,2):
        a=groups[(4,False,round_)]['metrics'];b=groups[(4,True,round_)]['metrics']
        diffs.append({'round':round_,
          'build_leaf_wall_trace_overhead_pct':100*(b['leaf_phase_wall_s']/a['leaf_phase_wall_s']-1),
          'process_wall_with_csv_flush_pct':100*(b['process_wall_s_includes_csv_flush']/a['process_wall_s_includes_csv_flush']-1)})
    traced=[r for r in runs if r['trace']]
    summary={
      'study':'H26_P4A_OBSERVED_LEAF_EXECUTION_ENVELOPE_NOT_TRUE_CRITICAL_PATH',
      'data':{'n':1000000,'base':'SIFT1M','expected_leaves':85529,'threads_4_cpuset':'0,2,4,6'},
      'runs':runs,'paired_4thread_instrumentation_overhead':diffs,
      'critical_path_not_proven':['No dependency DAG edges or true span','No per-lock acquire latency yet','Thread elapsed includes scheduler deschedule and blocking','1t/2t scaling if present has one replication','CSV flush contributes to process wall on traced runs','No graph output, Recall/QPS/Pareto not tested']
    }
    out=directory/'h26_p4a_summary.json';out.write_text(json.dumps(summary,indent=2,ensure_ascii=False)+'\n')
    lines=['H26-P4a: LEAF TIMELINE / PARALLELISM AUDIT — DIAGNOSTIC ONLY',
           'NO exact critical path or per-vertex lock contention measured.',
           'Graph output disabled; wall on trace includes CSV flush at exit.',
           '--- 4-thread instrumentation on/off comparisons ---']
    for rr in diffs:
        lines.append(f"round={rr['round']}: leaf wall overhead={rr['build_leaf_wall_trace_overhead_pct']:+.2f}%; process wall(+CSV)={rr['process_wall_with_csv_flush_pct']:+.2f}%")
    lines.append('--- traced runs ---')
    for r in sorted(traced,key=lambda q:(q['round'],-q['threads'])):
        m=r['metrics'];t=r['trace_summary']
        lines.append(f"{r['run']}: threads={r['threads']} leaf_phase_wall={m['leaf_phase_wall_s']:.3f}s, trace_envelope={t['leaf_envelope_span_s']:.3f}s, elapsed_sum={t['leaf_elapsed_sum_s']:.3f} worker-s; avg concurrent leaf calls={t['average_concurrent_leaf_calls']:.3f}, max={t['maximum_concurrent_leaf_calls']}, distinct thread tokens={t['worker_thread_tokens_observed']}")
        lines.append(f"  leaf ms p50={t['leaf_duration_ms_quantiles']['p50']:.3f}, p99={t['leaf_duration_ms_quantiles']['p99']:.3f}; longest 1% of leaves carry {t['longest_one_percent_leaf_share_of_elapsed_sum_pct']:.2f}% of elapsed work; worker load Gini={t['worker_leaf_elapsed_gini']:.4f}")
        lines.append('  concurrency_pct='+str(t['concurrency_time_pct_by_active_leaf_count']))
        lines.append('  per_thread_elapsed_s='+str({w['token']:round(w['elapsed_sum_s'],3) for w in t['workers']}))
    lines.append('ATTENTION: high avg concurrency is NOT CPU utilization; merge stage includes both lock wait and work.')
    lines.append('DECISION: if 4t saturation low or load skew strong, profile scheduler and tail; if merge expensive, proceed to low-rate lock acquisition sampling with overhead control.')
    (directory/'h26_p4a_summary.txt').write_text('\n'.join(lines)+'\n')
    print('\n'.join(lines));print('OUTPUT:',out)

def main():
    p=argparse.ArgumentParser();p.add_argument('--dir',required=True);a=p.parse_args()
    analyze(pathlib.Path(a.dir))
if __name__=='__main__':
    try:main()
    except Exception as e:print('H26P4A_FAIL_CLOSED:',e,file=sys.stderr);sys.exit(2)
