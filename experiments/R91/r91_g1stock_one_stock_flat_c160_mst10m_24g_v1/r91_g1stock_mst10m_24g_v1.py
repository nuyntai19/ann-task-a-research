#!/usr/bin/env python3
"""One isolated historical Stock OFF 10M build; no Search, no historical writes."""
import array, hashlib, json, math, os, re, shlex, shutil, signal, struct, subprocess, sys, tempfile, time
from pathlib import Path
H=Path.home(); ROOT=H/'ann-task-a'; R=ROOT/'experiments/R91'; ORIG=ROOT/'experiments/R90/r90_p0a_v13_historical_highway_6bc2_controlled_v1'
PREF=R/'r91_g1stock_native_preflight_v1'; OUT=R/'r91_g1stock_one_stock_flat_c160_mst10m_24g_v1'
G1=R/'r91_g1_one_fastv2_flat_c160_mst10m_24g_v1'; DATA=ROOT/'data/MSTuring_10M_v1'
BINREL='algorithms/PipNN/neighbors-pipnn_FLOAT_T_EUCLIDEAN'; STOCK=ORIG/'build/stock_off'/BINREL; FAST=ORIG/'build/fast_off'/BINREL
BASE=DATA/'base.10M.fbin'; QUERY=DATA/'query.public.100K.fbin'; GT=DATA/'groundtruth.public.100K.ibin'; FASTGRAPH=G1/'graphs/MSTuring10M_fast_off_C160_K1024_N2.graph'
FASTTIME=G1/'logs/MSTuring10M_fast_off_C160_K1024_N2.time'; FASTSTD=G1/'logs/MSTuring10M_fast_off_C160_K1024_N2.stdout'
GRAPH=OUT/'graphs/MSTuring10M_stock_off_C160_K1024_N2.graph'; LOG=OUT/'logs'; CAP=24*1024**3; GIB=1024**3; CPUS=(0,2,4,6); N=10_000_000; DEG=64
TAG='R91_G1STOCK_MST10M_24G_V1'; FLAGS=['-num_clusters','2','-cluster_size','1024','-table_size','160','-top_level_leaders','100','-fanout_scheme','10,3,1','-mst_deg','2','-prune','1','-prune_all','1','-prune_degree','64','-hash_bits','12','-alpha','1.1','-k','0']
PIN={
 'inventory':(R/'r91_g1stock_readonly_preflight_v1/inventory.json','7a353e47ba684048f66d8b54c26a29c9fe04afbddbef185972329adf152530f8'),
 'manifest':(ORIG/'compile_manifest.json','48531781fbcd89f1e7256f2fa8a85d26f28098dc21447f9891988d6312400675'),
 'stock':(STOCK,'13bef65c01d4638959b16b74fc2b8b6130b433ebc09fff8f436c8b1503e688c9'),
 'fast':(FAST,'fcfb16d0ca2b498f94db8383dfc311c2e7ba88cb3036281accd5f30c6d876793'),
 'g1':(G1/'r91_g1_single10m_result.json','bd46f8327e634e05ebdf3975c602d3c069df749be8dc3a6e140f286a606e3835'),
 'graph':(FASTGRAPH,'4055dedc2ccb3b6406fed45ed28de2ec57c46fe2b085b5046ae13cd943702429'),
 'base':(BASE,'e7756f6b54a07e8af171c7644ce2e1be6d7053ee2a2c30c4b02f99e85984b700'),
 'query':(QUERY,'48d087a17bec15a5ec9ea526fe9bd14ac31bbbb5cd200817b341adbb77695644'),
 'gt':(GT,'77b558bd3b77e4cc1149384996b953b040e412477eb0df9889718fc13e17aff2'),
 'g1bc':(R/'r91_g1bc_fast10m_highbeam_search_v1/quality_screen_summary.json','ad3be04bbdc83b04d5d71068a44dc74b37b098743a06bdc5b4b2e7260d278a07'),
 'old_runner':(H/'Downloads/r91_g07_g1_mst10m_hardcap_v1.py','b216af7d3b49994f3ad9704d7354ebe3fac5dec57ec986c41deb02644d1957ed'),
 'old_shell':(H/'Downloads/R91_G1_ONE_FASTV2_MST10M_24G_NOSWAP_v1_Ubuntu.sh','15f2fb92f6e0a72de75ee34e8cf8c91790903a1e1e615e595c300127e23b2e2d'),
}
def must(b,msg):
    if not b: raise RuntimeError(TAG+'_HOLD_'+msg)
