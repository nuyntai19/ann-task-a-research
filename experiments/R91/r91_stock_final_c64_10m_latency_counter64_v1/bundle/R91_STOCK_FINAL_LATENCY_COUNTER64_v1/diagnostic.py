#!/usr/bin/env python3
import argparse, json, math, re, sys, time, statistics
from pathlib import Path
import prepare as prep
import stock_final as sf
v=sf.v; p=sf.p; need=sf.need; sha=sf.sha; pin=sf.pin; load=sf.load; atom=sf.atom; clean=sf.clean
OUT=prep.OUT; H=prep.H; A=sf.ARMS; BEAMS=(544,1728); N=100000
TAG='R91_STOCK_FINAL_LATENCY_COUNTER64_V1'; CLEAN=sf.OUT; TOPO=v.R91/'r91_stock_final_c64_10m_topology_v1'
CLEAN_SHA='1c69fd1abcbf8720961eeefb5cbc25539a23d8d81d9405b04bbf97ca0a49eecd'; TOPO_SHA='d044a031d815315747c4a4cf739ab44b6bbe9f3911943cfb747f98bf5cdcf1ef'
FILES=sf.FILES
LIMITS=['One fixed graph per arm, Stock first, one invocation per arm','Fixed beam 544 and 1728, both arms meet Recall floors, not exact matched Recall','Instrumented per-query service time includes beam traversal and top-k result mapping; excludes load, ground-truth validation and output serialization','Counter64 traversal excludes 10 full precision top-k recomputations; traversal+10 reported separately','Diagnostic latency and diagnostic QPS not substituted for clean QPS; not a client/server latency']
def absent(f):clean(f);need(not f.exists(),'OUTPUT_EXISTS '+str(f))
def bulk():
 sf.bulk();prep.inputs();pin(CLEAN/'summary.json',CLEAN_SHA,'CLEAN_SUM');pin(CLEAN/'preflight.json','7c8ae670b6fc0d13d3277ce65ae009f3774e6a26111e35c38ea3c636dc936055','CLEAN_PRE');pin(TOPO/'summary.json',TOPO_SHA,'TOPO_SUM');pin(TOPO/'preflight.json','2212e0862b43302fda180cc0a38b18116c774c788c31b26e291dc198c9b1e10f','TOPO_PRE');need(load(CLEAN/'preflight.json')['graph_sha256']==sf.PINS,'CLEAN_GRAPH');need(load(TOPO/'preflight.json')['graph_sha256']==sf.PINS,'TOPO_GRAPH')
def plan():return dict(status='PREFLIGHT_PASS_COMPILE_ONLY_NO_SEARCH',script_sha256=sha(Path(__file__)),prepare_sha256=sha(H/'prepare.py'),manifest_sha256=sha(H/'SHA256SUMS.txt'),clean_summary_sha256=CLEAN_SHA,topology_summary_sha256=TOPO_SHA,graph_sha256=sf.PINS,data_sha256={str(f):h for f,h in v.DATA_PINS.items()},source_pins={str(f):h for f,h in prep.PINS.items()},instrumented_files=prep.snapshot(),order=list(A),beams=list(BEAMS),queries=N,cpu='0',memory_max_bytes=v.MEMORY_MAX,swap_max_bytes=0,no_build=True,limits=LIMITS)
def checkpre(h):pin(OUT/'preflight.json',h,'PREFLIGHT');need(load(OUT/'preflight.json')==plan(),'PLAN_DRIFT')
def preflight():
 scope=v.cgroup(True);v.environment_gate();absent(OUT);bulk();OUT.mkdir();prep.prepare();_,end=v.cgroup(True);need(v.evparse(scope[1]['memory.events'])==v.evparse(end['memory.events']) and int(end['memory.peak'])<v.MEMORY_MAX,'PREFLIGHT_RESOURCE');atom(OUT/'preflight.json',plan());print(TAG+'_PREFLIGHT_PASS_COMPILE_ONLY_NO_SEARCH',sha(OUT/'preflight.json'),flush=True)
