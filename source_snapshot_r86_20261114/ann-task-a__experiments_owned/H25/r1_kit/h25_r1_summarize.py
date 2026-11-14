#!/usr/bin/env python3
"""Summarize H25 native ablation with upfront confounding and integrity flags.
Do not interpret offline replay as feasible BUILD speedup or novelty.
"""
from __future__ import annotations
import argparse,csv,json,re,sys
from pathlib import Path

def load(p):
    with p.open() as f:return list(csv.DictReader(f))
def main():
    a=argparse.ArgumentParser();a.add_argument('--runs',type=Path,required=True);a.add_argument('--out',type=Path,required=True);v=a.parse_args()
    policies=('baseline','nearest','random')
    rows={p:load(v.runs/f'{p}_eval.csv') for p in policies}
    metric={};g={};warnings=[]
    for p in policies:
        log=(v.runs/f'{p}_build.log').read_text(errors='replace')
        checks=re.findall(r'H25_R1_VERIFY: checked_rows=(\d+)/(\d+) applied_patches=(\d+)/(\d+)',log)
        if not checks or 'H25_R1_VERIFY_PASS' not in log:raise RuntimeError('Missing native hook verification: '+p)
        checked,ncheck,applied,npatch=map(int,checks[-1])
        if checked!=ncheck or applied!=npatch:raise RuntimeError('Native patch/control incomplete: '+p)
        marker=re.search(r'Maximum resident set size \(kbytes\):\s*(\d+)',log)
        mem_kb=int(marker.group(1)) if marker else None
        if mem_kb is None:warnings.append(f'Missing RSS measurement for {p}')
        if len(rows[p])==0:raise RuntimeError('Empty eval: '+p)
        eds=set(x['ef'] for x in rows[p]);g[p]={k:rows[p][0][k] for k in ('n','edges','graph_bytes','reachable0','zero_indegree')}
        metric[p]={row['ef']:{'recall10':float(row['recall10']),'median_qps':float(row['median_qps']),
                  'min_qps':float(row['min_qps']),'max_qps':float(row['max_qps'])} for row in rows[p]}
        g[p].update({'peak_rss_kb_build':mem_kb,'verified_rows':checked,'patches_applied':applied,
                     'native_BUILD_includes_offline_policy_cost':False})
    efs=list(metric['baseline']);
    if any(set(metric[p])!=set(efs) for p in policies):raise RuntimeError('ef grid not identical across variants')
    for p in policies[1:]:
        base=int(g['baseline']['graph_bytes']);their=int(g[p]['graph_bytes'])
        if base!=their:warnings.append(f'{p}: index bytes {their} != baseline {base}; NOT memory/edge-matched')
        if int(g['baseline']['edges'])!=int(g[p]['edges']):warnings.append(f'{p}: total graph edge count differs from baseline')
        if int(g[p]['reachable0'])!=int(g['baseline']['reachable0']):warnings.append(f'{p}: reachable0 changed')
    diff={p:{ef:{'delta_recall10_percentage_points':100*(metric[p][ef]['recall10']-metric['baseline'][ef]['recall10']),
                  'relative_median_qps_pct':100*(metric[p][ef]['median_qps']/metric['baseline'][ef]['median_qps']-1)}
                for ef in efs}for p in policies[1:]}
    report={'study':'H25_R1_NATIVE_PIPNN_OFFLINE_INTERVENTION_PILOT',
      'verdict':'DIAGNOSTIC_ONLY_NOT_PARETO_NOT_NOVELTY',
      'gates':{'native_leaves_match_capture':True,'samples':len(rows['baseline']),
               'same_evaluator_for_all':True,'offline_patch_cost_excluded_from_BUILD':True,
               'matched_index_bytes':len({g[p]['graph_bytes'] for p in policies})==1,
               'matched_edge_count':len({g[p]['edges'] for p in policies})==1},
      'graph':g,'search':metric,'relative_to_baseline':diff,'warnings':warnings,
      'not_proved':['feasible concurrent first-occurrence detection','complete policy BUILD cost',
          'deterministic graph equivalence across runs','post-HashPrune proposal survival attribution',
          'matched Recall/bytes across builder settings','repeated native BUILD','algorithm novelty']}
    if v.out.exists():raise RuntimeError('refuse overwrite existing summary: '+str(v.out))
    v.out.write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n')
    print('H25_R1_SUMMARY_WRITTEN',v.out)
    print('WARNINGS:',json.dumps(warnings,ensure_ascii=False))
if __name__=='__main__':
    try:main()
    except Exception as e:print('FAIL CLOSED:',e,file=sys.stderr);sys.exit(2)
