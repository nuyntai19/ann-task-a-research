#!/usr/bin/env python3
"""R91-G1B v2: EXACT one-guard R86-v4 source adaptation + native MS-Turing10M Search.

Stages: selftest, prepare, preflight, scope-check, run, audit.
Patches a SHA-pinned OLD evaluator *copy*, compiles using the original SHA-pinned
R86 compile_command, writes only R91 new paths. Never BUILDs or changes an ANN graph.
Do not compare across different evaluators unless the only input-guard source diff
and protocol are audited. Search is a fixed-beam screen, not matched-Recall QPS.
"""
from __future__ import annotations
import argparse, difflib, hashlib, json, math, os, re, shutil, struct, subprocess, sys, time
from array import array
from pathlib import Path

TAG = 'R91_G1B_V2_MST10M_EXACT_GUARD_EVAL'
HOME = Path.home()
ROOT = HOME/'ann-task-a'
R91 = ROOT/'experiments/R91'
R86 = ROOT/'experiments/R86/msturing_1m_eval'
OLD_SOURCE = R86/'r86_msturing1m_graph_recall_v4_highbeam.cc'
OLD_MANIFEST = R86/'r86_msturing1m_highbeam_v4_manifest.json'
OLD_BINARY = R86/'r86_msturing1m_graph_recall_v4_highbeam'
EVAL_ROOT = R91/'r91_g1b_v2_native_eval_mst10m_exactguard_v1_1'
NEW_SOURCE = EVAL_ROOT/'r91_mst10m_recall_exactguard_v2.cc'
NEW_BINARY = EVAL_ROOT/'r91_mst10m_recall_exactguard_v2'
NEW_BUILD = EVAL_ROOT/'eval_build_receipt.json'
PRE_ROOT = R91/'r91_g1b_v2_mst10m_fast_preflight_v1_1'
PRE_JSON = PRE_ROOT/'r91_g1b_v2_preflight.json'
OUT_ROOT = R91/'r91_g1b_v2_mst10m_fast_fixedbeam_search_v1_1'
SEARCH_REPORT = OUT_ROOT/'quality_screen_summary.json'
G1ROOT = R91/'r91_g1_one_fastv2_flat_c160_mst10m_24g_v1'
G1_JSON = G1ROOT/'r91_g1_single10m_result.json'
G07_JSON = R91/'r91_g07_mst10m_flat_c160_preflight_v1/r91_g07_preflight.json'
GRAPH = G1ROOT/'graphs/MSTuring10M_fast_off_C160_K1024_N2.graph'
D = ROOT/'data/MSTuring_10M_v1'
BASE = D/'base.10M.fbin'
QUERY = D/'query.public.100K.fbin'
GT = D/'groundtruth.public.100K.ibin'
OLD_HOLD = R91/'r91_g1b_mst10m_fastv2_search_screen_v1/quality_screen_summary.json'
OLD_PREF = R91/'r91_g1b_mst10m_fastv2_search_preflight_v1/r91_g1b_preflight.json'
BEAMS = (384, 896, 1024, 1536)
HARD_CAP = 24 * 1024**3
ORIG_GUARD = 'base.size() != 1000000 || base.dimension() != 100 ||'
NEW_GUARD  = 'base.size() != 10000000 || base.dimension() != 100 ||'
PIN = {
 'old_source':'6aa0e38a3b0a536ccbcd3bfe0ca690257ab963215b5135d642cbb60d259c3f89',
 'old_manifest':'8f6b9b87f8bcf0e1651cf2b8a168526c8e8d56175224bbeda534431be57e4f22',
 'old_binary':'bb6576ad3e1e0cc770535aa06355c664993ca70bd1170d6dd4d202ab5767e144',
 'new_source':'c851ec10cdc673eb2ef7237340c95a035656cad890f94b03df87b3595390baef',
 'g1':'bd46f8327e634e05ebdf3975c602d3c069df749be8dc3a6e140f286a606e3835',
 'g07':'70e9f33fa933b791f45e3254185b0374b129b6c4297a0e469c7d3ae02f38b8b0',
 'graph':'4055dedc2ccb3b6406fed45ed28de2ec57c46fe2b085b5046ae13cd943702429',
 'base':'e7756f6b54a07e8af171c7644ce2e1be6d7053ee2a2c30c4b02f99e85984b700',
 'query':'48d087a17bec15a5ec9ea526fe9bd14ac31bbbb5cd200817b341adbb77695644',
 'gt':'77b558bd3b77e4cc1149384996b953b040e412477eb0df9889718fc13e17aff2',
 'old_hold':'9d48e98acadbba7ff66ba55ac5ba3f1f81bb4e56e53ada248cc7d1812607e003',
 'old_pre':'58d651b7598643ea784e026d79343395b29e57d8dc7582d09f9b0d18ce653fd4',
}
ROW = re.compile(r'^R72_RECALL_ROW\s+beam=(\d+)\s+recall=([^\s]+)\s+qps=([^\s]+)\s+avg_cmps=([^\s]+)\s+avg_visited=([^\s]+)\s*$', re.M)