def sha(p):
    must(p.is_file() and not p.is_symlink(),'NOT_REGULAR_'+p.name)
    h=hashlib.sha256()
    with p.open('rb') as f:
        for block in iter(lambda:f.read(8*1024**2),b''): h.update(block)
    return h.hexdigest()
def js(p): return json.loads(p.read_text())
def save(p,x):
    with p.open('x') as f: json.dump(x,f,indent=2,sort_keys=True); f.write('\n')
def absent(p): must(not p.exists() and not p.is_symlink(),'OUTPUT_EXISTS_'+p.name)
def mem(): return int(re.search(r'^MemAvailable:\s+(\d+)',Path('/proc/meminfo').read_text(),re.M)[1])*1024
def free(): return shutil.disk_usage(R).free
def resources():
    must(mem()>=26*GIB,'MEMAVAILABLE_LT26G')
    must(free()>=12*GIB,'DISK_FREE_LT12G')
    must(set(CPUS)<=os.sched_getaffinity(0),'CPU_AFFINITY')
    topo=[]
    for n in CPUS:
        p=Path(f'/sys/devices/system/cpu/cpu{n}/topology')
        topo.append((int((p/'physical_package_id').read_text()),int((p/'core_id').read_text())))
    must(len(set(topo))==4,'CPU_NOT_FOUR_DISTINCT_PHYSICAL_CORES')
    return {'MemAvailable_bytes':mem(),'disk_free_bytes':free(),'cpu_topology':topo}
def cgpath():
    rows=[i[3:] for i in Path('/proc/self/cgroup').read_text().splitlines() if i.startswith('0::')]; must(len(rows)==1,'NO_CGROUP_V2')
    cg=Path('/sys/fs/cgroup')/rows[0].lstrip('/')
    must((cg/'memory.max').read_text().strip()==str(CAP),'HARD_CAP_NOT_24G')
    must((cg/'memory.swap.max').read_text().strip()=='0','SWAP_CAP_NOT_ZERO')
    for par in cg.parents:
        if par==Path('/sys/fs/cgroup'): break
        f=par/'memory.max'
        if f.exists():
            v=f.read_text().strip(); must(v=='max' or int(v)>=CAP,'ANCESTOR_CAP_LT24G')
    must(num(cg,'memory.swap.current')==0,'NONZERO_SWAP')
    return cg
def num(cg,k): return int((cg/k).read_text())
def kv(p): return {k:int(v) for k,v in (line.split() for line in p.read_text().splitlines())}
def events(cg): return kv(cg/'memory.events')
def delta(a,b): return {k:b.get(k,0)-a.get(k,0) for k in set(a)|set(b)}
def command(binary,graph): return ['taskset','-c','0,2,4,6',str(binary),'-base_path',str(BASE),'-graph_outfile',str(graph),*FLAGS]
def gnu_cmd(p):
    m=re.search(r'^\s*Command being timed: "(.*)"\s*$',p.read_text(),re.M); must(m is not None,'FAST_TIME_CMD_MISSING'); return shlex.split(m[1])
def headers():
    for p,n,d,size in [(BASE,N,100,4000000008),(QUERY,100000,100,40000008),(GT,100000,100,80000008),(FASTGRAPH,N,DEG,2202769196)]:
        with p.open('rb') as f: must(f.read(8)==struct.pack('<II',n,d),'HEADER_'+p.name)
        must(p.stat().st_size==size,'SIZE_'+p.name)
