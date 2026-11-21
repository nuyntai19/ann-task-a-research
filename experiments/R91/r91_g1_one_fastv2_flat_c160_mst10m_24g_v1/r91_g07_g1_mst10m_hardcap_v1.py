#!/usr/bin/env python3
"""R91 G0.7 / G1: ONE MS-Turing10M Fast v2 OFF 4CPU Flat C160 hard-capped pilot.

G0.7 'preflight' is read-only on all historical artifacts and writes ONE NEW
receipt directory under R91 only. 'build-inscope' is meant to be launched by
systemd-run --user --scope -p MemoryMax=24G -p MemorySwapMax=0. It refuses to
start unless both real cgroup v2 kernel files show the exact limits. The
builder is the existing six-ELF v1.3 historical H85 fast_off (NO rebuild).
No retries, no fallback to swap, no modification of R85/R90 outputs.
"""
from __future__ import annotations
import argparse, hashlib, importlib.util, json, os, re, shutil, signal, struct, subprocess, sys, time
from pathlib import Path

TAG='R91_G07_G1_MST10M_HARDCAP_V1'
H=Path.home(); ROOT=H/'ann-task-a'; R90=ROOT/'experiments/R90'; R91=ROOT/'experiments/R91'
ORIG=R90/'r90_p0a_v13_historical_highway_6bc2_controlled_v1'
MATRIX=R90/'r90_p0a_v13_h85_24build_native_v1'
DATA=ROOT/'data/MSTuring_10M_v1'
BASE=DATA/'base.10M.fbin';QUERY=DATA/'query.public.100K.fbin';GT=DATA/'groundtruth.public.100K.ibin'
V11_PY=H/'Downloads/r90_p0a_unified_1m_three_arm_v1_1.py'
PREF=R91/'r91_g07_mst10m_flat_c160_preflight_v1'
OUT=R91/'r91_g1_one_fastv2_flat_c160_mst10m_24g_v1'
BIN=ORIG/'build/fast_off/algorithms/PipNN/neighbors-pipnn_FLOAT_T_EUCLIDEAN'
SOURCE=ORIG/'source/fast_off'
H85='6bc2d47793bae9c521fb4150936669647700765d'
LIMIT=24*1024**3
DATA_SHAS={
 'base':'e7756f6b54a07e8af171c7644ce2e1be6d7053ee2a2c30c4b02f99e85984b700',
 'query':'48d087a17bec15a5ec9ea526fe9bd14ac31bbbb5cd200817b341adbb77695644',
 'gt':'77b558bd3b77e4cc1149384996b953b040e412477eb0df9889718fc13e17aff2'}
PIN={
 'v11py':'fa9cdc09b3f447161f5c1f65382b15a0bc9645f425a679b73ca26f5ce8abecf0',
 'source_manifest':'5f42250caa47659daf978a73355857e355cc86096571d327518e676d41f1423b',
 'stageA':'58406df0aaa4813a8562623726a627e133efdf08ddb2eaec1c5501f6157e230a',
 'stageB':'5827a3f5e52d552521cd4f64ce42324a0f13d6549be5cb37e5f2e987fdf9f785',
 'compiled_manifest':'48531781fbcd89f1e7256f2fa8a85d26f28098dc21447f9891988d6312400675',
 'compile_provenance':'81dd161594fb92c8dc3c8bea54c004afdbdc6f7ba71d8ed5b187ecd01d64d89e',
 'build_audit':'9550858dcb763349ed5180b3b65577e48a600e54becc0ecb9c755970a4d4bbfb',
 'build_manifest':'0c76f3e5bc3dc0d82f70aa1aadac9b26c5b0e8f4607f31d9aa6d8b0b0a4121c3',
 'fast_off_elf':'fcfb16d0ca2b498f94db8383dfc311c2e7ba88cb3036281accd5f30c6d876793',
 'compiler':'1353e9bdd29a7295c7226bf6c63abccce056d8cac31f112e5cdbecc3f28c2769',
 'fast_off_commands':'0530321bbcb14f60a4c4db136207f03eeb452794233ed136b978b63dae69f20a'}
