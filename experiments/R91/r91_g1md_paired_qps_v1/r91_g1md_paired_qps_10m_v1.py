#!/usr/bin/env python3
"""R91 G1M-A: two frozen 10M graphs, calibration only; no ANN build."""
import hashlib,json,math,os,re,shlex,shutil,signal,struct,subprocess,sys,time
from pathlib import Path
H=Path.home(); ROOT=H/'ann-task-a'; R=ROOT/'experiments/R91'; DATA=ROOT/'data/MSTuring_10M_v1'
TAG='R91_G1MD_10M_PAIRED_QPS_V1'; BEAMS=(576,1792); GIB=1024**3; CAP=24*GIB
PREF=R/'r91_g1md_paired_qps_preflight_v1'; OUT=R/'r91_g1md_paired_qps_v1'
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
PIN.update({
 'stock_search':(R/'r91_g1stock_search_10m_sixbeam_v1/quality_screen_summary.json','499c5608956d8c33a8d206b039074f871065546de32b7edbde49ced5acd60e6d'),
 'stock_search_preflight':(R/'r91_g1stock_search_10m_sixbeam_preflight_v1/preflight.json','a883034f6c1960a78c173ddc65bb3de6d8b8c068b354363c0d7841ea65b64ae5'),
})
PIN.update({
 'g1ma_preflight':(R/'r91_g1ma_calibration_preflight_v1/preflight.json','6b61c57be18b6eff419159f7d8827edfa7f374117087015941211bc779fd3ed4'),
 'g1ma_summary':(R/'r91_g1ma_calibration_v1/calibration_summary.json','e534316cfbe0a2ddd8a7b7d73b6ad5d114930f8929db379d17b8692235e7e13e'),
 'g1ma_stock_receipt':(R/'r91_g1ma_calibration_v1/stock/receipt.json','017ef6c3b21d0c7188ed7d1fc755fdefb70f5f505170c996ef92d44188248dfc'),
 'g1ma_fast_receipt':(R/'r91_g1ma_calibration_v1/fast/receipt.json','00a1ba5136409988df4e8e05530c22ff801945b4ae6c3569b80470bcba686dc7'),
})
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
 ss=js(PIN['stock_search'][0]); pp=js(PIN['stock_search_preflight'][0]); must(ss['status']=='R91_G1STOCK_SEARCH_10M_SIXBEAM_V1_NATIVE_SEARCH_PASS' and ss['native_exit_code']==0 and ss['preflight_sha256']==SHAS['stock_search_preflight'] and ss['pins']==pp['pins'] and ss['elf_sha256']==SHAS['elf'] and ss['graph_sha256']==SHAS['stock_graph'] and ss['beam_grid']==[384,896,1024,1536,1792,2048],'STOCK_SEARCH_CHAIN')
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

ARMS=('stock','fast')
GRAPHS={'stock':GRAPH,'fast':FASTGRAPH}
ENV={'PARLAY_NUM_THREADS':'1','LC_ALL':'C','OMP_NUM_THREADS':'1'}
# Each within-round pair uses its own fresh native process and scope.
# Three rounds cannot perfectly balance each beam's order. Overall 3 pairs are
# Stock-first and 3 Fast-first, and each beam reverses order across rounds.
SCHEDULE=(
 (1,576,'stock'),(1,576,'fast'),(1,1792,'fast'),(1,1792,'stock'),
 (2,576,'fast'),(2,576,'stock'),(2,1792,'stock'),(2,1792,'fast'),
 (3,576,'stock'),(3,576,'fast'),(3,1792,'fast'),(3,1792,'stock'),
)
EXPECTED_RECALL={(576,'stock'):0.99118501,(576,'fast'):0.99129599,
                 (1792,'stock'):0.99811602,(1792,'fast'):0.99817097}

def calibration():
 c=js(PIN['g1ma_summary'][0]);p=js(PIN['g1ma_preflight'][0]);must(c['status']=='R91_G1MA_10M_CALIBRATION_V1_NATIVE_CALIBRATION_PASS' and c['preflight_sha256']==SHAS['g1ma_preflight'] and c['plan']==p['plan'],'CALIB_CHAIN')
 must(c['arm_receipt_sha256']=={'stock':SHAS['g1ma_stock_receipt'],'fast':SHAS['g1ma_fast_receipt']},'CALIB_RECEIPT_CHAIN')
 for arm in ARMS:
  q=js(PIN['g1ma_'+arm+'_receipt'][0]);must(q['arm']==arm and q['native_exit_code']==0 and q['preflight_sha256']==SHAS['g1ma_preflight'] and q['status']=='R91_G1MA_10M_CALIBRATION_V1_ARM_SEARCH_PASS','CALIB_ARM')
  for beam,target in ((576,.99),(1792,.998)):
   must(float(c['all_recall'][arm][str(beam)])>=target and abs(float(c['all_recall'][arm][str(beam)])-EXPECTED_RECALL[(beam,arm)])<1e-8,'CALIB_QUALITY_FLOOR')
 return c

