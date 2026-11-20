#!/usr/bin/env python3
"""R90 P0-A: gated ONE-SNAPSHOT three-arm Source/BUILD/Counters experiment.

Strong safeguards: nothing touches historical source, binary, graph, or logs.
The SAME R86 v1_2 source snapshot is copied into six isolated variants.
Stock OFF/ON are baseline; H17 toggles its already-present R71_H17_TOP2
branch; Fast OFF adds precisely the FP32 cutoff; Fast ON transplants the
previously source-instrumented exact D6 N2 branch into that common snapshot.
This is an experimental reconstruction, NOT yet native certified: pilot gate
MUST pass before any 1M execution, and quality search is an independent gate.

Phases selftest, preflight, prepare, compile, pilot10k, auditpilot, full1m, audit1m.
The shipped shell runs ONLY selftest+preflight+prepare. No 1M BUILD by default.
"""
from __future__ import annotations
import argparse, hashlib, json, os, re, shutil, struct, subprocess, sys, time
from pathlib import Path

H=Path.home(); ROOT=H/'ann-task-a'; R90=ROOT/'experiments/R90'
BASE_SOURCE=ROOT/'experiments/R86/r86_v1_2_source'
D6=R90/'r90_d6_h17_fastv2_top2_exact_counters_v1'
OUT=R90/'r90_p0a_unified_1m_three_arm_v1'
SIFT10K=R90/'r90_p38_h17_top2_prefilter_native_v2/data/sift10k.fbin'
BASES={'SIFT1M':ROOT/'data/sift1m.fbin','MS-Turing1M':ROOT/'data/MSTuring_1M_v1/base.1M.fbin'}
BASE_SHAS={'SIFT1M':'8c7b3d999ba3133f865af72df078f77c2d248fdb80571d7ea1f1bb8e1750658e',
 'MS-Turing1M':'44e83e1dd4c65999b75873101adc5ac06ca900d259a2befd05c2c3aa28ff4042'}
DEPS={
 'PARLAYLIB':ROOT/'experiments/R86/r86_v1_2_builds/stock_off/_deps/parlaylib-src',
 'EIGEN':ROOT/'experiments/R86/r86_v1_2_builds/stock_off/_deps/eigen-src',
 'ABSEIL-CPP':ROOT/'experiments/R86/r86_v1_2_builds/stock_off/_deps/abseil-cpp-src',
 'HIGHWAY':ROOT/'experiments/H85/r85_0_matched_baseline/build_stock/_deps/highway-src',
 'GOOGLEBENCHMARK':ROOT/'experiments/R86/r86_v1_2_builds/stock_off/_deps/googlebenchmark-src'}
FLAGS=['-num_clusters','2','-cluster_size','1024','-table_size','160','-top_level_leaders','100',
 '-fanout_scheme','10,3,1','-mst_deg','2','-prune','1','-prune_all','1',
 '-prune_degree','64','-hash_bits','12','-alpha','1.1','-k','0']
ARMS=('stock','h17','fast'); MODES=('off','on')
TAG='R90_P0A_UNIFIED_V1'

def need(ok,label):
 if not ok:raise RuntimeError(TAG+'_HOLD_'+label)
def sha(path):
 d=hashlib.sha256()
 with Path(path).open('rb') as f:
  for chunk in iter(lambda:f.read(4<<20),b''):d.update(chunk)
 return d.hexdigest()
def digest_tree(root):
 d=hashlib.sha256();root=Path(root)
 for p in sorted(root.rglob('*')):
  if p.is_symlink():raise RuntimeError('SOURCE_TREE_SYMLINK_'+str(p))
  if p.is_file():
   d.update(str(p.relative_to(root)).encode());d.update(b'\x00');d.update(sha(p).encode());d.update(b'\n')
 return d.hexdigest()
def json_file(path):
 path=Path(path);need(path.is_file() and not path.is_symlink(),'MISSING_'+path.name)
 return json.loads(path.read_text())
