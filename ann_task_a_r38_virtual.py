#!/usr/bin/env python3
"""H32-R38: PRE-REGISTERED read-only, matched-arc virtual ONE-EDGE replacement.

No graph is written. Scoring is a ONE-HOP held-out-query geometry proxy,
NOT ANN Recall, navigation, BUILD speed, or novelty evidence.
Requires ann_task_a_r37_coreslack.py from H32-R37 in the same folder.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
import os
import tempfile
from pathlib import Path
import struct
import numpy as np
from ann_task_a_r37_coreslack import Graph, Pool, Fbin, sha256, GRAPH_PIN, POOL_PIN

METHODS = ('random_union','nearest_union','nearest_pool','nearest_reverse',
           'max_angular_novelty','low_indegree_union')
VICTIMS = ('farthest','most_directionally_redundant')


def choose_candidates(u, out, poolids, inbound, X, indeg, seed):
    old = set(out.tolist())
    p = set(poolids.tolist()) - old
    r = set(inbound[u]) - old
    universe = np.asarray(sorted((p | r) - {u}), dtype=np.int64)
    nearpool = np.asarray(sorted(p - {u}), dtype=np.int64)
    nearrev = np.asarray(sorted(r - {u}), dtype=np.int64)
    x = np.asarray(X[u], dtype=np.float64)
    def dist(ids):
        if not len(ids):return np.empty(0, dtype=np.float64)
        v = np.asarray(X[ids], dtype=np.float64)-x
        return np.einsum('ij,ij->i',v,v)
    def near(ids):
        if not len(ids):return None
        D=dist(ids)
        return int(ids[np.lexsort((ids,D))[0]])
    answers = {m:None for m in METHODS}
    if not len(universe):return answers
    # Stable per-source RNG, independent of the order of the sampled source IDs.
    rng=np.random.default_rng(seed + 104729*int(u))
    answers['random_union']=int(universe[int(rng.integers(len(universe)))])
    answers['nearest_union']=near(universe)
    answers['nearest_pool']=near(nearpool)
    answers['nearest_reverse']=near(nearrev)
    answers['low_indegree_union']=int(universe[np.lexsort((universe, dist(universe), indeg[universe]))[0]])
    if len(out):
        V = np.asarray(X[universe], dtype=np.float64)-x
        W = np.asarray(X[out],dtype=np.float64)-x
        V /= np.maximum(np.linalg.norm(V,axis=1,keepdims=True),1e-30)
        W /= np.maximum(np.linalg.norm(W,axis=1,keepdims=True),1e-30)
        maxcos = np.max(V@W.T,axis=1)
        answers['max_angular_novelty']=int(universe[np.lexsort((universe,dist(universe),maxcos))[0]])
    else:
        answers['max_angular_novelty']=near(universe)
    return answers


def pick_victims(u, out, X):
    if len(out)==0:return {v:None for v in VICTIMS}
    x=np.asarray(X[u], dtype=np.float64)
    v=np.asarray(X[out], dtype=np.float64)-x
    dsq=np.einsum('ij,ij->i',v,v)
    idx=int(np.lexsort((out,-dsq))[0])
    if len(out)<2:
        redundant=idx
    else:
        vn=v/np.maximum(np.linalg.norm(v,axis=1,keepdims=True),1e-30)
        sim=vn@vn.T
        np.fill_diagonal(sim,-np.inf)
        redundancy=np.max(sim,axis=1)
        redundant=int(np.lexsort((out,-dsq,-redundancy))[0])
    return {'farthest':idx,'most_directionally_redundant':redundant}


def sqdist_to_queries(queries, X, ids):
    if not len(ids):return np.empty((len(queries),0), dtype=np.float64)
    q=np.asarray(queries,dtype=np.float64)
    v=np.asarray(X[ids],dtype=np.float64)
    qnorm=np.einsum('ij,ij->i',q,q)
    vnorm=np.einsum('ij,ij->i',v,v)
    ans=qnorm[:,None]+vnorm[None,:]-2*(q@v.T)
    return np.maximum(ans,0.)


def evaluate_source(u, chosen, victims, out, X, queries, normalizer_eps=1.e-9):
    if len(out)==0:return { (a,b): None for a in METHODS for b in VICTIMS }
    d=sqdist_to_queries(queries,X,out)
    before=np.sqrt(np.min(d,axis=1))
    dsrc=np.sqrt(sqdist_to_queries(queries,X,[u])[:,0])
    scale=np.maximum(dsrc,normalizer_eps)
    results={}
    for name in METHODS:
        c=chosen[name]
        cdis=np.sqrt(sqdist_to_queries(queries,X,[c])[:,0]) if c is not None else None
        for victim, idx in victims.items():
            if idx is None:
                results[(name,victim)]=None
                continue
            if c is None:
                # Missing candidate = untouched graph row, not an omitted observation.
                results[(name,victim)]=dict(delta_sum=0.,improved=0,harmed=0,
                    unchanged=len(queries),net_progress_changes=0,max_abs_delta=0.,
                    replaced=False)
                continue
            if len(out)==1:
                keep=np.full(len(queries),np.inf)
            else:
                keep=np.sqrt(np.min(np.delete(d,idx,axis=1),axis=1))
            after=np.minimum(keep,cdis)
            delta=(before-after)/scale # positive means virtual improvement
            # use a fixed absolute epsilon (meters for SIFT L2) to avoid float tie noise
            diff=before-after
            results[(name,victim)]=dict(
                delta_sum=float(np.sum(delta)),
                improved=int(np.count_nonzero(diff>1.e-8)),
                harmed=int(np.count_nonzero(diff< -1.e-8)),
                unchanged=int(np.count_nonzero(np.abs(diff)<=1.e-8)),
                net_progress_changes=int(np.count_nonzero(after<dsrc)-np.count_nonzero(before<dsrc)),
                max_abs_delta=float(np.max(np.abs(delta))),
                replaced=True,
            )
    return results


def audit(args):
    g=Graph(args.graph); p=Pool(args.pool,g.n,args.capacity); X=Fbin(args.fbin,g.n)
    q=Fbin(args.queries,args.queries_n)
    if X.d!=q.d:raise ValueError('Base and query dim differ')
    if not args.no_pins:
        if g.n != 1_000_000 or g.maxdeg!=32 or args.capacity!=160:
            raise ValueError('R26a header/cap mismatch')
        if sha256(args.graph)!=GRAPH_PIN or sha256(args.pool)!=POOL_PIN:
            raise ValueError('R26a SHA mismatch: STOP')
    if args.sources >g.n or args.targets >q.rows.shape[0]:raise ValueError('Sample > population')
    rng=np.random.default_rng(args.seed)
    sources=np.sort(rng.choice(g.n,args.sources,replace=False))
    qrng=np.random.default_rng(args.query_seed)
    qi=np.sort(qrng.choice(q.rows.shape[0],args.targets,replace=False))
    queries=q.rows[qi]
    indeg=g.indegrees()
    inbound=g.incoming_for_sample(sources)
    sums={f'{m}__{v}':dict(n_sources_with_replacement=0,n_pair_comparisons=0,delta_sum=0.,improved=0,harmed=0,unchanged=0,net_progress_changes=0,max_abs_delta=0.) for m in METHODS for v in VICTIMS}
    skipped={m:0 for m in METHODS}
    fullcap=0
    emptyout=0
    source_degrees=[]
    for u in sources:
        u=int(u)
        out=g.neighbors(u)
        if len(out)==0:emptyout+=1
        if len(out)==g.maxdeg:fullcap+=1
        source_degrees.append(int(len(out)))
        c=choose_candidates(u,out,p.candidates(u,g.n),inbound,X.rows,indeg,args.seed)
        for m in METHODS:
            if c[m] is None:skipped[m]+=1
        victim=pick_victims(u,out,X.rows)
        results=evaluate_source(u,c,victim,out,X.rows,queries)
        for (m,v), z in results.items():
            if z is None:continue
            s=sums[f'{m}__{v}']
            s['n_sources_with_replacement']+=int(z['replaced']);s['n_pair_comparisons']+=len(queries)
            for k in ('delta_sum','improved','harmed','unchanged','net_progress_changes'):
                s[k]+=z[k]
            s['max_abs_delta']=max(s['max_abs_delta'],z['max_abs_delta'])
    for m,v in ((m,v) for m in METHODS for v in VICTIMS):
        s=sums[f'{m}__{v}']; n=s['n_pair_comparisons']
        s['mean_normalized_best_neighbor_improvement']=(s['delta_sum']/n if n else None)
        s['fraction_improved']=(s['improved']/n if n else None)
        s['fraction_harmed']=(s['harmed']/n if n else None)
        s['fraction_unchanged']=(s['unchanged']/n if n else None)
    result={
      'audit':'CORE-SLACK-R1-VIRTUAL-REPLACE','status':'READ_ONLY_ONE_HOP_DIAGNOSTIC_NO_GRAPH_WRITTEN',
      'warning':'Single-edge virtual replacement, equal arc counts per row. NOT ANN Recall, QPS, BUILD speed, dynamic reachability, or valid novelty proof. No real query graph traversal.',
      'dataset':{'graph':str(args.graph),'pool':str(args.pool),'base_fbin':str(args.fbin),'query_fbin':str(args.queries),
                 'graph_sha':GRAPH_PIN if not args.no_pins else 'UNPINNED_TOY',
                 'pool_sha':POOL_PIN if not args.no_pins else 'UNPINNED_TOY',
                 'n':g.n,'base_dim':X.d,'query_count':q.rows.shape[0],'total_arcs':g.arcs},
      'protocol':{'sources':args.sources,'source_seed':args.seed,'targets':args.targets,'query_seed':args.query_seed,
                  'sample_source_ids_sha256':hashlib.sha256(sources.astype('<u4').tobytes()).hexdigest(),
                  'sample_query_ids_sha256':hashlib.sha256(qi.astype('<u4').tobytes()).hexdigest(),
                  'candidate_choices':list(METHODS),'victim_choices':list(VICTIMS),
                  'replacement_only':'One existing outgoing arc is removed if a new candidate is added. Degree and total arc counts preserved virtually.'},
      'sample':{'sources_full_at_cap':fullcap,'sources_nonfull':len(sources)-fullcap,'sources_zero_outdegree_excluded':emptyout,
                'mean_degree':float(np.mean(source_degrees)),'min_degree':min(source_degrees)},
      'no_candidates_per_method':skipped,'comparisons':sums,
    }
    if args.output:
        dst=Path(args.output);dst.parent.mkdir(parents=True,exist_ok=True)
        dst.write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n')
    print(json.dumps(result,indent=2,ensure_ascii=False))
    return result


def selftest():
    with tempfile.TemporaryDirectory() as td:
        td=Path(td)
        n=7;dim=2;cap=5
        X=np.array([[0,0],[1,0],[0,1],[2,0],[0,2],[3,1],[-1,-1]],dtype='<f4')
        q=X[:5]+np.array([.3,.2],dtype='<f4')
        f=td/'x.fbin'; k=td/'q.fbin'
        for path, arr in [(f,X),(k,q)]:
            path.write_bytes(struct.pack('<ii',len(arr),dim)+arr.tobytes())
        out=[[1,2],[0,3],[0,4],[1,5],[2],[3],[]]
        graph=td/'g.graph'; graph.write_bytes(struct.pack('<II',n,3)+np.array([len(x) for x in out],dtype='<u4').tobytes()+np.array([z for x in out for z in x],dtype='<u4').tobytes())
        pool=np.array([[1,2,3,4,-1],[0,3,2,-1,-1],[0,4,1,-1,-1],[1,5,0,-1,-1],[2,0,-1,-1,-1],[3,1,-1,-1,-1],[0,1,-1,-1,-1]],dtype='<i4')
        poolfile=td/'pool.i32';poolfile.write_bytes(pool.tobytes())
        args=argparse.Namespace(graph=graph,pool=poolfile,fbin=f,queries=k,queries_n=5,capacity=cap,
             no_pins=True,sources=n,targets=5,seed=3,query_seed=4,output=td/'out.json')
        result=audit(args)
        assert result['sample']['sources_full_at_cap']>=0
        assert result['dataset']['total_arcs']==10
        for z in result['comparisons'].values():
            ncomp=z['n_pair_comparisons']
            assert z['improved']+z['harmed']+z['unchanged']==ncomp
            assert z['mean_normalized_best_neighbor_improvement'] is None or math.isfinite(z['mean_normalized_best_neighbor_improvement'])
        assert (td/'out.json').exists()
        print('R38_SELFTEST_PASS: parsers, stable selection, equal arc virtual replacement, 12 comparisons, conservation')


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    sub=ap.add_subparsers(dest='command',required=True);sub.add_parser('selftest')
    a=sub.add_parser('audit')
    a.add_argument('--graph',required=True);a.add_argument('--pool',required=True)
    a.add_argument('--fbin',required=True);a.add_argument('--queries',required=True)
    a.add_argument('--queries-n',type=int,default=10000);a.add_argument('--capacity',type=int,default=160)
    a.add_argument('--sources',type=int,default=512);a.add_argument('--targets',type=int,default=64)
    a.add_argument('--seed',type=int,default=20261030);a.add_argument('--query-seed',type=int,default=20261101)
    a.add_argument('--output');a.add_argument('--no-pins',action='store_true')
    args=ap.parse_args()
    if args.command=='selftest':return selftest()
    if args.sources<=0 or args.targets<=0:ap.error('samples must be >0')
    audit(args)

if __name__=='__main__':main()