FLAGS_EXPECTED=['-num_clusters','2','-cluster_size','1024','-table_size','160','-top_level_leaders','100',
 '-fanout_scheme','10,3,1','-mst_deg','2','-prune','1','-prune_all','1',
 '-prune_degree','64','-hash_bits','12','-alpha','1.1','-k','0']

def must(v,msg):
 if not v:raise RuntimeError(TAG+'_HOLD_'+msg)
def regular(p):return Path(p).is_file() and not Path(p).is_symlink()
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(8<<20),b''):h.update(b)
 return h.hexdigest()
def json_pin(path,expected,label):
 must(regular(path),'MISSING_OR_SYMLINK_'+label)
 must(sha(path)==expected,'PIN_SHA_'+label)
 return json.loads(path.read_text())
def file_pin(path,wanted,label):
 must(regular(path) and sha(path)==wanted,'FILE_SHA_'+label)
def fbin_pin(path,n,d,label):
 file_pin(path,DATA_SHAS[label],label)
 with path.open('rb') as f:hdr=f.read(8)
 must(hdr==struct.pack('<II',n,d),'FBIN_HEADER_'+label)
 must(path.stat().st_size==8+4*n*d,'FBIN_EXACT_SIZE_'+label)
def gt_pin():
 file_pin(GT,DATA_SHAS['gt'],'gt')
 with GT.open('rb') as f:hdr=f.read(8)
 must(hdr==struct.pack('<II',100000,100),'GT_DUAL_ARRAY_HEADER')
 must(GT.stat().st_size==8+8*100000*100,'GT_DUAL_ARRAY_EXACT_SIZE')
 # GT layout: all ID uint32s first, then all distance float32s.
 from array import array
 count=0;mini=10_000_000;maxi=-1
 with GT.open('rb') as f:
  f.seek(8)
  while count<10_000_000:
   raw=f.read(4*min(1<<18,10_000_000-count))
   must(len(raw)%4==0 and raw,'GT_ID_CHUNK')
   a=array('I');a.frombytes(raw)
   if sys.byteorder!='little':a.byteswap()
   mini=min(mini,min(a));maxi=max(maxi,max(a));count+=len(a)
 must(count==10_000_000 and mini>=0 and maxi<10_000_000,'GT_ID_RANGE')
 return {'min_id':mini,'max_id':maxi,'count':count}
def js(p):
 must(regular(p),'MISSING_RECEIPT_'+p.name)
 return json.loads(p.read_text())
def src_module():
 file_pin(V11_PY,PIN['v11py'],'ORIG_V11_PY')
 spec=importlib.util.spec_from_file_location('r91_frozen_v11',V11_PY)
 must(spec is not None and spec.loader is not None,'PY_SPEC')
 mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
 must(list(mod.FLAGS)==FLAGS_EXPECTED,'PIN_NATIVE_BUILD_FLAGS')
 return mod

def cgroup_info(required=False):
 content=Path('/proc/self/cgroup').read_text()
 line=next((x for x in content.splitlines() if x.startswith('0::')),None)
 must(line is not None,'NOT_UNIFIED_CGROUP_V2')
 relative=line.split('::',1)[1]
 must(relative not in ('','/') and '..' not in Path(relative).parts,'CGROUP_SCOPE_NOT_ISOLATED')
 root=Path('/sys/fs/cgroup')/relative.lstrip('/')
 vals={}
 for name in ('memory.max','memory.swap.max','memory.current','memory.swap.current','memory.peak','memory.events','memory.oom.group','memory.pressure'):
  p=root/name
  vals[name]=p.read_text().strip() if regular(p) else None
 if required:
  must(vals['memory.max']==str(LIMIT),'CGROUP_MEMORY_MAX_24G_NOT_ACTIVE')
  must(vals['memory.swap.max']=='0','CGROUP_SWAP_MAX_0_NOT_ACTIVE')
  must(vals['memory.swap.current'] is not None and int(vals['memory.swap.current'])==0,'CGROUP_SWAP_IN_USE_AT_START')
 return {'relative':relative,'root':str(root),'files':vals}