def hold(ok, why):
 if not ok: raise RuntimeError(TAG+'_HOLD_'+why)

def regular(p): return p.is_file() and not p.is_symlink()

def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(4*1024*1024),b''):h.update(b)
 return h.hexdigest()

def pin(p,key):
 hold(regular(p),'SOURCE_MISSING_OR_SYMLINK_'+key)
 hold(sha(p)==PIN[key],'SHA_DRIFT_'+key)

def read_json(p):
 hold(regular(p),'RECEIPT_MISSING_'+p.name)
 return json.loads(p.read_text(encoding='utf-8'))

def atomic(path,obj):
 hold(not path.exists() and not path.is_symlink(),'COLLISION_'+str(path))
 tmp=Path(str(path)+'.part')
 hold(not tmp.exists() and not tmp.is_symlink(),'PART_COLLISION_'+str(tmp))
 with tmp.open('x',encoding='utf8') as f:
  json.dump(obj,f,indent=2,sort_keys=True,allow_nan=False)
  f.write('\n');f.flush();os.fsync(f.fileno())
 os.replace(tmp,path)

def source_patch(old):
 hold(old.count(ORIG_GUARD)==1,'OLD_GUARD_MUST_BE_UNIQUE')
 hold(NEW_GUARD not in old,'SOURCE_ALREADY_PATCHED')
 new=old.replace(ORIG_GUARD,NEW_GUARD,1)
 hold(new.count(NEW_GUARD)==1 and len(new)==len(old)+1,'EXACT_ONE_GUARD_DIFF')
 return new

def read_original():
 pin(OLD_SOURCE,'old_source');pin(OLD_MANIFEST,'old_manifest');pin(OLD_BINARY,'old_binary')
 src=OLD_SOURCE.read_text(encoding='utf-8')
 patched=source_patch(src)
 hold(hashlib.sha256(patched.encode()).hexdigest()==PIN['new_source'],'PATCHED_SOURCE_EXPECTED_SHA')
 manifest=read_json(OLD_MANIFEST)
 hold(manifest['source_v4_sha256']==PIN['old_source'] and manifest['binary_v4_sha256']==PIN['old_binary'], 'ORIGINAL_MANIFEST_PROVENANCE')
 args=manifest.get('compile_command')
 hold(isinstance(args,list) and args[0]=='/usr/bin/c++' and all(isinstance(a,str) for a in args),'ORIGINAL_COMPILE_CMD')
 hold(args.count(str(OLD_SOURCE))==1 and args.count(str(OLD_BINARY))==1 and args.count('-o')==1,'SOURCE_OUTPUT_ONLY_ONCE')
 hold(args[args.index('-o')+1]==str(OLD_BINARY),'ORIGINAL_COMPILE_OUTPUT_POSITION')
 for flag in ('-DHWY_STATIC_DEFINE','-DPARLAY_ELASTIC_PARALLELISM=true','-march=native','-ffast-math','-O3','-std=gnu++17','-fopenmp'):
  hold(flag in args,'ORIGINAL_COMPILE_FLAG_'+flag)
 hold(all(NEW_SOURCE.as_posix()!=x and NEW_BINARY.as_posix()!=x for x in args),'COMPILE_ALREADY_MODIFIED')
 return src,patched,args

