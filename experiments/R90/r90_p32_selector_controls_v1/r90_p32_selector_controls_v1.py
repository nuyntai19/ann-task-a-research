#!/usr/bin/env python3
"""R90-P3.2 selector ablation on pinned PiPNN A5 source (SIFT100K, 10K GT).

Constructs an isolated source with ONLY A5 selector choices: degree_low (original),
degree_high, deterministic_random. Maintains Pass1, Pass2 partition, RunLeaf,
HashPrune, RobustPrune. Builds 6 graphs (3 selectors x q=1%,2%), checks the
low-selector graph SHA against the PREVIOUS pinned native A5 graphs, then
uses the same pinned R85 native read-only evaluator for 18-beam sweeps and
3 interleaved repeat evaluations per graph, also re-evaluating Stock N1/N2.

Primary output is an exploratory interpolated-Recall (0.990/0.998) evaluation.
Not an exactly-matched Recall or statistically independent seeds/BUILD study.
No source in P0/R86/H17, historical graph or prior result is ever modified.
"""
from __future__ import annotations
import argparse, hashlib, json, math, os, re, shutil, statistics, struct, subprocess, sys, time
from pathlib import Path

ROOT=Path.home()/'ann-task-a'
R90=ROOT/'experiments/R90'
P0=R90/'r90_p0_stock_a5_compile_gate_v1'
P21=R90/'r90_p2_sift100k_pass2_value_gate1_v1'
P22=R90/'r90_p22_sift100k_10kq_floor_v1'
P23=R90/'r90_p23_sift100k_a5_qgrid_v1'
OUT=R90/'r90_p32_selector_controls_v1'
SOURCE=P0/'a5_source'
BASE=ROOT/'data/sift100k.fbin'
QUERY=ROOT/'data/sift1m_queries.fbin'
GT=ROOT/'experiments/H85/r85_b1_controlled/step8e_gt10k/sift100k_sift1mqueries10k_exact100.ibin'
EVAL=ROOT/'experiments/H85/r85_b1_controlled/step8e_native_eval/r85_b1_100k_graph_recall'
SHA_INPUT={
 'base':'e50ff1bc34bcc6d1c97dd001023c09a666971cde64605cc06671ed8a8ff1ed12',
 'query':'9b0082b67d0ac55b4c7d42216560344567ad87ce3e75a9d5214a0762f1c15d65',
 'gt':'70d25b3fff9d68ee3571931cc28e36f03d77c8bb4eea089ca206e5e709be8e28',
 'evaluator':'3698f915ef3b7369aee527b6bb126512c0e31eb677a46480a5526cf4f909c64a',
 'source_pipnn':'315747c65f10ce3783b0622682b1237741ac307e21a8484e627e18fb00c24340',
 'source_utils':'ee2048738ad4462f21bdfea4a1cf7c2ac140f72fbd8875d869bc4f613d93db53',
 'root_cmake':'198badc698ebd5a87fe10e854dca124ac94825535931f20265b86c5d6643c2f9',
}
KNOWN_GRAPHS={
 'stock_N1':'67310319473693823c37bb441fdfb97ceb3c379f6da50f46e7623f8141559781',
 'stock_N2':'4998cb93784da92728f2f6bd02aee6d3006d44c2b80f7b8b5be2a7f85f27d3e1',
 'low_q1':'4cceb72e0dcb34f030f9cd447f2d7da2ed67a166f32188f7cfde20bcdd72e9c0',
}
DEPS={
 'PARLAYLIB':(ROOT/'experiments/R86/r86_v1_2_builds/stock_off/_deps/parlaylib-src','51017699dcc421f80479cdb238d3092233ad0d26'),
 'EIGEN':(ROOT/'experiments/R86/r86_v1_2_builds/stock_off/_deps/eigen-src','3147391d946bb4b6c68edd901f2add6ac1f31f8c'),
 'ABSEIL-CPP':(ROOT/'experiments/R86/r86_v1_2_builds/stock_off/_deps/abseil-cpp-src','bc257a88f7c1939f24e0379f14a3589e926c950c'),
 'HIGHWAY':(ROOT/'experiments/H85/r85_0_matched_baseline/build_stock/_deps/highway-src','6bc2d47793bae9c521fb4150936669647700765d'),
 'GOOGLEBENCHMARK':(ROOT/'experiments/R86/r86_v1_2_builds/stock_off/_deps/googlebenchmark-src','d886e3177c5dc48f150fbfbf142be6e724a032a4'),
}
SEED=20261117
QS=(('q1','0.01'),('q2','0.02'))
SELECTORS=('low','random','high')
ARMS=tuple((f'{mode}_{tag}',mode,frac) for mode in SELECTORS for tag,frac in QS)
BEAMS=(40,48,56,64,72,80,88,96,104,112,128,144,160,176,192,224,256,320)
TARGETS=(0.990,0.998)
EVAL_RX=re.compile(r'^R72_RECALL_ROW beam=(\d+) recall=([0-9.]+) qps=([0-9.]+) avg_cmps=([0-9.]+) avg_visited=([0-9.]+)\s*$',re.M)
COV_RX=re.compile(r'^R90_A5_LEAF_SCREEN total=(\d+) eligible=(\d+) WL_total=(\d+) WL_eligible=(\d+) gate=(\d+)\s*$',re.M)
SEL_RX=re.compile(r'^R90_A5_PASS1 selected=(\d+) n=(\d+) sort_comparisons=(\d+) GT_free=1\s*$',re.M)
CTRL_RX=re.compile(r'^R90_P32_SELECTOR mode=(low|random|high) seed=(\d+)\s*$',re.M)

