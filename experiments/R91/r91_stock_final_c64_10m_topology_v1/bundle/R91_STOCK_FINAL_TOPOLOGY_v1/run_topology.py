import argparse,json,math,os,shutil,subprocess,sys,time
from pathlib import Path
import vendor_calibration_v1 as v
H=Path(__file__).resolve().parent; OUT=v.R91/'r91_stock_final_c64_10m_topology_v1'; CLEAN=v.R91/'r91_stock_final_c64_10m_report_v1'; BIN=OUT/'topology'; A=('STOCK','FINAL_C64'); N=10_000_000
PRE='7c8ae670b6fc0d13d3277ce65ae009f3774e6a26111e35c38ea3c636dc936055'; SUM='1c69fd1abcbf8720961eeefb5cbc25539a23d8d81d9405b04bbf97ca0a49eecd'; TAG='R91_STOCK_FINAL_TOPOLOGY_V1'
PINS={'STOCK':'6beda1aa823a49ca928e6046f411a4b6945d2eb56e125d85a50e30c8ab3deffe','FINAL_C64':'4c54e712c1ba859201a33a8754534c9e3f855664c63db1075a4cf7803dea6e8d'}
G={'STOCK':v.R91/'r91_g1stock_one_stock_flat_c160_mst10m_24g_v1/graphs/MSTuring10M_stock_off_C160_K1024_N2.graph','FINAL_C64':v.PARENT/'runs/C64/graph.bin'}
M={'STOCK':540816693,'FINAL_C64':541002463}; FILES=('native.stdout','native.stderr','native.time','preregister.json')
def need(b,msg):
 if not b: raise RuntimeError(msg)
def clean(p):need(not any(q.is_symlink() for q in (p,*p.parents)),f'SYMLINK {p}')
def absent(p):clean(p);need(not p.exists(),f'OUTPUT_EXISTS {p}')
def pin(p,h):clean(p);need(v.sha(p)==h,f'SHA {p}')
def load(p):clean(p);need(v.regular(p),f'MISSING {p}');return json.loads(p.read_text())
def bulk():
 pin(CLEAN/'preflight.json',PRE);pin(CLEAN/'summary.json',SUM);x=load(CLEAN/'preflight.json');need(x['graph_sha256']==PINS and x['graph_paths']=={a:str(G[a]) for a in A},'GRAPH_LINEAGE');need(load(CLEAN/'summary.json')['status']=='TWO_GRAPH_FIVE_BEAM_CLEAN_SEARCH_AUDIT_PASS','CLEAN_STATUS')
 for a in A:pin(G[a],PINS[a]);need(G[a].stat().st_size==8+4*N+4*M[a],'GRAPH_BYTES')
def plan():return dict(status='PREFLIGHT_PASS_NO_TOPOLOGY_10M',clean_summary_sha256=SUM,clean_preflight_sha256=PRE,graph_sha256=PINS,arcs=M,nodes=N,order=list(A),script_sha256=v.sha(Path(__file__)),source_sha256=v.sha(H/'topology.cpp'),fixture_sha256=v.sha(H/'fixtures.py'),vendor_sha256=v.sha(H/'vendor_calibration_v1.py'),manifest_sha256=v.sha(H/'SHA256SUMS.txt'),analyzer_sha256=v.sha(BIN),compiler_version=(OUT/'compiler.version').read_text().strip(),cpu='0',memory_max_bytes=v.MEMORY_MAX,swap_max_bytes=0,no_ann_build=True,no_search=True)
def checkpre(h):pin(OUT/'preflight.json',h);need(load(OUT/'preflight.json')==plan(),'PLAN_DRIFT')
def good(m):return v.resources_good(m) and {'max','oom','oom_kill','oom_group_kill','high'}.issubset(m['events_delta']) and all(x==0 for x in m['events_delta'].values())
def gn(g):return g['exit_status']=='0' and g['swaps']==0 and g['max_rss_kib']>0 and g['major_faults']>=0 and g['file_system_inputs']>=0
def preflight():
 scope=v.cgroup(True);v.environment_gate();absent(OUT);bulk();need(shutil.which('g++') is not None,'GPP_MISSING');OUT.mkdir(exist_ok=False)
 compiler=shutil.which('g++');(OUT/'compiler.version').write_text(subprocess.check_output([compiler,'--version'],text=True));subprocess.run([compiler,'-std=c++17','-O3','-Wall','-Wextra','-Werror',str(H/'topology.cpp'),'-o',str(BIN)],check=True);subprocess.run([sys.executable,'-B',str(H/'fixtures.py'),str(BIN)],check=True);_,end=v.cgroup(True);need(all(n==v.evparse(scope[1]['memory.events']).get(k,0) for k,n in v.evparse(end['memory.events']).items()) and int(end['memory.peak'])<v.MEMORY_MAX,'PREFLIGHT_RESOURCE');v.atom(OUT/'preflight.json',plan());print(TAG+'_PREFLIGHT_PASS_NO_TOPOLOGY_10M',v.sha(OUT/'preflight.json'),flush=True)