def events_map(raw):
 d={}
 if raw:
  for s in raw.splitlines():
   z=s.split()
   if len(z)==2:
    try:d[z[0]]=int(z[1])
    except ValueError:pass
 return d
def free_gib(p=R91):return shutil.disk_usage(p).free/1024**3
def mem_available_kib():
 m=re.search(r'^MemAvailable:\s+(\d+)\s+kB',Path('/proc/meminfo').read_text(),re.M)
 must(m is not None,'MEMAVAILABLE_ABSENT')
 return int(m.group(1))
def host_vmstat():
 d={}
 for s in Path('/proc/vmstat').read_text().splitlines():
  z=s.split()
  if len(z)==2 and z[0] in ('pswpin','pswpout','pgmajfault'):
   d[z[0]]=int(z[1])
 return d
def df_h():
 p=subprocess.run(['df','-h',str(R91)],capture_output=True,text=True,check=False)
 return (p.stdout+p.stderr).strip()
def concurrent_builds():
 me=os.getpid();rows=[]
 for p in Path('/proc').iterdir():
  if not p.name.isdigit() or int(p.name)==me:continue
  try:
   command=(p/'cmdline').read_bytes()
   if b'neighbors-pipnn_FLOAT_T_EUCLIDEAN' in command:rows.append(p.name)
  except (OSError,PermissionError):pass
 return rows

def verify_source():
 must(not OUT.exists() and not OUT.is_symlink(),'G1_OUTPUT_ROOT_EXISTS_PRESERVE')
 mod=src_module()
 audit=json_pin(MATRIX/'audit1m_buildonly.json',PIN['build_audit'],'AUDIT1M')
 full=json_pin(MATRIX/'full1m_manifest.json',PIN['build_manifest'],'FULL1M')
 sr=json_pin(ORIG/'source_manifest.json',PIN['source_manifest'],'V13_SOURCE')
 st=json_pin(ORIG/'stageA_audit.json',PIN['stageA'],'STAGEA')
 b=json_pin(ORIG/'stageB_stock_sift1m_quality.json',PIN['stageB'],'STAGEB')
 cm=json_pin(ORIG/'compile_manifest.json',PIN['compiled_manifest'],'COMPILER_MANIFEST')
 cp=json_pin(ORIG/'compile_provenance_audit.json',PIN['compile_provenance'],'COMPILE_PROVENANCE')
 must(audit['Highway_commit']==st['highway_commit_full']==b['h85_commit']==H85,'H85_PIN')
 must(audit['full_manifest_sha256']==PIN['build_manifest'] and len(full['runs'])==24,'R90_24_BUILD_LINK')
 must(cm['binaries']['fast_off']==PIN['fast_off_elf']==cp['per_arm']['fast_off']['elf_sha256'],'ELF_RECORDED_SHA')
 must(cp['six_binary_compiler_sha256']==cm['compiler_sha256']==PIN['compiler'],'COMPILER_PIN')
 must(regular(cm['cxx_binary']) and sha(cm['cxx_binary'])==PIN['compiler'],'COMPILER_ELF_SHA')
 file_pin(BIN,PIN['fast_off_elf'],'FAST_OFF_H85_ELF')
 v=next((x for x in sr['variants'] if x['variant']=='fast_off'),None)
 must(v is not None and mod.digest_tree(SOURCE)==v['tree_sha256'],'FAST_OFF_TREE_SHA')
 commands=ORIG/'build/fast_off/compile_commands.json'
 file_pin(commands,PIN['fast_off_commands'],'FAST_OFF_COMPILE_COMMANDS')
 cc=commands.read_text(errors='replace')
 must(not re.search(r'(?:^|[\s\"\'])-DR70_TWO_TIER(?:[=\s\"\']|$)',cc),'FLAT_FLAG_HAS_TWO_TIER')
 must('-ffast-math' in cc,'ORIGINAL_FAST_MATH_MISSING')
 must(not concurrent_builds(),'ANOTHER_PINNED_BUILD_RUNNING')
 must(set((0,2,4,6)).issubset(os.sched_getaffinity(0)),'CPU_AFFINITY_NOT_ALL_AVAILABLE')
 for key in ('taskset','df'):
  must(shutil.which(key) is not None,'MISSING_EXECUTABLE_'+key)
 must(Path('/usr/bin/time').is_file(),'GNU_TIME_MISSING')
 import numpy
 must(hasattr(numpy,'memmap'),'NUMPY_REQUIRED_FOR_FULL_GRAPH_AUDIT')
 return {'fast_off_tree_sha256':v['tree_sha256'],'compile_commands_sha256':PIN['fast_off_commands'],
         'fast_off_elf_sha256':PIN['fast_off_elf'],'highway_git_head':H85,
         'canonical_flags':list(mod.FLAGS),'python_version':sys.version.split()[0],
         'numpy_version':numpy.__version__}
