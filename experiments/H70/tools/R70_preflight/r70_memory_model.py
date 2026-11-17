#!/usr/bin/env python3
"""Counterfactual nominal reservoir allocation only; never actual process RSS."""
import argparse, json
p=argparse.ArgumentParser();p.add_argument('--nodes',type=int,default=1000000);p.add_argument('--cap',type=int,default=160);p.add_argument('--base',type=int,default=64);p.add_argument('--promoted',type=int,default=45804);p.add_argument('--slot-bytes',type=int,default=8);p.add_argument('--ptr-bytes',type=int,default=8);a=p.parse_args()
assert a.nodes>0 and 0<=a.promoted<=a.nodes and a.cap>a.base>=1
flat=a.nodes*(a.cap+1)*a.slot_bytes
small=a.nodes*(a.base+1)*a.slot_bytes
expanded=a.promoted*(a.cap+1)*a.slot_bytes
pointers=a.nodes*a.ptr_bytes
tier=small+expanded+pointers
print(json.dumps({'kind':'NOMINAL_ALLOCATION_MODEL_NOT_RSS','nodes':a.nodes,'cap':a.cap,'base':a.base,'promoted':a.promoted,'flat_bytes':flat,'small_bytes':small,'promoted_bytes':expanded,'pointer_bytes':pointers,'tier_bytes':tier,'nominal_saved_bytes':flat-tier,'nominal_saved_MiB':round((flat-tier)/2**20,3),'nominal_saved_percent':round(100*(flat-tier)/flat,3),'limitations':['allocator overhead, page residency, fragmentation, slab reserves, vector buffers, graph, peak overlap not modeled','promoted count is from R60 snapshot, not proven for any modified concurrency schedule']},ensure_ascii=False,indent=2))