def prepare():
 hold(not EVAL_ROOT.exists() and not EVAL_ROOT.is_symlink(),'EVAL_ROOT_EXISTS_DO_NOT_OVERWRITE')
 hold(not PRE_ROOT.exists() and not OUT_ROOT.exists(),'OUTPUT_ROOT_EXISTS_PRESERVE')
 src,patched,args=read_original()
 hold(shutil.which('/usr/bin/c++') is not None,'COMPILER_MISSING')
 for a in args:
  if a.startswith('-I'):
   hold(Path(a[2:]).is_dir(),'INCLUDE_DIR_MISSING_'+Path(a[2:]).name)
  elif a.endswith('.a'):
   hold(Path(a).is_file(),'STATIC_LIB_MISSING_'+Path(a).name)
 newargs=[str(NEW_SOURCE) if x==str(OLD_SOURCE) else str(NEW_BINARY) if x==str(OLD_BINARY) else x for x in args]
 hold(len(newargs)==len(args) and sum(x!=y for x,y in zip(args,newargs))==2,'COMPILE_ARGV_ONLY_TWO_PATHS_CHANGED')
 EVAL_ROOT.mkdir(parents=True,exist_ok=False)
 NEW_SOURCE.write_text(patched,encoding='utf-8')
 hold(sha(NEW_SOURCE)==PIN['new_source'],'WRITTEN_SOURCE_SHA')
 difflist=list(difflib.unified_diff(src.splitlines(True),patched.splitlines(True),fromfile='R86_PRESERVED_ORIGINAL',tofile='R91_10M_GUARD_ONLY'))
 hold(sum(x.startswith('-') and not x.startswith('---') for x in difflist)==1 and sum(x.startswith('+') and not x.startswith('+++') for x in difflist)==1,'DIFF_NOT_SINGLE_LINE')
 (EVAL_ROOT/'guard_one_line_only.diff').write_text(''.join(difflist),encoding='utf-8')
 atomic(EVAL_ROOT/'compile_command_pinned.json',{'old_manifest_sha256':PIN['old_manifest'],'argv':newargs,'original_sha256':PIN['old_source'],'new_source_sha256':PIN['new_source']})
 print(TAG+'_PREPARE_COMPILE_START_ONE_GUARD_SOURCE_H85_PIN',flush=True)
 started=time.perf_counter()
 rc=None;err=None
 try:
  with (EVAL_ROOT/'compile.stdout').open('x') as fo,(EVAL_ROOT/'compile.stderr').open('x') as fe:
   try:rc=subprocess.run(newargs,stdout=fo,stderr=fe,timeout=1200,check=False).returncode
   except subprocess.TimeoutExpired:rc=124;err='COMPILE_TIMEOUT'
 except Exception as e:
  rc=125;err=repr(e)
 t=time.perf_counter()-started
 receipt={'status':'R91_G1B_V2_EVAL_COMPILE_PASS' if rc==0 else 'R91_G1B_V2_EVAL_COMPILE_HOLD_PRESERVE',
          'compile_exit':rc,'error':err,'compile_seconds':t,'source_old_sha':PIN['old_source'],
          'source_new_sha':sha(NEW_SOURCE),'compile_manifest_original_sha':PIN['old_manifest'],
          'compile_command_new_sha':sha(EVAL_ROOT/'compile_command_pinned.json'),
          'source_diff_sha':sha(EVAL_ROOT/'guard_one_line_only.diff'),
          'compile_stdout_sha':sha(EVAL_ROOT/'compile.stdout') if regular(EVAL_ROOT/'compile.stdout') else None,
          'compile_stderr_sha':sha(EVAL_ROOT/'compile.stderr') if regular(EVAL_ROOT/'compile.stderr') else None,
          'compiled_elf_sha':sha(NEW_BINARY) if regular(NEW_BINARY) else None,
          'old_binary_sha':PIN['old_binary'],'no_original_write':True,'timestamp':time.time()}
 if rc==0:
  hold(regular(NEW_BINARY),'MISSING_BUILT_BINARY')
  hold(NEW_BINARY.open('rb').read(4)==b'\x7fELF','NOT_ELF')
  usage=subprocess.run([str(NEW_BINARY)],capture_output=True,text=True,timeout=10,check=False)
  receipt['usage_test_exit_code']=usage.returncode
  receipt['usage_test_stderr']=usage.stderr[:300]
  if usage.returncode != 2 or 'Usage:' not in usage.stderr:
   receipt['status']='R91_G1B_V2_EVAL_COMPILE_HOLD_PRESERVE';receipt['error']='USAGE_TEST_FAILED'
 atomic(NEW_BUILD,receipt)
 print(TAG+'_COMPILE_RECEIPT',NEW_BUILD,'sha256',sha(NEW_BUILD),flush=True)
 hold(receipt['status']=='R91_G1B_V2_EVAL_COMPILE_PASS','COMPILATION_OR_SMOKE_FAILED_INSPECT_OUTPUT')
 print(TAG+'_PREPARE_EVAL_10M_ONE_GUARD_COMPILE_PASS', 'ELF_SHA',receipt['compiled_elf_sha'],flush=True)

