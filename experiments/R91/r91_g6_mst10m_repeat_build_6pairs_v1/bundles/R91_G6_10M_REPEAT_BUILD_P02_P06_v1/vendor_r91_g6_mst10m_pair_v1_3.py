#!/usr/bin/env python3
"""R91 G6 MS-Turing10M C512/C64 -- strict isolated native study.

Phases: selftest, scopecheck, preflight, build, audit-build, search, audit-search.\nV1.2 carries v1.1 G4 schema repair, SHA pins, and 22 GiB host precheck.
V1.3 retains separation of native exit/swap from ru_majflt: record major page faults, do not reject
mere cold I/O faults if zero swap and all cgroup/resource guardrails pass.
Requires the exact G4-10M preflight and full summary from the original Ubuntu run.
No compilation, source patching, overwrite, retry, or modification of historic outputs.
"""
from __future__ import annotations
import argparse, hashlib, json, math, os, re, shutil, signal, struct, subprocess, sys, time
from pathlib import Path
from array import array

TAG='R91_G6_MST10M_C512_C64_PAIR_V1_3'
HOME=Path.home(); ROOT=HOME/'ann-task-a'; R91=ROOT/'experiments/R91'
G4=R91/'r91_g4_mst10m_d2_diagnostic_v1'
G6=R91/'r91_g6_d2_leader_cap_v1'
OUT=R91/'r91_g6_mst10m_c512_c64_pair_v1_3'
BIN=G6/'build/algorithms/PipNN/neighbors-pipnn_FLOAT_T_EUCLIDEAN'
EVAL=R91/'r91_g1b_v2_native_eval_mst10m_exactguard_v1_1/r91_mst10m_recall_exactguard_v2'
EVAL_BUILD=EVAL.parent/'eval_build_receipt.json'
BASE=ROOT/'data/MSTuring_10M_v1/base.10M.fbin'
QUERY=ROOT/'data/MSTuring_10M_v1/query.public.100K.fbin'
GT=ROOT/'data/MSTuring_10M_v1/groundtruth.public.100K.ibin'
PINS={
 'g4_pre':'016ba2332096039211359dff692871667a82668768122d65773f46fa072c1679',
 'g4_summary':'bdbb8371fce39f44609a0eca967fed46fb4790c228f4fc0f960cc01bd170aca9',
 'g4_receipt':'d49027aed33529caa95a315a186253ded49d2cb205b6021e00167880510aea36',
 'g6_elf':'53be9510ead14aff25ec5adffc07d959c78d575f7ffcc9306435360ce9342690',
 'g6_1m_audit':'e383e2828650fe398a3af7aba2ba80a0787f236628f0111684409b715d0762c0',
 'g6_c32_1m_audit':'5ce65a16936f23433654581740e320fcf4a95c32ef648877fc20b42b5550c531',
 'base':'e7756f6b54a07e8af171c7644ce2e1be6d7053ee2a2c30c4b02f99e85984b700',
 'query':'48d087a17bec15a5ec9ea526fe9bd14ac31bbbb5cd200817b341adbb77695644',
 'gt':'77b558bd3b77e4cc1149384996b953b040e412477eb0df9889718fc13e17aff2',
 'eval':'394c6564750722001897254939ba4895e0d7ae6a6dbab44748c30937ea0413c9',
 'eval_new_source':'c851ec10cdc673eb2ef7237340c95a035656cad890f94b03df87b3595390baef',
}
G4_GRAPH_SHA='6f190a26e91bdd402d6b0b341778bd822fac8b1ff58b88824135fa583b9c364e'
LIMIT=25769803776; CPU_BUILD='0,2,4,6'; CPU_SEARCH='0'; BEAMS=(576,1792)
FLAGS=['-num_clusters','2','-cluster_size','1024','-table_size','160','-top_level_leaders','100',
 '-fanout_scheme','10,3,1','-mst_deg','2','-prune','1','-prune_all','1',
 '-prune_degree','64','-hash_bits','12','-alpha','1.1','-k','0']
N=10_000_000; D=100; Q=100_000; K=100
LINE_RE=re.compile(r'^R72_RECALL_ROW\s+beam=(\d+)\s+recall=([^\s]+)\s+qps=([^\s]+)\s+avg_cmps=([^\s]+)\s+avg_visited=([^\s]+)\s*$',re.M)

def hold(ok,label):
 if not ok: raise RuntimeError(TAG+'_HOLD_'+label)

def regular(p):
 p=Path(p);return p.is_file() and not p.is_symlink()

def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(8<<20),b''):h.update(b)
 return h.hexdigest()

def pin(p,expected,label):
 hold(regular(p),'MISSING_OR_SYMLINK_'+label)
 hold(sha(p)==expected,'SHA_MISMATCH_'+label)

def loadj(p):
 hold(regular(p),'JSON_MISSING_'+p.name)
 return json.loads(p.read_text(encoding='utf8'))

def atomic(p,j):
 hold(not p.exists() and not p.is_symlink(),'OUTPUT_COLLISION_'+p.name)
 part=Path(str(p)+'.part')
 hold(not part.exists() and not part.is_symlink(),'PART_COLLISION_'+p.name)
 with part.open('x',encoding='utf8') as f:
  json.dump(j,f,ensure_ascii=False,indent=2,sort_keys=True,allow_nan=False)
  f.write('\n');f.flush();os.fsync(f.fileno())
 os.replace(part,p)

def fbin(p,n,d,label):
 pin(p,PINS[label],label)
 with p.open('rb') as f: header=f.read(8)
 hold(header==struct.pack('<II',n,d),'HEADER_'+label)
 hold(p.stat().st_size==8+4*n*d,'SIZE_'+label)

def gt_file():
 pin(GT,PINS['gt'],'gt')
 with GT.open('rb') as f:hdr=f.read(8)
 hold(hdr==struct.pack('<II',Q,K),'GT_HEADER')
 hold(GT.stat().st_size==8+8*Q*K,'GT_BYTES_DUAL_ARRAY')
 with GT.open('rb') as f:
  f.seek(8);left=Q*K;lo=N;hi=-1
  while left:
   b=f.read(4*min(left,1<<18));hold(b and len(b)%4==0,'GT_ID_TRUNCATED')
   x=array('I');x.frombytes(b)
   if sys.byteorder!='little':x.byteswap()
   hold(len(x)<=left,'GT_ID_OVERRUN');left-=len(x)
   lo=min(lo,min(x));hi=max(hi,max(x))
 hold(lo>=0 and hi<N,'GT_ID_OUT_OF_RANGE')
 return {'id_min':lo,'id_max':hi,'id_count':Q*K}