# Anchors are exact passages from A5 at upstream-pinned source; fail-closed if changed.
ANCHOR_SETUP='''    std::string r90_mode = "off";
    if (const char* v = std::getenv("R90_A5_MODE")) r90_mode = v;'''
PATCH_SETUP=ANCHOR_SETUP+'''
    // R90-P3.2: independent GT-free selector ablation, default LOW is stock A5.
    std::string r90_p32_selector = "low";
    if (const char* v = std::getenv("R90_P32_SELECTOR")) r90_p32_selector = v;
    if (r90_p32_selector != "low" && r90_p32_selector != "high" &&
        r90_p32_selector != "random") {
      std::cerr << "R90_P32_INVALID_SELECTOR" << std::endl; std::abort();
    }'''
ANCHOR_SORT='''          std::sort(ranks.begin(), ranks.end(),
                    [&](const auto& a, const auto& b) {
            ++comparisons;
            return a.first != b.first ? a.first < b.first : a.second < b.second;
          });'''
PATCH_SORT='''          if (r90_p32_selector == "low") {
            // EXACT original A5 sort, including tie-break by global point ID.
            std::sort(ranks.begin(), ranks.end(),
                      [&](const auto& a, const auto& b) {
              ++comparisons;
              return a.first != b.first ? a.first < b.first : a.second < b.second;
            });
          } else if (r90_p32_selector == "high") {
            std::sort(ranks.begin(), ranks.end(),
                      [&](const auto& a, const auto& b) {
              ++comparisons;
              return a.first != b.first ? a.first > b.first : a.second < b.second;
            });
          } else {
            // Fixed-seed uniform random permutation of all global point IDs.
            // NOT derived from GT, query features, or graph neighbor quality.
            std::mt19937_64 r90_p32_rng(20261117ULL);
            std::shuffle(ranks.begin(), ranks.end(), r90_p32_rng);
          }'''
ANCHOR_PRINT='''        std::cout << "R90_A5_PASS1 selected=" << count << " n=" << n
                  << " sort_comparisons=" << comparisons
                  << " GT_free=1" << std::endl;'''
PATCH_PRINT=ANCHOR_PRINT+'''
        std::cout << "R90_P32_SELECTOR mode=" << r90_p32_selector
                  << " seed=20261117" << std::endl;'''

def ck(cond,why):
    if not cond: raise RuntimeError('R90_P32_HOLD_'+why)

def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for blob in iter(lambda:f.read(4*1024*1024),b''):h.update(blob)
    return h.hexdigest()

def patch(text):
    for name,before,after in [('SETUP',ANCHOR_SETUP,PATCH_SETUP),('SORT',ANCHOR_SORT,PATCH_SORT),('PRINT',ANCHOR_PRINT,PATCH_PRINT)]:
        ck(text.count(before)==1,'PATCH_'+name+'_'+str(text.count(before)))
        text=text.replace(before,after,1)
    ck(text.count('R90_P32_SELECTOR mode=')==1,'PATCH_PRINT_COUNT')
    return text

