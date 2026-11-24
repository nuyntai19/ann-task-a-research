#!/usr/bin/env python3
"""Pinned, fail-closed, fixed-seed repeated BUILD P02–P06 for R91 G6 10M.

Each pair is executed ONLY by an explicit per-pair command, with a separate
scope per arm; an independently guarded audit must PASS before a later pair.
The pre-registered sequence is AB BA BA AB AB BA. No multi-seed claim.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
import math
import os
import statistics
import sys
from pathlib import Path

TAG='R91_G6_10M_REPEAT_BUILD_P02_P06_V1'
HERE=Path(__file__).resolve().parent
VENDOR_P01=HERE/'vendor_r91_g6_10m_repeat_build_p01_v1.py'
VENDOR_P01_SHA='0b363339c5d02e6cf23701074f06d9f0dc83b7a5516550d9a27d1f1951baa216'
VENDOR_V13=HERE/'vendor_r91_g6_mst10m_pair_v1_3.py'
VENDOR_V13_SHA='0e62c69dcf73f499d4c99e3181c526c0d908150ff6e77ca4d1fde4144801cab7'
HOME=Path.home()
ROOT=HOME/'ann-task-a/experiments/R91/r91_g6_mst10m_repeat_build_6pairs_v1'
PRE=ROOT/'extension_p02_p06_preflight_v1.json'
P01_PRE_SHA='1999377c94cd71a5f1bc2cb5a11c6589645985cb033ef1b264b45d10ab1b0c93'
P01_AUDIT_SHA='5844ca60f5ffa3ab01a6d03b23047ddff0982f60d7a8ccd2793416e029fa575c'
P01_RECEIPT_SHA={
 'C512':'80bc90efdbb41d47d7165e17e684808ddb8adc44c22e8cad66b148724f5590bf',
 'C64':'b668a9966bdb6c62ca1a653aae349cedd51250ed32882c0aee1a94a3400f3888',
}
P01_GRAPHS={
 'C512':'614b2fe5e05b168abdd327cb1dbcd731a70ab142deb85e652c9153053fd905ae',
 'C64':'45b561197a7c1c1dccb2d2ffc72ca7e89e812ea86225f6263d1d8c2dd673d482',
}
SCHEDULE=(('C512','C64'),('C64','C512'),('C64','C512'),('C512','C64'),('C512','C64'),('C64','C512'))
PAIRS=tuple(f'p{i:02}' for i in range(2,7))
MEM=25769803776
DISK_PREFLIGHT_GIB=75
DISK_FIRST_GIB=55
DISK_SECOND_GIB=48
DISK_ABORT_GIB=38
HOST_MEM_KIB=22*1024*1024


def need(cond,why):
 if not cond:raise RuntimeError(TAG+'_HOLD_'+why)

def regular(p):return p.is_file() and not p.is_symlink()

def digest(p):
 need(regular(p),'FILE_MISSING_OR_SYMLINK_'+p.name)
 h=hashlib.sha256()
 with p.open('rb') as f:
  for chunk in iter(lambda:f.read(8*1024*1024),b''):h.update(chunk)
 return h.hexdigest()

def pin(p,sha,why):need(digest(p)==sha,'SHA_DRIFT_'+why)

def readj(p):
 need(regular(p),'JSON_NOT_REGULAR_'+p.name)
 return json.loads(p.read_text(encoding='utf8'))

def writej(p,obj):
 need(not p.exists() and not p.is_symlink(),'OUTPUT_ALREADY_EXISTS_'+p.name)
 t=Path(str(p)+'.part');need(not t.exists() and not t.is_symlink(),'PARTIAL_ALREADY_EXISTS_'+p.name)
 with t.open('x',encoding='utf8') as f:
  json.dump(obj,f,sort_keys=True,indent=2,ensure_ascii=False,allow_nan=False)
  f.write('\n');f.flush();os.fsync(f.fileno())
 os.replace(t,p)

def import_frozen():
 pin(VENDOR_P01,VENDOR_P01_SHA,'ORIGINAL_P01_RUNNER')
 pin(VENDOR_V13,VENDOR_V13_SHA,'ORIGINAL_V13_RUNNER')
 spec=importlib.util.spec_from_file_location('_repeat_p01_verbatim_v1',VENDOR_P01)
 need(spec is not None and spec.loader is not None,'P01_IMPORT')
 mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
 c=mod.core()
 need(mod.TAG=='R91_G6_10M_REPEAT_BUILD_P01_V1','P01_TAG')
 need(mod.OUT==ROOT and mod.MEM==MEM and mod.ORDER==SCHEDULE,'P01_ROOT_OR_PROTOCOL_DRIFT')
 need(c.PINS['g6_elf']=='53be9510ead14aff25ec5adffc07d959c78d575f7ffcc9306435360ce9342690','G6_ELF_DRIFT')
 need(c.CPU_BUILD=='0,2,4,6' and c.LIMIT==MEM,'CPU_MEM_DRIFT')
 return mod,c

def pairs_dir(pid):return ROOT/'pairs'/pid

def pair_order(pid):
 need(pid in PAIRS,'PAIR_INVALID')
 return SCHEDULE[int(pid[1:])-1]

def check_p01(m,c,full=False):
 pin(ROOT/'preflight.json',P01_PRE_SHA,'ORIGINAL_P01_PREFLIGHT')
 pin(pairs_dir('p01')/'pilot_pair_audit.json',P01_AUDIT_SHA,'ORIGINAL_P01_AUDIT')
 for arm in ('C512','C64'):
  pin(pairs_dir('p01')/'arms'/arm/'receipt.json',P01_RECEIPT_SHA[arm],'P01_RECEIPT_'+arm)
  pin(pairs_dir('p01')/'arms'/arm/'graph.bin',P01_GRAPHS[arm],'P01_GRAPH_'+arm)
 p=readj(pairs_dir('p01')/'pilot_pair_audit.json')
 need(p['status']=='PILOT_PAIR_01_TWO_10M_BUILDS_FULL_AUDIT_PASS_FIVE_PAIRS_NOT_RUN','P01_STATUS')
 need(p['future_preregistered_schedule']==[list(z) for z in SCHEDULE] and p['order']==list(SCHEDULE[0]),'P01_ORDER')
 need(p['source_receipt_sha256']==P01_RECEIPT_SHA,'P01_RECEIPT_LINK')
 need(p['source_elf_sha256']==c.PINS['g6_elf'] and p['preflight_sha256']==P01_PRE_SHA,'P01_SOURCE')
 for arm in ('C512','C64'):
  need(p[arm]['stage1_baseline_match']=='STAGE1_COUNTERS_MATCH_V13_REFERENCE','P01_STAGE1_'+arm)
  need(p[arm]['graph_sha256']==P01_GRAPHS[arm] and p[arm]['swap_after']==0,'P01_GRAPH_RESOURCE_'+arm)
  need(all(int(n)==0 for n in p[arm]['cgroup_events_delta'].values()),'P01_EVENTS_'+arm)
 if full:
  m.audit_pair(verify_only=True)  # full 10M graph re-audit & log SHA comparisons in cgroup
 return p

def check_source(m):
 s=m.source_seed_audit()
 orig=readj(ROOT/'preflight.json')['source_seed_audit']
 need(s==orig,'ORIGINAL_P01_FIXED_SEED_SOURCE_DRIFT')
 need(s['seed_555_markers']==[530] and s['hash64_seed_markers']==[456],'SOURCE_LINE_MARKERS_CHANGED')
 return s

def check_extension_preflight(m,c):
 p=readj(PRE)
 need(p['status']=='P02_P06_PREFLIGHT_PASS_NO_NEW_BUILD' and p['script_sha256']==digest(Path(__file__)),'PREFLIGHT_SHA_OR_STATUS')
 need(p['p01_preflight_sha256']==P01_PRE_SHA and p['p01_pair_audit_sha256']==P01_AUDIT_SHA,'PREFLIGHT_P01_PIN')
 need(p['order']==[list(x) for x in SCHEDULE] and p['eligible_pairs']==list(PAIRS),'PREFLIGHT_ORDER')
 need(p['vendor_p01_sha256']==VENDOR_P01_SHA and p['vendor_v13_sha256']==VENDOR_V13_SHA,'PREFLIGHT_VENDOR')
 need(p['source_seed_audit']==check_source(m),'PREFLIGHT_SOURCE_DRIFT')
 need(p['resource']['memory_bytes']==MEM and p['resource']['swap_max_bytes']==0,'PREFLIGHT_RESOURCE')
 return p

def preflight():
 m,c=import_frozen()
 c.cgroup(True)
 need(ROOT.is_dir() and not ROOT.is_symlink(),'ORIGINAL_OUTPUT_ROOT_MISSING')
 need((ROOT/'pairs').is_dir() and not (ROOT/'pairs').is_symlink(),'PAIR_PARENT_NOT_DIR')
 need(not PRE.exists() and not PRE.is_symlink(),'EXTENSION_PREFLIGHT_EXISTS')
 need(not (ROOT/'repeat_6pair_summary.json').exists(),'AGGREGATE_EXISTS')
 for pid in PAIRS:
  need(not pairs_dir(pid).exists() and not pairs_dir(pid).is_symlink(),'PAIR_ALREADY_PRESENT_'+pid)
 m.setup(c,True)  # pins original 10M parent graphs/ELF/dataset and G4 lineage
 check_p01(m,c,full=True)
 seed=check_source(m)
 need(c.host_memory_kib()>=HOST_MEM_KIB,'HOST_MEMAVAILABLE_BELOW_22GIB')
 need(c.disk_gib()>=DISK_PREFLIGHT_GIB,'DISK_FREE_BELOW_75GIB')
 obj={'status':'P02_P06_PREFLIGHT_PASS_NO_NEW_BUILD','script_sha256':digest(Path(__file__)),
  'vendor_p01_sha256':VENDOR_P01_SHA,'vendor_v13_sha256':VENDOR_V13_SHA,
  'p01_preflight_sha256':P01_PRE_SHA,'p01_pair_audit_sha256':P01_AUDIT_SHA,
  'p01_receipt_sha256':P01_RECEIPT_SHA,'p01_graph_sha256':P01_GRAPHS,
  'source_seed_audit':seed,'g6_elf_sha256':c.PINS['g6_elf'],
  'order':[list(x) for x in SCHEDULE],'eligible_pairs':list(PAIRS),
  'resource':{'memory_bytes':MEM,'swap_max_bytes':0,'cpu_build':'0,2,4,6','threads':4,
     'disk_preflight_min_gib':DISK_PREFLIGHT_GIB,'disk_before_first_gib':DISK_FIRST_GIB,
     'disk_before_second_gib':DISK_SECOND_GIB,'abort_if_disk_below_gib':DISK_ABORT_GIB,
     'host_memavailable_min_kib':HOST_MEM_KIB},
  'scope':'FIXED_STAGE1_SEED555_REPEATED_PAIRED_BUILDS_NOT_MULTISEED',
  'scientific_limits':['Only fixed seed 555; 6 BUILD timing pairs are not six independent cluster seeds',
    'Stage2 graph differences cannot uniquely be attributed to thread scheduling',
    'This preflight starts no native BUILD; each pair requires explicit run and separate audit',
    'Conditional sign test does not establish statistical speedup under correlated system noise',
    'No Search is run on new graphs'],}
 writej(PRE,obj)
 print(TAG+'_PREFLIGHT_PASS_NO_BUILD',digest(PRE),flush=True)

def context(m,c,pid,deep_previous=False):
 check_extension_preflight(m,c)
 m.setup(c,True)
 check_p01(m,c,full=False)
 n=int(pid[1:]);prev=f'p{n-1:02}'
 if prev=='p01':return
 _=audit_pair(m,c,prev,verify_only=True,full_graph=deep_previous)

def stage1(c,parsed,nativetime,arm):
 # Match original v1.3 full Stage 1 pass and work counters for same arm.
 ref=readj(m_path(arm))['parsed']
 keys=('passes','native_comparisons','total_wp','depth2_wp','depth2_original_wp',
       'total_leaf_memberships','fallback_maxdepth_points','fallback_shrink_points')
 for key in keys:need(parsed.get(key)==ref.get(key),'STAGE1_REF_DRIFT_'+arm+'_'+key)
 need(nativetime['wall_s']>0,'WALL_NONPOSITIVE_'+arm)
 return 'STAGE1_COUNTERS_MATCH_V13_REFERENCE'

def m_path(arm):
 return HOME/'ann-task-a/experiments/R91/r91_g6_mst10m_c512_c64_pair_v1_3/runs'/arm/'receipt.json'

def run_arm(pid,arm):
 m,c=import_frozen()
 cgroup=c.cgroup(True)
 need(arm in pair_order(pid),'ARM_NOT_IN_PAIR')
 need(not (ROOT/'repeat_6pair_summary.json').exists(),'AGGREGATE_ALREADY_EXISTS')
 first,second=pair_order(pid)
 context(m,c,pid,deep_previous=False)
 p=pairs_dir(pid)
 if arm==first:
  need(not p.exists() and not p.is_symlink(),'PAIR_ALREADY_EXISTS_'+pid)
 else:
  need(p.is_dir() and not p.is_symlink(),'PAIR_DIR_MISSING')
  check_receipt(m,c,pid,first,full_graph=True)
  need(not (p/'pair_audit.json').exists(),'PAIR_AUDIT_ALREADY_EXISTS')
 need(c.host_memory_kib()>=HOST_MEM_KIB,'HOST_MEMAVAILABLE_BELOW_22GIB')
 need(c.disk_gib()>=(DISK_FIRST_GIB if arm==first else DISK_SECOND_GIB),'DISK_BELOW_PRE_ARM_GUARD')
 slot=p/'arms'/arm
 need(not slot.exists() and not slot.is_symlink(),'ARM_ALREADY_EXISTS_'+pid+'_'+arm)
 slot.mkdir(parents=True,exist_ok=False)
 graph=slot/'graph.bin';timing=slot/'native.time';stdout=slot/'native.stdout';stderr=slot/'native.stderr'
 cmd=c.build_command(arm,graph,timing)
 need(cmd[0:5]==['/usr/bin/time','-v','-o',str(timing),'taskset'] and cmd[-2:]==['-r91_g6_d2_cap',str(int(arm[1:]))],'COMMAND_DRIFT')
 writej(slot/'preregister.json',{'pair_id':pid,'arm':arm,'cap':int(arm[1:]),
  'script_sha256':digest(Path(__file__)),'extension_preflight_sha256':digest(PRE),
  'p01_audit_sha256':P01_AUDIT_SHA,'source_elf_sha256':c.PINS['g6_elf'],
  'fixed_seed_555':True,'order':list(pair_order(pid)),'command':cmd,'cgroup_start':cgroup,
  'claim_scope':'repeated build fixed seed timing; no multi-seed or causal scheduling claim'})
 env=os.environ.copy()
 env.update(PARLAY_NUM_THREADS='4',OMP_NUM_THREADS='4',OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='1',LC_ALL='C')
 print(TAG+'_BUILD_START_'+pid+'_'+arm,flush=True)
 monitor=m.monitor_strict(c,cmd,slot,cgroup,env)
 parsed=graphreport=t=None;err=None;stage=None
 try:
  need(c.resource_pass(monitor),'PROCESS_RESOURCES_OR_EXIT_'+pid+'_'+arm)
  need(stderr.stat().st_size==0,'NATIVE_STDERR_NONEMPTY')
  txt=stdout.read_text(errors='replace')
  parsed=c.parse_native(txt,int(arm[1:]))
  parsed['stage_times']=c.parse_stage(txt)
  graphreport=c.graph_audit(graph)
  t=c.parse_time(timing)
  need(c.native_time_build_ok(t),'GNU_TIME_INVALID')
  stage=stage1(c,parsed,t,arm)
  need(digest(c.BIN)==c.PINS['g6_elf'],'ELF_CHANGED_AFTER_BUILD')
 except Exception as ex:err=str(ex)
 monitor=c.refresh_resource_after_audit(monitor,cgroup)
 if not c.resource_pass(monitor):err=err or 'RESOURCE_POST_AUDIT_FAIL'
 if c.disk_gib()<DISK_ABORT_GIB:err=err or 'DISK_FREE_BELOW_38GIB'
 ok=(graphreport is not None and parsed is not None and t is not None and stage is not None and not err)
 receipt={'status':'BUILD_GRAPH_WORK_RESOURCE_AUDIT_PASS' if ok else 'BUILD_HOLD_PRESERVE_OUTPUT',
  'pair_id':pid,'arm':arm,'cap':int(arm[1:]),'order':list(pair_order(pid)),
  'error':err,'preflight_sha256':digest(PRE),'source_elf_sha256':c.PINS['g6_elf'],
  'source_seed_audit':check_source(m),'native_time':t,'resource':monitor,
  'graph':graphreport,'parsed':parsed,'stage1_baseline_match':stage,
  'files_sha256':{z.name:digest(z) for z in (stdout,stderr,timing,graph) if regular(z)}}
 writej(slot/'receipt.json',receipt)
 print(TAG+'_'+receipt['status']+'_'+pid+'_'+arm+' receipt_sha256 '+digest(slot/'receipt.json'),flush=True)
 need(ok,'BUILD_ARM_FAILED_PRESERVE_OUTPUT_'+pid+'_'+arm)

def check_receipt(m,c,pid,arm,full_graph=False):
 slot=pairs_dir(pid)/'arms'/arm
 r=readj(slot/'receipt.json')
 need(r['status']=='BUILD_GRAPH_WORK_RESOURCE_AUDIT_PASS','ARM_NOT_PASS_'+pid+'_'+arm)
 need(r['pair_id']==pid and r['arm']==arm and r['cap']==int(arm[1:]) and r['order']==list(pair_order(pid)),'ARM_LABEL_DRIFT')
 need(r['preflight_sha256']==digest(PRE) and r['source_elf_sha256']==c.PINS['g6_elf'],'ARM_SOURCE_DRIFT')
 need(c.resource_pass(r['resource']) and c.native_time_build_ok(r['native_time']),'ARM_RESOURCE_FAILED')
 need(r['stage1_baseline_match']=='STAGE1_COUNTERS_MATCH_V13_REFERENCE','ARM_STAGE1_STATUS')
 need(set(r['files_sha256'])=={'graph.bin','native.stdout','native.stderr','native.time'},'ARM_FILE_SET')
 for name,sha in r['files_sha256'].items():pin(slot/name,sha,'ARM_FILE_'+pid+'_'+arm+'_'+name)
 need(r['graph']['sha256']==digest(slot/'graph.bin'),'ARM_GRAPH_SHA')
 if full_graph:need(c.graph_audit(slot/'graph.bin')==r['graph'],'ARM_FULL_GRAPH_READBACK')
 txt=(slot/'native.stdout').read_text(errors='replace')
 need(c.parse_native(txt,int(arm[1:]))['passes']==r['parsed']['passes'],'ARM_PASSES_DRIFT')
 need(c.parse_stage(txt)==r['parsed']['stage_times'],'ARM_TIMES_DRIFT')
 need(c.parse_time(slot/'native.time')==r['native_time'],'ARM_GNU_TIME_DRIFT')
 stage1(c,r['parsed'],r['native_time'],arm)
 return r

def summarize(r):
 p=r['parsed'];t=r['native_time']
 return {'arm':r['arm'],'cap':r['cap'],'wall_s':t['wall_s'],
  'max_rss_kib':t['max_rss_kib'],'cgroup_peak_bytes':r['resource']['cg_peak_bytes'],
  'swap_after':r['resource']['swap_after'],'cgroup_events_delta':r['resource']['events_delta'],
  'major_faults':t['major_faults'],'stage_times':p['stage_times'],
  'total_wp':p['total_wp'],'depth2_wp':p['depth2_wp'],
  'depth_ge2_wp':sum(sum(int(z['W_P']) for k,z in x['depth'].items() if int(k)>=2) for x in p['passes']),
  'leaf_count':sum(x['cap']['leaf_count'] for x in p['passes']),
  'fallback_maxdepth_points':p['fallback_maxdepth_points'],
  'fallback_shrink_points':p['fallback_shrink_points'],
  'graph_sha256':r['graph']['sha256'],'graph_arcs':r['graph']['arcs'],
  'graph_full_all_vertices_audit':True,'stage1_baseline_match':r['stage1_baseline_match']}

def audit_pair(m,c,pid,verify_only=False,full_graph=True):
 need(pid in PAIRS,'PAIR_INVALID')
 check_extension_preflight(m,c)
 r={arm:check_receipt(m,c,pid,arm,full_graph=full_graph) for arm in ('C512','C64')}
 x,y=summarize(r['C512']),summarize(r['C64'])
 ratio=lambda z:100*(y[z]/x[z]-1) if x[z] else None
 diff={k:{'absolute':y[k]-x[k],'relative_percent':ratio(k)} for k in (
  'wall_s','max_rss_kib','cgroup_peak_bytes','total_wp','depth2_wp',
  'depth_ge2_wp','graph_arcs','fallback_maxdepth_points')}
 parts=('buckets','leaf','final_prune')
 times={k:{'C512':x['stage_times'][k+'_total_s'],'C64':y['stage_times'][k+'_total_s'],
  'delta_s':y['stage_times'][k+'_total_s']-x['stage_times'][k+'_total_s']} for k in parts}
 d={'status':'PAIRED_BUILD_FULL_AUDIT_PASS','pair_id':pid,'order':list(pair_order(pid)),
  'preflight_sha256':digest(PRE),'p01_audit_sha256':P01_AUDIT_SHA,
  'source_elf_sha256':c.PINS['g6_elf'],'source_seed_audit':check_source(m),
  'C512':x,'C64':y,'C64_minus_C512':diff,'stage_time_s':times,
  'source_receipt_sha256':{a:digest(pairs_dir(pid)/'arms'/a/'receipt.json') for a in ('C512','C64')},
  'limitations':['Fixed Stage1 seed=555; not randomized leader seeds',
   'Same hardware / separate native scopes / sequential fixed-order pair',
   'No Search quality on the new graph pair',
   'Graph SHA variations cannot be uniquely attributed to scheduling alone']}
 dest=pairs_dir(pid)/'pair_audit.json'
 if verify_only:
  need(readj(dest)==d,'PAIRED_AUDIT_READBACK_DRIFT_'+pid)
 else:
  writej(dest,d)
 print(TAG+'_PAIRED_BUILD_FULL_AUDIT_PASS_'+pid,digest(dest),flush=True)
 return d

def pilot_audit(pid,verify_only=False):
 m,c=import_frozen();c.cgroup(True)
 context(m,c,pid,deep_previous=False)
 s=audit_pair(m,c,pid,verify_only=verify_only,full_graph=True)
 for arm in ('C512','C64'):
  print(TAG+'_SUMMARY_'+pid+'_'+arm,json.dumps(s[arm],sort_keys=True),flush=True)
 print(TAG+'_DELTA_'+pid,json.dumps(s['C64_minus_C512'],sort_keys=True),flush=True)

def collect_all(m,c,verify_only=False):
 check_extension_preflight(m,c)
 m.setup(c,True)
 p01=check_p01(m,c,full=False)
 per={'p01':{'order':list(SCHEDULE[0]),'C512':p01['C512'],'C64':p01['C64'],
   'delta':p01['C64_minus_C512']['wall_s'],'audit_sha256':P01_AUDIT_SHA}}
 for pid in PAIRS:
  s=audit_pair(m,c,pid,verify_only=True,full_graph=False)
  per[pid]={'order':s['order'],'C512':s['C512'],'C64':s['C64'],
    'delta':s['C64_minus_C512']['wall_s'],'audit_sha256':digest(pairs_dir(pid)/'pair_audit.json')}
 gains=[-per[p]['delta']['absolute'] for p in ('p01',)+PAIRS]
 w512=[per[p]['C512']['wall_s'] for p in ('p01',)+PAIRS]
 w64=[per[p]['C64']['wall_s'] for p in ('p01',)+PAIRS]
 ratios=[w512[i]/w64[i] for i in range(6)]
 need(all(x>0 and math.isfinite(x) for x in w512+w64),'WALL_INVALID')
 s={'status':'SIX_PAIRED_FIXED_SEED_BUILDS_AUDIT_PASS_NO_SEARCH','order':[list(z) for z in SCHEDULE],
  'preflight_sha256':digest(PRE),'source_elf_sha256':c.PINS['g6_elf'],
  'source_seed_audit':check_source(m),'p01_audit_sha256':P01_AUDIT_SHA,
  'pairs':per,'stats':{'n_pairs':6,'C512_wall_median_s':statistics.median(w512),
   'C64_wall_median_s':statistics.median(w64),'median_C512_minus_C64_s':statistics.median(gains),
   'min_C512_minus_C64_s':min(gains),'max_C512_minus_C64_s':max(gains),
   'C64_faster_pairs':sum(z>0 for z in gains),'geomean_C512_over_C64':math.exp(sum(math.log(q) for q in ratios)/6),
   'sign_test_one_sided_if_all_six_faster':1/64 if all(z>0 for z in gains) else None},
  'claims_limit':['Conditional sign probability is a descriptive test requiring independent exchangeable sign assumptions',
   'Stage1 uses fixed seed 555; this is not multi-seed statistical independence',
   'Graph-SHA drift is not proof of solely thread-scheduling causality',
   'No native Search or quality evaluation of 10 new graph outputs in this extension',
   'No p95/p99 and no formal cross-graph Recall noninferiority']}
 dest=ROOT/'repeat_6pair_summary.json'
 if verify_only:
  need(readj(dest)==s,'SIX_PAIR_SUMMARY_READBACK_DRIFT')
 else:writej(dest,s)
 print(TAG+'_SIX_PAIR_AGGREGATE_AUDIT_PASS',digest(dest),flush=True)
 print(TAG+'_SIX_PAIR_STATS',json.dumps(s['stats'],sort_keys=True),flush=True)

def selftest():
 m,c=import_frozen()
 need(PAIRS==('p02','p03','p04','p05','p06'),'PAIR_LIST_DRIFT')
 need(SCHEDULE==m.ORDER and sum(x[0]=='C512' for x in SCHEDULE)==3,'SCHEDULE_DRIFT')
 need(pair_order('p02')==('C64','C512') and pair_order('p03')==('C64','C512'),'ORDER_BA')
 need(pair_order('p04')==('C512','C64') and pair_order('p05')==('C512','C64'),'ORDER_AB')
 need(pair_order('p06')==('C64','C512'),'ORDER_FINAL')
 need(MEM==24*2**30 and DISK_PREFLIGHT_GIB==75 and DISK_ABORT_GIB==m.DISK_MONITOR_GIB,'GUARD_DRIFT')
 need(stage1.__name__=='stage1','STAGE1_FN')
 m.selftest()
 # Ensure parser keeps source uint64 work without accidentally using avg_cmps legacy.
 need('avg_cmps' not in summarize.__code__.co_names,'LEGACY_AVG_CMPS_MISUSE')
 print(TAG+'_SELFTEST_PASS_ORDER_P02_P06_PINNED_P01_V13_STAGE1_RESOURCE_NO_OVERWRITE',flush=True)

def main():
 p=argparse.ArgumentParser()
 p.add_argument('mode',choices=('selftest','scopecheck','preflight','build-arm','audit-pair','aggregate'))
 p.add_argument('--pair',choices=PAIRS)
 p.add_argument('--arm',choices=('C512','C64'))
 p.add_argument('--verify-only',action='store_true')
 args=p.parse_args()
 try:
  if args.mode=='selftest':selftest()
  elif args.mode=='scopecheck':
   m,c=import_frozen();cg=c.cgroup(True)
   print(TAG+'_SCOPE_PROBE_PASS_24GIB_ZERO_SWAP',cg['root'],flush=True)
  elif args.mode=='preflight':preflight()
  elif args.mode=='build-arm':
   need(args.pair in PAIRS and args.arm is not None,'PAIR_ARM_REQUIRED')
   run_arm(args.pair,args.arm)
  elif args.mode=='audit-pair':
   need(args.pair in PAIRS,'PAIR_REQUIRED');pilot_audit(args.pair,verify_only=args.verify_only)
  else:collect_all(*import_frozen(),verify_only=args.verify_only)
 except Exception as ex:
  print(TAG+'_HOLD',type(ex).__name__,str(ex),file=sys.stderr,flush=True)
  raise SystemExit(2)
if __name__=='__main__':main()
