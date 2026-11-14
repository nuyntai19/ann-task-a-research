#!/usr/bin/env python3
"""H32-R47-R8: read-only Q100/Q160 directed-hop & intermediate-event audit.

Purposes:
- Compare 15 recovered-vs-5-persistent strict-GT IDs on SAME SIFT1M R26a
  graph with Q100 and Q160 expansion sets.
- Find shortest directed paths of 0, 1, 2, or 3 hops from ANY expanded vertex.
  A hop-3 negative means ONLY 'not found within 3', never disconnected.
- For 2-hop witnesses u->v->GT, describe actual v decision trace events,
  distinguishing graph accessibility from beam selection/execution.
- Require R46 Q100 graph-2hop classification to replicate exactly.

Does not mutate graph, candidate pool, native code, or existing reports.
Does not infer a NEW graph-construction method or causal efficacy.
No new native search. Keep selected Q100-failing queries as a diagnostic case set.

  python3 ann_task_a_r47_r8_q160_topology.py selftest
  python3 -u ann_task_a_r47_r8_q160_topology.py audit \\
    > experiments/H47/r47_r8_audit.stdout \\
    2> experiments/H47/r47_r8_audit.stderr
"""
import argparse
from array import array
from collections import Counter, defaultdict
from hashlib import sha256
import json
import mmap
from pathlib import Path
import struct
import sys
from tempfile import TemporaryDirectory

ROOT = Path('experiments/H47')
GRAPH = Path('experiments/H32/H32_R26a_pool_20261029_172452_132314/dump.graph')
PIN = 'd497f6d19fff4b7db6436f960d036755e375be92483c03ec0b9ed61968d17bef'
OUT = ROOT / 'r47_r8_q160_topology.json'
FIVE = {(1715, 420244), (2711, 886706), (7167, 925061),
        (7935, 978211), (8083, 823939)}
STATUS_TYPES = ('EXPAND','DISCOVER','SEEN_SKIP','SCORE','CUTOFF_REJECT',
                'STAGE','MERGE_KEEP','MERGE_DROP','BEAM_EVICT','BATCH_WAIT')
MAX_VERTEX = 1_000_000


def file_hash(path):
    h = sha256()
    with path.open('rb') as f:
        for b in iter(lambda: f.read(4*1024*1024), b''):
            h.update(b)
    return h.hexdigest()


class DirectedGraph:
    """Verified read-only ParlayANN graph; degrees followed by packed IDs.

    The graph contains 1m degrees and 22.8m neighbors. The only derived
    in-memory index is an array('Q') of byte-independent neighbor offsets
    (~8MB), not a Python list of 23m edges. Do not blindly use on other n.
    """
    def __init__(self, path, expected_hash=None, expected_n=None):
        self.path = path
        self.f = None
        self.mm = None
        actual = file_hash(path)
        if expected_hash is not None and actual != expected_hash:
            raise ValueError(f'Graph SHA mismatch: {actual} != {expected_hash}')
        self.sha256 = actual
        try:
            self.f = path.open('rb')
            self.mm = mmap.mmap(self.f.fileno(), 0, access=mmap.ACCESS_READ)
            if len(self.mm) < 8:
                raise ValueError('Truncated graph header')
            self.n, self.cap = struct.unpack_from('<II', self.mm, 0)
            if expected_n is not None and self.n != expected_n:
                raise ValueError(f'Graph n changed: {self.n} != {expected_n}')
            if not (1 <= self.n <= MAX_VERTEX and 1 <= self.cap <= 8192):
                raise ValueError(f'Invalid graph header n={self.n},cap={self.cap}')
            self.ids_start = 8 + 4*self.n
            if len(self.mm) < self.ids_start:
                raise ValueError('Truncated graph degree array')
            cumulative = array('Q', [0])
            running = 0
            for u in range(self.n):
                degree = struct.unpack_from('<I', self.mm, 8 + u*4)[0]
                if degree > self.cap:
                    raise ValueError(f'Graph degree > cap at u={u}: {degree}>{self.cap}')
                running += degree
                cumulative.append(running)
            if len(self.mm) != self.ids_start + running*4:
                raise ValueError(f'Graph layout mismatch: file bytes={len(self.mm)}, '
                                 f'expected={self.ids_start + running*4}')
            self.offsets = cumulative
            self.arcs = running
        except BaseException:
            self.close()
            raise

    def neighbors(self, node):
        if not 0 <= node < self.n:
            raise ValueError(f'Invalid graph vertex id={node}')
        off = int(self.offsets[node])
        degree = int(self.offsets[node+1]-off)
        if not degree:
            return ()
        ids = struct.unpack_from('<'+str(degree)+'I', self.mm,
                                 self.ids_start + 4*off)
        if any(v >= self.n for v in ids):
            raise ValueError(f'Out-of-range graph neighbor at source={node}')
        return ids

    def close(self):
        if self.mm is not None:
            self.mm.close()
            self.mm = None
        if self.f is not None:
            self.f.close()
            self.f = None

    def __enter__(self): return self
    def __exit__(self,*_): self.close()


