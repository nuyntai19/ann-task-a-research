#!/usr/bin/env python3
"""H26-P2b: offline pair-reuse locality audit of one pinned PiPNN H18 capture.

WARNING: leaf capture IDs are NOT a guaranteed temporal execution order under
parallel_for. Window hits are idealized serial leaf-ID locality, not cache hit
rates or actual speedups. No PiPNN code is modified.
"""
from __future__ import annotations
import argparse
import bisect
import json
import math
import time
from pathlib import Path

import numpy as np
from h26_p2_pair_reuse_audit import read_capture, digest, EXPECTED_SHA, DEFAULT_CAPTURE, BINS

WINDOWS=(1,4,16,64,256,1024,4096,16384,65536,85529)
MULT_THRESHOLDS=(2,3,4,5,8,16)


def analyze(cap, samples, seed, progress=True):
    if samples < 1000:
        raise RuntimeError('Require at least 1000 samples')
    start=time.perf_counter()
    sizes=cap['sizes']
    w=sizes*(sizes-1)//2
    if int(np.sum(w)) != cap['offdiag']:
        raise RuntimeError('Invalid pair workload')
    rng=np.random.default_rng(seed)
    selected=rng.choice(cap['leaves'],size=samples,replace=True,p=w/np.sum(w))
    counts=sizes[selected]
    posa=rng.integers(0,counts)
    posb=rng.integers(0,counts-1)
    posb+=(posb>=posa)
    offs=np.asarray(cap['offsets'][selected],dtype=np.int64)
    ev=cap['events']
    va=np.asarray(ev[offs+2*posa]>>np.uint64(32),dtype=np.int32)
    vb=np.asarray(ev[offs+2*posb]>>np.uint64(32),dtype=np.int32)
    if np.any(va<0) or np.any(vb<0) or np.any(va>=cap['n']) or np.any(vb>=cap['n']) or np.any(va==vb):
        raise RuntimeError('Invalid pair endpoints in capture')
    # Inverted index built ONLY for sampled vertices: memory O(incidences of sampled endpoints).
    endpoint_ids, rev = np.unique(np.concatenate((va,vb)),return_inverse=True)
    direct=np.full(cap['n'],-1,dtype=np.int32)
    direct[endpoint_ids]=np.arange(len(endpoint_ids),dtype=np.int32)
    incidence=[[] for _ in range(len(endpoint_ids))]
    if progress: print(f'H26P2B_SAMPLE count={samples} endpoints={len(endpoint_ids)}',flush=True)
    leaf_offsets=cap['offsets']
    for i in range(cap['leaves']):
        a=int(leaf_offsets[i]);b=int(leaf_offsets[i+1])
        src0=np.asarray(ev[a:b:2]>>np.uint64(32),dtype=np.int32)
        src1=np.asarray(ev[a+1:b:2]>>np.uint64(32),dtype=np.int32)
        if len(src0)!=int(sizes[i]) or not np.array_equal(src0,src1) or len(np.unique(src0))!=len(src0):
            raise RuntimeError(f'Invalid paired proposals or repeated leaf sources at leaf={i}')
        if np.any(src0<0) or np.any(src0>=cap['n']):
            raise RuntimeError(f'Out-of-range source at leaf={i}')
        matched=direct[src0]
        for p in matched[matched>=0]: incidence[int(p)].append(i)
        if progress and (i+1)%25000==0:
            print(f'H26P2B_INDEX_PROGRESS {i+1}/{cap["leaves"]}',flush=True)
    # Sorted integer leaf lists; each source unique within one leaf by validation.
    m=np.empty(samples,dtype=np.int16)
    prior_lag=np.full(samples,cap['leaves']+1,dtype=np.int32)
    prior_exists=np.zeros(samples,dtype=np.bool_)
    for s in range(samples):
        a=incidence[int(rev[s])]
        b=incidence[int(rev[s+samples])]
        x=y=0
        match=[]
        while x<len(a) and y<len(b):
            if a[x]==b[y]:
                match.append(a[x]);x+=1;y+=1
            elif a[x]<b[y]:x+=1
            else:y+=1
        if not match or len(match)>32767:
            raise RuntimeError(f'Invalid pair multiplicity: {len(match)}')
        i=int(selected[s])
        j=bisect.bisect_left(match,i)
        if j>=len(match) or match[j]!=i:
            raise RuntimeError(f'Sampled leaf missing from pair incidence at sample={s}')
        m[s]=len(match)
        if j:
            prior_exists[s]=True
            prior_lag[s]=i-match[j-1]
    expected_redundancy=float(np.mean(1.0-1.0/m.astype(float)))
    observed_prior=float(np.mean(prior_exists))
    # If sampling is uniform among pair occurrences, both target the same
    # redundancy fraction. They differ due to Monte Carlo variation.
    windows={str(W): {
         'ideal_serial_leaf_id_hit_fraction':float(np.mean(prior_exists & (prior_lag<=W))),
         'sampling_hoeffding_95ci':[max(0.,float(np.mean(prior_exists & (prior_lag<=W)))-math.sqrt(math.log(40)/(2*samples))),
                                    min(1.,float(np.mean(prior_exists & (prior_lag<=W)))+math.sqrt(math.log(40)/(2*samples)))]
         } for W in WINDOWS}
    oracle_selective={str(k): float(np.mean(np.where(m>=k,1.-1./m,0.))) for k in MULT_THRESHOLDS}
    lags=prior_lag[prior_exists]
    def perbin(lo,hi):
        selected_bin=(counts>=lo)&(counts<=hi)
        n=int(np.sum(selected_bin))
        if n==0:return None
        return {
          'samples':n,
          'prior_occurred_fraction':float(np.mean(prior_exists[selected_bin])),
          'within_64_leaf_ids_fraction':float(np.mean(prior_exists[selected_bin] & (prior_lag[selected_bin]<=64))),
          'within_1024_leaf_ids_fraction':float(np.mean(prior_exists[selected_bin] & (prior_lag[selected_bin]<=1024))),
          'mean_oracle_redundancy':float(np.mean(1-1/m[selected_bin].astype(float)))
        }
    bins={f'{lo}-{hi}' if hi<10_000_000 else f'{lo}+':perbin(lo,hi) for lo,hi in BINS}
    return dict(
        study='H26_P2B_H18_OFFLINE_LEAF_ID_LOCALITY',
        capture_sha256=digest(cap['path']),
        samples=samples,seed=seed,
        total_pair_occurrences=cap['offdiag'],capture_leaves=cap['leaves'],
        estimated_global_oracle_redundancy=expected_redundancy,
        fraction_sampled_occurrences_with_prior_leaf_id=observed_prior,
        ideal_serial_leaf_id_window_hit_fraction=windows,
        selective_oracle_redundancy_achievable_if_only_multiplicity_ge=oracle_selective,
        prior_leaf_id_gap_quantiles=(dict(zip(('q10','q25','median','q75','q90','q99'),
            [float(v) for v in np.quantile(lags,[.1,.25,.5,.75,.9,.99])])) if len(lags) else {}),
        samples_with_prior_occurrence=int(np.sum(prior_exists)),
        bins=bins,
        independent_sample_Hoeffding_halfwidth=math.sqrt(math.log(40)/(2*samples)),
        theoretical_minimum_full_cache_12B_per_unique_pair_gb_decimal=(cap['offdiag']*(1-expected_redundancy)*12/1e9),
        theoretical_minimum_full_cache_12B_per_unique_pair_gib=(cap['offdiag']*(1-expected_redundancy)*12/(1024**3)),
        warnings=[
          'Leaf IDs/capture order are NOT measured execution timestamps or scheduler order: window figures are NOT observed cache-hit rates.',
          'Window figure assumes perfect pair lookup, zero overhead, infinite capacity while retained, and exact sharing across workers.',
          'Selective oracle values assume advance knowledge of global pair multiplicities and omit all indexing costs.',
          '12 bytes per unique key is a lower bound only: 8B unordered pair key plus 4B float distance; no hashing/alignment/memory management.',
          'Eigen rankUpdate uses optimized batched kernel; pairwise lookup likely destroys arithmetic throughput and incurs synchronization.',
          'Estimates pertain only to pinned H18 capture; no BUILD-seed or dataset variability.',
          'Does not demonstrate any real BUILD speedup, graph benefit, Pareto advantage, or ANN research novelty.'
        ],
        elapsed_seconds=round(time.perf_counter()-start,2)
    )


