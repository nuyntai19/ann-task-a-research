#!/usr/bin/env python3
"""Verify R86 ON counters against source-branch invariants and independent leaf dump.

This is a logical counter audit, not search-quality or timing validation.
Usage: python3 tests/verify_event_stream.py --events counters.jsonl --leaves sizes.jsonl \
       --occupancy occupancy.json [--build-log build.log] [--top2 stock|h17]
"""
import argparse, collections, json, re, sys
from pathlib import Path

p=argparse.ArgumentParser()
p.add_argument('--events',type=Path,required=True)
p.add_argument('--leaves',type=Path,required=True)
p.add_argument('--occupancy',type=Path,required=True)
p.add_argument('--build-log',type=Path)
p.add_argument('--top2',choices=['stock','h17'])
a=p.parse_args()

def load_jsonl(path):
 return [json.loads(x) for x in path.read_text().splitlines() if x.strip()]

records=load_jsonl(a.events)
leaves=load_jsonl(a.leaves)
c=collections.defaultdict(dict)
for e in records:
 key=(e['pass_id'],e.get('depth'),e['metric_code'])
 if key[2] in c[(key[0],key[1])]:
  raise SystemExit('FAIL duplicate counter row '+str(key))
 c[(key[0],key[1])][key[2]]=e['observed']
passids=sorted(set(x['pass_id'] for x in records if x['pass_id']>0))
errors=[];passes=[]
def check(tag,pred):
 (passes if pred else errors).append(tag)

leafsum=collections.defaultdict(lambda:collections.Counter())
for x in leaves:
 ps=x['pass_id'];size=x['size'];dep=x.get('depth')
 check(f'leaf depth null P{ps}',dep is None)
 check(f'leaf size>=2 P{ps}',size>=2)
 leafsum[ps].update({'leaf_count':1,'leaf_size_sum':size,'W_L':size*size,'W_pairs':size*(size-1)//2})

required=['merge_attempts','proposals','hash_early_break','collision_same_id',
 'collision_diff_id','hash_insert_not_full','hash_replace_full','hash_accept',
 'hash_reject','hash_diff_collision_rewrite','hash_diff_collision_reject',
 'hash_replace','hash_same_id_rewrite','hash_compute','hash_moves',
 'hash_lb_compares','hash_worst_scan','hash_worst_compares','top2_q_writes',
 'partial_sort_calls','hash_slot_writes']
for ps in passids:
 d=c[(ps,None)]
 for name in required:
  check(f'P{ps} measured {name}',name in d)
 if any(k not in d for k in required): continue
 g=lambda x:d[x]
 check(f'P{ps} merge=2*proposals',g('merge_attempts')==2*g('proposals'))
 check(f'P{ps} branch partition',g('merge_attempts')==g('hash_early_break')+g('collision_same_id')+g('collision_diff_id')+g('hash_insert_not_full')+g('hash_replace_full'))
 check(f'P{ps} mutually-exclusive outcomes',g('merge_attempts')==g('hash_accept')+g('hash_reject')+g('collision_same_id'))
 check(f'P{ps} diff-id decisions',g('collision_diff_id')==g('hash_diff_collision_rewrite')+g('hash_diff_collision_reject'))
 check(f'P{ps} accepted decomposition',g('hash_accept')==g('hash_insert_not_full')+g('hash_replace_full')+g('hash_diff_collision_rewrite'))
 check(f'P{ps} rejected decomposition',g('hash_reject')==g('hash_early_break')+g('hash_diff_collision_reject'))
 check(f'P{ps} replaced decomposition',g('hash_replace')==g('hash_replace_full')+g('hash_diff_collision_rewrite'))
 check(f'P{ps} same-id rewritten subset',g('hash_same_id_rewrite')<=g('collision_same_id'))
 check(f'P{ps} relative_hash calls',g('hash_compute')==g('merge_attempts')-g('hash_early_break'))
 for k in ['leaf_count','leaf_size_sum','W_L','W_pairs']:
  check(f'P{ps} independently audited {k}', d.get(k)==leafsum[ps][k])
 if a.top2=='stock':
  check(f'P{ps} stock Q writes',d['top2_q_writes']==sum(x['size']*(x['size']-1) for x in leaves if x['pass_id']==ps))
  check(f'P{ps} stock partial sort calls',d['partial_sort_calls']==leafsum[ps]['leaf_size_sum'])
 elif a.top2=='h17':
  check(f'P{ps} h17 q writes',d['top2_q_writes']==0)
  check(f'P{ps} h17 partialsort calls',d['partial_sort_calls']==0)

if a.build_log:
 text=a.build_log.read_text(errors='replace')
 cmps=list(map(int,re.findall(r'# of comparisons during clustering:\s*(\d+)',text)))
 totalpoints=list(map(int,re.findall(r'Total points:\s*(\d+)',text)))
 if len(cmps)!=len(passids):errors.append('legacy clustering comparison line count mismatch')
 else:
  previous=0
  for ps,current in zip(passids,cmps):
   wp=sum(x['observed'] for x in records if x['pass_id']==ps and x['metric_code']=='W_P' and x['depth'] is not None)
   check(f'P{ps} W_P matches source COMPARISONS increment',wp==current-previous)
   previous=current
 if len(totalpoints)==len(passids):
  for ps,tp in zip(passids,totalpoints):
   check(f'P{ps} executed leaf membership<=all bucket membership',leafsum[ps]['leaf_size_sum']<=tp)

occ=json.loads(a.occupancy.read_text())
if isinstance(occ.get('histogram'),dict):
 hist={int(k):int(v) for k,v in occ['histogram'].items()}
 check('occupancy histogram node count',sum(hist.values())==occ['n'])
 check('occupancy histogram occupied slots',sum(k*v for k,v in hist.items())==occ['occupied_slots'])
 check('occupancy histogram full count',hist.get(occ['capacity'])==occ['full_nodes'])
else:errors.append('missing occupancy histogram')
for msg in errors: print('FAIL',msg)
print('R86_v1_1_NATIVE_COUNTER_GATE_'+('FAIL' if errors else 'PASS'),f'checks={len(passes)+len(errors)} pass={len(passes)} fail={len(errors)}')
sys.exit(bool(errors))
