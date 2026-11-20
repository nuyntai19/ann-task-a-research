#!/usr/bin/env python3
"""R90 P0A v1.3 — historical Highway one-variable controlled rebuild.

STAGE A: copy exact six original P0A v1.1 source trees (no edits), compile
six fresh OFF/ON ELF with H85 Highway 6bc2d477 only, run controlled MXCSR
probe and six SIFT10K native pilot BUILDs, quality-aware audit.
STAGE B: only after Stage A audit PASS, build ONE Stock SIFT1M OFF graph,
check graph/v0/exact duplicates and native held-out Recall@10 beams 80/160.

NO earlier source/binary/graph mutation. NO 24-run 1M campaign or 10M build.
"""
from __future__ import annotations
import argparse, array, hashlib, importlib.util, json, math, mmap, os, re, shutil, struct, subprocess, sys, tempfile
from collections import Counter
from pathlib import Path

HOME=Path.home();ROOT=HOME/'ann-task-a';R90=ROOT/'experiments/R90'
PREV=R90/'r90_p0a_unified_1m_three_arm_v1_1'
OUT=R90/'r90_p0a_v13_historical_highway_6bc2_controlled_v1'
ORIG_PY=HOME/'Downloads/r90_p0a_unified_1m_three_arm_v1_1.py'
CPP=HOME/'Downloads/r90_p0a_v13_hwy_old_ftz_probe_v1.cpp'
H85=ROOT/'experiments/H85/r85_0_matched_baseline/build_stock/_deps/highway-src'
R86_HWY=ROOT/'experiments/R86/r86_v1_2_builds/stock_off/_deps/highway-src'
SIFT10K=R90/'r90_p38_h17_top2_prefilter_native_v2/data/sift10k.fbin'
SIFT1M=ROOT/'data/sift1m.fbin';QUERIES=ROOT/'data/sift1m_queries.fbin';GT=ROOT/'data/sift1m_gt.ibin'
EVAL=ROOT/'experiments/H70/build-r70/algorithms/PipNN/r72_graph_recall'
REPORT_V0=HOME/'R90_HIGHWAY_VERSION_V0_READONLY_v1_report.json'
SOURCE_SHA='6e5d82c4ca331476240950afedfad970d8358fc7252d0d2b8b9ac441e1afb298'
ORIG_SCRIPT_SHA='fa9cdc09b3f447161f5c1f65382b15a0bc9645f425a679b73ca26f5ce8abecf0'
COMPILER_SHA='1353e9bdd29a7295c7226bf6c63abccce056d8cac31f112e5cdbecc3f28c2769'
PILOT_OLD_SHA='b45ab2841b6f8ade980735d9b5414b921366eeab65d48dd52e770b8aef5947c9'
V0_REPORT_SHA='7562055b2a548c67c4831570ae1923918fbafa762a25c4cb5b0230d4264e7d50'
SIFT10K_SHA='94320c4336a35f046de768a24ada57aa8998f511df9aa2a7c72fe9ed8c67c1f5'
SIFT1M_SHA='8c7b3d999ba3133f865af72df078f77c2d248fdb80571d7ea1f1bb8e1750658e'
Q_SHA='9b0082b67d0ac55b4c7d42216560344567ad87ce3e75a9d5214a0762f1c15d65'
GT_SHA='047418d19f3981e4fc2dd28ae3b6f72fa7108f40d9336bd2d80b07829885ba13'
EVAL_SHA='3c2294efa1d7fb5d89c79ca5bf9c1eaca86247f7246e6d6d7c6c94549d08ed57'
CPP_SHA='93275ee4d3d273caf2864b523986097b7631b5bdd1c9f710a1f3563ed17caebb'
ARMS=('stock','h17','fast');MODES=('off','on')
OLD_FILES={
 'traits-inl.h':('b02ed8b9ab0d2e7d3d70f48c74f006531ff54753','1ff31627d815e2f9690ecb1fdfdd53132c7b11858036bc4b645d848e1503cab7'),
 'sorting_networks-inl.h':('54b15230730ef3785ae1eaa09ce97485ce917021','ccfa81cecbfe05410941093b9d019f849832d81d170568c71ceedfbc64ae552b')}
NEW_FILES={
 'traits-inl.h':('3a4d8506e6794432009c70ac312380b1d2ba801b','ba1f0797074f2571d99eeab223a58c8480e050d61b0cbf122300c511580feaac'),
 'sorting_networks-inl.h':('92c2dfad48291f0c194d85f1bbe05dc6aee8d71a','ce8e82e95bb897ab72e6bd6b8dc801d5dde44bcb642dbdef218173637b967403')}
TAG='R90_P0A_V13_H85HWY'

def need(ok,msg):
 if not ok:raise RuntimeError(TAG+'_HOLD_'+str(msg))

def regular(p):
 p=Path(p);return p.is_file() and not p.is_symlink()

def sha(p):
 need(regular(p),'FILE_MISSING_OR_SYMLINK_'+str(p))
 h=hashlib.sha256()
 with Path(p).open('rb') as fp:
  for block in iter(lambda:fp.read(4<<20),b''):h.update(block)
 return h.hexdigest()

def pin(p,wanted,label):need(sha(p)==wanted,'SHA_'+label)

