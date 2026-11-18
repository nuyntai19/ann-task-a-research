#!/usr/bin/env python3
"""Compare two saved user graphs with measured Recall matching and common search protocol."""
import argparse
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import re
import statistics
import subprocess

import numpy as np
from run import HERE, REPO, read_queries, run_name, save, sha


def cpu_set(count):
    options=[]
    for cpu in sorted(os.sched_getaffinity(0)):
        p=Path(f'/sys/devices/system/cpu/cpu{cpu}')
        core=((p/'topology/physical_package_id').read_text().strip(),(p/'topology/core_id').read_text().strip())
        freq=p/'cpufreq/cpuinfo_max_freq'
        options.append((-(int(freq.read_text()) if freq.exists() else 0),cpu,core))
    chosen=[];seen=set()
    for _,cpu,core in sorted(options):
        if core not in seen:chosen.append(cpu);seen.add(core)
        if len(chosen)==count:return chosen
    raise ValueError('Not enough distinct physical cores')


def parameters(m):
    c=m['command'][1:]
    return dict(zip(c[::2],c[1::2]))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--fixed-run',type=Path,default=REPO/'local_setup/khoa-linux/runs/sift1m_h17_on_q10000_t4_r2')
    p.add_argument('--adaptive-run',type=Path,default=HERE/'runs/af_eps015_sift1m_r1')
    p.add_argument('--targets',default='.95,.98,.99,.995,.997,.999')
    p.add_argument('--repeats',type=int,default=6)
    p.add_argument('--name',type=run_name,default='user_af_eps015_vs_fixed_r2')
    args=p.parse_args()
    targets=list(map(float,args.targets.split(',')))
    if args.repeats<3 or any(not math.isfinite(t) or not 0<t<1 for t in targets) or len(set(targets))!=len(targets):
        p.error('Need distinct Recall targets between 0 and 1 and >=3 repetitions')
    dirs={'fixed':args.fixed_run.resolve(),'adaptive':args.adaptive_run.resolve()}
    meta={arm:json.loads((path/'summary.json').read_text()) for arm,path in dirs.items()}
    a,b=meta['fixed'],meta['adaptive']
    if a['status']!='LOCAL_FUNCTIONAL_CHECK_PASS' or b['status']!='PASS':raise ValueError('Incomplete saved runs')
    if a['variant']!='h17_on' or b['mode']!='adaptive':raise ValueError('Wrong graph variants')
    da,db=a['data_manifest'],{'base_rows':b['rows'],'query_rows':b['queries']}
    if da['base_rows']!=db['base_rows'] or da['query_rows']!=db['query_rows'] or a['threads']!=b['threads']:
        raise ValueError('Dataset sizes or threads differ')
    count=da['query_rows'];threads=a['threads'];total_neighbors=count*10
    params={arm:parameters(m) for arm,m in meta.items()}
    clean=lambda d:{k:v for k,v in d.items() if k not in ('-base_path','-graph_outfile')}
    if clean(params['fixed'])!=clean(params['adaptive']):raise ValueError('Graph build parameters differ')
    checks={}
    for filename in ['base.fbin','query.fbin','gt.ibin']:
        old=sha(Path(a['data'])/filename);new=sha(Path(b['data'])/filename)
        if old!=new:raise ValueError(f'Dataset mismatch: {filename}')
        checks[filename]=old
    graphs={arm:dirs[arm]/'index.graph' for arm in dirs}
    graph_hashes={arm:sha(path) for arm,path in graphs.items()}
    if graph_hashes['fixed']!=a['graph_audit']['sha256'] or graph_hashes['adaptive']!=b['graph']['sha256']:
        raise ValueError('Saved graph changed')
    out=HERE/'comparisons'/args.name;out.mkdir(parents=True,exist_ok=False)
    raw=out/'raw';raw.mkdir()
    cpus=cpu_set(threads)
    evaluator=HERE/'build/local_graph_recall'
    protocol={'utc':datetime.now(timezone.utc).isoformat(),'fixed_run':str(dirs['fixed']),'adaptive_run':str(dirs['adaptive']),
              'rows':da['base_rows'],'queries':count,'threads':threads,'cpu_affinity':cpus,'targets':targets,
              'repetitions':args.repeats,'evaluator':str(evaluator),'evaluator_sha256':sha(evaluator),
              'data_sha256':checks,'graph_sha256':graph_hashes,'common_build_parameters':clean(params['fixed']),
              'measurement':'Same evaluator and CPU affinity; search only on frozen saved graphs; counterbalanced methods and beam order; one warmup pass per graph',
              'matching':'Measured integer beam search for smallest beam found meeting each target; adjacent lower beam checked; report achieved Recall, no interpolated timing',
              'latency':'Per-query service microseconds excluding scheduler queue wait and file I/O',
              'historical_build_time_caveat':'Original fixed uses R86_COUNTERS ON; adaptive uses R86_COUNTERS OFF plus AF telemetry; different execution times of day. Historical build durations are descriptive, not controlled speedup.',
              'status':'RUNNING'}
    save(out/'protocol.json',protocol)
    env={k:v for k,v in os.environ.items() if not k.startswith(('AF_','R86_'))}
    env.update(PARLAY_NUM_THREADS=str(threads),OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='1')
    data=Path(b['data'])
    serial=0;known={'fixed':{},'adaptive':{}};all_probes=[]

    def measure(arm,beams,phase):
        nonlocal serial
        serial+=1;stem=f'{serial:03d}_{phase}_{arm}'
        csv_path=raw/f'{stem}.csv';log_path=raw/f'{stem}.log'
        cmd=['taskset','-c',','.join(map(str,cpus)),str(evaluator),str(graphs[arm]),str(data/'base.fbin'),
             str(data/'query.fbin'),str(data/'gt.ibin'),str(csv_path),','.join(map(str,beams))]
        with log_path.open('w') as f:subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT,env=env,check=True,timeout=600)
        arrays=read_queries(csv_path,beams,count)
        log=log_path.read_text()
        parsed=re.findall(r'LOCAL_RECALL_ROW beam=(\d+) recall=([\d.eE+-]+) qps=([\d.eE+-]+)',log)
        if [int(r[0]) for r in parsed]!=beams:raise ValueError('Beam output mismatch')
        values={}
        for beam,recall,qps in parsed:
            beam=int(beam);sample=arrays[beam]
            hits=int(round(sample[:,1].sum()*10))
            achieved=hits/total_neighbors
            if abs(achieved-float(recall))>1e-6:raise ValueError('Raw recall disagrees with native aggregate')
            if beam in known[arm] and known[arm][beam]['hits']!=hits:raise ValueError('Query results changed across repeats')
            values[beam]={'beam':beam,'hits':hits,'recall':achieved,'qps':float(qps),
                          'latency_mean_us':float(sample[:,0].mean()),
                          'latency_p50_us':float(np.percentile(sample[:,0],50)),
                          'latency_p95_us':float(np.percentile(sample[:,0],95)),
                          'latency_p99_us':float(np.percentile(sample[:,0],99)),
                          'raw_csv':str(csv_path),'raw_log':str(log_path)}
        all_probes.append({'phase':phase,'arm':arm,'beams':beams,'command':cmd,'results':values})
        save(out/'progress.json',{'measurements_completed':serial,'latest_phase':phase,'latest_arm':arm,'latest_beams':beams})
        return values

    initial=[10,40,60,80,100,120,140,160,240,320]
    for arm in dirs:
        known[arm].update(measure(arm,initial,'calibrate'))
        print(f'INITIAL_CURVE_READY={arm}',flush=True)
    target_hits={target:math.ceil(target*total_neighbors-1e-8) for target in targets}
    for iteration in range(20):
        pending={arm:set() for arm in dirs}
        for arm in dirs:
            for target,required in target_hits.items():
                passing=sorted(q for q,row in known[arm].items() if row['hits']>=required)
                if not passing:
                    q=max(known[arm])*2
                    if q>4096:raise ValueError(f'Recall target {target} not reached by reasonable beams')
                    pending[arm].add(q);continue
                hi=passing[0]
                lo=max([9]+[q for q,row in known[arm].items() if q<hi and row['hits']<required])
                if hi-lo>1:pending[arm].add((hi+lo)//2)
        if not any(pending.values()):break
        for arm,beams in pending.items():
            if beams:known[arm].update(measure(arm,sorted(beams),f'tune{iteration}'))
        print(f'RECALL_MATCHING_ROUND={iteration+1}',flush=True)
    else:raise ValueError('Recall matching did not converge')
    selected={arm:{} for arm in dirs}
    observed_nonmonotonic={}
    for arm in dirs:
        ordered=sorted(known[arm]);observed_nonmonotonic[arm]=[(x,y) for x,y in zip(ordered,ordered[1:]) if known[arm][x]['hits']>known[arm][y]['hits']]
        for target,required in target_hits.items():
            q=min(q for q,row in known[arm].items() if row['hits']>=required)
            if q>10 and (q-1 not in known[arm] or known[arm][q-1]['hits']>=required):
                raise ValueError('Adjacent lower beam was not verified')
            selected[arm][target]=q
    save(out/'matched_beams.json',{'selected':selected,'observed_nonmonotonic_pairs':observed_nonmonotonic,
                                  'quality_probe_results':known})
    print('MATCHED_BEAMS='+json.dumps(selected),flush=True)
    for arm in dirs:measure(arm,sorted(set(selected[arm].values())),'warmup')
    repetitions=[]
    for repeat in range(args.repeats):
        paired={}
        order=list(dirs) if repeat%2==0 else list(reversed(dirs))
        for arm in order:
            beams=sorted(set(selected[arm].values()),reverse=bool(repeat%2))
            paired[arm]=measure(arm,beams,f'measure{repeat+1}')
        repetitions.append(paired)
        print(f'MEASURED_REPEAT={repeat+1}/{args.repeats}',flush=True)
    matched=[]
    for target in targets:
        result={'target_recall':target}
        for arm in dirs:
            q=selected[arm][target];runs=[r[arm][q] for r in repetitions]
            row={'beam':q,'recall':runs[0]['recall'],'recall_overshoot_pp':100*(runs[0]['recall']-target)}
            for field in ['qps','latency_mean_us','latency_p50_us','latency_p95_us','latency_p99_us']:
                sample=[v[field] for v in runs];row[field]=float(statistics.median(sample))
                row[field+'_range']=[min(sample),max(sample)]
            result[arm]=row
        result['qps_change_percent']=100*(result['adaptive']['qps']/result['fixed']['qps']-1)
        result['mean_latency_change_percent']=100*(result['adaptive']['latency_mean_us']/result['fixed']['latency_mean_us']-1)
        matched.append(result)
    # Structural/logical build work can be compared, but historical wall time
    # differs in counters and execution conditions and is not an A/B timing.
    old_counts=[json.loads(line) for line in (dirs['fixed']/'counters.jsonl').read_text().splitlines()]
    counter=lambda name:sum(r['observed'] for r in old_counts if r['metric_code']==name)
    structure={'directed_proposals':{'fixed':counter('proposals'),'adaptive':b['telemetry']['directed_proposals']},
               'graph_edges':{'fixed':a['graph_audit']['edges'],'adaptive':b['graph']['edges']},
               'leaf_squared_work':{'fixed':counter('W_L'),'adaptive':b['telemetry']['leaf_squared_work']},
               'historical_build_seconds':{'fixed':a['build_seconds'],'adaptive':b['wall_s'],'controlled_comparison':False}}
    for key,row in structure.items():
        if key!='historical_build_seconds':row['reduction_percent']=100*(1-row['adaptive']/row['fixed'])
    for arm in dirs:
        if sha(graphs[arm])!=graph_hashes[arm]:raise ValueError('Input graph modified')
    protocol['status']='COMPLETE'
    report={'status':'PASS','protocol':protocol,'matched_recall':matched,'structure':structure,
            'graphs_unchanged':True,'same_beam_is_not_same_quality':True,
            'limits':['Two specific user graphs, not a multi-seed algorithm superiority claim.',
                      'Recall targets use minimum integer beams found in measured brackets; achieved Recall is displayed.',
                      'Six search repetitions default, core affinity controlled, OS/thermal load not exclusively isolated.',
                      'Performance numbers are fresh common-evaluator measurements, not the original afternoon throughput.']}
    save(out/'report.json',report);save(out/'measurement_commands.json',all_probes)
    save(out/'protocol.json',protocol)
    print('COMPARISON_COMPLETE='+str(out/'report.json'),flush=True)
    print(json.dumps(matched,indent=2),flush=True)


if __name__=='__main__':main()