def references():
    for k,(p,h) in PIN.items(): must(sha(p)==h,'SHA_'+k)
    cm=js(PIN['manifest'][0]); must(cm['binaries']['stock_off']==PIN['stock'][1] and cm['binaries']['fast_off']==PIN['fast'][1],'MANIFEST_ELFS')
    must(os.access(STOCK,os.X_OK),'STOCK_NOT_EXECUTABLE')
    g=js(PIN['g1'][0]); must(g['status']=='NATIVE_1_OF_1_10M_BUILD_AND_FULL_GRAPH_STRUCTURE_PASS_NO_SWAP' and g['graph_quality']['sha256']==PIN['graph'][1],'G1_STATUS')
    must(sha(FASTTIME)==g['timefile_sha256'] and sha(FASTSTD)==g['stdout_sha256'],'G1_RAW_LOG_SHA')
    must(gnu_cmd(FASTTIME)==command(FAST,FASTGRAPH),'G1_ACTUAL_CLI_MISMATCH')
    q=js(PIN['g1bc'][0]); must(q['native_exit_code']==0 and q['graph_sha256']==PIN['graph'][1] and q['metrics']['1792']['meets_0_998'] is True,'G1BC_GATE')
    headers()
    return {k:h for k,(_,h) in PIN.items()}
def scope_args(mode):
    return ['systemd-run','--user','--scope','--collect','--expand-environment=no','-p','MemoryAccounting=yes','-p','MemoryMax=24G','-p','MemorySwapMax=0',sys.executable,str(Path(__file__).resolve()),mode]
def preflight():
    absent(PREF); absent(OUT); resources(); p=references(); res=resources()
    x=subprocess.run(scope_args('scope-check')); must(x.returncode==0,'NATIVE_SCOPE_CHECK')
    PREF.mkdir(exist_ok=False)
    save(PREF/'preflight.json',{'status':TAG+'_PREFLIGHT_PASS_NO_BUILD','pins':p,'resources':res,'cmd':command(STOCK,GRAPH),'env':{'PARLAY_NUM_THREADS':'4','OMP_NUM_THREADS':'4','LC_ALL':'C'},'script_sha':sha(Path(__file__).resolve()),'hardcap_bytes':CAP,'swapmax_bytes':0,'timestamp':time.time()})
    print(TAG+'_PREFLIGHT_PASS_NO_BUILD',sha(PREF/'preflight.json'),flush=True)
def full_graph(p,n=N,cap=DEG):
    """Stream exact n degree words and exact adjacency. No graph-sized adjacency allocation."""
    h=hashlib.sha256(); bad=dup=loop=0; arcs=0; maxdeg=0
    must(p.is_file() and not p.is_symlink(),'GRAPH_MISSING')
    with p.open('rb') as f:
        b=f.read(8); h.update(b); must(b==struct.pack('<II',n,cap),'STOCK_GRAPH_HEADER')
        b=f.read(4*n); must(len(b)==4*n,'DEGREE_LENGTH'); h.update(b)
        degrees=array.array('I'); must(degrees.itemsize==4,'U32_ARRAY'); degrees.frombytes(b); del b
        if sys.byteorder!='little': degrees.byteswap()
        maxdeg=max(degrees,default=0); must(maxdeg<=cap,'DEGREE_CAP'); arcs=sum(degrees)
        must(p.stat().st_size==8+4*n+4*arcs,'GRAPH_SIZE_ARCS')
        fmts=[struct.Struct('<'+'I'*d) for d in range(cap+1)]
        for start in range(0,n,16384):
            ds=degrees[start:start+16384]; count=sum(ds); buf=f.read(4*count); must(len(buf)==4*count,'ADJ_TRUNCATED'); h.update(buf); off=0
            for i,d in enumerate(ds,start):
                row=fmts[d].unpack_from(buf,off); off+=4*d
                if row:
                    bad+=sum(1 for v in row if v>=n) if max(row)>=n else 0
                    loop+=int(i in row); dup+=int(len(set(row))!=d)
        must(f.read(1)==b'','GRAPH_TRAILING_BYTES')
    return dict(nodes=n,degree_cap=cap,max_degree=maxdeg,arcs=arcs,bytes=p.stat().st_size,sha256=h.hexdigest(),full_graph_invalid_id=bad,full_graph_selfloops=loop,full_graph_duplicate_neighbor_rows=dup,full_audit_all_vertices=True)
