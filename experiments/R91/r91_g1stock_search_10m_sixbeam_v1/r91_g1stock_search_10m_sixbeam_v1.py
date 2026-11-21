#!/usr/bin/env python3
"""R91 Stock 10M Search-only: one native six-beam screen; no ANN build."""
import hashlib,json,math,os,re,shlex,shutil,signal,struct,subprocess,sys,time
from pathlib import Path
H=Path.home(); ROOT=H/'ann-task-a'; R=ROOT/'experiments/R91'; DATA=ROOT/'data/MSTuring_10M_v1'
TAG='R91_G1STOCK_SEARCH_10M_SIXBEAM_V1'; BEAMS=(384,896,1024,1536,1792,2048); GIB=1024**3; CAP=24*GIB
PREF=R/'r91_g1stock_search_10m_sixbeam_preflight_v1'; OUT=R/'r91_g1stock_search_10m_sixbeam_v1'
STOCK=R/'r91_g1stock_one_stock_flat_c160_mst10m_24g_v1'; G1=R/'r91_g1_one_fastv2_flat_c160_mst10m_24g_v1'
EVAL=R/'r91_g1b_v2_native_eval_mst10m_exactguard_v1_1'/'r91_mst10m_recall_exactguard_v2'
GRAPH=STOCK/'graphs/MSTuring10M_stock_off_C160_K1024_N2.graph'; FASTGRAPH=G1/'graphs/MSTuring10M_fast_off_C160_K1024_N2.graph'
BASE=DATA/'base.10M.fbin'; QUERY=DATA/'query.public.100K.fbin'; GT=DATA/'groundtruth.public.100K.ibin'
PIN={
 'stock_result':(STOCK/'stock_result.json','4c64741bde0847465fa237d412d69cf00958a6c2de214d5e82f50d5ef13ceda6'),
 'stock_preflight':(R/'r91_g1stock_native_preflight_v1/preflight.json','7a42faffab06f64a2af88d90c3a855dadd1bb9e109f6a47497b9a8619132629d'),
 'stock_outside':(STOCK/'outside_scope_receipt.json','968f297cd502e281f922520e4a84fbe925bb0e1371362094e2fb15fcd4417cf2'),
 'stock_graph':(GRAPH,'6beda1aa823a49ca928e6046f411a4b6945d2eb56e125d85a50e30c8ab3deffe'),
 'fast_graph':(FASTGRAPH,'4055dedc2ccb3b6406fed45ed28de2ec57c46fe2b085b5046ae13cd943702429'),
 'fast_build':(G1/'r91_g1_single10m_result.json','bd46f8327e634e05ebdf3975c602d3c069df749be8dc3a6e140f286a606e3835'),
 'fast_search':(R/'r91_g1b_v2_mst10m_fast_fixedbeam_search_v1_1/quality_screen_summary.json','960295996dc176dc6d1bb5074ff0543e96f43cba06907b5142c44be8949a44eb'),
 'fast_highbeam':(R/'r91_g1bc_fast10m_highbeam_search_v1/quality_screen_summary.json','ad3be04bbdc83b04d5d71068a44dc74b37b098743a06bdc5b4b2e7260d278a07'),
 'eval_receipt':(EVAL.parent/'eval_build_receipt.json','79373da654e102c9a115eb63bd1aca7937f1349d4a289c181bd9befd27b69f62'),
 'elf':(EVAL,'394c6564750722001897254939ba4895e0d7ae6a6dbab44748c30937ea0413c9'),
 'base':(BASE,'e7756f6b54a07e8af171c7644ce2e1be6d7053ee2a2c30c4b02f99e85984b700'),
 'query':(QUERY,'48d087a17bec15a5ec9ea526fe9bd14ac31bbbb5cd200817b341adbb77695644'),
 'gt':(GT,'77b558bd3b77e4cc1149384996b953b040e412477eb0df9889718fc13e17aff2'),
}
SHAS={k:v[1] for k,v in PIN.items()}; ROW=re.compile(r'^R72_RECALL_ROW beam=(\d+) recall=([^ ]+) qps=([^ ]+) avg_cmps=([^ ]+) avg_visited=([^ ]+)\s*$')
INPUT='R72_RECALL_INPUT_PASS graph_nodes=10000000 queries=100000 gt_k=100'; END='R72_RECALL_EVAL_PASS'
def must(x,msg):
 if not x: raise RuntimeError(TAG+'_HOLD_'+msg)
