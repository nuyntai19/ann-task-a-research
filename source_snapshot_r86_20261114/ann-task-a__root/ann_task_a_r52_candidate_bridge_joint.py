#!/usr/bin/env python3
"""H32-R52: read-only joint cross-tab of an EXISTING R51 JSON, no graph/search.

R51 anchor target IDs are exact base-neighbor diagnostics, NOT heldout query GT.
This script only examines previously measured boolean flags; it never mutates graph.

python3 ann_task_a_r52_candidate_bridge_joint.py selftest
python3 ann_task_a_r52_candidate_bridge_joint.py audit
"""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import sys

INPUT = Path('experiments/H51/r51_reverse_pool_audit.json')
OUTPUT = Path('experiments/H52/r52_candidate_bridge_joint.json')
GRAPH_SHA = 'd497f6d19fff4b7db6436f960d036755e375be92483c03ec0b9ed61968d17bef'
POOL_SHA = '7e22a4ca2b71bd560560f7e4aa2a1f2dcad46b8f25ae48ca8ea014c17086f9e8'
EXPECTED_GROUPS = {'DIRECT': 207, 'CAPTURED_BUT_PRUNED': 71, 'MISSING_BEFORE_POOL': 42}
FIELDS = ('reverse_candidate_in_pool', 'reverse_direct_edge_in_graph',
          'directed_graph_hops_le_2', 'graph_neighbor_can_offer_target_as_candidate')


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for data in iter(lambda: f.read(1024 * 1024), b''):
            h.update(data)
    return h.hexdigest()


def validate(d, strict=True):
    if not isinstance(d, dict) or d.get('audit') != 'R51_REVERSE_POOL_GRAPH_READONLY_PASS':
        raise ValueError('Input does not carry the expected R51 PASS marker')
    prov = d.get('provenance', {})
    if prov.get('graph_sha256') != GRAPH_SHA or prov.get('pool_sha256') != POOL_SHA:
        raise ValueError('Pinned R26a graph/pool provenance differs from expected SHA')
    if prov.get('h18_leaves_used') is not False or prov.get('no_new_build_or_search') is not True:
        raise ValueError('R51 read-only/same-build provenance flags not present')
    rows = d.get('per_target')
    if not isinstance(rows, list) or (strict and len(rows) != 320):
        raise ValueError(f'Expected exactly 320 R51 per-target records, got {type(rows).__name__} / {len(rows) if isinstance(rows, list) else "?"}')
    seen=set(); source_ranks=defaultdict(set); groups=Counter()
    for row in rows:
        if not isinstance(row,dict) or row.get('class') not in EXPECTED_GROUPS:
            raise ValueError('Invalid R51 row class')
        s,t,r=row.get('source_id'),row.get('target_id'),row.get('exact_base_GT_rank')
        if not all(isinstance(v,int) and not isinstance(v,bool) for v in (s,t,r)) or not(1<=r<=10) or s==t:
            raise ValueError('Invalid source/target/exact-base-rank field')
        key=(s,t)
        if key in seen: raise ValueError('Repeated exact base anchor pair')
        seen.add(key);source_ranks[s].add(r);groups[row['class']]+=1
        for k in FIELDS:
            if type(row.get(k)) is not bool:
                raise ValueError(f'{k} must be a boolean for {s}->{t}')
    if strict:
        if dict(groups) != EXPECTED_GROUPS:
            raise ValueError(f'Wrong R41 category replication: {dict(groups)}')
        if len(source_ranks)!=32 or any(v!=set(range(1,11)) for v in source_ranks.values()):
            raise ValueError('Not exactly 32 base sources with all ranks 1..10')
        summ=d.get('summary',{})
        if (summ.get('slots'),summ.get('direct_graph'),summ.get('in_source_pool'),
            summ.get('missing_before_pool'),summ.get('captured_but_pruned'),
            summ.get('reachable_directed_within_two_graph_hops'))!=(320,207,278,42,71,300):
            raise ValueError('R41/R43 aggregate controls do not match expected values')
    return rows