def js(p):return json.loads(Path(p).read_text()) if regular(p) else need(False,'JSON_MISSING_'+str(p))

def write(path,obj):
 path=Path(path);tmp=path.with_name(path.name+'.part')
 need(not path.exists() and not path.is_symlink() and not tmp.exists() and not tmp.is_symlink(),'OUTPUT_EXISTS_'+str(path))
 with tmp.open('x') as f:
  json.dump(obj,f,indent=2,sort_keys=True,ensure_ascii=False,allow_nan=False);f.write('\n');f.flush();os.fsync(f.fileno())
 os.replace(tmp,path)

def blob_sha(p):
 content=Path(p).read_bytes();return hashlib.sha1(b'blob '+str(len(content)).encode()+b'\x00'+content).hexdigest()

def hwy_gate(root,checks,label):
 need(root.is_dir() and not root.is_symlink(),'HIGHWAY_SOURCE_ROOT_'+label)
 blobs={}
 for name,(wanted_blob,wanted_sha) in checks.items():
  p=root/'hwy/contrib/sort'/name;pin(p,wanted_sha,'HIGHWAY_'+label+'_'+name)
  need(blob_sha(p)==wanted_blob,'BLOB_'+label+'_'+name)
  blobs[name]={'sha256':wanted_sha,'git_blob_sha1':wanted_blob}
 return blobs

def original_module():
 pin(ORIG_PY,ORIG_SCRIPT_SHA,'V11_RUNNER')
 spec=importlib.util.spec_from_file_location('r90_v13_import_frozen_v11',ORIG_PY)
 need(spec is not None and spec.loader is not None,'V11_SPEC')
 mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
 need(mod.OUT==PREV and tuple(mod.ARMS)==ARMS and tuple(mod.MODES)==MODES,'V11_API')
 return mod

def source_gate():
 pin(REPORT_V0,V0_REPORT_SHA,'V0_REPORT')
 report=js(REPORT_V0)
 need(report['status']=='NATIVE_READONLY_SOURCE_REVISION_AND_V0_GRAPH_OBSERVATION_COMPLETE','V0_REPORT_STATUS')
 need(report['old_new_highway_source']['old']['source_root']==str(H85),'OLD_HWY_PATH')
 hwy_gate(H85,OLD_FILES,'H85');hwy_gate(R86_HWY,NEW_FILES,'R86')
 # Require the exact historical checked-out commit, not just a directory name.
 cmd=subprocess.run(['git','-C',str(H85),'rev-parse','HEAD'],capture_output=True,text=True)
 need(cmd.returncode==0 and re.fullmatch(r'[0-9a-f]{40}',cmd.stdout.strip()) is not None,'H85_HIGHWAY_GIT_HEAD_MISSING')
 commit=cmd.stdout.strip()
 need(commit.startswith('6bc2d477'),'H85_HIGHWAY_COMMIT_DRIFT_'+commit)
 dirty=subprocess.run(['git','-C',str(H85),'diff','--quiet','HEAD','--'],capture_output=True)
 need(dirty.returncode==0,'H85_HIGHWAY_TRACKED_SOURCE_DIRTY')
 return {'expected_commit_prefix':'6bc2d477','git_head':commit,'source_root':str(H85),'git_blobs':hwy_gate(H85,OLD_FILES,'H85')}

def base_gate():
 mod=original_module()
 pin(PREV/'source_manifest.json',SOURCE_SHA,'V11_SOURCE_MANIFEST')
 pin(PREV/'pilot_manifest.json',PILOT_OLD_SHA,'V11_PILOT_MANIFEST')
 pin(SIFT10K,SIFT10K_SHA,'SIFT10K')
 pin(CPP,CPP_SHA,'CONTROL_CPP')
 hwy=source_gate()
 src=js(PREV/'source_manifest.json')
 comp=js(PREV/'compile_manifest.json')
 need(comp['compiler_sha256']==COMPILER_SHA,'ORIGINAL_COMPILER_SHA')
 pin(Path(comp['cxx_binary']),COMPILER_SHA,'COMPILER_BINARY')
 names={a+'_'+b for a in ARMS for b in MODES}
 need({r['variant'] for r in src['variants']}==names and set(comp['binaries'])==names,'SIX_VARIANT_NAMES')
 for rec in src['variants']:
  root=PREV/'source'/rec['variant']
  need(mod.digest_tree(root)==rec['tree_sha256'],'OLD_SOURCE_TREE_'+rec['variant'])
  need(sha(mod.header(root))==rec['utils_sha256'] and sha(mod.main_h(root))==rec['pipnn_sha256'],'OLD_SOURCE_FILES_'+rec['variant'])
  exe=PREV/'build'/rec['variant']/'algorithms/PipNN/neighbors-pipnn_FLOAT_T_EUCLIDEAN'
  pin(exe,comp['binaries'][rec['variant']],'ORIGINAL_ELF_'+rec['variant'])
 need((PREV/'source/stock_off/CMakeLists.txt').read_text().count('-ffast-math')>=1,'EXPECTED_FAST_MATH_FLAG')
 need(0 in os.sched_getaffinity(0),'CPU0_NOT_AVAILABLE')
 for util in ('cmake','taskset','git'):
  need(shutil.which(util) is not None,'TOOL_MISSING_'+util)
 need(regular('/usr/bin/time'),'GNU_TIME')
 return mod,src,comp,hwy