def verify_g4_schema(pre,summary,receipt):
 """Validate actual native JSON schema, not guessed scalar fields."""
 hold(pre.get('status')=='R91_G4_MST10M_D2_DIAGNOSTIC_V1_PREFLIGHT_PASS_NO_BUILD','G4_PREFLIGHT_STATUS')
 hold(summary.get('status')=='R91_G4_MST10M_D2_DIAGNOSTIC_V1_FULL_NATIVE_10M_GRAPH_AND_WORK_DIAGNOSTIC_AUDIT_PASS','G4_SUMMARY_STATUS')
 hold(receipt.get('status')=='R91_G4_MST10M_D2_DIAGNOSTIC_V1_SLOT_PASS' and receipt.get('error') is None and receipt.get('native_exit_code')==0,'G4_NATIVE_RECEIPT_STATUS')
 hold(summary.get('preflight_sha256')==PINS['g4_pre']==receipt.get('preflight_sha256'),'G4_PREFLIGHT_LINK')
 hold(summary.get('receipt_sha256')==PINS['g4_receipt'],'G4_RECEIPT_LINK')
 hold(pre.get('dataset_sha256')==summary.get('dataset_sha256')==receipt.get('dataset_sha256')==PINS['base'],'G4_DATASET_LINEAGE')
 hold(pre.get('g4_elf_sha256')==summary.get('g4_elf_sha256'),'G4_ELF_LINEAGE')
 hold(pre.get('cgroup_memory_max_bytes')==LIMIT and pre.get('cgroup_swap_max_bytes')==0,'G4_RESOURCE_SCOPE')
 hold(pre.get('cpu_set')==CPU_BUILD,'G4_CPU_AFFINITY')
 g=summary.get('graph'); rg=receipt.get('graph')
 hold(isinstance(g,dict) and g==rg,'G4_SUMMARY_RECEIPT_GRAPH_MISMATCH')
 hold(g.get('sha256')==G4_GRAPH_SHA and g.get('nodes')==N and g.get('max_degree')==64
      and g.get('full_audit') is True and g.get('arcs',0)>0
      and all(g.get(k)==0 for k in ('bad_duplicate','bad_self','bad_neighbor_id')),'G4_GRAPH_INVALID')
 hold(summary.get('resource_events')==receipt.get('resource_events'),'G4_RESOURCE_LINK')
 e=summary.get('resource_events',{})
 hold(all(e.get(k)==0 for k in ('max_events_delta','oom_delta','oom_kill_delta','swap_current')),'G4_RESOURCE_EVENTS')
 hold(summary.get('cgroup_peak_bytes')==receipt.get('cgroup_peak_bytes') and 0<summary['cgroup_peak_bytes']<LIMIT,'G4_CGROUP_PEAK')
 t=summary.get('gnu_time',{})
 hold(t.get('exit_status')==0 and t.get('major_faults')==0 and t.get('swaps')==0,'G4_GNU_TIME_STATUS')
 d=summary.get('depth_stats'); profiles=summary.get('g3_profiles'); diag=summary.get('g4_diagnostics')
 hold(isinstance(d,dict) and set(d)=={'0','1','2','3','4'},'G4_DEPTH_STATS_SCHEMA')
 hold(isinstance(profiles,list) and len(profiles)==2 and isinstance(diag,list) and len(diag)==2,'G4_TWO_PASS_SCHEMA')
 bydepth={k:int(x['W_P']) for k,x in d.items()}
 byprofile={k:0 for k in d};bydiag={k:0 for k in d}
 cum=[]; running=0
 for idx,(p,q) in enumerate(zip(profiles,diag)):
  rows=p.get('depth_work'); buckets=q.get('bucket_statistics')
  hold(isinstance(rows,list) and len(rows)==5 and isinstance(buckets,list) and len(buckets)==5,'G4_PASS_DEPTH_COUNT')
  hold({int(z['depth']) for z in rows}==set(range(5)) and {int(z['depth']) for z in buckets}==set(range(5)),'G4_PASS_DEPTH_SET')
  for v in rows:byprofile[str(v['depth'])]+=int(v['W_P']);running+=int(v['W_P'])
  for v in buckets:bydiag[str(v['depth'])]+=int(v['total_wp'])
  cum.append(running)
 hold(bydepth==byprofile==bydiag,'G4_THREE_WP_SOURCES_DISAGREE')
 hold(sum(bydepth.values())==156998418988,'G4_NATIVE_TOTAL_WP_MISMATCH')
 hold(bydepth['2']==52146043480,'G4_DEPTH2_WP_MISMATCH')
 hold(receipt.get('native_comparisons')==cum,'G4_NATIVE_COMPARISON_CUMULATIVE_MISMATCH')
 hold(int(d['2']['calls'])==96275 and int(d['2']['cap512_calls'])==174,'G4_D2_CALLS_MISMATCH')
 hold(all(int(d[k]['calls'])==sum(int(q['calls']) for diagpass in diag for q in diagpass['bucket_statistics'] if str(q['depth'])==k) for k in d),'G4_CALLS_AGGREGATE_MISMATCH')
 hold(int(d['2']['N_sum'])==595582342,'G4_DEPTH2_N_SUM_MISMATCH')
 return {'g4_baseline_full_wp':sum(bydepth.values()),'g4_depth2_wp':bydepth['2'],
         'g4_depth_wp':bydepth,'g4_depth2_calls':d['2']['calls'],
         'g4_depth2_cap512_calls':d['2']['cap512_calls'],
         'g4_graph_sha256':G4_GRAPH_SHA,'g4_cgroup_peak_bytes':summary['cgroup_peak_bytes']}

def g4_pins():
 p=G4/'preflight.json';s=G4/'full_10m_diagnostic_summary.json';r=G4/'runs/mst10m_g4_on/receipt.json'
 pin(p,PINS['g4_pre'],'G4_10M_PREFLIGHT')
 pin(s,PINS['g4_summary'],'G4_10M_FULL_SUMMARY')
 pin(r,PINS['g4_receipt'],'G4_10M_NATIVE_RECEIPT')
 verified=verify_g4_schema(loadj(p),loadj(s),loadj(r))
 return {'g4_preflight_sha256':PINS['g4_pre'],'g4_full_summary_sha256':PINS['g4_summary'],
         'g4_receipt_sha256':PINS['g4_receipt'], **verified}

def cgroup(strict=False):
 path=Path('/proc/self/cgroup')
 hold(regular(path),'NO_PROC_CGROUP')
 lines=[z.split('::',1)[1] for z in path.read_text().splitlines() if z.startswith('0::')]
 hold(len(lines)==1 and lines[0].startswith('/user.slice/') and '..' not in Path(lines[0]).parts,'NOT_ISOLATED_CGROUP_V2')
 root=Path('/sys/fs/cgroup')/lines[0].lstrip('/')
 names=('memory.max','memory.swap.max','memory.swap.current','memory.current','memory.peak','memory.events')
 vals={x:(root/x).read_text().strip() if regular(root/x) else None for x in names}
 if strict:
  hold(vals['memory.max']==str(LIMIT),'CGROUP_MEMORY_MAX_NOT_25769803776')
  hold(vals['memory.swap.max']=='0','CGROUP_SWAP_MAX_NOT_ZERO')
  hold(vals['memory.swap.current'] is not None and int(vals['memory.swap.current'])==0,'CGROUP_START_SWAP_NONZERO')
 return {'root':str(root),'vals':vals}