def eval_receipt():
 src,patched,_=read_original()
 r=read_json(NEW_BUILD)
 hold(r['status']=='R91_G1B_V2_EVAL_COMPILE_PASS' and r['compile_exit']==0 and r.get('usage_test_exit_code')==2,'EVAL_BUILD_NOT_PASS')
 hold(regular(NEW_SOURCE) and sha(NEW_SOURCE)==PIN['new_source'],'NEW_SRC_PIN')
 hold(regular(NEW_BINARY) and sha(NEW_BINARY)==r['compiled_elf_sha'],'NEW_ELF_PIN')
 hold(r['source_old_sha']==PIN['old_source'] and r['source_new_sha']==PIN['new_source'] and r['compile_manifest_original_sha']==PIN['old_manifest'],'EVAL_LINEAGE')
 hold(sha(EVAL_ROOT/'guard_one_line_only.diff')==r['source_diff_sha'],'GUARD_DIFF_PIN')
 return r

def fbin(p,n,d,bytes_per):
 with p.open('rb') as f: h=f.read(8)
 hold(len(h)==8 and struct.unpack('<II',h)==(n,d),'HEADER_'+p.name)
 hold(p.stat().st_size==8+n*d*bytes_per,'SIZE_'+p.name)

def ids():
 fbin(GT,100000,100,8)
 with GT.open('rb') as f:
  f.seek(8);left=10000000;low=10000000;hi=0
  while left:
   chunk=f.read(4*min(left,1<<18))
   hold(chunk and len(chunk)%4==0,'GT_ID_TRUNCATED')
   a=array('I');a.frombytes(chunk)
   if sys.byteorder!='little':a.byteswap()
   low=min(low,min(a));hi=max(hi,max(a));left-=len(a)
 hold(low==0 and hi==9999998,'GT_ID_BOUNDS_DRIFT')
 return {'count':10000000,'min_id':low,'max_id':hi}

def read_degrees_exact(f, n):
 """Read exactly n uint32 degrees, not one byte of adjacent neighbor IDs."""
 d=array('I')
 left=n
 while left:
  k=min(left,250000)
  part=f.read(k*4)
  hold(len(part)==k*4,'GRAPH_DEGREE_READ')
  d.frombytes(part)
  left-=k
 if sys.byteorder!='little':d.byteswap()
 hold(len(d)==n,'GRAPH_DEGREE_COUNT')
 return d

def graph_info():
 with GRAPH.open('rb') as f:
  hold(f.read(8)==struct.pack('<II',10000000,64),'GRAPH_HEADER')
  d=read_degrees_exact(f,10000000)
 hold(len(d)==10000000 and max(d)<=64 and sum(d)==540692297,'GRAPH_DEGREE_ARCS')
 hold(GRAPH.stat().st_size==2202769196,'GRAPH_TOTAL_BYTES')
 return {'nodes':10000000,'degree_cap':64,'arcs':540692297,'sha256':PIN['graph']}