def shape(path,b):
    with Path(path).open('rb') as f: header=f.read(8)
    ck(len(header)==8,'SHAPE_HEADER_'+Path(path).name)
    n,d=struct.unpack('<II',header)
    ck(Path(path).stat().st_size==8+n*d*b,'SHAPE_BYTES_'+Path(path).name)
    return (n,d)

def graph(path):
    p=Path(path)
    ck(p.is_file(),'GRAPH_MISSING_'+p.name)
    with p.open('rb') as f: h=f.read(8)
    ck(h==struct.pack('<II',100000,64) and p.stat().st_size>400008,'GRAPH_BAD_'+p.name)
    return p

def git_head(path):
    p=subprocess.run(['git','-C',str(path),'rev-parse','HEAD'],capture_output=True,text=True)
    ck(p.returncode==0,'GIT_DEP_'+path.name)
    return p.stdout.strip()

def env(selector=None,frac=None):
    e=os.environ.copy();e.update(PARLAY_NUM_THREADS='1',OMP_NUM_THREADS='1',LC_ALL='C')
    for k in ('R90_A5_MODE','R90_A5_FRACTION','R90_P32_SELECTOR'):e.pop(k,None)
    if selector is not None:e.update(R90_A5_MODE='gate',R90_A5_FRACTION=str(frac),R90_P32_SELECTOR=selector)
    return e

def log_call(cmd,path,timeout=1800,environment=None):
    ck(not path.exists() and not path.is_symlink(),'LOG_EXISTS_'+path.name)
    with path.open('x',encoding='utf-8') as f:
        p=subprocess.run([str(x) for x in cmd],env=environment,stdout=f,stderr=subprocess.STDOUT,timeout=timeout,check=False)
    ck(p.returncode==0,'CALL_RC_'+str(p.returncode)+'_'+path.name)

def load_json(path):
    ck(path.is_file(),'MANIFEST_MISSING_'+path.name)
    return json.loads(path.read_text())

def preflight(out,cpu,need_fresh):
    ck(out.parent.is_dir(),'OUT_PARENT')
    if need_fresh:ck(not out.exists() and not out.is_symlink(),'OUTPUT_EXISTS')
    ck(cpu in os.sched_getaffinity(0),'CPU_NOT_AVAILABLE')
    for exe in ('cmake','taskset','git'):
        ck(shutil.which(exe) is not None,'EXE_MISSING_'+exe)
    ck(Path('/usr/bin/time').is_file(),'USR_BIN_TIME')
    h=SOURCE/'algorithms/PipNN/pipnn.h';u=SOURCE/'algorithms/PipNN/pipnn_utils.h'
    inp={'base':BASE,'query':QUERY,'gt':GT,'evaluator':EVAL,'source_pipnn':h,'source_utils':u,'root_cmake':SOURCE/'CMakeLists.txt'}
    for k,p in inp.items(): ck(p.is_file() and sha(p)==SHA_INPUT[k],'SHA_'+k)
    ck(shape(BASE,4)==(100000,128),'BASE_SHAPE')
    ck(shape(QUERY,4)==(10000,128),'QUERY_SHAPE')
    ck(shape(GT,8)==(10000,100),'GT_SHAPE')
    ck(os.access(EVAL,os.X_OK),'EVAL_ELF')
    for key,(p,head) in DEPS.items():ck(p.is_dir() and git_head(p)==head,'DEP_'+key)
    m21=load_json(P21/'result_manifest.json');m22=load_json(P22/'result_manifest.json');m23=load_json(P23/'result_manifest.json')
    ck(m21.get('status')=='NATIVE_SCREEN_COMPLETED' and m22.get('status')=='COMPLETE' and m23.get('status')=='COMPLETE','PARENTS_STATUS')
    pgraphs={
      'stock_N1': P21/'graphs/stock_N1.graph',
      'stock_N2': P21/'graphs/stock_N2.graph',
      'low_q1': P21/'graphs/a5_gate_q001_N2.graph',
      'low_q2': P23/'graphs/a5_gate_q2_N2.graph',
    }
    build21={v['arm']:v for v in m21['builds']};build23={v['arm']:v for v in m23['builds']}
    for name,p in pgraphs.items():
        graph(p)
        expected=KNOWN_GRAPHS[name] if name in KNOWN_GRAPHS else build23['a5_gate_q2_N2']['graph_sha256']
        ck(sha(p)==expected,'PARENT_GRAPH_SHA_'+name)
    ck(m22.get('graphs_sha256',{}).get('stock_N2')==KNOWN_GRAPHS['stock_N2'],'P22_GRAPH_RECEIPT')
    ck(build21['a5_gate_q001_N2']['graph_sha256']==KNOWN_GRAPHS['low_q1'],'P21_A5_SHA')
    patch(h.read_text())
    print('R90_P32_PREFLIGHT_SOURCE_DEP_GT_PARENT_GRAPHS_AND_PATCH_PASS',flush=True)
    return pgraphs