def validate(x,a):
 need(x['status']=='TOPOLOGY_PASS' and x['nodes']==N and x['arcs']==M[a] and x['bytes']==8+4*N+4*M[a] and x['degree_cap']==64,'TOPOLOGY_HEADER')
 for k in ('out_degree','in_degree'):
  d=x[k];h=d['histogram'];need(all(isinstance(i,int) and isinstance(c,int) and i>=0 and c>0 for i,c in h) and [i for i,c in h]==sorted(set(i for i,c in h)),'HIST_ORDER');need(sum(c for i,c in h)==N and sum(i*c for i,c in h)==M[a],'HIST_TOTALS');need(d['min']==h[0][0] and d['max']==h[-1][0] and d['zero']==dict(h).get(0,0) and math.isclose(d['mean'],M[a]/N,rel_tol=1e-14),'HIST_STATS');
  for t in (50,95,99):
   rank=(N*t+99)//100;acc=0
   for i,c in h:
    acc+=c
    if acc>=rank:need(d['p'+str(t)]==i,'QUANTILE');break
 need(x['out_degree']['max']<=64,'DEGREE_CAP')
 for k in ('scc','wcc'):
  z=x[k];need(z['vertices']==N and 1<=z['count']<=N and 1<=z['largest']<=N and 0<=z['singletons']<=z['count'] and z['largest']+z['count']-1<=N,'COMPONENT_STATS');need((z['count']==1)==(z['largest']==N),'CONNECTED_CONSISTENCY')
 need(x['wcc']['count']<=x['scc']['count'] and x['wcc']['largest']>=x['scc']['largest'],'COMPONENT_NESTING');return x
def path(a):return OUT/'runs'/a
def cmd(a):return ['/usr/bin/time','-v','-o',str(path(a)/'native.time'),'/usr/bin/taskset','-c','0',str(BIN),str(G[a]),str(N),str(M[a])]
def base(a,h):return dict(arm=a,preflight_sha256=h,graph_sha256=PINS[a],analyzer_sha256=v.sha(BIN),clean_summary_sha256=SUM)
def verify(a,h):
 d=path(a);r=load(d/'receipt.json');need(all(r[k]==z for k,z in base(a,h).items()) and r['status']=='TOPOLOGY_SLOT_PASS' and r['error'] is None and good(r['resource']) and gn(r['gnu_time']),'RECEIPT');need(set(r['files_sha256'])==set(FILES),'FILE_SET');
 for k,z in r['files_sha256'].items():pin(d/k,z)
 pr=load(d/'preregister.json');need(all(pr[k]==z for k,z in base(a,h).items()) and pr['command']==cmd(a),'PREREGISTER');need((d/'native.stderr').stat().st_size==0 and v.timeparse(d/'native.time')==r['gnu_time'] and validate(load(d/'native.stdout'),a)==r['topology'],'NATIVE_DRIFT');pin(G[a],PINS[a]);return dict(r,receipt_sha256=v.sha(d/'receipt.json'))
