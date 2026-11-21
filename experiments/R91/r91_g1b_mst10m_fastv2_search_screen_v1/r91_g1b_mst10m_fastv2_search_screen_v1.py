#!/usr/bin/env python3
"""R91 G1B: SHA-frozen graph MS-Turing10M, single-graph fixed-beam Search screen.

No native BUILD or source edits. Reuses the EXACT SHA-pinned R86 v4 high-beam
Search evaluator that passed 1M. Its compatibility with 10M is NOT assumed:
input marker must report graph_nodes=10000000, queries=100000 and gt_k=100.
This first screen checks beams 384/896 only, not guaranteed to bracket 0.99/0.998.
A followup dynamic matched-recall experiment needs independent protocol.
"""
from __future__ import annotations
import argparse, hashlib, json, math, os, re, shutil, struct, subprocess, sys, time
from array import array
from pathlib import Path

TAG='R91_G1B_MST10M_FASTV2_FIXEDBEAM_SEARCH_V1'
H=Path.home(); ROOT=H/'ann-task-a'; R91=ROOT/'experiments/R91'
DATA=ROOT/'data/MSTuring_10M_v1'
BASE=DATA/'base.10M.fbin'; QUERY=DATA/'query.public.100K.fbin'; GT=DATA/'groundtruth.public.100K.ibin'
EVAL=ROOT/'experiments/R86/msturing_1m_eval/r86_msturing1m_graph_recall_v4_highbeam'
G1=R91/'r91_g1_one_fastv2_flat_c160_mst10m_24g_v1'
G1JSON=G1/'r91_g1_single10m_result.json'
G07=R91/'r91_g07_mst10m_flat_c160_preflight_v1/r91_g07_preflight.json'
GRAPH=G1/'graphs/MSTuring10M_fast_off_C160_K1024_N2.graph'
PREF=R91/'r91_g1b_mst10m_fastv2_search_preflight_v1'
OUT=R91/'r91_g1b_mst10m_fastv2_search_screen_v1'
BEAMS=(384,896)
LIMIT=24*1024**3
SHA={
 'g1':'bd46f8327e634e05ebdf3975c602d3c069df749be8dc3a6e140f286a606e3835',
 'g07':'70e9f33fa933b791f45e3254185b0374b129b6c4297a0e469c7d3ae02f38b8b0',
 'graph':'4055dedc2ccb3b6406fed45ed28de2ec57c46fe2b085b5046ae13cd943702429',
 'base':'e7756f6b54a07e8af171c7644ce2e1be6d7053ee2a2c30c4b02f99e85984b700',
 'query':'48d087a17bec15a5ec9ea526fe9bd14ac31bbbb5cd200817b341adbb77695644',
 'gt':'77b558bd3b77e4cc1149384996b953b040e412477eb0df9889718fc13e17aff2',
 'evaluator':'bb6576ad3e1e0cc770535aa06355c664993ca70bd1170d6dd4d202ab5767e144',
 'h85_elf':'fcfb16d0ca2b498f94db8383dfc311c2e7ba88cb3036281accd5f30c6d876793',
}
RE_ROW=re.compile(r'^R72_RECALL_ROW\s+beam=(\d+)\s+recall=([^\s]+)\s+qps=([^\s]+)\s+avg_cmps=([^\s]+)\s+avg_visited=([^\s]+)\s*$',re.M)

def gate(p,why):
 if not p:raise RuntimeError(TAG+'_HOLD_'+why)
def regular(p):return p.is_file() and not p.is_symlink()
def sha(path):
 h=hashlib.sha256()
 with path.open('rb') as f:
  for b in iter(lambda:f.read(8<<20),b''):h.update(b)
 return h.hexdigest()
def pin(path,k):
 gate(regular(path),'FILE_MISSING_OR_SYMLINK_'+k)
 gate(sha(path)==SHA[k],'FILE_SHA_DRIFT_'+k)
def readj(p):
 gate(regular(p),'JSON_MISSING_'+p.name)
 return json.loads(p.read_text())
