#!/usr/bin/env python3
"""Read-only P0A v1.1 SIFT10K pilot failure audit.

Does not modify any existing P0A source, ELF, graph, stdout or manifest.
Does not run BUILD/Search and does not attempt to waive graph-parity gates.
Native receipts are SHA validated against the P0A compile/pilot manifests.

Evidence boundaries:
* Detects graph differences and source-level FTZ/DAZ risk conditions.
* Does NOT claim direct proof of Highway SIMD bit loss or sorting random seeds.
* Adjacency order versus geometric L2 is DIAGNOSTIC, not a graph invariant.
"""
from __future__ import annotations
import argparse
import array
import csv
import hashlib
import importlib.util
import json
import os
import re
import struct
import sys
import tempfile
import time
from functools import lru_cache
from pathlib import Path

HOME=Path.home()
ROOT=HOME/'ann-task-a/experiments/R90/r90_p0a_unified_1m_three_arm_v1_1'
SCRIPT_V11=HOME/'Downloads/r90_p0a_unified_1m_three_arm_v1_1.py'
OUTPUT=HOME/'ann-task-a/experiments/R90/r90_p0a_v11_pilot_hold_diagnostic_v1'
SOURCE_SHA='fa9cdc09b3f447161f5c1f65382b15a0bc9645f425a679b73ca26f5ce8abecf0'
SOURCE_MANIFEST_SHA='6e5d82c4ca331476240950afedfad970d8358fc7252d0d2b8b9ac441e1afb298'
COMPILER_SHA='1353e9bdd29a7295c7226bf6c63abccce056d8cac31f112e5cdbecc3f28c2769'
EXPECTED_GRAPH={
 'stock_off':'ff5de5d2a741fc3a669bbd7d23494abef2acb77c10c1c92b72962eca35e463c4',
 'h17_off':'a49557be4fb15ac43b8fd4ca729c8d2e5fcf228a6c5880864748288c1b6632e8',
 'fast_off':'7fe09244afa40e7e25aa8c5dd062b09858c092b79119aa03ef357973efbc0d16',
 'stock_on':'ff5de5d2a741fc3a669bbd7d23494abef2acb77c10c1c92b72962eca35e463c4',
 'h17_on':'7fe09244afa40e7e25aa8c5dd062b09858c092b79119aa03ef357973efbc0d16',
 'fast_on':'7fe09244afa40e7e25aa8c5dd062b09858c092b79119aa03ef357973efbc0d16',
}
EXPECTED_BIN={
 'stock_off':'0b4e27255d9dd21bf9346fab16894b0e3e876d3b56bbc2a9da70e825f7f3ac02',
 'stock_on':'846d387525c372428d82fd994e526e8639f1a90e235d94f1f8e5f85ea3f67b1b',
 'h17_off':'63a7550992ba30ce2a89effd98b738a620727ff12de13f89ad024ea2e95b7636',
 'h17_on':'8bb92dbf9a63b3924f7ba395c889446fc5421ce25535971317cdba240a273cfc',
 'fast_off':'61bce9705348b2b3cb7d2c7c5ed7c9a0684cddb29d58ed214dc0a7def56157ed',
 'fast_on':'77cfe433775d7d7443c074025fa5131e08122862f191c0c75ed59507d94ddb30',
}
VARIANTS=tuple(EXPECTED_GRAPH)
TEST_VERTICES=(2,15,746,2887)


def guard(ok,label):
 if not ok:raise RuntimeError('R90_P0A_DIAGNOSTIC_HOLD_'+label)

def sha(path:Path):
 d=hashlib.sha256()
 with path.open('rb') as f:
  for block in iter(lambda:f.read(4*1024*1024),b''):d.update(block)
 return d.hexdigest()

def require_file(path,label):
 path=Path(path)
 guard(path.is_file() and not path.is_symlink(),label+'_FILE_MISSING_OR_SYMLINK')
 return path

