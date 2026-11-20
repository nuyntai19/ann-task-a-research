#!/usr/bin/env python3
"""R90-P3.7 VBT ANN *offline* candidate coverage screening, NOT a native ANN builder.

Design: fixed SIFT100K source SHA; 3 independent partition seeds; random vs 1% sampled
centroids; deterministic median splits for overfull cells; recompute seam features from
FINAL tiles; seam vs centroid-nearest and exact-work-matched centroid baselines. Exact
sampled base-to-base brute-force Top10 and per-cell bidirectional Top2 simulation.

IMPORTANT: This is NOT the RBC N1/N2 direct raw/pool control (native leaf-proposal
snapshots do not yet exist for the same 2,000 SIFT100K anchors). The outcome must
remain HOLD_PENDING_RBC_MATCHED_POOL after any successful run. Never infer graph
Recall, QPS or speedup from this script.

Usage: selftest | preflight | pilot | audit. No overwrite or background execution.
Requires numpy, a BLAS implementation, and ~1 GiB free memory.
"""
from __future__ import annotations
import argparse, csv, hashlib, json, math, os, struct, sys, time
from pathlib import Path
from collections import defaultdict

os.environ.setdefault('OPENBLAS_NUM_THREADS', '4')
os.environ.setdefault('OMP_NUM_THREADS', '4')
import numpy as np

ROOT=Path.home()/'ann-task-a'
BASE=ROOT/'data/sift100k.fbin'
OUT=ROOT/'experiments/R90/r90_p37_vbt_offline_c0_gate_v1'
BASE_SHA='e50ff1bc34bcc6d1c97dd001023c09a666971cde64605cc06671ed8a8ff1ed12'
KBS=(8,12,16,20)
SEEDS=(555,556,557)
EVAL_SEED=20261118

class GateError(RuntimeError):pass
def ck(cond,reason):
    if not cond:raise GateError('R90_P37_HOLD_'+reason)
def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(4*1024*1024),b''):h.update(b)
    return h.hexdigest()
def numpy_sha(a):return hashlib.sha256(np.asarray(a).tobytes(order='C')).hexdigest()
def read_fbin(p, expected_n=100000, expected_d=128, verify_sha=True):
    p=Path(p);ck(p.is_file(),'BASE_MISSING')
    with p.open('rb') as f: b=f.read(8)
    ck(len(b)==8,'BASE_HEADER')
    n,d=struct.unpack('<II',b)
    ck((n,d)==(expected_n,expected_d),'BASE_SHAPE_'+str((n,d)))
    ck(p.stat().st_size==8+4*n*d,'BASE_LENGTH')
    if verify_sha:ck(sha(p)==BASE_SHA,'BASE_SHA')
    return np.memmap(p,dtype='<f4',mode='r',offset=8,shape=(n,d)),n,d

def brute_sample_gt(x,qids,k=10,chunk=20):
    """Full base-to-base brute-force, float32 dense dot; tie ID ascending.
    Extra distance-precision caveat preserved in manifest.
    """
    n=len(x);ck(k<n,'K_GE_N')
    x=np.asarray(x,dtype=np.float32)
    norms=np.einsum('ij,ij->i',x,x,dtype=np.float32)
    gt=np.empty((len(qids),k),dtype=np.int32)
    for st in range(0,len(qids),chunk):
        sel=qids[st:st+chunk]
        sq=np.ascontiguousarray(x[sel])
        dots=sq@x.T
        dist=norms[sel,None]+norms[None,:]-2.0*dots
        dist[np.arange(len(sel)),sel]=np.inf
        for j in range(len(sel)):
            # Stable tie-breaking by ascending vector ID, no GT leakage into partition.
            pidx=np.argpartition(dist[j],k-1)[:k]
            bound=float(np.max(dist[j,pidx]))
            # Include all exact ties at boundary (can be many identical SIFT vectors).
            tie=np.flatnonzero(dist[j]<=bound)
            if len(tie)>10000:
                # fall back full stable argsort; correctness before speed
                gt[st+j]=np.argsort(dist[j],kind='stable')[:k]
            else:
                gt[st+j]=tie[np.lexsort((tie,dist[j,tie]))][:k]
            ck(int(sel[j]) not in gt[st+j],'GT_SELF')
    return gt