def parse_build(s,mode,frac):
    sel=SEL_RX.findall(s);cov=COV_RX.findall(s);ctrl=CTRL_RX.findall(s)
    ck(len(sel)==len(cov)==len(ctrl)==1,'BUILD_MARKERS_'+mode)
    selected,n,comp=map(int,sel[0]);total,eligible,wl,kept,gate=map(int,cov[0]);actual,seed=ctrl[0]
    ck(actual==mode and int(seed)==SEED,'SELECTOR_MODE_'+mode)
    ck(n==100000 and selected==int(n*float(frac)),'SELECTED_'+mode)
    ck(0<=eligible<=total and 0<=kept<=wl and gate==1 and wl>0,'LEAF_COUNTERS')
    ck((mode!='random' and comp>0) or (mode=='random' and comp==0),'SORT_CMPS')
    return dict(selector=mode,fraction=float(frac),selected=selected,sort_comparisons=comp,
                total_leaves=total,eligible_leaves=eligible,eligible_leaf_pct=100*eligible/total,
                total_wl=wl,retained_wl=kept,retained_wl_pct=100*kept/wl)

def parse_eval(text,beams):
    ck(text.count('R72_RECALL_INPUT_PASS')==1 and text.count('R72_RECALL_EVAL_PASS')==1,'EVAL_MARKERS')
    got=EVAL_RX.findall(text);ck(len(got)==len(beams),'EVAL_ROW_COUNT')
    rows=[]
    for z,b in zip(got,beams):
        bb=int(z[0]);r,q,c,v=map(float,z[1:]);ck(bb==b and 0<=r<=1 and q>0 and c>=0 and v>=0 and all(map(math.isfinite,(r,q,c,v))),'EVAL_ROW_BAD')
        rows.append(dict(beam=bb,recall=r,qps=q,avg_cmps=c,avg_visited=v))
    return rows

def crossing(rows,target):
    for i,b in enumerate(rows):
        if b['recall']==target:return dict(b0=b['beam'],b1=b['beam'],r0=target,r1=target,t=0)
        if i>0 and rows[i-1]['recall']<target<b['recall']:
            a=rows[i-1];t=(target-a['recall'])/(b['recall']-a['recall'])
            return dict(b0=a['beam'],b1=b['beam'],r0=a['recall'],r1=b['recall'],t=t)
    return None

def save_json(path,obj):
    tmp=path.with_name(path.name+'.part')
    with tmp.open('w',encoding='utf-8') as f:json.dump(obj,f,indent=2);f.write('\n')
    tmp.replace(path)

def build_command(exe,output):
    return [str(exe),'-base_path',str(BASE),'-graph_outfile',str(output),
            '-num_clusters','2','-cluster_size','1024','-table_size','160',
            '-top_level_leaders','100','-fanout_scheme','10,3,1','-mst_deg','2',
            '-prune','1','-prune_all','1','-prune_degree','64','-hash_bits','12','-alpha','1.1','-k','0']