def verify_data():
 fbin_pin(BASE,10_000_000,100,'base')
 fbin_pin(QUERY,100_000,100,'query')
 gt=gt_pin()
 return {'base_sha256':DATA_SHAS['base'],'query_sha256':DATA_SHAS['query'],'gt_sha256':DATA_SHAS['gt'],
         'dataset_n':10_000_000,'dimension':100,'queries':100_000,'gt_k':100,'gt_id_bounds':gt}
def verify_resources(strict=True):
 R91.mkdir(parents=True,exist_ok=True)
 available=mem_available_kib();disk=free_gib()
 if strict:
  must(available>=int(25.5*1024**2),'HOST_MEMAVAILABLE_BELOW_25_5_GIB')
  must(disk>=15,'DISK_AVAILABLE_BELOW_15_GIB')
 return {'memavailable_kib':available,'memavailable_GiB':available/1024**2,
         'disk_available_GiB':disk,'df_h':df_h(),
         'host_vmstat':host_vmstat()}
def atomic_json(path,data):
 path=Path(path);must(not path.exists() and not path.is_symlink(),'OUTPUT_EXISTS_'+path.name)
 tmp=path.with_suffix(path.suffix+'.part');must(not tmp.exists(),'PART_ALREADY_EXISTS')
 with tmp.open('x') as f:
  json.dump(data,f,indent=2,sort_keys=True);f.write('\n');f.flush();os.fsync(f.fileno())
 os.replace(tmp,path)

def preflight():
 must(not PREF.exists() and not PREF.is_symlink(),'G07_RECEIPT_ALREADY_EXISTS_PRESERVE')
 info=verify_source();data=verify_data();res=verify_resources()
 report={'status':'R91_G07_READONLY_PINNED_SOURCE_DATA_RESOURCES_PREFLIGHT_PASS__NO_10M_BUILD',
         'runner_sha256':sha(Path(__file__)),'source':info,'data':data,'resources':res,
         'cgroup_dry_run_user_terminal':'kernel user scope memory.max=25769803776 swap.max=0, G1 scope still must recheck both',
         'scope_limit_bytes':LIMIT,'swap_max_bytes':0,'single_build_only':True,
         'output_root_strictly_new':str(OUT),'no_legacy_source_or_graph_write':True}
 PREF.mkdir(parents=True,exist_ok=False)
 p=PREF/'r91_g07_preflight.json';atomic_json(p,report)
 print(TAG+'_PREFLIGHT_PASS_SOURCE_ELF_3_DATA_SHA_GT_ID_HOST_CPU_DISK__NO_10M_BUILD',flush=True)
 print(TAG+'_PREFLIGHT_REPORT',p,'sha256',sha(p),flush=True)

