#!/usr/bin/env python3
"""G15-R2-P0 telemetry-only original C64 Search, no adaptive policy.

Source is an isolated staged G13-CTRL copy (original G11 Counter64 source lineage).
Native Search output and early frontier probes are post-run observables; no GT
feeds any decision. Requires full counter/Recall parity versus preexisting G15
CSV before treating features as valid. Never rewrites original graph or source.
"""
from __future__ import annotations
import argparse,csv,hashlib,importlib.util,json,os,re,shutil,subprocess,sys,tempfile
from pathlib import Path

HERE=Path(__file__).resolve().parent
HOME=Path.home(); ROOT=HOME/'ann-task-a';R86=ROOT/'experiments/R86'
OUT=HOME/'Downloads/G15_R2_P0_NATIVE_EARLY_TRACE_v1'
MANIFEST_SHA='3a0fc161fb030e3aa1deecc201d483f9a3188840cc6bdbf084bd358961c7db8f'
G15_R1_SCRIPT=HOME/'Downloads/g15_r1_c64_beam_oracle_v1.py'
G15_R1_SCRIPT_SHA='d05e545d49d7169118fe371c5b8976cc9212edeea8e1a3f551b1a1b6057a2d05'
G15_R1_RECEIPT=HOME/'Downloads/G15_R1_C64_BEAM_ORACLE_v1/RECEIPT.json'
G11=R86/'g11_counter64_diagnostic_v2_0'
G11BIN=G11/'msturing_1m_eval/r86_msturing1m_graph_recall_v4_diag_counter64'
G11CC=G11/'msturing_1m_eval/r86_msturing1m_graph_recall_v4_diag_counter64.cc'
G11_BIN_SHA='a98b8748b92787e6ccbf52556a8eef2c24bff4580c6275c9fa464dd82af4d3a4'
G11_CC_SHA='1bd183316d4076475be393a7f92c72df552389c1a84dfae430e8931705a343cf'
DEPS=ROOT/'experiments/H70/build-r70/_deps'
H70SRC=ROOT/'experiments/H70/pipnn-clean-443a328/algorithms/utils'
DATAS={'base':(ROOT/'data/MSTuring_1M_v1/base.1M.fbin','44e83e1dd4c65999b75873101adc5ac06ca900d259a2befd05c2c3aa28ff4042'),
       'queries':(ROOT/'data/MSTuring_1M_v1/query.public.100K.fbin','48d087a17bec15a5ec9ea526fe9bd14ac31bbbb5cd200817b341adbb77695644'),
       'gt':(ROOT/'data/MSTuring_1M_v1/groundtruth.public.100K.ibin','fa5acf5ab262b42355296e99f920e6aa863f48820ca6f70fa37ca7966634c344')}
GRAPHS={1:'964e8ce3df93f113bb5fb6ab809b6cf7da132dc6129ef0d7bbe8de52bbc31248',
        2:'d099a8154315016bf9783444bc041838dad738be60caad2ae91dc5daf07f28cf',
        3:'aa791b42e992c7d1fe712ccf783387bffcb2a894e891fa97dd01ca50739a52ff'}
BEAM=384; QUERY_N=100000; STEPS=(16,64,128,256)
class Hold(Exception):pass

def need(x,msg):
 if not x:raise Hold('G15_R2_P0_HOLD_'+msg)

def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(1<<20),b''):h.update(b)
 return h.hexdigest()

def pin(p,h,label):
 p=Path(p)
 need(p.is_file() and not p.is_symlink(),label+'_MISSING_OR_SYMLINK')
 need(sha(p)==h,label+'_SHA_MISMATCH')