def compare_groups(rows):
    result={};unresolved=[]
    for cls in ('MISSING_BEFORE_POOL','CAPTURED_BUT_PRUNED'):
        group=[r for r in rows if r['class']==cls]
        tab=Counter()
        bysource=Counter()
        for r in group:
            hops=r['directed_graph_hops_le_2']
            via_pool=r['graph_neighbor_can_offer_target_as_candidate']
            rev_pool=r['reverse_candidate_in_pool']
            rev_graph=r['reverse_direct_edge_in_graph']
            state=('GRAPH_2HOP_AND_POOL_WITNESS' if hops and via_pool else
                   'GRAPH_2HOP_WITHOUT_POOL_WITNESS' if hops else
                   'CANDIDATE_BRIDGE_ONLY' if via_pool else
                   'NO_GRAPH_OR_CANDIDATE_BRIDGE')
            tab[state]+=1
            tab['reverse_candidate_and_unreachable']+=int(rev_pool and not hops)
            tab['reverse_graph_and_unreachable']+=int(rev_graph and not hops)
            tab['unreachable_and_pool_offer_and_reverse_candidate']+=int(not hops and via_pool and rev_pool)
            if not hops:
                bysource[r['source_id']]+=1
                unresolved.append({'source_id':r['source_id'],
                    'exact_base_GT_rank':r['exact_base_GT_rank'],
                    'target_id':r['target_id'], 'category':cls,
                    'bridge_class':state,
                    'reverse_candidate_in_pool':rev_pool,
                    'reverse_direct_edge_in_graph':rev_graph,
                    'source_graph_degree':r.get('source_graph_degree'),
                    'source_pool_degree':r.get('source_pool_degree'),
                    'graph_2hop_witnesses':r.get('graph_2hop_witnesses'),
                    'graph_then_candidate_2hop_witnesses':r.get('graph_then_candidate_2hop_witnesses')})
        n=len(group)
        tab['n']=n
        tab['graph_hops_le_2']=sum(r['directed_graph_hops_le_2'] for r in group)
        tab['neighbor_pool_can_offer']=sum(r['graph_neighbor_can_offer_target_as_candidate'] for r in group)
        tab['reverse_candidate']=sum(r['reverse_candidate_in_pool'] for r in group)
        tab['reverse_graph']=sum(r['reverse_direct_edge_in_graph'] for r in group)
        tab['unreachable']=n-tab['graph_hops_le_2']
        tab['distinct_sources_with_unreachable']=len(bysource)
        tab['unreachable_by_source']={str(k):int(v) for k,v in sorted(bysource.items())}
        assert sum(tab[k] for k in ('GRAPH_2HOP_AND_POOL_WITNESS','GRAPH_2HOP_WITHOUT_POOL_WITNESS',
                                    'CANDIDATE_BRIDGE_ONLY','NO_GRAPH_OR_CANDIDATE_BRIDGE'))==n
        result[cls]=dict(tab)
    unresolved.sort(key=lambda x:(x['category'],x['source_id'],x['exact_base_GT_rank']))
    return result,unresolved


def audit(infile,outfile):
    if outfile.exists():
        raise FileExistsError(f'Output already exists, refuse overwrite: {outfile}')
    d=json.loads(infile.read_text(encoding='utf-8'))
    rows=validate(d,strict=True)
    groups,unresolved=compare_groups(rows)
    if len(unresolved)!=20 or sum(x['category']=='MISSING_BEFORE_POOL' for x in unresolved)!=13:
        raise ValueError('Historical R43 unresolved group control fails (13 missing + 7 pruned)')
    out={'audit':'R52_R51_JOINT_OFFLINE_PASS','source_r51':str(infile),
         'source_r51_sha256':digest(infile),
         'graph_sha256':GRAPH_SHA,'pool_sha256':POOL_SHA,
         'n_sources':32,'exact_base_top10_slots':320,
         'unreachable_within_two_hops':20,
         'by_category':groups,
         'unresolved_exact_base_pairs':unresolved,
         'interpretation_limits':[
            'CANDIDATE_BRIDGE_ONLY means u->w is a graph edge and w has t in its stored candidate pool; w->t is NOT a retained graph edge.',
            'This does not establish beam will expand w or that adding w->t improves Recall.',
            'Base-anchor exact kNN IDs are diagnostic labels, not heldout ANN user-query GT; never tune a graph using this selected pair list.',
            'No graph/build/search/ground truth scanning performed. Cross-tabs are observational on one graph and 32 base anchors.',
            'An observed no-graph-2hop target may be reachable in >=3 hops.']}
    outfile.parent.mkdir(parents=True,exist_ok=True)
    with outfile.open('x',encoding='utf-8') as f:
        json.dump(out,f,ensure_ascii=False,indent=2);f.write('\n')
    print('R52_R51_32x10_AND_R41_R43_GATES_PASS')
    for cls,z in groups.items():
        print('R52_GROUP',cls,'n',z['n'],'graph2hop',z['graph_hops_le_2'],
              'candidate_bridge_only',z.get('CANDIDATE_BRIDGE_ONLY',0),
              'no_bridge',z.get('NO_GRAPH_OR_CANDIDATE_BRIDGE',0),
              'graph2hop_without_pool',z.get('GRAPH_2HOP_WITHOUT_POOL_WITNESS',0),
              'unreachable',z['unreachable'],'unreachable_sources',z['distinct_sources_with_unreachable'])
    print('R52_UNRESOLVED_BASE_PAIRS',len(unresolved))
    print('R52_R51_JOINT_OFFLINE_PASS')
    print('OUTPUT',outfile)