def sq_l2_rows(x,centroids):
    a=np.einsum('ij,ij->i',x,x,dtype=np.float32)
    b=np.einsum('ij,ij->i',centroids,centroids,dtype=np.float32)
    return np.maximum(a[:,None]+b[None,:]-2.0*(x@centroids.T),0)

def choose_centers(x,M,seed,mode,sample_fraction=.01,iterations=4):
    rng=np.random.default_rng(seed*100+ (1 if mode=='sample1pct_kmeans' else 0))
    n=len(x)
    if mode=='random':
        ids=rng.choice(n,size=M,replace=False)
        return np.ascontiguousarray(x[ids],dtype=np.float32),0,{'train_size':0,'iterations':0,'init_sha':numpy_sha(ids)}
    ck(mode=='sample1pct_kmeans','METHOD')
    train_size=max(M,int(math.ceil(n*sample_fraction)))
    ck(train_size<=n,'TRAIN_TOO_LARGE')
    chosen=rng.choice(n,size=train_size,replace=False)
    train=np.ascontiguousarray(x[chosen],dtype=np.float32)
    centers=np.ascontiguousarray(train[rng.choice(train_size,size=M,replace=False)])
    counted=0
    for iteration in range(iterations):
        dist=sq_l2_rows(train,centers)
        assign=dist.argmin(axis=1)
        counts=np.bincount(assign,minlength=M)
        new=np.zeros_like(centers)
        np.add.at(new,assign,train)
        nonempty=counts>0
        new[nonempty]/=counts[nonempty,None]
        new[~nonempty]=centers[~nonempty]
        centers=new
        counted+=train_size*M
    return centers,counted,{'train_size':train_size,'iterations':iterations,'init_sha':numpy_sha(chosen)}

def assign_coarse(x,centers,chunk=512):
    labels=np.empty(len(x),dtype=np.int32)
    for st in range(0,len(x),chunk):
        d=sq_l2_rows(np.ascontiguousarray(x[st:st+chunk]),centers)
        labels[st:st+len(d)]=np.argmin(d,axis=1)
    return labels

def split_overfull(x,labels,B):
    """Median split on axis of maximum within-cell variance; no point duplication."""
    ck(B>=8,'TILE_B')
    cells=[]; splits=0
    # All original centroids create a coarse cell; some can be empty.
    order=np.argsort(labels,kind='stable')
    boundary=np.r_[0, np.flatnonzero(np.diff(labels[order]))+1,len(order)]
    for left,right in zip(boundary[:-1],boundary[1:]):
        if left==right:continue
        queue=[order[left:right]]
        while queue:
            ids=queue.pop()
            if len(ids)<=B:
                cells.append(np.asarray(ids,dtype=np.int32))
                continue
            part=np.asarray(x[ids],dtype=np.float32)
            dim=int(part.var(axis=0,dtype=np.float64).argmax())
            ranked=np.argsort(part[:,dim],kind='stable')
            mid=len(ids)//2
            queue.extend([ids[ranked[mid:]],ids[ranked[:mid]]]);splits+=1
    ck(sum(map(len,cells))==len(x),'POINT_CONSERVATION')
    tile=np.empty(len(x),dtype=np.int32)
    for t,ids in enumerate(cells):
        ck(1<=len(ids)<=B,'BAD_FINAL_CELL_SIZE')
        tile[ids]=t
    ck(len(np.unique(tile))==len(cells),'TILE_NONEMPTY')
    centers=np.stack([np.asarray(x[ids],dtype=np.float32).mean(axis=0) for ids in cells])
    sizes=np.array(list(map(len,cells)),dtype=np.int32)
    return cells,tile,centers,sizes,splits

def final_alternates(x,centers,tile,chunk=512):
    """Recompute two nearby FINAL-tile representatives after oversize splits.
    These are heuristic proximity features, not exact geometric Voronoi boundaries.
    """
    ck(len(centers)>=3,'FEW_TILES')
    out=np.empty((len(x),2),dtype=np.int32)
    for st in range(0,len(x),chunk):
        d=sq_l2_rows(np.ascontiguousarray(x[st:st+chunk]),centers)
        d[np.arange(len(d)),tile[st:st+len(d)]]=np.inf
        candidates=np.argpartition(d,1,axis=1)[:,:2]
        v=np.take_along_axis(d,candidates,axis=1)
        sw=v[:,0]>v[:,1]
        candidates[sw]=candidates[sw][:,::-1]
        out[st:st+len(d)]=candidates
    return out