def events(raw):
 ans={}
 for l in (raw or '').splitlines():
  z=l.split();
  if len(z)==2:
   try:ans[z[0]]=int(z[1])
   except ValueError:pass
 return ans

def host_memory_kib():
 m=re.search(r'^MemAvailable:\s+(\d+)\s+kB',Path('/proc/meminfo').read_text(),re.M)
 hold(m is not None,'HOST_MEMAVAILABLE_MISSING')
 return int(m.group(1))

def disk_gib():return shutil.disk_usage(R91).free/(1024**3)

def environment_gate(build):
 hold(os.name=='posix' and sys.platform=='linux','NOT_LINUX')
 hold(regular('/usr/bin/time') and shutil.which('taskset') and shutil.which('systemd-run'),'LINUX_DEPS_MISSING')
 cpus={0,2,4,6} if build else {0}
 hold(cpus.issubset(os.sched_getaffinity(0)),'CPU_AFFINITY_MISSING')
 hold(disk_gib()>=20 if build else disk_gib()>=8,'LOW_DISK')
 hold(host_memory_kib()>=int((22.0 if build else 10)*1024**2),'LOW_HOST_MEMAVAILABLE')

def native_inputs(build=True):
 hold(R91.is_dir(),'R91_DIRECTORY_MISSING')
 pre=g4_pins()
 pin(BIN,PINS['g6_elf'],'G6_10M_ELF')
 hold(os.access(BIN,os.X_OK),'G6_ELF_NOT_EXECUTABLE')
 pin(G6/'one_m_build_audit.json',PINS['g6_1m_audit'],'G6_1M_AUDIT')
 pin(G6/'c32_build_audit.json',PINS['g6_c32_1m_audit'],'G6_C32_1M_AUDIT')
 fbin(BASE,N,D,'base');fbin(QUERY,Q,D,'query');gt=gt_file()
 if not build:
  pin(EVAL,PINS['eval'],'EXACTGUARD_EVAL_10M')
  er=loadj(EVAL_BUILD)
  hold(er.get('status')=='R91_G1B_V2_EVAL_COMPILE_PASS' and er.get('compiled_elf_sha')==PINS['eval'] and er.get('source_new_sha')==PINS['eval_new_source'],'EXACTGUARD_EVAL_LINEAGE')
 environment_gate(build)
 return {'pinned_g4':pre,'g6_elf':PINS['g6_elf'],'dataset':{z:PINS[z] for z in ('base','query','gt')},'groundtruth':gt}

def ensure_preflight():
 f=OUT/'preflight.json'
 hold(regular(f),'PREFLIGHT_NOT_RUN')
 j=loadj(f)
 hold(j.get('status')=='PREFLIGHT_PASS_NO_BUILD' and j.get('script_sha256')==sha(Path(__file__)),'PREFLIGHT_SCRIPT_OR_STATUS_DRIFT')
 hold(j.get('g4_summary_sha256')==PINS['g4_summary'],'G4_PREFLIGHT_LINK_DRIFT')
 return j

def preflight():
 hold(not OUT.exists() and not OUT.is_symlink(),'OUTPUT_ROOT_ALREADY_EXISTS')
 x=native_inputs(build=False)
 hold(disk_gib()>=20 and host_memory_kib()>=int(22.0*1024**2),'BUILD_RESOURCE_PREFLIGHT_HOLD')
 OUT.mkdir(parents=True,exist_ok=False)
 atomic(OUT/'preflight.json',{'status':'PREFLIGHT_PASS_NO_BUILD','script_sha256':sha(Path(__file__)),
   'g4_summary_sha256':PINS['g4_summary'],'g4_preflight_sha256':PINS['g4_pre'],
   'inputs':x,'protocol':{'n':N,'d':D,'queries':Q,'degree_cap':64,'fanout':'10,3,1',
   'table_size':160,'max_mem_bytes':LIMIT,'swap_bytes':0,'cpu_build':CPU_BUILD,'cpu_search':CPU_SEARCH,
   'cap_options':[512,64],'beams':list(BEAMS)},'created_epoch':time.time(),
   'notes':['One BUILD per arm; no statistical runtime claim','G4 pin is from original Ubuntu file, not GitHub']})
 print(TAG+'_PREFLIGHT_PASS_G4_NATIVE_SHA_ELF_DATA_GT_EVAL_NO_BUILD',sha(OUT/'preflight.json'),flush=True)

def build_command(arm,graph,timing):
 cap=512 if arm=='C512' else 64
 return ['/usr/bin/time','-v','-o',str(timing),'taskset','-c',CPU_BUILD,str(BIN),
         '-base_path',str(BASE),'-graph_outfile',str(graph),*FLAGS,'-r91_g6_d2_cap',str(cap)]

def stdout_json(s,marker):
 found=[]
 for line in s.splitlines():
  if line.startswith(marker+' '):
   found.append(json.loads(line[len(marker)+1:]))
 return found

def parse_native(stdout,cap):
 gs=stdout_json(stdout,'R91_G3_PROFILE_JSON')
 cs=stdout_json(stdout,'R91_G6_CAP_JSON')
 hold(len(gs)==2 and len(cs)==2,'G3_G6_TWO_PASS_MARKERS')
 work=[]
 for i,(g,c) in enumerate(zip(gs,cs)):
  hold(c.get('cap')==cap and c.get('schema')==1,'G6_CAP_OR_SCHEMA_DRIFT')
  rows=g.get('depth_work')
  hold(isinstance(rows,list) and any(z.get('depth')==2 for z in rows),'G3_DEPTH_WORK_MISSING')
  bydepth={int(z['depth']):z for z in rows}
  hold(len(bydepth)==len(rows),'G3_DUP_DEPTH')
  hold(int(bydepth[2]['W_P'])==int(c['depth2_wp_actual']),'G3_G6_DEPTH2_WORK_MISMATCH')
  hold(int(c['depth2_wp_original'])>=int(c['depth2_wp_actual']),'G6_CAP_INCREASED_D2_WORK')
  hold(int(c['total_leaf_points'])>0 and int(c['leaf_max'])<=1024 and int(c['leaf_empty_count'])==0,'LEAF_AUDIT_INVARIANT')
  hold(int(c['depth2_affected_calls'])<=int(c['depth2_calls']),'CAP_AFFECTED_CALLS_INVALID')
  work.append({'pass':i+1,'depth':{str(k):v for k,v in bydepth.items()},'cap':c,
               'wp_total':sum(int(z['W_P']) for z in rows)})
 cumul=[int(x) for x in re.findall(r'^\s*# of comparisons during clustering:\s*(\d+)\s*$',stdout,re.M)]
 hold(len(cumul)==2 and cumul[0]==work[0]['wp_total'] and cumul[1]==work[0]['wp_total']+work[1]['wp_total'],'COMPARISON_CUMULATIVE_MATCH')
 return {'passes':work,'native_comparisons':cumul,'total_wp':cumul[-1],
         'depth2_wp':sum(int(w['cap']['depth2_wp_actual']) for w in work),
         'depth2_original_wp':sum(int(w['cap']['depth2_wp_original']) for w in work),
         'total_leaf_memberships':sum(int(w['cap']['total_leaf_points']) for w in work),
         'fallback_maxdepth_points':sum(int(w['cap']['fallback_max_depth_points']) for w in work),
         'fallback_shrink_points':sum(int(w['cap']['fallback_small_shrinkage_points']) for w in work)}