def pilot(out,cpu,reps):
    parents=preflight(out,cpu,True)
    out.mkdir();(out/'graphs').mkdir();(out/'logs').mkdir()
    progress=dict(status='RUNNING',script_sha256=sha(Path(__file__).resolve()),cpu=cpu,seed=SEED,reps=reps,
                  source_sha256=None,elf_sha256=None,builds=[],sweeps=[],repeats=[],summary=[],
                  limits=['Single CPU, fixed graph construction seed; one random selector seed, not statistical proof',
                          'N1/N2 baseline graphs reused from P2.1; baseline build wall from P2.1',
                          'Interpolated Recall from discrete beams, not native exact-matched Recall',
                          'Ten thousand query ground truth used only for offline evaluation; selector GT-free',
                          'Cost of sorting/shuffling differs between selector arms and is included in measured BUILD'])
    save_json(out/'progress.json',progress)
    shutil.copytree(SOURCE,out/'source',symlinks=True)
    h=out/'source/algorithms/PipNN/pipnn.h'
    h.write_text(patch(h.read_text()))
    progress['source_sha256']=sha(h);save_json(out/'progress.json',progress)
    build=out/'build'
    conf=['cmake','-S',str(out/'source'),'-B',str(build),'-DCMAKE_BUILD_TYPE=Release',
          '-DCMAKE_CXX_FLAGS=-O3 -pthread','-DCMAKE_EXPORT_COMPILE_COMMANDS=ON',
          '-DFETCHCONTENT_FULLY_DISCONNECTED=ON','-DR90_A5_GATE=ON']
    for key,(dep,_) in DEPS.items():conf.append('-DFETCHCONTENT_SOURCE_DIR_'+key+'='+str(dep))
    log_call(conf,out/'configure.log',timeout=1800)
    log_call(['cmake','--build',str(build),'--target','neighbors-pipnn_FLOAT_T_EUCLIDEAN','--parallel','2'],out/'compile.log',timeout=3600)
    exe=build/'algorithms/PipNN/neighbors-pipnn_FLOAT_T_EUCLIDEAN'
    ck(exe.is_file() and os.access(exe,os.X_OK),'BUILT_ELF_MISSING')
    progress['elf_sha256']=sha(exe)
    print('R90_P32_SOURCE_CPP_COMPILATION_PASS',progress['elf_sha256'],flush=True)
    for arm,mode,q in ARMS:
        gp=out/'graphs'/f'{arm}.graph';stdout=out/'logs'/f'{arm}.build.stdout';timefile=out/'logs'/f'{arm}.build.time'
        cmd=['/usr/bin/time','-v','-o',str(timefile),'taskset','-c',str(cpu),*build_command(exe,gp)]
        print('R90_P32_BUILD_START',arm,'q',q,flush=True)
        start=time.perf_counter();log_call(cmd,stdout,timeout=2400,environment=env(mode,q));wall=time.perf_counter()-start
        gsha=sha(graph(gp));data=parse_build(stdout.read_text(errors='replace'),mode,q)
        ck(data['total_wl']==1493961225,'P2_LEAF_WORK_DIFF_'+arm)
        if mode=='low':
            expected=KNOWN_GRAPHS['low_q1'] if q=='0.01' else sha(parents['low_q2'])
            ck(gsha==expected,'LOW_SOURCE_GRAPH_PARITY_'+arm)
        entry=dict(arm=arm,selector=mode,fraction=float(q),wall_s=wall,graph_path=str(gp),graph_sha256=gsha,
                   stdout_path=str(stdout),stdout_sha256=sha(stdout),time_path=str(timefile),time_sha256=sha(timefile),
                   graph_bytes=gp.stat().st_size,coverage=data)
        progress['builds'].append(entry);save_json(out/'progress.json',progress)
        print('R90_P32_BUILD_PASS',arm,'wall_s',round(wall,4),'retained_wl_pct',round(data['retained_wl_pct'],3),flush=True)
    graph_paths={'stock_N1':parents['stock_N1'],'stock_N2':parents['stock_N2']}
    graph_paths.update({a:out/'graphs'/f'{a}.graph' for a,_,_ in ARMS})
    for arm,gp in graph_paths.items():
        print('R90_P32_SWEEP_START',arm,flush=True)
        log=out/'logs'/f'{arm}.sweep.stdout'
        cmd=['taskset','-c',str(cpu),str(EVAL),str(gp),str(BASE),str(QUERY),str(GT),','.join(map(str,BEAMS))]
        log_call(cmd,log,timeout=1800,environment=env())
        rows=parse_eval(log.read_text(errors='replace'),BEAMS)
        ck(all(v['recall']<=w['recall']+1e-6 for v,w in zip(rows,rows[1:])),'RECALL_NON_MONOTONE_'+arm)
        targets={str(target):crossing(rows,target) for target in TARGETS}
        progress['sweeps'].append(dict(arm=arm,log_path=str(log),log_sha256=sha(log),graph_sha256=sha(gp),rows=rows,targets=targets))
        print('R90_P32_SWEEP_PASS',arm,targets,flush=True)
        save_json(out/'progress.json',progress)
    target_map={x['arm']:x['targets'] for x in progress['sweeps']}
    arms=list(graph_paths)
    for rep in range(1,reps+1):
        order=arms[(rep-1)%len(arms):]+arms[:(rep-1)%len(arms)]
        if rep%2==0:order.reverse()
        for arm in order:
            found=[t for t in target_map[arm].values() if t is not None]
            if not found:continue
            beams=sorted({int(v[k]) for v in found for k in ('b0','b1')})
            gp=graph_paths[arm]
            log=out/'logs'/f'{arm}.repeat{rep}.stdout'
            cmd=['taskset','-c',str(cpu),str(EVAL),str(gp),str(BASE),str(QUERY),str(GT),','.join(map(str,beams))]
            log_call(cmd,log,timeout=1800,environment=env())
            rows=parse_eval(log.read_text(errors='replace'),beams)
            sweep_rows={r['beam']:r for r in next(z for z in progress['sweeps'] if z['arm']==arm)['rows']}
            ck(all(abs(r['recall']-sweep_rows[r['beam']]['recall'])<2e-6 for r in rows),'REPEAT_RECALL_'+arm)
            progress['repeats'].append(dict(arm=arm,rep=rep,beams=beams,log_path=str(log),log_sha256=sha(log),graph_sha256=sha(gp),rows=rows))
            print('R90_P32_REPEAT_PASS',arm,rep,flush=True)
            save_json(out/'progress.json',progress)
    buildmap={x['arm']:x for x in progress['builds']}
    parent_manifest=load_json(P21/'result_manifest.json')
    bm={x['arm']:x for x in parent_manifest['builds']}
    for arm in graph_paths:
        for target in TARGETS:
            x=target_map[arm][str(target)]
            if x is None:
                progress['summary'].append(dict(arm=arm,target=target,status='NO_CROSSING_UP_TO_320'));continue
            rrep=[z for z in progress['repeats'] if z['arm']==arm]
            ck(len(rrep)==reps,'REPEAT_COUNT_'+arm)
            med={beam:statistics.median(next(v['qps'] for v in z['rows'] if v['beam']==beam) for z in rrep) for beam in (x['b0'],x['b1'])}
            latency=(1-x['t'])*(1e6/med[x['b0']])+x['t']*(1e6/med[x['b1']])
            qps=1e6/latency
            wall=bm[arm].get('wall_s_external_including_output',bm[arm].get('build_wall_s')) if arm in bm else buildmap[arm]['wall_s']
            ck(wall is not None,'BUILD_WALL_'+arm)
            progress['summary'].append(dict(arm=arm,target=target,status='INTERPOLATION_PILOT',build_s=wall,
                      bracket=[x['b0'],x['b1']],recall_bracket=[x['r0'],x['r1']],qps_latency_interp=qps,
                      qps_endpoints_median=med,selector='stock' if arm.startswith('stock_') else buildmap[arm]['selector'],
                      retained_wl_pct=None if arm.startswith('stock_') else buildmap[arm]['coverage']['retained_wl_pct']))
            print('R90_P32_INTERP_ROW',json.dumps(progress['summary'][-1],sort_keys=True),flush=True)
    progress['status']='COMPLETE'
    save_json(out/'result_manifest.json',progress)
    print('R90_P32_PILOT_COMPLETE_ONE_RANDOM_SEED_NOT_FORMAL',flush=True)
    audit(out,cpu)

