#!/usr/bin/env python3
"""R85-A2b: read-only post-hoc analysis of nine archived H85 A2 graphs.

No ANN BUILD and no SEARCH. Inputs are only opened for reading; JSON outputs
are stored under a NEW experiments/H85/r85_a2b_readonly/analysis_* directory.

Analyses:
  1. Per-graph measured recall/comparisons interpolated on an efficient frontier;
     per-arm median/range (n=3), plus per-repetition paired ratios.
  2. Exact global in/out degree distributions and source-aligned degree changes.
  3. Directed reachability from native search entry vertex 0.
  4. Sampled directed-edge Euclidean lengths and neighbor-set overlap.
  5. For sampled source nodes, exact base-wide 1st and 10th NN distances,
     and outgoing edge lengths normalized by the true NN distance.

Interpreting these graph-level summaries as causal proof about the *input*
reservoir would be unsound. No live intermediate candidate stream is observed.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
import os
import sys
from collections import deque
from pathlib import Path
from statistics import median

ROOT = Path.home() / 'ann-task-a'
A2_RUN = ROOT / 'experiments/H85/r85_a2_edge_match/runs_20261109-224526'
BASE = ROOT / 'data/sift1m.fbin'
OUTROOT = ROOT / 'experiments/H85/r85_a2b_readonly'
ARMS = ('B64', 'EDGE_R', 'EDGE_ALPHA')
TARGETS = (0.76, 0.89, 0.96, 0.99, 0.998)
SEED = 20261109


def fail(msg):
    raise RuntimeError('R85_A2B_FAIL_CLOSED ' + str(msg))


def numpy():
    try:
        import numpy as np
    except ImportError:
        fail('Requires numpy: run python3 -c "import numpy" (do not modify the graphs)')
    return np


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda: f.read(2 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def atomic_json(p, obj):
    p = Path(p)
    tmp = p.with_name(p.name + '.tmp')
    tmp.write_text(json.dumps(obj, indent=2, ensure_ascii=False, allow_nan=False) + '\n', encoding='utf8')
    tmp.replace(p)


def fbin_info(path, np):
    path = Path(path)
    if not path.is_file():
        fail('Missing SIFT base '+str(path))
    with path.open('rb') as f:
        n, d = __import__('struct').unpack('<II', f.read(8))
    if (n,d) != (1_000_000, 128) or path.stat().st_size != 8+4*n*d:
        fail(f'Unexpected base dimensions/file size: {n}x{d}, {path.stat().st_size}')
    return np.memmap(path, dtype='<f4', mode='r', offset=8, shape=(n,d))


class Graph:
    """Native PiPNN saved graph: u32 header, u32 degrees, flat u32 destinations."""
    def __init__(self, path, np, expected_arcs=None, expected_degree=None):
        self.path = Path(path)
        self.np = np
        if not self.path.is_file():
            fail('Missing graph '+str(self.path))
        if self.path.stat().st_size < 8 + 4*1_000_000:
            fail('Truncated graph '+str(self.path))
        self.mm = np.memmap(self.path, dtype='<u4', mode='r')
        self.n, self.maxdeg = (int(x) for x in self.mm[:2])
        if self.n != 1_000_000 or not 1 <= self.maxdeg <= 64:
            fail(f'Bad n/maxdegree {self.n}/{self.maxdeg} in {self.path}')
        if expected_degree is not None and self.maxdeg != int(expected_degree):
            fail('Wrong max-degree '+str(self.path))
        self.deg = self.mm[2:2+self.n]
        if np.any(self.deg > self.maxdeg):
            fail('Out-degree > graph bound '+str(self.path))
        self.off = np.empty(self.n+1, dtype=np.int64)
        self.off[0] = 0
        np.cumsum(self.deg, dtype=np.int64, out=self.off[1:])
        self.m = int(self.off[-1])
        self.edges = self.mm[2+self.n:]
        if self.m != len(self.edges) or (expected_arcs is not None and self.m != int(expected_arcs)):
            fail('Bad graph edge count or file length '+str(self.path))
        if np.any(self.edges >= self.n):
            fail('Destination out of bounds '+str(self.path))

    def adjacency(self, i):
        return self.edges[self.off[i]:self.off[i+1]]


def load_a2(run):
    run = Path(run)
    br,qr = run/'build_results.json',run/'quality/quality_results.json'
    summ = run/'build_summary.json'
    if not all(p.is_file() for p in (br,qr,summ,run/'manifest.json')):
        fail('A2 source manifests/results not complete: '+str(run))
    builds=json.loads(br.read_text())
    quality=json.loads(qr.read_text())
    if len(builds)!=9 or len(quality)!=9*25:
        fail(f'Unexpected A2 rows builds={len(builds)}, quality={len(quality)}')
    bmap={}
    for r in builds:
        key=(r['arm'],int(r['rep']))
        if key in bmap or key[0] not in ARMS or key[1] not in (1,2,3):
            fail('Duplicate/unknown A2 build record '+str(key))
        bmap[key]=r
    if set(bmap)!={(arm,rep) for arm in ARMS for rep in (1,2,3)}:
        fail('A2 missing graph')
    qmap={}
    for r in quality:
        key=(r['arm'],int(r['rep']),int(r['beam']))
        if key in qmap or (key[0],key[1]) not in bmap:
            fail('Duplicate/unknown quality record '+str(key))
        qmap[key]=r
    if len(qmap)!=225 or len({k[2] for k in qmap})!=25:
        fail('Unexpected quality beam arrangement')
    if set(qmap)!={(arm,rep,b) for arm in ARMS for rep in (1,2,3) for b in {k[2] for k in qmap}}:
        fail('Missing per-rep per-beam quality row')
    for key,r in bmap.items():
        p=Path(r['graph'])
        if not p.is_file() or sha256(p)!=r['graph_sha256']:
            fail('Graph missing or SHA mismatch '+str(key))
    return bmap,qmap


def monotone_frontier(rows):
    """Remove dominated search points; interpolate only within measured bounds."""
    points=[]
    for r in rows:
        rec,cmp=float(r['recall']),float(r['avg_cmps'])
        if not (0<=rec<=1 and cmp>0 and math.isfinite(cmp)):
            fail('Bad measured recall/comparisons')
        points.append((cmp,rec,int(r['beam'])))
    points.sort()
    result=[]
    best=-1.0
    for c,r,b in points:
        if r > best+1.e-10:
            result.append((r,c,b))
            best=r
    return result


def interpolate(frontier,target):
    if not frontier:
        return {'status':'NO_POINTS'}
    if target < frontier[0][0]-1e-10:
        return {'status':'BELOW_MIN_MEASURED_RECALL'}
    if target > frontier[-1][0]+1e-10:
        return {'status':'ABOVE_MAX_MEASURED_RECALL'}
    for p in frontier:
        if abs(p[0]-target) <= 1e-10:
            return {'status':'EXACT_MEASURED', 'comparisons':p[1], 'beams':[p[2],p[2]], 'recall_bracket':[p[0],p[0]]}
    for lo,hi in zip(frontier,frontier[1:]):
        if lo[0] <= target <= hi[0] and hi[0]>lo[0]:
            frac=(target-lo[0])/(hi[0]-lo[0])
            return {'status':'INTERPOLATED', 'comparisons':lo[1]+frac*(hi[1]-lo[1]),
                    'beams':[lo[2],hi[2]], 'recall_bracket':[lo[0],hi[0]],
                    'bracket_width_pp':100*(hi[0]-lo[0])}
    return {'status':'NO_VALID_BRACKET'}


def interp_report(qmap):
    all_rows=[]
    curves={}
    for arm in ARMS:
        for rep in (1,2,3):
            rows=[v for (a,r,b),v in qmap.items() if (a,r)==(arm,rep)]
            curves[(arm,rep)]=monotone_frontier(rows)
    for target in TARGETS:
        row={'target_recall':target,'arms':{},'paired_ratios':{}}
        for arm in ARMS:
            rep_results=[]
            for rep in (1,2,3):
                v=interpolate(curves[(arm,rep)],target)
                rep_results.append({'rep':rep,**v})
            vals=[v['comparisons'] for v in rep_results if 'comparisons' in v]
            row['arms'][arm]={'per_rep':rep_results,'covered_reps':len(vals)}
            if vals:
                row['arms'][arm]['comparisons_min_med_max']=[float(min(vals)),float(median(vals)),float(max(vals))]
        for arm in ('EDGE_R','EDGE_ALPHA'):
            ratios=[]
            for rep in (1,2,3):
                a=row['arms'][arm]['per_rep'][rep-1]
                b=row['arms']['B64']['per_rep'][rep-1]
                if 'comparisons' in a and 'comparisons' in b:
                    ratios.append(float(a['comparisons']/b['comparisons']))
            row['paired_ratios'][arm]={'n':len(ratios),'min_med_max':([min(ratios),median(ratios),max(ratios)] if ratios else None)}
        all_rows.append(row)
    return all_rows


def quart(np,values):
    arr=np.asarray(values,dtype=np.float64)
    if arr.size==0:return {'count':0}
    return {'count':int(arr.size),'min':float(np.min(arr)),'p10':float(np.quantile(arr,.10)),
            'p50':float(np.quantile(arr,.50)),'p90':float(np.quantile(arr,.90)),
            'p95':float(np.quantile(arr,.95)),'p99':float(np.quantile(arr,.99)),
            'max':float(np.max(arr))}


def degree_report(np,g):
    deg=g.deg
    inh=np.bincount(g.edges,minlength=g.n)
    if len(inh)!=g.n:
        fail('indegree shape mismatch')
    return {'n':g.n,'arcs':g.m,'degree_bound':g.maxdeg,
            'out_hist':np.bincount(deg,minlength=65).tolist(),
            'in_hist_quantiles':quart(np,inh),'out_degree_quantiles':quart(np,deg),
            'in_zero':int(np.count_nonzero(inh==0)),
            'out_zero':int(np.count_nonzero(deg==0)),
            'out_lt8':int(np.count_nonzero(deg<8)),
            'out_mean':float(np.mean(deg))}


def degree_paired(np,base,control):
    a=base.deg.astype(np.int16)
    b=control.deg.astype(np.int16)
    diff=b-a
    count=np.bincount((diff+64).astype(np.uint8),minlength=129)
    ha=np.bincount(a,minlength=65).astype(float)/base.n
    hb=np.bincount(b,minlength=65).astype(float)/base.n
    return {'control_minus_B64_mean':float(np.mean(diff)),
            'fraction_control_more_degree':float(np.mean(diff>0)),
            'fraction_control_less_degree':float(np.mean(diff<0)),
            'fraction_equal_degree':float(np.mean(diff==0)),
            'total_variation_out_degree':float(.5*np.sum(np.abs(ha-hb))),
            'degree_delta_counts_from_minus64_to_plus64':count.tolist()}


def reached_from_zero(np,g):
    # Vectorized BFS in batches; no Python loop over 24M neighbor IDs.
    visited=np.zeros(g.n,dtype=np.bool_)
    frontier=np.array([0],dtype=np.int64)
    visited[0]=True
    counts_per_hop=[1]
    while len(frontier):
        additions=[]
        for s in range(0,len(frontier),40000):
            ids=frontier[s:s+40000]
            start=g.off[ids]
            deg=g.deg[ids].astype(np.int64,copy=False)
            total=int(np.sum(deg))
            if not total:continue
            # Expand a CSR row slice into a vector of flat indices.
            starts=np.repeat(start,deg)
            prev=np.repeat(np.cumsum(deg,dtype=np.int64)-deg,deg)
            flat=starts+np.arange(total,dtype=np.int64)-prev
            to=g.edges[flat]
            new=np.unique(to[~visited[to]])
            if len(new):
                visited[new]=True
                additions.append(new)
        if not additions:break
        frontier=np.concatenate(additions)
        counts_per_hop.append(int(len(frontier)))
    return {'entry_vertex':0,'reached_nodes':int(np.count_nonzero(visited)),
            'reached_fraction':float(np.mean(visited)),
            'unreachable_nodes':int(g.n-np.count_nonzero(visited)),
            'bfs_levels':len(counts_per_hop),
            'new_nodes_per_level':counts_per_hop}


def euclidean_dist(np,base,src,dst):
    # Chunked gather to avoid a huge (edges × dimension) intermediate tensor.
    out=np.empty(len(src),dtype=np.float64)
    for i in range(0,len(src),8192):
        a=base[np.asarray(src[i:i+8192],dtype=np.int64)]
        b=base[np.asarray(dst[i:i+8192],dtype=np.int64)]
        diff=np.asarray(a-b,dtype=np.float64)
        out[i:i+len(diff)]=np.sqrt(np.einsum('ij,ij->i',diff,diff))
    return out


def edge_length_sample(np,base,g,count,seed):
    rng=np.random.default_rng(seed)
    edge_pos=rng.integers(0,g.m,size=count,dtype=np.int64)
    src=np.searchsorted(g.off,edge_pos,side='right')-1
    dst=g.edges[edge_pos]
    dist=euclidean_dist(np,base,src,dst)
    return {'sampled_directed_edges':count,
            'sampling':'uniform directed-edge positions WITH replacement',
            'euclidean_edge_length':quart(np,dist),
            'fraction_length_gt_500':float(np.mean(dist>500)),
            'fraction_length_gt_1000':float(np.mean(dist>1000))}


def exact_knn_for_anchors(np,base,anchor_ids,k=10,block=32768,qblock=16):
    # Brute-force exact within the numerical precision of FP32 matmul, no ANN.
    # The source vectors in SIFT are integer-valued float32; nonetheless call
    # this a numerical exact-distance reference, not a bitwise proof.
    n=len(base)
    result=np.empty((len(anchor_ids),k),dtype=np.float64)
    for j in range(0,len(anchor_ids),qblock):
        ids=anchor_ids[j:j+qblock]
        q=np.asarray(base[ids],dtype=np.float32)
        qnorm=np.einsum('ij,ij->i',q,q,dtype=np.float64)
        top=np.full((k,len(ids)),np.inf,dtype=np.float64)
        for s in range(0,n,block):
            b=np.asarray(base[s:s+block],dtype=np.float32)
            bn=np.einsum('ij,ij->i',b,b,dtype=np.float64)
            dots=np.asarray(b@q.T,dtype=np.float64)
            d2=np.maximum(0.0,bn[:,None]+qnorm[None,:]-2.0*dots)
            for ix,source in enumerate(ids):
                if s<=int(source)<s+len(b):
                    d2[int(source)-s,ix]=np.inf
            local=np.partition(d2,kth=min(k-1,len(d2)-1),axis=0)[:k,:]
            top=np.partition(np.concatenate((top,local)),kth=k-1,axis=0)[:k,:]
        result[j:j+len(ids),:]=np.sqrt(np.sort(top,axis=0).T)
        print(f"R85_A2B_EXACT_KNN_BATCH_PASS anchors={j+len(ids)}/{len(anchor_ids)}", flush=True)
    if np.any(~np.isfinite(result)) or np.any(result<0):
        fail('Invalid exact anchor kNN distances')
    return result


def anchored_edges(np,base,g,anchor_ids,knn):
    src=[];dest=[];near1=[];near10=[]
    for idx,vertex in enumerate(anchor_ids):
        nbr=g.adjacency(int(vertex))
        if len(nbr):
            src.extend([int(vertex)]*len(nbr))
            dest.extend(int(x) for x in nbr)
            near1.extend([float(knn[idx,0])]*len(nbr))
            near10.extend([float(knn[idx,9])]*len(nbr))
    d=euclidean_dist(np,base,np.asarray(src,dtype=np.int64),np.asarray(dest,dtype=np.int64))
    near1=np.asarray(near1,dtype=np.float64)
    near10=np.asarray(near10,dtype=np.float64)
    good1=near1>1e-12
    good10=near10>1e-12
    return {'anchors':len(anchor_ids),'outgoing_directed_edges':int(len(d)),
            'k1_zero_denominator_edges_skipped':int(np.count_nonzero(~good1)),
            'edge_length':quart(np,d),
            'edge_length_over_exact_k1':quart(np,d[good1]/near1[good1]),
            'edge_length_over_exact_k10':quart(np,d[good10]/near10[good10]),
            'fraction_edge_length_over_4x_k1':float(np.mean((d[good1]/near1[good1])>4)) if np.any(good1) else None}


def overlap_sample(np,a,b,ids):
    jacc=[];delcount=[];addcount=[];different=0
    for i in ids:
        sa=set(int(x) for x in a.adjacency(int(i)))
        sb=set(int(x) for x in b.adjacency(int(i)))
        union=sa|sb
        jacc.append(len(sa&sb)/len(union) if union else 1.0)
        delcount.append(len(sa-sb))
        addcount.append(len(sb-sa))
        if sa!=sb:different+=1
    return {'uniform_source_vertex_sample_n':int(len(ids)),
            'mean_jaccard_neighbors':float(np.mean(jacc)),
            'jaccard_quantiles':quart(np,jacc),
            'fraction_neighbor_set_differs':different/len(ids),
            'mean_B64_only_neighbors_per_node':float(np.mean(delcount)),
            'mean_control_only_neighbors_per_node':float(np.mean(addcount))}


def density_relations(np,graphs,anchor_ids,knn):
    # Independent exact local-density reference on SAME source node IDs.
    # Smaller true d_10 = denser neighborhood.
    distance10=knn[:,9]
    qs=np.quantile(distance10,[1/3,2/3])
    groups=[]
    for i,mask in enumerate((distance10<=qs[0],(distance10>qs[0])&(distance10<=qs[1]),distance10>qs[1])):
        if not np.any(mask):continue
        verts=anchor_ids[mask]
        row={'density_group':('dense','middle','sparse')[i],
             'sample_n':int(mask.sum()),'exact_knn10_distance':quart(np,distance10[mask])}
        for arm in ARMS:
            degrees=graphs[arm].deg[verts]
            row[arm+'_mean_out_degree']=float(np.mean(degrees))
        for arm in ('EDGE_R','EDGE_ALPHA'):
            row[arm+'_minus_B64_mean_degree']=float(np.mean(graphs[arm].deg[verts].astype(np.int16)-graphs['B64'].deg[verts].astype(np.int16)))
        groups.append(row)
    return {'exact_knn10_cut_points':[float(x) for x in qs], 'groups':groups,
            'note':'True density measured on a small *uniform node sample*, not on all 1M nodes'}


def selftest():
    np=numpy()
    rows=[{'beam':1,'recall':.7,'avg_cmps':100},
          {'beam':2,'recall':.8,'avg_cmps':200},
          {'beam':3,'recall':.79,'avg_cmps':220},
          {'beam':4,'recall':.9,'avg_cmps':300}]
    f=monotone_frontier(rows)
    assert len(f)==3
    p=interpolate(f,.85)
    assert p['status']=='INTERPOLATED' and abs(p['comparisons']-250)<1e-7
    assert interpolate(f,.65)['status']=='BELOW_MIN_MEASURED_RECALL'
    assert interpolate(f,.95)['status']=='ABOVE_MAX_MEASURED_RECALL'
    import tempfile,struct
    with tempfile.TemporaryDirectory() as td:
        # Test binary layout checker indirectly with a small native graph header.
        p=Path(td)/'tiny.graph'
        p.write_bytes(struct.pack('<II4I6I',4,2,2,2,1,1,1,2,2,3,0,0))
        mm=np.memmap(p,dtype='<u4',mode='r')
        assert int(mm[0])==4 and int(mm[1])==2 and int(np.sum(mm[2:6]))==6
    print('R85_A2B_SELFTEST_PASS')


def dry_run(run,args):
    np=numpy()
    bmap,qmap=load_a2(run)
    fbin_info(BASE,np)
    print('R85_A2B_INPUT_PIN_PASS graphs=9 quality_rows=225 n=1000000')
    print('R85_A2B_PLAN '+json.dumps({'run':str(run),'targets':TARGETS,
          'exact_uniform_anchor_nodes':args.anchors,
          'uniform_edge_samples_per_graph':args.edge_sample,
          'neighbor_overlap_source_vertices':args.overlap_nodes,
          'analyses':['recall_comparison_interpolation','degree_hist_and_pairwise_deltas','reachability_from_vertex_0','uniform_directed_edge_lengths','exact_anchor_1NN_10NN_and_normalized_edge_lengths','edge_overlap'],
          'write_new_directory_under':str(OUTROOT),'source_files_read_only':True}))
    print('R85_A2B_DRY_RUN_PASS_NO_BUILD_NO_SEARCH')


def run(args):
    np=numpy()
    bmap,qmap=load_a2(args.run_dir)
    base=fbin_info(BASE,np)
    rng=np.random.default_rng(SEED)
    anchor_ids=np.sort(rng.choice(len(base),size=args.anchors,replace=False).astype(np.int64))
    overlap_ids=np.sort(rng.choice(len(base),size=args.overlap_nodes,replace=False).astype(np.int64))
    stamp=dt.datetime.now().strftime('%Y%m%d-%H%M%S')
    out=OUTROOT/('analysis_'+stamp)
    out.mkdir(parents=True,exist_ok=False)
    atomic_json(out/'manifest.json', {'protocol':'R85-A2b analysis v1','input_run':str(args.run_dir),'n_graphs':9,
        'source_base':str(BASE),'source_base_sha256':sha256(BASE),
        'graph_sha256':{f'{a}_r{r}':bmap[(a,r)]['graph_sha256'] for a in ARMS for r in (1,2,3)},
        'seed':SEED,'anchors':anchor_ids.tolist(),'overlap_node_sample_n':args.overlap_nodes,
        'edge_sample_per_graph':args.edge_sample,'target_recall':TARGETS,
        'note':'Only source files read. Separate analysis output under H85. Interpolation descriptive; not measured at exact target Recall.'})
    interp=interp_report(qmap)
    atomic_json(out/'interpolated_matched_recall.json',interp)
    for r in interp:
        print('R85_A2B_INTERP_ROW '+json.dumps({'target':r['target_recall'],
              'arm_median_cmps':{a:(r['arms'][a].get('comparisons_min_med_max') or [None]*3)[1] for a in ARMS},
              'pairwise_ratio_median':{a:(r['paired_ratios'][a]['min_med_max'] or [None]*3)[1] for a in ('EDGE_R','EDGE_ALPHA')},
              'covered_reps':{a:r['arms'][a]['covered_reps'] for a in ARMS}},allow_nan=False),flush=True)
    print('R85_A2B_EXACT_KNN_START anchors='+str(args.anchors)+' across full SIFT1M',flush=True)
    knn=exact_knn_for_anchors(np,base,anchor_ids)
    atomic_json(out/'exact_anchor_knn.json',{'uniform_anchor_ids':anchor_ids.tolist(),
        'exact_k1':[float(x) for x in knn[:,0]],'exact_k10':[float(x) for x in knn[:,9]],
        'method':'FP32 matrix multiplication, FP64 accumulations of norms/outputs; exclude self; full 1M scan'})
    print('R85_A2B_EXACT_KNN_PASS',flush=True)
    graph_rows=[];paired=[];density=[]
    for rep in (1,2,3):
        graphs={}
        for arm in ARMS:
            br=bmap[(arm,rep)]
            graphs[arm]=Graph(br['graph'],np,expected_arcs=br['arcs'],expected_degree=br['R'])
        for a_idx,arm in enumerate(ARMS):
            g=graphs[arm]
            print(f'R85_A2B_GRAPH_START rep={rep} arm={arm}',flush=True)
            row={'rep':rep,'arm':arm,'graph':str(g.path),
                 'degree':degree_report(np,g),
                 'entry0_reachability':reached_from_zero(np,g),
                 'global_edge_length_sample':edge_length_sample(np,base,g,args.edge_sample,SEED+rep*100+a_idx),
                 'exact_anchor_edge_lengths':anchored_edges(np,base,g,anchor_ids,knn)}
            graph_rows.append(row)
            atomic_json(out/'graph_results.json',graph_rows)
            print(f"R85_A2B_GRAPH_PASS rep={rep} arm={arm} arcs={g.m} reached={row['entry0_reachability']['reached_fraction']:.6f}",flush=True)
        for arm in ('EDGE_R','EDGE_ALPHA'):
            row={'rep':rep,'control_arm':arm,
                 'degree_vs_B64':degree_paired(np,graphs['B64'],graphs[arm]),
                 'neighbor_overlap_vs_B64':overlap_sample(np,graphs['B64'],graphs[arm],overlap_ids)}
            paired.append(row)
            atomic_json(out/'paired_graph_comparisons.json',paired)
        density.append({'rep':rep,**density_relations(np,graphs,anchor_ids,knn)})
        atomic_json(out/'exact_density_by_arm.json',density)
        del graphs
    # Compact report: select key metrics; verbose data are separate JSON artifacts.
    summary={'interpretation_limitations':[
        'Total arcs match does not mean matched in/out degree, topology or same candidate stream.',
        'Matched Recall estimates are linearly interpolated per graph between adjacent measured efficient-frontier points, not directly measured at exact target.',
        'Three graphs are descriptive runs, not confidence intervals.',
        'Edge length distribution samples directed edges; density-normalized length uses uniformly sampled source nodes.',
        'Structural differences in final graph cannot identify the causal stage without intermediate candidate traces.',
        'Reachability from node 0 is graph-theoretic access, not proof of efficient navigability.'
    ]}
    for arm in ARMS:
        rows=[r for r in graph_rows if r['arm']==arm]
        summary[arm]={
            'arcs_median':median(r['degree']['arcs'] for r in rows),
            'entry0_reached_fraction_min_med_max':[min(r['entry0_reachability']['reached_fraction'] for r in rows),
                 median(r['entry0_reachability']['reached_fraction'] for r in rows),
                 max(r['entry0_reachability']['reached_fraction'] for r in rows)],
            'global_edge_length_p99_median':median(r['global_edge_length_sample']['euclidean_edge_length']['p99'] for r in rows),
            'exact_anchor_norm_edge_length_k1_p95_median':median(r['exact_anchor_edge_lengths']['edge_length_over_exact_k1'].get('p95',float('nan')) for r in rows)
        }
    for arm in ('EDGE_R','EDGE_ALPHA'):
        rows=[r for r in paired if r['control_arm']==arm]
        summary[arm]['jaccard_neighbors_vs_B64_median']=median(r['neighbor_overlap_vs_B64']['mean_jaccard_neighbors'] for r in rows)
        summary[arm]['out_degree_TV_vs_B64_median']=median(r['degree_vs_B64']['total_variation_out_degree'] for r in rows)
    atomic_json(out/'summary.json',summary)
    print('R85_A2B_ALL_9_GRAPH_ANALYSES_PASS',flush=True)
    print('R85_A2B_SUMMARY '+json.dumps({k:v for k,v in summary.items() if k!='interpretation_limitations'},allow_nan=False),flush=True)
    print('R85_A2B_RESULTS_DIR '+str(out),flush=True)


def main():
    ap=argparse.ArgumentParser(description=__doc__,formatter_class=argparse.RawTextHelpFormatter)
    g=ap.add_mutually_exclusive_group(required=True)
    g.add_argument('--selftest',action='store_true')
    g.add_argument('--dry-run',action='store_true')
    g.add_argument('--run',action='store_true')
    ap.add_argument('--run-dir',type=Path,default=A2_RUN)
    ap.add_argument('--anchors',type=int,default=128,help='Uniform exact-kNN source nodes (default 128, costly full scan)')
    ap.add_argument('--edge-sample',type=int,default=100_000,help='Uniform directed edge samples per graph')
    ap.add_argument('--overlap-nodes',type=int,default=4096,help='Uniform source nodes for adjacency-overlap')
    args=ap.parse_args()
    if args.selftest:
        selftest();return
    if not (16<=args.anchors<=2048 and 100<=args.edge_sample<=2_000_000 and 64<=args.overlap_nodes<=100_000):
        fail('Arguments out of allowed bounds')
    if args.dry_run:
        dry_run(args.run_dir,args);return
    run(args)


if __name__=='__main__':
    try:
        main()
    except Exception as e:
        print('R85_A2B_ERROR '+str(e),file=sys.stderr,flush=True)
        sys.exit(1)
