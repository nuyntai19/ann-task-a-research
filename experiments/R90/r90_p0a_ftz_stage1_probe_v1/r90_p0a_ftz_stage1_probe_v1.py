#!/usr/bin/env python3
"""R90-P0A. One isolated native diagnostic bundle (NO original source/ELF/graph edits).

- SHA gates all six frozen original P0A ELF/graph/stdout/time artifacts.
- Links the *existing R86/P0A* static Highway archive into a NEW tiny binary.
- Tests packed subnormal keys under explicit FTZ/DAZ ON and OFF, with
  independent uint64 reference plus H17/Fast-style scalar Top2 controls.
- Re-runs EXISTING P0A Stock/H17/Fast OFF binaries 3 times each on SIFT10K,
  CPU0 single-threaded, in a NEW output dir only. Records buckets + graph SHA.
- Never runs Full1M or changes original P0A files. A synthetic witness alone
  does NOT prove the root cause of the historical Stock graph differences.
"""
from __future__ import annotations
import argparse,hashlib,importlib.util,json,os,re,shutil,struct,subprocess,sys,time
from collections import defaultdict
from pathlib import Path

HOME=Path.home(); R90=HOME/'ann-task-a/experiments/R90'
ORIGINAL=R90/'r90_p0a_unified_1m_three_arm_v1_1'
OLD_DIAG=R90/'r90_p0a_v11_pilot_hold_diagnostic_v1/diagnostic_report.json'
BASE=R90/'r90_p38_h17_top2_prefilter_native_v2/data/sift10k.fbin'
ORIG_PY=HOME/'Downloads/r90_p0a_unified_1m_three_arm_v1_1.py'
CPP=HOME/'Downloads/r90_p0a_ftz_highway_native_probe_v1.cpp'
OUT=R90/'r90_p0a_ftz_stage1_probe_v1'
P0A_PY_SHA='fa9cdc09b3f447161f5c1f65382b15a0bc9645f425a679b73ca26f5ce8abecf0'
SOURCE_MANIFEST_SHA='6e5d82c4ca331476240950afedfad970d8358fc7252d0d2b8b9ac441e1afb298'
PILOT_SHA='b45ab2841b6f8ade980735d9b5414b921366eeab65d48dd52e770b8aef5947c9'
DIAGNOSTIC_SHA='cffe7fb508b3d5550e9ea7a41a11fa41f101b23a0034cd6b4c051a15fec9e519'
COMPILER_SHA='1353e9bdd29a7295c7226bf6c63abccce056d8cac31f112e5cdbecc3f28c2769'
CPP_SHA='93275ee4d3d273caf2864b523986097b7631b5bdd1c9f710a1f3563ed17caebb'
ARMS=('stock','h17','fast');MODES=('off','on')
TAG='R90_P0A_FTZ_STAGE1_V1'

def guard(cond,msg):
 if not cond:raise RuntimeError(TAG+'_HOLD_'+msg)

def file(path,label):
 p=Path(path);guard(p.is_file() and not p.is_symlink(),label+'_MISSING_OR_SYMLINK')
 return p

def sha(path):
 d=hashlib.sha256()
 with file(path,'HASH').open('rb') as f:
  for buf in iter(lambda:f.read(4*1024*1024),b''):d.update(buf)
 return d.hexdigest()

def checked_sha(path,expected,label):
 guard(sha(path)==expected,label+'_SHA');return str(path)

def readj(path):return json.loads(file(path,'JSON').read_text())

def atomic(path,j):
 path=Path(path);guard(not path.exists() and not path.is_symlink(),'OUTPUT_EXISTS_'+path.name)
 tmp=path.with_suffix(path.suffix+'.part');guard(not tmp.exists(),'PART_EXISTS_'+tmp.name)
 with tmp.open('x') as f:json.dump(j,f,indent=2,sort_keys=True);f.write('\n');f.flush();os.fsync(f.fileno())
 tmp.replace(path)