def sha(p):
 must(p.is_file() and not p.is_symlink(),'NOT_REGULAR_'+p.name)
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(8*1024**2),b''):h.update(b)
 return h.hexdigest()
def js(p):return json.loads(p.read_text())
def save(p,x):
 with p.open('x',encoding='utf-8') as f:json.dump(x,f,indent=2,sort_keys=True,allow_nan=False); f.write('\n')
def absent(p):must(not p.exists() and not p.is_symlink(),'OUTPUT_EXISTS_'+p.name)
def header(p,n,d,size):
 with p.open('rb') as f:must(f.read(8)==struct.pack('<II',n,d),'HEADER_'+p.name)
 must(p.stat().st_size==size,'SIZE_'+p.name)
def references():
 for k,(p,h) in PIN.items():must(sha(p)==h,'SHA_'+k)
 s=js(PIN['stock_result'][0]); p=js(PIN['stock_preflight'][0]); o=js(PIN['stock_outside'][0]); g=s['graph_quality']
 must(s['status']=='R91_G1STOCK_MST10M_24G_V1_NATIVE_BUILD_FULL_GRAPH_PASS' and s['native_exit_code']==0 and s['no_search'] is True,'STOCK_BUILD_STATUS')
 must(s['preflight_sha256']==SHAS['stock_preflight'] and s['pins']==p['pins'] and o['scope_exit_code']==0,'STOCK_RECEIPT_CHAIN')
 must(g['sha256']==SHAS['stock_graph'] and g['full_audit_all_vertices'] is True and g['nodes']==10000000 and g['degree_cap']==64 and g['arcs']==540816693 and g['bytes']==2203266780 and all(g[k]==0 for k in ('full_graph_duplicate_neighbor_rows','full_graph_invalid_id','full_graph_selfloops')),'STOCK_GRAPH_AUDIT')
 must(s['pins']['graph']==SHAS['fast_graph'] and all(s['pins'][k]==SHAS[k] for k in ('base','query','gt')),'DATA_PIN_CHAIN')
 e=js(PIN['eval_receipt'][0]); must(e['status']=='R91_G1B_V2_EVAL_COMPILE_PASS' and e['compile_exit']==0 and e['compiled_elf_sha']==SHAS['elf'] and os.access(EVAL,os.X_OK),'EVAL_RECEIPT')
 old=js(PIN['fast_search'][0]); hi=js(PIN['fast_highbeam'][0]); must(old['source_graph_sha256']==SHAS['fast_graph'] and old['eval_binary_sha256']==SHAS['elf'] and old['status']=='R91_G1B_V2_10M_SEARCH_NATIVE_FIXEDBEAM_PASS' and old['evaluator_exit_code']==0,'FAST_FIRST4')
 must(hi['graph_sha256']==SHAS['fast_graph'] and hi['elf_sha256']==SHAS['elf'] and hi['native_exit_code']==0 and hi['status']=='R91_G1BC_FAST10M_HIGHBEAM_SEARCH_ONLY_V1_NATIVE_SEARCH_PASS','FAST_LAST2')
 for args in [(BASE,10000000,100,4000000008),(QUERY,100000,100,40000008),(GT,100000,100,80000008),(GRAPH,10000000,64,2203266780),(FASTGRAPH,10000000,64,2202769196)]:header(*args)
 must(sha(Path(__file__).resolve())==SCRIPT_SHA,'SCRIPT_CHANGED')
 return SHAS

def resources():
 mem=int(re.search(r'^MemAvailable:\s+(\d+)',Path('/proc/meminfo').read_text(),re.M)[1])*1024; disk=shutil.disk_usage(R).free
 must(mem>=12*GIB,'HOST_MEMAVAILABLE_LT12G'); must(disk>=8*GIB,'DISK_LT8G'); must(0 in os.sched_getaffinity(0),'CPU0_NOT_ALLOWED')
 for name in ('systemd-run','taskset'):must(shutil.which(name) is not None,'MISSING_'+name)
 must(Path('/usr/bin/time').is_file(),'MISSING_GNU_TIME')
 return {'MemAvailable_bytes':mem,'disk_free_bytes':disk,'cpu0_available':True}
