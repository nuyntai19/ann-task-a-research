#!/usr/bin/env python3
"""H25-R1: reproducibly generate sampled per-leaf plans for native PiPNN source hook.

The interventions depend on H18 full-capture hindsight first occurrence. This is
an OFFLINE INTERVENTION, NOT a feasible online concurrent backfill algorithm.
"""
from __future__ import annotations
import argparse, hashlib, json, struct, sys, time
from pathlib import Path
import numpy as np
import h25_r0_backfill_gate as r0

ROW_MAGIC=b'H25R1C01'
PATCH_MAGIC=b'H25R1P01'
HDR='<8sQQQ'
RECORD='<IIII'
DEFAULT_OUT=Path.home()/'ann-task-a/experiments/H25/r1_graph_gate_sift1m_seed42'

def write_bin(path, magic, n, leaves, data):
    with path.open('wb') as f:
        f.write(struct.pack(HDR,magic,len(data),n,leaves))
        for rec in data:f.write(struct.pack(RECORD,*rec))

def hash_file(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda:f.read(2**20),b''):h.update(b)
    return h.hexdigest()

def generate(cap, base, out, sample, rank, seed, force=False, check_sha=True):
    if out.exists() and any(out.iterdir()) and not force:
        raise RuntimeError(f'Output nonempty {out}; use another path or --force')
    if check_sha:
        digest=r0.sha256(cap.path)
        if digest!=r0.EXPECTED_SHA:
            raise RuntimeError('Input H18 SHA mismatch: '+digest)
    else:digest='SKIPPED'
    if cap.n >= 100_000 and r0.available_gib() is not None and r0.available_gib()<5:
        raise RuntimeError('MemAvailable < 5GiB; abort before global np.unique')
    X,dim=r0.read_fbin(base,cap.n)
    result,traces=r0.evaluate(cap,X,sample,rank,seed,min_top2_agreement=1.0,trace_limit=10_000_000)
    if result['sample_design']['top2_agreement']!=1.0 or result['sample_design']['top2_mismatched_rows_skipped']:
        raise RuntimeError('Top2 must match capture exactly for safe intervention')
    policy_names=('nearest','random','hindsight')
    patches={p:[] for p in policy_names}
    for t in traces:
        p=t['policy']
        patches[p].append((int(t['leaf']),int(t['src']),int(t['replaced_dst']),int(t['replacement_dst'])))
    for p in policy_names:
        arr=patches[p]
        if len(arr)!=result['policies'][p]['replacements']:
            raise RuntimeError(f'{p} trace loss {len(arr)} vs report {result["policies"][p]["replacements"]}')
        if len({tuple(x[:3]) for x in arr})!=len(arr):
            raise RuntimeError(f'{p}: duplicate (leaf,src,old) patch keys')
    rows=[]
    for s in result['per_leaf']:
        leaf=int(s['leaf'])
        ids,dst,_=r0.extract_leaf(cap,leaf)
        for u,(v0,v1) in zip(ids,dst):
            rows.append((leaf,int(u),int(v0),int(v1)))
    if len(rows)!=result['sample_design']['top2_valid_rows']:
        raise RuntimeError('Control row count mismatch')
    if len({(x[0],x[1]) for x in rows})!=len(rows):raise RuntimeError('Duplicate (leaf,src) row')
    out.mkdir(parents=True,exist_ok=True)
    write_bin(out/'expected_rows.bin',ROW_MAGIC,cap.n,cap.nleaves,rows)
    write_bin(out/'patch_baseline.bin',PATCH_MAGIC,cap.n,cap.nleaves,[])
    for p in policy_names:write_bin(out/f'patch_{p}.bin',PATCH_MAGIC,cap.n,cap.nleaves,patches[p])
    # Report is diagnostic; actual PiPNN native BUILD and SEARCH have not run.
    manifest={'study':'H25_R1_NATIVE_PIPELINE_INTERVENTION_PLAN_NOT_RESULTS',
      'warning':'OFFLINE hindsight plan from H18 first occurrences; no online collision detector, no BUILD/speedup claim.',
      'capture':str(cap.path),'capture_sha256':digest,'base':str(base),'d':dim,
      'same_capture_and_sample_as_R0b':{'sample':sample,'rank':rank,'seed':seed},
      'expected_rows':len(rows),'patch_counts':{p:len(v) for p,v in patches.items()},
      'r0b_summary':{p:result['policies'][p] for p in policy_names},
      'sha256_files':{p.name:hash_file(p) for p in sorted(out.glob('*.bin'))},
      'not_measured':['native replay equality','HashPrune survival','final RobustPrune effect','Recall/QPS','BUILD time','algorithm novelty']}
    (out/'plan.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    print('PLAN_CREATED',json.dumps({k:manifest[k] for k in ('expected_rows','patch_counts','sha256_files')},indent=2))
    print('NO-GO unless selected native leaf rows match all expected H18 rows; never mix graphs.')
    return manifest

def selftest():
    from tempfile import TemporaryDirectory
    with TemporaryDirectory(prefix='h25r1_') as td:
        root=Path(td)
        cap_path,fb=r0.make_synthetic_capture(root)
        cap=r0.read_capture(cap_path,allow_other_shape=True)
        plan=generate(cap,fb,root/'out',3,4,42,check_sha=False)
        assert plan['expected_rows']>0
        for name in ['expected_rows.bin','patch_baseline.bin','patch_nearest.bin','patch_random.bin','patch_hindsight.bin']:
            p=root/'out'/name
            with p.open('rb') as f:mg,n,nu,nl=struct.unpack(HDR,f.read(32))
            assert p.stat().st_size==32+16*n
            assert nu==8 and nl==3
            if name=='expected_rows.bin':assert mg==ROW_MAGIC
            else:assert mg==PATCH_MAGIC
        print('SELFTEST PASS: synthetic sample, exact Top2, patch/row record formats, counts, header/size/SHA')

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--mode',choices=['selftest','plan'],required=True)
    ap.add_argument('--capture',type=Path,default=r0.DEFAULT_CAPTURE)
    ap.add_argument('--base',type=Path,default=r0.DEFAULT_BASE)
    ap.add_argument('--out',type=Path,default=DEFAULT_OUT)
    ap.add_argument('--sample-leaves',type=int,default=64)
    ap.add_argument('--rank',type=int,default=8)
    ap.add_argument('--seed',type=int,default=42)
    ap.add_argument('--skip-sha',action='store_true')
    ap.add_argument('--force',action='store_true')
    a=ap.parse_args()
    if a.mode=='selftest':selftest();return
    if a.rank!=8 or a.sample_leaves!=64 or a.seed!=42:
        raise RuntimeError('R1 is frozen to verified R0b Top8/64/seed42; other settings require new paired control design')
    cap=r0.read_capture(a.capture)
    generate(cap,a.base,a.out,a.sample_leaves,a.rank,a.seed,a.force,not a.skip_sha)
if __name__=='__main__':
    try:main()
    except Exception as e:
        print('FAIL CLOSED:',e,file=sys.stderr);sys.exit(2)
