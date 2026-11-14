#!/usr/bin/env python3
"""Observe final directed-edge presence for H25 planned interventions.
IMPORTANT: Presence in final graph does not prove edge arose ONLY from that injected proposal.
"""
from __future__ import annotations
import argparse,struct,sys,json
from pathlib import Path
import numpy as np

def load_graph(p):
    if not p.is_file():raise RuntimeError('Missing graph '+str(p))
    with p.open('rb') as f: h=f.read(8)
    if len(h)!=8:raise RuntimeError('Graph too short')
    n,maxdeg=struct.unpack('<II',h)
    if n<1 or n>1_000_000_000 or maxdeg<1 or maxdeg>10000:raise RuntimeError('Invalid header')
    degrees=np.memmap(p,dtype='<u4',mode='r',offset=8,shape=(n,))
    if np.any(degrees>maxdeg):raise RuntimeError('Degree cap exceeded')
    offset=np.empty(n+1,dtype=np.int64);offset[0]=0
    np.cumsum(degrees,out=offset[1:])
    if p.stat().st_size!=8+4*n+4*int(offset[-1]):raise RuntimeError('Graph size inconsistent')
    dest=np.memmap(p,dtype='<u4',mode='r',offset=8+4*n,shape=(int(offset[-1]),))
    return n,maxdeg,offset,dest

def load_patch(path):
    with path.open('rb') as f: h=f.read(32)
    magic,n,npts,leaves=struct.unpack('<8sQQQ',h)
    if magic!=b'H25R1P01':raise RuntimeError('Bad patch header')
    if path.stat().st_size!=32+16*n:raise RuntimeError('patch size mismatch')
    rec=np.memmap(path,dtype='<u4',mode='r',offset=32,shape=(n,4))
    return rec,int(npts)

def contains(off,ids,u,v):
    return bool(np.any(ids[off[u]:off[u+1]]==v))

def main():
    a=argparse.ArgumentParser();a.add_argument('--runs',type=Path,required=True);a.add_argument('--plan',type=Path,required=True);a.add_argument('--out',type=Path,required=True);x=a.parse_args()
    if x.out.exists():raise RuntimeError('refuse overwrite '+str(x.out))
    graphs={p:load_graph(x.runs/f'{p}.graph') for p in ('baseline','nearest','random')}
    b_n=graphs['baseline'][0]
    if any(g[0]!=b_n for g in graphs.values()):raise RuntimeError('graph vertex counts mismatch')
    output={}
    for policy in ('nearest','random'):
        patch,n=load_patch(x.plan/f'patch_{policy}.bin')
        if n!=b_n:raise RuntimeError('patch vs graph n mismatch')
        offb,idb=graphs['baseline'][2:];offv,idv=graphs[policy][2:]
        stats={'patched_events':len(patch),'replacement_endpoint_present_in_native_baseline':0,
               'replacement_endpoint_present_in_variant_final':0,
               'replacement_endpoint_absent_baseline_present_variant':0,
               'original_endpoint_present_in_baseline':0,
               'original_endpoint_present_in_variant':0,
               'removed_original_endpoint_baseline_to_variant':0,
               'note':'Edge membership in final graph is an association, not proof of survival of the injected proposal: other leaves/reverse merges may also contribute.'}
        for leaf,u,old,new in patch:
            u,old,new=int(u),int(old),int(new)
            bnew=contains(offb,idb,u,new);vnew=contains(offv,idv,u,new)
            bold=contains(offb,idb,u,old);vold=contains(offv,idv,u,old)
            stats['replacement_endpoint_present_in_native_baseline']+=bnew
            stats['replacement_endpoint_present_in_variant_final']+=vnew
            stats['replacement_endpoint_absent_baseline_present_variant']+=(not bnew and vnew)
            stats['original_endpoint_present_in_baseline']+=bold
            stats['original_endpoint_present_in_variant']+=vold
            stats['removed_original_endpoint_baseline_to_variant']+=(bold and not vold)
        output[policy]=stats
    x.out.write_text(json.dumps({'study':'H25_R1_FINAL_GRAPH_PATCH_EDGE_PRESENCE',
      'limitations':'Not a HashPrune decision trace; baseline and variant can differ because of concurrent merge nondeterminism; native paired repeats needed.',
      'policies':output},ensure_ascii=False,indent=2)+'\n')
    print('EDGE_SURVIVAL_DIAGNOSTIC_WRITTEN',x.out)
    for p,st in output.items():
        print(p,st['replacement_endpoint_absent_baseline_present_variant'],'new final directed endpoint(s) among planned patches; no causal attribution')
if __name__=='__main__':
    try:main()
    except Exception as e:print('FAIL CLOSED:',e,file=sys.stderr);sys.exit(2)
