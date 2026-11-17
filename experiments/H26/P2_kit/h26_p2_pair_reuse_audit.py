#!/usr/bin/env python3
"""H26-P2: unbiased offline sampling of repeated undirected point pairs across PiPNN leaves.

This does not speed up BUILD, measure cache utility, or prove novelty.
A pair occurrence is an unordered pair of distinct vertices within one leaf.
Capture format from H18-R1; leaf member list reconstructed from directed sources.
"""
from __future__ import annotations
import argparse
import collections
import hashlib
import json
import math
import struct
import tempfile
import time
from pathlib import Path

import numpy as np

MAGIC=b'H18R1P01'
EXPECTED_SHA='13e78697bb4e56b5013ee2df3b6c7cee4daa1cfad0185f56a576448d428ccc95'
DEFAULT_CAPTURE=Path.home()/'ann-task-a/experiments/H18/phase2_candidate_audit/leaf_proposals.bin'
EXPECTED=(1000000,85529,59990170)
EXPECTED_ROWS=29995085
EXPECTED_OFFDIAG=7289822248
EXPECTED_TRIANGULAR=7319817333
BINS=[(2,63),(64,127),(128,255),(256,383),(384,511),(512,767),(768,1023),(1024,1535),(1536,10_000_000)]


def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda:f.read(8*1024*1024),b''):h.update(b)
    return h.hexdigest()