def source_inputs():
 eval_receipt()
 for path,key in ((G1_JSON,'g1'),(G07_JSON,'g07'),(GRAPH,'graph'),(BASE,'base'),(QUERY,'query'),(GT,'gt'),(OLD_HOLD,'old_hold'),(OLD_PREF,'old_pre')):pin(path,key)
 j=read_json(G1_JSON)
 hold(j['status']=='NATIVE_1_OF_1_10M_BUILD_AND_FULL_GRAPH_STRUCTURE_PASS_NO_SWAP' and j['builder_exit_code']==0,'G1_STATUS')
 hold(j['graph_quality']['sha256']==PIN['graph'] and j['graph_quality']['arcs']==540692297 and j['graph_quality']['nodes']==10000000,'G1_GRAPH_LINK')
 for k in ('full_graph_invalid_id','full_graph_selfloops','full_graph_duplicate_neighbor_rows'):
  hold(j['graph_quality'][k]==0,'G1_INVALID_GRAPH_'+k)
 pre=read_json(G07_JSON)
 hold(pre['status']=='R91_G07_READONLY_PINNED_SOURCE_DATA_RESOURCES_PREFLIGHT_PASS__NO_10M_BUILD','G07_PIN')
 hold(pre['source']['highway_git_head']=='6bc2d47793bae9c521fb4150936669647700765d','H85_HEAD_DRIFT')
 hold(pre['data']['dataset_n']==10000000 and pre['data']['queries']==100000,'G07_COUNTS')
 fbin(BASE,10000000,100,4);fbin(QUERY,100000,100,4)
 gti=ids();g=graph_info()
 old=read_json(OLD_HOLD)
 hold(old['status']=='R91_G1B_SEARCH_HOLD_PRESERVE_ORPHAN_LOGS' and old['native_evaluator_exit']==3 and old['error']=='EVALUATOR_EXIT_3','OLD_HOLD_SOURCE')
 hold(shutil.which('taskset') is not None and Path('/usr/bin/time').is_file(),'TIME_TASKSET_MISSING')
 hold(0 in os.sched_getaffinity(0),'CPU0_NOT_AVAILABLE')
 disk=shutil.disk_usage(R91).free/1024**3
 mem_avail=next((int(a.split()[1]) for a in Path('/proc/meminfo').read_text().splitlines() if a.startswith('MemAvailable:')),0)
 hold(disk>=8,'DISK_BELOW_8GiB')
 hold(mem_avail>=10*1024*1024,'HOST_MEMAVAILABLE_BELOW_10GiB')
 return {'graph':g,'gt':gti,'compiled_eval_sha256':sha(NEW_BINARY),'orig_eval_sha256':PIN['old_binary'],'input_shas':{z:PIN[z] for z in ('base','query','gt','graph','g1','g07','old_hold','old_pre')},'beam_grid':list(BEAMS),'host_disk_free_GiB':disk,'host_memavailable_kib':mem_avail}

def cgroup(check=False):
 a=[line.split('::',1)[1] for line in Path('/proc/self/cgroup').read_text().splitlines() if line.startswith('0::')]
 hold(len(a)==1 and a[0].startswith('/user.slice/') and '..' not in a[0],'CGROUP_UNEXPECTED')
 p=Path('/sys/fs/cgroup')/a[0].lstrip('/')
 names=('memory.max','memory.swap.max','memory.swap.current','memory.current','memory.peak','memory.events')
 d={k:(p/k).read_text().strip() if (p/k).is_file() else None for k in names}
 if check:
  hold(d['memory.max']==str(HARD_CAP) and d['memory.swap.max']=='0','HARD_24GiB_NO_SWAP_MISSING')
  hold(d['memory.swap.current'] is not None and int(d['memory.swap.current'])==0,'SWAP_ALREADY_USED')
 return {'path':str(p),'metrics':d}

def events(s):
 d={}
 for ln in (s or '').splitlines():
  z=ln.split()
  if len(z)==2 and z[1].isdigit():d[z[0]]=int(z[1])
 return d

def preflight():
 hold(not PRE_ROOT.exists() and not OUT_ROOT.exists(),'PREF_OR_SEARCH_ROOT_EXISTS')
 x=source_inputs()
 PRE_ROOT.mkdir(parents=True,exist_ok=False)
 atomic(PRE_JSON,{'status':'R91_G1B_V2_PINNED_10M_NEW_ELF_PREFLIGHT_PASS_NO_SEARCH','script_sha256':sha(Path(__file__)),
                 'eval_build_sha256':sha(NEW_BUILD),'eval_bin_sha256':x['compiled_eval_sha256'],
                 'validated':x,'timestamp':time.time()})
 print(TAG+'_PREFLIGHT_PINNED_NEW_10M_ELF_GRAPH_100KGT_PASS_NO_SEARCH',flush=True)
 print(TAG+'_PREFLIGHT_REPORT',PRE_JSON,'sha256',sha(PRE_JSON),flush=True)