def atomic(p,obj):
 gate(not p.exists() and not p.is_symlink(),'OUTPUT_COLLISION_'+p.name)
 q=p.with_suffix(p.suffix+'.part')
 gate(not q.exists() and not q.is_symlink(),'PART_COLLISION_'+q.name)
 with q.open('x',encoding='utf-8') as f:
  json.dump(obj,f,indent=2,sort_keys=True,allow_nan=False)
  f.write('\n'); f.flush();os.fsync(f.fileno())
 os.replace(q,p)
def header(path,shape,unit):
 with path.open('rb') as f: hdr=f.read(8)
 gate(len(hdr)==8 and struct.unpack('<II',hdr)==shape,'HEADER_'+path.name)
 gate(path.stat().st_size==8+unit*shape[0]*shape[1],'SIZE_'+path.name)
def graph_shape():
 with GRAPH.open('rb') as f:
  gate(f.read(8)==struct.pack('<II',10000000,64),'GRAPH_HEADER_10M_CAP64')
  degrees=array('I')
  for _ in range(40):
   raw=f.read(1000000)
   gate(len(raw)==1000000,'GRAPH_DEGREE_TRUNCATED')
   degrees.frombytes(raw)
 if sys.byteorder!='little':degrees.byteswap()
 gate(len(degrees)==10000000 and min(degrees)>=0 and max(degrees)<=64,'GRAPH_DEGREE_BOUNDS')
 arcs=sum(degrees)
 gate(arcs==540692297,'GRAPH_ARCS_MISMATCH')
 gate(GRAPH.stat().st_size==8+4*10000000+4*arcs,'GRAPH_EXACT_BYTES')
 return {'nodes':10000000,'max_degree':64,'arcs':arcs,'file_bytes':GRAPH.stat().st_size}
def gt_shape():
 header(GT,(100000,100),8)
 with GT.open('rb') as f:
  f.seek(8); id_count=0; mi=10000000; ma=0
  while id_count<10000000:
   raw=f.read(4*min(1<<18,10000000-id_count))
   gate(len(raw)>0 and len(raw)%4==0,'GT_IDS_TRUNCATED')
   a=array('I');a.frombytes(raw)
   if sys.byteorder!='little':a.byteswap()
   gate(len(a)>0,'GT_IDS_EMPTY')
   mi=min(mi,min(a));ma=max(ma,max(a));id_count+=len(a)
 gate(id_count==10000000 and mi>=0 and ma<10000000,'GT_ID_RANGE')
 return {'ids':id_count,'min':mi,'max':ma}
def parse(s):
 input_lines=[line for line in s.splitlines() if line.startswith('R72_RECALL_INPUT_PASS')]
 gate(len(input_lines)==1,'EVAL_INPUT_MARKER_COUNT')
 gate(re.search(r'\bgraph_nodes=10000000\b',input_lines[0]) is not None,'EVAL_NOT_10M_COMPATIBLE')
 gate(re.search(r'\bqueries=100000\b',input_lines[0]) is not None,'EVAL_WRONG_QUERY_COUNT')
 gate(re.search(r'\bgt_k=100\b',input_lines[0]) is not None,'EVAL_WRONG_GT_K')
 gate(s.count('R72_RECALL_EVAL_PASS')==1,'EVAL_PASS_MARKER_MISSING')
 rows={}
 for m in RE_ROW.finditer(s):
  b=int(m.group(1));gate(b in BEAMS and b not in rows,'UNEXPECTED_OR_DUP_BEAM')
  try:rec,qps,cmps,vis=[float(m.group(i)) for i in range(2,6)]
  except ValueError:raise RuntimeError(TAG+'_HOLD_BAD_FLOAT_'+str(b))
  gate(math.isfinite(rec) and 0<=rec<=1 and math.isfinite(qps) and qps>0 and math.isfinite(vis) and vis>=0,'NONFINITE_OR_WRONG_METRIC_'+str(b))
  rows[b]={'recall_at10':rec,'qps':qps,'avg_visited':vis,
           'avg_cmps_legacy_not_for_comparison':None,
           'latency_us_inverse_qps_NOT_TAIL':1e6/qps,
           'meets_0_99':rec>=.99,'meets_0_998':rec>=.998}
 gate(tuple(rows)==BEAMS,'MISSING_OR_REORDERED_BEAM')
 return {str(b):rows[b] for b in BEAMS}