def original_preflight():
 checked_sha(ORIG_PY,P0A_PY_SHA,'ORIGINAL_PY')
 checked_sha(CPP,CPP_SHA,'CPP_SOURCE')
 checked_sha(ORIGINAL/'source_manifest.json',SOURCE_MANIFEST_SHA,'SOURCE_MANIFEST')
 checked_sha(ORIGINAL/'pilot_manifest.json',PILOT_SHA,'PILOT_MANIFEST')
 checked_sha(OLD_DIAG,DIAGNOSTIC_SHA,'PREVIOUS_DIAGNOSTIC')
 source=readj(ORIGINAL/'source_manifest.json')
 comp=readj(ORIGINAL/'compile_manifest.json')
 pilot=readj(ORIGINAL/'pilot_manifest.json')
 old=readj(OLD_DIAG)
 guard(source['status']=='SOURCE_6_VARIANTS_PREPARED__NO_COMPILE_NO_BUILD','SRC_STATUS')
 guard(pilot['status']=='PILOT10K_6_BUILD_COMPLETE__AUDIT_REQUIRED','PILOT_STATUS')
 guard(comp['status']=='OFF_ON_SIX_BINARIES_COMPILED__PILOT_NOT_RUN','COMP_STATUS')
 guard(comp['compiler_sha256']==COMPILER_SHA==old['compiler_sha256'],'COMPILER_SHA_IN_MANIFEST')
 cxx=file(comp['cxx_binary'],'CXX');guard(sha(cxx)==COMPILER_SHA,'COMPILER_EXECUTABLE_HASH')
 guard(len(pilot['runs'])==6 and len(source['variants'])==6,'VARIANT_COUNT')
 spec=importlib.util.spec_from_file_location('r90_p0a_v11_pinned_for_probe',ORIG_PY)
 guard(spec is not None and spec.loader is not None,'SOURCE_IMPORT_SPEC')
 mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
 expected={a+'_'+m for a in ARMS for m in MODES}
 guard({x['variant'] for x in source['variants']}==expected,'SOURCE_VARIANTS')
 guard(set(comp['binaries'])==expected,'COMP_BINARY_KEYS')
 for v in source['variants']:
  root=ORIGINAL/'source'/v['variant']
  guard(mod.digest_tree(root)==v['tree_sha256'],'TREE_DRIFT_'+v['variant'])
  guard(mod.sha(mod.header(root))==v['utils_sha256'],'HEADER_DRIFT_'+v['variant'])
  guard(mod.sha(mod.main_h(root))==v['pipnn_sha256'],'PIPNN_DRIFT_'+v['variant'])
 for rec in pilot['runs']:
  name=rec['arm']+'_'+rec['mode']
  guard(name in expected and rec['dataset']=='SIFT10K' and rec['threads']==1,'PILOT_CONTEXT_'+name)
  guard(sha(rec['graph'])==rec['graph_sha']==old['results'][name]['graph_sha256'],'ORIG_GRAPH_SHA_'+name)
  guard(sha(rec['stdout'])==rec['stdout_sha']==old['results'][name]['stdout_sha256'],'ORIG_STDOUT_SHA_'+name)
  guard(sha(rec['timefile'])==rec['timefile_sha']==old['results'][name]['timefile_sha256'],'ORIG_TIME_SHA_'+name)
  exe=mod.compiled_path(rec['arm'],rec['mode'])
  guard(sha(exe)==comp['binaries'][name]==rec['elf_sha']==old['results'][name]['elf_sha256'],'ORIG_BINARY_SHA_'+name)
  if rec['mode']=='on':
   log=ORIGINAL/'logs'/('SIFT10K_'+rec['arm']+'_'+rec['mode']+'_r1.counters.jsonl')
   guard(sha(log)==rec['r86_work_jsonl_sha'],'ORIG_COUNTER_SHA_'+name)
 base=file(BASE,'SIFT10K_BASE');size=base.stat().st_size
 with base.open('rb') as f:n,d=struct.unpack('<II',f.read(8))
 guard((n,d,size)==(10000,128,8+10000*128*4),'SIFT10K_HEADER')
 for util in ('cmake','taskset'):
  guard(shutil.which(util) is not None,'UTIL_'+util)
 guard(file('/usr/bin/time','GNU_TIME').exists(),'GNU_TIME')
 if hasattr(os,'sched_getaffinity'):guard(0 in os.sched_getaffinity(0),'CPU0_UNAVAILABLE')
 need_cmake=(ORIGINAL/'source/stock_off/CMakeLists.txt').read_text()
 guard('-ffast-math' in need_cmake and '-march=native' in need_cmake,'ORIGINAL_CMAKE_FLOAT_FLAGS')
 hwy=Path(source['input']['deps']['HIGHWAY'])
 guard(hwy==HOME/'ann-task-a/experiments/R86/r86_v1_2_builds/stock_off/_deps/highway-src','HWY_SOURCE_PATH_CHANGED')
 guard(file(hwy/'hwy/contrib/sort/vqsort.h','HWY_HEADER').exists(),'HWY_HEADER')
 # Require the original Highway archive produced by the stock_off P0A build.
 highbuild=ORIGINAL/'build/stock_off/_deps/highway-build'
 guard(highbuild.is_dir() and not highbuild.is_symlink(),'HIGHWAY_BUILD_DIR_MISSING')
 archive_candidates=sorted(p for p in highbuild.rglob('libhwy_contrib.a') if p.is_file() and not p.is_symlink())
 core_candidates=sorted(p for p in highbuild.rglob('libhwy.a') if p.is_file() and not p.is_symlink())
 guard(len(archive_candidates)==1 and len(core_candidates)==1,'HIGHWAY_ARCHIVE_UNIQUE_'+str(len(archive_candidates))+'_'+str(len(core_candidates)))
 contrib,core=archive_candidates[0],core_candidates[0]
 guard(contrib.stat().st_size>10000 and core.stat().st_size>1000,'HIGHWAY_ARCHIVE_SUSPICIOUS_SIZE')
 # The CMake export include may reside here; never pick a system or new Highway dependency.
 result={
  'original_source_manifest_sha256':SOURCE_MANIFEST_SHA,'original_pilot_manifest_sha256':PILOT_SHA,
  'original_diagnostic_sha256':DIAGNOSTIC_SHA,'original_python_sha256':P0A_PY_SHA,
  'original_compiler_sha256':COMPILER_SHA,'compiler_binary':str(cxx),
  'existing_six_binary_graph_and_log_sha_checked':True,
  'sift10k_base_sha256_observed_this_run':sha(BASE),
  'sift10k_base_header':{'n':n,'dim':d,'size_bytes':size},
  'hwy_header':str(hwy/'hwy/contrib/sort/vqsort.h'),
  'hwy_header_sha256':sha(hwy/'hwy/contrib/sort/vqsort.h'),
  'hwy_source':str(hwy),'hwy_build_dir':str(highbuild),
  'hwy_contrib_archive':str(contrib),'hwy_contrib_archive_sha256':sha(contrib),
  'hwy_core_archive':str(core),'hwy_core_archive_sha256':sha(core),
  'probe_cpp_sha256':CPP_SHA,
  'previous_source_graph_sha':{x['arm']+'_'+x['mode']:x['graph_sha'] for x in pilot['runs']},
  'prior_pilot_status':'AUDITPILOT_HOLD_CROSS_ARM_GRAPH_SHA',
 }
 print(TAG+'_PREFLIGHT_PASS_SIX_ORIGINAL_SHA_AND_EXACT_HIGHWAY_STATIC_ARCHIVES',flush=True)
 return result,mod