def parse(stdout):
 hold(stdout.count('R85_A1C_DYNAMIC_BEAMS count=4')==1,'BEAM_COUNT_MARKER')
 v=[s for s in stdout.splitlines() if s.startswith('R72_RECALL_INPUT_PASS ')]
 hold(len(v)==1 and re.search(r'\bgraph_nodes=10000000\b',v[0]) and re.search(r'\bqueries=100000\b',v[0]) and re.search(r'\bgt_k=100\b',v[0]),'10M_INPUT_MARKER')
 hold(stdout.count('R72_RECALL_EVAL_PASS')==1,'EVAL_END_MARKER')
 got={}
 for m in ROW.finditer(stdout):
  b=int(m.group(1))
  hold(b in BEAMS and b not in got,'ROW_WRONG_OR_DUPLICATE_BEAM')
  rec,qps,cmp,vis=(float(m.group(i)) for i in range(2,6))
  hold(math.isfinite(rec) and 0<=rec<=1 and math.isfinite(qps) and qps>0 and math.isfinite(vis) and vis>=0,'NONFINITE_METRICS')
  got[b]={'recall_at10':rec,'qps':qps,'avg_visited':vis,'avg_cmps_legacy_untrusted':None,
          'latency_inverse_qps_us_NOT_P95':1e6/qps,'meets_recall_0_99':rec>=.99,'meets_recall_0_998':rec>=.998}
 hold(tuple(got.keys())==BEAMS,'ROWS_MISSING_OR_ORDER')
 return {str(i):got[i] for i in BEAMS}

