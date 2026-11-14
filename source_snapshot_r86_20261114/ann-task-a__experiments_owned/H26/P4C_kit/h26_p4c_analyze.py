#!/usr/bin/env python3
"""Analyze H26-P4c P0 no-graph perf stat data; this is whole-process PMU, not phase-local."""
import argparse
import json
import pathlib
import re
import statistics
import sys

EXPECTED = ['r1_4t_off', 'r1_4t_perf', 'r1_2t_perf', 'r1_1t_perf', 'r2_4t_perf', 'r2_4t_off']
COUNTS = {'leaf_count':85529, 'rows':29995085,'proposals':59990170}


def match_one(pat, raw, desc):
    hits = re.findall(pat,raw,flags=re.M)
    if len(hits)!=1: raise ValueError(f'Expected 1 {desc}, found {len(hits)}')
    return hits[0]


def parse_gnu_elapsed(s):
    return sum(float(v)*60**i for i,v in enumerate(s.split(':')[::-1]))


def parse_log(p):
    t=p.read_text(errors='replace')
    x={k:int(match_one(r'^H26_PROFILE,'+k+r',([0-9]+)$',t,k)) for k in COUNTS}
    for k,v in COUNTS.items():
        if x[k]!=v:raise ValueError(f'{p}: invalid {k}: {x[k]}')
    for k,pat in [('leaf_wall_s',r'Parlay time: build leaf time: ([0-9.]+)'),
                  ('buckets_wall_s',r'Parlay time: buckets time: ([0-9.]+)'),
                  ('prune_wall_s',r'Parlay time: Final prune time: ([0-9.]+)')]:
        x[k]=float(match_one(pat,t,k))
    for k in ('dist_worker_ns','select_worker_ns','merge_worker_ns'):
        x[k]=int(match_one(r'^H26_PROFILE,'+k+r',([0-9]+)$',t,k))
    x['process_wall_s']=parse_gnu_elapsed(match_one(r'^\s*Elapsed \(wall clock\) time \(h:mm:ss or m:ss\):\s*([^\n]+)',t,'process elapsed').strip())
    for k,label in [('user_cpu_s','User time (seconds)'),('sys_cpu_s','System time (seconds)'),('vcs','Voluntary context switches'),('ivcs','Involuntary context switches')]:
        x[k]=float(match_one(r'^\s*'+re.escape(label)+r':\s*([0-9.]+)',t,k))
    x['process_cpu_ratio']=(x['user_cpu_s']+x['sys_cpu_s'])/x['process_wall_s']
    return x


def parse_perf(path):
    counters={}
    for l in path.read_text(errors='replace').splitlines():
        if not l.strip() or l.lstrip().startswith('#'): continue
        parts=l.split(';')
        if len(parts)<3: continue
        val,_,event=parts[:3]
        event=event.strip().split(':')[0]
        if event not in {'task-clock','cycles','instructions','cache-references','cache-misses','branches','branch-misses'}:continue
        raw=val.strip().replace(',','')
        if not re.fullmatch(r'(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)',raw):
            raise ValueError(f'{path}: unsupported/missing {event}={raw}')
        if event in counters: raise ValueError(f'{path}: duplicate event {event}')
        counters[event]=float(raw)
    required={'task-clock','cycles','instructions'}
    if not required.issubset(counters):raise ValueError(f'{path}: missing {required - counters.keys()}')
    if counters['cycles']<=0 or counters['instructions']<=0 or counters['task-clock']<=0:raise ValueError(f'{path}: zero core PMU count')
    counters['ipc']=counters['instructions']/counters['cycles']
    counters['cycles_per_instruction']=1/counters['ipc']
    counters['cpu_occupancy_from_perf_taskclock']=counters['task-clock']/1000 # read as CPU seconds (not occupancy yet)
    if counters.get('cache-references',0)>0:
        counters['cache_miss_ratio_pct']=100*counters['cache-misses']/counters['cache-references']
    if 'cache-misses' in counters:
        counters['cache_mpki']=1000*counters['cache-misses']/counters['instructions']
    if 'branch-misses' in counters and counters.get('branches',0)>0:
        counters['branch_miss_ratio_pct']=100*counters['branch-misses']/counters['branches']
    return counters


