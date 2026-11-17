#!/usr/bin/env python3
"""H26-P4b: sampled lock wait vs hold + CPU process telemetry; no causal claims."""
import argparse, csv, json, pathlib, re, statistics, sys, collections, math

def quant(values,p):
    if not values:return 0.
    xs=sorted(values);i=(len(xs)-1)*p/100; lo=int(i);hi=min(lo+1,len(xs)-1)
    return xs[lo]+(xs[hi]-xs[lo])*(i-lo)

def parse_log(path):
    raw=path.read_text(errors='replace')
    def single(pattern,description):
        z=re.findall(pattern,raw,re.M)
        if len(z)!=1:raise ValueError(f'{path}: expected one {description}, got {len(z)}')
        return z[0]
    z={k:int(single(r'^H26_PROFILE,'+k+r',([0-9]+)$',k)) for k in ('leaf_count','rows','proposals','dist_worker_ns','select_worker_ns','merge_worker_ns')}
    if (z['leaf_count'],z['rows'],z['proposals'])!=(85529,29995085,59990170):raise ValueError('Wrong dataset/graph proposal counts')
    for name,pattern in [('leaf_wall_s',r'Parlay time: build leaf time: ([0-9.]+)'),('buckets_wall_s',r'Parlay time: buckets time: ([0-9.]+)'),('prune_wall_s',r'Parlay time: Final prune time: ([0-9.]+)')]:
        z[name]=float(single(pattern,name))
    rawclock=single(r'Elapsed \(wall clock\) time \(h:mm:ss or m:ss\):\s*([^\n]+)','GNU wall time').strip()
    z['process_wall_s']=sum(float(v)*60**i for i,v in enumerate(rawclock.split(':')[::-1]))
    for key,text in [('user_cpu_s','User time (seconds)'),('sys_cpu_s','System time (seconds)'),('vcs','Voluntary context switches'),('ivcs','Involuntary context switches'),('rss_kb','Maximum resident set size (kbytes)')]:
        match=re.escape(text)
        z[key]=float(single(r'^\s*'+match+r':\s*([0-9.]+)',key))
    z['process_cpu_ratio']=(z['user_cpu_s']+z['sys_cpu_s'])/z['process_wall_s']
    z['trace_enabled']=int(single(r'^H26P4B_LOCK,enabled,([01])$', 'trace enabled')) if 'H26P4B_LOCK,enabled' in raw else None
    if z['trace_enabled']==1:
        z['samples']=int(single(r'^H26P4B_LOCK,samples,([0-9]+)$','samples'))
        z['sample_mod']=int(single(r'^H26P4B_LOCK,sample_mod,([0-9]+)$','sample mod'))
    return z

def parse_csv(path,expected):
    w=[];h=[]; ids=[]; workers=set();n=0
    with path.open(newline='') as fp:
        r=csv.DictReader(fp)
        if r.fieldnames!=['wait_ns','hold_ns','vertex','worker']:raise ValueError('Wrong sample CSV schema '+str(r.fieldnames))
        for z in r:
            wait=int(z['wait_ns']); hold=int(z['hold_ns']); vertex=int(z['vertex']); worker=int(z['worker'])
            if wait<0 or hold<0 or not (0<=vertex<1000000):raise ValueError('Invalid sample')
            w.append(wait);h.append(hold);ids.append(vertex);workers.add(worker);n+=1
    if n!=expected['samples'] or n<1000: raise ValueError(f'Unexpected sample count {n} != {expected["samples"]}')
    expected_n=2*expected['proposals']/expected['sample_mod']
    if n<0.6*expected_n or n>1.4*expected_n:raise ValueError(f'Sample rate suspect: {n} vs expected {expected_n}')
    return {
        'sample_count':n,'sample_mod':expected['sample_mod'],'expected_lock_calls_formula':'2 * directed_proposals',
        'expected_lock_calls':2*expected['proposals'],'expected_sample_count':expected_n,
        'workers_observed':len(workers),
        'wait_mean_us':statistics.mean(w)/1000,'wait_p50_us':quant(w,50)/1000,
        'wait_p90_us':quant(w,90)/1000,'wait_p99_us':quant(w,99)/1000,'wait_p99_9_us':quant(w,99.9)/1000,
        'hold_mean_us':statistics.mean(h)/1000,'hold_p50_us':quant(h,50)/1000,
        'hold_p90_us':quant(h,90)/1000,'hold_p99_us':quant(h,99)/1000,
        'pct_wait_gt_1us':100*sum(x>1000 for x in w)/n,
        'pct_wait_gt_10us':100*sum(x>10000 for x in w)/n,
        'pct_wait_gt_100us':100*sum(x>100000 for x in w)/n,
        'wait_share_of_sampled_wait_plus_hold_pct':100*sum(w)/(sum(w)+sum(h)) if sum(w)+sum(h) else 0,
        'sampled_wait_sum_s':sum(w)/1e9,'sampled_hold_sum_s':sum(h)/1e9,
        'sample_vertex_distinct_count':len(set(ids)),
        'caveat':'Sampling and steady_clock overhead; OS descheduling included; per-lock probes themselves may influence contention; not true lock contention ground truth.'
    }