def selftest():
 assert len(FLAGS_EXPECTED)==24
 for z in list(PIN.values())+list(DATA_SHAS.values()):must(len(z)==64 and all(ch in '0123456789abcdef' for ch in z),'SELFTEST_SHA_64HEX')
 must(LIMIT==25769803776,'SELFTEST_CGROUP_LIMIT')
 with __import__('tempfile').TemporaryDirectory() as temp:
  p=Path(temp)/'t.fbin';p.write_bytes(struct.pack('<II',2,3)+b'\0'*24)
  must(p.stat().st_size==8+4*2*3,'SELFTEST_FBIN_LENGTH')
  bad=p.with_name('bad');bad.write_bytes(b'\0'*7)
  must(len(bad.read_bytes())!=8,'SELFTEST_BAD_LENGTH')
  e=events_map('low 0\nhigh 1\nmax 2\noom 3\noom_kill 4\n')
  must(e['oom_kill']==4 and e['max']==2,'SELFTEST_EVENTS')
  good=Path(temp)/'g.graph'
  # n4, deg [2,1,0,1], arcs [1,2, 0, 2]
  good.write_bytes(struct.pack('<II4I4I',4,64,2,1,0,1,1,2,0,2))
  x=audit_graph(good,4)
  must(x['nodes']==4 and x['arcs']==4 and x['full_graph_duplicate_neighbor_rows']==0,'SELFTEST_GRAPH_GOOD')
  badgraph=Path(temp)/'bad.graph'
  badgraph.write_bytes(struct.pack('<II4I4I',4,64,2,1,0,1,1,1,0,2))
  try:audit_graph(badgraph,4)
  except RuntimeError as exc:must('GRAPH_DUPLICATE_OR_SELFLOOP' in str(exc),'SELFTEST_GRAPH_DUP_ERROR')
  else:must(False,'SELFTEST_GRAPH_DUP_ACCEPTED')
  badgraph.write_bytes(struct.pack('<II4I4I',4,64,2,1,0,1,1,4,0,2))
  try:audit_graph(badgraph,4)
  except RuntimeError as exc:must('GRAPH_INVALID_ID' in str(exc),'SELFTEST_GRAPH_INVALID_ERROR')
  else:must(False,'SELFTEST_GRAPH_INVALID_ACCEPTED')
 print(TAG+'_SELFTEST_PASS_64HEX_H85_FLAT_FLAGS_LIMIT_GT_SOURCE_EVENTS_GRAPH_FIXTURES_NO_BUILD',flush=True)