def parse_keyvals(line):
 fields=line.split();guard(len(fields)>1,'PARSE_EMPTY')
 out={'tag':fields[0]}
 for pair in fields[1:]:
  guard(pair.count('=')==1,'PARSE_NONKV_'+pair)
  k,v=pair.split('=',1);guard(k not in out and k,'DUPKEY_'+k)
  out[k]=v
 return out

def parse_hwy_stdout(txt):
 lines=[x.strip() for x in txt.splitlines() if x.strip()]
 guard(len(lines)==2+126,'HWY_PROBE_LINE_COUNT_'+str(len(lines)))
 start=parse_keyvals(lines[0]);end=parse_keyvals(lines[-1]);guard(start['tag']=='PROBE_BEGIN' and end['tag']=='PROBE_DONE','HWY_SENTINELS')
 guard(start['compiler_fast_math']=='1' and start['float64_available']=='1','HWY_SUPPORT_FAST_MATH')
 guard(end['mxcsr_restored']==start['initial_mxcsr'],'HWY_MXCSR_NOT_RESTORED')
 rows=[];keys=set()
 for line in lines[1:-1]:
  d=parse_keyvals(line)
  guard(d['tag']=='CASE' and d['mode'] in ('on','off'),'HWY_CASE_MODE')
  guard(d['kind'] in ('zero12_tail','zero12_front','zero12_and45'),'HWY_KIND')
  n=int(d['n']);rep=int(d['rep'])
  guard(n in (2,8,16,32,64,189,512) and rep in (1,2,3),'HWY_N_REP')
  k=(d['mode'],n,d['kind'],rep);guard(k not in keys,'HWY_DUP_CASE');keys.add(k)
  guard(d['flags_valid']=='1','HWY_FLAGS_NOT_SET')
  guard(int(d['mxcsr_before'],16)&0x8040==(0x8040 if d['mode']=='on' else 0),'HWY_MXCSR_INVALID')
  guard(int(d['mxcsr_after'],16)&0x8040==(0x8040 if d['mode']=='on' else 0),'HWY_MXCSR_CHANGED_INSIDE_SORT')
  guard(d['injected_bits']=='0x000000000000000c','HWY_PACKED_SUBNORMAL_TEST_DRIFT')
  for j in ('highway_exact','h17_exact','fast_exact','raw_multiset_preserved','index12_survives','zero_bits_introduced'):guard(d[j] in ('0','1'),'HWY_BOOLEAN_'+j)
  rows.append(d)
 guard(len(keys)==126,'HWY_NOT_126_UNIQUE')
 pairs=defaultdict(dict)
 for row in rows:pairs[(int(row['n']),row['kind'],int(row['rep']))][row['mode']]=row
 for x in pairs.values():guard(set(x)=={'on','off'},'HWY_PAIRED_MODE_MISSING')
 delta=[k for k,x in pairs.items() if x['off']['highway_exact']!=x['on']['highway_exact']]
 off_bad=sum(x['highway_exact']=='0' for x in rows if x['mode']=='off')
 on_bad=sum(x['highway_exact']=='0' for x in rows if x['mode']=='on')
 witnesses=[{k:r[k] for k in ('mode','n','kind','rep','mxcsr_before','mxcsr_after','ref0','ref1','highway0','highway1','h17_0','h17_1','fast_0','fast_1','highway_exact','h17_exact','fast_exact')}
            for r in rows if r['highway_exact']=='0']
 if any(x['off']['raw_multiset_preserved']=='1' and x['on']['raw_multiset_preserved']=='0' for x in pairs.values()):
  status='CONTROLLED_FTZ_DAZ_PACKED_KEY_BIT_MUTATION_WITNESS'
 elif any(x['off']['highway_exact']=='1' and x['on']['highway_exact']=='0' for x in pairs.values()):
  status='FTZ_DAZ_DEPENDENT_TOP2_ORDER_ONLY_NO_BIT_MUTATION_PROVEN'
 elif off_bad:
  status='HIGHWAY_SORT_MISMATCH_ALSO_WITH_FTZ_DAZ_OFF'
 else:
  status='NO_HIGHWAY_SORT_MISMATCH_IN_TESTED_CASES'
 return {'classification':status,'case_count':len(rows),'mismatch_off':off_bad,'mismatch_on':on_bad,
         'paired_mode_changed_cases':len(delta),'bit_mutation_off':sum(x['raw_multiset_preserved']=='0' for x in rows if x['mode']=='off'),'bit_mutation_on':sum(x['raw_multiset_preserved']=='0' for x in rows if x['mode']=='on'),'mismatch_examples':witnesses[:30],
         'per_case':rows,'interpretation':'Controlled synthetic Highway sort; a reproduced bit mismatch does not alone prove cause of any historical graph edge.'}