def snapshot():
 def get(k):
  for line in Path('/proc/meminfo').read_text().splitlines():
   if line.startswith(k+':'):return int(line.split()[1])
  return None
 disk=shutil.disk_usage(R91) if R91.is_dir() else shutil.disk_usage(ROOT)
 return {'memavailable_kib':get('MemAvailable'),'disk_free_GiB':disk.free/1024**3,'ts_unix':time.time()}
def cgroup(required=False):
 a=[x for x in Path('/proc/self/cgroup').read_text().splitlines() if x.startswith('0::')]
 gate(len(a)==1,'CGROUP_NOT_UNIFIED_V2')
 rel=a[0].split('::',1)[1];gate(rel.startswith('/user.slice/') and '..' not in rel,'CGROUP_SCOPE_NOT_USER')
 root=Path('/sys/fs/cgroup')/rel.lstrip('/')
 names=('memory.max','memory.swap.max','memory.current','memory.swap.current','memory.peak','memory.events')
 files={k:(root/k).read_text().strip() if (root/k).is_file() else None for k in names}
 if required:
  gate(files['memory.max']==str(LIMIT) and files['memory.swap.max']=='0','CGROUP_24G_NOSWAP_NOT_ACTIVE')
  gate(files['memory.swap.current'] is not None and int(files['memory.swap.current'])==0,'CGROUP_ALREADY_SWAPPED')
 return {'path':str(root),'files':files}
def events(s):
 out={}
 for line in (s or '').splitlines():
  p=line.split()
  if len(p)==2 and p[1].isdigit():out[p[0]]=int(p[1])
 return out
def validate_source(check_disk=True):
 pin(G1JSON,'g1');pin(G07,'g07');pin(GRAPH,'graph')
 for p,k in ((BASE,'base'),(QUERY,'query'),(GT,'gt'),(EVAL,'evaluator')):pin(p,k)
 header(BASE,(10000000,100),4)
 header(QUERY,(100000,100),4)
 bounds=gt_shape();info=graph_shape()
 src=readj(G1JSON); pre=readj(G07)
 gate(src['status']=='NATIVE_1_OF_1_10M_BUILD_AND_FULL_GRAPH_STRUCTURE_PASS_NO_SWAP' and src['builder_exit_code']==0,'G1_NATIVE_STATUS')
 gate(src['graph_quality']['sha256']==SHA['graph'] and src['graph_quality']['arcs']==info['arcs'] and src['graph_quality']['nodes']==10000000,'G1_NATIVE_GRAPH_LINK')
 for field in ('full_graph_invalid_id','full_graph_selfloops','full_graph_duplicate_neighbor_rows'):
  gate(src['graph_quality'][field]==0,'G1_GRAPH_STRUCT_'+field)
 gate(src['graph_quality']['full_audit_all_vertices'] is True,'G1_GRAPH_AUDIT_SCOPE')
 gate(src['cgroup_events_delta']['oom_kill']==0 and src['peak_swap_current']==0 and src['source_cgroup_swap_after_bytes']==0,'G1_NOSWAP_OOM_RECORD')
 gate(pre['status']=='R91_G07_READONLY_PINNED_SOURCE_DATA_RESOURCES_PREFLIGHT_PASS__NO_10M_BUILD','G07_STATE')
 gate(pre['source']['fast_off_elf_sha256']==SHA['h85_elf'] and pre['source']['highway_git_head']=='6bc2d47793bae9c521fb4150936669647700765d','FASTV2_H85_PROVENANCE')
 for k in ('base','query','gt'):gate(pre['data'][k+'_sha256']==SHA[k],'GT_SOURCE_PIN_'+k)
 gate(pre['data']['dataset_n']==10000000 and pre['data']['queries']==100000,'GT_SOURCE_COUNTS')
 gate(bounds['max']==pre['data']['gt_id_bounds']['max_id'],'GT_ID_MAX_SOURCE_DRIFT')
 gate(0 in os.sched_getaffinity(0),'CPU0_NOT_AVAILABLE')
 for cmd in ('taskset','df'):
  gate(shutil.which(cmd) is not None,'CMD_MISSING_'+cmd)
 if check_disk:
  snap=snapshot();gate(snap['disk_free_GiB']>=8,'DISK_BELOW_8_GIB')
  gate(snap['memavailable_kib'] is not None and snap['memavailable_kib']>=10*1024*1024,'HOST_MEMAVAILABLE_BELOW_10_GIB')
 return {'graph':info,'gt_id_bounds':bounds,'files_sha256':SHA.copy(),'data_format':'fbin FP32; GT dual-array ibin IDs then distances',
  'eval_note':'R86 1M-named binary pinned; 10M compatibility verified ONLY by native input marker during run',
  'screens_beams':list(BEAMS),'native_build':False,'timestamp':time.time()}