def synthetic_test():
    # leaves: pair (0,1) at leaf IDs 0,1,2; pair (0,2) at 0 and 3.
    import struct,tempfile
    from h26_p2_pair_reuse_audit import MAGIC
    leaves=[[0,1,2],[0,1,3],[0,1,4],[0,2,3]]
    with tempfile.TemporaryDirectory() as tmp:
        path=Path(tmp)/'small.bin'
        events=[];ofs=[0]
        for ids in leaves:
            for u in ids:
                for v in [x for x in ids if x!=u][:2]:
                    events.append((u<<32)|v)
            ofs.append(len(events))
        with path.open('wb') as f:
            f.write(struct.pack('<8sQQQ',MAGIC,5,len(leaves),len(events)))
            f.write(np.asarray(ofs,dtype='<u8').tobytes())
            f.write(np.asarray(events,dtype='<u8').tobytes())
        cap=read_capture(path,strict=False)
        report=analyze(cap,15000,42,progress=False)
        # 4 leaves * C(3,2)=12 occurrence events.
        # Pair (0,1): 3 occurrences, pair (0,2): 2 occurrences,
        # pair (0,3): 2 occurrences; 8 distinct keys => 4/12 redundancy.
        ideal=4./12.
        if abs(report['estimated_global_oracle_redundancy']-ideal)>0.025:
            raise RuntimeError(f'Oracle test failed {report["estimated_global_oracle_redundancy"]} != {ideal}')
        if abs(report['fraction_sampled_occurrences_with_prior_leaf_id']-ideal)>0.025:
            raise RuntimeError('Prior occurrence sampling test failed')
        local=report['ideal_serial_leaf_id_window_hit_fraction']
        if not (0<=local['1']['ideal_serial_leaf_id_hit_fraction']<=local['65536']['ideal_serial_leaf_id_hit_fraction']<=1):
            raise RuntimeError('Window monotonicity failed')
        if abs(local['85529']['ideal_serial_leaf_id_hit_fraction']-ideal)>0.025:
            raise RuntimeError('Full-window oracle test failed')
        if abs(local['1']['ideal_serial_leaf_id_hit_fraction']-(2/12))>0.025:
            raise RuntimeError('Window=1 test failed')
        if report['theoretical_minimum_full_cache_12B_per_unique_pair_gb_decimal']<=0:
            raise RuntimeError('Memory estimate sanity check failed')
        print('H26P2B_SYNTHETIC_PASS', 'oracle_expected=0.333333',
              f'oracle_observed={report["estimated_global_oracle_redundancy"]:.5f}',
              f'prior_observed={report["fraction_sampled_occurrences_with_prior_leaf_id"]:.5f}')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--mode',choices=['selftest','run'],required=True)
    p.add_argument('--capture',type=Path,default=DEFAULT_CAPTURE)
    p.add_argument('--samples',type=int,default=30000)
    p.add_argument('--seed',type=int,default=42)
    p.add_argument('--out',type=Path)
    a=p.parse_args()
    if a.mode=='selftest':synthetic_test();return
    path=a.capture
    if not path.is_file():raise RuntimeError(f'Missing input capture: {path}')
    print('Checking pinned H18 capture provenance...',flush=True)
    actual=digest(path)
    if actual!=EXPECTED_SHA:raise RuntimeError(f'Unexpected SHA256: {actual}')
    cap=read_capture(path,strict=True)
    out=a.out or (Path.home()/f'ann-task-a/experiments/H26/H26_P2B_locality_H18_seed{a.seed}_n{a.samples}')
    if out.exists():raise RuntimeError(f'Output directory already exists: {out}')
    result=analyze(cap,a.samples,a.seed)
    if result['capture_sha256']!=EXPECTED_SHA:raise RuntimeError('Capture changed during run')
    out.mkdir(parents=True,exist_ok=False)
    (out/'h26_p2b_locality.json').write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n')
    outtext=['H26-P2b: OFFLINE LEAF-ID REUSE LOCALITY (NOT actual cache hits)',
        f'LEAVES={cap["leaves"]:,} SAMPLES={a.samples:,} SEED={a.seed}',
        f'ORACLE_REDUNDANT_FRACTION={100*result["estimated_global_oracle_redundancy"]:.3f}%',
        f'FRACTION_HAS_EARLIER_LEAF_ID={100*result["fraction_sampled_occurrences_with_prior_leaf_id"]:.3f}%',
        f'FULL_CACHE_LOWER_BOUND={result["theoretical_minimum_full_cache_12B_per_unique_pair_gb_decimal"]:.2f} GB (no metadata)',
        'IDEAL_SERIAL_LEAF_ID_WINDOW (NOT actual temporal locality, not real cache hit rate):']
    for k,v in result['ideal_serial_leaf_id_window_hit_fraction'].items():
        outtext.append(f'  W={int(k):>6} leaf IDs: {100*v["ideal_serial_leaf_id_hit_fraction"]:7.3f}% of ALL pair occurrences')
    outtext.append('ORACLE selective caching upper bounds (global m known in hindsight):')
    for k,v in result['selective_oracle_redundancy_achievable_if_only_multiplicity_ge'].items():
        outtext.append(f'  m >= {int(k):>2}: {100*v:7.3f}% of ALL pair occurrences')
    outtext.append('GAP_QUANTILES among occurrences with an earlier leaf ID:')
    outtext.append(str(result['prior_leaf_id_gap_quantiles']))
    outtext.extend(['IMPORTANT: all window metrics rely on leaf/capture ID order, NOT verified scheduler or wall-clock order.',
        'No speedup or feasible cache claim; evaluate against optimized Eigen blocked rankUpdate.',
        'H26P2B_DONE '+str(out)])
    txt='\n'.join(outtext)+'\n'
    (out/'h26_p2b_locality.txt').write_text(txt)
    print(txt)


if __name__=='__main__':
    try:main()
    except Exception as exc:raise SystemExit(f'H26P2B_FAIL_CLOSED: {exc}')