def preflight():
 mod,src,comp,hwy=base_gate()
 need(not OUT.exists() and not OUT.is_symlink(),'V13_OUTPUT_ALREADY_EXISTS_DO_NOT_REPREPARE')
 print(TAG+'_PREFLIGHT_PASS_6_SOURCE_SHA_COMPILER_H85_HIGHWAY_COMMIT_BLOBS',flush=True)

def prepare():
 mod,source,comp,hwy=base_gate()
 need(not OUT.exists() and not OUT.is_symlink(),'OUTPUT_ALREADY_EXISTS')
 OUT.mkdir(parents=True,exist_ok=False)
 for d in ('source','build','logs','graphs','bin'):(OUT/d).mkdir()
 copied=[]
 for v in source['variants']:
  name=v['variant'];dst=OUT/'source'/name
  shutil.copytree(PREV/'source'/name,dst,symlinks=True)
  need(mod.digest_tree(dst)==v['tree_sha256'],'COPIED_TREE_SHA_'+name)
  copied.append(dict(v))
 new=dict(source)
 new['input']=dict(source['input'])
 new['input']['deps']=dict(source['input']['deps'])
 new['input']['deps']['HIGHWAY']=str(H85)
 new['highway_historical_pin']=hwy
 new['copied_from_v11_source_manifest_sha256']=SOURCE_SHA
 new['controlled_change']='ONLY FETCHCONTENT_SOURCE_DIR_HIGHWAY changed from R86 0e0a01da to H85 6bc2d477; original 6 source tree SHAs and compiler/macros unchanged'
 new['status']='SOURCE_6_VARIANTS_PREPARED__NO_COMPILE_NO_BUILD'
 new['variants']=copied
 write(OUT/'source_manifest.json',new)
 write(OUT/'experiment_preregister.json',{'status':'V13_HISTORICAL_HIGHWAY_SOURCE_SIX_COPY_PREPARED','old_source_manifest_sha256':SOURCE_SHA,
  'original_v11_runner_sha256':ORIG_SCRIPT_SHA,'compiler_sha256':COMPILER_SHA,'baseline_commit_full':hwy['git_head'],
  'highway_before_0e0a':{f:v[0] for f,v in NEW_FILES.items()},'highway_after_6bc2':{f:v[0] for f,v in OLD_FILES.items()},
  'source_trees_sha256':{r['variant']:r['tree_sha256'] for r in copied},'original_flags':list(mod.FLAGS),
  'A':'compile6 + controlled 126-case Highway probe + 6 SIFT10K graph builds + structural gate; cross-arm graph SHA NOT REQUIRED',
  'B':'only after A PASS: ONE SIFT1M Stock OFF 4CPU graph, v0/dup geometry and 10000Q Recall@10 screening beam80/160',
  'future':'Any 24-run SIFT1M/MS-Turing1M campaign requires explicit new authorization; NO 10M'},)
 # Errata is written as a NEW artifact; the v1.2 original summary is immutable.
 errata=js(REPORT_V0)['original_screen_grid_metadata']
 need(all(errata['SIFT1M'][a]['metadata_error'] for a in ARMS),'EXPECTED_OLD_SCREEN_METADATA_ERROR')
 write(OUT/'v12_screen_metadata_errata.json',{'status':'DERIVED_ERRATA_ORIGINAL_SEARCH_SUMMARY_UNCHANGED',
   'old_readonly_report_sha256':V0_REPORT_SHA,
   'correct_SIFT1M_tested_beam_grid':[10,20,40,80,160],
   'correct_MS_Turing1M_tested_beam_grid':[384,896],
   'original_reported':errata,
   'impact':'v1.2 summary tested_beam_grid field only; per-graph native Recall lines remain intact; this does not amend original report.'})
 print(TAG+'_PREPARE_PASS_6_SAME_SOURCE_TREES_OLD_HIGHWAY_6BC2_NO_BUILD',flush=True)

def v13_mod():
 mod=original_module();mod.OUT=OUT;mod.DEPS=dict(mod.DEPS);mod.DEPS['HIGHWAY']=H85
 return mod