def run():
 c0=cgroup(True)
 hold(regular(PRE_JSON),'PRE_JSON_MISSING')
 pj=read_json(PRE_JSON)
 hold(pj['status']=='R91_G1B_V2_PINNED_10M_NEW_ELF_PREFLIGHT_PASS_NO_SEARCH' and pj['script_sha256']==sha(Path(__file__)) and pj['eval_build_sha256']==sha(NEW_BUILD),'PRE_JSON_SHA_OR_SCRIPT_DRIFT')
 hold(not OUT_ROOT.exists() and not OUT_ROOT.is_symlink(),'OUT_EXISTS_NO_RERUN')
 vals=source_inputs()
 hold(pj['eval_bin_sha256']==vals['compiled_eval_sha256'] and pj['validated']['input_shas']==vals['input_shas'] and pj['validated']['graph']==vals['graph'],'PREF_AND_SOURCE_DRIFT')
 OUT_ROOT.mkdir(parents=True,exist_ok=False)
 (OUT_ROOT/'logs').mkdir(exist_ok=False)
 out=OUT_ROOT/'logs/native_10m_search.stdout';err=OUT_ROOT/'logs/native_10m_search.stderr';times=OUT_ROOT/'logs/native_10m_search.time'
 cmd=['/usr/bin/time','-v','-o',str(times),'taskset','-c','0',str(NEW_BINARY),str(GRAPH),str(BASE),str(QUERY),str(GT),','.join(map(str,BEAMS))]
 atomic(OUT_ROOT/'preregister.json',{'script_sha256':sha(Path(__file__)),'preflight_sha256':sha(PRE_JSON),
  'build_receipt_sha256':sha(NEW_BUILD),'evaluator_sha256':vals['compiled_eval_sha256'],
  'evaluator_new_source_sha256':PIN['new_source'],'original_v4_sha256':PIN['old_binary'],
  'graph_sha256':PIN['graph'],'cmd':cmd,'beam_grid':list(BEAMS),'cgroup':c0,'no_graph_build':True,
  'limitations':['fixed beam only; not exact matched-Recall','Search throughput != perquery p95/p99',
                 'Do not use MS legacy avg_cmps counter','Stock 10M not yet built']})
 env=os.environ.copy()
 env.update(PARLAY_NUM_THREADS='1',OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='1',LC_ALL='C')
 print(TAG+'_ONE_GRAPH_SEARCH_START_BEAMS_'+','.join(map(str,BEAMS)),flush=True)
 begin=time.perf_counter();ret=None;error=None;results=None
 try:
  with out.open('x') as fo,err.open('x') as fe:
   try:ret=subprocess.run(cmd,stdout=fo,stderr=fe,env=env,timeout=5400,check=False).returncode
   except subprocess.TimeoutExpired:ret=-124;error='EVALUATOR_TIMEOUT_5400S'
  if ret==0:
   hold(err.stat().st_size==0,'EVALUATOR_STDERR_NONEMPTY')
   results=parse(out.read_text(errors='replace'))
   pin(GRAPH,'graph')
  elif error is None:error='EVALUATOR_EXIT_'+str(ret)
 except Exception as exc: error='RUN_EXCEPTION_'+repr(exc)
 elapsed=time.perf_counter()-begin
 c1=cgroup(False)
 ev0=events(c0['metrics']['memory.events']);ev1=events(c1['metrics']['memory.events'])
 delta={k:v-ev0.get(k,0) for k,v in ev1.items()}
 swap=int(c1['metrics']['memory.swap.current'] or 0)
 if swap!=0 or delta.get('oom',0) or delta.get('oom_kill',0):
  error='CGROUP_OOM_OR_SWAP '+str(error);results=None
 status='R91_G1B_V2_10M_SEARCH_NATIVE_FIXEDBEAM_PASS' if results is not None else 'R91_G1B_V2_SEARCH_HOLD_PRESERVE_LOGS'
 receipt={'status':status,'error':error,'evaluator_exit_code':ret,'elapsed_external_seconds':elapsed,
  'beam_grid':list(BEAMS),'nqueries':100000,'source_graph_sha256':PIN['graph'],'preflight_sha256':sha(PRE_JSON),
  'eval_build_receipt_sha256':sha(NEW_BUILD),'eval_binary_sha256':sha(NEW_BINARY),'metrics':results,
  'stdout_sha256':sha(out) if regular(out) else None,'stderr_sha256':sha(err) if regular(err) else None,
  'time_sha256':sha(times) if regular(times) else None,
  'cgroup_peak_bytes':int(c1['metrics']['memory.peak'] or 0),'cgroup_events_delta':delta,
  'cgroup_swap_after':swap,'cgroup_path':c1['path'],
  'no_build':True,'stock10m_unrun':True,'timestamp':time.time()}
 atomic(SEARCH_REPORT,receipt)
 print(TAG+'_SEARCH_RESULT',status,'exit',ret,'sha256',sha(SEARCH_REPORT),flush=True)
 hold(results is not None,'NATIVE_SEARCH_HOLD_PRESERVE_OUTPUT')

def audit():
 pj=read_json(PRE_JSON);x=read_json(SEARCH_REPORT);p=read_json(OUT_ROOT/'preregister.json')
 hold(x['status']=='R91_G1B_V2_10M_SEARCH_NATIVE_FIXEDBEAM_PASS' and x['evaluator_exit_code']==0,'NATIVE_RUN_NOT_PASS')
 hold(x['preflight_sha256']==sha(PRE_JSON) and p['preflight_sha256']==sha(PRE_JSON) and p['script_sha256']==sha(Path(__file__)),'SOURCE_RECEIPTS_DRIFT')
 hold(x['eval_build_receipt_sha256']==sha(NEW_BUILD) and x['eval_binary_sha256']==sha(NEW_BINARY),'EVAL_SOURCE_DRIFT')
 hold(x['beam_grid']==list(BEAMS) and x['stock10m_unrun'] and x['no_build'],'PROTOCOL_DRIFT')
 out=OUT_ROOT/'logs/native_10m_search.stdout';err=OUT_ROOT/'logs/native_10m_search.stderr';t=OUT_ROOT/'logs/native_10m_search.time'
 hold(all(regular(z) for z in (out,err,t)),'MISSING_NATIVE_LOGS')
 hold(sha(out)==x['stdout_sha256'] and sha(err)==x['stderr_sha256'] and sha(t)==x['time_sha256'],'NATIVE_LOG_SHA_DRIFT')
 hold(parse(out.read_text(errors='replace'))==x['metrics'],'REPARSE_DISAGREEMENT')
 hold(x['cgroup_swap_after']==0 and x['cgroup_events_delta'].get('oom_kill',-1)==0 and x['cgroup_events_delta'].get('oom',-1)==0,'RESOURCE_FAIL')
 pin(GRAPH,'graph')
 print(TAG+'_AUDIT_PASS_FROZEN_10M_GRAPH_FOUR_BEAMS_SEARCH_ONLY',flush=True)
 print(TAG+'_FINAL_SUMMARY',SEARCH_REPORT,'sha256',sha(SEARCH_REPORT),flush=True)
 for b,values in x['metrics'].items():
  print(TAG+'_BEAM',b,'RECALL',values['recall_at10'],'QPS',values['qps'],
        'QUALIFIES_099',values['meets_recall_0_99'],'QUALIFIES_0998',values['meets_recall_0_998'],flush=True)
 print(TAG+'_NOTE_STOCK_10M_NOT_BUILT_NOT_EXACT_MATCHED_RECALL',flush=True)

