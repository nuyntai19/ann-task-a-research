from pathlib import Path
import re, subprocess, json, os, textwrap, tempfile, shutil
ROOT=Path(__file__).resolve().parent.parent
W=Path(tempfile.mkdtemp(prefix='r86_v11_test_'))
(W/'smoke').mkdir(exist_ok=True)
method=(ROOT/'tests/fixtures/merge_neighbors.inc').read_text()
# Ensure exact source is included with no modifications.
code=r'''#include <algorithm>
#include <array>
#include <cassert>
#include <cmath>
#include <cstdint>
#include <iostream>
#include <mutex>
#include <utility>
#include <vector>
#include "r86_counters.hpp"
namespace Eigen {
struct bfloat16 {
 float v;
 bfloat16(float f=0):v(std::round(f*16)/16){}
 operator float() const {return v;}
};
}
struct Mutex {
 std::mutex m;
 void Lock(){m.lock();}
 void Unlock(){m.unlock();}
};
struct FakeHash {
 unsigned relative_hash(size_t i,unsigned pid) const {return (pid*17u + i) % 13;}
};
struct Candidate {unsigned point_id;Eigen::bfloat16 norm;uint16_t hash;};
struct Graph {
 using indexType=uint32_t;
 using distanceType=float;
 using T=Candidate;
 size_t kMaxDegree=6;
 size_t n=1;
 FakeHash H;
 Mutex locks[1];
 T tables[7]{};
 Graph(){tables[0].point_id=0;tables[0].hash=0;tables[0].norm=Eigen::bfloat16(0);}
 size_t degree(size_t) {return tables[0].point_id;}
'''+method+r'''
 void ingest(unsigned pid,float dist){
   std::array<std::pair<uint32_t,float>,1> a{{{pid,dist}}};
   merge_neighbors(0,a);
 }
 void show(){
  size_t count=tables[0].point_id;
  std::cout<<count;
  for(size_t i=0;i<count;++i)
   std::cout<<' '<<tables[i+1].point_id<<':'<<tables[i+1].hash<<':'<<float(tables[i+1].norm);
  std::cout<<'\n';
 }
};
int main(){
  r86::begin_pass(1);
  Graph g;
  for(unsigned i=0;i<300;++i){
    unsigned pid=(i*7u+3u)%53u;
    float dist=float((i*31u)%157u)/13.0f;
    g.ingest(pid,dist);
  }
  g.show();
  Graph special;
  special.ingest(14,1.49f);
  special.ingest(14,1.45f); // bf16 rounded old>float new, same-ID rewrite
  special.ingest(1,0.50f);  // different-ID hash collision, replacement
  special.ingest(1,0.45f);  // another same-ID rewrite
  special.ingest(27,1.0f); // different-ID collision rejection
  special.show();
  r86::emit_reservoir_occupancy(special,1,1); // P1 snapshot
  r86::emit_reservoir_occupancy(special,1,0); // pre-prune final snapshot
#if defined(R86_COUNTERS) && R86_COUNTERS
  struct NotReservoir { };
  try { NotReservoir v; r86::emit_reservoir_occupancy(v,1,1); assert(false); }
  catch(const std::runtime_error& e) { std::cout<<"R86_EXPECTED_MISSING_CAPACITY_FAILURE\n"; }
#endif
  r86::dump_jsonl_from_env();
}
'''
(W/'smoke/merger.cpp').write_text(code)
for mode in [0,1]:
 p=W/f'smoke/merger_{mode}'
 subprocess.run(['g++','-std=c++17','-O2',f'-DR86_COUNTERS={mode}','-I',str(ROOT/'cpp'),str(W/'smoke/merger.cpp'),'-o',str(p)],check=True)
 env=os.environ.copy();env['R86_COUNTER_OUT']=str(W/f'smoke/hash_{mode}.jsonl');env['R86_LEAF_SIZE_OUT']=str(W/f'smoke/hash_{mode}.leaves');env['R86_OCCUPANCY_OUT']=str(W/f'smoke/occupancy_{mode}.json'); env['R86_DEGREES_PREFIX']=str(W/f'smoke/degrees_{mode}')
 r=subprocess.run([str(p)],env=env,capture_output=True,text=True,check=True)
 print('MODE',mode,'graph:',r.stdout.strip())
 if mode==0:out0=r.stdout
 else:out1=r.stdout
assert out0.replace('R86_EXPECTED_MISSING_CAPACITY_FAILURE\n','') == out1.replace('R86_EXPECTED_MISSING_CAPACITY_FAILURE\n',''), 'ON/OFF graph state differs!'
assert 'R86_EXPECTED_MISSING_CAPACITY_FAILURE' in out1
events=[json.loads(x) for x in (W/'smoke/hash_1.jsonl').read_text().splitlines()]
d={x['metric_code']:x['observed'] for x in events if x['pass_id']==1 and x['depth'] is None}
print(json.dumps({k:v for k,v in d.items() if k.startswith('hash') or k.startswith('collision') or k=='merge_attempts'},indent=2))
assert d['merge_attempts'] == d['hash_early_break']+d['collision_same_id']+d['collision_diff_id']+d['hash_insert_not_full']+d['hash_replace_full']
assert d['merge_attempts'] == d['hash_accept']+d['hash_reject']+d['collision_same_id']
assert d['collision_diff_id'] == d['hash_diff_collision_rewrite']+d['hash_diff_collision_reject']
assert d['hash_accept'] == d['hash_insert_not_full']+d['hash_replace_full']+d['hash_diff_collision_rewrite']
assert d['hash_reject'] == d['hash_early_break']+d['hash_diff_collision_reject']
assert d['hash_replace'] == d['hash_replace_full']+d['hash_diff_collision_rewrite']
assert d['hash_same_id_rewrite'] <= d['collision_same_id']
assert d['hash_compute'] == d['merge_attempts']-d['hash_early_break']
assert d['hash_lb_compares']>=d['hash_compute']-2
assert d['hash_same_id_rewrite']>0
assert d['hash_diff_collision_rewrite']>0
print('R86_v1_2_SYNTHETIC_MERGE_PARITY_AND_INVARIANTS_PASS')

snaps=[json.loads(x) for x in (W/'smoke/occupancy_1.json').read_text().splitlines()]
assert [x['pass_id'] for x in snaps]==[1,0]
assert [x['stage'] for x in snaps]==['after_pass','pre_prune']
assert (W/'smoke/degrees_1_pass1.u32le').read_bytes()==(1).to_bytes(4,'little')
assert not (W/'smoke/degrees_1_pass0.u32le').exists()
occ=snaps[-1]
assert occ['n']==1 and occ['capacity']==6 and occ['occupied_slots']==1
assert sum(occ['histogram'].values())==1
print('R86_v1_2_SYNTHETIC_OCCUPANCY_PASS')
shutil.rmtree(W)
