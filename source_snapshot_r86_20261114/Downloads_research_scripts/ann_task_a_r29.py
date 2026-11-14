#!/usr/bin/env python3
"""H32-R29 offline audits for PiPNN / CHARM / LOSF.

This is a diagnostic tool, NOT a validated ANN construction algorithm.
It never labels proxy Core/Halo selections as genuine leader assignment.
Requires Python 3.9+ and numpy for CHARM; validation and LOSF also use numpy.
"""
import argparse
import hashlib
import json
import mmap
import os
import random
import struct
import sys
from contextlib import contextmanager
from pathlib import Path

import numpy as np

LEAF_MAGIC = b'H18LEAF1'
CORE_MAGIC = b'H29CORE1'


def json_print(d):
    print(json.dumps(d, indent=2, ensure_ascii=False, default=lambda x: x.item() if isinstance(x, np.generic) else str(x)))


def sha256_file(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for block in iter(lambda: f.read(8*1024*1024), b''):
            h.update(block)
    return h.hexdigest()


class LeafIndex:
    def __init__(self, file):
        self.file = Path(file)
        self.fd = open(self.file, 'rb')
        self.mm = mmap.mmap(self.fd.fileno(), 0, access=mmap.ACCESS_READ)
        if self.mm.size()<24 or self.mm[:8]!=LEAF_MAGIC:
            raise ValueError('Invalid H18LEAF1 magic / header')
        self.n, self.nleaves=struct.unpack_from('<QQ',self.mm,8)
        self.offsets=np.empty(self.nleaves,dtype=np.int64)
        self.sizes=np.empty(self.nleaves,dtype=np.uint32)
        off=24
        self.memberships=0
        self.pair_events=0
        for i in range(self.nleaves):
            if off+4>self.mm.size(): raise ValueError(f'Truncated leaf header at {i}')
            (sz,)=struct.unpack_from('<I', self.mm, off)
            off+=4
            if off+4*sz>self.mm.size(): raise ValueError(f'Truncated leaf data at {i}')
            self.offsets[i]=off
            self.sizes[i]=sz
            self.memberships+=sz
            self.pair_events+=sz*(sz-1)//2
            off+=4*sz
        if off!=self.mm.size():
            raise ValueError(f'File trailing bytes or mismatched layout: parsed {off} vs actual {self.mm.size()}')
    def leaf(self, idx):
        v=np.frombuffer(self.mm, dtype='<u4', count=int(self.sizes[idx]),offset=int(self.offsets[idx]))
        if v.size and int(np.max(v))>=self.n:
            raise ValueError(f'Out of bounds id in leaf {idx}')
        return v.copy()
    def close(self):
        self.mm.close()
        self.fd.close()
    def summary(self, hash_it=False):
        out={'format':LEAF_MAGIC.decode(),'file':str(self.file), 'bytes':self.mm.size(),
             'n_base':int(self.n),'n_leaves':int(self.nleaves),
             'memberships':int(self.memberships),'pair_events':int(self.pair_events),
             'min_leaf_size':int(self.sizes.min()) if self.nleaves else 0,
             'max_leaf_size':int(self.sizes.max()) if self.nleaves else 0,
             'mean_leaf_size':float(np.mean(self.sizes)) if self.nleaves else 0}
        if hash_it:out['sha256']=sha256_file(self.file)
        return out


class CoreFlags:
    """H29CORE1: 8-byte magic, uint64 leaf_count, then each [uint32 size][size uint8 flags].
    MUST be generated from true lineage metadata, not guessed from leaf member IDs.
    """
    def __init__(self, path, leaves):
        self.fd=open(path,'rb')
        self.mm=mmap.mmap(self.fd.fileno(),0,access=mmap.ACCESS_READ)
        if len(self.mm)<16 or self.mm[:8]!=CORE_MAGIC: raise ValueError('Invalid H29CORE1 core flag magic')
        (nleaves,)=struct.unpack_from('<Q',self.mm,8)
        if nleaves!=leaves.nleaves:raise ValueError('core flag leaf count mismatch')
        self.offsets=[]; off=16
        for i in range(nleaves):
            if off+4>len(self.mm): raise ValueError('Truncated core flag leaf header')
            (sz,)=struct.unpack_from('<I',self.mm,off); off+=4
            if sz!=int(leaves.sizes[i]):raise ValueError(f'core label count != leaf size at leaf {i}')
            if off+sz>len(self.mm):raise ValueError('Truncated core flag leaf flags')
            self.offsets.append(off);off+=sz
        if off!=len(self.mm):raise ValueError('Trailing core file data')
    def get(self, idx):
        # Unlike input ids, even non-boolean flags are rejected.
        sz=int(self.leaves.sizes[idx]) if hasattr(self,'leaves') else None
        if sz is None:raise RuntimeError('core flags not bound')
        a=np.frombuffer(self.mm,dtype=np.uint8,count=sz,offset=self.offsets[idx])
        if np.any(a>1):raise ValueError(f'Non-boolean Core flag in leaf {idx}')
        return a.astype(bool)
    def bind(self, leaves):self.leaves=leaves;return self
    def close(self):self.mm.close();self.fd.close()


class Fbin:
    def __init__(self,path,n_expected):
        self.file=Path(path)
        with open(path,'rb') as f: head=f.read(8)
        if len(head)!=8:raise ValueError('Invalid fbin header')
        n,d=struct.unpack('<ii',head)
        if n!=n_expected or d<=0:raise ValueError(f'Fbin shape {(n,d)} incompatible with n_base {n_expected}')
        if os.stat(path).st_size!=8+4*n*d:raise ValueError('Fbin byte length does not match header')
        self.n=n;self.d=d
        self.rows=np.memmap(path,dtype='<f4',mode='r',offset=8,shape=(n,d))


def choose_core(mode, ids_sorted, x, orig_top2, ncore, leaf_index, rng, core_flags_sorted=None):
    m=len(ids_sorted)
    core=np.zeros(m,dtype=bool)
    if mode=='flags':
        if core_flags_sorted is None: raise ValueError('core labels not provided')
        return core_flags_sorted.copy()
    if ncore==0:return core
    if mode=='random':
        core[rng.sample(range(m),ncore)]=True
    elif mode=='centroid-proxy':
        cen=np.mean(x,axis=0,dtype=np.float64)
        diff=x.astype(np.float64)-cen
        scores=np.sum(diff*diff,axis=1)
        core[np.argsort(scores,kind='stable')[:ncore]]=True
    elif mode=='degree-oracle':
        # Deliberately uses exact baseline Top-2 edges, so is NOT implementable
        # as a low-overhead constructor; optimistic diagnostic only.
        src=np.repeat(np.arange(m),orig_top2.shape[1])
        dst=orig_top2.reshape(-1)
        for _ in range(ncore):
            missed=~(core[src] | core[dst])
            if not np.any(missed):
                avail=np.flatnonzero(~core)
                core[avail[0]]=True
                continue
            score=np.bincount(src[missed],minlength=m)+np.bincount(dst[missed],minlength=m)
            score[core]=-1
            core[int(np.argmax(score))]=True
    else:raise ValueError(f'Unknown core mode {mode}')
    return core


def audit_one_leaf(ids,x,mode,gamma,rng,leaf_idx,flags=None):
    m=len(ids)
    if m<3:return None
    # Stable global-ID order makes exact ties reproducible in this diagnostic.
    order=np.argsort(ids,kind='stable')
    ids=np.asarray(ids)[order].astype(np.int64)
    x=np.asarray(x)[order].astype(np.float32)
    if len(np.unique(ids))!=m:raise ValueError(f'Duplicate IDs within leaf {leaf_idx}')
    if np.any(~np.isfinite(x)):raise ValueError('Non-finite vectors cannot be evaluated')
    norms=np.einsum('ij,ij->i',x,x)
    dist=norms[:,None]+norms[None,:]-2.0*(x@x.T)
    np.maximum(dist,0.0,out=dist)
    np.fill_diagonal(dist,np.inf)
    top2=np.argsort(dist,axis=1,kind='stable')[:,:2]
    assert np.isfinite(dist[np.arange(m),top2[:,0]]).all()
    if mode=='flags':
        if flags is None:raise ValueError('Missing real Core flags')
        core=choose_core(mode,ids,x,top2,0,leaf_idx,rng,core_flags_sorted=np.asarray(flags)[order])
    else:
        ncore=max(0,min(m,int(round(m*gamma))))
        core=choose_core(mode,ids,x,top2,ncore,leaf_idx,rng)
    c=int(core.sum());h=m-c
    keep=core[:,None]|core[None,:]
    # baseline proposal preservation, no need to re-rank: if an original Top2
    # pair is retained it is still eligible (and cannot be displaced by a new pair)
    kept_top2=int(np.count_nonzero(keep[np.arange(m)[:,None],top2]))
    masked=dist.copy()
    masked[~keep]=np.inf
    new_top2=np.argsort(masked,axis=1,kind='stable')[:,:2]
    valid=np.isfinite(masked[np.arange(m)[:,None],new_top2])
    new_proposals=int(valid.sum())
    lost_original=2*m-kept_top2
    pair_saved=h*(h-1)//2
    return {'leaf_id':leaf_idx,'size':m,'core':c,'halo':h,
            'original_pairs':m*(m-1)//2,'pairs_skipped':pair_saved,
            'original_directed_top2':2*m,'retained_original_top2':kept_top2,
            'lost_original_top2':lost_original,
            'new_directed_proposals':new_proposals,
            'vertices_with_2_reduced_neighbors':int(np.count_nonzero(valid.sum(axis=1)==2)),
            'retained_nearest_neighbor':int(np.count_nonzero(keep[np.arange(m),top2[:,0]]))}


def cmd_charm(a):
    idx=LeafIndex(a.leaves)
    try:
        vec=Fbin(a.fbin,idx.n)
        if a.mode=='flags' and not a.core_flags:raise ValueError('--core-flags required for genuine Core/Halo audit')
        cf=CoreFlags(a.core_flags,idx).bind(idx) if a.mode=='flags' else None
        try:
            rng=random.Random(a.seed)
            sample=sorted(rng.sample(range(idx.nleaves),min(a.sample,idx.nleaves)))
            results=[]
            for j in sample:
                ids=idx.leaf(j)
                flags=cf.get(j) if cf else None
                x=vec.rows[ids]
                r=audit_one_leaf(ids,x,a.mode,a.gamma,rng,j,flags=flags)
                if r:results.append(r)
            tot=lambda key:sum(r[key] for r in results)
            output={'audit':'CHARM-R0','status':'DIAGNOSTIC_ONLY','core_label_provenance':a.mode,
                    'external_core_flags_supplied':a.mode=='flags',
                    'warning':'Proxy/oracle labels are NOT CHARM real-leader labels and are not a fair ANN BUILD benchmark.' if a.mode!='flags' else 'External Core flags accepted structurally; provenance as true leader lineage is NOT verified by this program.',
                    'leaf_file':str(a.leaves),'vector_file':str(a.fbin),'dimension':vec.d,
                    'leaf_sample_count':len(results),'leaf_sample_rule':'uniform random leaves (no global pair weighting correction)',
                    'seed':a.seed,'gamma_requested':a.gamma if a.mode!='flags' else None,
                    'sampled_original_pairs':tot('original_pairs'),
                    'sampled_pairs_skipped':tot('pairs_skipped'),
                    'pair_savings_fraction':tot('pairs_skipped')/max(1,tot('original_pairs')),
                    'baseline_top2_proposal_events':tot('original_directed_top2'),
                    'retained_baseline_top2_events':tot('retained_original_top2'),
                    'top2_event_coverage':tot('retained_original_top2')/max(1,tot('original_directed_top2')),
                    'nearest_event_coverage':tot('retained_nearest_neighbor')/max(1,sum(r['size'] for r in results)),
                    'reduced_top2_proposal_events':tot('new_directed_proposals'),
                    'vertices_2_neighbors_fraction':tot('vertices_with_2_reduced_neighbors')/max(1,sum(r['size'] for r in results)),
                    'weighted_core_fraction':tot('core')/max(1,sum(r['size'] for r in results)),
                    'per_leaf_sample':results[:a.show_leaves]}
            if a.output:Path(a.output).write_text(json.dumps(output,indent=2),encoding='utf-8')
            json_print(output)
        finally:
            if cf:cf.close()
    finally:idx.close()


def cmd_validate(a):
    idx=LeafIndex(a.leaves)
    try:
        d=idx.summary(a.hash)
        rng=random.Random(a.seed)
        samp=sorted(rng.sample(range(idx.nleaves),min(a.sample,idx.nleaves)))
        dup=0
        for j in samp:
            ids=idx.leaf(j)
            if np.unique(ids).size!=ids.size:dup+=1
        d.update({'audit':'H18LEAF1_INPUT','sampled_duplicate_id_leaves':dup,'sampled_leaves':len(samp), 'note':'Sampled duplicate audit is not a full exhaustive ID check.'})
        if a.output:Path(a.output).write_text(json.dumps(d,indent=2),encoding='utf-8')
        json_print(d)
    finally:idx.close()


def losf_one(idx, order, workers, counts):
    remain=counts.copy();seen=np.zeros(idx.n,dtype=np.bool_)
    ever=int(np.count_nonzero(counts))
    active=0;peak=0;when_peak=0
    for j in range(0,len(order),workers):
        # Model a batch of up to W leaves concurrently in flight.
        batch=order[j:j+workers]
        # Intermediate copies for batch concurrency should not be counted more than once.
        ids=np.concatenate([idx.leaf(k).astype(np.int64) for k in batch])
        un=np.unique(ids)
        new=un[~seen[un]]
        seen[new]=True
        active+=len(new)
        if active>peak:peak=active;when_peak=j
        # Accumulate decreases so multi-leaf duplicate memberships are correct.
        dec=np.bincount(np.searchsorted(un,ids),minlength=len(un))
        if np.any(remain[un]<dec):raise ValueError('negative remaining membership: inconsistent leaves')
        remain[un]-=dec.astype(remain.dtype)
        finalize=un[remain[un]==0]
        active-=len(finalize)
    if active or np.any(remain):raise ValueError('Unfinished reservoirs after simulated scheduling')
    return {'workers_in_flight_model':workers,'peak_live_vertices':int(peak),
            'peak_live_fraction':peak/max(1,ever),
            'ever_present_vertices':ever,'peak_batch_start_index':int(when_peak),
            'note':'Idealized whole-leaf batches; excludes active flush time, per-edge buffers, synchronization, metadata, and RSS.'}


def cmd_losf(a):
    idx=LeafIndex(a.leaves)
    try:
        counts=np.zeros(idx.n,dtype=np.uint32)
        for i in range(idx.nleaves):
            ids=idx.leaf(i)
            if np.unique(ids).size!=ids.size:
                raise ValueError(f'Duplicate IDs within leaf {i}: requires separate accounting')
            counts[ids]+=1
        rng=random.Random(a.seed)
        base=np.arange(idx.nleaves,dtype=np.int64)
        orders={'original':base,'reverse':base[::-1],
                'small-first':np.argsort(idx.sizes,kind='stable'),
                'large-first':np.argsort(-idx.sizes.astype(np.int64),kind='stable')}
        if a.random_order:
            arr=base.copy();rng.shuffle(arr)
            orders['random']=arr
        reports=[]
        for key,order in orders.items():
            for workers in a.workers:
                r=losf_one(idx,order,workers,counts)
                r['order']=key
                reports.append(r)
        out={'audit':'LOSF-R0','status':'IDEALIZED_OFFLINE_SCHEDULING_ONLY',
             'leaf_file':str(a.leaves),'n_leaves':int(idx.nleaves),
             'memberships':int(idx.memberships), 'baseline_full_reservoir_vertices':int(idx.n),
             'scheduling_results':reports,
             'warning':'Live-front is NOT measured peak RSS. Memory savings require real reservoir allocations, scheduler and finalization correctness.'}
        if a.output:Path(a.output).write_text(json.dumps(out,indent=2),encoding='utf-8')
        json_print(out)
    finally:idx.close()


def make_fixture(folder):
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
    pts=np.array([[0,0],[10,0],[10,.01],[11,0],[0,.1],[10,-.01],[40,0],[40,.01]],dtype=np.float32)
    with open(folder/'toy.fbin','wb') as f:
        f.write(struct.pack('<ii',len(pts),2));f.write(pts.tobytes())
    leaves=[[0,1,2,3,4,5],[1,2,3,5,6],[0,2,4,6,7],[1,5,6,7]]
    with open(folder/'toy.leaves.bin','wb') as f:
        f.write(LEAF_MAGIC);f.write(struct.pack('<QQ',len(pts),len(leaves)))
        for leaf in leaves:
            f.write(struct.pack('<I',len(leaf)));f.write(np.array(leaf,dtype='<u4').tobytes())
    with open(folder/'toy.coreflags.bin','wb') as f:
        f.write(CORE_MAGIC);f.write(struct.pack('<Q',len(leaves)))
        for leaf in leaves:
            f.write(struct.pack('<I',len(leaf)))
            f.write(bytes([1 if x in [0,6] else 0 for x in leaf]))
    return folder


def cmd_selftest(a):
    folder=make_fixture(a.dir)
    idx=LeafIndex(folder/'toy.leaves.bin')
    try:
        assert idx.n==8 and idx.nleaves==4
        vec=Fbin(folder/'toy.fbin',idx.n)
        lf=idx.leaf(0)
        r=audit_one_leaf(lf,vec.rows[lf],'flags',0,random.Random(0),0,flags=np.array([1,0,0,0,0,0],dtype=bool))
        assert r['pairs_skipped']==10 and r['original_pairs']==15
        assert r['lost_original_top2']>0,'known Halo-Halo neighbors must be lost'
        cnt=np.zeros(idx.n,dtype=np.uint32)
        for i in range(idx.nleaves):cnt[idx.leaf(i)]+=1
        order=np.arange(idx.nleaves)
        one=losf_one(idx,order,1,cnt)
        four=losf_one(idx,order,4,cnt)
        assert one['peak_live_vertices']<=four['peak_live_vertices']
        cf=CoreFlags(folder/'toy.coreflags.bin',idx).bind(idx)
        assert len(cf.get(0))==6
        cf.close()
        json_print({'selftest':'PASS', 'fixture_directory':str(folder), 'H18_format':'PASS',
                    'CHARM_pair_count':'PASS','CHARM_HaloHalo_counterexample':'PASS',
                    'LOSF_no_negative_remaining':'PASS','LOSF_batch_monotonicity':'PASS',
                    'example_first_leaf':r,'example_losf_W1':one,'example_losf_W4':four,
                    'IMPORTANT':'Synthetic fixture only; NOT a SIFT1M benchmark or evidence of real CHARM effectiveness.'})
    finally:idx.close()


def main():
    parser=argparse.ArgumentParser(description=__doc__,formatter_class=argparse.RawDescriptionHelpFormatter)
    sub=parser.add_subparsers(dest='cmd',required=True)
    pv=sub.add_parser('validate',help='Validate H18LEAF1 and compute total leaf pair events')
    pv.add_argument('--leaves',required=True);pv.add_argument('--sample',type=int,default=128)
    pv.add_argument('--seed',type=int,default=20261029);pv.add_argument('--hash',action='store_true');pv.add_argument('--output')
    pv.set_defaults(func=cmd_validate)
    pc=sub.add_parser('charm',help='Sampled Top2 retention under explicitly labeled Core/Halo scenarios')
    pc.add_argument('--leaves',required=True);pc.add_argument('--fbin',required=True)
    pc.add_argument('--mode',choices=['random','centroid-proxy','degree-oracle','flags'],default='centroid-proxy')
    pc.add_argument('--core-flags',help='H29CORE1 genuine masks emitted by a provenance-checked instrumented builder')
    pc.add_argument('--gamma',type=float,default=.25);pc.add_argument('--sample',type=int,default=32)
    pc.add_argument('--seed',type=int,default=20261029);pc.add_argument('--show-leaves',type=int,default=5);pc.add_argument('--output')
    pc.set_defaults(func=cmd_charm)
    pl=sub.add_parser('losf',help='Idealized front-width scheduling analysis (no build)')
    pl.add_argument('--leaves',required=True);pl.add_argument('--workers',type=int,nargs='+',default=[1,4])
    pl.add_argument('--seed',type=int,default=20261029);pl.add_argument('--random-order',action='store_true');pl.add_argument('--output')
    pl.set_defaults(func=cmd_losf)
    pt=sub.add_parser('selftest',help='Create fixture and run deterministic safety assertions')
    pt.add_argument('--dir',default='r29_fixture');pt.set_defaults(func=cmd_selftest)
    args=parser.parse_args()
    if args.cmd=='charm' and not (0<=args.gamma<=1):parser.error('--gamma must be in [0,1]')
    if args.cmd=='charm' and args.sample<=0:parser.error('--sample must be positive')
    if args.cmd=='losf' and (not args.workers or any(w<=0 for w in args.workers)):parser.error('--workers must be positive')
    args.func(args)

if __name__=='__main__':
    main()
