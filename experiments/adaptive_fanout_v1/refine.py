#!/usr/bin/env python3
"""Prespecified conservative refinement, using only calibration for selection."""
from datetime import datetime, timezone
import json

from campaign import finish_report
from run import HERE, parser, prepare_data, run_case, save, check_protected, read_queries, sha, validate_args, run_name


def main():
    p=parser();p.description=__doc__
    p.add_argument('--repeats',type=int,default=3)
    p.add_argument('--calibration-queries',type=int,default=1000)
    p.add_argument('--recall-tolerance',type=float,default=.002)
    p.add_argument('--baseline-prefix',type=run_name,default='sift1m_lower_depth_v1')
    args=p.parse_args();validate_args(args,p);check_protected()
    out=HERE/'runs'/args.run_name;out.mkdir(parents=True,exist_ok=False)
    old=json.loads((HERE/'runs'/args.baseline_prefix/'protocol.json').read_text())
    if (old['rows']!=args.rows or old['queries']!=args.queries or old['threads']!=args.threads
            or old['beams']!=args.beams or old.get('min_depth',1)!=args.min_depth
            or old['calibration_query_ids']!=[0,args.calibration_queries-1]):
        raise ValueError('Baseline protocol differs')
    fixed=[]
    for seed in range(args.seed,args.seed+args.repeats):
        path=HERE/'runs'/f'{args.baseline_prefix}__fixed_s{seed}'
        m=json.loads((path/'summary.json').read_text())
        if m['status']!='PASS' or m['seed']!=seed or m['mode']!='fixed' or m['binary_sha256']!=sha(HERE/'build/algorithms/PipNN/neighbors-pipnn_FLOAT_T_EUCLIDEAN'):
            raise ValueError('Baseline binary/seed/status differs')
        fixed.append((path,m,read_queries(path/'query_metrics.csv',args.beams,args.queries)))
    protocol={**old,'utc':datetime.now(timezone.utc).isoformat(),'status':'RUNNING','completed_runs':[],
              'refinement_design':'refinement_protocol.json','fixed_runs_reused':[str(c[0]) for c in fixed]}
    save(out/'protocol.json',protocol)
    data,_=prepare_data(args)
    if any(c[1]['data']!=str(data) for c in fixed):raise ValueError('Baseline dataset snapshot differs')
    arms=[('eps0.1_min2',.10,2),('eps0.15_min1',.15,1),('eps0.15_min2',.15,2),('eps0.2_min1',.20,1),('eps0.2_min2',.20,2)]
    cases={};calibration=[];base=fixed[0];protected=protocol['protected_beams']
    for name,eps,floor in arms:
        case=run_case(args,data,f'{args.run_name}__{name}_s{args.seed}','adaptive',eps,args.seed,floor)
        cases[name]=case;protocol['completed_runs'].append(str(case[0]));save(out/'protocol.json',protocol)
        delta={str(b):float((case[2][b][:args.calibration_queries,1]-base[2][b][:args.calibration_queries,1]).mean()) for b in protected}
        reduction=1-case[1]['telemetry']['directed_proposals']/base[1]['telemetry']['directed_proposals']
        calibration.append({'name':name,'epsilon':eps,'min_fanout':floor,'delta_recall':delta,
                            'proposal_reduction':reduction,'accepted':min(delta.values())>=-args.recall_tolerance and reduction>=.05})
    feasible=[c for c in calibration if c['accepted']]
    choice=max(feasible,key=lambda c:c['proposal_reduction']) if feasible else max(calibration,key=lambda c:min(c['delta_recall'].values()))
    save(out/'selection.json',{'selected':choice,'any_candidate_passed_calibration':bool(feasible),
                              'all_calibration_candidates':calibration,'selection_frozen_before_holdout_analysis':True})
    print('FROZEN_REFINEMENT_SELECTION='+json.dumps(choice),flush=True)
    adaptive=[cases[choice['name']]]
    for seed in range(args.seed+1,args.seed+args.repeats):
        case=run_case(args,data,f'{args.run_name}__{choice["name"]}_s{seed}',
                      'adaptive',choice['epsilon'],seed,choice['min_fanout'])
        adaptive.append(case);protocol['completed_runs'].append(str(case[0]));save(out/'protocol.json',protocol)
    finish_report(args,out,protocol,choice,fixed,adaptive,bool(feasible))


if __name__=='__main__':main()