def atomic(path,obj):
 path=Path(path);need(not path.exists() and not path.is_symlink(),'OUTPUT_EXISTS_'+path.name)
 tmp=path.with_suffix(path.suffix+'.part');need(not tmp.exists() and not tmp.is_symlink(),'PART_EXISTS_'+tmp.name)
 with tmp.open('x') as f:json.dump(obj,f,indent=2,sort_keys=True);f.write('\n');f.flush();os.fsync(f.fileno())
 tmp.replace(path)
def replace_once(text,old,new,tag):
 need(text.count(old)==1,'ANCHOR_'+tag+'_'+str(text.count(old)))
 return text.replace(old,new,1)
def header(loc):return loc/'algorithms/PipNN/pipnn_utils.h'
def main_h(loc):return loc/'algorithms/PipNN/pipnn.h'

def make_fast_off(h):
 # Operate only inside the existing R71 exact Top-2 branch. All non-Top-2 code stays common.
 a=h.index('  if (MST_DEG == 2) {',h.index('#if defined(R71_H17_TOP2)'))
 b=h.index('  } else {\n#endif',a)
 seg=h[a:b]
 seg=replace_once(seg,'      size_t count = 0;\n','''      size_t count = 0;
      float r90_second_cutoff = std::numeric_limits<float>::infinity();
''','FAST_COUNT')
 seg=replace_once(seg,'        double d = packFloatAndInt(dist_ij, j);','''        if (count == 2 && dist_ij > r90_second_cutoff) continue;
        double d = packFloatAndInt(dist_ij, j);''','FAST_REJECT')
 seg=replace_once(seg,'          second = first;\n          first = d;','''          second = first;
          first = d;
          r90_second_cutoff = static_cast<float>(second);''','FAST_UPDATE1')
 seg=replace_once(seg,'          second = d;','''          second = d;
          r90_second_cutoff = static_cast<float>(second);''','FAST_UPDATE2')
 return h[:a]+seg+h[b:]

def graft_d6(h,d6,arm):
 # Copy only the source-tested D6 N2 branch into the R86 common snapshot.
 # Global counter definitions are copied exactly from original instrumented D6 source.
 d_start=d6.index('// R90-D6 separate diagnostic counters:')
 d_end=d6.index('// R90-D6 ends.',d_start)+len('// R90-D6 ends.')
 counter_block=d6[d_start:d_end]
 h=replace_once(h,'namespace parlayANN {\n','namespace parlayANN {\n\n'+counter_block+'\n','D6_GLOBAL')
 h_start=h.index('  if (MST_DEG == 2) {',h.index('#if defined(R71_H17_TOP2)'))
 h_end=h.index('  } else {\n#endif',h_start)+len('  } else {')
 d_start=d6.index('  if (MST_DEG == 2) {',d6.index('template<typename GraphH, typename PR>\nvoid eigen_knn'))
 d_end=d6.index('  } else {\n    std::vector<double> Q;',d_start)+len('  } else {')
 seg=d6[d_start:d_end]
 need('r90_d6_merge(r90_d6_local);' in seg and 'R90D6Local r90_d6_local' in seg,'D6_N2_NOT_EXACT')
 h=h[:h_start]+seg+h[h_end:]
 return h

def instrument_stock(h):
 # The frozen R86_COUNTERS code already counts Stock top2_q_writes and partial_sort_calls.
 # Do not pretend this counts internal SIMD shuffles or scalar assignments.
 need(h.count('r86::add(r86::Metric::top2_q_writes,')==1,'STOCK_Q_WRITE_COUNTER')
 need(h.count('r86::add(r86::Metric::partial_sort_calls,')==1,'STOCK_SORT_CALL_COUNTER')
 return h