def command(beam,arm):
 must(arm in ARMS and beam in BEAMS,'RUN_PARAMS')
 return ['taskset','-c','0',str(EVAL),str(GRAPHS[arm]),str(BASE),str(QUERY),str(GT),str(beam)]

def ident(round_,beam,arm):
 must((round_,beam,arm) in SCHEDULE,'UNKNOWN_SLOT')
 return f'r{round_}_b{beam}_{arm}'

def order_manifest():
 return [{'round':r,'beam':b,'arm':a,'slot':ident(r,b,a)} for r,b,a in SCHEDULE]

def plan():
 return {'rounds':3,'beams':list(BEAMS),'schedule':order_manifest(),
         'pins':SHAS,'source_script_sha256':SCRIPT_SHA,'commands':{f'b{b}_{a}':command(b,a) for b in BEAMS for a in ARMS},
         'cpu':0,'threads':1,'env':ENV,'nqueries':100000,'hardcap_bytes':CAP,'swapmax_bytes':0,
         'no_ann_build':True,'goal':'PILOT_PAIRED_INTERLEAVED_QPS_AT_THRESHOLD_RECALL_NOT_FORMAL_NONINFERIORITY'}

def parse_one(text,beam):
 lines=[l.strip() for l in text.splitlines()]
 must(lines.count(INPUT)==1 and lines.count(END)==1,'NATIVE_MARKERS')
 found=[]
 for line in lines:
  if line.startswith('R72_RECALL_ROW'):
   m=ROW.fullmatch(line);must(m is not None,'MALFORMED_ROW')
   b=int(m.group(1)); must(b==beam,'UNEXPECTED_BEAM')
   r,q,vis=map(float,[m.group(2),m.group(3),m.group(5)])
   must(all(map(math.isfinite,(r,q,vis))) and 0<=r<=1 and q>0 and vis>=0,'ROW_VALUES')
   found.append({'beam':b,'recall_at10':r,'qps':q,'avg_visited':vis,
      'latency_inverse_qps_us_NOT_P95':1e6/q,'avg_cmps_legacy_untrusted':None,
      'meets_0_990':r>=.99,'meets_0_998':r>=.998})
 must(len(found)==1,'NOT_EXACTLY_ONE_BEAM');return found[0]

def preflight():
 absent(PREF);absent(OUT);resources();references();calibration()
 res=resources();p=subprocess.run(scope_cmd('scope-check'));must(p.returncode==0,'SCOPE_CHECK')
 PREF.mkdir(exist_ok=False);save(PREF/'preflight.json',{'status':TAG+'_PREFLIGHT_PASS_NO_SEARCH_NO_BUILD','plan':plan(),'resources':res,'timestamp':time.time()})
 print(TAG+'_PREFLIGHT_PASS',sha(PREF/'preflight.json'),flush=True)

def check_pre():
 x=js(PREF/'preflight.json');must(x['status']==TAG+'_PREFLIGHT_PASS_NO_SEARCH_NO_BUILD' and x['plan']==plan(),'PREFLIGHT_MISMATCH')
 return sha(PREF/'preflight.json')