def source_check():
 man=HERE/'PROBE_SOURCE_MANIFEST.json'
 need(sha(man)==MANIFEST_SHA,'PROBE_MANIFEST_SHA_CHANGED')
 m=json.loads(man.read_text())
 need(len(m)>=20,'SOURCE_FILE_COUNT')
 for k,v in m.items():
  p=HERE/k
  pin(p,v['sha256'],'SRC_'+k)
  need(p.stat().st_size==v['bytes'],'SOURCE_SIZE_'+k)
 old=json.loads((HERE/'UPSTREAM_G13_CTRL_MANIFEST.json').read_text())
 need(len(old)==19,'UPSTREAM_G13_FILE_COUNT')
 for k,v in old.items():
  need(k in m,'UPSTREAM_FILE_MISSING_'+k)
  if k not in ('effective_utils/beamSearch.h','eval.cc'):
   need(m[k]['sha256']==v['sha256'],'NONPROBE_ORIGINAL_CHANGED_'+k)
 b=(HERE/'effective_utils/beamSearch.h').read_text()
 need(b.count('g15_maybe_snapshot();')==2 and b.count('g15_trace_save(i, ngh_dist, QueryStats);')==2,'TRACE_INJECTION_NOT_AT_BOTH_PATHS')
 need(b.index('int offset = 0;')<b.index('auto g15_maybe_snapshot'),'EARLY_TRACE_OFFSET_NOT_DEFINED_BEFORE_LAMBDA')
 need('g15_trace_dump' in (HERE/'eval.cc').read_text(),'TRACE_EVAL_DUMP_MISSING')
 print('G15_R2_P0_PACKAGED_SOURCE_SHA_ORIGINAL_G13_CTRL_NONTRACE_PARITY_PASS')

def load_g15():
 pin(G15_R1_SCRIPT,G15_R1_SCRIPT_SHA,'PRIOR_G15_R1_SCRIPT')
 need(G15_R1_RECEIPT.is_file(),'PRIOR_G15_R1_RECEIPT_MISSING')
 spec=importlib.util.spec_from_file_location('g15_r1_source_pinned',G15_R1_SCRIPT)
 mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
 paths,receipt,summary,parent=mod.validate_inputs()
 rec=json.loads(G15_R1_RECEIPT.read_text())
 need(rec.get('source_script_sha256')==G15_R1_SCRIPT_SHA,'G15_R1_PRIOR_RECEIPT_SCRIPT_SHA')
 need(rec.get('summary_sha256')==sha(mod.OUT/'g15_r1_oracle_summary.json'),'G15_R1_SUMMARY_SHA')
 return mod,paths,summary,parent

def preflight(check_all_graphs=False):
 source_check()
 pin(G11BIN,G11_BIN_SHA,'ORIGINAL_G11_BINARY')
 pin(G11CC,G11_CC_SHA,'ORIGINAL_G11_EVAL_SRC')
 old_cmd=G11/'compile_command.json'
 need(old_cmd.is_file() and '-ffast-math' in json.dumps(json.loads(old_cmd.read_text())),'G11_COMPILE_FLAG_NOT_VERIFIED')
 for x in (DEPS/'parlaylib-src/include/parlay/parallel.h',DEPS/'abseil-cpp-src/absl/container/flat_hash_set.h',DEPS/'eigen-src/Eigen/Core',H70SRC/'point_range.h'):
  need(x.is_file(),'BUILD_DEP_MISSING_'+str(x))
 for k,(p,h) in DATAS.items():pin(p,h,'DATA_'+k)
 for rep,h in GRAPHS.items():
  if check_all_graphs or rep==1:
   pin(graph_path(rep),h,'GRAPH_A2R'+str(rep))
 mod,paths,summary,parent=load_g15()
 for rep in GRAPHS:
  need(paths[(rep,384)][1]==parent.sha(paths[(rep,384)][0]),'R1_PRIOR_B384_INPUT_SHA_'+str(rep))
 print('G15_R2_P0_NATIVE_SOURCE_BINARY_DATA_G15_R1_ORIGINAL_INPUTS_PASS')
 return mod,paths,summary,parent

def graph_path(rep):return R86/f'msturing_1m_sixarm/formal_mst1m_v1/A2/r{rep}/index.graph'