def analyze(folder):
    paths={p.stem:p for p in folder.glob('r*.log')}
    expected={'r1_p0','r1_off','r1_on','r1_1t_on','r2_on','r2_off','r2_p0'}
    if set(paths)!=expected:raise ValueError('Missing or unexpected logs '+str(set(paths)^expected))
    runs={}
    for k,p in paths.items():
        x=parse_log(p)
        if k.endswith('_p0') and x['trace_enabled'] is not None:raise ValueError('P0 has unexpected logger')
        if k.endswith('_off') and x['trace_enabled']!=0:raise ValueError('P4b OFF missing')
        if k.endswith('_on') and x['trace_enabled']!=1:raise ValueError('P4b ON missing')
        if k.endswith('_on'):x['locks']=parse_csv(p.with_suffix('.csv'),x)
        runs[k]=x
    diffs=[]
    for i in (1,2):
        def pct(a,b,field):return 100*(runs[b][field]/runs[a][field]-1)
        diffs.append({'round':i,
                      'off_vs_p0_wall_pct':pct(f'r{i}_p0',f'r{i}_off','process_wall_s'),
                      'on_vs_off_leaf_pct':pct(f'r{i}_off',f'r{i}_on','leaf_wall_s'),
                      'on_vs_off_process_wall_incl_csv_pct':pct(f'r{i}_off',f'r{i}_on','process_wall_s'),
                      'on_vs_p0_leaf_pct':pct(f'r{i}_p0',f'r{i}_on','leaf_wall_s')})
    out={'study':'H26_P4B_SAMPLED_LSH_LOCK_WAIT_HOLD_NO_CAUSAL_CLAIM',
         'runs':runs,'paired_controls':diffs,
         'limits':['Process CPU includes bucket/prune and process startup; not leaf CPU utilization',
                   'Sampled lock wait includes timer/OS preemption and is not pure mutex contention',
                   'Control ON process wall includes CSV flush',
                   'P0 vs P4b OFF uses two compiled binaries; compiler layout may alter performance',
                   'Equal directed proposal count does NOT prove identical graph topology',
                   'No graph output, search quality, multi-seed scaling or novelty claim']}
    (folder/'h26_p4b_summary.json').write_text(json.dumps(out,indent=2,ensure_ascii=False)+'\n')
    lines=['H26-P4b LOCK WAIT/HOLD + PROCESS CPU TRIAGE — DIAGNOSTIC ONLY',
           '4-thread SIFT1M, Top2, ABBA-like balanced arms, sampled lock pre/post; no graph output.',
           'PROCESS CPU ratio=(GNU user+system)/GNU elapsed; includes all BUILD phases.',
           'ARM          process-wall(s) leaf-wall(s) process-CPU(x) merge-worker(s) context-switches(v/i)']
    for k in ['r1_p0','r1_off','r1_on','r1_1t_on','r2_on','r2_off','r2_p0']:
        a=runs[k];lines.append(f'{k:<12} {a["process_wall_s"]:>10.3f} {a["leaf_wall_s"]:>12.3f} {a["process_cpu_ratio"]:>13.2f} {a["merge_worker_ns"]/1e9:>15.3f}  {int(a["vcs"])} / {int(a["ivcs"])}')
    lines.append('--- On/off and original-P0 controls (two independent pairs only) ---')
    for z in diffs:
        lines.append(f'round {z["round"]}: off vs P0 process-wall {z["off_vs_p0_wall_pct"]:+.2f}%, on vs off leaf-wall {z["on_vs_off_leaf_pct"]:+.2f}%, on vs off process-wall(+CSV) {z["on_vs_off_process_wall_incl_csv_pct"]:+.2f}%')
    lines.append('--- Sampled LSHGraph::merge_neighbors mutex waits vs hold intervals ---')
    for k in ['r1_4t_on','r1_1t_on','r2_4t_on']:
        actual=k.replace('_4t','') if '4t' in k else k
        a=runs[actual]['locks'];lines.append(f'{k}: samples={a["sample_count"]:,} wait p50/p90/p99={a["wait_p50_us"]:.3f}/{a["wait_p90_us"]:.3f}/{a["wait_p99_us"]:.3f} us; hold p50/p90/p99={a["hold_p50_us"]:.3f}/{a["hold_p90_us"]:.3f}/{a["hold_p99_us"]:.3f} us; wait>10us={a["pct_wait_gt_10us"]:.4f}%, sample-wait-share={a["wait_share_of_sampled_wait_plus_hold_pct"]:.2f}%')
    lines.append('WARNING: sample-wait-share is NOT percentage of BUILD wall time lost to mutex contention.')
    lines.append('Decision gate: look for robust 4t vs 1t lock-wait tail plus low process CPU / significant merge-worker pressure before considering lock-aware algorithm; inspect probe overhead.')
    (folder/'h26_p4b_summary.txt').write_text('\n'.join(lines)+'\n')
    print('\n'.join(lines))
if __name__=='__main__':
    try:
        a=argparse.ArgumentParser();a.add_argument('--dir',required=True);args=a.parse_args();analyze(pathlib.Path(args.dir))
    except Exception as e:print('H26P4B_FAIL_CLOSED:',e,file=sys.stderr);sys.exit(2)