def read_capture(path,strict=True):
    if not path.is_file():raise RuntimeError(f'Missing H18 capture: {path}')
    with path.open('rb') as f:head=f.read(32)
    if len(head)!=32:raise RuntimeError('Invalid capture header length')
    magic,n,l,e=struct.unpack('<8sQQQ',head)
    if magic!=MAGIC:raise RuntimeError(f'Wrong magic: {magic!r}')
    if strict and (n,l,e)!=EXPECTED:raise RuntimeError(f'H18 shape mismatch: {n,l,e}')
    if path.stat().st_size!=32+8*(l+1)+8*e:raise RuntimeError('H18 file byte size mismatch')
    off=np.memmap(path,dtype='<u8',mode='r',offset=32,shape=(l+1,))
    events=np.memmap(path,dtype='<u8',mode='r',offset=32+8*(l+1),shape=(e,))
    if int(off[0])!=0 or int(off[-1])!=e or np.any(np.diff(off.astype(np.int64))<0):
        raise RuntimeError('Invalid leaf offsets')
    diff=np.diff(off.astype(np.int64))
    if np.any(diff%2):raise RuntimeError('Cannot reconstruct leaf membership: odd proposals/leaf')
    sizes=diff//2
    if np.any(sizes<2) or np.any(sizes>2048):raise RuntimeError('Unexpected leaf size outside [2,2048]')
    rows=int(sizes.sum())
    offdiag=int(np.sum(sizes*(sizes-1)//2))
    triangle=int(np.sum(sizes*(sizes+1)//2))
    if strict and (rows,offdiag,triangle)!=(EXPECTED_ROWS,EXPECTED_OFFDIAG,EXPECTED_TRIANGULAR):
        raise RuntimeError(f'P1B/H18 workload mismatch! rows,pairs,triangle={(rows,offdiag,triangle)}')
    return dict(path=path,n=int(n),leaves=int(l),events_count=int(e),offsets=off,events=events,
                sizes=sizes,rows=rows,offdiag=offdiag,triangle=triangle)


def intersection_count(x,y):
    # x,y: lists of leaf IDs, in ascending order, each with no duplicates
    i=j=k=0
    while i<len(x) and j<len(y):
        if x[i]==y[j]:k+=1;i+=1;j+=1
        elif x[i]<y[j]:i+=1
        else:j+=1
    return k


def stats_for(values,lower,upper):
    if len(values)==0:return None
    z=np.asarray(values,dtype=np.float64)
    mean=float(np.mean(1.0-1.0/z))
    prob=float(np.mean(z>1))
    hw=math.sqrt(math.log(40)/(2*len(z))) # Hoeffding two-sided alpha=0.05
    return dict(n=len(z),fraction_pair_occurrences_with_multiplicity_gt_1=prob,
                estimated_redundant_pair_occurrence_fraction=mean,
                ci95_hoeffding=[max(lower,mean-hw),min(upper,mean+hw)],
                multiplicity_mean_occurrence_weighted=float(np.mean(z)),
                multiplicity_max_in_sample=int(np.max(z)),
                multiplicity_histogram={str(k):int(v) for k,v in sorted(collections.Counter(int(m) for m in z).items())})


def audit(cap,samples,seed,progress=True):
    if samples<100:raise RuntimeError('Need >=100 pair occurrence samples')
    t=time.perf_counter()
    n=cap['sizes']; weight=n*(n-1)//2
    assert int(weight.sum())==cap['offdiag']
    rng=np.random.default_rng(seed)
    chosen=rng.choice(len(n),size=samples,replace=True,p=weight/weight.sum())
    count=n[chosen]
    ia=rng.integers(0,count)
    ib=rng.integers(0,count-1)
    ib+= (ib>=ia)
    offs=cap['offsets'][chosen].astype(np.int64)
    src_a=(np.asarray(cap['events'][offs+2*ia])>>np.uint64(32)).astype(np.int32)
    src_b=(np.asarray(cap['events'][offs+2*ib])>>np.uint64(32)).astype(np.int32)
    if np.any(src_a<0) or np.any(src_b<0) or np.any(src_a>=cap['n']) or np.any(src_b>=cap['n']) or np.any(src_a==src_b):
        raise RuntimeError('Invalid sampled source membership: H18 capture not suitable')
    unique_verts,reverse=np.unique(np.concatenate((src_a,src_b)),return_inverse=True)
    rev_a=reverse[:samples];rev_b=reverse[samples:]
    direct=np.full(cap['n'],-1,dtype=np.int32)
    direct[unique_verts]=np.arange(len(unique_verts),dtype=np.int32)
    incidence=[[] for _ in range(len(unique_verts))]
    if progress:print(f'SAMPLED {samples:,} pair OCCURRENCES, distinct endpoints={len(unique_verts):,}',flush=True)
    ev=cap['events'];offsets=cap['offsets']
    for leaf in range(cap['leaves']):
        a=int(offsets[leaf]);b=int(offsets[leaf+1]);
        f=np.asarray(ev[a:b:2]);g=np.asarray(ev[a+1:b:2])
        src=(f>>np.uint64(32)).astype(np.int32)
        if not np.array_equal(src,(g>>np.uint64(32)).astype(np.int32)):
            raise RuntimeError(f'Leaf {leaf}: expected exactly two proposal events per source')
        if np.unique(src).size!=src.size:
            raise RuntimeError(f'Leaf {leaf}: duplicate source ID')
        if np.any(src>=cap['n']) or np.any(src<0):
            raise RuntimeError(f'Leaf {leaf}: invalid source ID')
        hit=direct[src]
        for vi in hit[hit>=0]: incidence[int(vi)].append(leaf)
        if progress and (leaf+1)%25000==0:
            print(f'INDEX_PROGRESS {leaf+1}/{cap["leaves"]} leaves',flush=True)
    if progress:print('MEMBERSHIP_INDEX_BUILT, checking pair multiplicities...',flush=True)
    multi=np.empty(samples,dtype=np.int32)
    for i in range(samples):
        m=intersection_count(incidence[int(rev_a[i])],incidence[int(rev_b[i])])
        if m<1:raise RuntimeError(f'Pair sample {i}: sampled leaf missing from incidence intersection')
        multi[i]=m
    all_stats=stats_for(multi,0,1)
    perbin={}
    for lo,hi in BINS:
        keep=(count>=lo)&(count<=hi)
        label=f'{lo}-{hi}' if hi<10_000_000 else f'{lo}+'
        perbin[label]=stats_for(multi[keep],0,1)
    # Observation-weighted mean(1/m) estimates number of distinct unordered
    # vertex-pair keys divided by total pair occurrences, without listing pairs.
    unique_fraction=1-all_stats['estimated_redundant_pair_occurrence_fraction']
    return dict(study='H26_P2_OFFLINE_H18_PAIR_REUSE_AUDIT',
                capture_path=str(cap['path']), capture_shape={'n':cap['n'],'leaves':cap['leaves'],
                    'proposal_events':cap['events_count'],'rows':cap['rows'],
                    'total_undirected_offdiag_pair_occurrences':cap['offdiag'],
                    'triangular_pair_dim_proxy_at_dim128':cap['triangle']*128},
                method='Independent sample with replacement: select leaf proportional to C(n,2); sample unordered distinct pair within leaf; scan all leaf memberships and count multiplicity of each sampled pair.',
                sample_size=samples, seed=seed, all_pair_occurrences=all_stats, per_leaf_size_bin=perbin,
                estimated_unique_pair_fraction_of_total_occurrences=unique_fraction,
                estimated_distinct_undirected_pair_keys=int(round(cap['offdiag']*unique_fraction)),
                elapsed_seconds=round(time.perf_counter()-t,2),
                not_proven=['A repeated mathematical point pair causes avoidable time in Eigen rankUpdate',
                            'A pair-distance cache could beat BLAS/Eigen matrix kernels',
                            'A cache can be implemented without extra synchronization/memory overhead',
                            'A new algorithm or a speedup has been demonstrated',
                            'Replicability across BUILD seeds/datasets'],
                warnings=['Confidence interval is only for independent sampling of one pinned H18 capture, NOT across BUILD seeds.',
                          'Proposal duplicate fraction is NOT pair-computation redundancy.',
                          'Pair multiplicity ignores diagonal; distance matrix also includes diagonals.',
                          'Floating-point tie behavior and kernel execution order may matter for exact equivalence.'])


def synthetic_test():
    leaves=[[0,1,2,3],[0,1,2,4],[0,1,3,4]]
    with tempfile.TemporaryDirectory() as td:
        path=Path(td)/'test.bin'
        ev=[];ofs=[0]
        for ids in leaves:
            for u in ids:
                neigh=[v for v in ids if v!=u][:2]
                for v in neigh:ev.append((u<<32)|v)
            ofs.append(len(ev))
        with path.open('wb') as f:
            f.write(struct.pack('<8sQQQ',MAGIC,5,len(leaves),len(ev)))
            f.write(np.asarray(ofs,dtype='<u8').tobytes())
            f.write(np.asarray(ev,dtype='<u8').tobytes())
        cap=read_capture(path,strict=False)
        # 18 pair occurrences, 10 distinct undirected vertex pairs; fraction 8/18
        if cap['offdiag']!=18:raise RuntimeError('Synthetic test wrong workload')
        report=audit(cap,30000,42,progress=False)
        value=report['all_pair_occurrences']['estimated_redundant_pair_occurrence_fraction']
        if abs(value-(8/18))>0.012:
            raise RuntimeError(f'Sampling estimator self-test FAIL: value={value}, expected={8/18}')
        # Direct ground truth: pair (0,1) appears in all three leaves.
        if intersection_count([0,1,2],[0,1,2])!=3:raise RuntimeError('Intersection test failed')
        print(f'H26P2_SYNTHETIC_PASS theoretical_redundancy={8/18:.6f} observed={value:.6f}')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--mode',choices=['selftest','run'],required=True)
    p.add_argument('--capture',type=Path,default=DEFAULT_CAPTURE)
    p.add_argument('--samples',type=int,default=30000)
    p.add_argument('--seed',type=int,default=42)
    p.add_argument('--out',type=Path,default=None)
    a=p.parse_args()
    if a.mode=='selftest':synthetic_test();return
    out=a.out or (Path.home()/f'ann-task-a/experiments/H26/H26_P2_pair_audit_H18_seed{a.seed}_n{a.samples}')
    if out.exists():raise RuntimeError(f'Output directory already exists: {out}. Do not overwrite existing experiments.')
    cap=read_capture(a.capture)
    print('Verifying H18 SHA256 provenance...',flush=True)
    actual=digest(a.capture)
    if actual!=EXPECTED_SHA:raise RuntimeError(f'SHA256 MISMATCH: {actual}, expected {EXPECTED_SHA}')
    print(f'H26P2_INPUT_VALID sha256={actual} leaves={cap["leaves"]} offdiag_pairs={cap["offdiag"]:,}',flush=True)
    result=audit(cap,a.samples,a.seed)
    result['capture_sha256']=actual
    out.mkdir(parents=True,exist_ok=False)
    (out/'h26_p2_pair_audit.json').write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    s=result['all_pair_occurrences']
    text=(f'H26-P2 PAIR REUSE AUDIT (offline, weighted pair occurrence sampling)\n'
          f'H18_CAPTURE_LEAVES={cap["leaves"]}\n'
          f'OFFDIAGONAL_PAIR_OCCURRENCES={cap["offdiag"]:,}\n'
          f'SAMPLE_COUNT={a.samples:,} SEED={a.seed}\n'
          f'P_MULTIPLICITY_GT1={100*s["fraction_pair_occurrences_with_multiplicity_gt_1"]:.3f}%\n'
          f'REDUNDANT_OCCURRENCE_FRACTION={100*s["estimated_redundant_pair_occurrence_fraction"]:.3f}%\n'
          f'SAMPLING_ONLY_HOEFFDING_95CI={100*s["ci95_hoeffding"][0]:.3f}%..{100*s["ci95_hoeffding"][1]:.3f}%\n'
          f'EST_UNIQUE_UNDIRECTED_PAIR_KEYS={result["estimated_distinct_undirected_pair_keys"]:,}\n'
          f'NOTE: This is arithmetic work redundancy potential, NOT demonstrated kernel or BUILD speedup.\n'
          f'NOTE: The CI does NOT include between-BUILD variance.\n'
          f'\nPER_BIN (conditional on sampled pair occurrence in bin):\n')
    for k,v in result['per_leaf_size_bin'].items():
        if v is not None:
            text+=f'  {k:>11s} samples={v["n"]:>6} redundant={100*v["estimated_redundant_pair_occurrence_fraction"]:6.2f}% probability_mult_gt1={100*v["fraction_pair_occurrences_with_multiplicity_gt_1"]:6.2f}%\n'
    (out/'h26_p2_pair_audit.txt').write_text(text,encoding='utf-8')
    print(text)
    print('H26P2_DONE',out)


if __name__=='__main__':
    try:main()
    except Exception as e:
        raise SystemExit(f'H26P2_FAIL_CLOSED: {e}')