def selftest():
 source_check()
 if shutil.which('g++'):
  with tempfile.TemporaryDirectory() as td:
   binary=Path(td)/'smoke'
   cmd=['g++','-std=c++17','-O2',str(HERE/'probe_smoke.cc'),'-o',str(binary)]
   r=subprocess.run(cmd,capture_output=True,text=True)
   need(r.returncode==0,'CXX_PROBE_SMOKE_COMPILE_'+r.stderr[:400])
   trace=Path(td)/'trace.csv'; subprocess.run([str(binary),str(trace)],check=True)
   with trace.open(newline='') as f:
    rr=list(csv.DictReader(f))
   need(len(rr)==2 and rr[0]['query_id']=='0' and rr[1]['nn9']=='19','CXX_PROBE_SMOKE_CSV')
 print('G15_R2_P0_SELFTEST_SOURCE_PATCH_2PATHS_CPP_SMOKE_AND_CSV_PASS_NO_ANN_NATIVE')

def build():
 preflight()
 need(not OUT.exists(),'OUTPUT_ROOT_EXISTS_NO_OVERWRITE')
 need(shutil.which('g++') is not None,'GXX_MISSING')
 builddir=OUT/'build';builddir.mkdir(parents=True,exist_ok=False)
 binary=builddir/'g15_r2_p0_telemetry'
 dep=builddir/'deps.d'
 cmd=['g++','-std=c++17','-O3','-march=native','-ffast-math','-pthread','-MMD','-MF',str(dep),
      '-I',str(DEPS/'parlaylib-src/include'),'-I',str(H70SRC),
      '-I',str(DEPS/'abseil-cpp-src'),'-I',str(DEPS/'eigen-src'),str(HERE/'eval.cc'),'-o',str(binary)]
 (builddir/'compile_command.json').write_text(json.dumps(cmd,indent=2)+'\n')
 with (builddir/'stdout.log').open('x') as so,(builddir/'stderr.log').open('x') as se:
  ret=subprocess.run(cmd,stdout=so,stderr=se).returncode
 need(ret==0,'NATIVE_COMPILE_FAILED_SEE_'+str(builddir/'stderr.log'))
 need(binary.is_file() and dep.is_file(),'BUILD_MISSING_BINARY_OR_DEPFILE')
 deps=dep.read_text().replace('\\\n',' ')
 for name in ('beamSearch.h','g15_early_probe.h','check_nn_recall.h','graph.h','stats.h'):
  need(str((HERE/'effective_utils'/name).resolve()) in deps,'ACTIVE_DEPFILE_MISSING_'+name)
 manifest={'binary_sha256':sha(binary),'source_manifest_sha256':MANIFEST_SHA,
           'compile_command_sha256':sha(builddir/'compile_command.json'),
           'depfile_sha256':sha(dep),'source_binary':str(binary),'flags':'-std=c++17 -O3 -march=native -ffast-math -pthread',
           'probe_only_no_adaptive_policy':True}
 (builddir/'BUILD_RECEIPT.json').write_text(json.dumps(manifest,indent=2,sort_keys=True)+'\n')
 print('G15_R2_P0_TELEMETRY_ONLY_NATIVE_CPP_BUILD_DEPFILE_PASS',json.dumps(manifest,sort_keys=True))

def parse_result(out,beam):
 pat=rf'R72_RECALL_ROW beam={beam} recall=([0-9.]+) qps=([0-9.]+) avg_cmps=(\d+) avg_visited=(\d+)'
 m=re.search(pat,out)
 need(m is not None,'NATIVE_RECALL_ROW_NOT_FOUND')
 return {'recall':float(m[1]),'qps_diagnostic_instrumented':float(m[2]),'avg_cmps':int(m[3]),'avg_visited':int(m[4])}