def number(cg,k):return int((cg/k).read_text())
def scope():
 x=[v[3:] for v in Path('/proc/self/cgroup').read_text().splitlines() if v.startswith('0::')]; must(len(x)==1,'CGROUP_V2')
 cg=Path('/sys/fs/cgroup')/x[0].lstrip('/')
 must((cg/'memory.max').read_text().strip()==str(CAP) and (cg/'memory.swap.max').read_text().strip()=='0','HARD_CAP_OR_SWAP_CAP')
 for parent in cg.parents:
  if parent==Path('/sys/fs/cgroup'):break
  p=parent/'memory.max'
  if p.exists():
   v=p.read_text().strip(); must(v=='max' or int(v)>=CAP,'ANCESTOR_CAP_LT24G')
 must(number(cg,'memory.swap.current')==0,'NONZERO_SWAP')
 return cg
def event(cg):return {k:int(v) for k,v in (l.split() for l in (cg/'memory.events').read_text().splitlines())}
def scope_cmd(mode):return ['systemd-run','--user','--scope','--collect','--expand-environment=no','-p','MemoryAccounting=yes','-p','MemoryMax=24G','-p','MemorySwapMax=0',sys.executable,str(Path(__file__).resolve()),mode]
def command():return ['taskset','-c','0',str(EVAL),str(GRAPH),str(BASE),str(QUERY),str(GT),','.join(map(str,BEAMS))]
def preflight():
 absent(PREF); absent(OUT); resources(); references(); res=resources(); x=subprocess.run(scope_cmd('scope-check')); must(x.returncode==0,'SCOPE_CHECK')
 PREF.mkdir(exist_ok=False); save(PREF/'preflight.json',{'status':TAG+'_PREFLIGHT_PASS_NO_SEARCH_NO_BUILD','pins':SHAS,'beam_grid':list(BEAMS),'command':command(),'script_sha256':SCRIPT_SHA,'hardcap_bytes':CAP,'swapmax_bytes':0,'resources':res,'no_ann_build':True,'nqueries':100000,'cpu_core':0,'timestamp':time.time()}); print(TAG+'_PREFLIGHT_PASS',sha(PREF/'preflight.json'),flush=True)
def check_pre():
 p=js(PREF/'preflight.json'); must(p['status']==TAG+'_PREFLIGHT_PASS_NO_SEARCH_NO_BUILD' and p['pins']==SHAS and p['beam_grid']==list(BEAMS) and p['command']==command() and p['script_sha256']==SCRIPT_SHA and p['hardcap_bytes']==CAP and p['swapmax_bytes']==0,'PREFLIGHT_MISMATCH');return sha(PREF/'preflight.json')
def parse(text):
 lines=[l.strip() for l in text.splitlines()]; must(lines.count(INPUT)==1 and lines.count(END)==1,'NATIVE_MARKERS')
 found={}
 for l in lines:
  if not l.startswith('R72_RECALL_ROW'):continue
  m=ROW.fullmatch(l); must(m is not None,'MALFORMED_ROW'); b=int(m[1]); r,q,v=map(float,(m[2],m[3],m[5])); must(b in BEAMS and b not in found and all(math.isfinite(z) for z in (r,q,v)) and 0<=r<=1 and q>0 and v>=0,'INVALID_ROW')
  found[b]={'recall_at10':r,'qps':q,'avg_visited':v,'avg_cmps_legacy_untrusted':None,'latency_inverse_qps_us_NOT_P95':1e6/q,'meets_0_99':r>=.99,'meets_0_998':r>=.998}
 must(tuple(found)==BEAMS,'BEAM_GRID_OR_ORDER'); return {str(k):v for k,v in found.items()}
