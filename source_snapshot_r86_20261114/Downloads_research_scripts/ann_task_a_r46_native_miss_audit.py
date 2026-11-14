#!/usr/bin/env python3
"""R46: postprocess R45 native ParlayANN traces; no ANN searches, no graph edits.

Distinguish per-query strict Top10 misses from native tie-aware misses, and
measure graph adjacency of strict-missing GT nodes from expanded/remaining
frontier, and at two directed hops from expanded nodes.
"""
from __future__ import annotations
import argparse, collections, hashlib, json, mmap, os, pathlib, struct

GRAPH_SHA='d497f6d19fff4b7db6436f960d036755e375be92483c03ec0b9ed61968d17bef'
N=1_000_000
Q=100
K=10

def sha256(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for block in iter(lambda:f.read(4<<20),b''):h.update(block)
    return h.hexdigest()

def parse_ids(x):
    if x and not x.endswith(','): raise ValueError('Missing trailing comma for trace ID list')
    return [int(t) for t in x.split(',') if t]

def read_trace(path):
    S=[];E=[]
    for line in pathlib.Path(path).read_text().splitlines():
        t=line.split('|')
        if len(t)==8 and t[0]=='SEARCH':
            _,i,q,k,re,cmps,front,visited=t
            S.append(dict(qid=int(i),Q=int(q),k=int(k),rerank=int(re),cmps=int(cmps),frontier=parse_ids(front),visited=parse_ids(visited)))
        elif len(t)==7 and t[0]=='EVAL':
            _,i,q,k,returned,gt10,allowed=t
            E.append(dict(qid=int(i),Q=int(q),k=int(k),returned=parse_ids(returned),gt10=parse_ids(gt10),allowed=parse_ids(allowed)))
        else:raise ValueError(f'Unexpected trace line in {path}: {line[:100]!r}')
    if len(S)!=5 or len(E)!=5:raise ValueError(f'Expected 5 SEARCH and 5 EVAL in {path}, got {len(S)},{len(E)}')
    if S!=[S[0]]*5 or E!=[E[0]]*5:raise ValueError(f'R45 native repeat mismatch: {path}')
    s,e=S[0],E[0]
    if not (s['qid']==e['qid'] and s['Q']==e['Q']==Q and s['k']==e['k']==K):raise ValueError('Protocol/ID mismatch')
    if s['rerank']:raise ValueError('Quantized/rerank source path not handled')
    if len(s['frontier'])!=len(set(s['frontier'])) or len(s['visited'])!=len(set(s['visited'])):raise ValueError('Duplicate frontier/visited IDs')
    if e['returned']!=s['frontier'][:K]:raise ValueError('Returned order != frontier Top-k')
    if len(e['returned'])!=K or len(e['gt10'])!=K or len(set(e['gt10']))!=K:raise ValueError('Expected K unique IDs')
    if not set(e['gt10']).issubset(set(e['allowed'])):raise ValueError('Allowed GT excludes strict GT10')
    return s,e

class Graph:
    def __init__(self,path,pinned=True):
        self.path=path
        if pinned and sha256(path)!=GRAPH_SHA:raise ValueError('R26a graph SHA differs from pinned record')
        self.f=open(path,'rb')
        self.buf=mmap.mmap(self.f.fileno(),0,access=mmap.ACCESS_READ)
        if len(self.buf)<8:raise ValueError('Graph file too small')
        self.n,self.cap=struct.unpack_from('<II',self.buf,0)
        if pinned and (self.n!=N or self.cap!=32):raise ValueError('R26a graph shape mismatch')
        self.deg=memoryview(self.buf)[8:8+4*self.n].cast('I')
        if len(self.deg)!=self.n:raise ValueError('Truncated degree array')
        self.offsets=[0]*(self.n+1)
        for i in range(self.n):
            deg=int(self.deg[i]);
            if deg>self.cap:raise ValueError(f'Invalid outdegree {deg} for {i}')
            self.offsets[i+1]=self.offsets[i]+deg
        if len(self.buf)!=8+4*self.n+4*self.offsets[-1]:raise ValueError('Unexpected graph file length')
        self.edge_start=8+4*self.n
    def neighbors(self,u):
        if u<0 or u>=self.n:raise ValueError(f'Node out of range {u}')
        a=self.edge_start+4*self.offsets[u];b=self.edge_start+4*self.offsets[u+1]
        return struct.unpack_from('<'+'I'*(self.offsets[u+1]-self.offsets[u]),self.buf,a)
    def close(self):
        self.deg.release();self.buf.close();self.f.close()

def audit_one(qid, s, e, g):
    returned=set(e['returned']);gt=set(e['gt10']);allowed=set(e['allowed'])
    visited=set(s['visited']);front=set(s['frontier']);pending=front-visited
    strict_hits=len(returned&gt);native_hits=len(returned&allowed)
    strict_misses=[t for t in e['gt10'] if t not in returned]
    found=set()
    pending_near=set()
    horizon2=set()
    # Avoid any graph expansion for the majority of queries with no strict miss.
    if strict_misses:
        for v in visited:
            found.update(g.neighbors(v))
        for v in pending:
            pending_near.update(g.neighbors(v))
        # 2-hop 'horizon' from ALL truly expanded nodes. Does not imply the
        # intermediary was expanded or that the native beam would keep it.
        if any(t not in found for t in strict_misses):
            for v in found:
                if v>=g.n:raise ValueError('Invalid adjacency target')
                horizon2.update(g.neighbors(v))
    rows=[]
    for t in strict_misses:
        if t in visited:cat='expanded_but_not_returned'
        elif t in front:cat='final_frontier_outside_k'
        elif t in found:cat='adjacent_to_expanded_but_not_returned'
        else:cat='not_adjacent_to_expanded'
        rows.append(dict(GT=t,category=cat,
                         adjacent_to_unexpanded_final_frontier=t in pending_near,
                         graph_twohop_from_expanded=t in found or t in horizon2,
                         strict_gt_rank=e['gt10'].index(t)+1))
    return dict(query_id=qid, strict_hits=strict_hits,native_tie_hits=native_hits,
                native_deficit=K-native_hits,strict_misses=K-strict_hits,
                tie_credits=native_hits-strict_hits,
                tied_extra_returned=sorted((returned-gt)&allowed),
                visited_count=len(visited),final_frontier_count=len(front),
                pending_final_frontier_count=len(pending),misses=rows)

def build(report,trace_dir,g):
    if report.get('audit')!='R45_PINNED_NATIVE_QUERY_TRACE_DIAGNOSTIC':raise ValueError('Not R45 report')
    if report.get('parity')!='PASS_RECALL_VISITED_COMPARISONS' or not report.get('all_traced_queries_deterministic_across_5_repeats'):
        raise ValueError('R45 native parity/repeat gate not passed')
    proto=report['protocol']
    if proto['graph_sha256']!=GRAPH_SHA or proto['Q']!=Q or proto['k']!=K or proto['n_base']!=N:
        raise ValueError('R45 R26a/Q100/k10 protocol mismatch')
    x=report['query_sample'];ids=x['selected_query_ids']
    h=hashlib.sha256(struct.pack('<'+'I'*len(ids),*ids)).hexdigest()
    if h!=x['sample_sha256'] or len(ids)!=x['sample_count'] or len(ids)!=len(set(ids)):
        raise ValueError('R45 sampled-query list SHA/count mismatch')
    if len(list(pathlib.Path(trace_dir).glob('q_*.trace')))!=len(ids):raise ValueError('Trace file count mismatch')
    per=[];ct=collections.Counter();old={v['query_id']:v for v in report['missed_query_details']}
    if len(old)!=report['counts']['queries_with_any_strict_miss']:raise ValueError('R45 missed query row count mismatch')
    missing_categories=collections.Counter();missing_nativequery_categories=collections.Counter()
    n_frontier=collections.Counter(); horizon=collections.Counter()
    for i in ids:
        s,e=read_trace(pathlib.Path(trace_dir)/f'q_{i}.trace')
        if s['qid']!=i or e['qid']!=i:raise ValueError('Wrong query trace file')
        a=audit_one(i,s,e,g)
        if a['strict_misses']:
            b=old.get(i)
            if b is None or a['strict_hits']!=b['strict_hits'] or a['native_tie_hits']!=b['native_tie_eligible_hits']:
                raise ValueError('Mismatch with original R45 per-query summary')
            if sorted((j['GT'],j['category']) for j in a['misses'])!=sorted((j['GT'],j['category']) for j in b['misses']):
                raise ValueError('Changed R45 exposure category')
        elif i in old:raise ValueError('Unexpected R45 missed-query row')
        ct['traced_queries']+=1;ct['strict_hits']+=a['strict_hits'];ct['native_tie_hits']+=a['native_tie_hits']
        ct['strict_misses']+=a['strict_misses'];ct['native_deficit']+=a['native_deficit'];ct['tie_credits']+=a['tie_credits']
        ct['queries_strict_miss']+=bool(a['strict_misses']);ct['queries_native_miss']+=bool(a['native_deficit'])
        ct['queries_strict_miss_but_native_full']+=bool(a['strict_misses'] and not a['native_deficit'])
        ct['queries_strict_miss_and_native_miss']+=bool(a['strict_misses'] and a['native_deficit'])
        for j in a['misses']:
            cat=j['category'];missing_categories[cat]+=1
            if a['native_deficit']:missing_nativequery_categories[cat]+=1
            if cat=='not_adjacent_to_expanded':
                n_frontier['all_strict_nonadj']+=1
                n_frontier['adjacent_to_unexpanded_frontier']+=j['adjacent_to_unexpanded_final_frontier']
                horizon['all_strict_nonadj']+=1
                horizon['twohop_from_expanded']+=j['graph_twohop_from_expanded']
                if a['native_deficit']:
                    n_frontier['native_miss_query_strict_nonadj']+=1
                    n_frontier['native_miss_query_adjacent_to_unexpanded_frontier']+=j['adjacent_to_unexpanded_final_frontier']
                    horizon['native_miss_query_strict_nonadj']+=1
                    horizon['native_miss_query_twohop_from_expanded']+=j['graph_twohop_from_expanded']
        if a['strict_misses']:per.append(a)
    exp=report['counts']
    for k,ref in [('strict_hits','strict_GT10_hit'),('native_tie_hits','native_tie_eligible_hit'),('strict_misses',None),('queries_strict_miss','queries_with_any_strict_miss')]:
        if ref and ct[k]!=exp[ref]:raise ValueError(f'R45 global total mismatch: {k}')
    if ct['strict_misses']!=K*ct['traced_queries']-ct['strict_hits']:raise ValueError('Strict conservation violated')
    if ct['native_deficit']!=K*ct['traced_queries']-ct['native_tie_hits']:raise ValueError('Native conservation violated')
    if ct['tie_credits']!=ct['strict_misses']-ct['native_deficit']:raise ValueError('Tie conservation violated')
    for c,v in missing_categories.items():
        if exp.get(c)!=v:raise ValueError(f'R45 original category count mismatch {c}')
    return dict(audit='R46_OFFLINE_NATIVE_TIE_AND_GRAPH_EXPOSURE_RECHECK',
                protocol=dict(graph_sha256=GRAPH_SHA,R45_query_sample_sha256=x['sample_sha256'],Q=Q,k=K,traced_queries=len(ids),native_search_rerun=False),
                counts=dict(ct),original_strict_missing_categories=dict(missing_categories),
                strict_missing_categories_within_queries_that_still_fail_native=dict(missing_nativequery_categories),
                nonadjacent_subcategories=dict(n_frontier),nonadjacent_twohop_horizon=dict(horizon),
                missed_query_details=sorted(per,key=lambda a:(-a['native_deficit'],-a['strict_misses'],a['query_id'])),
                interpretation={
                    'strict_misses':'R45 first10 GT ID mismatch counts, not native tie-aware recall misses',
                    'native_deficit':'k minus returned IDs in tie-eligible GT set, aggregated by query',
                    'tie_credits':'Returned extra IDs from GT ranks11..100 at the exact kth GT distance; a query-level matching credit, not one-to-one causal rescue of a particular GT10 ID',
                    'strict_missing_categories_within_queries_that_still_fail_native':'Strict-GT ID categories restricted to queries with native deficit >0; NOT one-to-one category counts of the native missing slots',
                    'adjacent_to_unexpanded_final_frontier':'Graph adjacency from any final frontier node that is not in expanded visited set; NO proof it was scored/queued',
                    'graph_twohop_from_expanded':'Directed <=2-hop graph horizon from expanded nodes; does NOT prove beam search would traverse the intermediate or score the GT',
                    'no_algorithm_teleology':'This is query diagnostics, not evidence of novelty or speedup'})

def selftest():
    # Six points, degrees and variable adjacency serialization.
    from tempfile import TemporaryDirectory
    with TemporaryDirectory() as t:
        p=pathlib.Path(t)/'graph';n=16;cap=3;adj=[[1],[2,3],[4],[5],[],[]]+[[] for _ in range(10)]
        with open(p,'wb') as f:
            f.write(struct.pack('<II',n,cap));f.write(struct.pack('<'+'I'*n,*map(len,adj)))
            for a in adj:
                if a:f.write(struct.pack('<'+'I'*len(a),*a))
        g=Graph(p,pinned=False)
        assert g.neighbors(0)==(1,) and g.neighbors(1)==(2,3)
        S=dict(visited=[0,1],frontier=[0,1,2,3],qid=7,Q=Q,k=K)
        E=dict(returned=[0,1,2,3,4,5,10,11,12,13],gt10=[0,1,2,3,4,5,10,11,12,15],allowed=[0,1,2,3,4,5,10,11,12,15,13])
        # One strict GT missing, but native full credit due to tie at boundary.
        a=audit_one(7,S,E,g)
        assert a['strict_hits']==9 and a['native_tie_hits']==10 and a['native_deficit']==0 and a['tie_credits']==1
        # GT 15 not seen by any expanded edge, but missing ID alone isn't a native miss.
        assert a['misses'][0]['GT']==15 and a['misses'][0]['category']=='not_adjacent_to_expanded'
        assert a['misses'][0]['adjacent_to_unexpanded_final_frontier'] is False
        # End-to-end R45 JSON + 5-repeat trace fixture, with one *native full*
        # query despite a strict miss, and one genuine native-deficit query.
        original_n,original_sha=globals()['N'],globals()['GRAPH_SHA']
        globals()['N']=n;globals()['GRAPH_SHA']=sha256(p)
        traces=pathlib.Path(t)/'traces';traces.mkdir()
        ids=[7,8];samp_sha=hashlib.sha256(struct.pack('<II',*ids)).hexdigest()
        gt10=list(range(10));returned1=list(range(9))+[10];returned2=list(range(9))+[11]
        sample={'selected_query_ids':ids,'sample_count':2,'sample_sha256':samp_sha}
        oldmiss=[]
        for i,ret,allowed,nhit in [(7,returned1,list(range(11)),10),(8,returned2,gt10,9)]:
            def csv(values):return ''.join(str(x)+',' for x in values)
            pair=(f'SEARCH|{i}|100|10|0|21|{csv(ret)}|0,1,\n'
                  f'EVAL|{i}|100|10|{csv(ret)}|{csv(gt10)}|{csv(allowed)}\n')
            (traces/f'q_{i}.trace').write_text(pair*5)
            oldmiss.append({'query_id':i,'strict_hits':9,'native_tie_eligible_hits':nhit,
                            'misses':[{'GT':9,'category':'not_adjacent_to_expanded'}]})
        fake={'audit':'R45_PINNED_NATIVE_QUERY_TRACE_DIAGNOSTIC',
              'parity':'PASS_RECALL_VISITED_COMPARISONS',
              'all_traced_queries_deterministic_across_5_repeats':True,
              'protocol':{'graph_sha256':globals()['GRAPH_SHA'],'Q':100,'k':10,'n_base':n},
              'query_sample':sample,
              'counts':{'strict_GT10_hit':18,'native_tie_eligible_hit':19,
                        'queries_with_any_strict_miss':2,'not_adjacent_to_expanded':2},
              'missed_query_details':oldmiss}
        result=build(fake,traces,g)
        assert result['counts']['strict_misses']==2 and result['counts']['native_deficit']==1
        assert result['counts']['tie_credits']==1 and result['counts']['queries_native_miss']==1
        assert result['counts']['queries_strict_miss_but_native_full']==1
        assert result['strict_missing_categories_within_queries_that_still_fail_native']['not_adjacent_to_expanded']==1
        globals()['N']=original_n;globals()['GRAPH_SHA']=original_sha
        g.close()
        bad=pathlib.Path(t)/'bad';bad.write_bytes(p.read_bytes()+b'bad')
        try:Graph(bad,pinned=False)
        except ValueError:pass
        else:raise AssertionError('Trailing bytes not rejected')
    print('R46_SELFTEST_PASS: graph encoding, complete R45 JSON/trace fixtures, tie rescue, native deficit and file integrity')

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    sub=ap.add_subparsers(dest='mode',required=True);sub.add_parser('selftest')
    p=sub.add_parser('audit')
    p.add_argument('--r45',required=True);p.add_argument('--traces',required=True);p.add_argument('--graph',required=True);p.add_argument('--output',required=True)
    a=ap.parse_args()
    if a.mode=='selftest':return selftest()
    report=json.loads(pathlib.Path(a.r45).read_text())
    g=Graph(a.graph,pinned=True)
    try:out=build(report,a.traces,g)
    finally:g.close()
    path=pathlib.Path(a.output);path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(out,indent=2,ensure_ascii=False)+'\n')
    print('R46_OFFLINE_TRACE_AUDIT_PASS')
    print('COUNTS',json.dumps(out['counts'],sort_keys=True))
    print('NATIVE_QUERY_STRICT_CATEGORIES',json.dumps(out['strict_missing_categories_within_queries_that_still_fail_native'],sort_keys=True))
    print('NONADJ_FINAL_FRONTIER',json.dumps(out['nonadjacent_subcategories'],sort_keys=True))
    print('NONADJ_2HOP',json.dumps(out['nonadjacent_twohop_horizon'],sort_keys=True))
    print('OUTPUT',path)

if __name__=='__main__':main()