def summarize(dir):
    expected=set(EXPECTED)
    found={p.name.removesuffix('.log') for p in dir.glob('r*.log')}
    if found!=expected: raise ValueError(f'run set mismatch: missing={expected-found}, extra={found-expected}')
    out={}
    for name in EXPECTED:
        x=parse_log(dir/(name+'.log'))
        if name.endswith('_perf'):
            x['perf']=parse_perf(dir/(name+'.perf.csv'))
            x['perf']['perf_taskclock_cpu_ratio']=x['perf']['task-clock']/1000/x['process_wall_s']
        out[name]=x
    def compare(a,b,key): return 100*(out[b][key]/out[a][key]-1)
    pairs=[]
    for i in (1,2):
        a=f'r{i}_4t_off';b=f'r{i}_4t_perf'
        pairs.append({'round':i,'perf_vs_off_wall_pct':compare(a,b,'process_wall_s'),'perf_vs_off_leaf_pct':compare(a,b,'leaf_wall_s')})
    p1=out['r1_1t_perf']; p2=out['r1_2t_perf']; p4=[out['r1_4t_perf'],out['r2_4t_perf']]
    p4leaf=statistics.median(x['leaf_wall_s'] for x in p4)
    derived={
      'speedup_leaf_1_to_2_PMU_single_pilot':p1['leaf_wall_s']/p2['leaf_wall_s'],
      'speedup_leaf_1_to_4_PMU_vs_two_4t_median':p1['leaf_wall_s']/p4leaf,
      '4t_per_process_IPC_range':[min(x['perf']['ipc'] for x in p4),max(x['perf']['ipc'] for x in p4)],
      '4t_per_process_CPU_ratio_range':[min(x['process_cpu_ratio'] for x in p4),max(x['process_cpu_ratio'] for x in p4)],
      '4t_perf_effect_wall_pct': [x['perf_vs_off_wall_pct'] for x in pairs],
    }
    obj={'study':'H26_P4C_P0_PROCESS_WIDE_PMU_DIAGNOSTIC','runs':out,'paired_controls':pairs,'derived':derived,
         'limits':['Counter values aggregated across entire BUILD process, not leaf phase / Eigen / merge-specific',
                   'perf event cache-misses != measured DRAM bytes/bandwidth and cannot alone prove memory boundedness',
                   'perf counting scales with enabled counters and can multiplex; inspect raw perf files and perf event scaling',
                   'No graph output and no direct Recall/topology equivalence or algorithm novelty',
                   '1T, 2T are single PMU pilot runs, not multi-seed scaling or confidence intervals',
                   'Instrumentation and OS scheduling can bias wall-time; compare P0 perf OFF controls']}
    (dir/'h26_p4c_summary.json').write_text(json.dumps(obj,indent=2,ensure_ascii=False)+'\n')
    lines=['H26-P4c — ORIGINAL H26-P0 TOP2 / PROCESS-WIDE CPU PMU DIAGNOSTIC',
        'Same binary, same SIFT1M, no graph output; perf OFF/ON check. NOT exact leaf critical path or DRAM bandwidth.',
        'ARM           wall(s)  leaf(s) cpu(x) IPC   cache MPKI  cache-miss(%)  branch-miss(%)']
    for name in EXPECTED:
        x=out[name];p=x.get('perf',{})
        v=lambda key: f'{p[key]:.3f}' if key in p else 'n/a'
        lines.append(f'{name:<14}{x["process_wall_s"]:>7.2f}{x["leaf_wall_s"]:>9.2f}{x["process_cpu_ratio"]:>7.2f}{v("ipc"):>7}{v("cache_mpki"):>12}{v("cache_miss_ratio_pct"):>16}{v("branch_miss_ratio_pct"):>16}')
    lines.append('--- Paired measurement overhead (perf ON vs OFF on same P0 binary) ---')
    for q in pairs:
        lines.append(f'round={q["round"]}: process wall {q["perf_vs_off_wall_pct"]:+.2f}%, leaf wall {q["perf_vs_off_leaf_pct"]:+.2f}%')
    lines.append('--- Scaling with PMU enabled (diagnostic; 1T and 2T one run each) ---')
    lines.append(f'1T/2T leaf wall speedup={derived["speedup_leaf_1_to_2_PMU_single_pilot"]:.3f}x; 1T/4T leaf wall speedup={derived["speedup_leaf_1_to_4_PMU_vs_two_4t_median"]:.3f}x')
    lines.append('Interpret IPC/miss ratios together; cache-misses alone DO NOT establish memory bandwidth saturation.')
    lines.append('Decision: if low IPC/high misses or IPC drops with cores -> focus next on phase-local hardware profiling; if stable IPC and scaling, do not invent bottleneck. NO algorithm speedup/novelty claim.')
    (dir/'h26_p4c_summary.txt').write_text('\n'.join(lines)+'\n')
    print('\n'.join(lines))
    return obj

if __name__=='__main__':
    try:
        ap=argparse.ArgumentParser();ap.add_argument('--dir',type=pathlib.Path,required=True)
        args=ap.parse_args();summarize(args.dir)
    except Exception as exc:
        print('H26P4C_FAIL_CLOSED:',exc,file=sys.stderr);sys.exit(2)