def audit(out,cpu):
    preflight(out,cpu,False)
    m=load_json(out/'result_manifest.json');ck(m.get('status')=='COMPLETE','RESULT_STATUS')
    ck(m.get('script_sha256')==sha(Path(__file__).resolve()),'SCRIPT_CHANGED')
    h=out/'source/algorithms/PipNN/pipnn.h';exe=out/'build/algorithms/PipNN/neighbors-pipnn_FLOAT_T_EUCLIDEAN'
    ck(h.is_file() and sha(h)==m['source_sha256'],'SOURCE_SHA')
    ck(exe.is_file() and sha(exe)==m['elf_sha256'],'ELF_SHA')
    ck(len(m['builds'])==6 and len(m['sweeps'])==8,'BUILD_AND_SWEEP_COUNTS')
    expected_repeated_arms=sum(any(v is not None for v in row['targets'].values()) for row in m['sweeps'])
    ck(len(m['repeats'])==expected_repeated_arms*m['reps'] and len(m['summary'])==16,
       'REPEAT_AND_SUMMARY_COUNTS')
    for row in m['builds']:
        p=graph(row['graph_path']);ck(p.parent.resolve()==(out/'graphs').resolve() and sha(p)==row['graph_sha256'],'BUILT_GRAPH_'+row['arm'])
        for pkey,hkey in [('stdout_path','stdout_sha256'),('time_path','time_sha256')]:
            f=Path(row[pkey]);ck(f.is_file() and sha(f)==row[hkey],'BUILD_LOG_'+row['arm'])
        ck(parse_build(Path(row['stdout_path']).read_text(errors='replace'),row['selector'],row['fraction'])==row['coverage'],'BUILD_PARSE_'+row['arm'])
    for category in ('sweeps','repeats'):
        for z in m[category]:
            f=Path(z['log_path']);ck(f.is_file() and sha(f)==z['log_sha256'],'SEARCH_SHA_'+f.name)
            ck(parse_eval(f.read_text(errors='replace'),BEAMS if category=='sweeps' else z['beams'])==z['rows'],'SEARCH_PARSE_'+f.name)
    print('R90_P32_AUDIT_SOURCE_ELF_GRAPHS_LOGS_AND_INTERPOLATION_PASS',flush=True)