def center_distance(centers):
    d=sq_l2_rows(np.asarray(centers,dtype=np.float32),np.asarray(centers,dtype=np.float32))
    np.fill_diagonal(d,np.inf)
    return d

def edge_id(a,b,T):
    return min(int(a),int(b))*T+max(int(a),int(b))

def seam_adjacency(tile,alternates,centerd,k):
    T=len(centerd)
    lo=np.minimum(tile[:,None],alternates).astype(np.int64)
    hi=np.maximum(tile[:,None],alternates).astype(np.int64)
    enc=(lo*T+hi).ravel()
    uniq,cnt=np.unique(enc,return_counts=True)
    graph=[[] for _ in range(T)]
    for u,w in zip(uniq,cnt):
        a,b=divmod(int(u),T)
        if a==b:continue
        graph[a].append((b,int(w)))
        graph[b].append((a,int(w)))
    chosen=set(); deficit=0
    for a in range(T):
        cand=sorted(graph[a], key=lambda e:(-e[1],float(centerd[a,e[0]]),e[0]))[:k]
        deficit+=max(0,k-len(cand))
        for b,w in cand:chosen.add(edge_id(a,b,T))
    return chosen,deficit,len(uniq)

def center_knn_adjacency(centerd,k):
    T=len(centerd); chosen=set()
    for a in range(T):
        # Stable tie by ID by stable argsort, same per-cell top-k budget as seam.
        neigh=np.argsort(centerd[a],kind='stable')[:k]
        for b in neigh:chosen.add(edge_id(a,b,T))
    return chosen