def event_index(events):
    result = defaultdict(set)
    for event in events:
        try:
            node = int(event.get('node', -1))
        except (TypeError, ValueError):
            continue
        if node < 0:
            continue
        typ = str(event.get('type','UNKNOWN'))
        result[node].add(typ)
    return result


def node_label(event_types, expanded):
    if expanded or 'EXPAND' in event_types:
        return 'EXPANDED'
    if 'MERGE_KEEP' in event_types and 'BEAM_EVICT' in event_types:
        return 'KEPT_THEN_EVICTED'
    if 'MERGE_DROP' in event_types:
        return 'MERGE_DROP'
    if 'CUTOFF_REJECT' in event_types:
        return 'CUTOFF_REJECT'
    if 'BEAM_EVICT' in event_types:
        return 'BEAM_EVICT'
    if 'MERGE_KEEP' in event_types:
        return 'MERGE_KEEP_UNEXPANDED'
    if 'SCORE' in event_types:
        return 'SCORED_OTHER'
    if 'DISCOVER' in event_types or 'SEEN_SKIP' in event_types:
        return 'DISCOVERED_OTHER'
    return 'NO_DIRECT_NODE_EVENT'


def path_audit(graph, expanded, targets, idx, hop_limit=3):
    """Find directed E -> t path <=3, with all distinct 2-hop v witnesses.

    At depth1, keep v->a parent. At depth2 keep w->v parent.
    Only query target adjacency for depth3 (do not populate 1m layer3).
    Returns bounded explanatory fields; no exhaustive all-path enumeration.
    """
    target_ids = set(targets)
    if not target_ids:
        return {}
    if not expanded:
        raise ValueError('Empty EXPAND set')
    for s in expanded:
        if not 0 <= s < graph.n:
            raise ValueError(f'Expanded vertex outside graph: {s}')
    if any(not 0 <= t < graph.n for t in target_ids):
        raise ValueError('GT target outside graph')
    starts = set(expanded)
    near1 = {}  # intermediate -> first expanded parent
    direct_sources = defaultdict(set)
    for source in sorted(starts):
        for v in graph.neighbors(source):
            if v in target_ids:
                direct_sources[v].add(source)
            near1.setdefault(v, source)

    second = {}  # second frontier vertex -> first-frontier parent
    two_hop = {t: {} for t in target_ids}  # t -> {intermediate v: one expanded u}
    for v, u in near1.items():
        for w in graph.neighbors(v):
            if w in target_ids:
                two_hop[w].setdefault(v, u)
            if w not in starts and w not in near1:
                second.setdefault(w, v)

    # Third-hop scan is ONLY needed if t was not reached within 0,1,2.
    need3 = {t for t in target_ids
             if t not in starts and not direct_sources[t] and not two_hop[t]}
    path3 = {}      # one concrete shortest path, no causal guarantee
    count3 = Counter()
    if hop_limit >= 3 and need3:
        for w, v in second.items():
            for t in graph.neighbors(w):
                if t in need3:
                    count3[t] += 1
                    path3.setdefault(t, [near1[v], v, w, t])
    results = {}
    for target in sorted(target_ids):
        if target in starts:
            hop = 0
            example = [target]
        elif direct_sources[target]:
            hop = 1
            example = [min(direct_sources[target]), target]
        elif two_hop[target]:
            hop = 2
            v = min(two_hop[target])
            example = [two_hop[target][v], v, target]
        elif target in path3:
            hop = 3
            example = path3[target]
        else:
            hop = None
            example = None
        witnesses = two_hop[target]
        classes = Counter(node_label(idx.get(v,set()), v in starts) for v in witnesses)
        examples = []
        for v in sorted(witnesses)[:5]:
            examples.append({'expanded_u':witnesses[v], 'intermediate_v':v,
                             'v_trace_events': sorted(idx.get(v,set())),
                             'v_trace_status':node_label(idx.get(v,set()), v in starts)})
        if example is not None:
            for a,b in zip(example,example[1:]):
                if b not in graph.neighbors(a):
                    raise ValueError(f'Bug: evidence path has missing edge {a}->{b}')
        results[target] = {
            'shortest_hops_from_expanded_at_most_3':hop,
            'shortest_path_example':example,
            'outgoing_edges_from_expanded_to_target':len(direct_sources[target]),
            'directed_2hop_witness_intermediates':len(witnesses),
            'twohop_witness_status_counts':dict(sorted(classes.items())),
            'twohop_witness_examples':examples,
            'directed_3hop_last_intermediate_count':count3[target],
            'hop3_example_intermediate_status':(
                [{'node':v,'status':node_label(idx.get(v,set()),v in starts),
                  'trace_events':sorted(idx.get(v,set()))} for v in example[1:3]]
                if hop==3 else [])
        }
    return results


