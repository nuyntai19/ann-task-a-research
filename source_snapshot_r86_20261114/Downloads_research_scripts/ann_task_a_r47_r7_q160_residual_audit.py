#!/usr/bin/env python3
"""H32-R47-R7A: read-only audit of the five native-Q160 residual GT misses.

Requires existing R47-R5/R6 native parity artifacts, R47 decision-event files,
SIFT1M original float fbin and groundTruth ibin. Reuses the already validated
parsers. No new search, graph build, tracing, or modification of prior results.

This is observational: absence of a logged event is NOT proof that a vertex
is unreachable in the graph. This stage does not compute graph shortest paths.

Run from ~/ann-task-a:
  python3 ann_task_a_r47_r7_q160_residual_audit.py selftest
  python3 -u ann_task_a_r47_r7_q160_residual_audit.py audit
"""
import argparse
from collections import Counter
import json
from pathlib import Path
import sys

ROOT=Path('experiments/H47')
R6=ROOT/'R6_v2'
PIN='d497f6d19fff4b7db6436f960d036755e375be92483c03ec0b9ed61968d17bef'
EXPECTED_FIVE={(1715,420244),(2711,886706),(7167,925061),(7935,978211),(8083,823939)}
LOGGED_TYPES=('EXPAND','DISCOVER','SEEN_SKIP','SCORE','CUTOFF_REJECT',
              'STAGE','MERGE_KEEP','MERGE_DROP','BEAM_EVICT','BATCH_WAIT')


def summarize_events(events,target):
    """Conservatively count only node-ID-targeted events, not inferred routes."""
    selected=[]
    for i,event in enumerate(events):
        try:
            node=int(event.get('node',-1))
        except (TypeError,ValueError):
            continue
        if node==target:
            item={'ordinal':i,'event':event.get('type','UNKNOWN')}
            # Copy a bounded set of diagnostic fields; do not infer meanings.
            for key in ('distance','cutoff','step','source','parent'):
                if key in event and isinstance(event[key],(int,float,str)):
                    item[key]=event[key]
            selected.append(item)
    counts=Counter(x['event'] for x in selected)
    if counts.get('EXPAND',0):
        label='TARGET_EXPANDED_BUT_NOT_RETURNED'
    elif counts.get('MERGE_KEEP',0) and counts.get('BEAM_EVICT',0):
        label='TARGET_KEPT_AND_EVICTED_LOGGED'
    elif counts.get('MERGE_KEEP',0):
        label='TARGET_MERGE_KEEP_LOGGED_BUT_ABSENT_TOP10'
    elif counts.get('SCORE',0) and counts.get('CUTOFF_REJECT',0):
        label='TARGET_SCORE_AND_CUTOFF_REJECT_LOGGED'
    elif counts.get('SCORE',0):
        label='TARGET_SCORED_OUTCOME_NEEDS_TIMELINE'
    elif counts.get('DISCOVER',0) or counts.get('SEEN_SKIP',0):
        label='TARGET_SEEN_IN_LOG_BUT_NO_SCORE_EVENT'
    else:
        label='NO_DIRECT_TARGET_NODE_EVENT'
    return {'label':label,'event_counts':{t:counts.get(t,0) for t in LOGGED_TYPES},
            'direct_event_sequence':selected[:24], 'direct_event_total':len(selected)}