def compile():
 need(OUT.is_dir() and regular(OUT/'source_manifest.json'),'PREPARE_FIRST')
 mod=v13_mod()
 src=js(OUT/'source_manifest.json')
 need(src['highway_historical_pin']['git_head'].startswith('6bc2d477'),'SOURCE_COMMIT_PIN')
 need(src['input']['deps']['HIGHWAY']==str(H85),'OLD_HIGHWAY_DEPENDENCY')
 need(src['copied_from_v11_source_manifest_sha256']==SOURCE_SHA,'ORIGINAL_TREE_SOURCE_PIN')
 source_gate()
 mod.compile()
 comp=js(OUT/'compile_manifest.json')
 need(comp['compiler_sha256']==COMPILER_SHA,'NEW_COMPILER_DRIFT')
 prov={}
 for arm in ARMS:
  for mode in MODES:
   label=arm+'_'+mode;build=OUT/'build'/label
   cache=(build/'CMakeCache.txt').read_text(errors='replace')
   # Explicit offline override must point to the historical source, not the newer R86 revision.
   match=re.search(r'^FETCHCONTENT_SOURCE_DIR_HIGHWAY:[^=]+=(.*)$',cache,re.M)
   need(match is not None and Path(match.group(1)).resolve()==H85.resolve(),'CMAKE_HIGHWAY_DRIFT_'+label)
   cc=build/'compile_commands.json'
   need(regular(cc),'COMPILATION_COMMANDS_MISSING_'+label)
   commands=json.loads(cc.read_text())
   hwy_cmd=[x for x in commands if 'hwy' in x['file'] and ('sort' in x['file'] or 'vqsort' in x['file'])]
   need(bool(hwy_cmd),'HIGHWAY_SORT_NOT_COMPILED_'+label)
   need(all(Path(x['file']).resolve().is_relative_to(H85.resolve()) for x in hwy_cmd),'HIGHWAY_COMPILE_FILE_PATH_DRIFT_'+label)
   need(all('-ffast-math' in (x.get('command','')+' '+' '.join(x.get('arguments',[]))) for x in hwy_cmd),'HIGHWAY_FAST_MATH_FLAG_MISSING_'+label)
   prov[label]={'elf_sha256':comp['binaries'][label], 'highway_source':match.group(1),
    'compile_commands_sha256':sha(cc),'highway_sort_compile_units':len(hwy_cmd)}
 pin(H85/'hwy/contrib/sort/traits-inl.h',OLD_FILES['traits-inl.h'][1],'HWY_FINAL')
 write(OUT/'compile_provenance_audit.json',{'status':'SIX_HISTORICAL_HWY_COMPILER_SOURCE_MACRO_PROVENANCE_PASS',
  'six_binary_compiler_sha256':COMPILER_SHA,'highway_commit':src['highway_historical_pin'], 'per_arm':prov,
  'source_manifest_sha256':sha(OUT/'source_manifest.json')})
 print(TAG+'_COMPILE_AUDIT_PASS_6_ELF_H85_HIGHWAY_CMAKE_CACHE_SOURCE_AND_FLAGS',flush=True)

def parse_probe(txt):
 lines=[s.strip() for s in txt.splitlines() if s.strip()]
 need(len(lines)==128 and lines[0].startswith('PROBE_BEGIN ') and lines[-1].startswith('PROBE_DONE '),'PROBE_LINE_COUNT')
 rows=[]
 for s in lines[1:-1]:
  d={}
  for field in s.split():
   if '=' in field:
    k,v=field.split('=',1);need(k not in d,'PROBE_DUP_KEY');d[k]=v
  need(s.startswith('CASE ') and d.get('mode') in ('on','off') and d.get('flags_valid')=='1','PROBE_FIELDS')
  rows.append(d)
 counts={}
 for mode in ('off','on'):
  a=[x for x in rows if x['mode']==mode];need(len(a)==63,'PROBE_63_'+mode)
  counts[mode]={'cases':len(a),'top2_mismatches':sum(x['highway_exact']=='0' for x in a),
   'raw_bit_mutations':sum(x['raw_multiset_preserved']=='0' for x in a),
   'index12_lost':sum(x['index12_survives']=='0' for x in a)}
 one_zero_on=[x for x in rows if x['mode']=='on' and x['kind'] in ('zero12_tail','zero12_front') and int(x['n'])>=32]
 need(len(one_zero_on)==24,'SINGLE_ZERO_COUNT')
 critical=[{'n':x['n'],'kind':x['kind'],'rep':x['rep'],'zero_bits_introduced':x['zero_bits_introduced'],
  'index12_survives':x['index12_survives']} for x in one_zero_on if x['index12_survives']!='1' or x['zero_bits_introduced']!='0']
 return {'status':'SINGLE_ZERO_SELECTED_SIZES_SAFE' if not critical else 'SINGLE_ZERO_PACKED_KEY_BIT_CLEARING_DETECTED_HOLD',
  'summary':counts,'critical_one_zero_cases':critical,'all_126_cases':rows,
  'limitations':'Two simultaneous subnormal values may be tie-inexact under DAZ; two-valued special-case VQSort mutations are reported, NOT treated as single-zero corruption. No universal safety guarantee.'}