def readjson(path):return json.loads(require_file(path,'JSON').read_text())

def graph_from_bytes(blob, expected_n=None):
 guard(sys.byteorder=='little','HOST_ENDIAN')
 guard(len(blob)>=8,'GRAPH_TOO_SHORT')
 n,md=struct.unpack_from('<II',blob,0)
 guard(0<n<=100000 and 0<md<=4096,'GRAPH_HEADER_RANGE')
 if expected_n is not None:guard(n==expected_n,'GRAPH_N_MISMATCH')
 guard(len(blob)>=8+4*n,'GRAPH_TRUNCATED_DEGREES')
 deg=array.array('I');deg.frombytes(blob[8:8+4*n]); guard(all(x<=md for x in deg),'GRAPH_DEGREE_GT_MAX')
 edges=sum(deg);guard(len(blob)==8+4*n+4*edges,'GRAPH_SIZE_MISMATCH')
 ids=array.array('I');ids.frombytes(blob[8+4*n:])
 offsets=[0];off=0
 for d in deg:off+=d;offsets.append(off)
 return {'n':n,'max_deg':md,'degree':deg,'edges':ids,'offsets':offsets,'arcs':edges}

def graph(path):return graph_from_bytes(require_file(path,'GRAPH').read_bytes(),10000)

def base_fbin(path):
 import mmap
 f=require_file(path,'BASE').open('rb')
 size=f.seek(0,2);f.seek(0)
 guard(size>=8,'BASE_TOO_SHORT');n,dim=struct.unpack('<II',f.read(8))
 guard(n==10000 and dim==128 and size==8+n*dim*4,'BASE_10K_HEADER_SIZE')
 mm=mmap.mmap(f.fileno(),0,access=mmap.ACCESS_READ)
 @lru_cache(maxsize=5000)
 def row(i):
  guard(0<=i<n,'BASE_ID_RANGE')
  return struct.unpack_from('<'+str(dim)+'f',mm,8+4*dim*i)
 return f,mm,row

def l2sq(x,y):return sum((a-b)*(a-b) for a,b in zip(x,y))

def vertex_sample(G,base,v):
 off=G['offsets'][v];ids=G['edges'][off:G['offsets'][v+1]]
 vals=[];q=base(v)
 for j,nb in enumerate(ids):
  vals.append({'position':j,'neighbor':int(nb),'distance_l2_squared':l2sq(q,base(nb)) if nb<G['n'] else None})
 first2=vals[:2]
 return {'vertex':v,'degree':len(ids),'first_neighbors':vals[:5],
         'nearest_graph_neighbor':min(vals,key=lambda z:z['distance_l2_squared']) if vals and all(v['distance_l2_squared'] is not None for v in vals) else None,
         'first_two_inversion':bool(len(first2)==2 and first2[0]['distance_l2_squared']>first2[1]['distance_l2_squared'])}

def check_graph(G,base):
 n=G['n'];a=G['edges'];off=G['offsets'];bad=[];selfs=[];dups=[];inversions=0;two_count=0
 for i in range(n):
  row=a[off[i]:off[i+1]]
  if any(nb>=n for nb in row):bad.append(i)
  if i in row:selfs.append(i)
  if len(row)!=len(set(row)):dups.append(i)
  if len(row)>=2 and all(nb<n for nb in row[:2]):
   two_count+=1
   if l2sq(base(i),base(row[0]))>l2sq(base(i),base(row[1])):inversions+=1
 return {'vertices':n,'max_degree':G['max_deg'],'arcs':G['arcs'],
 'invalid_neighbor_rows':len(bad),'self_loop_rows':len(selfs),'duplicate_neighbor_rows':len(dups),
 'rows_where_first_edge_farther_than_second':inversions,'rows_with_two_neighbors':two_count,
 'important':'First/second adjacency geometric order is not guaranteed by binary graph format; inversions ALONE do not establish corruption.',
 'sample_vertices':[vertex_sample(G,base,v) for v in TEST_VERTICES]}