def native_time_build_ok(t):
 # ru_majflt counts I/O-backed major faults, not exclusively memory-pressure swaps.
 # Preserve the exact count; do not treat a small cold file page-in as a failed BUILD.
 return (isinstance(t,dict) and t.get('exit_status')=='0'
     and t.get('swaps')==0
     and isinstance(t.get('major_faults'),int) and t['major_faults']>=0
     and isinstance(t.get('wall_s'),(float,int)) and t['wall_s']>0
     and isinstance(t.get('max_rss_kib'),int) and t['max_rss_kib']>0)

def parse_time(p):
 hold(regular(p),'GNU_TIME_MISSING')
 s=p.read_text(errors='replace')
 def value(name):
  m=re.search(r'^\s*'+re.escape(name)+r':\s*([^\n]+)',s,re.M)
  return m.group(1).strip() if m else None
 def walltime(v):
  if v is None:return None
  a=[float(z) for z in v.split(':')]
  return sum(v*60**i for i,v in enumerate(reversed(a)))
 return {'wall_s':walltime(value('Elapsed (wall clock) time (h:mm:ss or m:ss)')),
         'max_rss_kib':int(value('Maximum resident set size (kbytes)') or 0),
         'major_faults':int(value('Major (requiring I/O) page faults') or -1),
         'minor_faults':int(value('Minor (reclaiming a frame) page faults') or -1),
         'file_system_inputs':int(value('File system inputs') or -1),
         'file_system_outputs':int(value('File system outputs') or -1),
         'swaps':int(value('Swaps') or -1),'exit_status':value('Exit status')}

def parse_stage(s):
 periods=[('buckets','buckets time',2),('leaf','build leaf time',2),('final_prune','Final prune time',1)]
 result={}
 for label,phrase,want in periods:
  vals=[]
  for line in s.splitlines():
   if phrase.lower() not in line.lower():continue
   m=re.search(re.escape(phrase)+r'\s*[:=]?\s*([0-9]+(?:\.[0-9]+)?)',line,re.I)
   if not m:m=re.search(r'([0-9]+(?:\.[0-9]+)?)\s*(?:s\s*)?'+re.escape(phrase),line,re.I)
   if m:vals.append(float(m.group(1)))
  hold(len(vals)==want,'STAGE_TIME_LINECOUNT_'+label)
  result[label+'_per_pass_s']=vals
  result[label+'_total_s']=sum(vals)
 return result

def graph_audit(p,n=N):
 import numpy as np
 hold(regular(p),'GRAPH_MISSING_OR_SYMLINK')
 with p.open('rb') as f: h=f.read(8)
 hold(h==struct.pack('<II',n,64),'GRAPH_HEADER_N_OR_MAXDEG')
 d=np.memmap(p,mode='r',dtype='<u4',offset=8,shape=(n,))
 hold(bool(np.all(d<=64)),'GRAPH_DEGREE_OVER64')
 arc=int(np.sum(d,dtype=np.uint64))
 hold(arc>0 and p.stat().st_size==8+4*n+4*arc,'GRAPH_FILE_LENGTH')
 edges=np.memmap(p,mode='r',dtype='<u4',offset=8+4*n,shape=(arc,))
 hold(bool(np.all(edges<n)),'GRAPH_NEIGHBOR_ID_OUT_OF_RANGE')
 offsets=np.empty(n+1,dtype=np.uint64);offsets[0]=0
 np.cumsum(d,dtype=np.uint64,out=offsets[1:])
 selfloops=duprows=0
 for lo in range(0,n,4096):
  hi=min(lo+4096,n);a=int(offsets[lo]);b=int(offsets[hi])
  if a==b:continue
  count=d[lo:hi].astype(np.int64)
  owners=np.repeat(np.arange(lo,hi,dtype=np.uint32),count)
  sub=edges[a:b]
  selfloops+=int(np.count_nonzero(owners==sub))
  start=offsets[lo:hi].astype(np.int64)-a
  indexes=np.arange(b-a,dtype=np.int64)-np.repeat(start,count)
  rows=np.full((hi-lo,64),0xffffffff,dtype=np.uint32)
  rows[owners.astype(np.int64)-lo,indexes]=sub
  rows.sort(axis=1)
  duprows+=int(np.count_nonzero(np.any((rows[:,1:]==rows[:,:-1]) & (rows[:,:-1]!=0xffffffff),axis=1)))
  hold(not selfloops and not duprows,'GRAPH_SELFLOOP_OR_DUPLICATE')
 del edges,d,offsets
 return {'nodes':n,'max_degree':64,'arcs':arc,'bytes':p.stat().st_size,'sha256':sha(p),
         'bad_id':0,'bad_self':selfloops,'bad_duplicate_rows':duprows,'full_all_vertices_audit':True}

def monitor_child(cmd,out,err,env,scope,timeout_s=3600):
 root=Path(scope['root']);e0=events(scope['vals']['memory.events'])
 m={'sample_count':0,'sampled_peak_current':0,'sampled_peak_swap':0,'min_available_kib':host_memory_kib(),
    'min_disk_free_gib':disk_gib(),'status':'STARTED','exit_code':None}
 start=time.monotonic();proc=None
 try:
  with out.open('x') as fo,err.open('x') as fe:
   proc=subprocess.Popen(cmd,stdout=fo,stderr=fe,env=env,start_new_session=True)
   while True:
    code=proc.poll();v=cgroup(False)['vals']
    m['sample_count']+=1
    m['sampled_peak_current']=max(m['sampled_peak_current'],int(v['memory.current'] or 0))
    m['sampled_peak_swap']=max(m['sampled_peak_swap'],int(v['memory.swap.current'] or 0))
    m['min_available_kib']=min(m['min_available_kib'],host_memory_kib())
    m['min_disk_free_gib']=min(m['min_disk_free_gib'],disk_gib())
    delta=events(v['memory.events'])
    trouble=(time.monotonic()-start>timeout_s or int(v['memory.swap.current'] or 0)>0
             or delta.get('oom',0)>e0.get('oom',0) or delta.get('oom_kill',0)>e0.get('oom_kill',0)
             or m['min_disk_free_gib']<8 or m['min_available_kib']<int(1.5*1024**2))
    if code is not None:break
    if trouble:
     m['status']='RESOURCE_OR_TIMEOUT_ABORT';os.killpg(proc.pid,signal.SIGTERM)
     try:proc.wait(timeout=6)
     except subprocess.TimeoutExpired:os.killpg(proc.pid,signal.SIGKILL);proc.wait(timeout=10)
     break
    time.sleep(1)
 except BaseException:
  if proc is not None and proc.poll() is None:
   os.killpg(proc.pid,signal.SIGTERM)
   try:proc.wait(timeout=6)
   except subprocess.TimeoutExpired:os.killpg(proc.pid,signal.SIGKILL);proc.wait(timeout=10)
  raise
 v=cgroup(False)['vals'];e1=events(v['memory.events'])
 m.update({'exit_code':proc.returncode,'elapsed_s':time.monotonic()-start,
           'cg_peak_bytes':int(v['memory.peak'] or 0),'swap_after':int(v['memory.swap.current'] or 0),
           'events_delta':{k:x-e0.get(k,0) for k,x in e1.items()}})
 if m['status']=='STARTED':m['status']='COMPLETED'
 return m

