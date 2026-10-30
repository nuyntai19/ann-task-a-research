#!/usr/bin/env python3
"""H32-R41: read-only exact base-anchor top-k pool-vs-final-graph attribution.

Samples SIFT1M BASE vectors, not heldout queries. Computes exact Float64 L2
neighbors by scanning all base points. No graph building/search/Recall claims.
Requires ann_task_a_r37_coreslack.py beside this file for pinned R26a parsers.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import tempfile
from pathlib import Path
import struct
import numpy as np
from ann_task_a_r37_coreslack import Graph, Pool, Fbin, sha256, GRAPH_PIN, POOL_PIN


def topk_scan(X, src: int, k: int, block_size: int) -> tuple[np.ndarray, np.ndarray]:
    """Exact Float64 squared L2; deterministic global-ID ties; bounded working RAM.

    Sorting all boundary-score ties in each block ensures global-ID tie break.
    Full data scan (not ANN search), O(n*d) work per sampled source.
    """
    n, dim = X.shape
    if n <= k:
        raise ValueError('Need n > k to exclude the source')
    target = np.asarray(X[src], dtype=np.float64)
    best_ids = np.empty(0, dtype=np.int64)
    best_d2 = np.empty(0, dtype=np.float64)
    for start in range(0, n, block_size):
        end = min(n, start + block_size)
        diff = np.asarray(X[start:end], dtype=np.float64).copy()
        diff -= target
        dist2 = np.einsum('ij,ij->i', diff, diff, optimize=False)
        if start <= src < end:
            dist2[src - start] = np.inf
        # Exact tie-safe k-smallest on this block (including all boundary ties).
        local_k = min(k, end - start)
        threshold = float(np.partition(dist2, local_k - 1)[local_k - 1])
        select = np.flatnonzero(dist2 <= threshold)
        order = np.lexsort((select + start, dist2[select]))[:local_k]
        local_ids = (select[order] + start).astype(np.int64)
        local_d2 = dist2[select[order]]
        ids = np.concatenate((best_ids, local_ids))
        d2 = np.concatenate((best_d2, local_d2))
        sorted_idx = np.lexsort((ids, d2))[:k]
        best_ids, best_d2 = ids[sorted_idx], d2[sorted_idx]
    if not (len(best_ids) == k and np.isfinite(best_d2).all()):
        raise AssertionError('Exact top-k failed')
    return best_ids, best_d2


def wilson_bootstrap(data: np.ndarray, rngseed: int, iterations: int = 1000):
    """Source-cluster bootstrap CI for mean fractions; descriptive only."""
    if len(data) < 2:
        return None
    rng = np.random.default_rng(rngseed)
    a = np.asarray(data, dtype=np.float64)
    picks = rng.integers(0, len(a), size=(iterations, len(a)))
    means = a[picks].mean(axis=1)
    return [round(float(np.quantile(means, .025)), 7), round(float(np.quantile(means, .975)), 7)]


def compute(args):
    graph, pool = Graph(args.graph), None
    if not args.no_pins:
        gsha = sha256(args.graph)
        psha = sha256(args.pool)
        if gsha != GRAPH_PIN or psha != POOL_PIN:
            raise ValueError('R26a graph/pool SHA mismatch; refusing audit')
    else:
        gsha = sha256(args.graph)
        psha = sha256(args.pool)
    if args.expected_n and graph.n != args.expected_n:
        raise ValueError('Unexpected graph n')
    if args.expected_maxdeg and graph.maxdeg != args.expected_maxdeg:
        raise ValueError('Unexpected graph max_degree')
    pool = Pool(args.pool, graph.n, args.capacity)
    X = Fbin(args.fbin, graph.n).rows
    if args.expected_dim and X.shape[1] != args.expected_dim:
        raise ValueError('Unexpected vector dimension')
    if not np.isfinite(np.asarray(X[:min(1000, graph.n)])).all():
        raise ValueError('Non-finite input sample')
    if args.sources_file:
        chosen = np.loadtxt(args.sources_file, dtype=np.int64, ndmin=1)
        if len(chosen) != len(set(chosen.tolist())) or not np.all((chosen >= 0) & (chosen < graph.n)):
            raise ValueError('Source-file duplicates/out-of-range IDs')
        sources = np.sort(chosen)
    else:
        rng = np.random.default_rng(args.seed)
        sources = np.sort(rng.choice(graph.n, size=min(args.sources, graph.n), replace=False)).astype(np.int64)
    idhash=hashlib.sha256(np.asarray(sources, dtype='<u4').tobytes()).hexdigest()
    kmax=max(args.k)
    details=[]
    print(f'R41 starting: {len(sources)} anchors; graph={graph.n} vectors; exact scan float64; k={args.k}', flush=True)
    for idx, u in enumerate(sources):
        uid=int(u)
        exact_ids, exact_d2 = topk_scan(X, uid, kmax, args.chunk)
        row_pool = pool.candidates(uid, graph.n)
        row_graph = graph.neighbors(uid)
        P, G = set(map(int,row_pool)), set(map(int,row_graph))
        if uid in G or len(G) != len(row_graph) or np.any(row_graph >= graph.n):
            raise ValueError('Graph self/duplicate/invalid edge in sampled row')
        rec={'u': uid, 'outdegree':len(G), 'pool_count':len(P), 'graph_outside_pool':len(G-P),
             'knn10_ids':list(map(int,exact_ids[:min(10,len(exact_ids))])),
             'knn10_dist2':list(map(float,exact_d2[:min(10,len(exact_d2))]))}
        for k in args.k:
            GT=set(map(int,exact_ids[:k]))
            in_p=GT&P
            in_g=GT&G
            rec[f'k{k}']={'pool_hit':len(in_p), 'graph_hit':len(in_g),
                'captured_but_pruned':len(in_p-G),
                'graph_recovered_outside_pool':len(in_g-P),
                'lost_before_pool':k-len(in_p),
                'graph_missing':k-len(in_g),
                'top1_in_pool':int(exact_ids[0] in P),
                'top1_in_graph':int(exact_ids[0] in G)}
            assert (k-len(in_g)) == (k-len(in_p)) + len(in_p-G) - len(in_g-P)
        details.append(rec)
        if (idx+1)%8==0 or idx+1==len(sources):
            print(f'  {idx+1}/{len(sources)} anchor scans completed', flush=True)

    groups={}
    all_idx=np.arange(len(details))
    groups['uniform_sample_all']=all_idx
    groups['sample_outdegree_full']=np.array([i for i,s in enumerate(details) if s['outdegree']==graph.maxdeg],dtype=int)
    groups['sample_outdegree_slack']=np.array([i for i,s in enumerate(details) if s['outdegree']<graph.maxdeg],dtype=int)
    summary={}
    for name, indexes in groups.items():
        if len(indexes)==0:
            summary[name]={'n':0};continue
        group=[details[int(i)] for i in indexes]
        piece={'n':len(group),'mean_outdegree':sum(s['outdegree'] for s in group)/len(group),
               'mean_pool_count':sum(s['pool_count'] for s in group)/len(group),
               'graph_outside_pool_positions':sum(s['graph_outside_pool'] for s in group)}
        for k in args.k:
            z=[s[f'k{k}'] for s in group]
            ag={x:sum(m[x] for m in z) for x in ['pool_hit','graph_hit','captured_but_pruned','graph_recovered_outside_pool','lost_before_pool','graph_missing','top1_in_pool','top1_in_graph']}
            ag['gt_total']=k*len(group)
            ag['pool_coverage']=round(ag['pool_hit']/ag['gt_total'],7)
            ag['graph_coverage']=round(ag['graph_hit']/ag['gt_total'],7)
            ag['pool_to_graph_coverage_loss_pp']=round(100*(ag['pool_hit']-ag['graph_hit'])/ag['gt_total'],4)
            ag['bootstrap_source_CI_95_graph_coverage']=wilson_bootstrap(np.array([v['graph_hit']/k for v in z]),args.seed+19+k)
            ag['bootstrap_source_CI_95_pool_coverage']=wilson_bootstrap(np.array([v['pool_hit']/k for v in z]),args.seed+91+k)
            piece[f'k{k}']=ag
        summary[name]=piece
    output={'audit':'R41_BASE_ANCHOR_EXACT_KNN_POOL_VS_GRAPH','status':'READ_ONLY_BASE_ANCHORS_NOT_QUERY_RECALL',
        'protocol':{'source_count':len(sources),'seed':args.seed,'source_ids_sha256':idhash,
                    'source_file':str(args.sources_file) if args.sources_file else None,
                    'n':graph.n,'dim':X.shape[1],'chunk':args.chunk,'k_list':args.k,
                    'distance':'squared_L2_float64_over_original_fbin_values_tie_global_id',
                    'full_scan_per_anchor':True},
        'provenance':{'graph_sha256':gsha,'pool_sha256':psha,
                      'graph_path':str(args.graph),'pool_path':str(args.pool),
                      'fbin_path':str(args.fbin),'fbin_length':Path(args.fbin).stat().st_size},
        'summary':summary,'sample_sources':details,
        'limitations':['Exact base-point ground truth is not heldout ANN query Recall@10.',
          'Only sampled outgoing graph edges and sampled pool rows are evaluated.',
          'A graph kNN miss is not necessarily a search failure; diverse long edges can be helpful.',
          'No BUILD wall/RSS, final graph modification, PiPNN II replication, or algorithmic novelty proven.',
          'Bootstrap is over sampled anchors conditional on this dataset, not over independent datasets.']}
    if args.output:
        dest=Path(args.output);dest.parent.mkdir(parents=True,exist_ok=True)
        dest.write_text(json.dumps(output,indent=2,ensure_ascii=False)+'\n')
    print(json.dumps({'audit':output['audit'],'status':output['status'],'protocol':output['protocol'],
       'summary':output['summary'],'provenance':{'graph_sha256':gsha,'pool_sha256':psha}},indent=2),flush=True)
    return output


def selftest():
    with tempfile.TemporaryDirectory() as td:
        td=Path(td)
        X=np.array([[0.,0.],[1.,0.],[2.,0.],[3.,0.],[4.,0.],[5.,0.],[6.,0.],[7.,0.]],dtype='<f4')
        fbin=td/'synthetic.fbin'
        fbin.write_bytes(struct.pack('<ii',len(X),2)+X.tobytes())
        # Point 0 exact top2: 1,2. Pool 1,2,3. Graph keeps 1,3 (prunes true neighbor 2).
        edges=[[1,3],[0,2],[1,3],[2,4],[3,5],[4,6],[5,7],[6]]
        graph=td/'synthetic.graph'
        graph.write_bytes(struct.pack('<II',8,3)+np.array(list(map(len,edges)),dtype='<u4').tobytes()+np.array([v for row in edges for v in row],dtype='<u4').tobytes())
        pool=td/'synthetic.candidates.i32'
        P=np.full((8,4),-1,dtype='<i4')
        P[0,:3]=[1,2,3]
        for i in range(1,8):
            c=[j for j in range(8) if j != i][:3]
            P[i,:len(c)]=c
        pool.write_bytes(P.tobytes())
        samples=td/'sample.txt';samples.write_text('0\n')
        cfg=argparse.Namespace(graph=graph,pool=pool,fbin=fbin,capacity=4,
            sources=1,sources_file=samples,seed=20261103,k=[1,2],chunk=3,
            expected_n=8,expected_maxdeg=3,expected_dim=2,no_pins=True,output=td/'out.json')
        report=compute(cfg)
        a=report['summary']['uniform_sample_all']
        assert a['k2']['pool_hit']==2 and a['k2']['graph_hit']==1
        assert a['k2']['captured_but_pruned']==1 and a['k2']['lost_before_pool']==0
        assert a['k1']['graph_hit']==1
        assert report['sample_sources'][0]['knn10_ids'][:2]==[1,2]
        # Deterministic tie globally by ID, with tie across 2 chunks.
        X2=np.array([[0.,0.],[1.,0.],[-1.,0.],[0.,1.]],dtype='<f4')
        ids,dist=topk_scan(X2,0,3,2)
        assert ids.tolist()==[1,2,3] and np.allclose(dist,[1.,1.,1.])
        print('R41_SELFTEST_PASS: exact source anchors, pool-vs-graph attribution, deterministic ties, pinned format, conservation')


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    sub=ap.add_subparsers(dest='command',required=True)
    sub.add_parser('selftest')
    a=sub.add_parser('audit')
    for name in ['graph','pool','fbin']:
        a.add_argument('--'+name,required=True)
    a.add_argument('--capacity',type=int,default=160)
    a.add_argument('--sources',type=int,default=32)
    a.add_argument('--sources-file')
    a.add_argument('--seed',type=int,default=20261103)
    a.add_argument('--k',type=int,nargs='+',default=[10,32])
    a.add_argument('--chunk',type=int,default=16384)
    a.add_argument('--expected-n',type=int,default=1000000)
    a.add_argument('--expected-dim',type=int,default=128)
    a.add_argument('--expected-maxdeg',type=int,default=32)
    a.add_argument('--no-pins',action='store_true',help='ONLY for synthetic fixtures; never use on R26a')
    a.add_argument('--output',required=True)
    args=ap.parse_args()
    if args.command=='selftest': selftest();return
    if args.sources<=0 or args.chunk<8 or not args.k or min(args.k)<1 or len(set(args.k))!=len(args.k):
        ap.error('Invalid sample size/chunk/k list')
    if not args.no_pins and (args.expected_n!=1000000 or args.expected_maxdeg!=32 or args.capacity!=160):
        ap.error('R26a source pins need n=1m, degree32, capacity160')
    compute(args)

if __name__=='__main__':main()