def compare(A,B,label):
 guard(A['n']==B['n'],'GRAPH_COMPARE_N')
 exact=0;setchanged=0;shared=0;total_a=0;total_b=0
 for i in range(A['n']):
  x=A['edges'][A['offsets'][i]:A['offsets'][i+1]]
  y=B['edges'][B['offsets'][i]:B['offsets'][i+1]]
  if x!=y: exact+=1
  sx,sy=set(x),set(y)
  if sx!=sy:setchanged+=1
  shared+=len(sx&sy);total_a+=len(sx);total_b+=len(sy)
 return {'comparison':label,'different_ordered_neighbor_rows':exact,
         'different_neighbor_set_rows':setchanged,'common_edges_across_rows':shared,
         'edges_armA_count_as_sets':total_a,'edges_armB_count_as_sets':total_b}

def pack_zero_j(j):
 guard(0<=j<2048,'PACK_ID_RANGE')
 # 0.0 -> IEEE754 binary64 bits zero; low 11 bits store local index.
 bits=j & 2047
 return {'j':j,'bits_hex':f'0x{bits:016x}','double_value':struct.unpack('<d',struct.pack('<Q',bits))[0],
         'is_subnormal':bool(bits and (bits>>52)==0),
         'index_if_all_subnormal_bits_cleared':0}

def parse_stdout(text):
 def seq(regex):return [int(x) for x in re.findall(regex,text,re.M)]
 return {'total_buckets_by_round':seq(r'^\s*Total buckets:\s*(\d+)\s*$'),
         'total_points_by_round':seq(r'^\s*Total points:\s*(\d+)\s*$'),
         'clustering_comparisons_cumulative':seq(r'^\s*# of comparisons during clustering:\s*(\d+)\s*$'),
         'r90_d6_work_lines':re.findall(r'^R90_D6_WORK .*$',text,re.M)}

def original_sha_gates():
 require_file(SCRIPT_V11,'RUNNER_V11');guard(sha(SCRIPT_V11)==SOURCE_SHA,'RUNNER_SHA_DRIFT')
 source_manifest=ROOT/'source_manifest.json';guard(sha(require_file(source_manifest,'SOURCE_MANIFEST'))==SOURCE_MANIFEST_SHA,'SOURCE_MANIFEST_SHA_DRIFT')
 src=readjson(source_manifest);guard(len(src.get('variants',[]))==6,'SOURCE_MANIFEST_COUNT')
 # Reuse only safe (read-only) tree-fingerprint implementation from the SHA-pinned v1.1 runner.
 spec=importlib.util.spec_from_file_location('r90_p0a_v11_source_only_sha',SCRIPT_V11)
 guard(spec is not None and spec.loader is not None,'RUNNER_IMPORT_SPEC')
 mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
 for rec in src['variants']:
  name=rec['variant'];guard(name in VARIANTS,'SOURCE_VARIANT_NAME')
  guard(mod.digest_tree(ROOT/'source'/name)==rec['tree_sha256'],'SOURCE_TREE_DRIFT_'+name)
 pilot=readjson(ROOT/'pilot_manifest.json');comp=readjson(ROOT/'compile_manifest.json')
 guard('PILOT10K_6_BUILD_COMPLETE__AUDIT_REQUIRED'==pilot.get('status'),'PILOT_STATUS')
 guard('OFF_ON_SIX_BINARIES_COMPILED__PILOT_NOT_RUN'==comp.get('status'),'COMPILER_STATUS')
 guard(comp.get('compiler_sha256')==COMPILER_SHA,'COMPILER_SHA_DRIFT')
 guard(len(pilot.get('runs',[]))==6 and set(comp.get('binaries',{}))==set(VARIANTS),'PILOT_SIX')
 out={};graphs={}
 for rec in pilot['runs']:
  name=rec['arm']+'_'+rec['mode'];guard(name in VARIANTS and name not in out,'PILOT_VARIANT_BAD_'+name)
  guard(rec.get('dataset')=='SIFT10K' and rec.get('rep')==1 and rec.get('threads')==1,'PILOT_CONTEXT_'+name)
  graphpath=require_file(rec['graph'],'PILOT_GRAPH_'+name)
  stdout=require_file(rec['stdout'],'PILOT_STDOUT_'+name)
  timefile=require_file(rec['timefile'],'PILOT_TIME_'+name)
  gsha=sha(graphpath);guard(gsha==rec['graph_sha']==EXPECTED_GRAPH[name],'PILOT_GRAPH_SHA_'+name)
  guard(sha(stdout)==rec['stdout_sha'] and sha(timefile)==rec['timefile_sha'],'PILOT_LOG_SHA_'+name)
  exe=mod.compiled_path(rec['arm'],rec['mode']);guard(sha(require_file(exe,'PILOT_ELF_'+name))==comp['binaries'][name]==rec['elf_sha']==EXPECTED_BIN[name], 'PILOT_ELF_SHA_'+name)
  parsed=parse_stdout(stdout.read_text(errors='replace'))
  guard(len(parsed['total_buckets_by_round'])==2,'BUCKET_COUNT_PARSE_'+name)
  if rec['mode']=='on':
   guard(sha(require_file(ROOT/'logs'/('SIFT10K_'+rec['arm']+'_'+rec['mode']+'_r1.counters.jsonl'),'WORK_ON_'+name))==rec['r86_work_jsonl_sha'],'WORK_COUNTER_SHA_'+name)
  graphs[name]=graph(graphpath)
  out[name]={'graph_sha256':gsha,'stdout_sha256':rec['stdout_sha'],'timefile_sha256':rec['timefile_sha'],'elf_sha256':rec['elf_sha'],'parsed_stdout':parsed}
 guard(set(out)==set(VARIANTS),'PILOT_VARIANT_SET')
 return out,graphs,src,comp