def time_metrics(text):
 def field(name):
  m=re.search(r'^\s*'+re.escape(name)+r':\s*(.*?)\s*$',text,re.M); must(m is not None,'TIME_FIELD_'+name);return m[1]
 elapsed=field('Elapsed (wall clock) time (h:mm:ss or m:ss)'); parts=list(map(float,elapsed.split(':'))); must(len(parts) in (2,3) and all(math.isfinite(z) and z>=0 for z in parts),'TIME_ELAPSED'); wall=sum(x*60**i for i,x in enumerate(reversed(parts)))
 return {'wall_seconds':wall,'max_RSS_KiB':int(field('Maximum resident set size (kbytes)')),'major_page_faults':int(field('Major (requiring I/O) page faults')),'minor_page_faults':int(field('Minor (reclaiming a frame) page faults')),'swaps_time_counter':int(field('Swaps')),'exit_status_time':int(field('Exit status'))}
def in_scope():
 must(OUT.is_dir() and not OUT.is_symlink(),'OUT_NOT_PRESENT'); request=js(OUT/'run_request.json'); must(request['preflight_sha256']==check_pre() and request['script_sha256']==SCRIPT_SHA,'RUN_REQUEST'); cg=scope(); references(); resources()
 log=OUT/'logs'; log.mkdir(exist_ok=False); before=event(cg); sw0=number(cg,'memory.swap.current'); t=time.monotonic(); rc=None; err=None; metrics={}; tm={}; cmd=['/usr/bin/time','-v','-o',str(log/'native.time'),*command()]
 env={**os.environ,'PARLAY_NUM_THREADS':'1','LC_ALL':'C'}; print(TAG+'_NATIVE_SEARCH_START_6BEAMS_NO_BUILD',flush=True)
 try:
  with (log/'native.stdout').open('xb') as so,(log/'native.stderr').open('xb') as se:
   child=subprocess.Popen(cmd,stdout=so,stderr=se,env=env,start_new_session=True)
   try:rc=child.wait(timeout=7200)
   except BaseException:
    try:os.killpg(child.pid,signal.SIGKILL)
    except ProcessLookupError:pass
    child.wait(); raise
  must(rc==0,'NATIVE_EXIT_'+str(rc)); metrics=parse((log/'native.stdout').read_text()); tm=time_metrics((log/'native.time').read_text()); must(tm['exit_status_time']==0 and tm['swaps_time_counter']==0,'GNU_TIME_EXIT_OR_SWAP'); must((log/'native.stderr').stat().st_size==0,'NATIVE_STDERR_NONEMPTY')
 except BaseException as e:err=repr(e)
 after=event(cg); delta={k:after.get(k,0)-before.get(k,0) for k in set(before)|set(after)}; sw1=number(cg,'memory.swap.current'); peak=number(cg,'memory.peak'); good=rc==0 and err is None and sw0==sw1==0 and all(delta.get(k,0)==0 for k in ('oom','oom_kill','oom_group_kill')) and peak<=CAP
 x={'status':TAG+('_NATIVE_SEARCH_PASS' if good else '_HOLD_PRESERVE_LOGS'),'error':err,'native_exit_code':rc,'metrics':metrics,'time_metrics':tm,'elapsed_external_s':time.monotonic()-t,'pins':SHAS,'graph_sha256':SHAS['stock_graph'],'elf_sha256':SHAS['elf'],'beam_grid':list(BEAMS),'cpu_core':0,'nqueries':100000,'no_ann_build':True,'preflight_sha256':check_pre(),'script_sha256':SCRIPT_SHA,'command':cmd,'env_override':{'PARLAY_NUM_THREADS':'1','LC_ALL':'C'},'inherited_OMP_NUM_THREADS':env.get('OMP_NUM_THREADS'),'cgroup_peak_bytes':peak,'cgroup_events_delta':delta,'cgroup_swap_before':sw0,'cgroup_swap_after':sw1,'hardcap_bytes':CAP,'swapmax_bytes':0,'log_shas':{p.name:sha(p) for p in log.iterdir() if p.is_file()},'timestamp':time.time()}
 save(OUT/'quality_screen_summary.json',x); print(TAG+'_RESULT',x['status'],sha(OUT/'quality_screen_summary.json'),flush=True); must(good,'NATIVE_OR_RESOURCE_FAILURE_PRESERVE_LOGS')