def run(a,h):
 scope=v.cgroup(True);v.environment_gate();checkpre(h);bulk();absent(path(a));absent(OUT/'summary.json');
 if a==A[1]:verify(A[0],h)
 else:absent(path(A[1]))
 d=path(a);d.mkdir(parents=True,exist_ok=False);v.atom(d/'preregister.json',dict(base(a,h),command=cmd(a),scope=str(scope[0]),timestamp=time.time()));print(TAG+'_START_'+a,flush=True);m=v.monitor(cmd(a),d/'native.stdout',d/'native.stderr',scope,max_seconds=3600);err=None;x=None;t=None
 try:
  need(good(m),'RESOURCE_OR_EXIT');need((d/'native.stderr').stat().st_size==0,'STDERR');t=v.timeparse(d/'native.time');need(gn(t),'GNU_TIME');x=validate(load(d/'native.stdout'),a);pin(G[a],PINS[a]);checkpre(h);_,end=v.cgroup(True);orig=v.evparse(scope[1]['memory.events']);ev=v.evparse(end['memory.events']);m.update(events_delta={k:ev[k]-orig.get(k,0) for k in ev},cg_peak_bytes=int(end['memory.peak']),swap_after=int(end['memory.swap.current']));need(good(m),'POSTHASH_RESOURCE')
 except Exception as e:err=str(e)
 r=dict(base(a,h),status='TOPOLOGY_SLOT_PASS' if err is None else 'TOPOLOGY_SLOT_HOLD_PRESERVE_OUTPUT',error=err,topology=x,resource=m,gnu_time=t,files_sha256={k:v.sha(d/k) for k in FILES if v.regular(d/k)});v.atom(d/'receipt.json',r);print(TAG+'_'+r['status']+'_'+a,v.sha(d/'receipt.json'),flush=True);need(err is None,'SLOT_FAILED')
def audit(h,readonly):
 v.cgroup(True);checkpre(h);bulk();slots=[verify(a,h) for a in A];x=dict(status='TWO_GRAPH_FULL_TOPOLOGY_AUDIT_PASS',preflight_sha256=h,clean_summary_sha256=SUM,slots=slots,limits=['Directed SCC, undirected WCC; connectivity is not proof of navigability','Degree quantiles nearest-rank over all vertices including zero degree','Read-only frozen graph analysis; one graph per arm']);f=OUT/'summary.json';
 if readonly:need(load(f)==x,'SUMMARY_DRIFT')
 else:v.atom(f,x)
 print(TAG+('_READONLY_AUDIT_PASS' if readonly else '_AUDIT_PASS'),v.sha(f),flush=True)
 for r in slots:
  z=r['topology'];print(TAG+'_ROW',json.dumps({'arm':r['arm'],**{k:v for k,v in z.items() if k not in ('in_degree','out_degree')},**{k:{j:w for j,w in z[k].items() if j!='histogram'} for k in ('in_degree','out_degree')}}),flush=True)
def main():
 p=argparse.ArgumentParser();p.add_argument('mode',choices=['preflight','run','audit','readonly']);p.add_argument('--pre');p.add_argument('--arm',choices=A);a=p.parse_args()
 if a.mode=='preflight':preflight();return
 need(a.pre and len(a.pre)==64,'PRE_REQUIRED')
 if a.mode=='run':need(a.arm in A,'ARM_REQUIRED');run(a.arm,a.pre)
 else:audit(a.pre,a.mode=='readonly')
if __name__=='__main__':
 try:main()
 except Exception as e:print(TAG+'_HOLD',str(e),file=sys.stderr);sys.exit(2)