def parse_build_stdout(txt):
 def vals(pat):return [int(v) for v in re.findall(pat,txt,re.M)]
 b=vals(r'^\s*Total buckets:\s*(\d+)\s*$')
 pts=vals(r'^\s*Total points:\s*(\d+)\s*$')
 cmp=vals(r'^\s*# of comparisons during clustering:\s*(\d+)\s*$')
 guard(len(b)==len(pts)==len(cmp)==2,'BUILD_STAGE1_PARSE_INCOMPLETE')
 return {'buckets':b,'total_points':pts,'clustering_cmps_cumulative':cmp}

def graph_quick(path):
 p=file(path,'GRAPH');length=p.stat().st_size
 with p.open('rb') as f:
  n,maxdeg=struct.unpack('<II',f.read(8))
  guard(n==10000 and maxdeg==64,'GRAPH_HEADER');raw=f.read(4*n)
 degrees=struct.unpack('<'+str(n)+'I',raw)
 guard(all(0<=d<=maxdeg for d in degrees),'GRAPH_DEGREE');arcs=sum(degrees)
 guard(length==8+4*n+4*arcs,'GRAPH_FILE_SIZE')
 return {'n':n,'max_degree':maxdeg,'arcs':arcs,'sha256':sha(p)}

def one_build(arm,rep,pin,mod):
 name=f'SIFT10K_{arm}_off_probe_r{rep}';exe=mod.compiled_path(arm,'off')
 guard(sha(exe)==pin['previous_elf_shas'][arm+'_off'],'ORIG_ELF_SHA_'+arm)
 graph=OUT/'graphs'/(name+'.graph');std=OUT/'logs'/(name+'.stdout');tfile=OUT/'logs'/(name+'.time')
 guard(not any(p.exists() or p.is_symlink() for p in (graph,std,tfile)),'EXISTING_NEW_PROBE_LOGS_'+name)
 cmd=['/usr/bin/time','-v','-o',str(tfile),'taskset','-c','0',str(exe),'-base_path',str(BASE),'-graph_outfile',str(graph),*mod.FLAGS]
 env=dict(os.environ);env.update({'PARLAY_NUM_THREADS':'1','OMP_NUM_THREADS':'1','LC_ALL':'C'})
 print(TAG+'_BUILD_START',name,flush=True)
 with std.open('x') as f:rc=subprocess.run(cmd,env=env,stdout=f,stderr=subprocess.STDOUT,check=False).returncode
 guard(rc==0,'BUILD_RC_'+name+'_'+str(rc))
 guard(graph.is_file() and tfile.is_file(),'BUILD_MISSING_OUTPUT_'+name)
 stages=parse_build_stdout(std.read_text(errors='replace'))
 record={'name':name,'arm':arm,'rep':rep,'elf_sha256':pin['previous_elf_shas'][arm+'_off'],
         'stdout_sha256':sha(std),'timefile_sha256':sha(tfile),'graph':graph_quick(graph),
         'stage1':stages,'threads':1,'cpu_affinity':'0','timing_not_used_for_production':True}
 atomic(OUT/(name+'.json'),record)
 print(TAG+'_BUILD_PASS',name,'buckets',stages['buckets'],'graph_sha',record['graph']['sha256'],flush=True)
 return record