def run_one(rep):
 mod,paths,summary,parent=preflight(check_all_graphs=False)
 pin(graph_path(rep),GRAPHS[rep],'GRAPH_A2R'+str(rep))
 bd=OUT/'build'; br=bd/'BUILD_RECEIPT.json';need(br.is_file(),'BUILD_FIRST')
 receipt=json.loads(br.read_text());binary=bd/'g15_r2_p0_telemetry'
 pin(binary,receipt['binary_sha256'],'BUILT_CPP_BINARY')
 d=OUT/'runs'/f'A2_r{rep}_b384';need(not d.exists(),'REPEATED_RUN_NO_OVERWRITE_R'+str(rep))
 d.mkdir(parents=True,exist_ok=False)
 trace=d/'query_early.csv'
 args=['taskset','-c','0',str(binary),str(graph_path(rep)),str(DATAS['base'][0]),str(DATAS['queries'][0]),str(DATAS['gt'][0]),str(BEAM)]
 need(shutil.which('taskset') is not None and 0 in os.sched_getaffinity(0),'CPU0_AFFINITY_UNAVAILABLE')
 (d/'command.json').write_text(json.dumps(args,indent=2)+'\n')
 env=os.environ.copy();env['PARLAY_NUM_THREADS']='1';env['G15_R2_TRACE_OUT']=str(trace)
 print('G15_R2_P0_NATIVE_TRACE_START',json.dumps({'rep':rep,'beam':BEAM,'output':str(trace)}),flush=True)
 with (d/'stdout.log').open('x') as so,(d/'stderr.log').open('x') as se:
  ret=subprocess.run(args,env=env,stdout=so,stderr=se).returncode
 need(ret==0,'NATIVE_TRACE_EVAL_FAILED_R'+str(rep)+'_SEE_'+str(d/'stderr.log'))
 native=(d/'stdout.log').read_text(); need('R72_RECALL_EVAL_PASS' in native,'R72_EVAL_NOT_FINISHED')
 result=parse_result(native,BEAM)
 oracle_summary=json.loads((mod.OUT/'g15_r1_oracle_summary.json').read_text())
 expected=oracle_summary['results'][f'r{rep}']['shallow_mean_recall10']
 need(abs(expected-result['recall'])<1.1e-6,'AGGREGATE_RECALL_PARITY_R'+str(rep)+'_ORIGINAL_'+str(expected)+'_NEW_'+str(result['recall']))
 need(trace.is_file(),'TRACE_CSV_MISSING')
 native_vis=parent.colmap(next(csv.reader(paths[(rep,384)][0].open(newline='')))).get('visited')
 cmps_ref={};visited_ref={}
 with paths[(rep,384)][0].open(newline='') as f:
  reader=csv.DictReader(f);col=parent.colmap(reader.fieldnames or [])
  need('cmps' in col and 'query_id' in col,'G12_ORIGINAL_CMPS_QID_NOT_IN_CSV')
  for x in reader:
   i=int(x[col['query_id']]); cmps_ref[i]=int(float(x[col['cmps']]))
   if 'visited' in col:visited_ref[i]=int(float(x[col['visited']]))
 need(len(cmps_ref)==QUERY_N,'ORIGINAL_100K_CSV_MISSING')
 n=0; bad=[];visbad=[]; reached={m:0 for m in STEPS};allc=0
 with trace.open(newline='') as f:
  reader=csv.DictReader(f);cols=reader.fieldnames or []
  need(len(cols)==3+8*len(STEPS)+10,'EARLY_TRACE_SCHEMA_LENGTH')
  seen=bytearray(QUERY_N)
  for x in reader:
   i=int(x['query_id']);need(0<=i<QUERY_N and not seen[i],'EARLY_TRACE_QID_DUP_INVALID')
   seen[i]=1;n+=1
   cmp=int(x['final_comps']);allc+=cmp
   if cmp!=cmps_ref[i]:
    if len(bad)<6:bad.append((i,cmp,cmps_ref[i]))
   if visited_ref and int(x['final_visited'])!=visited_ref[i]:
    if len(visbad)<6:visbad.append((i,int(x['final_visited']),visited_ref[i]))
   ids=[int(x[f'nn{j}']) for j in range(10)]
   need(len(set(ids))==10 and all(0<=z<1000000 for z in ids),'BAD_RETURNED_TOP10_IDS')
   for m in STEPS:
    if int(x[f'hit{m}'])==1:
     reached[m]+=1
     need(int(x[f'cmps{m}'])<=cmp,'EARLY_COUNT_AFTER_FINAL_COUNT')
     need(int(x[f'frontier{m}'])<=BEAM,'EARLY_FRONTIER_ABOVE_BEAM')
 need(n==QUERY_N and sum(seen)==QUERY_N,'EARLY_TRACE_QUERY_COUNT')
 need(not bad,'EXACT_PERQUERY_DISTANCE_COMPS_PARITY_FAILED_SAMPLE_'+str(bad))
 need(not visbad,'EXACT_PERQUERY_VISITED_PARITY_FAILED_SAMPLE_'+str(visbad))
 expected_cmps=int(oracle_summary['results'][f'r{rep}']['shallow_mean_comps'])
 need(abs(allc/n-expected_cmps)<0.01,'ORACLE_AVG_CMPS_PARITY')
 receipt={**result,'rep':rep,'beam':BEAM,'query_count':n,'source_csv_sha256':paths[(rep,384)][1],
          'graph_sha256':GRAPHS[rep],'trace_sha256':sha(trace),'stdout_sha256':sha(d/'stdout.log'),
          'stderr_sha256':sha(d/'stderr.log'),'command_sha256':sha(d/'command.json'),
          'visited_parity_checked':bool(visited_ref),'exact_original_returned_id_parity':'NOT_CHECKED',
          'early_reached_count':{str(k):v for k,v in reached.items()},
          'full_original_native_cmps_perquery_equal':True,'full_original_native_visited_perquery_equal':bool(visited_ref),
          'instrumented_qps_not_a_speed_comparison':True}
 (d/'RUN_RECEIPT.json').write_text(json.dumps(receipt,indent=2,sort_keys=True)+'\n')
 print('G15_R2_P0_NATIVE_TRACE_100K_PERQUERY_COMPS_RECALL_PARITY_PASS',json.dumps(receipt,sort_keys=True),flush=True)