def audit_graph(g,n=10_000_000):
 import numpy as np
 must(regular(g),'GRAPH_MISSING')
 with g.open('rb') as f:hdr=f.read(8)
 must(hdr==struct.pack('<II',n,64),'GRAPH_HEADER_N_DEG64')
 md=64
 deg=np.memmap(g,mode='r',dtype='<u4',offset=8,shape=(n,))
 must(bool(np.all(deg<=md)),'GRAPH_DEGREE_OUT_OF_RANGE')
 arc=int(np.sum(deg,dtype=np.uint64))
 must(arc>0 and g.stat().st_size==8+4*n+4*arc,'GRAPH_EXACT_FILE_BYTES')
 edges=np.memmap(g,mode='r',dtype='<u4',offset=8+4*n,shape=(arc,))
 must(bool(np.all(edges<n)),'GRAPH_INVALID_ID')
 offsets=np.empty(n+1,dtype=np.uint64);offsets[0]=0
 np.cumsum(deg,dtype=np.uint64,out=offsets[1:])
 duplicates=0;selfloops=0
 for lo in range(0,n,4096):
  hi=min(lo+4096,n);aa=int(offsets[lo]);bb=int(offsets[hi]);cnt=deg[lo:hi]
  if bb==aa:continue
  owners=np.repeat(np.arange(lo,hi,dtype=np.uint32),cnt.astype(np.int64))
  portion=edges[aa:bb]
  selfloops+=int(np.sum(owners==portion))
  starts=offsets[lo:hi]-np.uint64(aa)
  colid=np.arange(bb-aa,dtype=np.int64)-np.repeat(starts.astype(np.int64),cnt.astype(np.int64))
  rows=np.full((hi-lo,md),np.uint32(0xffffffff),dtype=np.uint32)
  rows[owners.astype(np.int64)-lo,colid]=portion
  rows.sort(axis=1)
  duplicates+=int(np.sum(np.any((rows[:,1:]==rows[:,:-1])&(rows[:,:-1]!=np.uint32(0xffffffff)),axis=1)))
  must(selfloops==0 and duplicates==0,'GRAPH_DUPLICATE_OR_SELFLOOP')
 return {'nodes':n,'degree_cap':md,'arcs':arc,'bytes':g.stat().st_size,
         'sha256':sha(g),'full_graph_invalid_id':0,'full_graph_selfloops':selfloops,
         'full_graph_duplicate_neighbor_rows':duplicates,'full_audit_all_vertices':True}
def parse_time(p):
 if not regular(p):return None
 txt=p.read_text(errors='replace')
 def get(s):
  m=re.search(r'^\s*'+re.escape(s)+r':\s*([0-9:.]+)',txt,re.M)
  return m.group(1) if m else None
 w=get('Elapsed (wall clock) time (h:mm:ss or m:ss)')
 wall=None
 if w:
  try:
   x=list(map(float,w.split(':')));wall=sum(z*60**i for i,z in enumerate(reversed(x)))
  except ValueError:pass
 return {'wall_seconds':wall,'max_RSS_KiB':int(get('Maximum resident set size (kbytes)') or 0),
         'major_page_faults':int(get('Major (requiring I/O) page faults') or 0),
         'minor_page_faults':int(get('Minor (reclaiming a frame) page faults') or 0),
         'swaps_time_counter':int(get('Swaps') or 0), 'exit_status_time':get('Exit status')}
def parse_stage(p):
 if not regular(p):return None
 txt=p.read_text(errors='replace')
 ret={}
 for name,phrase,count in [('buckets','buckets time',2),('leaf','build leaf time',2),('prune','Final prune time',1)]:
  vals=[]
  for line in txt.splitlines():
   if phrase.lower() not in line.lower():continue
   m=re.search(re.escape(phrase)+r'\s*[:=]?\s*([0-9]+(?:\.[0-9]+)?)',line,re.I)
   if not m:m=re.search(r'([0-9]+(?:\.[0-9]+)?)\s*(?:s\s*)?'+re.escape(phrase),line,re.I)
   if m:vals.append(float(m.group(1)))
  ret[name+'_per_pass_seconds']=vals
  ret[name+'_total_seconds']=sum(vals) if len(vals)==count else None
  ret[name+'_expected_line_count']=count
  ret[name+'_actual_line_count']=len(vals)
 ret['bucket_counts']=[int(x) for x in re.findall(r'^\s*Total buckets:\s*(\d+)\s*$',txt,re.M)]
 ret['clustering_comparisons_cumulative']=[int(x) for x in re.findall(r'^\s*# of comparisons during clustering:\s*(\d+)\s*$',txt,re.M)]
 return ret