def selftest():
 fake=('PROBE_BEGIN compiler_fast_math=1 initial_mxcsr=0x00001f80 float64_available=1\n')
 for m in ('off','on'):
  for n in (2,8,16,32,64,189,512):
   for kind in ('zero12_tail','zero12_front','zero12_and45'):
    for rep in (1,2,3):
     fake+=(f'CASE mode={m} n={n} kind={kind} rep={rep} mxcsr_before={"0x00009fc0" if m=="on" else "0x00001f80"} mxcsr_after={"0x00009fc0" if m=="on" else "0x00001f80"} '
       'injected_bits=0x000000000000000c ref0=0x000000000000000c ref1=0x3ff0000000000000 '
       'highway0=0x000000000000000c highway1=0x3ff0000000000000 h17_0=0x000000000000000c h17_1=0x3ff0000000000000 '
       'fast_0=0x000000000000000c fast_1=0x3ff0000000000000 highway_exact=1 h17_exact=1 fast_exact=1 raw_multiset_preserved=1 index12_survives=1 zero_bits_introduced=0 flags_valid=1\n')
 fake+='PROBE_DONE mxcsr_restored=0x00001f80\n'
 z=parse_hwy_stdout(fake);guard(z['case_count']==126 and z['mismatch_on']==0,'SYNTHETIC_PARSER')
 guard(parse_build_stdout('Total buckets: 474\nTotal points: 222585\n# of comparisons during clustering: 1827627\nTotal buckets: 499\nTotal points: 230942\n# of comparisons during clustering: 3734009')=={'buckets':[474,499],'total_points':[222585,230942],'clustering_cmps_cumulative':[1827627,3734009]},'STAGE1_PARSER')
 print(TAG+'_SELFTEST_PASS_PARSER_126_CASES_STAGE1_NO_FULL1M')

