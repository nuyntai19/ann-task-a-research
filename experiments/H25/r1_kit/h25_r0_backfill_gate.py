#!/usr/bin/env python3
"""H25-R0: offline candidate-backfill falsification test; never edits graph/capture.

Source: H18-R1 per-leaf directed proposals (H18R1P01), SIFT1M fbin.
This does NOT measure BUILD speedup, final graph Recall/QPS, or prove novelty.
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
import os
import struct
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
import numpy as np

MAGIC = b'H18R1P01'
EXPECTED_SHA = '13e78697bb4e56b5013ee2df3b6c7cee4daa1cfad0185f56a576448d428ccc95'
EXPECTED = {'n': 1_000_000, 'leaves': 85_529, 'events': 59_990_170}
DEFAULT_CAPTURE = Path.home() / 'ann-task-a/experiments/H18/phase2_candidate_audit/leaf_proposals.bin'
DEFAULT_BASE = Path.home() / 'ann-task-a/data/sift1m.fbin'
DEFAULT_OUT = Path.home() / 'ann-task-a/experiments/H25/r0_candidate_backfill_sift1m_seed42'


def sha256(path: Path) -> str:
    h=hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(8*1024*1024), b''): h.update(block)
    return h.hexdigest()


def available_gib() -> float | None:
    try:
        for line in Path('/proc/meminfo').read_text().splitlines():
            if line.startswith('MemAvailable:'):
                return int(line.split()[1])/1024**2
    except OSError: pass
    return None


@dataclass
class Capture:
    path: Path
    n: int
    nleaves: int
    total: int
    offsets: np.memmap
    events: np.memmap


def read_capture(path: Path, allow_other_shape=False) -> Capture:
    if not path.is_file(): raise RuntimeError(f'Missing capture: {path}')
    with path.open('rb') as f: head = f.read(32)
    if len(head)!=32: raise RuntimeError('Capture too short for 32-byte header')
    magic,n,leaves,total=struct.unpack('<8sQQQ',head)
    if magic!=MAGIC: raise RuntimeError(f'Unexpected magic {magic!r}; expected {MAGIC!r}')
    if not allow_other_shape and (n,leaves,total)!=(EXPECTED['n'],EXPECTED['leaves'],EXPECTED['events']):
        raise RuntimeError(f'Capture shape {(n,leaves,total)} differs from H18-R1 expected {tuple(EXPECTED.values())}')
    correct_size=32+8*(leaves+1)+8*total
    if path.stat().st_size!=correct_size:
        raise RuntimeError(f'Capture size mismatch: found {path.stat().st_size}, expected {correct_size}')
    offsets=np.memmap(path,dtype='<u8',mode='r',offset=32,shape=(leaves+1,))
    events=np.memmap(path,dtype='<u8',mode='r',offset=32+8*(leaves+1),shape=(total,))
    if int(offsets[0])!=0 or int(offsets[-1])!=total or np.any(offsets[1:]<offsets[:-1]):
        raise RuntimeError('Offsets are not monotonic [0..events]')
    return Capture(path,int(n),int(leaves),int(total),offsets,events)


def read_fbin(path: Path, expected_n: int) -> tuple[np.memmap,int]:
    if not path.is_file(): raise RuntimeError(f'Missing fbin: {path}')
    with path.open('rb') as f: head=f.read(8)
    if len(head)!=8: raise RuntimeError('fbin too short')
    n,d=struct.unpack('<II',head)
    if n!=expected_n or d<=0 or d>100_000:
        raise RuntimeError(f'fbin dimensions ({n},{d}) unexpected (expected n={expected_n})')
    if path.stat().st_size!=8+4*n*d:
        raise RuntimeError('fbin file size != 8 + n*d*sizeof(float32)')
    return np.memmap(path,dtype='<f4',mode='r',offset=8,shape=(n,d)),d


def extract_leaf(cap: Capture, leaf_id: int) -> tuple[np.ndarray,np.ndarray,np.ndarray]:
    """Return source IDs, two destinations/source and flat captured proposal positions.

    The writer puts each source's MST_DEG proposals adjacent within each disjoint leaf span.
    Refuse if source ordering/grouping/provenance does not match.
    """
    a,b=int(cap.offsets[leaf_id]),int(cap.offsets[leaf_id+1]); span=b-a
    if span<6 or span%2: raise RuntimeError(f'leaf={leaf_id} not eligible: {span} events')
    e=np.asarray(cap.events[a:b],dtype=np.uint64)
    src=(e>>np.uint64(32)).astype(np.uint32).reshape(-1,2)
    dst=(e&np.uint64(0xffffffff)).astype(np.uint32).reshape(-1,2)
    if not np.all(src[:,0]==src[:,1]):
        raise RuntimeError(f'leaf={leaf_id} proposals not grouped exactly 2/source; abort')
    u=src[:,0]
    if np.unique(u).size!=u.size: raise RuntimeError(f'leaf={leaf_id} duplicate source occurrences')
    if np.any(u>=cap.n) or np.any(dst>=cap.n): raise RuntimeError(f'leaf={leaf_id} invalid node ID')
    if np.any(dst==u[:,None]) or np.any(dst[:,0]==dst[:,1]):
        raise RuntimeError(f'leaf={leaf_id} self-edge or duplicate within same source')
    if not np.all(np.isin(dst,u)):
        raise RuntimeError(f'leaf={leaf_id} destination outside reconstructed leaf membership')
    pos=np.arange(a,b,dtype=np.int64).reshape(-1,2)
    return u,dst,pos


def local_ranks(X: np.ndarray, ids: np.ndarray, rank: int) -> tuple[np.ndarray,np.ndarray]:
    """Blocked per-leaf float32 L2^2; distances are recomputed ONLY by oracle.

    Candidate ranking may vary at ties/float32 rounding vs Eigen; compare Top2 before using.
    """
    pts=np.asarray(X[ids],dtype=np.float32)
    sq=np.sum(pts*pts,axis=1,dtype=np.float32)
    D=np.asarray((-2.0*np.matmul(pts,pts.T)),dtype=np.float32)
    D+=sq[:,None]
    D+=sq[None,:]
    np.fill_diagonal(D,np.inf)
    k=min(rank,len(ids)-1)
    ids_local=np.argpartition(D,kth=k-1,axis=1)[:,:k]
    vals=np.take_along_axis(D,ids_local,axis=1)
    # tie break by leaf-local index, since PiPNN packs (distance,local index)
    order=np.lexsort((ids_local,vals),axis=1)
    ids_local=np.take_along_axis(ids_local,order,axis=1)
    return np.asarray(ids[ids_local],dtype=np.uint32),np.take_along_axis(vals,order,axis=1)


def lookup_key(key: int, keys: np.ndarray, first: np.ndarray) -> tuple[bool,int]:
    j=int(np.searchsorted(keys,np.uint64(key)))
    if j<len(keys) and int(keys[j])==key: return True,int(first[j])
    return False,-1


def collect_global_first(cap: Capture):
    """Exact, memory-intensive sorted unique keys and first event positions."""
    return np.unique(cap.events,return_index=True)


def choose_tail(ranked: np.ndarray, original: np.ndarray, u: int, pos: int,
                keys:np.ndarray, first:np.ndarray, extra:set[int], mode:str,
                rng:np.random.Generator) -> int|None:
    # Tail excludes ranks 1/2 and the original captured top-2, even at numerical ties.
    tail=[]
    excluded={int(original[0]),int(original[1])}
    for v_ in ranked[2:]:
        v=int(v_)
        if v==u or v in excluded: continue
        k=(u<<32)|v
        if k in extra: continue
        exists, when=lookup_key(k,keys,first)
        if mode=='hindsight': eligible=not exists
        else: eligible=(not exists or when>pos)
        if eligible: tail.append(k)
    if not tail:return None
    return int(tail[int(rng.integers(len(tail)))]) if mode=='random' else tail[0]


def evaluate(cap:Capture,X:np.ndarray,num_leaves:int,rank:int,seed:int,
             min_top2_agreement:float=0.98,max_leaf_size:int=2048,
             trace_limit:int=2000) -> tuple[dict,list[dict]]:
    if rank<3:raise RuntimeError('rank must >=3 for replacement tail')
    diff=np.diff(cap.offsets)
    eligible=np.flatnonzero((diff>=6)&(diff%2==0)&((diff//2)<=max_leaf_size))
    if len(eligible)==0: raise RuntimeError('No eligible leaves')
    rng=np.random.default_rng(seed)
    chosen=np.sort(rng.choice(eligible,size=min(num_leaves,len(eligible)),replace=False))
    t=time.perf_counter();print(f'Exact global proposal KEY UNION + first occurrence over {cap.total:,} events...',flush=True)
    unique,first=collect_global_first(cap)
    unique=np.asarray(unique,dtype=np.uint64)
    first=np.asarray(first,dtype=np.int64)
    if len(unique)>cap.total:raise RuntimeError('Impossible uniqueness count')
    print(f'Unique={len(unique):,} duplicates={cap.total-len(unique):,}, elapsed={time.perf_counter()-t:.1f}s',flush=True)
    if cap.n==EXPECTED['n'] and cap.total==EXPECTED['events'] and len(unique)!=24_186_173:
        raise RuntimeError(f'Unexpected unique key count {len(unique)}; H18 reference=24,186,173')
    policies=('nearest','random','hindsight')
    extras={p:set() for p in policies}
    stats={p:{'replacements':0,'novel_full_union_keys':0,'fallback_duplicates':0,'selected_in_later_baseline':0} for p in policies}
    traces=[]
    sampled_events=0;dup_slots=0;matched_rows=0;tested_rows=0;skipped_rows=0
    leaf_stats=[]; s0=time.perf_counter()
    for i,leaf in enumerate(chosen):
        u,dst,positions=extract_leaf(cap,int(leaf))
        ranks,_=local_ranks(X,u,rank)
        agreement=np.all(np.sort(ranks[:,:2],axis=1)==np.sort(dst,axis=1),axis=1)
        matched_rows+=int(np.sum(agreement));tested_rows+=len(u)
        skipped_rows+=int(np.sum(~agreement))
        this_dups=0;this_new={p:0 for p in policies}
        for row in range(len(u)):
            if not agreement[row]: continue # no backfill if recomputed local candidates disagree
            source=int(u[row]);orig=dst[row]
            for slot in range(2):
                position=int(positions[row,slot])
                baseline=(source<<32)|int(orig[slot])
                exists,original_first=lookup_key(baseline,unique,first)
                if not exists or original_first>position:
                    raise RuntimeError('Baseline directed proposal missing/bad first-index')
                if original_first==position:continue # preserve FIRST occurrence of each baseline key
                dup_slots+=1;this_dups+=1
                for p in policies:
                    replacement=choose_tail(ranks[row],orig,source,position,unique,first,extras[p],p,rng)
                    if replacement is None:
                        stats[p]['fallback_duplicates']+=1
                        continue
                    stats[p]['replacements']+=1
                    extras[p].add(replacement)
                    in_baseline,_=lookup_key(replacement,unique,first)
                    if not in_baseline:
                        stats[p]['novel_full_union_keys']+=1
                        this_new[p]+=1
                    else:
                        stats[p]['selected_in_later_baseline']+=1
                    if len(traces)<trace_limit:
                        traces.append({'policy':p,'leaf':int(leaf),'event_position':position,
                                       'src':source,'replaced_dst':int(orig[slot]),
                                       'replacement_dst':int(replacement&0xffffffff),
                                       'new_in_full_baseline_union':not in_baseline})
        sampled_events+=len(u)*2
        leaf_stats.append({'leaf':int(leaf),'size':len(u),'valid_top2_rows':int(agreement.sum()),
                           'duplicate_slots':this_dups,**{f'{p}_new_full_union':this_new[p] for p in policies}})
        if (i+1)%16==0 or i+1==len(chosen):
            print(f'[{i+1}/{len(chosen)}] leaves, {sampled_events:,} events, '
                  f'nearest backfilled={stats["nearest"]["replacements"]:,}, '
                  f'novel={stats["nearest"]["novel_full_union_keys"]:,}',flush=True)
    agree=matched_rows/max(1,tested_rows)
    if agree<min_top2_agreement:
        raise RuntimeError(f'Top-2 agreement {agree:.4%} below {min_top2_agreement:.2%}; '
                           'the reconstruction is not validated; do NOT interpret pilot as oracle')
    out={
        'study':'H25_R0_OFFLINE_PROPOSAL_BACKFILL_DIAGNOSTIC_NOT_GRAPH_BUILDER',
        'provenance':'H18-R1 32-byte header, uint64 leaf offsets, uint64 directed keys (u<<32)|v',
        'input_capture':str(cap.path),'n':cap.n,'leaf_count':cap.nleaves,
        'baseline_proposal_events':cap.total,'baseline_unique_directed_keys':int(len(unique)),
        'baseline_duplicate_fraction':float(1-len(unique)/cap.total),
        'sample_design':{'method':'uniform random over eligible leaves, canonical leaf-ID order',
                         'seed':seed,'sampled_leaf_count':len(chosen),'eligible_leaf_count':len(eligible),
                         'sampled_events':sampled_events,'rank':rank,'max_leaf_size':max_leaf_size,
                         'top2_agreement':agree,'top2_valid_rows':matched_rows,
                         'top2_mismatched_rows_skipped':skipped_rows},
        'duplicate_baseline_slots_in_valid_rows':dup_slots,
        'proposal_event_budget_unchanged_by_construction':True,
        'baseline_unique_directed_key_set_preserved_by_first_occurrence_rule':True,
        'extra_leaf_GEMM_pair_evaluations_in_PROPOSED_builder':0,
        'extra_offline_oracle_computation_not_included_in_BUILD':True,
        'policies':stats,
        'ratios':{p:{'replaceable_duplicate_slot_fraction':stats[p]['replacements']/max(1,dup_slots),
                     'truly_new_key_fraction_of_duplicate_slots':stats[p]['novel_full_union_keys']/max(1,dup_slots),
                     'truly_new_key_fraction_of_sample_events':stats[p]['novel_full_union_keys']/max(1,sampled_events)} for p in policies},
        'per_leaf':leaf_stats,
        'timing':{'backfill_phase_wall_seconds':round(time.perf_counter()-s0,3),
                  'NOTE':'time measured in Python offline diagnostic; NOT PiPNN BUILD wall'},
        'NOT_MEASURED':['post-HashPrune survival','final graph degree/index bytes',
                        'final graph Recall/QPS','production grouping/synchronization overhead',
                        'end-to-end BUILD','peak memory at 1B','algorithm novelty'],
        'interpretation':'Only structural feasibility. Even positive novelty of proposal keys DOES NOT establish Recall or Pareto gains.'}
    return out,traces


def output_report(outdir:Path,report:dict,traces:list[dict],overwrite:bool):
    if outdir.exists() and any(outdir.iterdir()) and not overwrite:
        raise RuntimeError(f'Output already exists/nonempty: {outdir}; choose --out or --force')
    outdir.mkdir(parents=True,exist_ok=True)
    (outdir/'report.json').write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    with (outdir/'replacements_sample.csv').open('w',newline='',encoding='utf-8') as f:
        if traces:
            w=csv.DictWriter(f,fieldnames=list(traces[0]));w.writeheader();w.writerows(traces)
    print(f'SAVED {outdir/"report.json"}')


def make_synthetic_capture(root:Path):
    # Three overlapping leaves. Sources 0/1 appear in all, creating duplicate proposals.
    pts=np.array([[0.,0.],[1.,0.],[2.,0.],[3.,0.],[4.,0.],[5.,0.],[6.,0.],[7.,0.]],dtype='<f4')
    fb=root/'base.fbin'
    with fb.open('wb') as f: f.write(struct.pack('<II',len(pts),pts.shape[1]));f.write(pts.tobytes())
    leaves=[[0,1,2,3,4],[0,1,2,4,5],[0,1,2,5,6]]
    events=[];off=[0]
    for ids in leaves:
        for pos,u in enumerate(ids):
            d=np.sum((pts[ids]-pts[u])**2,axis=1)
            order=sorted((float(d[j]),j) for j in range(len(ids)) if j!=pos)
            for _,local in order[:2]:events.append((u<<32)|ids[local])
        off.append(len(events))
    cp=root/'capture.bin'
    with cp.open('wb') as f:
        f.write(struct.pack('<8sQQQ',MAGIC,len(pts),len(leaves),len(events)))
        f.write(np.array(off,dtype='<u8').tobytes())
        f.write(np.array(events,dtype='<u8').tobytes())
    return cp,fb


def selftest():
    with tempfile.TemporaryDirectory(prefix='h25_r0_') as td:
        root=Path(td)
        cp,fb=make_synthetic_capture(root)
        cap=read_capture(cp,allow_other_shape=True)
        x,d=read_fbin(fb,cap.n)
        assert cap.n==8 and cap.nleaves==3 and d==2
        report,_=evaluate(cap,x,num_leaves=3,rank=4,seed=42,min_top2_agreement=1.0)
        assert report['sample_design']['top2_agreement']==1
        assert report['duplicate_baseline_slots_in_valid_rows']>0
        assert report['policies']['nearest']['replacements']>0
        baseline=np.asarray(cap.events,dtype=np.uint64).copy()
        baseline_union=set(map(int,baseline))
        # ACTUALLY replay every policy's synthetic trace; do not trust a hard-coded boolean.
        report2,traces=evaluate(cap,x,num_leaves=3,rank=4,seed=42,
                                min_top2_agreement=1.0,trace_limit=10000)
        for p in ('nearest','random','hindsight'):
            rewritten=baseline.copy()
            chosen=[t for t in traces if t['policy']==p]
            assert len(chosen)==report2['policies'][p]['replacements']
            for t in chosen:
                rewritten[t['event_position']]=np.uint64((t['src']<<32)|t['replacement_dst'])
            output_union=set(map(int,rewritten))
            assert len(rewritten)==len(baseline), 'Event count changed'
            assert baseline_union.issubset(output_union),'Lost one original unique directed key'
            assert len(output_union-baseline_union)==report2['policies'][p]['novel_full_union_keys']
            assert all((int(z)>>32)!=(int(z)&0xffffffff) for z in rewritten),'Self edge introduced'
        print('SELFTEST PASS: header, provenance, actual Top2 match, candidate backfill, replay, union preservation, exact event budget')
        print('Synthetic rates (NOT real SIFT1M):',json.dumps(report['ratios'],indent=2))


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--mode',choices=['selftest','plan','run'],required=True)
    ap.add_argument('--phase',default='pilot',choices=['pilot'])
    ap.add_argument('--capture',type=Path,default=DEFAULT_CAPTURE)
    ap.add_argument('--base',type=Path,default=DEFAULT_BASE)
    ap.add_argument('--out',type=Path,default=DEFAULT_OUT)
    ap.add_argument('--sample-leaves',type=int,default=64)
    ap.add_argument('--rank',type=int,default=4,help='local TopR, e.g. 4 or 8')
    ap.add_argument('--seed',type=int,default=42)
    ap.add_argument('--max-leaf-size',type=int,default=2048)
    ap.add_argument('--min-top2-agreement',type=float,default=0.98)
    ap.add_argument('--skip-sha',action='store_true',help='unsafe for claims; only to inspect modified capture')
    ap.add_argument('--force',action='store_true',help='overwrite ONLY H25 output files')
    a=ap.parse_args()
    if a.mode=='selftest':selftest();return
    cap=read_capture(a.capture)
    x,dim=read_fbin(a.base,cap.n)
    digest='SKIPPED'
    if not a.skip_sha:
        print('Checking input SHA256...',flush=True)
        digest=sha256(cap.path)
        if digest!=EXPECTED_SHA:
            raise RuntimeError('H18-R1 capture SHA mismatch: '+digest+' != '+EXPECTED_SHA+'; abort to avoid mixing runs')
    print('Input:',json.dumps({'capture':str(cap.path),'sha256':digest,'base':str(a.base),
                               'n':cap.n,'d':dim,'leaves':cap.nleaves,'events':cap.total,
                               'MemAvailableGiB':available_gib()},indent=2))
    if a.mode=='plan':
        eligible=np.diff(cap.offsets)
        print('PLAN ONLY, no capture or graph modifications.')
        print('Eligible leaf count (size>=3, <= max size):',int(np.sum((eligible>=6)&(eligible%2==0)&((eligible//2)<=a.max_leaf_size))))
        print('Expected sample:',a.sample_leaves,'leafs, rank',a.rank,'(chosen deterministically by seed)')
        print('Output:',a.out)
        return
    if a.sample_leaves<=0 or a.sample_leaves>1024:raise RuntimeError('sample leaves must be 1..1024')
    if a.rank<3 or a.rank>32:raise RuntimeError('rank must be in [3,32]')
    if (available_gib() is not None) and available_gib()<5.0:
        raise RuntimeError('MemAvailable <5 GiB; np.unique(return_index) could cause swap/OOM; close other apps')
    report,traces=evaluate(cap,x,a.sample_leaves,a.rank,a.seed,a.min_top2_agreement,a.max_leaf_size)
    report['sha256_capture']=digest
    report['input_base']=str(a.base)
    report['parameter_skip_sha']=a.skip_sha
    output_report(a.out,report,traces,a.force)
    print('VERDICT: structural diagnostic only; NEVER equate extra unique proposal keys with graph Recall or Pareto.')

if __name__=='__main__':
    try:main()
    except (RuntimeError,ValueError,AssertionError,MemoryError) as e:
        print('FAIL CLOSED:',e,file=sys.stderr);sys.exit(2)