def preflight():
    from ann_task_a_r47_r6_native_topk_v2 import (required_inputs,
          check_source_copy, read_trace_file, qdir)
    from ann_task_a_r47_r4_topk_parity_v2 import read_r45_search
    from ann_task_a_r47_r3_witness_audit import read_events

    if OUT.exists():
        raise ValueError(f'Output already exists; refusing to overwrite: {OUT}')
    qids, by_id = required_inputs()  # Includes fixed graph SHA check
    check_source_copy()
    r5=json.loads((ROOT/'r47_r5_q_sensitivity.json').read_text())
    r6=json.loads((ROOT/'R6_v2/r47_r6_v2_independent_native_parity.json').read_text())
    r7=json.loads((ROOT/'r47_r7_q160_residual_offline.json').read_text())
    if r5.get('audit')!='R47_R5_FIXED_GRAPH_Q_SENSITIVITY_PASS':
        raise ValueError('R47-R5 PASS missing')
    if r5.get('graph_sha256')!=PIN:
        raise ValueError('R47-R5 graph SHA mismatch')
    if r6.get('audit')!='R47_R6_V2_INDEPENDENT_NATIVE_TOP10_PARITY_PASS':
        raise ValueError('R47-R6 native parity PASS missing')
    if r7.get('audit')!='R47_R7_Q160_RESIDUAL_NATIVE_TRACE_OFFLINE_PASS':
        raise ValueError('R47-R7A PASS missing')
    if r6.get('repeats')!=5 or sorted(r6.get('selected_queries',[]))!=qids:
        raise ValueError('R47-R6 17 queries/5 repeat pin mismatch')
    rawtargets = r5['old_missing_gt_targets']
    targets = {(int(t['query_id']),int(t['gt_id'])):t for t in rawtargets}
    if len(targets)!=20 or set(t[0] for t in targets)!=set(qids):
        raise ValueError('Expected 20 unique selected Q100-missed GTs over 17 queries')
    r7_five={(int(t['query_id']), int(t['GT_id'])) for t in r7['targets']}
    if r7_five!=FIVE:
        raise ValueError('R7 residual five changed')
    n160={int(x['query_id']):x for x in next(s for s in r6['per_q'] if s['Q']==160)['query_results']}
    if set(n160)!=set(qids):
        raise ValueError('R6 Q160 ID set differs from 17 selected queries')
    native = {100:{},160:{}}
    for qid in qids:
        old=read_r45_search(Path('experiments/H45/native_q100_256/traces')/f'q_{qid}.trace',qid)
        newest=read_trace_file(qdir(160)/'traces'/f'q_{qid}.trace',qid,160)
        if tuple(n160[qid]['top10_ids']) != newest['top10']:
            raise ValueError(f'q={qid} R6 JSON and native Q160 trace disagree')
        if tuple(by_id[qid]['by_q']['100']['top10']) != old['beam'][:10]:
            raise ValueError(f'q={qid} R5 R45 Q100 native Top10 mismatch')
        if tuple(by_id[qid]['by_q']['160']['top10']) != newest['top10']:
            raise ValueError(f'q={qid} R5 and native Q160 Top10 mismatch')
        native[100][qid]={'visited':set(old['visited']),'top10':set(old['beam'][:10]),
                          'comparisons':old['comparisons']}
        native[160][qid]={'visited':set(newest['visited']),'top10':set(newest['top10']),
                          'comparisons':newest['comparisons']}
        for q in (100,160):
            if len(native[q][qid]['visited'])!=by_id[qid]['by_q'][str(q)]['visited_count']:
                raise ValueError(f'q={qid} Q{q} visited count differs R5')
    recovered = {(qid,gt) for qid,gt in targets if gt in native[160][qid]['top10']}
    if len(recovered)!=15 or set(targets)-recovered!=FIVE:
        raise ValueError(f'R47-R8 rescue target set differs R7: {len(recovered)}/20')
    return qids, targets, native, read_events