def preflight():
 pin,mod=original_preflight()
 print(TAG+'_STAGE1_SIFT10K_BASE_SHA',pin['sift10k_base_sha256_observed_this_run'])
 return pin,mod

def run():
 pin,mod=original_preflight()
 guard(not OUT.exists() and not OUT.is_symlink(),'OUTPUT_DIR_ALREADY_EXISTS')
 OUTPUT_EXE=OUT/'bin/highway_ftz_probe'
 OUT.mkdir(parents=True,exist_ok=False)
 for sub in ('logs','graphs','bin'):(OUT/sub).mkdir()
 # Re-use precisely the validated compiler from the original P0A 6arm native build.
 compiler=pin['compiler_binary'];hwy=pin['hwy_source'];build=pin['hwy_build_dir']
 contrib=pin['hwy_contrib_archive'];core=pin['hwy_core_archive']
 compile_cmd=[compiler,'-std=c++17','-O3','-march=native','-ffast-math','-pthread',
              '-I',hwy,'-I',build,str(CPP),str(contrib),str(core),'-ldl','-o',str(OUTPUT_EXE)]
 pin['probe_compile_flags']=compile_cmd[1:6]
 pin['previous_elf_shas']=readj(ORIGINAL/'compile_manifest.json')['binaries']
 compile_log=OUT/'logs/highway_probe_compile.txt'
 with compile_log.open('x') as f:compile_rc=subprocess.run(compile_cmd,stdout=f,stderr=subprocess.STDOUT,check=False).returncode
 guard(compile_rc==0,'NEW_HIGHWAY_PROBE_COMPILE_FAILED__SEE_'+str(compile_log))
 guard(OUTPUT_EXE.is_file(),'HIGHWAY_EXE_MISSING')
 pin['probe_elf_sha256']=sha(OUTPUT_EXE)
 out=OUT/'logs/highway_probe.stdout'
 with out.open('x') as f:probe_rc=subprocess.run(['taskset','-c','0',str(OUTPUT_EXE)],stdout=f,stderr=subprocess.STDOUT,check=False).returncode
 guard(probe_rc==0,'HIGHWAY_PROBE_PROCESS_EXIT_'+str(probe_rc))
 hwy_result=parse_hwy_stdout(out.read_text(errors='replace'))
 hwy_result['stdout_sha256']=sha(out)
 print(TAG+'_HIGHWAY_DONE',hwy_result['classification'],'off_mismatch',hwy_result['mismatch_off'],'on_mismatch',hwy_result['mismatch_on'],flush=True)
 runs=[]
 for rep in (1,2,3):
  for arm in {1:ARMS,2:('h17','fast','stock'),3:('fast','stock','h17')}[rep]:
   runs.append(one_build(arm,rep,pin,mod))
 byarm={}
 for arm in ARMS:
  a=[x for x in runs if x['arm']==arm]
  byarm[arm]={'round1_buckets':[x['stage1']['buckets'][0] for x in a],
              'round2_buckets':[x['stage1']['buckets'][1] for x in a],
              'final_clustering_cmps':[x['stage1']['clustering_cmps_cumulative'][-1] for x in a],
              'graph_shas':[x['graph']['sha256'] for x in a],
              'graph_sha_unique_count':len(set(x['graph']['sha256'] for x in a)),
              'round2_bucket_unique_count':len(set(x['stage1']['buckets'][1] for x in a))}
 report={'status':'NATIVE_HIGHWAY_PROBE_AND_THREE_REPS_EACH_ARM_COMPLETE__FULL1M_NOT_AUTHORIZED',
         'source_pins':pin,'highway_probe':hwy_result,'stage1_sift10k_repetitions':runs,
         'stage1_per_arm':byarm,'facts_and_limitations':[
            'The native synthetic Highway bit witness can establish a controlled FTZ/DAZ-dependent packed key change, not causation of the original Stock graph edges.',
            'A change in bucket count or graph SHA is evidence of non-reproducibility, not a direct leaf membership fingerprint or proof of random pivot seed.',
            'This bundle does NOT test Recall@10; old P0A auditpilot/full1m must remain HOLD until a separate quality-aware v1.2 gate is validated.',
            'Three repetitions per arm are small diagnostic samples and cannot establish a universal probability of drift.'
         ]}
 atomic(OUT/'probe_report.json',report)
 print(TAG+'_REPORT',OUT/'probe_report.json','sha256',sha(OUT/'probe_report.json'),flush=True)
 print(TAG+'_NO_ORIGINAL_BINARY_OR_GRAPH_MODIFICATION_NO_FULL1M',flush=True)

