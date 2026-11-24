#!/usr/bin/env python3
"""R91 G6 10M fixed-seed repeated paired BUILD. This bundle executes ONLY pair 1.

Frozen, SHA-pinned G6 ELF; identical G6 flags and four CPUs; no graph source edits.
The native Stage 1 reported SEED=555 is a fixed-seed experiment, NOT a multi-seed study.
Old artifacts untouched, output root new; per-arm fail-closed audit, hard 24GiB/0 swap.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
import math
import os
import re
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

TAG='R91_G6_10M_REPEAT_BUILD_P01_V1'
HOME=Path.home(); ROOT=HOME/'ann-task-a'; R91=ROOT/'experiments/R91'
PARENT=R91/'r91_g6_mst10m_c512_c64_pair_v1_3'
G6=R91/'r91_g6_d2_leader_cap_v1'
OUT=R91/'r91_g6_mst10m_repeat_build_6pairs_v1'
PAIR=OUT/'pairs/p01'
VENDOR=Path(__file__).with_name('vendor_r91_g6_mst10m_pair_v1_3.py')
VENDOR_SHA='0e62c69dcf73f499d4c99e3181c526c0d908150ff6e77ca4d1fde4144801cab7'
SOURCE=G6/'source/algorithms/PipNN/pipnn.h'
HASH_SRC=G6/'source/algorithms/utils/hash.h'
PARENT_SHA={
 'preflight.json':'0e968c761d749f3098956b1d1226923b67d67c050a5fc10b95b40f44e076a14e',
 'build_pair_audit.json':'e4816122d38bded111b158c227a6d28ef2d1d28130e38cefc83f45e4e41beb3b',
 'search_pair_audit.json':'9604f05dc7ca220ce06dbd8f891048328a801441701da5dbfe50c4e1c67a834d',
 'runs/C512/receipt.json':'b520f072d7c782a5efcb3ca5f3573d4bf9eddf1270861b06cafb1cdc37272082',
 'runs/C64/receipt.json':'b10c89d2075046b91b8d738cd9c245e9a3ba74e920c6281e676c2db0916475e6',
}
GRAPH_PIN={'C512':'5924279e3065953f407003fd7217476f04b214295c4f3801db510628c9e6c443',
           'C64':'4c54e712c1ba859201a33a8754534c9e3f855664c63db1075a4cf7803dea6e8d'}
CALIB=R91/'r91_g6_mst10m_matched_recall_calib_v1'
CALIB_PIN={'preflight.json':'abd26a5df6200d64b9e78f63a64bb168fe9453af738d7229d9db973708880a91',
           'matched_recall_calibration_summary.json':'92a5f9d0b4637e00b8d6c1672308a49e08dc4c83c6133641fd581aaaa60162c8'}
ORDER=(('C512','C64'),('C64','C512'),('C64','C512'),('C512','C64'),('C512','C64'),('C64','C512'))
MEM=25769803776
PREFLIGHT_HOST_KIB=22*1024*1024
DISK_FIRST_GIB=55
DISK_SECOND_GIB=48
DISK_MONITOR_GIB=38


def need(ok,why):
 if not ok:raise RuntimeError(TAG+'_HOLD_'+why)

def regular(p):
 return p.is_file() and not p.is_symlink()

def sha(p):
 need(regular(p),'MISSING_OR_SYMLINK_'+p.name)
 h=hashlib.sha256()
 with p.open('rb') as f:
  for x in iter(lambda:f.read(8*1024*1024),b''):h.update(x)
 return h.hexdigest()

def pin(p,digest,why):need(sha(p)==digest,'SHA_'+why)

def loadj(p):
 need(regular(p),'NO_JSON_'+p.name)
 return json.loads(p.read_text(encoding='utf8'))

def writej(p,obj):
 need(not p.exists() and not p.is_symlink(),'OUTPUT_EXISTS_'+p.name)
 tmp=Path(str(p)+'.part');need(not tmp.exists() and not tmp.is_symlink(),'PART_EXISTS_'+p.name)
 with tmp.open('x',encoding='utf8') as f:
  json.dump(obj,f,sort_keys=True,indent=2,ensure_ascii=False,allow_nan=False)
  f.write('\n');f.flush();os.fsync(f.fileno())
 os.replace(tmp,p)

def core():
 pin(VENDOR,VENDOR_SHA,'VENDORED_ORIGINAL_V13_PARSER_MONITOR')
 spec=importlib.util.spec_from_file_location('_r91_g6_v13_frozen_core',VENDOR)
 need(spec is not None and spec.loader is not None,'IMPORT_SPEC')
 m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
 need(m.TAG=='R91_G6_MST10M_C512_C64_PAIR_V1_3','VENDOR_TAG')
 need(m.PINS['g6_elf']=='53be9510ead14aff25ec5adffc07d959c78d575f7ffcc9306435360ce9342690','VENDOR_ELF_PIN')
 need(m.LIMIT==MEM and m.CPU_BUILD=='0,2,4,6','VENDOR_RESOURCE_CPU_DRIFT')
 need(m.FLAGS==['-num_clusters','2','-cluster_size','1024','-table_size','160','-top_level_leaders','100',
 '-fanout_scheme','10,3,1','-mst_deg','2','-prune','1','-prune_all','1',
 '-prune_degree','64','-hash_bits','12','-alpha','1.1','-k','0'],'VENDOR_BUILD_FLAGS_DRIFT')
 return m

def source_seed_audit():
 need(regular(SOURCE),'PIPNN_SOURCE_NOT_REGULAR')
 need(regular(HASH_SRC),'HASH_SOURCE_NOT_REGULAR')
 body=SOURCE.read_text(errors='replace');line=body.splitlines()
 # This establishes the two exact source markers; it is not a formal proof
 # that all Stage-1 operations lack any other entropy or thread-order effects.
 seed=[i for i,s in enumerate(line,1) if re.search(r'\bSEED\s*=\s*555\b',s)]
 pass2=[i for i,s in enumerate(line,1) if re.search(r'(?:parlay::)?hash64\s*\(\s*SEED\s*\)',s)]
 need(bool(seed) and bool(pass2),'SOURCE_SEED_555_OR_HASH64_MARKER_MISSING')
 sketch='SketchHash' in body or 'SketchHash' in HASH_SRC.read_text(errors='replace')
 snippets=[{'file':'pipnn.h','line':i,'text':line[i-1].strip()[:180]} for i in seed+pass2]
 return {'source_sha256':sha(SOURCE),'hash_header_sha256':sha(HASH_SRC),
         'seed_555_markers':seed,'hash64_seed_markers':pass2,'SketchHash_identifier_seen':sketch,
         'source_snippets':snippets,
         'conclusion':'Static source markers present, fixed-seed Stage1 counters must also match original reference by arm; no multi-seed sampling claim'}

def pinned_parent(check_graph=True):
 need(PARENT.is_dir() and not PARENT.is_symlink(),'PARENT_NOT_DIR')
 for rel,digest in PARENT_SHA.items():pin(PARENT/rel,digest,'PARENT_'+rel.replace('/','_'))
 for a,digest in GRAPH_PIN.items():
  p=PARENT/'runs'/a/'graph.bin'
  need(regular(p),'PARENT_GRAPH_NOT_REGULAR_'+a)
  if check_graph:pin(p,digest,'PARENT_GRAPH_'+a)
  need(loadj(PARENT/'runs'/a/'receipt.json')['graph']['sha256']==digest,'PARENT_RECEIPT_GRAPH_'+a)
 b=loadj(PARENT/'build_pair_audit.json')
 need(b['status']=='TWO_10M_NATIVE_BUILDS_FULL_GRAPH_WORK_RESOURCE_AUDIT_PASS_SEARCH_NOT_RUN','PARENT_BUILD_STATUS')
 need(b['protocol']['source_sha']=='53be9510ead14aff25ec5adffc07d959c78d575f7ffcc9306435360ce9342690','PARENT_ELF')
 need(b['protocol']['leader_cap_only_depth2']==[512,64] and b['protocol']['memory_max_bytes']==MEM,'PARENT_PROTOCOL')
 for a in GRAPH_PIN:
  need(b[a]['graph_sha']==GRAPH_PIN[a] and b['source_receipts'][a]==PARENT_SHA[f'runs/{a}/receipt.json'],'PARENT_PAIR_LINK_'+a)
 s=loadj(PARENT/'search_pair_audit.json')
 need(s['status']=='TWO_10M_NATIVE_FIXED_BEAM_SEARCH_AUDIT_PASS' and s['build_pair_sha']==PARENT_SHA['build_pair_audit.json'],'PARENT_SEARCH_STATUS')
 need(CALIB.is_dir() and not CALIB.is_symlink(),'CALIB_PARENT_NOT_DIR')
 for rel,digest in CALIB_PIN.items():pin(CALIB/rel,digest,'CALIB_'+rel)
 c=loadj(CALIB/'matched_recall_calibration_summary.json')
 need(c['status']=='TEN_BEAM_BOTH_GRAPHS_NATIVE_CALIBRATION_AUDIT_PASS' and c['parent_build_sha256']==PARENT_SHA['build_pair_audit.json'],'CALIB_STATUS_OR_LINEAGE')
 need(c['graph_sha256']==GRAPH_PIN,'CALIB_GRAPH_LINK')
 return b

def setup(c,check_graph=True):
 need(os.name=='posix' and sys.platform=='linux','NOT_LINUX')
 need(R91.is_dir() and not R91.is_symlink(),'R91_NOT_DIR')
 need(OUT.parent==R91 and not OUT.is_symlink(),'OUTPUT_PARENT')
 b=pinned_parent(check_graph)
 # Original v1.3 source checks G4 original JSON triple, original ELF and all 10M data SHA/header.
 c.native_inputs(True)
 seed=source_seed_audit()
 return b,seed

def preflight():
 c=core()
 need(not OUT.exists() and not OUT.is_symlink(),'OUTPUT_ROOT_ALREADY_EXISTS')
 b,seed=setup(c,True)
 need(c.host_memory_kib()>=PREFLIGHT_HOST_KIB,'HOST_MEMAVAILABLE_BELOW_22GIB')
 need(c.disk_gib()>=DISK_FIRST_GIB,'DISK_FREE_BELOW_55GIB')
 d={'status':'PREFLIGHT_PASS_NO_BUILD','script_sha256':sha(Path(__file__)),
    'vendor_sha256':VENDOR_SHA,'original_g6_elf_sha256':c.PINS['g6_elf'],
    'parent_sha256':PARENT_SHA,'parent_graph_sha256':GRAPH_PIN,
    'calibration_sha256':CALIB_PIN,'source_seed_audit':seed,
    'preregistered_schedule':[list(x) for x in ORDER],
    'pilot_only_pair_id':'p01','pilot_arm_order':list(ORDER[0]),
    'scope':'REPEATED_BUILD_WITH_SAME_SOURCE_SEED_555_NOT_MULTISEED_EXPERIMENT',
    'protocol':{'n':c.N,'d':c.D,'cgroup_memory_max':MEM,'cgroup_swap_max':0,
         'cpu':'0,2,4,6','threads':4,'flags':c.FLAGS,'depth2_cap':[512,64],
         'disk_preflight_min_gib':DISK_FIRST_GIB,'disk_before_second_gib':DISK_SECOND_GIB,
         'disk_monitor_abort_below_gib':DISK_MONITOR_GIB},
    'baseline_work':{a:{k:b[a][k] for k in ('total_wp','depth2_wp','wp_ge2','leaf_count','fallback_maxdepth_points','fallback_shrink_points','depth2_affected_calls')} for a in GRAPH_PIN},
    'scientific_limits':['Fixed Stage-1 seed 555: repeated timing and thread scheduling variation, NOT independent leader-seed graphs',
       'Observed graph differences do not alone identify their cause; parallel scheduling is a hypothesis',
       'One pilot pair cannot establish robust wall-time significance','Six all-same-sign results, under independent fair sign null, one-sided p=1/64; dependencies and host drift must be assessed',
       'No Search in this pilot, no cross-graph Recall measured yet'],
    'created_epoch':time.time()}
 OUT.mkdir(parents=False,exist_ok=False)
 writej(OUT/'preflight.json',d)
 print(TAG+'_PREFLIGHT_PASS_NO_BUILD',sha(OUT/'preflight.json'),flush=True)
 print(TAG+'_SOURCE_SEED_555_MARKERS_PASS_STATIC_NOT_PROOF',seed['source_sha256'],seed['hash_header_sha256'],seed['seed_555_markers'],seed['hash64_seed_markers'],flush=True)

def check_preflight(c):
 j=loadj(OUT/'preflight.json')
 need(j['status']=='PREFLIGHT_PASS_NO_BUILD','PREFLIGHT_STATUS')
 need(j['script_sha256']==sha(Path(__file__)) and j['vendor_sha256']==VENDOR_SHA,'PREFLIGHT_SOURCE_SHA_DRIFT')
 need(j['preregistered_schedule']==[list(x) for x in ORDER] and j['pilot_arm_order']==['C512','C64'],'ORDER_DRIFT')
 return j

def stage1_deterministic(c,r,arm):
 # Require exact equality of Stage-1 structural counters against native v1.3 by arm.
 p=r['parsed'];orig=loadj(PARENT/'runs'/arm/'receipt.json')['parsed']
 k=('passes','native_comparisons','total_wp','depth2_wp','depth2_original_wp','total_leaf_memberships','fallback_maxdepth_points','fallback_shrink_points')
 for name in k:need(p.get(name)==orig.get(name),'STAGE1_COUNTER_DRIFT_'+arm+'_'+name)
 need(r['time']['wall_s']>0,'INVALID_NATIVE_WALL_'+arm)
 return {'status':'STAGE1_COUNTERS_MATCH_V13_REFERENCE','reference_receipt_sha256':PARENT_SHA['runs/'+arm+'/receipt.json'],
         'reference_total_wp':orig['total_wp'],'reference_depth2_wp':orig['depth2_wp'],
         'no_claim_multi_seed':True}

def monitor_strict(c,cmd,slot,cg,env):
 # Independent hard stop: 24GiB memory / swap0 / no OOM events, 38GiB disk
 # remaining, MemAvailable>=1.5GiB, and 5400s timeout. Never silently retry.
 initial_events=c.events(cg['vals']['memory.events'])
 mon={'sample_count':0,'sampled_peak_current':0,'sampled_peak_swap':0,
      'min_available_kib':c.host_memory_kib(),'min_disk_free_gib':c.disk_gib(),
      'status':'STARTED','exit_code':None}
 start=time.monotonic();process=None
 try:
  with (slot/'native.stdout').open('x') as out, (slot/'native.stderr').open('x') as err:
   process=subprocess.Popen(cmd,stdout=out,stderr=err,env=env,start_new_session=True)
   while True:
    code=process.poll();current=c.cgroup(False)['vals']
    mon['sample_count']+=1
    mon['sampled_peak_current']=max(mon['sampled_peak_current'],int(current['memory.current'] or 0))
    mon['sampled_peak_swap']=max(mon['sampled_peak_swap'],int(current['memory.swap.current'] or 0))
    mon['min_available_kib']=min(mon['min_available_kib'],c.host_memory_kib())
    mon['min_disk_free_gib']=min(mon['min_disk_free_gib'],c.disk_gib())
    now_events=c.events(current['memory.events'])
    trouble=(time.monotonic()-start>5400
      or int(current['memory.swap.current'] or 0)>0
      or any(now_events.get(k,0)>initial_events.get(k,0) for k in ('max','oom','oom_kill'))
      or mon['min_disk_free_gib']<DISK_MONITOR_GIB
      or mon['min_available_kib']<int(1.5*1024**2))
    if code is not None:break
    if trouble:
     mon['status']='RESOURCE_TIMEOUT_OR_DISK_ABORT'
     os.killpg(process.pid,signal.SIGTERM)
     try:process.wait(timeout=6)
     except subprocess.TimeoutExpired:
      os.killpg(process.pid,signal.SIGKILL);process.wait(timeout=10)
     break
    time.sleep(1)
 except BaseException:
  if process is not None and process.poll() is None:
   os.killpg(process.pid,signal.SIGTERM)
   try:process.wait(timeout=6)
   except subprocess.TimeoutExpired:
    os.killpg(process.pid,signal.SIGKILL);process.wait(timeout=10)
  raise
 current=c.cgroup(False)['vals'];after_events=c.events(current['memory.events'])
 mon.update({'exit_code':process.returncode,'elapsed_s':time.monotonic()-start,
  'cg_peak_bytes':int(current['memory.peak'] or 0),
  'swap_after':int(current['memory.swap.current'] or 0),
  'events_delta':{k:v-initial_events.get(k,0) for k,v in after_events.items()}})
 if mon['status']=='STARTED':mon['status']='COMPLETED'
 return mon

def run_arm(arm):
 need(arm in ('C512','C64'),'UNKNOWN_ARM')
 c=core();cg=c.cgroup(True);pre=check_preflight(c)
 need(PAIR.parent==OUT/'pairs' and not PAIR.is_symlink(),'PAIR_ROOT_DRIFT')
 need(not (PAIR/'pilot_pair_audit.json').exists(),'PAIR_AUDIT_ALREADY_PRESENT')
 if arm=='C64':
  need(regular(PAIR/'arms/C512/receipt.json'),'C512_RECEIPT_REQUIRED_FIRST')
  check_receipt(c,'C512',recheck_graph=True)
 else:
  need(not PAIR.exists() and not PAIR.is_symlink(),'PAIR_ALREADY_EXISTS_BEFORE_FIRST_ARM')
 need(c.disk_gib() >= (DISK_FIRST_GIB if arm=='C512' else DISK_SECOND_GIB),'DISK_BELOW_PRE_ARM_GUARD_'+arm)
 setup(c,True)
 seed=source_seed_audit()
 need(seed['source_sha256']==pre['source_seed_audit']['source_sha256'] and seed['hash_header_sha256']==pre['source_seed_audit']['hash_header_sha256'],'SOURCE_CODE_SHA_DRIFT')
 slot=PAIR/'arms'/arm
 need(not slot.exists() and not slot.is_symlink(),'SLOT_ALREADY_EXISTS_'+arm)
 slot.mkdir(parents=True,exist_ok=False)
 graph=slot/'graph.bin';timing=slot/'native.time';stdout=slot/'native.stdout';stderr=slot/'native.stderr'
 cmd=c.build_command(arm,graph,timing)
 need(cmd[0:5]==['/usr/bin/time','-v','-o',str(timing),'taskset'] and cmd[-2:]==['-r91_g6_d2_cap',str(int(arm[1:]))],'COMMAND_MISMATCH')
 writej(slot/'preregister.json',{'pilot_id':'p01','arm':arm,'cap':int(arm[1:]),'script_sha256':sha(Path(__file__)),
    'pilot_preflight_sha256':sha(OUT/'preflight.json'),'original_parent_build_sha256':PARENT_SHA['build_pair_audit.json'],
    'source_seed_audit':seed,'source_elf_sha256':c.PINS['g6_elf'],'cmd':cmd,'cgroup_start':cg,'fixed_order':['C512','C64'],
    'claim_scope':'fixed-seed repeated build timing and scheduling variation ONLY'})
 env=os.environ.copy();env.update(PARLAY_NUM_THREADS='4',OMP_NUM_THREADS='4',OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='1',LC_ALL='C')
 print(TAG+'_BUILD_START_'+arm,flush=True)
 mon=monitor_strict(c,cmd,slot,cg,env)
 parsed=graphreport=t=None;error=None;stage1=None
 try:
  need(c.resource_pass(mon),'CGROUP_OR_EXIT_'+arm)
  need(stderr.stat().st_size==0,'NATIVE_STDERR_NONEMPTY_'+arm)
  parsed=c.parse_native(stdout.read_text(errors='replace'),int(arm[1:]))
  parsed['stage_times']=c.parse_stage(stdout.read_text(errors='replace'))
  graphreport=c.graph_audit(graph)
  t=c.parse_time(timing)
  need(c.native_time_build_ok(t),'GNU_TIME_INVALID_'+arm)
  stage1=stage1_deterministic(c,{'parsed':parsed,'time':t},arm)
  need(sha(c.BIN)==c.PINS['g6_elf'],'G6_ELF_POST_BUILD_DRIFT')
 except Exception as ex:error=str(ex)
 mon=c.refresh_resource_after_audit(mon,cg)
 if not c.resource_pass(mon):error=error or 'CGROUP_POST_AUDIT_FAIL'
 if c.disk_gib()<DISK_MONITOR_GIB:error=error or 'DISK_FREE_BELOW_38GIB_POST_AUDIT'
 receipt={'status':'PILOT_BUILD_GRAPH_WORK_RESOURCE_AUDIT_PASS' if graphreport is not None and parsed is not None and t is not None and stage1 is not None and not error else 'PILOT_BUILD_HOLD_PRESERVE_OUTPUT',
    'pilot_pair':'p01','arm':arm,'cap':int(arm[1:]),'error':error,
    'preflight_sha256':sha(OUT/'preflight.json'),'source_elf_sha256':c.PINS['g6_elf'],
    'source_seed_audit':seed,'native_time':t,'resource':mon,'graph':graphreport,'parsed':parsed,'stage1_baseline_match':stage1,
    'files_sha256':{p.name:sha(p) for p in (stdout,stderr,timing,graph) if regular(p)}}
 writej(slot/'receipt.json',receipt)
 print(TAG+'_'+receipt['status']+'_'+arm+' receipt_sha256 '+sha(slot/'receipt.json'),flush=True)
 need(receipt['status']=='PILOT_BUILD_GRAPH_WORK_RESOURCE_AUDIT_PASS','ARM_FAILED_'+arm)

def check_receipt(c,arm,recheck_graph=True):
 slot=PAIR/'arms'/arm
 r=loadj(slot/'receipt.json')
 need(r['status']=='PILOT_BUILD_GRAPH_WORK_RESOURCE_AUDIT_PASS' and r['arm']==arm and r['pilot_pair']=='p01','RECEIPT_STATUS_'+arm)
 need(r['preflight_sha256']==sha(OUT/'preflight.json') and r['source_elf_sha256']==c.PINS['g6_elf'],'RECEIPT_SOURCE_'+arm)
 need(c.resource_pass(r['resource']) and c.native_time_build_ok(r['native_time']),'RECEIPT_RESOURCES_'+arm)
 for name,digest in r['files_sha256'].items():pin(slot/name,digest,'RECEIPT_FILE_'+arm+'_'+name)
 need(set(r['files_sha256'])=={'native.stdout','native.stderr','native.time','graph.bin'},'RECEIPT_FILE_SET_'+arm)
 need(r['graph']['sha256']==sha(slot/'graph.bin'),'GRAPH_SHA_DRIFT_'+arm)
 if recheck_graph:need(c.graph_audit(slot/'graph.bin')==r['graph'],'GRAPH_FULL_READBACK_'+arm)
 need(c.parse_native((slot/'native.stdout').read_text(errors='replace'),int(arm[1:]))['passes']==r['parsed']['passes'],'NATIVE_LOG_WORK_DRIFT_'+arm)
 need(c.parse_stage((slot/'native.stdout').read_text(errors='replace'))==r['parsed']['stage_times'],'STAGE_TIMES_DRIFT_'+arm)
 need(c.parse_time(slot/'native.time')==r['native_time'],'GNU_TIME_READBACK_'+arm)
 stage1_deterministic(c,{'parsed':r['parsed'],'time':r['native_time']},arm)
 return r

def audit_pair(verify_only=False):
 c=core();c.cgroup(True);check_preflight(c);b,seed=setup(c,True)
 need(seed['source_sha256']==loadj(OUT/'preflight.json')['source_seed_audit']['source_sha256'],'SOURCE_PIPNN_SHA_CHANGED')
 need(seed['hash_header_sha256']==loadj(OUT/'preflight.json')['source_seed_audit']['hash_header_sha256'],'SOURCE_HASH_SHA_CHANGED')
 x=check_receipt(c,'C512');y=check_receipt(c,'C64')
 need(sha(c.BIN)==c.PINS['g6_elf'],'G6_ELF_CHANGED_AFTER_PILOT')
 def present(r):
  p=r['parsed']; return {'arm':r['arm'],'cap':r['cap'],'wall_s':r['native_time']['wall_s'],
    'max_rss_kib':r['native_time']['max_rss_kib'],'cgroup_peak_bytes':r['resource']['cg_peak_bytes'],
    'swap_after':r['resource']['swap_after'],'cgroup_events_delta':r['resource']['events_delta'],
    'major_faults':r['native_time']['major_faults'],'native_stage_s':p['stage_times'],
    'total_wp':p['total_wp'],'depth2_wp':p['depth2_wp'],
    'depth_ge2_wp':sum(sum(int(z['W_P']) for k,z in passrow['depth'].items() if int(k)>=2) for passrow in p['passes']),
    'fallback_maxdepth_points':p['fallback_maxdepth_points'],'fallback_shrink_points':p['fallback_shrink_points'],
    'leaf_memberships':p['total_leaf_memberships'],'graph_sha256':r['graph']['sha256'],
    'graph_arcs':r['graph']['arcs'],'graph_full_all_vertices_audit':True,
    'stage1_baseline_match':r['stage1_baseline_match']['status']}
 dx,dy=present(x),present(y)
 delta={k:{'absolute':dy[k]-dx[k],'relative_percent':100*(dy[k]/dx[k]-1) if dx[k] else None} for k in ('wall_s','max_rss_kib','cgroup_peak_bytes','total_wp','depth2_wp','depth_ge2_wp','graph_arcs','fallback_maxdepth_points')}
 st={part:{'C512':dx['native_stage_s'][part+'_total_s'],'C64':dy['native_stage_s'][part+'_total_s'],
       'delta_s':dy['native_stage_s'][part+'_total_s']-dx['native_stage_s'][part+'_total_s']} for part in ('buckets','leaf','final_prune')}
 summary={'status':'PILOT_PAIR_01_TWO_10M_BUILDS_FULL_AUDIT_PASS_FIVE_PAIRS_NOT_RUN',
   'pilot_pair_id':'p01','order':['C512','C64'],'future_preregistered_schedule':[list(z) for z in ORDER],
   'fixed_seed_555_markers_verified':True,'no_multi_seed_claim':True,
   'source_elf_sha256':c.PINS['g6_elf'],'source_seed_audit':seed,'preflight_sha256':sha(OUT/'preflight.json'),
   'reference_build_summary_sha256':PARENT_SHA['build_pair_audit.json'],
   'C512':dx,'C64':dy,'C64_minus_C512':delta,'stage_time_s':st,
   'source_receipt_sha256':{a:sha(PAIR/'arms'/a/'receipt.json') for a in ('C512','C64')},
   'limits':['A single paired BUILD pilot is not a statistically significant result',
             'Stage1 source seed 555 fixed and counters matched, not a multi-seed sample',
             'Graph variation if any cannot be attributed uniquely to thread schedule without further controls',
             'No native Search performed on new pilot graphs; future quality runs must be separately audited',
             'No rerun/overwrite of previous experiment output']}
 outfile=PAIR/'pilot_pair_audit.json'
 if verify_only:
  need(loadj(outfile)==summary,'PILOT_SUMMARY_READBACK_DRIFT')
 else:writej(outfile,summary)
 print(TAG+'_PILOT_PAIR_01_FULL_AUDIT_PASS_FIVE_PAIRS_NOT_RUN',sha(outfile),flush=True)
 for a in ('C512','C64'):print(TAG+'_SUMMARY_'+a,json.dumps(summary[a],sort_keys=True),flush=True)
 print(TAG+'_PILOT_DELTA',json.dumps(delta,sort_keys=True),flush=True)

def selftest():
 c=core()
 need(ORDER==(('C512','C64'),('C64','C512'),('C64','C512'),('C512','C64'),('C512','C64'),('C64','C512')),'PILOT_SCHEDULE_DRIFT')
 need(len(ORDER)==6 and sum(x[0]=='C512' for x in ORDER)==3,'ORDER_NOT_BALANCED')
 need(PAIR==OUT/'pairs/p01' and MEM==24*2**30,'PAIR_OR_LIMIT_DRIFT')
 need(c.build_command('C512',Path('/tmp/f.graph'),Path('/tmp/f.time'))[-2:]==['-r91_g6_d2_cap','512'],'CMD512_DRIFT')
 need(c.build_command('C64',Path('/tmp/f.graph'),Path('/tmp/f.time'))[-2:]==['-r91_g6_d2_cap','64'],'CMD64_DRIFT')
 for name in PARENT_SHA.values():need(len(name)==64,'PARENT_SHA_BAD')
 for name in GRAPH_PIN.values():need(len(name)==64,'GRAPH_SHA_BAD')
 t={'exit_status':'0','swaps':0,'major_faults':1,'wall_s':372.0,'max_rss_kib':21641624}
 need(c.native_time_build_ok(t),'MAJOR_FAULT1_SHOULD_PASS')
 need(not c.native_time_build_ok({**t,'swaps':1}),'SWAP_MUST_FAIL')
 need(not c.native_time_build_ok({**t,'exit_status':'137'}),'EXIT_MUST_FAIL')
 rec={'status':'COMPLETED','exit_code':0,'sampled_peak_swap':0,'swap_after':0,'cg_peak_bytes':22308368384,
   'min_available_kib':6071720,'events_delta':{'max':0,'oom':0,'oom_kill':0}}
 need(c.resource_pass(rec),'CGROUP_CLEAN_FIXTURE')
 for edited in ({**rec,'swap_after':1},{**rec,'events_delta':{'max':1}},{**rec,'cg_peak_bytes':MEM},
                {**rec,'min_available_kib':1}):need(not c.resource_pass(edited),'CGROUP_BAD_ACCEPTED')
 need(re.search(r'\bSEED\s*=\s*555\b','size_t SEED = 555;') is not None,'SEED_REGEX_FIXTURE')
 need(re.search(r'(?:parlay::)?hash64\s*\(\s*SEED\s*\)','parlay::hash64(SEED)') is not None,'HASH_REGEX_FIXTURE')
 print(TAG+'_SELFTEST_PASS_FROZEN_ELF_FIXED_SEED_555_TWO_ARMS_RESOURCE_STAGE1_AND_ORDER_GATES',flush=True)

def main():
 p=argparse.ArgumentParser();p.add_argument('mode',choices=('selftest','scopecheck','preflight','pilot','audit-pilot'))
 p.add_argument('--arm',choices=('C512','C64'));p.add_argument('--verify-only',action='store_true');a=p.parse_args()
 try:
  if a.mode=='selftest':selftest()
  elif a.mode=='scopecheck':
   c=core();cg=c.cgroup(True);print(TAG+'_SCOPE_PROBE_PASS_24GIB_ZERO_SWAP',cg['root'],flush=True)
  elif a.mode=='preflight':preflight()
  elif a.mode=='pilot':need(a.arm is not None,'ARM_REQUIRED');run_arm(a.arm)
  else:audit_pair(verify_only=a.verify_only)
 except Exception as ex:
  print(TAG+'_HOLD',type(ex).__name__,str(ex),file=sys.stderr,flush=True);raise SystemExit(2)
if __name__=='__main__':main()