def preflight():
 gate(not PREF.exists() and not PREF.is_symlink(),'PREFLIGHT_ALREADY_EXISTS_PRESERVE')
 gate(not OUT.exists() and not OUT.is_symlink(),'SCREEN_ALREADY_EXISTS_PRESERVE')
 x=validate_source()
 PREF.mkdir(parents=True,exist_ok=False)
 out={'status':'R91_G1B_10M_FASTV2_GRAPH_PINNED_PREFLIGHT_PASS__NO_SEARCH_NO_BUILD',
      'runner_sha256':sha(Path(__file__)),'resource_snapshot':snapshot(),'validated':x}
 atomic(PREF/'r91_g1b_preflight.json',out)
 print(TAG+'_PREFLIGHT_PASS_G1_10M_GRAPH_SHA_3_DATA_SHA_GT_BOUNDS_1M_NAMED_EVALUATOR_SHA',flush=True)
 print(TAG+'_PREFLIGHT_REPORT',PREF/'r91_g1b_preflight.json','sha256',sha(PREF/'r91_g1b_preflight.json'),flush=True)
def run():
 c0=cgroup(True)
 gate(regular(PREF/'r91_g1b_preflight.json'),'MISSING_PREFLIGHT')
 pre=readj(PREF/'r91_g1b_preflight.json')
 gate(pre['status'].endswith('__NO_SEARCH_NO_BUILD'),'PREFLIGHT_STATE')
 gate(pre['runner_sha256']==sha(Path(__file__)),'SCRIPT_PIN_DRIFT')
 gate(not OUT.exists() and not OUT.is_symlink(),'OUT_ALREADY_EXISTS_NO_RERUN')
 sources=validate_source()
 gate(pre['validated']['graph']==sources['graph'] and pre['validated']['files_sha256']==sources['files_sha256'],'PREFLIGHT_SOURCE_DRIFT')
 OUT.mkdir(parents=True,exist_ok=False);(OUT/'logs').mkdir(exist_ok=False)
 stdout=OUT/'logs/native_fixedbeam.stdout';stderr=OUT/'logs/native_fixedbeam.stderr'
 timelog=OUT/'logs/native_fixedbeam.time'
 cmd=['/usr/bin/time','-v','-o',str(timelog),'taskset','-c','0',str(EVAL),str(GRAPH),str(BASE),str(QUERY),str(GT),','.join(map(str,BEAMS))]
 gate(Path('/usr/bin/time').is_file(),'GNU_TIME_MISSING')
 env=dict(os.environ)
 env.update(PARLAY_NUM_THREADS='1',OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='1',LC_ALL='C')
 atomic(OUT/'preregister.json',{'source_preflight_sha':sha(PREF/'r91_g1b_preflight.json'),
     'runner_sha256':sha(Path(__file__)),'pins':SHA,'cmd':cmd,'scope_before':c0,
     'beam_grid':list(BEAMS),'single_cpu':0,'no_build':True,'limitations':['No guarantee .99 or .998 reached at selected beams',
     'MS legacy avg_cmps overflow excluded','No per-query p50/p95/p99','R86 evaluator 10M binary compatibility not proven until stdout input marker']})
 print(TAG+'_SEARCH_START_10M_ONE_GRAPH_BEAMS_'+','.join(map(str,BEAMS)),flush=True)
 begin=time.perf_counter();error=None;rc=None;results=None
 try:
  with stdout.open('x') as f,stderr.open('x') as e:
   try:
    p=subprocess.run(cmd,stdout=f,stderr=e,env=env,timeout=3600,check=False)
    rc=p.returncode
   except subprocess.TimeoutExpired as exc:rc=-124;error='EVALUATOR_TIMEOUT_3600_SECONDS'
  if rc==0:
   gate(stderr.stat().st_size==0,'EVALUATOR_NONEMPTY_STDERR')
   results=parse(stdout.read_text(errors='replace'))
   pin(GRAPH,'graph')
  elif error is None:error='EVALUATOR_EXIT_'+str(rc)
 except Exception as exc:
  error='SCREEN_EXCEPTION_'+repr(exc)
 time_used=time.perf_counter()-begin
 c1=cgroup(False)
 ev0=events(c0['files']['memory.events']);ev1=events(c1['files']['memory.events'])
 evd={k:v-ev0.get(k,0) for k,v in ev1.items()}
 swap=int(c1['files']['memory.swap.current'] or 0)
 if evd.get('oom',0)>0 or evd.get('oom_kill',0)>0 or swap>0:
  error=(error or '')+' CGROUP_OOM_OR_SWAP'; results=None
 status='R91_G1B_ONE_10M_GRAPH_FIXEDBEAM_SEARCH_NATIVE_PASS' if results is not None else 'R91_G1B_SEARCH_HOLD_PRESERVE_ORPHAN_LOGS'
 report={'status':status,'error':error,'native_evaluator_exit':rc,'elapsed_external_s':time_used,
         'metrics':results,'source_graph_sha256':SHA['graph'],'dataset':'MS-Turing10M',
         'beam_grid':list(BEAMS),'nqueries':100000,'src_preflight_sha256':sha(PREF/'r91_g1b_preflight.json'),
         'preregister_sha256':sha(OUT/'preregister.json'),'evaluator_sha256':SHA['evaluator'],
         'stdout_sha256':sha(stdout) if regular(stdout) else None,
         'stderr_sha256':sha(stderr) if regular(stderr) else None,
         'timefile_sha256':sha(timelog) if regular(timelog) else None,
         'cgroup_peak_bytes':int(c1['files']['memory.peak'] or 0),
         'cgroup_events_delta':evd,'cgroup_swap_after':swap,'cgroup_path':c1['path'],
         'limitations':['single frozen graph, first screen beams384/896 only; can miss Recall target',
                        'Stock 10M not yet built; no 10M speedup comparison',
                        'avg_cmps legacy ignored, QPS inversion is NOT tail latency']}
 atomic(OUT/'quality_screen_summary.json',report)
 print(TAG+'_RESULT',status,'rc',rc,'metrics',results,'sha256',sha(OUT/'quality_screen_summary.json'),flush=True)
 gate(results is not None,'SEARCH_FAILED_INSPECT_OUTPUT_NO_RERUN')