def time_metrics(p):
    raw=p.read_text(); ret={}
    for key,label in [('max_RSS_KiB','Maximum resident set size (kbytes)'),('major_page_faults','Major (requiring I/O) page faults'),('minor_page_faults','Minor (reclaiming a frame) page faults'),('swaps_time_counter','Swaps'),('exit_status_time','Exit status')]:
        m=re.search(r'^\s*'+re.escape(label)+r': (\d+)\s*$',raw,re.M); must(m is not None,'GNU_TIME_'+key); ret[key]=int(m[1])
    m=re.search(r'^\s*Elapsed \(wall clock\) time \(h:mm:ss or m:ss\): ([0-9:.]+)',raw,re.M); must(m is not None,'GNU_TIME_WALL')
    ret['wall_seconds']=sum(float(v)*60**i for i,v in enumerate(reversed(m[1].split(':')))); return ret
def stage_metrics(p):
    t=p.read_text(errors='replace'); must('R70_RESERVOIR_VARIANT=STOCK_FLAT_C160' in t and 'R71_SELECTION_VARIANT=STOCK_HIGHWAY' in t,'STOCK_NATIVE_VARIANT_MARKERS')
    out={}
    for key,label,expected in [('buckets','buckets time',2),('leaf','build leaf time',2),('prune','Final prune time',1)]:
        nums=[float(v) for v in re.findall(re.escape(label)+r'\s*[:=]\s*([0-9]+(?:\.[0-9]+)?)',t,re.I)]
        out[key+'_per_pass_seconds']=nums; out[key+'_total_seconds']=sum(nums) if len(nums)==expected else None; out[key+'_observed_count']=len(nums); out[key+'_expected_count']=expected
    out['bucket_counts']=[int(v) for v in re.findall(r'Total buckets:\s*(\d+)',t)]
    out['clustering_comparisons_cumulative']=[int(v) for v in re.findall(r'# of comparisons during clustering:\s*(\d+)',t)]
    out['average_table_size_printed']=[int(v) for v in re.findall(r'Average table size:\s*(\d+)',t)]
    return out
def stop(p):
    if p.poll() is None:
        os.killpg(p.pid,signal.SIGTERM)
        try:p.wait(timeout=10)
        except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL);p.wait()