def scoped_run(round_,beam,arm):
 name=ident(round_,beam,arm)
 must(OUT.is_dir() and not OUT.is_symlink(),'OUTPUT_ROOT')
 x=js(OUT/'run_request.json');must(x['plan']==plan() and x['preflight_sha256']==check_pre(),'RUN_REQUEST')
 cg=scope();resources();references();calibration()
 d=OUT/'runs'/name;d.mkdir(parents=False,exist_ok=False)
 start_events=event(cg);sw0=number(cg,'memory.swap.current');start=time.monotonic();native_rc=None;error=None;m={};tm={}
 cmd=['/usr/bin/time','-v','-o',str(d/'native.time'),*command(beam,arm)]
 print(TAG+'_NATIVE_START',name,flush=True)
 try:
  with (d/'native.stdout').open('xb') as so,(d/'native.stderr').open('xb') as se:
   p=subprocess.Popen(cmd,stdout=so,stderr=se,env={**os.environ,**ENV},start_new_session=True)
   try:native_rc=p.wait(timeout=1800)
   except BaseException:
    try:os.killpg(p.pid,signal.SIGKILL)
    except ProcessLookupError:pass
    p.wait();raise
  must(native_rc==0,'NATIVE_RC_'+str(native_rc));m=parse_one((d/'native.stdout').read_text(),beam)
  tm=time_metrics((d/'native.time').read_text());must(tm['exit_status_time']==0 and tm['swaps_time_counter']==0,'TIME_EXIT_OR_SWAP')
  must((d/'native.stderr').stat().st_size==0,'NATIVE_STDERR')
  target=.99 if beam==576 else .998
  must(m['recall_at10']>=target,'RECALL_FLOOR')
 except BaseException as e:error=repr(e)
 now=event(cg);delta={k:now.get(k,0)-start_events.get(k,0) for k in set(now)|set(start_events)}
 sw1=number(cg,'memory.swap.current');peak=number(cg,'memory.peak')
 good=(native_rc==0 and error is None and sw0==sw1==0 and peak<=CAP and all(delta.get(k,0)==0 for k in ('max','oom','oom_kill','oom_group_kill')))
 receipt={'status':TAG+('_RUN_PASS' if good else '_RUN_HOLD'),'slot':name,'round':round_,'beam':beam,'arm':arm,
          'native_exit_code':native_rc,'error':error,'metrics':m,'time_metrics':tm,'elapsed_external_s':time.monotonic()-start,
          'command':cmd,'graph_sha256':SHAS[arm+'_graph'],'evaluator_sha256':SHAS['elf'],
          'preflight_sha256':check_pre(),'plan':plan(),'cgroup_peak_bytes':peak,'cgroup_events_delta':delta,
          'cgroup_swap_before':sw0,'cgroup_swap_after':sw1,
          'log_shas':{a.name:sha(a) for a in d.iterdir() if a.is_file()},'timestamp':time.time()}
 save(d/'receipt.json',receipt)
 print(TAG+'_RUN_RESULT',name,receipt['status'],sha(d/'receipt.json'),flush=True)
 must(good,'NATIVE_FAILURE_PRESERVE_ALL_ARTIFACTS')

def verify_run(round_,beam,arm):
 name=ident(round_,beam,arm);d=OUT/'runs'/name;x=js(d/'receipt.json')
 must(x['status']==TAG+'_RUN_PASS' and x['slot']==name and x['round']==round_ and x['beam']==beam and x['arm']==arm,'RECEIPT_ID')
 must(x['plan']==plan() and x['preflight_sha256']==check_pre() and x['graph_sha256']==SHAS[arm+'_graph'] and x['evaluator_sha256']==SHAS['elf'],'RECEIPT_PINS')
 must(x['command']==['/usr/bin/time','-v','-o',str(d/'native.time'),*command(beam,arm)] and x['native_exit_code']==0,'RECEIPT_COMMAND')
 must(x['cgroup_swap_before']==x['cgroup_swap_after']==0 and x['cgroup_peak_bytes']<=CAP and all(x['cgroup_events_delta'].get(k,0)==0 for k in ('max','oom','oom_kill','oom_group_kill')),'RECEIPT_RESOURCES')
 must(set(x['log_shas'])=={'native.stdout','native.stderr','native.time'},'RECEIPT_LOGSET')
 for filename,h in x['log_shas'].items():must(sha(d/filename)==h,'LOG_SHA_'+name+'_'+filename)
 must(parse_one((d/'native.stdout').read_text(),beam)==x['metrics'] and time_metrics((d/'native.time').read_text())==x['time_metrics'],'METRIC_REPARSE')
 must((d/'native.stderr').stat().st_size==0 and x['time_metrics']['exit_status_time']==0 and x['time_metrics']['swaps_time_counter']==0,'TIME_STDERR')
 return x