def audit():
    qids, targets, native, read_events = preflight()
    events={}
    for q, path in ((100,ROOT/'r47_events.stderr'),
                    (160,ROOT/'r47_r5_q160_events.stderr')):
        events[q]=read_events(path,set(qids),expected_repeats=5)
        if set(events[q]) != set(qids):
            raise ValueError(f'Q{q} event query set not exact')
        for qid in qids:
            exp={int(e['node']) for e in events[q][qid] if e.get('type')=='EXPAND'}
            if exp!=native[q][qid]['visited']:
                raise ValueError(f'Q{q} q={qid} R47 EXPAND vs native visited set differs')
    print('R47_R8_PREFLIGHT_PASS graph_pin, 17x5 native parity, events Q100/Q160',flush=True)
    items=[]
    with DirectedGraph(GRAPH,expected_hash=PIN,expected_n=MAX_VERTEX) as graph:
        if graph.cap!=32 or graph.arcs!=22797630:
            raise ValueError(f'R26a graph degree/arc pin mismatch: cap={graph.cap} arcs={graph.arcs}')
        for qid in qids:
            asked={gt for a,gt in targets if a==qid}
            for q in (100,160):
                raw=events[q][qid]
                expanded=native[q][qid]['visited']
                idx=event_index(raw)
                found=path_audit(graph,expanded,asked,idx)
                for target,details in sorted(found.items()):
                    original=targets[(qid,target)]
                    if not isinstance(original.get('graph_twohop'), bool):
                        raise ValueError(f'Q100 R46 twohop flag not boolean at q={qid} target={target}')
                    row={'query_id':qid,'GT_id':target,'Q':q,
                         'Q160_group':('PERSISTENT_5' if (qid,target) in FIVE else 'RESCUED_15'),
                         'native_top10_contains_GT':target in native[q][qid]['top10'],
                         'native_visited_count':len(expanded),
                         'native_comparisons':native[q][qid]['comparisons'],
                         'R46_graph_twohop_Q100':bool(original['graph_twohop']),
                         'target_trace_node_event_types':sorted(idx.get(target,set())),
                         **details}
                    items.append(row)
            print(f'R47_R8_QUERY_DONE {qid} targets={len(asked)}',flush=True)

    # R46 already verified exactly 18 two-hop and 2 non-two-hop targets at Q100.
    old = [x for x in items if x['Q']==100]
    new = [x for x in items if x['Q']==160]
    assert len(old)==len(new)==20
    for x in old:
        is_2hop = x['shortest_hops_from_expanded_at_most_3']==2
        if is_2hop!=x['R46_graph_twohop_Q100']:
            raise ValueError(f"R46 mismatch Q100 q={x['query_id']} target={x['GT_id']}: "
                             f"hop={x['shortest_hops_from_expanded_at_most_3']} "
                             f"R46={x['R46_graph_twohop_Q100']}")
    if sum(x['shortest_hops_from_expanded_at_most_3']==2 for x in old)!=18:
        raise ValueError('R46 expected exactly 18/20 two-hop graph paths Q100')
    if sum(x['native_top10_contains_GT'] for x in new)!=15:
        raise ValueError('R6 Q160 native rescue count differs')
    print('R47_R8_R46_Q100_DIRECTED_2HOP_REPLICATION_PASS 18/20',flush=True)

    summary={}
    for q in (100,160):
        summary[str(q)]={}
        for group in ('PERSISTENT_5','RESCUED_15'):
            sub=[x for x in items if x['Q']==q and x['Q160_group']==group]
            counts=Counter(('>3_or_absent' if x['shortest_hops_from_expanded_at_most_3'] is None
                            else str(x['shortest_hops_from_expanded_at_most_3'])) for x in sub)
            wc=Counter()
            for x in sub: wc.update(x['twohop_witness_status_counts'])
            summary[str(q)][group]={
                'targets':len(sub),'shortest_hops_distribution':dict(sorted(counts.items())),
                'twohop_witness_total':sum(x['directed_2hop_witness_intermediates'] for x in sub),
                'twohop_witness_statuses':dict(sorted(wc.items()))}
            print(f"R47_R8_Q{q}_{group} shortest_hops={dict(sorted(counts.items()))} "
                  f"twohop_intermediates={summary[str(q)][group]['twohop_witness_total']} "
                  f"status_counts={dict(sorted(wc.items()))}",flush=True)

    print('R47_R8_RESIDUAL_DETAIL_Q160',flush=True)
    for x in new:
        if x['Q160_group'] != 'PERSISTENT_5': continue
        print(f"q={x['query_id']} GT={x['GT_id']} "
              f"shortest_hops={x['shortest_hops_from_expanded_at_most_3']} "
              f"twohop_witnesses={x['directed_2hop_witness_intermediates']} "
              f"witness_status={x['twohop_witness_status_counts']}",flush=True)

    output={'audit':'R47_R8_DIRECTED_TOPOLOGY_WITNESS_OFFLINE_PASS',
            'protocol':{'graph_sha256':PIN,'n':MAX_VERTEX,'max_degree':32,
                        'arcs':22797630,'queries':17,'Q_values':[100,160],
                        'preselected_GT_targets':20,'native_parity':'R47_R6_V2_INDEPENDENT_NATIVE_TOP10_PARITY_PASS',
                        'R46_Q100_directed_twohop_replication':18},
            'summary':summary,'per_target_Q100_Q160':items,
            'interpretation_limits':[
                'Shortest directed path means from ANY ALREADY expanded native search vertex; it is not an entry-point-to-target path or original query search trajectory.',
                'A graph 2-hop/3-hop witness is structural, not proof search would expand a candidate with its Q cutoff or ordering.',
                'Unknown within <=3 hops does not mean disconnected or impossible to reach by longer paths.',
                'Q160 rescued group is selected by recovery outcome; direct hop distribution is descriptive/selection-conditioned, not an unbiased causal control.',
                'No direct target event may indicate search did not score it; it is not proof construction omitted a useful edge.',
                'Twenty targets were selected via Q100 failures and holdout GT. Do not use their IDs to add/replace graph edges in a proposed training/builder method.',
                'No new graph, build, or ANN search executed. No novelty or search speedup established.']}
    OUT.write_text(json.dumps(output,ensure_ascii=False,indent=2)+'\n')
    print('R47_R8_DIRECTED_TOPOLOGY_WITNESS_OFFLINE_PASS',flush=True)
    print('OUTPUT',OUT,flush=True)