def audit():
    from ann_task_a_r47_r6_native_topk_v2 import read_trace_file,check_source_copy,required_inputs,qdir
    from ann_task_a_r47_r5_q_sensitivity_v2 import Fbin,exact_integer_l2,Ibin
    from ann_task_a_r47_r3_witness_audit import read_events

    qids,r5_by_id=required_inputs()  # validates fixed graph hash, source artifacts
    check_source_copy()
    r5=json.loads((ROOT/'r47_r5_q_sensitivity.json').read_text())
    r6=json.loads((R6/'r47_r6_v2_independent_native_parity.json').read_text())
    if r5.get('audit')!='R47_R5_FIXED_GRAPH_Q_SENSITIVITY_PASS':
        raise ValueError('R5 audit status mismatch')
    if r6.get('audit')!='R47_R6_V2_INDEPENDENT_NATIVE_TOP10_PARITY_PASS':
        raise ValueError('R6 independent native ID parity is NOT PASS')
    if set(map(int,r6['selected_queries']))!=set(qids) or r6.get('repeats')!=5:
        raise ValueError('R6 query IDs/repeats mismatch')
    if r5.get('graph_sha256')!=PIN:
        raise ValueError('R5 graph SHA pin differs')

    old_targets={(int(t['query_id']),int(t['gt_id'])) for t in r5['old_missing_gt_targets']}
    if len(old_targets)!=20:
        raise ValueError(f'R5 expected 20 preselected missing strict GT IDs; got {len(old_targets)}')
    q160={int(r['query_id']):r for r in next(s for s in r6['per_q'] if int(s['Q'])==160)['query_results']}
    if set(q160)!=set(qids):
        raise ValueError('R6 Q160 per-query ID coverage mismatch')
    q120={int(r['query_id']):r for r in next(s for s in r6['per_q'] if int(s['Q'])==120)['query_results']}
    q080={int(r['query_id']):r for r in next(s for s in r6['per_q'] if int(s['Q'])==80)['query_results']}
    if set(q120)!=set(qids) or set(q080)!=set(qids):
        raise ValueError('R6 Q80/Q120 query IDs mismatch')

    # Recheck R6 independent file-level SEARCH (not only its summary JSON).
    native={}
    for q in (80,120,160):
        native[q]={}
        for qid in qids:
            rec=read_trace_file(qdir(q)/'traces'/f'q_{qid}.trace',qid,q)
            expected={80:q080,120:q120,160:q160}[q][qid]
            if tuple(expected['top10_ids'])!=rec['top10']:
                raise ValueError(f'Q{q} q={qid}: native trace file disagrees with R6 report')
            if rec['comparisons']!=expected['comparisons'] or len(rec['visited'])!=expected['visited_count']:
                raise ValueError(f'Q{q} q={qid}: native visited/comparisons mismatch')
            native[q][qid]=rec

    remaining={(qid,gt) for qid,gt in old_targets
               if gt not in native[160][qid]['top10']}
    if remaining!=EXPECTED_FIVE:
        raise ValueError(f'Persistent five target ID set changed: found {sorted(remaining)}')
    rescued=sum(gt in native[160][qid]['top10'] for qid,gt in old_targets)
    if rescued!=15:
        raise ValueError('Independent native 15/20 rescue does not replicate')
    events160=read_events(ROOT/'r47_r5_q160_events.stderr',set(qids),expected_repeats=5)
    events100=read_events(ROOT/'r47_events.stderr',set(qids),expected_repeats=5)

    base=Fbin(Path('data/sift1m.fbin'))
    queries=Fbin(Path('data/sift1m_queries.fbin'))
    gtfile=Ibin(Path('data/sift1m_gt.ibin'))
    items=[]
    try:
        for qid,target in sorted(remaining):
            gt10=gtfile.row(qid)[:10]
            if target not in gt10:
                raise ValueError(f'q={qid}: GT target={target} NOT in ground truth first 10')
            rank=gt10.index(target)+1
            qvec=queries.vector(qid)
            actual=exact_integer_l2(qvec,base.vector(target))
            native160=native[160][qid]
            native100=(r5_by_id[qid]['by_q']['100']['top10'])
            kth_native=int(native160['top10'][9])
            kth_dist=exact_integer_l2(qvec,base.vector(kth_native))
            delta=kth_dist-actual
            status160=summarize_events(events160[qid],target)
            status100=summarize_events(events100[qid],target)
            expanded160={int(e['node']) for e in events160[qid] if e.get('type')=='EXPAND'}
            if expanded160!=set(native160['visited']):
                raise ValueError(f'q={qid} Q160: R47 expanded ID set != independent native visited ID set')
            if target in native160['top10'] or target in native100:
                raise ValueError('Expected GT residual in neither Q100 nor Q160 Top10')
            presence={str(q):target in native[q][qid]['top10'] for q in (80,120,160)}
            if any(presence.values()):
                raise ValueError(f'q={qid} target={target}: unexpected recovery in other Q')
            items.append({'query_id':qid,'GT_id':target,'GT_rank_1based':rank,
                          'Q160_distance_squared_exact':actual,
                          'Q160_native_rank10_id':kth_native,
                          'Q160_native_rank10_distance_squared_exact':kth_dist,
                          'positive_margin_if_GT_strictly_closer_than_rank10':delta,
                          'distance_relation':('GT_STRICTLY_CLOSER' if delta>0 else
                                               'GT_TIED_AT_RANK10' if delta==0 else 'GT_FARTHER_CHECK_GT'),
                          'Q160_visited':len(native160['visited']),
                          'Q160_comparisons':native160['comparisons'],
                          'Q100_direct_target_events':status100,
                          'Q160_direct_target_events':status160,
                          'native_ID_absence_Q80_Q120_Q160':[80,120,160]})
    finally:
        gtfile.close()
        base.close()
        queries.close()

    out=ROOT/'r47_r7_q160_residual_offline.json'
    if out.exists():
        raise ValueError(f'Refusing overwrite existing output {out}')
    result={'audit':'R47_R7_Q160_RESIDUAL_NATIVE_TRACE_OFFLINE_PASS',
            'source_parity':'R47_R6_V2_INDEPENDENT_NATIVE_TOP10_PARITY_PASS',
            'graph_sha256':PIN,'Q160_initial_20_strict_missing_targets_rescued':rescued,
            'Q160_residual_count':len(items),'targets':items,
            'scope':'Observational GT-to-kth squared-L2 margins and direct node event audit; no graph hop/reachability check.',
            'limitations':['Event labels are observational and not unique causal attributions.',
                           'No direct target event is not proof of global disconnection or of absence of a directed graph path.',
                           '17 query IDs were preselected for native Q100 failures; do not extrapolate to all queries.',
                           'No source/graph/build edits and no new search performed.']}
    out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print('R47_R7_Q160_RESIDUAL_NATIVE_TRACE_OFFLINE_PASS')
    print('INDEPENDENT_R6_Q160_RESCUE',f'{rescued}/20')
    print('PERSISTENT_TARGETS', len(items))
    for t in items:
        print(f"query={t['query_id']} GT={t['GT_id']} GT_rank={t['GT_rank_1based']} "
              f"GT_d2={t['Q160_distance_squared_exact']} "
              f"native_kth_d2={t['Q160_native_rank10_distance_squared_exact']} "
              f"margin={t['positive_margin_if_GT_strictly_closer_than_rank10']} "
              f"Q100={t['Q100_direct_target_events']['label']} "
              f"Q160={t['Q160_direct_target_events']['label']}")
    print('OUTPUT',out)