def probe():
 need(regular(OUT/'compile_provenance_audit.json') and not (OUT/'probe_report.json').exists(),'COMPILE_AUDIT_REQUIRED_NO_REPROBE')
 pin(CPP,CPP_SHA,'CPP')
 mod=v13_mod();comp=js(OUT/'compile_manifest.json');need(comp['compiler_sha256']==COMPILER_SHA,'COMPILER')
 contrib=OUT/'build/stock_off/_deps/highway-build/libhwy_contrib.a'
 core=OUT/'build/stock_off/_deps/highway-build/libhwy.a'
 need(regular(contrib) and regular(core),'V13_HIGHWAY_ARCHIVES_MISSING')
 cxx=comp['cxx_binary'];pin(cxx,COMPILER_SHA,'CURRENT_COMPILER')
 exe=OUT/'bin/hwy_6bc2_ftz_synthetic_probe'
 cmd=[cxx,'-std=c++17','-O3','-march=native','-ffast-math','-pthread','-I',str(H85),
      '-I',str(OUT/'build/stock_off/_deps/highway-build'),str(CPP),str(contrib),str(core),'-ldl','-o',str(exe)]
 log=OUT/'logs/probe_compile.stdout'
 with log.open('x') as fp:rc=subprocess.run(cmd,stdout=fp,stderr=subprocess.STDOUT,check=False).returncode
 need(rc==0 and regular(exe),'PROBE_COMPILE_FAILED_SEE_'+str(log))
 out=OUT/'logs/probe_run.stdout'
 with out.open('x') as fp:rc=subprocess.run(['taskset','-c','0',str(exe)],stdout=fp,stderr=subprocess.STDOUT,check=False).returncode
 need(rc==0,'PROBE_EXEC_RC_'+str(rc))
 result=parse_probe(out.read_text(errors='replace'))
 result.update({'highway_commit':js(OUT/'source_manifest.json')['highway_historical_pin']['git_head'],
  'compiler_sha256':COMPILER_SHA,'probe_source_sha256':CPP_SHA,'probe_elf_sha256':sha(exe),
  'hwy_archive_sha256':{'core':sha(core),'contrib':sha(contrib)},'probe_stdout_sha256':sha(out)})
 write(OUT/'probe_report.json',result)
 print(TAG+'_HIGHWAY_6BC2_PROBE',result['status'],'OFF_MUTATIONS',result['summary']['off']['raw_bit_mutations'],
  'ON_MUTATIONS',result['summary']['on']['raw_bit_mutations'],'SINGLE_ZERO_CRITICAL',len(result['critical_one_zero_cases']),flush=True)
 need(not result['critical_one_zero_cases'],'OLD_HIGHWAY_SINGLE_ZERO_CASE_UNSAFE_STOP')

def graph_check(p,n):
 p=Path(p);need(regular(p),'GRAPH_MISSING_'+p.name)
 with p.open('rb') as f:
  head=f.read(8);need(len(head)==8 and struct.unpack('<II',head)==(n,64),'GRAPH_HEADER_'+p.name)
  raw=f.read(4*n);need(len(raw)==4*n,'GRAPH_DEG_TRUNC_'+p.name)
  deg=array.array('I');deg.frombytes(raw)
  if sys.byteorder!='little':deg.byteswap()
  need(len(deg)==n and max(deg)<=64,'GRAPH_DEGREE_'+p.name)
  arcs=sum(deg);need(p.stat().st_size==8+4*n+4*arcs,'GRAPH_FILE_SIZE_'+p.name)
  badids=loops=dupes=0;start=0
  for v,k in enumerate(deg):
   rawedge=f.read(4*k);need(len(rawedge)==4*k,'GRAPH_EDGE_TRUNC_'+p.name)
   ids=struct.unpack('<'+str(k)+'I',rawedge) if k else ()
   badids+=sum(j>=n for j in ids);loops+=sum(j==v for j in ids);dupes+=len(ids)-len(set(ids))
   start+=k
  need(start==arcs,'GRAPH_ARCS_SUM')
 need(badids==0 and loops==0 and dupes==0,'GRAPH_INVALID_'+p.name)
 return {'node_count':n,'degree_bound':64,'arcs':arcs,'invalid_neighbor_ids':badids,'self_loops':loops,'duplicate_neighbor_slots':dupes,'graph_sha256':sha(p)}

def pilot():
 need(regular(OUT/'probe_report.json'),'PROBE_FIRST')
 need(js(OUT/'probe_report.json')['status']=='SINGLE_ZERO_SELECTED_SIZES_SAFE','PROBE_UNSAFE_HOLD')
 mod=v13_mod();need(regular(OUT/'compile_manifest.json'),'COMPILE_FIRST')
 need(not (OUT/'pilot_manifest.json').exists(),'PILOT_ALREADY_RUN')
 runs=[]
 for mode in MODES:
  for arm in ARMS:
   r=mod.native_one(arm,mode,SIFT10K,'SIFT10K',1,1)
   r['graph_structure']=graph_check(r['graph'],10000)
   log=Path(r['stdout']).read_text(errors='replace')
   r['buckets']=[int(x) for x in re.findall(r'^\s*Total buckets:\s*(\d+)\s*$',log,re.M)]
   need(len(r['buckets'])==2,'PILOT_BUCKET_PARSE_'+arm+mode)
   runs.append(r)
 write(OUT/'pilot_manifest.json',{'status':'SIX_H85_HWY_SIFT10K_BUILD_COMPLETE_AUDIT_PENDING',
 'runs':runs,'no_cross_arm_graph_sha_equality_requirement':True,'historical_highway_commit':js(OUT/'source_manifest.json')['highway_historical_pin']['git_head']})
 print(TAG+'_PILOT10K_COMPLETE_SIX_BUILDS_NO_CROSSARM_SHA_ASSUMPTION',flush=True)