def audit():
 gate(regular(OUT/'preregister.json') and regular(OUT/'quality_screen_summary.json'),'MISSING_OUTPUT_RECEIPTS')
 x=readj(OUT/'quality_screen_summary.json');p=readj(OUT/'preregister.json')
 gate(p['runner_sha256']==sha(Path(__file__)),'RUNNER_DRIFT')
 gate(p['source_preflight_sha']==sha(PREF/'r91_g1b_preflight.json'),'PREFLIGHT_DRIFT')
 gate(x['status']=='R91_G1B_ONE_10M_GRAPH_FIXEDBEAM_SEARCH_NATIVE_PASS' and x['native_evaluator_exit']==0,'SCREEN_NATIVE_NOT_PASS')
 gate(x['beam_grid']==list(BEAMS) and x['evaluator_sha256']==SHA['evaluator'] and x['source_graph_sha256']==SHA['graph'],'SCREEN_LINK')
 stdout=OUT/'logs/native_fixedbeam.stdout';stderr=OUT/'logs/native_fixedbeam.stderr';t=OUT/'logs/native_fixedbeam.time'
 gate(all(regular(f) for f in (stdout,stderr,t)),'MISSING_NATIVE_LOG')
 gate(sha(stdout)==x['stdout_sha256'] and sha(stderr)==x['stderr_sha256'] and sha(t)==x['timefile_sha256'],'LOG_SHA_DRIFT')
 gate(parse(stdout.read_text(errors='replace'))==x['metrics'],'LOG_REPARSE_MISMATCH')
 gate(x['cgroup_swap_after']==0 and x['cgroup_events_delta'].get('oom_kill',1)==0 and x['cgroup_events_delta'].get('oom',1)==0,'CGROUP_OOM')
 pin(GRAPH,'graph')
 print(TAG+'_AUDIT_PASS_G1_10M_FROZEN_GRAPH_TWO_BEAMS_NO_BUILD',flush=True)
 print(TAG+'_FINAL_SUMMARY',OUT/'quality_screen_summary.json','sha256',sha(OUT/'quality_screen_summary.json'),flush=True)
 for beam,m in x['metrics'].items():
  print(TAG+'_BEAM',beam,'RECALL',m['recall_at10'],'QPS',m['qps'],'TARGET_099',m['meets_0_99'],'TARGET_0998',m['meets_0_998'],flush=True)
 print(TAG+'_NOTE_STOCK_10M_NOT_BUILT_AND_IF_TARGETS_UNREACHED_EXPAND_BEAM_GRID_LATER',flush=True)