def resource_pass(m):
 return (m['status']=='COMPLETED' and m['exit_code']==0
   and m['sampled_peak_swap']==0 and m['swap_after']==0
   and 0<int(m.get('cg_peak_bytes',0))<LIMIT
   and int(m.get('min_available_kib',0))>=int(1.5*1024**2)
   and all(m['events_delta'].get(k,0)==0 for k in ('max','oom','oom_kill')))

def refresh_resource_after_audit(mon,cg0):
 # The full graph audit itself runs inside the same 24-GiB scope; account for it.
 now=cgroup(False)['vals'];e0=events(cg0['vals']['memory.events']);e1=events(now['memory.events'])
 mon['cg_peak_bytes']=max(mon['cg_peak_bytes'],int(now['memory.peak'] or 0))
 mon['swap_after']=int(now['memory.swap.current'] or 0)
 mon['events_delta']={k:v-e0.get(k,0) for k,v in e1.items()}
 mon['sampled_peak_swap']=max(mon['sampled_peak_swap'],mon['swap_after'])
 return mon

def do_build(arm):
 cg=cgroup(True);ensure_preflight();native_inputs(build=True)
 hold(arm in ('C512','C64'),'UNKNOWN_ARM')
 slot=OUT/'runs'/arm
 hold(not slot.exists() and not slot.is_symlink(),'EXISTING_BUILD_SLOT_'+arm)
 slot.mkdir(parents=True,exist_ok=False)
 graph=slot/'graph.bin';out=slot/'native.stdout';err=slot/'native.stderr';timing=slot/'native.time'
 cmd=build_command(arm,graph,timing)
 atomic(slot/'preregister.json',{'arm':arm,'cap':int(arm[1:]),'script_sha256':sha(Path(__file__)),
       'preflight_sha256':sha(OUT/'preflight.json'),'argv':cmd,'cg_start':cg,'source_elf_sha':PINS['g6_elf'],
       'cpu':CPU_BUILD,'locked_flags':FLAGS,'source_g4_summary_sha':PINS['g4_summary'],'source_g4_receipt_sha':PINS['g4_receipt']})
 env=os.environ.copy();env.update(PARLAY_NUM_THREADS='4',OMP_NUM_THREADS='4',
     OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='1',LC_ALL='C')
 print(TAG+'_BUILD_START_'+arm,flush=True)
 mon=monitor_child(cmd,out,err,env,cg,timeout_s=5400)
 result=None;parse=None;error=None
 try:
  hold(resource_pass(mon),'BUILD_RESOURCE_OR_EXIT')
  hold(err.stat().st_size==0,'BUILDER_STDERR_NONEMPTY')
  stdout=out.read_text(errors='replace')
  parse=parse_native(stdout,int(arm[1:]))
  parse['stage_times']=parse_stage(stdout)
  result=graph_audit(graph)
  ti=parse_time(timing)
  hold(native_time_build_ok(ti),'NATIVE_TIME_EXIT_SWAP_OR_INVALID_METRICS')
 except Exception as ex:error=str(ex)
 refresh_resource_after_audit(mon,cg)
 if not resource_pass(mon):error=error or 'CGROUP_EVENTS_OR_SWAP_AFTER_FULL_GRAPH_AUDIT'
 r={'status':'BUILD_GRAPH_WORK_AUDIT_PASS' if result is not None and error is None else 'BUILD_HOLD_PRESERVE_OUTPUT',
    'arm':arm,'cap':int(arm[1:]),'error':error,'resource':mon,'time':parse_time(timing) if regular(timing) else None,
    'graph':result,'parsed':parse,'preflight_sha256':sha(OUT/'preflight.json'),
    'source_elf_sha256':PINS['g6_elf'],
    'files_sha256':{p.name:sha(p) for p in (out,err,timing,graph) if regular(p)}}
 atomic(slot/'receipt.json',r)
 print(TAG+'_BUILD_SLOT_'+r['status']+'_'+arm+' receipt_sha256 '+sha(slot/'receipt.json'),flush=True)
 hold(r['status']=='BUILD_GRAPH_WORK_AUDIT_PASS','BUILD_SLOT_FAILED_'+arm)

def build_receipt(arm):
 slot=OUT/'runs'/arm
 r=loadj(slot/'receipt.json')
 hold(r.get('status')=='BUILD_GRAPH_WORK_AUDIT_PASS' and r.get('arm')==arm,'BUILD_RECEIPT_STATUS_'+arm)
 hold(r.get('source_elf_sha256')==PINS['g6_elf'],'BUILD_SOURCE_SHA_DRIFT_'+arm)
 hold(r.get('preflight_sha256')==sha(OUT/'preflight.json'),'BUILD_PRE_SOURCE_DRIFT_'+arm)
 for f,want in r['files_sha256'].items():pin(slot/f,want,'BUILD_FILE_'+arm+'_'+f)
 hold(resource_pass(r['resource']),'BUILD_RESOURCE_DRIFT_'+arm)
 hold(native_time_build_ok(r['time']),'BUILD_TIME_EXIT_SWAP_OR_INVALID_METRICS_'+arm)
 hold(r['parsed']['total_wp']==r['parsed']['native_comparisons'][-1],'BUILD_WORK_DRIFT_'+arm)
 hold(r['graph']['sha256']==sha(slot/'graph.bin'),'BUILD_GRAPH_SHA_DRIFT_'+arm)
 return r