def auditA():
 src=js(OUT/'source_manifest.json');cc=js(OUT/'compile_manifest.json');p=js(OUT/'pilot_manifest.json');probe=js(OUT/'probe_report.json')
 need(len(p['runs'])==6 and probe['status']=='SINGLE_ZERO_SELECTED_SIZES_SAFE','A_INCOMPLETE')
 need(cc['compiler_sha256']==COMPILER_SHA,'COMPILER_DRIFT')
 srcnames={a+'_'+b for a in ARMS for b in MODES};seen=set();rows=[]
 for run in p['runs']:
  k=run['arm']+'_'+run['mode'];need(k in srcnames and k not in seen,'DUP_PILOT_ARM_'+k);seen.add(k)
  for field,h in [('graph','graph_sha'),('stdout','stdout_sha'),('timefile','timefile_sha')]:pin(run[field],run[h],'PILOT_'+k+'_'+field)
  pin(v13_mod().compiled_path(run['arm'],run['mode']),cc['binaries'][k],'V13_ELF_'+k)
  check=graph_check(run['graph'],10000)
  need(check==run['graph_structure'],'PILOT_GRAPH_CHECK_'+k)
  rows.append({'arm':run['arm'],'mode':run['mode'],'buckets':run['buckets'],'graph_sha256':run['graph_sha'],'arcs':check['arcs']})
 need(seen==srcnames,'PILOT_MISSING_VARIANTS')
 write(OUT/'stageA_audit.json',{'status':'STAGEA_SIX_ELF_H85_HWY_PROBE_AND_SIFT10K_GRAPH_STRUCTURE_PASS',
  'compiler_sha256':COMPILER_SHA,'highway_commit_full':src['highway_historical_pin']['git_head'],
  'highway_source_manifest_sha256':sha(OUT/'source_manifest.json'), 'compile_manifest_sha256':sha(OUT/'compile_manifest.json'),
  'pilot_manifest_sha256':sha(OUT/'pilot_manifest.json'), 'probe_report_sha256':sha(OUT/'probe_report.json'),
  'pilot_graphs':rows, 'limitations':['A PASS is not SIFT1M recall certification.','No cross-arm bytewise graph SHA parity required due Stage1 randomness.',
  'Historical Highway probe PASS only rules out a particular synthetic single-zero clearing on this CPU; simultaneous subnormal ties and other numerical risks remain.',
  'B is one Stock SIFT1M quality pilot, not a 24-run study.']})
 print(TAG+'_STAGEA_AUDIT_PASS_6_H85_HIGHWAY_ELF_126_PROBE_6_10K_GRAPH_NO_1M',flush=True)

def fbin_shape(p,n,dim):
 pin(p,{SIFT1M:SIFT1M_SHA,QUERIES:Q_SHA}[p],'FBIN')
 with p.open('rb') as fp:hdr=fp.read(8)
 need(hdr==struct.pack('<II',n,dim) and p.stat().st_size==8+n*dim*4,'FBIN_HEADER_'+str(p))

def b_preflight():
 aud=js(OUT/'stageA_audit.json')
 need(aud['status']=='STAGEA_SIX_ELF_H85_HWY_PROBE_AND_SIFT10K_GRAPH_STRUCTURE_PASS','STAGEA_NOT_PASS')
 mod=v13_mod();src=js(OUT/'source_manifest.json');comp=js(OUT/'compile_manifest.json')
 need(src['highway_historical_pin']['git_head']==aud['highway_commit_full'],'COMMIT_DRIFT')
 for k,exe_sha in comp['binaries'].items():
  arm,mode=k.rsplit('_',1);pin(mod.compiled_path(arm,mode),exe_sha,'V13_ELF_'+k)
 pin(OUT/'pilot_manifest.json',aud['pilot_manifest_sha256'],'PILOT_MANIFEST')
 pin(OUT/'probe_report.json',aud['probe_report_sha256'],'PROBE_REPORT')
 fbin_shape(SIFT1M,1000000,128);fbin_shape(QUERIES,10000,128)
 pin(GT,GT_SHA,'GROUND_TRUTH')
 with GT.open('rb') as f:head=f.read(8)
 need(head==struct.pack('<II',10000,100) and GT.stat().st_size==8+10000*100*8,'GROUND_TRUTH_SHAPE')
 pin(EVAL,EVAL_SHA,'PINNED_R72_EVALUATOR')
 need(shutil.disk_usage(R90).free>=4*(1<<30),'DISK_HEADROOM_LT4GIB')
 with Path('/proc/meminfo').open() as f:txt=f.read()
 z=re.search(r'^MemAvailable:\s+(\d+) kB',txt,re.M)
 need(z and int(z.group(1))>=7*(1<<20),'MEMAVAILABLE_LT7GIB')
 need(0 in os.sched_getaffinity(0),'CPU0_UNAVAILABLE')
 need(not (OUT/'SIFT1M_stock_off_r1.json').exists() and not (OUT/'stageB_stock_sift1m_quality.json').exists(), 'STAGEB_OUTPUT_ALREADY_EXISTS')
 print(TAG+'_STAGEB_PREFLIGHT_PASS_H85_6ELF_STAGEA_GATE_SIFT1M_QUERY_GT_EVAL_RESOURCE',flush=True)
 return mod