def render(utils,pip,d6_ctrl,d6_fast,arm,mode):
 need(arm in ARMS and mode in MODES,'INVALID_ARM_MODE')
 if arm=='fast' and mode=='off': utils=make_fast_off(utils)
 if arm in ('h17','fast') and mode=='on':
  utils=graft_d6(utils,d6_ctrl if arm=='h17' else d6_fast,arm)
  pip=replace_once(pip,'    C.multiple_clustertrees(graph_h, Points, cluster_size, cluster_rounds);',
      '    C.multiple_clustertrees(graph_h, Points, cluster_size, cluster_rounds);\n    r90_d6_report("'+('ctrl' if arm=='h17' else 'fast')+'");','D6_REPORT')
 if arm=='stock' and mode=='on': utils=instrument_stock(utils)
 return utils,pip

def selftest():
 sample='''namespace parlayANN {\n#if defined(R71_H17_TOP2)\n  if (MST_DEG == 2) {\n      size_t count = 0;\n      for (indexType j = 0; j < N; ++j) {\n        float dist_ij = A;\n        double d = packFloatAndInt(dist_ij, j);\n        if (count == 0 || d < first) {\n          second = first;\n          first = d;\n        } else if (count == 1 || d < second) {\n          second = d;\n        }\n      }\n  } else {\n#endif\n'''
 z=make_fast_off(sample)
 need(z.count('r90_second_cutoff')==4 and 'dist_ij > r90_second_cutoff' in z,'SELFTEST_FAST')
 try:make_fast_off('not an original source')
 except ValueError:pass
 else:need(False,'SELFTEST_MISSING_ANCHOR')
 print(TAG+'_SELFTEST_PASS_ONE_SNAPSHOT_FAST_PATCH_AND_READONLY_GATES')

def preflight():
 for path in [header(BASE_SOURCE),main_h(BASE_SOURCE),header(D6/'source/ctrl'),header(D6/'source/fast'),BASES['SIFT1M'],BASES['MS-Turing1M'],SIFT10K]:
  need(path.is_file() and not path.is_symlink(),'FILE_NOT_FOUND_'+str(path))
 u=header(BASE_SOURCE).read_text();p=main_h(BASE_SOURCE).read_text();dc=header(D6/'source/ctrl').read_text();df=header(D6/'source/fast').read_text()
 need('R71_H17_TOP2' in u and 'r86::Metric::top2_q_writes' in u and 'R86_COUNTERS' in p,'SOURCE_FEATURES')
 for a in ARMS:
  for mode in MODES:
   x,y=render(u,p,dc,df,a,mode)
   need('eigen_knn' in x and 'C.multiple_clustertrees' in y,'RENDER_FAILED_'+a+mode)
 for n,pth in BASES.items():need(sha(pth)==BASE_SHAS[n],'DATA_SHA_'+n)
 # An offline CMake build requires these exact existing trees; this stage never builds.
 dep_status={k:str(p) for k,p in DEPS.items() if p.is_dir() and not p.is_symlink()}
 need(len(dep_status)==len(DEPS),'OFFLINE_DEPS_NOT_READY')
 need(not OUT.exists() and not OUT.is_symlink(),'OUTPUT_EXISTS')
 meta={'baseline_source':str(BASE_SOURCE),'source_tree_sha256':digest_tree(BASE_SOURCE),
  'd6_ctrl_utils_sha256':sha(header(D6/'source/ctrl')),'d6_fast_utils_sha256':sha(header(D6/'source/fast')),
  'data_sha256':BASE_SHAS,'deps':dep_status,'status':'LOCAL_SOURCE_TRANSFORM_GATE_PASS_NATIVE_COMPILE_NOT_RUN'}
 print(TAG+'_PREFLIGHT_PASS_SOURCE_SNAPSHOT_D6_COUNTER_BRANCH_SIFT1M_MST1M_DATA_SHA')
 return meta

