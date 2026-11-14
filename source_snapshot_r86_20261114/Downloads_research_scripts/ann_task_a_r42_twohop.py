#!/usr/bin/env python3
"""H32-R42: READ-ONLY exact base-anchor Top10 graph 2-hop reachability audit.

Inputs are the same pinned R26a ParlayANN graph, pool and SIFT1M base vectors,
plus R41's validated anchor Top10 exact neighbor IDs. No searches/BUILD/Recall.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import struct
import tempfile
from pathlib import Path
import numpy as np
from ann_task_a_r37_coreslack import Graph, Pool, Fbin, sha256, GRAPH_PIN, POOL_PIN


def sha_source_ids(sources):
    ids = np.sort(np.asarray(sources, dtype='<u4'))
    return hashlib.sha256(ids.tobytes()).hexdigest()


def sq_l2(a, b):
    v = np.asarray(a, dtype=np.float64) - np.asarray(b, dtype=np.float64)
    return float(np.dot(v, v))


def check_r41(data, G, P, X, gsha, psha):
    if data.get('audit') != 'R41_BASE_ANCHOR_EXACT_KNN_POOL_VS_GRAPH':
        raise ValueError('Input JSON is not an R41 exact-anchor report')
    pr = data['protocol']
    if pr['n'] != G.n or pr['dim'] != X.shape[1]:
        raise ValueError('R41 n/dim mismatch')
    if 10 not in pr['k_list']:
        raise ValueError('R41 must contain exact k=10')
    if 'provenance' in data:
        pv = data['provenance']
        if pv['graph_sha256'] != gsha or pv['pool_sha256'] != psha:
            raise ValueError('R41 vs R42 graph/pool SHA mismatch')
    entries = data['sample_sources']
    sources = [int(x['u']) for x in entries]
    if len(entries) != pr['source_count'] or len(set(sources)) != len(sources):
        raise ValueError('R41 source count/uniqueness mismatch')
    if sha_source_ids(sources) != pr['source_ids_sha256']:
        raise ValueError('R41 source ID SHA mismatch')
    for e in entries:
        u=int(e['u']); gt=list(map(int,e['knn10_ids']))
        if len(gt) != 10 or len(set(gt)) != 10 or u in gt or min(gt)<0 or max(gt)>=G.n:
            raise ValueError(f'Invalid exact top10 for source {u}')
    return entries


def audit_one(u, exact10, G, P, X):
    out = set(map(int, G.neighbors(u)))
    pool = set(map(int, P.candidates(u, G.n)))
    # Each cached adjacency is read only once per source.
    v_to_neighbors={v:set(map(int,G.neighbors(v))) for v in out}
    d0={t:sq_l2(X[u], X[t]) for t in exact10}
    details=[]
    for t in exact10:
        direct = t in out
        if direct:
            category='graph_direct'
        elif t in pool:
            category='pool_captured_but_pruned'
        else:
            category='missing_before_pool'
        via2 = direct or any(t in neighbors for neighbors in v_to_neighbors.values())
        # Strict monotonicity to the *base target point t* is required at the
        # intermediate hop. This is not a proof about query-time navigability.
        mono2 = direct or any(
            (t in neighbors and sq_l2(X[v],X[t]) < d0[t])
            for v,neighbors in v_to_neighbors.items()
        )
        assert not mono2 or via2
        details.append({'target':t,'category':category,'in_pool':t in pool,
                        'direct':direct,'reachable_within_2_hops':via2,
                        'monotone_to_base_target_within_2_hops':mono2})
    baseline = {'pool_hit':sum(x['in_pool'] for x in details),
                'graph_hit':sum(x['direct'] for x in details),
                'captured_but_pruned':sum(x['category']=='pool_captured_but_pruned' for x in details),
                'lost_before_pool':sum(x['category']=='missing_before_pool' for x in details)}
    return {'source':u,'outdegree':len(out),'records':details,'baseline':baseline}


def summarize(results, maxdeg):
    def bucket(subset):
        data=[r for s in subset for r in s['records']]
        summary={'sources':len(subset),'gt_total':len(data),'direct':sum(r['direct'] for r in data),
                 'reachable_within_2_hops':sum(r['reachable_within_2_hops'] for r in data),
                 'monotone_to_base_target_within_2_hops':sum(r['monotone_to_base_target_within_2_hops'] for r in data)}
        for category in ['pool_captured_but_pruned','missing_before_pool','graph_direct']:
            rows=[r for r in data if r['category']==category]
            summary[category]={ 'n':len(rows),
                'reachable_2hop':sum(r['reachable_within_2_hops'] for r in rows),
                'monotone_2hop':sum(r['monotone_to_base_target_within_2_hops'] for r in rows)}
        for name in ['direct','reachable_within_2_hops','monotone_to_base_target_within_2_hops']:
            summary[name+'_fraction'] = round(summary[name]/len(data),7) if data else None
        return summary
    return {'all':bucket(results),
            'full_outdegree':bucket([r for r in results if r['outdegree']==maxdeg]),
            'slack_outdegree':bucket([r for r in results if r['outdegree']<maxdeg])}


def compute(args):
    G=Graph(args.graph)
    if not args.no_pins and (G.n != 1_000_000 or G.maxdeg!=32):
        raise ValueError('Not pinned R26a graph n1m/degree32')
    gsha=sha256(args.graph); psha=sha256(args.pool)
    if not args.no_pins and (gsha!=GRAPH_PIN or psha!=POOL_PIN):
        raise ValueError('Pinned graph or candidate pool SHA does not match R26a')
    P=Pool(args.pool,G.n,args.capacity)
    f=Fbin(args.fbin,G.n)
    X=f.rows
    if not args.no_pins and X.shape[1]!=128:
        raise ValueError('Pinned SIFT1M dimension not 128')
    input_json=json.loads(Path(args.r41).read_text())
    entries=check_r41(input_json,G,P,X,gsha,psha)
    result=[]
    for i,e in enumerate(entries):
        u=int(e['u']); y=audit_one(u,[int(t) for t in e['knn10_ids']],G,P,X)
        old=e['k10']; new=y['baseline']
        for key,oldkey in [('pool_hit','pool_hit'),('graph_hit','graph_hit'),('captured_but_pruned','captured_but_pruned'),('lost_before_pool','lost_before_pool')]:
            if new[key]!=old[oldkey]:
                raise ValueError(f'R41 vs R42 source {u} mismatch on {key}: {new[key]} vs {old[oldkey]}')
        result.append(y)
        if (i+1)%8==0 or i+1==len(entries):
            print(f'checked {i+1}/{len(entries)} base anchors',flush=True)
    summary=summarize(result,G.maxdeg)
    assert summary['all']['gt_total']==10*len(entries)
    assert (summary['all']['graph_direct']['n']+
            summary['all']['pool_captured_but_pruned']['n']+
            summary['all']['missing_before_pool']['n']==summary['all']['gt_total'])
    report={'audit':'R42_EXACT_BASE_TOP10_2HOP_RESCUE',
            'status':'READ_ONLY_BASE_ANCHORS_NOT_SEARCH_RECALL',
            'protocol':{'n':G.n,'dim':X.shape[1],
                        'r41_source_count':len(entries),
                        'r41_source_ids_sha256':input_json['protocol']['source_ids_sha256'],
                        'topk':10,'hops':2,'directed':True,
                        'monotonicity':'strict Float64 squared L2 distance to exact BASE target at intermediate vertex',
                        'candidate_pool':'R26a original fixed capacity rows',
                        'graph_sha256':gsha,'pool_sha256':psha},
            'summary':summary,
            'limitations':['2-hop topological reachability and monotonic base-target witness are NOT query Recall, beam-search accessibility or multi-hop routing quality.',
                           'No heldout query in calculation, no graph modification, and the 32-anchor original sample is small.',
                           'Short paths do not imply a search algorithm finds them; local kNN loss need not be an ANN quality loss.'],
            'per_source':result}
    if args.output:
        dst=Path(args.output);dst.parent.mkdir(parents=True,exist_ok=True)
        dst.write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n')
    print(json.dumps({'audit':report['audit'],'status':report['status'],
                      'protocol':report['protocol'],'summary':summary},indent=2),flush=True)
    return report


def selftest():
    with tempfile.TemporaryDirectory() as td:
        root=Path(td)
        X=np.column_stack((np.arange(12,dtype=np.float32),np.zeros(12,dtype=np.float32)))
        f=root/'toy.fbin';f.write_bytes(struct.pack('<ii',len(X),2)+X.tobytes())
        edges=[[1,3],[2],[1,3],[4],[5],[4,6],[7],[8],[9],[10],[11],[10]]
        g=root/'toy.graph'
        g.write_bytes(struct.pack('<II',12,3)+np.array([len(a) for a in edges],dtype='<u4').tobytes()+np.array([x for row in edges for x in row],dtype='<u4').tobytes())
        pools=np.full((12,4),-1,dtype='<i4')
        pools[0]=[1,2,3,4]  # source 0 exact top10 are 1..10
        p=root/'toy.candidates.i32';p.write_bytes(pools.tobytes())
        G=Graph(g);P=Pool(p,G.n,4);vec=Fbin(f,G.n)
        row=audit_one(0,list(range(1,11)),G,P,vec.rows)
        assert row['baseline']=={'pool_hit':4,'graph_hit':2,'captured_but_pruned':2,'lost_before_pool':6}
        ids={x['target']:x for x in row['records']}
        assert ids[1]['direct'] and ids[3]['direct']
        assert ids[2]['reachable_within_2_hops'] and ids[2]['monotone_to_base_target_within_2_hops']
        assert ids[4]['reachable_within_2_hops'] and ids[4]['monotone_to_base_target_within_2_hops']
        assert not ids[5]['reachable_within_2_hops']
        # Independently validate format SHA, per-source summary, and R41 JSON guard.
        from ann_task_a_r41_attribution import topk_scan
        top10,_=topk_scan(vec.rows,0,10,3)
        assert top10.tolist()==list(range(1,11))
        k10={'pool_hit':4,'graph_hit':2,'captured_but_pruned':2,'lost_before_pool':6}
        sample={'audit':'R41_BASE_ANCHOR_EXACT_KNN_POOL_VS_GRAPH',
                'protocol':{'source_count':1,'source_ids_sha256':sha_source_ids([0]),'n':12,'dim':2,'k_list':[10,32]},
                'provenance':{'graph_sha256':sha256(g),'pool_sha256':sha256(p)},
                'sample_sources':[{'u':0,'knn10_ids':list(range(1,11)),'k10':k10}]}
        r=root/'r41.json';r.write_text(json.dumps(sample))
        cfg=argparse.Namespace(graph=g,pool=p,fbin=f,r41=r,capacity=4,no_pins=True,output=root/'out.json')
        report=compute(cfg)
        assert report['summary']['all']['graph_direct']['n']==2
        assert report['summary']['all']['pool_captured_but_pruned']['n']==2
        assert report['summary']['all']['missing_before_pool']['n']==6
        assert report['summary']['all']['reachable_within_2_hops']==4
        assert report['summary']['all']['monotone_to_base_target_within_2_hops']==4
        print('R42_SELFTEST_PASS: two-hop rescue, monotone base-target witness, R41 conservation, SHA guards')


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    sp=ap.add_subparsers(dest='cmd',required=True)
    sp.add_parser('selftest')
    p=sp.add_parser('audit')
    p.add_argument('--r41',required=True)
    p.add_argument('--graph',required=True)
    p.add_argument('--pool',required=True)
    p.add_argument('--fbin',required=True)
    p.add_argument('--capacity',type=int,default=160)
    p.add_argument('--no-pins',action='store_true',help='Only for synthetic fixtures; NEVER for real R26a')
    p.add_argument('--output')
    args=ap.parse_args()
    if args.cmd=='selftest':selftest()
    else:compute(args)
if __name__=='__main__':main()