def audit_builds(verify_only=False):
 ensure_preflight();native_inputs(True)
 x=build_receipt('C512');y=build_receipt('C64')
 # Full graph content is rechecked independently of builder's own receipt.
 for a in ('C512','C64'):
  r=x if a=='C512' else y
  hold(graph_audit(OUT/'runs'/a/'graph.bin')==r['graph'],'GRAPH_FULL_READBACK_DRIFT_'+a)
 def stats(r):
  p=r['parsed'];s={}
  for phase in p['passes']:
   for d,item in phase['depth'].items():
    s.setdefault(d,{'wp':0,'wa':0,'n':0,'calls':0})
    s[d]['wp']+=int(item['W_P']);s[d]['wa']+=int(item['W_A']);s[d]['n']+=int(item['N_sum'])
    s[d]['calls']+=int(item.get('fanout1_calls',0))+int(item.get('fanout3_calls',0))+int(item.get('fanout10_calls',0))
  return {'arm':r['arm'],'wall_s':r['time']['wall_s'],'max_rss_kib':r['time']['max_rss_kib'],
    'major_faults_reported_nonfatal':r['time']['major_faults'],
    'minor_faults':r['time']['minor_faults'],
    'file_system_inputs':r['time']['file_system_inputs'],
    'file_system_outputs':r['time']['file_system_outputs'],
    'cgroup_peak_bytes':r['resource']['cg_peak_bytes'],'total_wp':p['total_wp'],'depth':s,
    'wp_ge2':sum(z['wp'] for k,z in s.items() if int(k)>=2),
    'depth2_wp':p['depth2_wp'],'depth2_original_wp':p['depth2_original_wp'],
    'fallback_maxdepth_points':p['fallback_maxdepth_points'],
    'fallback_shrink_points':p['fallback_shrink_points'],
    'depth2_affected_calls':sum(int(w['cap']['depth2_affected_calls']) for w in p['passes']),
    'depth2_affected_n':sum(int(w['cap']['depth2_affected_n']) for w in p['passes']),
    'depth2_calls':sum(int(w['cap']['depth2_calls']) for w in p['passes']),
    'leaf_count':sum(int(w['cap']['leaf_count']) for w in p['passes']),
    'leaf_p50_by_pass':[int(w['cap']['leaf_p50']) for w in p['passes']],
    'leaf_p90_by_pass':[int(w['cap']['leaf_p90']) for w in p['passes']],
    'leaf_max_by_pass':[int(w['cap']['leaf_max']) for w in p['passes']],
    'stage_times':p['stage_times'],
    'leaf_memberships':p['total_leaf_memberships'],'arcs':r['graph']['arcs'],
    'graph_sha':r['graph']['sha256']}
 bx,by=stats(x),stats(y)
 hold(bx['depth'].get('0',{}).get('wa')==by['depth'].get('0',{}).get('wa'),'D0_WA_CHANGED')
 hold(bx['depth'].get('1',{}).get('wa')==by['depth'].get('1',{}).get('wa'),'D1_WA_CHANGED')
 def delta(a,b):return {'absolute':b-a,'relative_to_C512_percent':100*(b/a-1) if a else None}
 summary={'status':'TWO_10M_NATIVE_BUILDS_FULL_GRAPH_WORK_RESOURCE_AUDIT_PASS_SEARCH_NOT_RUN',
   'experiment_scope':'one native 4CPU build per arm; not a repeated randomized paired study',
   'protocol':{'source_sha':PINS['g6_elf'],'g4_summary_sha':PINS['g4_summary'],'g4_receipt_sha':PINS['g4_receipt'],'data_sha':PINS['base'],
      'fanout':'10,3,1','table_size':160,'leader_cap_only_depth2':[512,64],'memory_max_bytes':LIMIT,'swap_max':0},
   'C512':bx,'C64':by,
   'C64_minus_C512':{n:delta(bx[n],by[n]) for n in ('wall_s','max_rss_kib','cgroup_peak_bytes','total_wp','wp_ge2','depth2_wp','fallback_maxdepth_points','fallback_shrink_points','leaf_memberships','arcs','depth2_affected_calls','depth2_affected_n','depth2_calls','leaf_count')},
   'source_receipts':{a:sha(OUT/'runs'/a/'receipt.json') for a in ('C512','C64')},
   'limits':['Structural graph audit != Recall quality','one build per arm; no statistical build speedup claim',
      'depth2 work saving != net saving due to deeper depth and leaf costs',
      'major_faults (ru_majflt) and file_system_inputs recorded, nonfatal alone; zero swap/cgroup events remain mandatory',
      'each independent v1.2 build is new; historical v1.1 C512 HOLD artifact never reclassified or modified']}
 if verify_only:
  hold(loadj(OUT/'build_pair_audit.json')==summary,'BUILD_PAIR_READBACK_MISMATCH')
 else:
  atomic(OUT/'build_pair_audit.json',summary)
 print(TAG+'_TWO_10M_BUILD_GRAPH_WORK_AUDIT_PASS_SEARCH_PENDING',sha(OUT/'build_pair_audit.json'),flush=True)
 for a in ('C512','C64'):print(TAG+'_BUILD_SUMMARY_'+a,json.dumps(summary[a],sort_keys=True),flush=True)

def parse_search(txt):
 hold(txt.count('R85_A1C_DYNAMIC_BEAMS count=2')==1,'SEARCH_BEAM_COUNT_MARKER')
 p=[x for x in txt.splitlines() if x.startswith('R72_RECALL_INPUT_PASS ')]
 hold(len(p)==1 and 'graph_nodes=10000000' in p[0] and 'queries=100000' in p[0] and 'gt_k=100' in p[0],'SEARCH_INPUT_PROOF')
 hold(txt.count('R72_RECALL_EVAL_PASS')==1,'SEARCH_END_MARKER')
 arr=[]
 for m in LINE_RE.finditer(txt):
  try:rec,qps,vis=(float(m.group(i)) for i in (2,3,5))
  except ValueError:hold(False,'SEARCH_ROW_INVALID_FLOAT')
  hold(math.isfinite(rec) and 0<=rec<=1 and math.isfinite(qps) and qps>0 and math.isfinite(vis) and vis>=0,'SEARCH_METRIC_INVALID')
  arr.append({'beam':int(m.group(1)),'recall_at10':rec,'qps':qps,'avg_visited':vis,
    'avg_cmps_legacy_int32_untrusted':None,'inverse_qps_us_not_latency_p95':1e6/qps})
 hold([v['beam'] for v in arr]==list(BEAMS),'SEARCH_BEAMS_MISSING_OR_ORDER')
 return arr