def audit():
 report=readj(OUT/'probe_report.json')
 guard(report['status'].startswith('NATIVE_HIGHWAY_PROBE_AND_THREE_REPS'),'REPORT_STATUS')
 guard(report['highway_probe']['case_count']==126,'HWY_CASE_COUNT')
 guard(len(report['stage1_sift10k_repetitions'])==9,'STAGE1_NINE')
 guard(all(len(report['stage1_per_arm'][arm]['graph_shas'])==3 for arm in ARMS),'STAGE1_ARM_THREE')
 for rec in report['stage1_sift10k_repetitions']:
  p=OUT/'graphs'/(rec['name']+'.graph')
  guard(sha(p)==rec['graph']['sha256'],'REPLAY_GRAPH_SHA_'+rec['name'])
  for ext,key in [('stdout','stdout_sha256'),('time','timefile_sha256')]:
   guard(sha(OUT/'logs'/(rec['name']+'.'+ext))==rec[key],'REPLAY_LOG_SHA_'+rec['name']+ext)
 guard(sha(OUT/'bin/highway_ftz_probe')==report['source_pins']['probe_elf_sha256'],'REPLAY_HIGHWAY_ELF')
 guard(sha(OUT/'logs/highway_probe.stdout')==report['highway_probe']['stdout_sha256'],'REPLAY_HIGHWAY_LOG')
 print(TAG+'_AUDIT_PASS_126_CONTROLLED_CASES_AND_NINE_NATIVE_SIFT10K_REBUILDS__NO_FULL1M',flush=True)
 print(TAG+'_FINAL_REPORT',OUT/'probe_report.json','sha256',sha(OUT/'probe_report.json'),flush=True)

def main():
 cli=argparse.ArgumentParser();cli.add_argument('phase',choices=('selftest','preflight','run','audit'));arg=cli.parse_args()
 try:globals()[arg.phase]()
 except Exception as e:
  print(TAG+'_HOLD',str(e),file=sys.stderr);raise SystemExit(2)
if __name__=='__main__':main()