def v0_and_big_inv(graph,base):
 with graph.open('rb') as f,mmap.mmap(f.fileno(),0,access=mmap.ACCESS_READ) as gm,base.open('rb') as b,mmap.mmap(b.fileno(),0,access=mmap.ACCESS_READ) as bm:
  n,maxdeg=struct.unpack_from('<II',gm,0)
  degrees=array.array('I');degrees.frombytes(gm[8:8+4*n]);
  if sys.byteorder!='little':degrees.byteswap()
  need(n==1000000 and maxdeg==64 and len(degrees)==n,'GEOMETRY_GRAPH_HEADER')
  offsets=array.array('Q',[0]);z=0
  for degree in degrees:z+=degree;offsets.append(z)
  def neighbors(v):
   count=degrees[v];offset=8+4*n+4*offsets[v]
   return struct.unpack_from('<'+str(count)+'I',gm,offset) if count else ()
  def vector(v):return struct.unpack_from('<128f',bm,8+v*512)
  def d2(u,v):
   a=vector(u);b=vector(v)
   return math.fsum((x-y)*(x-y) for x,y in zip(a,b))
  v0=neighbors(0);v0ds=sorted(((j,d2(0,j)) for j in v0),key=lambda r:(r[1],r[0]))
  big=0;samples=[]
  for v in range(10000):
   ngh=neighbors(v)
   if len(ngh)<2:continue
   a=d2(v,ngh[0]);b=d2(v,ngh[1]);
   if a-b>10000 and a>1.5*max(b,1e-9):
    big+=1
    if len(samples)<10:samples.append({'vertex':v,'first_id':ngh[0],'first_d2':round(a,3),'second_id':ngh[1],'second_d2':round(b,3)})
  # Hash the BASE vectors, not the 1M graph. Confirm candidate exact-copy hashes by full raw vector comparison.
  seen={};duplicates=[]
  for i in range(n):
   raw=bm[8+i*512:8+(i+1)*512]
   key=hashlib.blake2b(raw,digest_size=16).digest()
   prior=seen.get(key)
   if prior is None:seen[key]=i
   elif bm[8+prior*512:8+(prior+1)*512]==raw:duplicates.append((prior,i))
   else:need(False,'BLAKE2B_COLLISION_UNEXPECTED')
  reciprocal=either=first=0
  for i,j in duplicates:
   ni=neighbors(i);nj=neighbors(j)
   left=j in ni;right=i in nj
   reciprocal+=int(left and right);either+=int(left or right)
   first+=int((ni and ni[0]==j) or (nj and nj[0]==i))
  return {'v0':{'degree':len(v0),'has_2':2 in v0,'has_6':6 in v0,'nearest':[{'id':v,'squared_l2':round(x,3)} for v,x in v0ds[:5]],
    'mean_neighbor_l2_squared':round(math.fsum(d for _,d in v0ds)/len(v0ds),3) if v0ds else None},
   'first_10000_large_first_second_inversions_threshold':'first_d2 - second_d2 >10000 AND first_d2 > 1.5*second_d2',
   'big_inv_first_10000':big,'big_inv_examples':samples,
   'exact_duplicate_vectors':{'detected_pairs':len(duplicates),'both_directions_direct_neighbors':reciprocal,
    'at_least_one_direct_neighbor':either,'one_endpoint_first_neighbor':first,
    'either_end_retention_ratio':either/len(duplicates) if duplicates else None},
   'caveats':['Neighbor list is not guaranteed sorted by L2; big_inv is diagnostic, not intrinsic graph corruption.',
    'Duplicate direct-neighbor retention is a quality diagnostic; ANN graph need not represent every exact duplicate directly.']}

def parse_recall(txt):
 regex=re.compile(r'^R72_RECALL_ROW beam=(\d+) recall=([0-9.]+) qps=([0-9.eE+-]+) avg_cmps=([0-9.eE+-]+) avg_visited=([0-9.eE+-]+)$',re.M)
 r={}
 for match in regex.finditer(txt):
  beam=int(match.group(1));rec=float(match.group(2));qps=float(match.group(3))
  need(beam not in r and 0<=rec<=1 and math.isfinite(rec) and qps>0 and math.isfinite(qps),'RECALL_ROW_INVALID')
  r[beam]={'recall':rec,'qps':qps,'latency_us_proxy':1e6/qps}
 need('R72_RECALL_EVAL_PASS' in txt and set(r)=={10,20,40,80,160},'EVAL_BEAM_GRID')
 return r