def assembled():
 receipts={(r,b,a):verify_run(r,b,a) for r,b,a in SCHEDULE}
 summary={}
 for beam in BEAMS:
  ratios=[];stock_qps=[];fast_qps=[];pairs=[]
  for r in (1,2,3):
   s=receipts[r,beam,'stock']['metrics'];f=receipts[r,beam,'fast']['metrics']
   ratio=f['qps']/s['qps'];must(math.isfinite(ratio) and ratio>0,'BAD_RATIO')
   ratios.append(ratio);stock_qps.append(s['qps']);fast_qps.append(f['qps'])
   pairs.append({'round':r,'stock_qps':s['qps'],'fast_qps':f['qps'],'ratio_fast_to_stock':ratio,
                 'delta_pct':100*(ratio-1),'stock_recall':s['recall_at10'],'fast_recall':f['recall_at10'],
                 'stock_visited':s['avg_visited'],'fast_visited':f['avg_visited']})
  def med(values):return sorted(values)[len(values)//2]
  summary[str(beam)]={'rounds':3,'pairs':pairs,'median_paired_ratio':med(ratios),
      'geomean_paired_ratio':math.exp(sum(map(math.log,ratios))/len(ratios)),
      'median_stock_qps':med(stock_qps),'median_fast_qps':med(fast_qps),
      'stock_qps_range':[min(stock_qps),max(stock_qps)],'fast_qps_range':[min(fast_qps),max(fast_qps)],
      'median_paired_delta_pct':100*(med(ratios)-1)}
 return {'status':TAG+'_PAIRED_PILOT_NATIVE_PASS','preflight_sha256':check_pre(),'plan':plan(),
  'run_receipt_sha256':{ident(r,b,a):sha(OUT/'runs'/ident(r,b,a)/'receipt.json') for r,b,a in SCHEDULE},
  'threshold_matched_qps_summary':summary,
  'caveats':['Three paired rounds are an exploratory pilot, not a formal equivalence/noninferiority statistical test.',
   'Recall satisfies thresholds for both arms but exact Recall is not matched.',
   'QPS timing uses one CPU, 100K queries, separate native evaluator processes; 1/QPS is not p95/p99 latency.',
   'Legacy avg_cmps invalid; do not infer search work from it. No graph build/rebuild.']}

def run():
 absent(OUT);check_pre();resources();references();calibration()
 OUT.mkdir(exist_ok=False);(OUT/'runs').mkdir(exist_ok=False)
 save(OUT/'run_request.json',{'plan':plan(),'preflight_sha256':check_pre(),'timestamp':time.time()})
 for r,b,a in SCHEDULE:
  resources()
  p=subprocess.run(scope_cmd('inscope-'+str(r)+'-'+str(b)+'-'+a));must(p.returncode==0,'SCOPE_EXIT_'+ident(r,b,a))
 references();calibration();report=assembled();save(OUT/'paired_qps_summary.json',report)
 print(TAG+'_SUMMARY',sha(OUT/'paired_qps_summary.json'),flush=True)

def audit():
 references();calibration();x=assembled()
 must(x==js(OUT/'paired_qps_summary.json'),'SUMMARY_DRIFT')
 print(TAG+'_FINAL_READONLY_AUDIT_PASS',sha(OUT/'paired_qps_summary.json'))
 for beam,info in x['threshold_matched_qps_summary'].items():
  print('BEAM',beam,'STOCK_MEDIAN_QPS',info['median_stock_qps'],'FAST_MEDIAN_QPS',info['median_fast_qps'],
        'PAIRED_MEDIAN_RATIO',info['median_paired_ratio'],'PAIRED_GMEAN_RATIO',info['geomean_paired_ratio'])

def selftest():
 assert len(SCHEDULE)==12 and set(SCHEDULE)=={(r,b,a) for r in (1,2,3) for b in BEAMS for a in ARMS}
 for b in BEAMS:
  o=[tuple(a for r0,b0,a in SCHEDULE if r0==r and b0==b) for r in (1,2,3)]
  assert len(set(o))==2 and all(len(v)==2 and set(v)==set(ARMS) for v in o)
 for beam in BEAMS:
  ok=f'R72_RECALL_INPUT_PASS graph_nodes=10000000 queries=100000 gt_k=100\nR72_RECALL_ROW beam={beam} recall=0.999 qps=123.0 avg_cmps=4294960000 avg_visited=400\nR72_RECALL_EVAL_PASS\n'
  m=parse_one(ok,beam);assert m['recall_at10']==.999 and m['avg_cmps_legacy_untrusted'] is None
  for bad in (ok.replace('qps=123.0','qps=nan'),ok.replace('recall=0.999','recall=1.001'),ok.replace(END,''),ok.replace('qps=123.0','qps=0'),ok+ok.splitlines()[1]+'\n'):
   try:parse_one(bad,beam)
   except RuntimeError:pass
   else:raise AssertionError('Parser accepted invalid one-beam stdout')
 assert all(re.fullmatch('[0-9a-f]{64}',h) for h in SHAS.values())
 assert all('-graph_outfile' not in command(b,a) for b in BEAMS for a in ARMS)
 assert all(command(b,'stock')[4]!=command(b,'fast')[4] for b in BEAMS)
 print(TAG+'_SELFTEST_PASS_SCHEDULE_PAIRING_PARSE_RECALL_SHA_NO_ANN_BUILD')

SCRIPT_SHA=sha(Path(__file__).resolve())
if __name__=='__main__':
 try:
  must(len(sys.argv)==2,'USAGE')
  arg=sys.argv[1]
  if arg=='scope-check':scope();print(TAG+'_CGROUP_24G_NOSWAP_PASS')
  elif arg.startswith('inscope-'):
   rr,bb,aa=arg.split('-')[1:]
   scoped_run(int(rr),int(bb),aa)
  else:
   modes={'selftest':selftest,'preflight':preflight,'run':run,'audit':audit}
   must(arg in modes,'MODE');modes[arg]()
 except BaseException as e:
  print(TAG+'_ERROR',repr(e),file=sys.stderr);sys.exit(2)