def do_search(arm):
 hold(arm in ('C512','C64'),'UNKNOWN_ARM_SEARCH')
 cg=cgroup(True);ensure_preflight();native_inputs(False)
 hold(regular(OUT/'build_pair_audit.json'),'BUILD_PAIR_AUDIT_MISSING')
 a=loadj(OUT/'build_pair_audit.json')
 hold(a['status']=='TWO_10M_NATIVE_BUILDS_FULL_GRAPH_WORK_RESOURCE_AUDIT_PASS_SEARCH_NOT_RUN','BUILD_PAIR_NOT_PASS')
 br=build_receipt(arm)
 graph=OUT/'runs'/arm/'graph.bin';hold(sha(graph)==br['graph']['sha256'],'GRAPH_SHA_DRIFT_BEFORE_SEARCH')
 slot=OUT/'search'/arm;hold(not slot.exists() and not slot.is_symlink(),'SEARCH_SLOT_EXISTS_'+arm)
 slot.mkdir(parents=True,exist_ok=False)
 so=slot/'native.stdout';se=slot/'native.stderr';tm=slot/'native.time'
 cmd=['/usr/bin/time','-v','-o',str(tm),'taskset','-c',CPU_SEARCH,str(EVAL),str(graph),str(BASE),str(QUERY),str(GT),','.join(map(str,BEAMS))]
 atomic(slot/'preregister.json',{'arm':arm,'script_sha':sha(Path(__file__)),'preflight_sha':sha(OUT/'preflight.json'),
    'build_pair_sha':sha(OUT/'build_pair_audit.json'),'build_receipt_sha':sha(OUT/'runs'/arm/'receipt.json'),
    'eval_bin_sha':PINS['eval'],'graph_sha':br['graph']['sha256'],'beams':list(BEAMS),
    'cmd':cmd,'cgroup':cg,'no_new_build':True,'not_matched_recall':True})
 env=os.environ.copy();env.update(PARLAY_NUM_THREADS='1',OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='1',LC_ALL='C')
 print(TAG+'_SEARCH_START_'+arm,flush=True)
 mon=monitor_child(cmd,so,se,env,cg,timeout_s=7200)
 p=None;error=None
 try:
  hold(resource_pass(mon),'SEARCH_RESOURCE_OR_EXIT')
  hold(se.stat().st_size==0,'SEARCH_STDERR_NOT_EMPTY')
  p=parse_search(so.read_text(errors='replace'))
  hold(sha(graph)==br['graph']['sha256'],'GRAPH_SHA_DRIFT_AFTER_SEARCH')
 except Exception as ex:error=str(ex)
 refresh_resource_after_audit(mon,cg)
 if not resource_pass(mon):error=error or 'CGROUP_EVENTS_OR_SWAP_AFTER_SEARCH_AUDIT'
 floor=bool(p and p[0]['recall_at10']>=.990 and p[1]['recall_at10']>=.998)
 receipt={'status':'SEARCH_AUDITABLE_NATIVE_PASS' if p is not None and not error else 'SEARCH_HOLD_PRESERVE_OUTPUT',
  'arm':arm,'error':error,'graph_sha256':br['graph']['sha256'],'build_receipt_sha256':sha(OUT/'runs'/arm/'receipt.json'),
  'eval_binary_sha256':PINS['eval'],'resource':mon,'time':parse_time(tm) if regular(tm) else None,
  'quality_floor_pass':floor,'metrics':p,'beams':list(BEAMS),
  'files_sha256':{z.name:sha(z) for z in (so,se,tm) if regular(z)}}
 atomic(slot/'receipt.json',receipt)
 print(TAG+'_SEARCH_'+receipt['status']+'_'+arm+' receipt_sha256 '+sha(slot/'receipt.json'),flush=True)
 hold(receipt['status']=='SEARCH_AUDITABLE_NATIVE_PASS','SEARCH_SLOT_FAILED_'+arm)

def search_receipt(arm):
 slot=OUT/'search'/arm;r=loadj(slot/'receipt.json')
 hold(r['status']=='SEARCH_AUDITABLE_NATIVE_PASS' and r['arm']==arm,'SEARCH_NOT_PASS_'+arm)
 hold(r['graph_sha256']==build_receipt(arm)['graph']['sha256'],'SEARCH_GRAPH_LINK_DRIFT_'+arm)
 hold(r['build_receipt_sha256']==sha(OUT/'runs'/arm/'receipt.json'),'SEARCH_BUILD_RECEIPT_DRIFT_'+arm)
 hold(r['eval_binary_sha256']==PINS['eval'] and r['beams']==list(BEAMS),'SEARCH_PROTOCOL_DRIFT_'+arm)
 hold(resource_pass(r['resource']),'SEARCH_RESOURCE_DRIFT_'+arm)
 for f,digest in r['files_sha256'].items():pin(slot/f,digest,'SEARCH_LOG_'+arm+'_'+f)
 hold(parse_search((slot/'native.stdout').read_text(errors='replace'))==r['metrics'],'SEARCH_REPARSE_DRIFT_'+arm)
 return r

def audit_search(verify_only=False):
 ensure_preflight();native_inputs(False)
 bs=loadj(OUT/'build_pair_audit.json')
 hold(bs.get('status')=='TWO_10M_NATIVE_BUILDS_FULL_GRAPH_WORK_RESOURCE_AUDIT_PASS_SEARCH_NOT_RUN','BUILD_PAIR_AUDIT_STATUS')
 x=search_receipt('C512');y=search_receipt('C64')
 results={a:r['metrics'] for a,r in (('C512',x),('C64',y))}
 def relative_metric(k,beam):
  a=next(z[k] for z in results['C512'] if z['beam']==beam)
  b=next(z[k] for z in results['C64'] if z['beam']==beam)
  return {'C512':a,'C64':b,'difference':b-a,'relative_percent':100*(b/a-1) if a else None}
 delta={str(beam):{key:relative_metric(key,beam) for key in ('recall_at10','qps','avg_visited')} for beam in BEAMS}
 quality={a:bool(r['quality_floor_pass']) for a,r in (('C512',x),('C64',y))}
 r={'status':'TWO_10M_NATIVE_FIXED_BEAM_SEARCH_AUDIT_PASS' if all(quality.values()) else 'TWO_10M_NATIVE_SEARCH_VALID_QUALITY_FLOOR_NOT_MET',
    'search_valid_for_both':True,'quality_floor_per_arm':quality,
    'results':results,'delta':delta,'build_pair_sha':sha(OUT/'build_pair_audit.json'),
    'source_receipts':{a:sha(OUT/'search'/a/'receipt.json') for a in ('C512','C64')},
    'limitations':['Fixed beam is not matched Recall; cannot claim matched QPS advantage',
                   'One independent graph and one Search trial per arm; no noninferiority claim',
                   'Legacy evaluator avg_cmps has int32 overflow risk at high beam; ignored']}
 if verify_only:
  hold(loadj(OUT/'search_pair_audit.json')==r,'SEARCH_PAIR_READBACK_MISMATCH')
 else:
  atomic(OUT/'search_pair_audit.json',r)
 print(TAG+'_SEARCH_PAIR_'+r['status'],sha(OUT/'search_pair_audit.json'),flush=True)
 for b in BEAMS:print(TAG+'_PAIR_BEAM_'+str(b),json.dumps(delta[str(b)],sort_keys=True),flush=True)
 hold(all(quality.values()),'ONE_OR_MORE_SEARCH_QUALITY_FLOORS_BELOW_THRESHOLD')