def selftest():
 p=pack_zero_j(12)
 guard(p['bits_hex']=='0x000000000000000c' and p['is_subnormal'] and p['index_if_all_subnormal_bits_cleared']==0,'SELFTEST_PACK')
 g=graph_from_bytes(struct.pack('<II',3,2)+struct.pack('<3I',2,1,0)+struct.pack('<3I',1,2,0),3)
 guard(g['arcs']==3 and g['offsets']==[0,2,3,3] and list(g['edges'])==[1,2,0],'SELFTEST_GRAPH')
 gg=graph_from_bytes(struct.pack('<II',3,2)+struct.pack('<3I',2,1,0)+struct.pack('<3I',1,2,0),3)
 guard(compare(g,gg,'self')['different_ordered_neighbor_rows']==0,'SELFTEST_DIFF')
 t='Total buckets: 500\nTotal points: 15000\n# of comparisons during clustering: 123\nTotal buckets: 499\nTotal points: 14500\n# of comparisons during clustering: 456\n'
 guard(parse_stdout(t)['total_buckets_by_round']==[500,499],'SELFTEST_PARSE')
 print('R90_P0A_PILOT_HOLD_DIAGNOSTIC_V1_SELFTEST_PASS_BITS_GRAPH_PARSE_DIFF')

def atomic(path,obj):
 p=Path(path);guard(not p.exists() and not p.is_symlink(),'TARGET_EXISTS_'+p.name)
 with p.open('x') as f:
  json.dump(obj,f,indent=2,sort_keys=True,allow_nan=False);f.write('\n');f.flush();os.fsync(f.fileno())