def prepare():
 meta=preflight();OUT.mkdir(parents=True,exist_ok=False)
 for p in ('source','build','logs','graphs'):(OUT/p).mkdir()
 base_u=header(BASE_SOURCE).read_text();base_p=main_h(BASE_SOURCE).read_text()
 dc=header(D6/'source/ctrl').read_text();df=header(D6/'source/fast').read_text()
 variants=[]
 for mode in MODES:
  for arm in ARMS:
   name=arm+'_'+mode;dst=OUT/'source'/name
   shutil.copytree(BASE_SOURCE,dst,symlinks=False)
   u,p=render(base_u,base_p,dc,df,arm,mode)
   header(dst).write_text(u);main_h(dst).write_text(p)
   variants.append({'variant':name,'tree_sha256':digest_tree(dst),
    'utils_sha256':sha(header(dst)),'pipnn_sha256':sha(main_h(dst)),
    'base_source_sha256':meta['source_tree_sha256'],
    'status':'SOURCE_PREPARED_UNCOMPILED'})
 atomic(OUT/'source_manifest.json',{'status':'SOURCE_6_VARIANTS_PREPARED__NO_COMPILE_NO_BUILD',
  'protocol':'one R86 v1_2 snapshot; R71_H17_TOP2 flag; Fast localized cutoff; R86 ON source counters + D6 exact Top2 branch for H17/Fast',
  'input':meta,'variants':variants})
 print(TAG+'_PREPARE_PASS_SIX_ISOLATED_SOURCE_VARIANTS_UNCOMPILED')

def compiled_path(arm,mode):return OUT/'build'/(arm+'_'+mode)/'algorithms/PipNN/neighbors-pipnn_FLOAT_T_EUCLIDEAN'
def compile():
 meta=json_file(OUT/'source_manifest.json');need(meta['status'].startswith('SOURCE_6_VARIANTS_PREPARED'),'SOURCE_MANIFEST')
 cxx_binary=shutil.which('c++')
 need(bool(cxx_binary),'COMPILER_MISSING')
 cxx_binary=Path(cxx_binary).resolve()
 compiler_sha=sha(cxx_binary)
 compiler_version=subprocess.run([str(cxx_binary),'--version'],capture_output=True,text=True,check=True).stdout.splitlines()[0]
 for arm in ARMS:
  for mode in MODES:
   src=OUT/'source'/(arm+'_'+mode);record=next(x for x in meta['variants'] if x['variant']==arm+'_'+mode)
   need(digest_tree(src)==record['tree_sha256'],'SOURCE_TAMPER_'+arm+mode)
   flags='-O3 -pthread'
   if arm!='stock':flags+=' -DR71_H17_TOP2=1'
   if mode=='on':flags+=' -DR86_COUNTERS=1'
   bd=OUT/'build'/(arm+'_'+mode)
   opts=['cmake','-S',str(src),'-B',str(bd),'-DCMAKE_BUILD_TYPE=Release','-DCMAKE_CXX_FLAGS='+flags,
         '-DCMAKE_EXPORT_COMPILE_COMMANDS=ON','-DFETCHCONTENT_FULLY_DISCONNECTED=ON']
   for k,p in DEPS.items():opts.append('-DFETCHCONTENT_SOURCE_DIR_'+k+'='+str(p))
   for args,log in [(opts,OUT/'logs'/('configure_'+arm+'_'+mode+'.txt')),
                    (['cmake','--build',str(bd),'--target','neighbors-pipnn_FLOAT_T_EUCLIDEAN','--parallel','2'],OUT/'logs'/('compile_'+arm+'_'+mode+'.txt'))]:
    need(not log.exists(),'COMPILE_LOG_EXISTS_'+log.name)
    with log.open('x') as fp: rc=subprocess.run(args,stdout=fp,stderr=subprocess.STDOUT,check=False).returncode
    need(rc==0,'COMPILATION_FAILED_'+log.name)
   exe=compiled_path(arm,mode);need(exe.is_file(),'ELF_MISSING_'+arm+mode)
   cmake_cache=(bd/'CMakeCache.txt').read_text(errors='replace')
   match=re.search(r'^CMAKE_CXX_COMPILER:FILEPATH=(.+)$',cmake_cache,re.M)
   need(match is not None and Path(match.group(1)).resolve()==cxx_binary,'COMPILER_ID_DRIFT_'+arm+mode)
   need(sha(cxx_binary)==compiler_sha,'COMPILER_BINARY_DRIFT_'+arm+mode)
   print(TAG+'_COMPILE_PASS',arm,mode,sha(exe),'compiler_sha',compiler_sha,flush=True)
 atomic(OUT/'compile_manifest.json',{'status':'OFF_ON_SIX_BINARIES_COMPILED__PILOT_NOT_RUN',
  'cxx_binary':str(cxx_binary),'compiler_sha256':compiler_sha,'compiler_version':compiler_version,
  'binaries':{a+'_'+m:sha(compiled_path(a,m)) for a in ARMS for m in MODES}})
 print(TAG+'_COMPILE_SIX_BINARY_PASS_PILOT_REQUIRED')