def audit():
 preflight()
 br=OUT/'build/BUILD_RECEIPT.json'; need(br.is_file(),'NO_BUILD_RECEIPT')
 b=json.loads(br.read_text());pin(OUT/'build/g15_r2_p0_telemetry',b['binary_sha256'],'AUDIT_BINARY_SHA')
 done=0
 for rep in GRAPHS:
  d=OUT/'runs'/f'A2_r{rep}_b384';rec=d/'RUN_RECEIPT.json'
  if not rec.exists():continue
  t=json.loads(rec.read_text())
  for k,p in (('trace_sha256',d/'query_early.csv'),('stdout_sha256',d/'stdout.log'),('stderr_sha256',d/'stderr.log'),('command_sha256',d/'command.json')):
   pin(p,t[k],'AUDIT_'+k+'_r'+str(rep))
  need(t['full_original_native_cmps_perquery_equal'] and t['query_count']==QUERY_N and t['rep']==rep,'AUDIT_ROW_PARITY_R'+str(rep))
  done+=1
 need(done>=1,'NO_COMPLETED_NATIVE_TRACE')
 print('G15_R2_P0_NATIVE_AUDIT_COMPLETED_GRAPHS',done,'OF3; TELEMETRY ONLY NO_PREDICTOR_NO_QPS_CLAIM')

def main():
 ap=argparse.ArgumentParser();ap.add_argument('phase',choices=['selftest','preflight','build','pilot_r1','pilot_r2','pilot_r3','audit'])
 phase=ap.parse_args().phase
 try:
  if phase=='selftest':selftest()
  elif phase=='preflight':preflight()
  elif phase=='build':build()
  elif phase.startswith('pilot_'):run_one(int(phase[-1]))
  elif phase=='audit':audit()
 except (Hold,ValueError,OSError,KeyError,TypeError) as ex:
  print(str(ex),file=sys.stderr);sys.exit(2)
if __name__=='__main__':main()