def build_inscope():
 # These source/data checks precede every filesystem write and are repeated in the actual scope.
 must(regular(PREF/'r91_g07_preflight.json'),'MISSING_G07_PREFLIGHT_RUN_G07_FIRST')
 pre=js(PREF/'r91_g07_preflight.json')
 must(pre['status'].endswith('__NO_10M_BUILD') and pre['runner_sha256']==sha(Path(__file__)),'G07_RECEIPT_DRIFT')
 cg0=cgroup_info(required=True)
 info=verify_source();data=verify_data();res=verify_resources()
 must(info['fast_off_elf_sha256']==pre['source']['fast_off_elf_sha256'] and data==pre['data'],'SOURCE_DATA_DRIFT')
 must(not OUT.exists() and not OUT.is_symlink(),'BUILD_OUTPUT_EXISTS')
 OUT.mkdir(parents=True,exist_ok=False)
 (OUT/'logs').mkdir(exist_ok=False);(OUT/'graphs').mkdir(exist_ok=False)
 # Outside-scope watcher can capture the cgroup peak/events even if OOM kills
 # every task within the transient scope before our in-scope finally runs.
 with (OUT/'cgroup_scope_path.txt').open('x') as f:
  f.write(cg0['root']+'\n');f.flush();os.fsync(f.fileno())
 g=OUT/'graphs/MSTuring10M_fast_off_C160_K1024_N2.graph'
 out=OUT/'logs/MSTuring10M_fast_off_C160_K1024_N2.stdout'
 timefile=OUT/'logs/MSTuring10M_fast_off_C160_K1024_N2.time'
 source={'preflight_sha256':sha(PREF/'r91_g07_preflight.json'),'runner_sha256':sha(Path(__file__)),
         'scope_kernel_before':cg0,'source':info,'data':data,'resources_before':res,
         'df_before':df_h(),'vmstat_before':host_vmstat(),
         'cmd':['/usr/bin/time','-v','-o',str(timefile),'taskset','-c','0,2,4,6',str(BIN),'-base_path',str(BASE),'-graph_outfile',str(g),*FLAGS_EXPECTED],
         'env':{'PARLAY_NUM_THREADS':'4','OMP_NUM_THREADS':'4','LC_ALL':'C'}}
 atomic_json(OUT/'pilot_preregister.json',source)
 env=dict(os.environ);env.update(source['env'])
 before=events_map(cg0['files']['memory.events']);root=Path(cg0['root'])
 monitor={'sample_count':0,'peak_memory_current':0,'peak_swap_current':0,
          'min_host_memavailable_kib':mem_available_kib(),'min_disk_free_GiB':free_gib(),
          'pressure_abort':False,'disk_abort':False,'oom_kill_observed':False,'max_event_increase':0}
 proc=None;rc=None;error=None;graph_status=None
 print(TAG+'_SINGLE10M_BUILD_START_PINNED_H85_FAST_OFF_FLAT_C160_4CPU_HARD24G_NO_SWAP',flush=True)
 try:
  with out.open('x') as fd:
   proc=subprocess.Popen(source['cmd'],env=env,stdout=fd,stderr=subprocess.STDOUT,start_new_session=True)
   lowmem_consecutive=0
   while True:
    status=proc.poll()
    cg=cgroup_info(required=False);v=cg['files']
    cur=int(v['memory.current'] or 0);sw=int(v['memory.swap.current'] or 0)
    monitor['sample_count']+=1
    monitor['peak_memory_current']=max(monitor['peak_memory_current'],cur)
    monitor['peak_swap_current']=max(monitor['peak_swap_current'],sw)
    available=mem_available_kib();monitor['min_host_memavailable_kib']=min(monitor['min_host_memavailable_kib'],available)
    disk=free_gib();monitor['min_disk_free_GiB']=min(monitor['min_disk_free_GiB'],disk)
    ev=events_map(v['memory.events']);monitor['oom_kill_observed']|=ev.get('oom_kill',0)>before.get('oom_kill',0)
    monitor['max_event_increase']=max(monitor['max_event_increase'],ev.get('max',0)-before.get('max',0))
    if status is not None:rc=status;break
    lowmem_consecutive=lowmem_consecutive+1 if available <int(1.5*1024**2) else 0
    if lowmem_consecutive>=2 or disk<8 or sw>0:
     monitor['pressure_abort']=lowmem_consecutive>=2 or sw>0
     monitor['disk_abort']=disk<8
     print(TAG+'_HOST_RESOURCE_ABORT','avail_kib',available,'freeGiB',round(disk,3),'swap_cur',sw,flush=True)
     os.killpg(proc.pid,signal.SIGTERM)
     try:proc.wait(timeout=5)
     except subprocess.TimeoutExpired:
      os.killpg(proc.pid,signal.SIGKILL);proc.wait(timeout=10)
     rc=proc.returncode;break
    time.sleep(1.0)
  if rc==0:
   graph_status=audit_graph(g)
  else:error='NATIVE_BUILDER_NONZERO_EXIT_'+str(rc)
 except Exception as e:
  error='WRAPPER_MONITOR_OR_AUDIT_EXCEPTION_'+repr(e)
  if proc is not None and proc.poll() is None:
   try:os.killpg(proc.pid,signal.SIGTERM);proc.wait(timeout=5)
   except Exception:
    try:os.killpg(proc.pid,signal.SIGKILL);proc.wait(timeout=10)
    except Exception:pass
  if proc is not None:rc=proc.returncode
 finally:
  cg1=cgroup_info(required=False)
  e1=events_map(cg1['files']['memory.events'])
  monitor.update({'builder_exit_code':rc,'source_cgroup_peak_bytes':int(cg1['files']['memory.peak'] or 0),
     'source_cgroup_swap_after_bytes':int(cg1['files']['memory.swap.current'] or 0),
     'cgroup_events_before':before,'cgroup_events_after':e1,
     'cgroup_events_delta':{k:v-before.get(k,0) for k,v in e1.items()},
     'vmstat_after':host_vmstat(),'df_after':df_h(),'disk_free_after_GiB':free_gib(),
     'time_metrics':parse_time(timefile),'stage_metrics':parse_stage(out),
     'stdout_sha256':sha(out) if regular(out) else None,
     'timefile_sha256':sha(timefile) if regular(timefile) else None,
     'graph_quality':graph_status,'error':error})
  passed=rc==0 and graph_status is not None and not monitor['oom_kill_observed'] and monitor['peak_swap_current']==0 and monitor['source_cgroup_swap_after_bytes']==0 and not monitor['pressure_abort'] and not monitor['disk_abort']
  monitor['status']='NATIVE_1_OF_1_10M_BUILD_AND_FULL_GRAPH_STRUCTURE_PASS_NO_SWAP' if passed else 'NATIVE_10M_SINGLE_PILOT_HOLD_PRESERVE_ORPHAN_AND_EVIDENCE'
  atomic_json(OUT/'r91_g1_single10m_result.json',monitor)
  print(TAG+'_RESULT',monitor['status'],'rc',rc,'peakGiB',round(monitor['source_cgroup_peak_bytes']/1024**3,4),'oom_kill_delta',monitor['cgroup_events_delta'].get('oom_kill'),'max_swap_bytes',monitor['peak_swap_current'],flush=True)
  print(TAG+'_MANIFEST',OUT/'r91_g1_single10m_result.json','sha256',sha(OUT/'r91_g1_single10m_result.json'),flush=True)
  must(passed,'BUILD_NOT_CERTIFIED_INSPECT_RECEIPT')

def main():
 p=argparse.ArgumentParser();p.add_argument('mode',choices=['selftest','preflight','scope-check','build-inscope']);a=p.parse_args()
 try:
  if a.mode=='selftest':selftest()
  elif a.mode=='preflight':preflight()
  elif a.mode=='scope-check':
   cg=cgroup_info(required=True)
   print(TAG+'_CGROUP_24G_NO_SWAP_KERNEL_SCOPE_PASS',cg['relative'],flush=True)
  else:build_inscope()
 except Exception as e:
  print(TAG+'_ERROR',repr(e),file=sys.stderr);raise SystemExit(2)
if __name__=='__main__':main()