def selftest():
    prov={'graph_sha256':GRAPH_SHA,'pool_sha256':POOL_SHA,'h18_leaves_used':False,'no_new_build_or_search':True}
    rows=[{'source_id':0,'target_id':1,'exact_base_GT_rank':1,'class':'MISSING_BEFORE_POOL',
           'reverse_candidate_in_pool':False,'reverse_direct_edge_in_graph':False,
           'directed_graph_hops_le_2':False,'graph_neighbor_can_offer_target_as_candidate':True},
          {'source_id':0,'target_id':2,'exact_base_GT_rank':2,'class':'CAPTURED_BUT_PRUNED',
           'reverse_candidate_in_pool':True,'reverse_direct_edge_in_graph':False,
           'directed_graph_hops_le_2':True,'graph_neighbor_can_offer_target_as_candidate':True},
          {'source_id':0,'target_id':3,'exact_base_GT_rank':3,'class':'MISSING_BEFORE_POOL',
           'reverse_candidate_in_pool':False,'reverse_direct_edge_in_graph':False,
           'directed_graph_hops_le_2':False,'graph_neighbor_can_offer_target_as_candidate':False}]
    assert len(validate({'audit':'R51_REVERSE_POOL_GRAPH_READONLY_PASS','provenance':prov,'per_target':rows},strict=False))==3
    g,unresolved=compare_groups(rows)
    assert g['MISSING_BEFORE_POOL']['CANDIDATE_BRIDGE_ONLY']==1
    assert g['MISSING_BEFORE_POOL']['NO_GRAPH_OR_CANDIDATE_BRIDGE']==1
    assert g['CAPTURED_BUT_PRUNED']['GRAPH_2HOP_AND_POOL_WITNESS']==1
    assert len(unresolved)==2
    rows_bad=[dict(r) for r in rows];rows_bad[0]['graph_neighbor_can_offer_target_as_candidate']='True'
    try: validate({'audit':'R51_REVERSE_POOL_GRAPH_READONLY_PASS','provenance':prov,'per_target':rows_bad},strict=False)
    except ValueError: pass
    else: raise AssertionError('Invalid boolean not rejected')
    try: validate({'audit':'R51_REVERSE_POOL_GRAPH_READONLY_PASS','provenance':dict(prov, pool_sha256='bad'), 'per_target':rows},strict=False)
    except ValueError: pass
    else: raise AssertionError('Invalid pool provenance not rejected')
    print('R52_SELFTEST_PASS: joint twohop/pool bridge, unresolved source clustering, provenance and schema gates')


def main():
    p=argparse.ArgumentParser()
    p.add_argument('action',choices=['selftest','audit'])
    p.add_argument('--input',type=Path,default=INPUT)
    p.add_argument('--output',type=Path,default=OUTPUT)
    args=p.parse_args()
    try:
        if args.action=='selftest': selftest()
        else: audit(args.input,args.output)
    except Exception as e:
        print('R52_FAIL:',e,file=sys.stderr)
        return 2
    return 0

if __name__=='__main__': sys.exit(main())