def selftest():
 hold(LIMIT==24*1024**3,'BAD_24G_LIMIT')
 hold(EVAL == R91/'r91_g1b_v2_native_eval_mst10m_exactguard_v1_1/r91_mst10m_recall_exactguard_v2', 'EXACTGUARD_EVAL_PATH_DRIFT')
 hold(EVAL_BUILD == EVAL.parent/'eval_build_receipt.json','EXACTGUARD_EVAL_RECEIPT_PATH_DRIFT')
 hold(PINS['eval']=='394c6564750722001897254939ba4895e0d7ae6a6dbab44748c30937ea0413c9','EXACTGUARD_EVAL_SHA_PIN_DRIFT')
 hold(all(len(x)==64 and set(x)<=set('0123456789abcdef') for x in PINS.values()),'BAD_SOURCE_SHA_PIN')
 hold(len(FLAGS)==24,'BAD_BUILDER_FLAG_COUNT')
 x=build_command('C64',Path('/tmp/new.graph'),Path('/tmp/new.time'))
 hold(x[-2:]==['-r91_g6_d2_cap','64'] and '-fanout_scheme' in x,'BAD_CAP_CLI')
 marker='R85_A1C_DYNAMIC_BEAMS count=2\nR72_RECALL_INPUT_PASS graph_nodes=10000000 queries=100000 gt_k=100\n'
 marker+='R72_RECALL_ROW beam=576 recall=0.991 qps=900 avg_cmps=4294967295 avg_visited=600\n'
 marker+='R72_RECALL_ROW beam=1792 recall=0.9981 qps=410 avg_cmps=4294967295 avg_visited=1100\nR72_RECALL_EVAL_PASS\n'
 a=parse_search(marker);hold(len(a)==2 and a[1]['avg_cmps_legacy_int32_untrusted'] is None,'PARSER_GOOD_FIXTURE')
 for bad in [marker.replace('graph_nodes=10000000','graph_nodes=1000000'),marker.replace('qps=900','qps=nan'),
             marker.replace('R72_RECALL_EVAL_PASS',''),marker.replace('beam=1792','beam=576')]:
  try:parse_search(bad)
  except RuntimeError:pass
  else:hold(False,'PARSER_MUTATION_ACCEPTED')
 # Schema-mutation test uses actual uploaded JSON in local validation (not during native preflight).
 hold(PINS['g4_receipt']=='d49027aed33529caa95a315a186253ded49d2cb205b6021e00167880510aea36','G4_RECEIPT_PIN_SELFTEST')
 hold(int(22*1024**2)>int(1.5*1024**2),'HOST_MEM_SAFE_MARGIN')
 import tempfile
 with tempfile.TemporaryDirectory(prefix='r91_g6_test_') as temp:
  p=Path(temp)/'test.graph'
  def writeg(edge):p.write_bytes(struct.pack('<II4I4I',4,64,2,1,0,1,*edge))
  writeg((1,2,0,2))
  hold(graph_audit(p,n=4)['arcs']==4,'GRAPH_GOOD_FIXTURE')
  for data in ((1,1,0,2),(1,2,3,9),(0,2,0,2)):
   writeg(data)
   try:graph_audit(p,n=4)
   except RuntimeError:pass
   else:hold(False,'GRAPH_INVALID_FIXTURE_ACCEPTED')
 # Native stage labels from PiPNN timing output, not a wall-time model.
 ss='buckets time: 5.12\nbuckets time: 5.20\nbuild leaf time: 12.5\nbuild leaf time: 12.6\nFinal prune time: 6.1\n'
 hold(parse_stage(ss)['buckets_total_s']==10.32,'STAGE_PARSER_FIXTURE')
 # Explicitly regression-test the v1.1 HOLD trigger: one major page fault is informational.
 import tempfile as _tempfile
 with _tempfile.TemporaryDirectory(prefix='r91_g6_time_test_') as _tempdir:
  tf=Path(_tempdir)/'native.time'
  tf.write_text('Elapsed (wall clock) time (h:mm:ss or m:ss): 6:11.03\n'
      'Maximum resident set size (kbytes): 21641624\n'
      'Major (requiring I/O) page faults: 1\n'
      'Minor (reclaiming a frame) page faults: 2495299\n'
      'File system inputs: 64\nFile system outputs: 4303840\n'
      'Swaps: 0\nExit status: 0\n')
  t=parse_time(tf)
  hold(native_time_build_ok(t) and t['major_faults']==1 and t['file_system_inputs']==64,
       'COLD_MAJOR_PAGEIN_MUST_NOT_HOLD')
  hold(not native_time_build_ok({**t,'swaps':1}),'SWAP_MUST_HOLD')
  hold(not native_time_build_ok({**t,'exit_status':'137'}),'EXIT_MUST_HOLD')
  hold(not native_time_build_ok({**t,'major_faults':-1}),'INVALID_MAJOR_COUNTER_MUST_HOLD')
  r={'status':'COMPLETED','exit_code':0,'sampled_peak_swap':0,'swap_after':0,
      'cg_peak_bytes':22215172096,'min_available_kib':5967324,
      'events_delta':{'max':0,'oom':0,'oom_kill':0}}
  hold(resource_pass(r),'CLEAN_RESOURCE_FIXTURE_MUST_PASS')
  hold(not resource_pass({**r,'sampled_peak_swap':1}),'SAMPLED_SWAP_MUST_HOLD')
  hold(not resource_pass({**r,'swap_after':1}),'END_SWAP_MUST_HOLD')
  hold(not resource_pass({**r,'cg_peak_bytes':LIMIT}),'CGROUP_AT_LIMIT_MUST_HOLD')
  hold(not resource_pass({**r,'min_available_kib':100}),'MIN_HOST_AVAILABLE_MUST_HOLD')
  hold(not resource_pass({**r,'events_delta':{'max':1,'oom':0,'oom_kill':0}}),
       'CGROUP_MAX_EVENT_MUST_HOLD')
 print(TAG+'_SELFTEST_PASS_MAJOR_FAULT_1_NONFATAL_SWAP_CGROUP_GRAPH_SEARCH_AND_STAGE_GATES',flush=True)

def main():
 p=argparse.ArgumentParser();p.add_argument('mode',choices=('selftest','scopecheck','preflight','build','audit-build','search','audit-search'))
 p.add_argument('--arm',choices=('C512','C64'));p.add_argument('--verify-only',action='store_true');a=p.parse_args()
 try:
  if a.mode=='selftest':selftest()
  elif a.mode=='scopecheck':
   x=cgroup(True);print(TAG+'_SCOPE_PROBE_PASS_24GIB_ZERO_SWAP',x['root'],flush=True)
  elif a.mode=='preflight':preflight()
  elif a.mode=='build':hold(a.arm is not None,'BUILD_REQUIRES_ARM');do_build(a.arm)
  elif a.mode=='audit-build':audit_builds(verify_only=a.verify_only)
  elif a.mode=='search':hold(a.arm is not None,'SEARCH_REQUIRES_ARM');do_search(a.arm)
  else:audit_search(verify_only=a.verify_only)
 except Exception as e:
  print(TAG+'_HOLD',type(e).__name__,str(e),file=sys.stderr,flush=True)
  sys.exit(2)
if __name__=='__main__':main()