def stat(xs):
 n=len(xs);need(n>0,'EMPTY');ys=sorted(xs);return dict(min=ys[0],max=ys[-1],mean=sum(xs)/n,p50=ys[(50*n+99)//100-1],p95=ys[(95*n+99)//100-1],p99=ys[(99*n+99)//100-1],total=sum(xs))
def parse(text,anchor,n=N):
 need(text.count('R85_A1C_DYNAMIC_BEAMS count=2')==1 and text.count(f'R72_RECALL_INPUT_PASS graph_nodes=10000000 queries={n} gt_k=100')==1 and text.count('R72_RECALL_EVAL_PASS')==1,'MARKERS')
 raw={b:[] for b in BEAMS};rows=[]
 for line in text.splitlines():
  if line.startswith('R91_DIAG_QUERY '):
   z=line.split();need(len(z)==6,'QUERY_FIELDS');b,i,ns,cm,vis=map(int,z[1:]);need(b in raw and i==len(raw[b]) and i<n and 0<ns<10**12 and 0<vis<=10000000 and 0<cm<=640000001 and cm>=vis,'QUERY_VALUE');need(len(rows)<len(BEAMS) and b==BEAMS[len(rows)],'QUERY_ORDER');raw[b].append((ns,cm,vis))
  elif line.startswith('R72_RECALL_ROW '):
   z=re.fullmatch(r'R72_RECALL_ROW beam=(\d+) recall=([0-9.]+) qps=([0-9.]+) avg_cmps=([0-9.]+) avg_visited=([0-9.]+)',line);need(z is not None,'ROW_FORMAT');b=int(z[1]);need(len(rows)<len(BEAMS) and b==BEAMS[len(rows)] and len(raw[b])==n,'ROW_ORDER');rec,qps,cm,vis=map(float,z.groups()[1:]);need(all(math.isfinite(y) for y in (rec,qps,cm,vis)) and qps>0,'FINITE');base=anchor[b];need(rec==base['recall_at10'] and vis==base['avg_visited'],'CLEAN_RECALL_VISITED_PARITY');lat,dist,visited=map(list,zip(*raw[b]));ds=stat(dist);vs=stat(visited);need(cm==ds['total']//n and vis==vs['total']//n,'COUNTER64_PARITY');rows.append(dict(beam=b,recall_at10=rec,diagnostic_qps_not_clean=qps,avg_visited_legacy=vis,n_queries=n,latency_ns=stat(lat),traversal_cmps=ds,search_cmps_including_top10_recompute=stat([x+10 for x in dist]),visited=vs))
 need(len(rows)==2 and all(len(raw[b])==n for b in BEAMS),'COMPLETE');return rows
def anchors(a):return {r['beam']:r for s in load(CLEAN/'summary.json')['slots'] if s['arm']==a for r in s['metrics']}
def path(a):return OUT/'runs'/a
def command(a):return ['/usr/bin/time','-v','-o',str(path(a)/'native.time'),'/usr/bin/taskset','-c','0',str(prep.BIN),str(sf.GRAPHS[a]),str(v.BASE),str(v.QUERY),str(v.GT),','.join(map(str,BEAMS))]
def base(a,h):return dict(arm=a,preflight_sha256=h,graph_sha256=sf.PINS[a],evaluator_sha256=sha(prep.BIN),clean_summary_sha256=CLEAN_SHA,topology_summary_sha256=TOPO_SHA,beams=list(BEAMS))
def verify(a,h):
 d=path(a);f=d/'receipt.json';r=load(f);need(all(r[k]==z for k,z in base(a,h).items()) and r['status']=='DIAGNOSTIC_SLOT_PASS' and r['error'] is None and p.good(r['resource']) and p.gnu_good(r['gnu_time']),'RECEIPT');need(set(r['files_sha256'])==set(FILES),'FILES')
 for k,z in r['files_sha256'].items():pin(d/k,z,'LOG')
 pr=load(d/'preregister.json');need(all(pr[k]==z for k,z in base(a,h).items()) and pr['command']==command(a),'PREREGISTER');need((d/'native.stderr').stat().st_size==0 and v.timeparse(d/'native.time')==r['gnu_time'] and parse((d/'native.stdout').read_text(),anchors(a))==r['metrics'],'NATIVE_DRIFT');pin(sf.GRAPHS[a],sf.PINS[a],'GRAPH');return dict(r,receipt_sha256=sha(f))
def run(a,h):
 scope=v.cgroup(True);v.environment_gate();checkpre(h);bulk();absent(path(a));absent(OUT/'summary.json')
 if a==A[1]:verify(A[0],h)
 else:absent(path(A[1]))
 d=path(a);d.mkdir(parents=True);atom(d/'preregister.json',dict(base(a,h),command=command(a),scope=str(scope[0]),timestamp=time.time()));print(TAG+'_START_'+a,flush=True);m=v.monitor(command(a),d/'native.stdout',d/'native.stderr',scope,max_seconds=10800);err=None;x=None;t=None
 try:
  need(p.good(m),'RESOURCE');need((d/'native.stderr').stat().st_size==0,'STDERR');t=v.timeparse(d/'native.time');need(p.gnu_good(t),'GNU_TIME');x=parse((d/'native.stdout').read_text(),anchors(a));pin(sf.GRAPHS[a],sf.PINS[a],'GRAPH_AFTER');checkpre(h);_,end=v.cgroup(True);orig=v.evparse(scope[1]['memory.events']);ev=v.evparse(end['memory.events']);m.update(events_delta={k:ev[k]-orig.get(k,0) for k in ev},cg_peak_bytes=int(end['memory.peak']),swap_after=int(end['memory.swap.current']));need(p.good(m),'POSTHASH_RESOURCE')
 except Exception as e:err=str(e)
 r=dict(base(a,h),status='DIAGNOSTIC_SLOT_PASS' if err is None else 'DIAGNOSTIC_SLOT_HOLD_PRESERVE_OUTPUT',error=err,metrics=x,resource=m,gnu_time=t,files_sha256={k:sha(d/k) for k in FILES if v.regular(d/k)});atom(d/'receipt.json',r);print(TAG+'_'+r['status']+'_'+a,sha(d/'receipt.json'),flush=True);need(err is None,'SLOT_FAILED')
def audit(h,readonly):
 v.cgroup(True);checkpre(h);bulk();slots=[verify(a,h) for a in A];f=OUT/'summary.json';x=dict(status='TWO_GRAPH_TWO_BEAM_DIAGNOSTIC_AUDIT_PASS',preflight_sha256=h,clean_summary_sha256=CLEAN_SHA,topology_summary_sha256=TOPO_SHA,slots=slots,limits=LIMITS)
 if readonly:need(load(f)==x,'SUMMARY_DRIFT')
 else:atom(f,x)
 print(TAG+('_READONLY_AUDIT_PASS' if readonly else '_AUDIT_PASS'),sha(f),flush=True)
 for s in slots:
  for r in s['metrics']:print(TAG+'_ROW',json.dumps(dict(arm=s['arm'],**r)),flush=True)
def selftest():
 n=3;t='R85_A1C_DYNAMIC_BEAMS count=2\nR72_RECALL_INPUT_PASS graph_nodes=10000000 queries=3 gt_k=100\n';anchors={}
 for b in BEAMS:
  t+=''.join(f'R91_DIAG_QUERY {b} {i} {100+i} {200+i} {10+i}\n' for i in range(n));t+=f'R72_RECALL_ROW beam={b} recall=0.99900000 qps=1000.0 avg_cmps=201 avg_visited=11\n';anchors[b]=dict(recall_at10=.999,avg_visited=11)
 t+='R72_RECALL_EVAL_PASS\n';r=parse(t,anchors,n);need(r[0]['latency_ns']['p99']==102 and r[0]['traversal_cmps']['total']==603 and r[0]['search_cmps_including_top10_recompute']['total']==633,'FIXTURE');need(stat([100000]*100000)['total']==10_000_000_000,'64BIT_FIXTURE')
 for bad in (t.replace('544 1 101','544 0 101'),t.replace('avg_cmps=201','avg_cmps=200'),t.replace('recall=0.99900000','recall=0.99800000')):
  try:parse(bad,anchors,n)
  except Exception:continue
  raise RuntimeError('BAD_FIXTURE_ACCEPTED')
 print(TAG+'_SELFTEST_PASS_COUNTER64_QUANTILES_PARITY_NO_SEARCH')
def main():
 a=argparse.ArgumentParser();a.add_argument('mode',choices=['selftest','preflight','run','audit','readonly']);a.add_argument('--pre');a.add_argument('--arm',choices=A);x=a.parse_args()
 if x.mode=='selftest':selftest();return
 if x.mode=='preflight':preflight();return
 need(x.pre and len(x.pre)==64,'PRE_SHA')
 if x.mode=='run':need(x.arm in A,'ARM');run(x.arm,x.pre)
 else:audit(x.pre,x.mode=='readonly')
if __name__=='__main__':
 try:main()
 except Exception as e:print(TAG+'_HOLD',str(e),file=sys.stderr,flush=True);sys.exit(2)