def selftest():
 gate(all(len(z)==64 and set(z)<=set('0123456789abcdef') for z in SHA.values()),'64HEX_SHA_FIXTURE')
 text='R72_RECALL_INPUT_PASS graph_nodes=10000000 queries=100000 gt_k=100\n'+''.join(f'R72_RECALL_ROW beam={b} recall={r:.8f} qps={q:.4f} avg_cmps=4294955363 avg_visited={v}\n' for b,r,q,v in ((384,.9899,1234,320),(896,.9979,561,741)))+'R72_RECALL_EVAL_PASS\n'
 p=parse(text)
 gate(len(p)==2 and not p['384']['meets_0_99'] and not p['896']['meets_0_998'],'TEST_THRESH_NOT_ASSUMED')
 for bad in [text.replace('graph_nodes=10000000','graph_nodes=1000000'),text.replace('R72_RECALL_EVAL_PASS',''),text.replace('recall=0.98990000','recall=nan'),text.replace('beam=896','beam=384')]:
  try:parse(bad)
  except RuntimeError:pass
  else:raise RuntimeError(TAG+'_SELFTEST_BAD_EVALUATOR_ACCEPTED')
 with __import__('tempfile').TemporaryDirectory() as td:
  pth=Path(td)/'g';raw=struct.pack('<II',2,64)+struct.pack('<2I',1,1)+struct.pack('<2I',1,0)
  pth.write_bytes(raw)
  gate(pth.stat().st_size==8+8+8,'SELFTEST_GRAPH_BYTES')
 gate(events('max 345\noom 0\noom_kill 0\n')['max']==345,'SELFTEST_EVENT')
 print(TAG+'_SELFTEST_PASS_PARSER_GRAPH_HEADER_CGROUP_TARGETS_NOT_ASSUMED_NO_BUILD',flush=True)

def main():
 a=argparse.ArgumentParser();a.add_argument('mode',choices=('selftest','preflight','run','audit','scope-check'));args=a.parse_args()
 try:
  if args.mode=='selftest':selftest()
  elif args.mode=='preflight':preflight()
  elif args.mode=='run':run()
  elif args.mode=='audit':audit()
  else:
   cg=cgroup(True)
   print(TAG+'_CGROUP_24G_NOSWAP_PASS',cg['path'],flush=True)
 except Exception as e:
  print(TAG+'_ERROR',repr(e),file=sys.stderr,flush=True)
  sys.exit(2)
if __name__=='__main__':main()