def stock1m():
 mod=b_preflight()
 mod.OUT=OUT
 # Native source-pinned build saves graph/stdout/time/one source receipt atomically.
 run=mod.native_one('stock','off',SIFT1M,'SIFT1M',1,4)
 structure=graph_check(run['graph'],1000000)
 geom=v0_and_big_inv(Path(run['graph']),SIFT1M)
 search=OUT/'logs/SIFT1M_stock_off_r1_QUALITY_10KQ.stdout'
 err=OUT/'logs/SIFT1M_stock_off_r1_QUALITY_10KQ.stderr'
 need(not search.exists() and not err.exists(),'SEARCH_OUTPUT_EXISTS')
 cmd=['taskset','-c','0',str(EVAL),str(run['graph']),str(SIFT1M),str(QUERIES),str(GT)]
 env=dict(os.environ);env.update(PARLAY_NUM_THREADS='1',OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='1',LC_ALL='C')
 with search.open('x') as fo,err.open('x') as fe:rc=subprocess.run(cmd,env=env,stdout=fo,stderr=fe,check=False).returncode
 need(rc==0,'EVALUATOR_RC_'+str(rc))
 recalls=parse_recall(search.read_text())
 safe_v0=geom['v0']['has_2'] and geom['v0']['has_6'] and geom['v0']['degree']<64
 enough_recall=recalls[80]['recall']>=0.99 and recalls[160]['recall']>=0.998
 pair=geom['exact_duplicate_vectors']
 duplicate_gate=pair['detected_pairs']>0 and pair['either_end_retention_ratio']>=0.95
 passes=safe_v0 and enough_recall and duplicate_gate
 report={'status':'STAGEB_STOCK_SIFT1M_QUALITY_PASS_READY_FOR_REVIEW' if passes else 'STAGEB_STOCK_SIFT1M_QUALITY_HOLD_FOR_REVIEW',
  'h85_commit':js(OUT/'stageA_audit.json')['highway_commit_full'],'stock_graph':structure,
  'stock_graph_record_sha256':sha(OUT/'SIFT1M_stock_off_r1.json'), 'v0_and_duplicates':geom,
  'search_recall_by_beam':{str(k):v for k,v in recalls.items()},
  'search_stdout_sha256':sha(search),'search_stderr_sha256':sha(err),
  'gates':{'v0_contains_2_and_6_degree_under64':safe_v0,'recall_80_atleast_099_and_160_atleast_0998':enough_recall,
   'duplicate_either_endpoint_retention_atleast_095':duplicate_gate,'big_inversion_is_diagnostic_not_gate':True},
  'build_only_one_stock_1m':True,'no_full_1m_six_arm_campaign':True,
  'limitations':['Historical Stock source revision restored, but causal attribution to a particular historical edge needs paired old/new leaf-key trace.',
  'Quality threshold is measured on same SIFT1M public 10KQ GT, not a formal independence/noninferiority test.',
  'Old Highway 6bc2 avoids observed synthetic single-zero clearing but other DAZ and tie behavior can remain.']}
 write(OUT/'stageB_stock_sift1m_quality.json',report)
 print(TAG+'_STAGEB_STOCK_SIFT1M_QUALITY',report['status'],'v0',geom['v0'],
 'duplicate',pair,'big_inv_first10000',geom['big_inv_first_10000'],
 'Recall80',recalls[80]['recall'],'Recall160',recalls[160]['recall'],flush=True)
 print(TAG+'_STAGEB_REPORT',OUT/'stageB_stock_sift1m_quality.json','sha256',sha(OUT/'stageB_stock_sift1m_quality.json'),flush=True)
 need(passes,'STAGEB_STOCK_SIFT1M_QUALITY_NOT_READY')

def selftest():
 with tempfile.TemporaryDirectory() as d:
  p=Path(d)/'g';p.write_bytes(struct.pack('<II',3,64)+struct.pack('<3I',1,1,0)+struct.pack('<2I',1,0))
  t=graph_check(p,3);need(t['arcs']==2,'SELFTEST_GRAPH_ARCS')
  p.write_bytes(struct.pack('<II',3,64)+struct.pack('<3I',1,1,0)+struct.pack('<2I',9,0))
  try:graph_check(p,3)
  except RuntimeError:pass
  else:need(False,'SELFTEST_MUST_HOLD_INVALID_NEIGHBOR')
  fake='PROBE_BEGIN compiler_fast_math=1 initial_mxcsr=0x00001f80 float64_available=1\n'
  for mode in ('off','on'):
   for n in (2,8,16,32,64,189,512):
    for kind in ('zero12_tail','zero12_front','zero12_and45'):
     for rep in range(1,4):
      fake+=f'CASE mode={mode} n={n} kind={kind} rep={rep} flags_valid=1 highway_exact=1 raw_multiset_preserved=1 index12_survives=1 zero_bits_introduced=0\n'
  fake+='PROBE_DONE mxcsr_restored=0x00001f80\n'
  z=parse_probe(fake);need(z['summary']['on']['cases']==63 and z['status']=='SINGLE_ZERO_SELECTED_SIZES_SAFE','SELFTEST_PROBE')
  z=parse_recall(''.join(f'R72_RECALL_ROW beam={b} recall=0.99850000 qps=1000.000000 avg_cmps=50 avg_visited=20\n' for b in (10,20,40,80,160))+'R72_RECALL_EVAL_PASS\n')
  need(len(z)==5 and 160 in z,'SELFTEST_RECALL_PARSE')
 print(TAG+'_SELFTEST_PASS_GRAPH_INVALID_ID_PROBE126_RECALL_PARSER_NO_1M',flush=True)

def main():
 ap=argparse.ArgumentParser();ap.add_argument('phase',choices=['selftest','preflight','prepare','compile','probe','pilot','auditA','preflightB','stock1m'])
 args=ap.parse_args()
 try:
  {'selftest':selftest,'preflight':preflight,'prepare':prepare,'compile':compile,'probe':probe,'pilot':pilot,
   'auditA':auditA,'preflightB':b_preflight,'stock1m':stock1m}[args.phase]()
 except Exception as e:
  print(TAG+'_ERROR',type(e).__name__,str(e),file=sys.stderr,flush=True)
  raise SystemExit(2)
if __name__=='__main__':main()
