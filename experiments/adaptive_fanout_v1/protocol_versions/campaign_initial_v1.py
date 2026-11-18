#!/usr/bin/env python3
"""Calibrate an adaptive rule, then validate a frozen choice on held-out queries."""
from datetime import datetime, timezone
import json
from pathlib import Path
import statistics

import numpy as np
from run import HERE, parser, prepare_data, run_case, save, check_protected


def bootstrap_paired(differences, rng, repeats=2000, lower_alpha=.01):
    nrep, nq = differences.shape
    samples = np.empty(repeats)
    for b in range(repeats):
        builds = rng.integers(0, nrep, nrep)
        queries = rng.integers(0, nq, nq)
        samples[b] = differences[builds][:, queries].mean()
    return {"mean_delta": float(differences.mean()),
            "ci95": list(map(float, np.percentile(samples, [2.5, 97.5]))),
            "familywise_one_sided_lower": float(np.quantile(samples, lower_alpha))}


def main():
    p = parser()
    p.description = __doc__
    p.add_argument('--repeats', type=int, default=3)
    p.add_argument('--calibration-queries', type=int, default=1000)
    p.add_argument('--recall-tolerance', type=float, default=.002)
    args = p.parse_args()
    if not 1 <= args.calibration_queries < args.queries or args.repeats < 2:
        p.error('Need calibration/holdout split and at least two build repeats')
    check_protected()
    out = HERE/'runs'/args.run_name; out.mkdir(parents=True, exist_ok=False)
    protocol = {"utc": datetime.now(timezone.utc).isoformat(), "rows": args.rows, "queries": args.queries,
                "calibration_query_ids": [0,args.calibration_queries-1],
                "holdout_query_ids": [args.calibration_queries,args.queries-1],
                "seed_start": args.seed, "build_repeats": args.repeats, "threads": args.threads,
                "beams": args.beams, "recall_tolerance_absolute": args.recall_tolerance,
                "minimum_proposal_reduction": .05,
                "selection": "On calibration queries only: keep all protected beams within tolerance; choose fewest directed proposals, not fastest noisy time",
                "protected_beams": [b for b in args.beams if 80<=b<=160],
                "holdout_test": "Paired hierarchical bootstrap of build pairs and query IDs; 2000 draws; Bonferroni one-sided lower bound, family alpha=.05",
                "no_GT_during_build": True, "timing_counters": "R86_COUNTERS=OFF; lightweight AF telemetry enabled equally in both modes",
                "status": "RUNNING", "completed_runs": []}
    save(out/'protocol.json',protocol)
    data, _ = prepare_data(args)
    seeds = [args.seed+i for i in range(args.repeats)]
    arms = [('fixed', 'fixed', .03, 1)] + [(f'eps{eps:g}_min1','adaptive',eps,1) for eps in [0,.01,.03,.05,.10]]
    arms += [('eps0.03_min2','adaptive',.03,2)]
    pilot={}
    for name,mode,eps,floor in arms:
        result=run_case(args,data,f'{args.run_name}__{name}_s{seeds[0]}',mode,eps,seeds[0],floor)
        pilot[name]=result
        protocol['completed_runs'].append(str(result[0]));save(out/'protocol.json',protocol)
    protected=protocol['protected_beams']
    if not protected: raise ValueError('Need at least one protected beam between 80 and 160')
    base=pilot['fixed'];base_proposals=base[1]['telemetry']['directed_proposals']
    calibration=[]
    for name,mode,eps,floor in arms[1:]:
        case=pilot[name]
        delta={str(b):float((case[2][b][:args.calibration_queries,1]-base[2][b][:args.calibration_queries,1]).mean()) for b in protected}
        reduction=1-case[1]['telemetry']['directed_proposals']/base_proposals
        accepted=min(delta.values())>=-args.recall_tolerance and reduction>=.05
        calibration.append({'name':name,'epsilon':eps,'min_fanout':floor,'delta_recall':delta,
                            'proposal_reduction':reduction,'accepted':accepted})
    feasible=[c for c in calibration if c['accepted']]
    if feasible:
        choice=max(feasible,key=lambda c:c['proposal_reduction'])
    else:
        # Continue testing the most conservative observed tradeoff, but do not
        # label it a successful hypothesis even if a later point estimate looks good.
        reduced=[c for c in calibration if c['proposal_reduction']>=.05] or calibration
        choice=max(reduced,key=lambda c:(min(c['delta_recall'].values()),c['proposal_reduction']))
    selection={'selected':choice,'any_candidate_passed_calibration':bool(feasible),
               'all_calibration_candidates':calibration,'selection_frozen_before_holdout_analysis':True}
    save(out/'selection.json',selection)
    print('FROZEN_SELECTION='+json.dumps(choice),flush=True)
    fixed=[base];adaptive=[pilot[choice['name']]]
    for i,seed in enumerate(seeds[1:],1):
        order=['adaptive','fixed'] if i%2 else ['fixed','adaptive']
        for mode in order:
            eps,floor=(choice['epsilon'],choice['min_fanout']) if mode=='adaptive' else (.03,1)
            name=choice['name'] if mode=='adaptive' else 'fixed'
            case=run_case(args,data,f'{args.run_name}__{name}_s{seed}',mode,eps,seed,floor)
            (adaptive if mode=='adaptive' else fixed).append(case)
            protocol['completed_runs'].append(str(case[0]));save(out/'protocol.json',protocol)
    # Arrays are in seed order despite counterbalanced execution order.
    rng=np.random.default_rng(20261118)
    holdout={}
    for b in args.beams:
        f=np.stack([case[2][b][args.calibration_queries:,1] for case in fixed])
        a=np.stack([case[2][b][args.calibration_queries:,1] for case in adaptive])
        ci=bootstrap_paired(a-f,rng,lower_alpha=.05/len(protected))
        holdout[str(b)]={'fixed_recall':float(f.mean()),'adaptive_recall':float(a.mean()),**ci}
    def med(cases,path):
        result=[]
        for c in cases:
            value=c[1]
            for key in path:value=value[key]
            result.append(value)
        return float(statistics.median(result))
    comparison={}
    for label,path in [('build_seconds',['wall_s']),('peak_rss_kib',['peak_rss_kib']),
                       ('directed_proposals',['telemetry','directed_proposals']),
                       ('leaf_squared_work',['telemetry','leaf_squared_work']),
                       ('leaf_points',['telemetry','leaf_points']),('graph_edges',['graph','edges']),
                       ('reservoir_occupied_slots',['telemetry','reservoir_occupied_slots'])]:
        f=med(fixed,path);a=med(adaptive,path)
        comparison[label]={'fixed_median':f,'adaptive_median':a,'reduction_fraction':1-a/f if f else 0}
    quality_pass=all(holdout[str(b)]['familywise_one_sided_lower']>=-args.recall_tolerance for b in protected)
    matched={}
    for target in [.95,.99]:
        matched[str(target)]={}
        for label,cases,field in [('fixed',fixed,'fixed_recall'),('adaptive',adaptive,'adaptive_recall')]:
            eligible=[b for b in args.beams if holdout[str(b)][field]>=target]
            if not eligible:matched[str(target)][label]={'status':'NOT_REACHED_ON_TESTED_BEAMS'};continue
            b=min(eligible)
            qps=[next(r['qps'] for r in c[1]['search'] if r['beam']==b) for c in cases]
            latency=np.concatenate([c[2][b][args.calibration_queries:,0] for c in cases])
            matched[str(target)][label]={'beam':b,'holdout_recall':holdout[str(b)][field],
                                        'full_batch_qps_median':float(statistics.median(qps)),
                                        'holdout_latency_mean_us':float(latency.mean()),
                                        'holdout_latency_p95_us':float(np.percentile(latency,95))}
    report={'status':'COMPLETE','selected':choice,'calibration_pass':bool(feasible),'holdout_noninferiority_pass':quality_pass,
            'empirical_accept':bool(feasible) and quality_pass and comparison['directed_proposals']['reduction_fraction']>=.05,
            'comparison':comparison,'holdout':holdout,'matched_recall':matched,
            'fixed_runs':[str(c[0]) for c in fixed],'adaptive_runs':[str(c[0]) for c in adaptive],
            'protected_originals_unchanged':check_protected(),
            'limitations':['One SIFT dataset; empirical evidence, no universal quality guarantee.',
                           'Three build seeds by default; CPU is not isolated from other applications.',
                           'Assignment buffer reserves original maximum; fixed reservoir capacity is unchanged.',
                           'Per-query latency has no queue wait and no warmup/repetition protocol.',
                           'Noninferiority permits the predeclared absolute Recall tolerance; this is not exact equality.']}
    save(out/'report.json',report)
    protocol['status']='COMPLETE';save(out/'protocol.json',protocol)
    print('CAMPAIGN_COMPLETE='+str(out/'report.json'),flush=True)
    print(json.dumps({'selected':choice['name'],'empirical_accept':report['empirical_accept'],'comparison':comparison}),flush=True)


if __name__=='__main__':main()