def selftest():
    assert summarize_events([],100)['label']=='NO_DIRECT_TARGET_NODE_EVENT'
    es=[{'type':'DISCOVER','node':42},{'type':'SCORE','node':42,'distance':23.0},
        {'type':'CUTOFF_REJECT','node':42,'cutoff':19.0}]
    assert summarize_events(es,42)['label']=='TARGET_SCORE_AND_CUTOFF_REJECT_LOGGED'
    assert summarize_events(es,42)['event_counts']['SCORE']==1
    assert summarize_events([{'type':'MERGE_KEEP','node':3},
                              {'type':'BEAM_EVICT','node':3}],3)['label']=='TARGET_KEPT_AND_EVICTED_LOGGED'
    assert summarize_events([{'type':'EXPAND','node':3}],3)['label']=='TARGET_EXPANDED_BUT_NOT_RETURNED'
    assert summarize_events([{'type':'SCORE','node':4}],3)['label']=='NO_DIRECT_TARGET_NODE_EVENT'
    assert len(EXPECTED_FIVE)==5
    print('R47_R7_SELFTEST_PASS: event extraction, cutoff/eviction/expanded/absent labels, 5 pinned residuals')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=('selftest','audit'))
    args=p.parse_args()
    try:
        if args.action=='selftest':selftest()
        else:audit()
    except (OSError,ValueError,KeyError,IndexError,AssertionError) as e:
        print('R47_R7_FAIL:',e,file=sys.stderr)
        sys.exit(2)

if __name__=='__main__':main()