def inscope():
    cg=cgpath(); request=js(OUT/'RUN_REQUEST.json'); must(request['stock_only'] is True and request['preflight_sha256']==sha(PREF/'preflight.json'),'REQUEST_MISMATCH'); save(OUT/'scope.json',{'cgroup_path':str(cg),'cap':CAP,'swapmax':0}); absent(LOG); absent(OUT/'graphs'); absent(OUT/'stock_result.json')
    pf=js(PREF/'preflight.json'); must(pf['status']==TAG+'_PREFLIGHT_PASS_NO_BUILD' and pf['pins']==references() and pf['cmd']==command(STOCK,GRAPH) and pf['script_sha']==sha(Path(__file__).resolve()),'PRECHECK_DRIFT')
    res=resources(); env={**os.environ,**pf['env']}; LOG.mkdir(); (OUT/'graphs').mkdir(); before=events(cg); scope_swap_before=num(cg,'memory.swap.current')
    build_cmd=['/usr/bin/time','-v','-o',str(LOG/'native.time'),*command(STOCK,GRAPH)]
    result={'status':TAG+'_HOLD_PRESERVE_ARTIFACTS','error':None,'native_exit_code':None,'graph_quality':None,'time_metrics':None,'stage_metrics':None,'command':build_cmd,'resources_before':res,'pins':pf['pins'],'preflight_sha256':sha(PREF/'preflight.json'),'cgroup_path':str(cg),'no_search':True,'sample_count':0,'peak_swap_sampled_bytes':0,'min_host_memavailable_bytes':mem(),'min_disk_free_bytes':free()}
    p=None; pressure=0; start=time.monotonic()
    try:
        with (LOG/'native.stdout').open('xb') as so,(LOG/'native.stderr').open('xb') as se,(LOG/'memory_monitor.tsv').open('x',buffering=1) as mon:
            mon.write('epoch\tmemory_current\tmemory_peak\tswap_current\tanon\tfile\tevents_max\toom\toom_kill\thost_memavailable_bytes\tdisk_free_bytes\n')
            p=subprocess.Popen(build_cmd,stdout=so,stderr=se,env=env,start_new_session=True,cwd=OUT)
            while True:
                ev=events(cg); st=kv(cg/'memory.stat'); ma=mem(); df=free(); sw=num(cg,'memory.swap.current'); peak=num(cg,'memory.peak')
                mon.write('\t'.join(map(str,[time.time(),num(cg,'memory.current'),peak,sw,st.get('anon',-1),st.get('file',-1),ev.get('max',0),ev.get('oom',0),ev.get('oom_kill',0),ma,df]))+'\n')
                result['sample_count']+=1; result['min_host_memavailable_bytes']=min(result['min_host_memavailable_bytes'],ma); result['min_disk_free_bytes']=min(result['min_disk_free_bytes'],df); result['peak_swap_sampled_bytes']=max(result['peak_swap_sampled_bytes'],sw)
                if p.poll() is not None: break
                pressure=pressure+1 if ma<2*GIB else 0
                if pressure>=3 or df<8*GIB or sw or ev.get('oom',0)>before.get('oom',0) or time.monotonic()-start>3600:
                    stop(p); raise RuntimeError('RESOURCE_OR_TIMEOUT_ABORT')
                time.sleep(1)
        result['native_exit_code']=p.returncode; result['builder_external_seconds']=time.monotonic()-start; result['builder_cgroup_peak_bytes']=num(cg,'memory.peak'); result['builder_cgroup_events_delta']=delta(before,events(cg))
        must(p.returncode==0,'BUILDER_EXIT_'+str(p.returncode)); must(gnu_cmd(LOG/'native.time')==command(STOCK,GRAPH),'STOCK_ACTUAL_CMD')
        result['time_metrics']=time_metrics(LOG/'native.time'); must(result['time_metrics']['exit_status_time']==0 and result['time_metrics']['swaps_time_counter']==0,'GNU_TIME_STATUS_SWAP')
        result['stage_metrics']=stage_metrics(LOG/'native.stdout')
        print(TAG+'_BUILD_EXIT0_START_FULL_GRAPH_AUDIT',flush=True)
        result['graph_quality']=full_graph(GRAPH); g=result['graph_quality']; must(not any(g[k] for k in ('full_graph_invalid_id','full_graph_selfloops','full_graph_duplicate_neighbor_rows')),'GRAPH_STRUCTURAL_ERRORS')
        must(sha(FASTGRAPH)==PIN['graph'][1] and sha(STOCK)==PIN['stock'][1],'FROZEN_REFERENCE_CHANGED')
        result['status']=TAG+'_NATIVE_BUILD_FULL_GRAPH_PASS'
    except BaseException as e:
        if p is not None: stop(p); result['native_exit_code']=p.returncode
        result['error']=repr(e)
    finally:
        result['cgroup_events_delta']=delta(before,events(cg)); result['cgroup_peak_bytes']=num(cg,'memory.peak'); result['cgroup_swap_before']=scope_swap_before; result['cgroup_swap_after']=num(cg,'memory.swap.current')
        if any(result['cgroup_events_delta'].get(k,0) for k in ('oom','oom_kill','oom_group_kill')) or result['cgroup_swap_after'] or result['peak_swap_sampled_bytes']:
            result['status']=TAG+'_HOLD_PRESERVE_ARTIFACTS'
        result['log_shas']={f.name:sha(f) for f in LOG.iterdir() if f.is_file()}; save(OUT/'stock_result.json',result)
        print(TAG+'_RESULT',result['status'],'sha256',sha(OUT/'stock_result.json'),flush=True)
    must(result['status']==TAG+'_NATIVE_BUILD_FULL_GRAPH_PASS','NATIVE_FAILURE_PRESERVE')