def native_one(arm,mode,base,dataset,rep,cpu):
 name=f'{dataset}_{arm}_{mode}_r{rep}';exe=compiled_path(arm,mode);pin=json_file(OUT/'compile_manifest.json')
 need(sha(exe)==pin['binaries'][arm+'_'+mode],'ELF_SHA_'+name)
 graph=OUT/'graphs'/(name+'.graph');out=OUT/'logs'/(name+'.stdout');timefile=OUT/'logs'/(name+'.time')
 need(all(not f.exists() and not f.is_symlink() for f in (graph,out,timefile)),'OUTPUT_EXISTS_'+name)
 env=dict(os.environ);env.update({'PARLAY_NUM_THREADS':str(cpu),'OMP_NUM_THREADS':str(cpu),'LC_ALL':'C'})
 if mode=='on':
  pref=OUT/'logs'/name
  env.update({'R86_COUNTER_OUT':str(pref)+'.counters.jsonl','R86_LEAF_SIZE_OUT':str(pref)+'.leaf_sizes.jsonl',
    'R86_OCCUPANCY_OUT':str(pref)+'.occupancy.jsonl','R86_DEGREES_PREFIX':str(pref)+'.degrees'})
 flags=['-base_path',str(base),'-graph_outfile',str(graph),*FLAGS]
 aff='0,2,4,6' if cpu==4 else '0'
 cmd=['/usr/bin/time','-v','-o',str(timefile),'taskset','-c',aff,str(exe),*flags]
 print(TAG+'_BUILD_START',name,'CPU',cpu,'DIAGNOSTIC' if mode=='on' else 'TIMING_OFF',flush=True)
 with out.open('x') as fd: rc=subprocess.run(cmd,env=env,stdout=fd,stderr=subprocess.STDOUT,check=False).returncode
 need(rc==0,'BUILD_EXIT_'+name+'_'+str(rc));need(graph.is_file(),'GRAPH_MISSING_'+name)
 hdr=graph.open('rb').read(8);need(hdr==struct.pack('<II',10000 if dataset=='SIFT10K' else 1000000,64),'GRAPH_HEADER_'+name)
 record={'dataset':dataset,'arm':arm,'mode':mode,'rep':rep,'graph':str(graph),'graph_sha':sha(graph),
  'stdout':str(out),'stdout_sha':sha(out),'timefile':str(timefile),'timefile_sha':sha(timefile),
  'elf_sha':pin['binaries'][arm+'_'+mode],'threads':cpu,'NOT_A_TIMING_COMPARISON':mode=='on'}
 if mode=='on':
  rec=re.findall(r'^R90_D6_WORK .*$',out.read_text(errors='replace'),re.M)
  if arm=='stock':need(not rec,'STOCK_MUST_NOT_CLAIM_D6')
  else:
   need(len(rec)==1 and ('arm=ctrl' if arm=='h17' else 'arm=fast') in rec[0],'D6_WORK_LOG_'+name)
   record['d6_counter_line']=rec[0]
  co=Path(env['R86_COUNTER_OUT']);need(co.is_file(),'R86_WORK_LOG_'+name)
  record['r86_work_jsonl_sha']=sha(co)
 atomic(OUT/(name+'.json'),record)
 print(TAG+'_BUILD_PASS',name,'graph_sha',record['graph_sha'],flush=True)
 return record