def work(edges,sizes,T):
    own=int(np.sum(sizes.astype(np.int64)**2))
    triangular=int(np.sum(sizes.astype(np.int64)*(sizes.astype(np.int64)-1)//2))
    cross=sum(int(sizes[int(e)//T])*int(sizes[int(e)%T]) for e in edges)
    return {'within_full_matrix_cells':own,'within_unique_pairs':triangular,
            'cross_rectangular_matrix_cells':int(cross),
            'total_distance_matrix_cells':int(own+cross),'unique_tile_joins':len(edges)}

def center_workmatched(centerd,sizes,target_cross):
    """Global shortest-center edge budget matched on cross-tile GEMM entries.
    Unlike top-k, this does not guarantee degrees; it is an honest distinct control.
    """
    T=len(sizes); ix,iy=np.triu_indices(T,1)
    dd=centerd[ix,iy]; ordered=np.argsort(dd,kind='stable')
    chosen=set();acc=0
    for j in ordered:
        a=int(ix[j]);b=int(iy[j]);c=int(sizes[a])*int(sizes[b])
        if acc+c>target_cross:continue
        chosen.add(a*T+b);acc+=c
        if acc==target_cross:break
    return chosen

def post2_hit(x,pid,nid,cell_map,tile,cached):
    """Whether either row of the x-y tile-pair join proposes the true pair.
    This is NOT PiPNN native packed-double bitwise-parity.
    """
    def near2(p,t):
        key=(int(p),int(t))
        if key not in cached:
            ids=cell_map[t]
            z=np.asarray(x[ids],dtype=np.float32)-np.asarray(x[p],dtype=np.float32)
            dd=np.einsum('ij,ij->i',z,z,dtype=np.float32)
            dd=dd.copy();dd[ids==p]=np.inf
            # Stable tie-ID ranking; no self. Same-cell and cross-cell both covered.
            top=np.lexsort((ids,dd))[:2]  # exact tie-break by global base ID
            cached[key]=set(int(ids[u]) for u in top if np.isfinite(dd[u]))
        return cached[key]
    return int(nid) in near2(pid,tile[nid]) or int(pid) in near2(nid,tile[pid])

def gt_tile_table(x,qids,gt,cells,tile):
    T=len(cells);keys=np.zeros_like(gt,dtype=np.int64)
    pass2=np.zeros_like(gt,dtype=np.bool_);cache={}
    for i,q in enumerate(qids):
        for j,n in enumerate(gt[i]):
            keys[i,j]=edge_id(int(tile[q]),int(tile[n]),T)
            pass2[i,j]=post2_hit(x,int(q),int(n),cells,tile,cache)
    return keys,pass2,len(cache)

def evaluate_edges(keys,pass2,tile,qids,gt,edges,T):
    selfpairs=np.asarray([edge_id(int(tile[q]),int(tile[q]),T) for q in qids],dtype=np.int64)
    hit=np.isin(keys,np.asarray(sorted(edges),dtype=np.int64)) | (keys==selfpairs[:,None])
    raw=int(hit.sum());post=int((hit&pass2).sum());total=int(keys.size)
    return {'raw_hits':raw,'post_top2_hits':post,'exact_top10_total':total,
            'raw_C0':round(raw/total,8),'post_top2_C0':round(post/total,8),
            'raw_per_sample_mean':round(raw/len(qids),6),'post_top2_per_sample_mean':round(post/len(qids),6)}

def scenario(x,qids,gt,seed,mode,B,kbs):
    n,d=x.shape;M=max(3,math.ceil(n/B));t0=time.perf_counter()
    cent,training_pairs,train_meta=choose_centers(x,M,seed,mode)
    coarse=assign_coarse(x,cent)
    cells,tile,final_centers,sizes,splits=split_overfull(x,coarse,B)
    alt=final_alternates(x,final_centers,tile)
    Dc=center_distance(final_centers)
    T=len(cells)
    keys,pass2,ncache=gt_tile_table(x,qids,gt,cells,tile)
    g_self=np.sum(sizes.astype(np.int64)**2)
    rows=[]
    for k in kbs:
        seam,deficit,seam_candidates=seam_adjacency(tile,alt,Dc,k)
        cknn=center_knn_adjacency(Dc,k)
        wseam=work(seam,sizes,T)
        matched=center_workmatched(Dc,sizes,wseam['cross_rectangular_matrix_cells'])
        for control,edges in [('seam',seam),('center_topk',cknn),('center_workmatched',matched)]:
            counts=work(edges,sizes,T)
            cov=evaluate_edges(keys,pass2,tile,qids,gt,edges,T)
            rows.append({**dict(seed=seed,center_mode=mode,kb=k,control=control,
                              n=n,dimension=d,B=B,M=M,final_tile_count=T,split_calls=splits,
                              min_tile=int(sizes.min()),median_tile=float(np.median(sizes)),max_tile=int(sizes.max()),
                              assign_point_centroid_evals=n*M,final_seam_point_centroid_evals=n*T,
                              training_point_centroid_evals=training_pairs,
                              TOTAL_PARTITION_POINT_CENTROID_EVALS=n*(M+T)+training_pairs,
                              TOTAL_PARTITION_AND_TILE_DISTANCE_CELLS=n*(M+T)+training_pairs+counts['total_distance_matrix_cells'],
                              seam_candidate_unique_pairs=seam_candidates,
                              missing_seam_directed_slots=deficit if control=='seam' else -1),
                         **counts,**cov})
    rec={'seed':seed,'mode':mode,'coarse_M':M,'final_T':T,'splits':splits,'training':train_meta,
         'n_eval':len(qids),'eval_ids_sha':numpy_sha(qids),'tile_map_sha':numpy_sha(tile),
         'coarse_map_sha':numpy_sha(coarse),'tile_size_min':int(sizes.min()),
         'tile_size_median':float(np.median(sizes)),'tile_size_p99':float(np.quantile(sizes,.99)),
         'tile_size_max':int(sizes.max()),'rank_cache_entries':ncache,
         'elapsed_s_DIAGNOSTIC':round(time.perf_counter()-t0,3)}
    return rows,rec

def settings():return {'kbs':list(KBS),'seeds':list(SEEDS),'B':256,'eval_sample_count':2000,
   'center_methods':['random','sample1pct_kmeans'],'evaluation_seed':EVAL_SEED,
   'screening':'HOLD_RBC_N1_N2_MATCHED_POOL_CAPTURE_MISSING',
   'description':'RBC N1/N2 SAME-SAMPLED raw co-leaf and post-native-Top2 proposal pools are REQUIRED before GO/NO-GO.',
   'numeric_caution':'GT by full FP32 dense brute-force with float32 tie-ID order, not native PiPNN packed-bit semantics',
   'algorithmic_caution':'Final-tile centroids used only as heuristic seam features; actual partition is coarse assigned then median split',
   'cost_caution':'Logical n*M+n*T+trainM+matrix cells, not physical FLOPs or exact total H17 W_P; per-cell Top2 simulation lacks HashPrune/RobustPrune.'}

def preflight(base=BASE,out=OUT):
    x,n,d=read_fbin(base)
    ck(np.isfinite(x[0:20]).all(),'NONFINITE_SAMPLE')
    ck(not out.exists() and not out.is_symlink(),'OUT_EXISTS')
    ck(np.__version__ is not None,'NUMPY_MISSING')
    print('R90_P37_PREFLIGHT_SIFT100K_DATA_SHA_SHAPE_AND_OUTPUT_PASS',n,d,flush=True)
    return x

def pilot(base=BASE,out=OUT):
    x=preflight(base,out)
    out.parent.mkdir(parents=True,exist_ok=True)
    tmp=out.with_name(out.name+'.incomplete')
    ck(not tmp.exists() and not tmp.is_symlink(),'INCOMPLETE_EXISTS')
    tmp.mkdir(mode=0o755)
    try:
        qids=np.sort(np.random.default_rng(EVAL_SEED).choice(len(x),size=2000,replace=False)).astype(np.int32)
        print('R90_P37_GT_BRUTEFORCE_2K_START',flush=True)
        gt=brute_sample_gt(x,qids,k=10)
        ck(gt.shape==(2000,10) and len(np.unique(qids))==2000,'GT_SHAPE')
        np.savez_compressed(tmp/'eval_qids_and_gt10.npz',qids=qids,gt10=gt,base_sha=np.array(BASE_SHA))
        print('R90_P37_GT_BRUTEFORCE_PASS gt_sha',numpy_sha(gt),flush=True)
        records=[];cases=[]
        for seed in SEEDS:
            for mode in ('random','sample1pct_kmeans'):
                print('R90_P37_CASE_START',seed,mode,flush=True)
                rows,meta=scenario(x,qids,gt,seed,mode,256,KBS)
                records+=rows;cases.append(meta)
                for y in rows:
                    print('R90_P37_RESULT',seed,mode,y['kb'],y['control'],
                          'raw_C0',y['raw_C0'],'post_top2_C0',y['post_top2_C0'],
                          'total_cells',y['TOTAL_PARTITION_AND_TILE_DISTANCE_CELLS'],flush=True)
                print('R90_P37_CASE_PASS',seed,mode,'final_tiles',meta['final_T'],flush=True)
        ck(len(records)==len(SEEDS)*2*len(KBS)*3,'ROW_COUNT')
        with (tmp/'offline_arms.csv').open('x',newline='',encoding='utf8') as f:
            w=csv.DictWriter(f,fieldnames=list(records[0].keys()))
            w.writeheader();w.writerows(records)
        manifest={'stage':'SIFT100K_VBT_OFFLINE_ONLY','status':'PASS_VBT_DIAGNOSTIC__HOLD_RBC_MATCHED_POOL',
                  'base_sha':BASE_SHA,'base_path':str(base),'n':len(x),'d':x.shape[1],
                  'config':settings(),'eval_qids_sha':numpy_sha(qids),'eval_gt10_sha':numpy_sha(gt),
                  'cases':cases,'rows':len(records),'csv_sha':sha(tmp/'offline_arms.csv'),
                  'eval_npz_sha':sha(tmp/'eval_qids_and_gt10.npz'),
                  'rbc_controls':{'N1':'MISSING_NATIVE_SIFT100K_SAME_QIDS_POOL_CAPTURE',
                                  'N2':'MISSING_NATIVE_SIFT100K_SAME_QIDS_POOL_CAPTURE'},
                  'decision':'NO_GO_DECISION_ALLOWED_UNTIL_RBC_N1_N2_POOL_TOP2_AND_WORK_BASELINES_SAME_QIDS',
                  'author_caution':'No graph BUILD or Search performed. Training and partition cost modeled as logical point-centroid distance counts.'}
        with (tmp/'result_manifest.json').open('x',encoding='utf8') as f:json.dump(manifest,f,indent=2,sort_keys=True);f.write('\n')
        tmp.rename(out)
        print('R90_P37_PILOT_PASS_OFFLINE_72ROWS__RBC_MATCHED_N1_N2_HOLD',flush=True)
        print('R90_P37_OUTPUT',out,flush=True)
    except BaseException:
        print('R90_P37_HOLD_PARTIAL_OUTPUT',tmp,flush=True)
        raise

def audit(out=OUT):
    ck(out.is_dir(),'PILOT_OUTPUT_MISSING')
    m=json.loads((out/'result_manifest.json').read_text())
    ck(m['stage']=='SIFT100K_VBT_OFFLINE_ONLY','MANIFEST_STAGE')
    ck(m['status']=='PASS_VBT_DIAGNOSTIC__HOLD_RBC_MATCHED_POOL','MANIFEST_STATUS')
    ck(m['base_sha']==BASE_SHA,'DATA_SHA_PIN')
    ck(m['rows']==72 and len(m['cases'])==6,'ARM_AND_CASE_COUNTS')
    ck(m['csv_sha']==sha(out/'offline_arms.csv'),'CSV_SHA')
    ck(m['eval_npz_sha']==sha(out/'eval_qids_and_gt10.npz'),'EVAL_FILE_SHA')
    with np.load(out/'eval_qids_and_gt10.npz',allow_pickle=False) as z:
        ck(numpy_sha(z['qids'])==m['eval_qids_sha'],'QIDS_SHA')
        ck(numpy_sha(z['gt10'])==m['eval_gt10_sha'],'GT_SHA')
        ck(len(np.unique(z['qids']))==2000,'QIDS_DISTINCT')
        ck(np.all(z['gt10']!=z['qids'][:,None]),'GT_SELF')
    with (out/'offline_arms.csv').open(newline='',encoding='utf8') as f: rows=list(csv.DictReader(f))
    ck(len(rows)==72,'CSV_72')
    for r in rows:
        ck(0<=float(r['post_top2_C0'])<=float(r['raw_C0'])<=1,'C0_ORDER')
        ck(int(r['TOTAL_PARTITION_AND_TILE_DISTANCE_CELLS'])>=int(r['total_distance_matrix_cells']),'WORK_COST')
        ck(1<=int(r['max_tile'])<=int(r['B']),'TILE_CAP')
        ck(int(r['n'])==100000,'DATA_SIZE')
    print('R90_P37_AUDIT_OFFLINE_SOURCE_DATA_QID_GT_COST_C0_AND_72ARM_PASS',flush=True)
    print('R90_P37_DECISION_HOLD_MISSING_MATCHED_NATIVE_RBC_N1_N2_PROPOSALS',flush=True)

def selftest():
    rng=np.random.default_rng(42)
    x=np.ascontiguousarray(rng.integers(0,256,(600,12)),dtype=np.float32)
    qids=np.array([0,20,51,125,300,598],dtype=np.int32)
    gt=brute_sample_gt(x,qids,k=5)
    ck(gt.shape==(6,5),'SELF_GT')
    rows,meta=scenario(x,qids,gt,555,'random',64,(2,3))
    ck(len(rows)==6 and meta['tile_size_max']<=64,'SELF_ROWS')
    ck(all(0<=r['post_top2_C0']<=r['raw_C0']<=1 for r in rows),'SELF_COVERAGE')
    # Exact tiny toy: qID0 and its closest in one final tile must be eligible raw.
    tile=np.array([0,0,1,1],dtype=np.int32)
    cells=[np.array([0,1],dtype=np.int32),np.array([2,3],dtype=np.int32)]
    u=np.array([[0.],[1.],[3.],[4.]],dtype=np.float32)
    ck(post2_hit(u,0,1,cells,tile,{}),'SELF_POST2')
    ck(work({1},np.array([2,2]),2)['cross_rectangular_matrix_cells']==4,'SELF_WORK')
    print('R90_P37_SELFTEST_PASS_TILES_SEAM_COST_TOP2_AND_GT',flush=True)

def main():
    a=argparse.ArgumentParser(description=__doc__)
    a.add_argument('phase',choices=['selftest','preflight','pilot','audit'])
    args=a.parse_args()
    try:
        if args.phase=='selftest':selftest()
        elif args.phase=='preflight':preflight()
        elif args.phase=='pilot':pilot()
        else:audit()
    except (GateError,ValueError,IndexError,AssertionError,MemoryError) as e:
        print('R90_P37_EXIT_HOLD',str(e),file=sys.stderr,flush=True);sys.exit(2)
if __name__=='__main__':main()