def run():
    absent(OUT); pf=js(PREF/'preflight.json'); must(pf['status']==TAG+'_PREFLIGHT_PASS_NO_BUILD' and pf['script_sha']==sha(Path(__file__).resolve()),'PREFLIGHT_NOT_VALID'); resources()
    OUT.mkdir(exist_ok=False); save(OUT/'RUN_REQUEST.json',{'preflight_sha256':sha(PREF/'preflight.json'),'time':time.time(),'stock_only':True})
    p=subprocess.Popen(scope_args('inscope')); samples=0
    with (OUT/'outside_scope_monitor.tsv').open('x',buffering=1) as f:
        f.write('epoch\tmemory_current\tmemory_peak\tswap_current\tmax_events\toom\toom_kill\thost_memavailable_bytes\tdisk_free_bytes\n')
        try:
            while p.poll() is None:
                try:
                    cg=Path(js(OUT/'scope.json')['cgroup_path']); must(cg.is_relative_to('/sys/fs/cgroup'),'OUTSIDE_SCOPE_PATH')
                    ev=events(cg); vals=[num(cg,'memory.current'),num(cg,'memory.peak'),num(cg,'memory.swap.current'),ev.get('max',0),ev.get('oom',0),ev.get('oom_kill',0)]
                    f.write('\t'.join(map(str,[time.time(),*vals,mem(),free()]))+'\n'); samples+=1
                except (OSError,KeyError,ValueError): pass
                time.sleep(1)
        except KeyboardInterrupt:
            print(TAG+'_INTERRUPTED_SCOPE_MAY_STILL_BE_RUNNING_DO_NOT_RESTART',flush=True); raise
    save(OUT/'outside_scope_receipt.json',{'scope_exit_code':p.returncode,'samples':samples,'monitor_sha256':sha(OUT/'outside_scope_monitor.tsv')})
    print(TAG+'_SCOPE_EXIT_CODE='+str(p.returncode),flush=True); must(p.returncode==0,'SCOPE_FAILED_PRESERVE')
def selftest():
    with tempfile.TemporaryDirectory() as td:
        p=Path(td)/'g'; p.write_bytes(struct.pack('<IIIIIIII',3,2,1,2,0,1,0,2)); a=full_graph(p,3,2); assert a['arcs']==3 and a['full_graph_selfloops']==a['full_graph_duplicate_neighbor_rows']==a['full_graph_invalid_id']==0
        p.write_bytes(struct.pack('<IIIIIIII',3,2,1,2,0,0,2,2)); a=full_graph(p,3,2); assert a['full_graph_selfloops']==1 and a['full_graph_duplicate_neighbor_rows']==1
        p.write_bytes(p.read_bytes()+b'x')
        try:full_graph(p,3,2)
        except RuntimeError:pass
        else:raise AssertionError('trailing bytes accepted')
        s=Path(td)/'stdout'; s.write_text('R70_RESERVOIR_VARIANT=STOCK_FLAT_C160\nR71_SELECTION_VARIANT=STOCK_HIGHWAY\nbuckets time: 1.0\nbuckets time: 2.0\nbuild leaf time: 3.0\nbuild leaf time: 4.0\nFinal prune time: 5.0\n'); assert stage_metrics(s)['leaf_total_seconds']==7
    print(TAG+'_SELFTEST_PASS_GRAPH_BOUNDARY_MARKERS_NO_BUILD')
if __name__=='__main__':
    try:
        mode=sys.argv[1]; {'selftest':selftest,'preflight':preflight,'run':run,'inscope':inscope,'scope-check':lambda: print(TAG+'_NATIVE_CGROUP24G_NO_SWAP_PASS',cgpath(),flush=True)}[mode]()
    except Exception as e: print(str(e),file=sys.stderr,flush=True);sys.exit(2)