def pilot10k():
 comp=json_file(OUT/'compile_manifest.json');need(comp['status'].startswith('OFF_ON'),'COMPILATION_MANIFEST')
 results=[]
 for mode in MODES:
  for arm in ARMS:results.append(native_one(arm,mode,SIFT10K,'SIFT10K',1,1))
 atomic(OUT/'pilot_manifest.json',{'status':'PILOT10K_6_BUILD_COMPLETE__AUDIT_REQUIRED','runs':results})
 print(TAG+'_PILOT10K_SIX_BUILD_COMPLETE_AUDIT_REQUIRED')

def auditpilot():
 p=json_file(OUT/'pilot_manifest.json');need(len(p['runs'])==6,'PILOT_COUNT')
 groups={}
 for run in p['runs']:
  need(sha(run['graph'])==run['graph_sha'] and sha(run['stdout'])==run['stdout_sha'],'PILOT_SHA')
  groups.setdefault(run['mode'],[]).append(run['graph_sha'])
 for mode in MODES:need(len(set(groups[mode]))==1,'PILOT10K_GRAPH_PARITY_'+mode)
 # OFF and ON instrumentation should not change graph semantics at CPU0.
 need(set(groups['off'])==set(groups['on']),'ON_OFF_GRAPH_DRIFT')
 atomic(OUT/'pilot_audit.json',{'status':'PILOT10K_6ARM_EXACT_GRAPH_PARITY_PASS','graph_sha':groups['off'][0]})
 print(TAG+'_PILOT10K_AUDIT_PASS_ALL_SIX_GRAPHS_SAME_SHA')

def full1m():
 audit=json_file(OUT/'pilot_audit.json');need(audit['status'].endswith('_PASS'),'PILOT_GATE')
 for k,path in BASES.items():need(sha(path)==BASE_SHAS[k],'SOURCE_DATA_SHA_'+k)
 runs=[]
 # OFF: 3 build graph repetitions for three arms and both datasets; ON: one build per arm and dataset
 for name,base in BASES.items():
  for rep in (1,2,3):
   for arm in {1:ARMS,2:('fast','stock','h17'),3:('h17','fast','stock')}[rep]:
    runs.append(native_one(arm,'off',base,name,rep,4))
  for arm in ARMS:runs.append(native_one(arm,'on',base,name,1,1))
 atomic(OUT/'full1m_manifest.json',{'status':'FULL_1M_OFF18_ON6_BUILD_COMPLETE__AUDIT_REQUIRED',
  'no_quality_search_yet':True,'runs':runs})
 print(TAG+'_FULL_1M_BUILD_COMPLETE_OFF18_ON6__AUDIT_REQUIRED')

def audit1m():
 p=json_file(OUT/'full1m_manifest.json');need(len(p['runs'])==24,'RUN_COUNT')
 for r in p['runs']:
  need(sha(r['graph'])==r['graph_sha'] and sha(r['stdout'])==r['stdout_sha'],'EVIDENCE_SHA_'+r['dataset']+r['arm'])
 for ds in BASES:
  on=[r for r in p['runs'] if r['dataset']==ds and r['mode']=='on']
  need(len(on)==3 and len({r['graph_sha'] for r in on})==1,'ON_GRAPH_PARITY_'+ds)
 atomic(OUT/'audit1m.json',{'status':'NATIVE_BUILD_OFF18_ON6_SOURCE_SHA_AUDIT_PASS__SEARCH_NOT_RUN',
  'warning':'Quality floor Search not measured on these new graph builds; do not call full thesis 1M matrix closed.',
  'diagnostic_on_timing_invalid':True,'all_24_graph_sha_verified':True})
 print(TAG+'_AUDIT1M_PASS_BUILD_ONLY_SEARCH_QUALITY_GATE_PENDING')

def main():
 p=argparse.ArgumentParser();p.add_argument('phase',choices=['selftest','preflight','prepare','compile','pilot10k','auditpilot','full1m','audit1m']);a=p.parse_args()
 try:globals()[a.phase]()
 except Exception as e:print(TAG+'_ERROR',str(e),file=sys.stderr);raise SystemExit(2)
if __name__=='__main__':main()