def selftest():
 hold(all(len(v)==64 and set(v)<=set('0123456789abcdef') for v in PIN.values()),'SHA_CONSTANTS')
 fixture='if (base.size() != 1000000 || base.dimension() != 100 ||\n x)'
 patch=source_patch(fixture)
 hold(patch.count('base.size() != 10000000')==1 and len(patch)==len(fixture)+1,'GUARD_TEST')
 for bad in ('base.size() != 1000000 ||','a'+fixture+fixture):
  try:source_patch(bad)
  except RuntimeError:pass
  else:raise AssertionError('BAD_GUARD_ACCEPTED')
 s='R85_A1C_DYNAMIC_BEAMS count=4\nR72_RECALL_INPUT_PASS graph_nodes=10000000 queries=100000 gt_k=100\n'+''.join(
     f'R72_RECALL_ROW beam={b} recall={rec:.8f} qps=123.456 avg_cmps=4294967295 avg_visited=200\n'
     for b,rec in ((384,.9879),(896,.9965),(1024,.99801),(1536,.9988)))+'R72_RECALL_EVAL_PASS\n'
 parsed=parse(s)
 hold(len(parsed)==4 and not parsed['384']['meets_recall_0_99'] and parsed['1024']['meets_recall_0_998'],'RECALL_TARGET_SELFTEST')
 for bad in (s.replace('graph_nodes=10000000','graph_nodes=1000000'),s.replace('R72_RECALL_EVAL_PASS',''),s.replace('recall=0.98790000','recall=nan'),s.replace('beam=1536','beam=896')):
  try:parse(bad)
  except RuntimeError:pass
  else:raise AssertionError('BAD_OUTPUT_ACCEPTED')
 import io
 fixture_degree=io.BytesIO(struct.pack('<3I',1,2,0)+struct.pack('<2I',91,92))
 loaded=read_degrees_exact(fixture_degree,3)
 hold(list(loaded)==[1,2,0] and fixture_degree.read(4)==struct.pack('<I',91),
      'GRAPH_DEGREE_NOT_EXACTLY_N_WORDS')
 hold(events('max 345\noom 0\noom_kill 0\n')['max']==345,'EVENT_PARSE')
 print(TAG+'_SELFTEST_PASS_EXACT_SOURCE_GUARD_PARSER_FALSE_TARGETS_CGROUP_NO_BUILD',flush=True)

def main():
 a=argparse.ArgumentParser();a.add_argument('phase',choices=('selftest','prepare','scope-check','preflight','run','audit'))
 phase=a.parse_args().phase
 try:
  if phase=='selftest':selftest()
  elif phase=='prepare':prepare()
  elif phase=='scope-check':
   c=cgroup(True);print(TAG+'_24GiB_NO_SWAP_CGROUP_PASS',c['path'],flush=True)
  elif phase=='preflight':preflight()
  elif phase=='run':run()
  else:audit()
 except Exception as exc:
  print(TAG+'_ERROR',repr(exc),file=sys.stderr,flush=True)
  sys.exit(2)
if __name__=='__main__':main()