def run():
 absent(OUT); h=check_pre(); resources(); OUT.mkdir(exist_ok=False); save(OUT/'run_request.json',{'preflight_sha256':h,'script_sha256':SCRIPT_SHA,'timestamp':time.time()}); p=subprocess.run(scope_cmd('inscope')); must(p.returncode==0,'SCOPE_EXIT_'+str(p.returncode)); print(TAG+'_SCOPE_EXIT0',flush=True)
def audit():
 s=js(OUT/'quality_screen_summary.json'); must(s['status']==TAG+'_NATIVE_SEARCH_PASS' and s['pins']==SHAS and s['preflight_sha256']==check_pre() and s['native_exit_code']==0,'RECEIPT'); must(s['beam_grid']==list(BEAMS) and s['no_ann_build'] is True and s['graph_sha256']==SHAS['stock_graph'] and s['elf_sha256']==SHAS['elf'],'IDENTITY'); must(s['cgroup_swap_before']==s['cgroup_swap_after']==0 and all(s['cgroup_events_delta'].get(k,0)==0 for k in ('oom','oom_kill','oom_group_kill')),'RESOURCE_RECEIPT')
 log=OUT/'logs'; must(set(s['log_shas'])=={'native.stdout','native.stderr','native.time'},'LOG_SET')
 for k,h in s['log_shas'].items():must(sha(log/k)==h,'LOG_SHA_'+k)
 must(parse((log/'native.stdout').read_text())==s['metrics'] and time_metrics((log/'native.time').read_text())==s['time_metrics'],'PARSED_RECEIPT'); references(); print(TAG+'_FINAL_READONLY_AUDIT_PASS',sha(OUT/'quality_screen_summary.json'))
 for b in BEAMS:
  m=s['metrics'][str(b)];print('BEAM',b,'RECALL',m['recall_at10'],'QPS',m['qps'],'AVG_VISITED',m['avg_visited'],'REACH0998',m['meets_0_998'])
 print('BEST_TESTED_099',next((b for b in BEAMS if s['metrics'][str(b)]['meets_0_99']),None),'BEST_TESTED_0998',next((b for b in BEAMS if s['metrics'][str(b)]['meets_0_998']),None))
def selftest():
 rows=[f'R72_RECALL_ROW beam={b} recall={.998 if i>=4 else .985} qps=123.4 avg_cmps=-12 avg_visited=100' for i,b in enumerate(BEAMS)]; text='\n'.join([INPUT,*rows,END]); d=parse(text); assert d['1792']['meets_0_998'] and not d['384']['meets_0_99'] and d['384']['avg_cmps_legacy_untrusted'] is None
 for x in (text.replace('beam=2048','beam=1792'),text.replace('qps=123.4','qps=nan'),text.replace(END,''),text.replace(rows[0]+'\n',''),text.replace('recall=0.998','recall=1.1')):
  try:parse(x)
  except RuntimeError:pass
  else:raise AssertionError('invalid parser case passed')
 assert not parse(text.replace('recall=0.998','recall=0.99799999'))['1792']['meets_0_998']
 t='''Elapsed (wall clock) time (h:mm:ss or m:ss): 1:02:03.45\nMaximum resident set size (kbytes): 123\nMajor (requiring I/O) page faults: 1\nMinor (reclaiming a frame) page faults: 2\nSwaps: 0\nExit status: 0\n'''; assert abs(time_metrics(t)['wall_seconds']-3723.45)<1e-8
 assert len(SHAS)==13 and all(re.fullmatch('[a-f0-9]{64}',h) for h in SHAS.values()); assert 'stock_off' in str(GRAPH) and '-graph_outfile' not in command()
 print(TAG+'_SELFTEST_PASS_SIXBEAM_PARSER_TIME_THRESHOLDS_NO_BUILD')
SCRIPT_SHA=sha(Path(__file__).resolve())
if __name__=='__main__':
 try:
  must(len(sys.argv)==2,'USAGE'); mode=sys.argv[1]
  if mode=='scope-check':scope();print(TAG+'_CGROUP_HARD24G_NOSWAP_PASS')
  else:
   modes={'selftest':selftest,'preflight':preflight,'run':run,'inscope':in_scope,'audit':audit}; must(mode in modes,'MODE');modes[mode]()
 except BaseException as e: print(TAG+'_ERROR',repr(e),file=sys.stderr);sys.exit(2)