def selftest():
    with TemporaryDirectory() as td:
        path=Path(td)/'toy.graph'
        # n=9, cap=3: graph 0->1->2->3 and 4->5->3 and 6->7.
        rows=((1,4),(2,),(3,),(8,),(5,),(3,), (7,),(),())
        arr=b''.join(struct.pack('<I',len(r)) for r in rows)
        edges=b''.join(struct.pack('<' + str(len(r)) + 'I',*r) if r else b'' for r in rows)
        path.write_bytes(struct.pack('<II',9,3)+arr+edges)
        with DirectedGraph(path,expected_hash=file_hash(path),expected_n=9) as g:
            assert g.n==9 and g.arcs==8 and g.cap==3
            assert g.neighbors(0)==(1,4)
            # Starting from 0: 1,4 at hop1; 2,5 at hop2; 3 at hop3; 8 at hop4.
            events={1:{'CUTOFF_REJECT'},4:{'MERGE_KEEP','BEAM_EVICT'},2:{'MERGE_DROP'}}
            r=path_audit(g,{0},{0,1,2,3,8,7},events)
            assert r[0]['shortest_hops_from_expanded_at_most_3']==0
            assert r[1]['shortest_hops_from_expanded_at_most_3']==1
            assert r[2]['shortest_hops_from_expanded_at_most_3']==2
            assert r[3]['shortest_hops_from_expanded_at_most_3']==3
            assert r[7]['shortest_hops_from_expanded_at_most_3'] is None
            assert r[8]['shortest_hops_from_expanded_at_most_3'] is None
            assert r[3]['shortest_path_example']==[0,1,2,3]
            assert r[2]['twohop_witness_status_counts']=={'CUTOFF_REJECT':1}
            assert node_label({'MERGE_KEEP','BEAM_EVICT'},False)=='KEPT_THEN_EVICTED'
            assert node_label({'EXPAND'},True)=='EXPANDED'
            assert event_index([{'node':1,'type':'SCORE'},{'node':1,'type':'CUTOFF_REJECT'}])[1] == {'SCORE','CUTOFF_REJECT'}
        # Layout/degree/header guards, and file SHA pin.
        with path.open('ab') as f:f.write(b'corruption')
        try:
            DirectedGraph(path,expected_n=9)
            raise AssertionError('Expected graph file-size mismatch')
        except ValueError as e:
            assert 'layout mismatch' in str(e)
    print('R47_R8_SELFTEST_PASS: graph offsets/SHA/layout, 0-3 directed hops, witness events, Q100 twohop-control machinery',flush=True)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=('selftest','audit'))
    args=p.parse_args()
    try:
        if args.action=='selftest': selftest()
        else: audit()
    except (OSError,ValueError,KeyError,IndexError,AssertionError,ImportError) as e:
        print('R47_R8_FAIL:',e,file=sys.stderr)
        sys.exit(2)

if __name__=='__main__':main()