def audit():
 guard(not OUTPUT.exists() and not OUTPUT.is_symlink(),'OUTPUT_ALREADY_EXISTS')
 results,graphs,src,comp=original_sha_gates()
 # Geometry is a diagnostic and may NOT be used to certify graph quality or corruption.
 f,mm,base=base_fbin(Path(__file__).resolve().parent/'unused' if False else
  HOME/'ann-task-a/experiments/R90/r90_p38_h17_top2_prefilter_native_v2/data/sift10k.fbin')
 try:
  for name,g in graphs.items():results[name]['graph_diagnostic']=check_graph(g,base)
 finally:mm.close();f.close()
 pairs=[('stock_off','stock_on'),('h17_off','h17_on'),('fast_off','fast_on'),
        ('h17_on','fast_on'),('h17_on','fast_off'),('stock_off','fast_off'),('h17_off','fast_off')]
 diffs=[compare(graphs[a],graphs[b],a+' vs '+b) for a,b in pairs]
 rep={'status':'READ_ONLY_SHA_GATED_PILOT_HOLD_ROOT_CAUSE_NOT_CERTIFIED',
  'source':'P0A v1.1 original compile_manifest/pilot_manifest/6 graph+stdout+timefile/6 binaries',
  'P0A_runner_sha256':SOURCE_SHA,'source_manifest_sha256':SOURCE_MANIFEST_SHA,
  'compiler_sha256':COMPILER_SHA,'original_pilot_status':'PILOT10K_6_BUILD_COMPLETE__AUDIT_REQUIRED',
  'original_auditpilot_status':'HOLD_PILOT10K_GRAPH_PARITY_off',
  'classification':'Stock leaf Highway FTZ/DAZ bit-loss and Stage1 sorting nondeterminism are plausible; direct SIMD trace/scratch evidence NOT present in this report.',
  'ftz_packed_zero_index_example':pack_zero_j(12),
  'important':'Graph SHA mismatches need not imply incorrect ANN; same buckets count does not prove equal leaf memberships; graph edge order inversion alone does not prove corruption.',
  'results':results,'graph_pair_differences':diffs,
  'read_only':True,'full_1m_authorized':False,
  'next_gates':['controlled raw Highway sort packed-bit probe with MXCSR evidence',
                'Stage1 equal membership or leaf fingerprint before kernel equivalence claims',
                'bounded and validated graph topology/Recall gate under identical source and data',
                'replace impossible global graph SHA parity only with scientifically justified per-arm and equivalence checks']}
 OUTPUT.mkdir(parents=True,exist_ok=False)
 atomic(OUTPUT/'diagnostic_report.json',rep)
 with (OUTPUT/'graph_pair_differences.csv').open('x',newline='') as f:
  wr=csv.DictWriter(f,fieldnames=list(diffs[0]));wr.writeheader();wr.writerows(diffs)
 print('R90_P0A_PILOT_HOLD_DIAGNOSTIC_V1_SHA_GATES_PASS_SIX_GRAPHS')
 for name in VARIANTS:
  x=results[name];print('PILOT_DIAGNOSTIC',name,'buckets',x['parsed_stdout']['total_buckets_by_round'],
      'arcs',x['graph_diagnostic']['arcs'],'first_two_inversions',x['graph_diagnostic']['rows_where_first_edge_farther_than_second'],
      'selfloops',x['graph_diagnostic']['self_loop_rows'])
 for x in diffs: print('PILOT_GRAPH_DIFF',x['comparison'],'changed_rows',x['different_ordered_neighbor_rows'],'changed_neighbor_sets',x['different_neighbor_set_rows'])
 print('R90_P0A_PILOT_HOLD_DIAGNOSTIC_V1_REPORT',OUTPUT/'diagnostic_report.json','sha256',sha(OUTPUT/'diagnostic_report.json'))
 print('R90_P0A_PILOT_HOLD_DIAGNOSTIC_V1_NO_BUILD_NO_SEARCH_NO_INPUT_MODIFICATION')

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('phase',choices=('selftest','audit'))
 opts=p.parse_args()
 try:
  if opts.phase=='selftest':selftest()
  else:audit()
 except Exception as e:
  print('R90_P0A_PILOT_HOLD_DIAGNOSTIC_V1_HOLD',str(e),file=sys.stderr)
  sys.exit(2)