def selftest():
    fake='\n'.join((ANCHOR_SETUP,ANCHOR_SORT,ANCHOR_PRINT))
    p=patch(fake)
    ck('r90_p32_selector == "high"' in p and 'mt19937_64' in p,'PATCH_TEST')
    try:patch(p)
    except RuntimeError:pass
    else:raise RuntimeError('R90_P32_HOLD_PATCH_NONIDEMPOTENT')
    rows=[dict(beam=40,recall=.98,qps=19000),dict(beam=48,recall=.995,qps=15000)]
    c=crossing(rows,.99)
    ck(c is not None and c['b0']==40 and c['b1']==48 and abs(c['t']-2/3)<1e-9,'CROSS_TEST')
    ck(crossing(rows,.998) is None,'NO_CROSS_TEST')
    s=('R90_A5_MODE=gate\nR90_A5_PASS1 selected=1000 n=100000 sort_comparisons=123456 GT_free=1\n'
       'R90_P32_SELECTOR mode=low seed=20261117\n'
       'R90_A5_LEAF_SCREEN total=8297 eligible=4846 WL_total=1493961225 WL_eligible=1067784975 gate=1\n')
    ck(parse_build(s,'low',.01)['selected']==1000,'BUILD_PARSE_TEST')
    ck(len(ARMS)==6 and len(set(a for a,_,_ in ARMS))==6,'ARMS_TEST')
    print('R90_P32_SELFTEST_PASS_PATCH_SELECTOR_EVAL_AND_INTERPOLATION',flush=True)

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('phase',choices=('selftest','preflight','pilot','audit'))
    ap.add_argument('--cpu',type=int,default=0)
    ap.add_argument('--reps',type=int,default=3)
    ap.add_argument('--out',type=Path,default=OUT)
    a=ap.parse_args()
    ck(a.reps in (3,5),'REPS_3_OR_5')
    out=a.out.expanduser().resolve(strict=False)
    if a.phase=='selftest':selftest()
    elif a.phase=='preflight':preflight(out,a.cpu,True)
    elif a.phase=='pilot':pilot(out,a.cpu,a.reps)
    else:audit(out,a.cpu)

if __name__=='__main__':
    try:main()
    except Exception as e:
        print('R90_P32_HOLD',type(e).__name__,str(e),file=sys.stderr,flush=True)
        sys.exit(2)
