#!/usr/bin/env python3
"""R90 P3.3-A: paired low/high-degree vs RANDOM-LEAF at matched Pass-2 W_L.

Usage: selftest | preflight | pilot | audit [--seed 555|556|557] [--random-reps 1..3]
Builds only an isolated copy of the pinned R90-P0 PiPNN+A5 source. New code:
* configurable deterministic graph partition SEED (default 555), checked against historical SHA;
* low/high first-pass degree selector for q=1% and 2%; and
* uniform shuffled LEAF-LEVEL randomized controls matched to the exact W_L budget
  of each low/high arm for the same graph seed (overshoot bounded by one leaf).
Search uses the pinned 10K-query native R85 evaluator. Computes exploratory
Recall--latency interpolation, never a formal matched-Recall claim. Audit
inputs and receipts. One script invocation runs ONE graph seed to keep
output independent; repeat with seed 556/557 after 555 pilot passes.
"""
from __future__ import annotations
import argparse,hashlib,json,math,os,re,shutil,statistics,struct,subprocess,sys,time
from pathlib import Path

ROOT=Path.home()/'ann-task-a'; R90=ROOT/'experiments/R90'
P0=R90/'r90_p0_stock_a5_compile_gate_v1'
P21=R90/'r90_p2_sift100k_pass2_value_gate1_v1'
P32=R90/'r90_p32_selector_controls_v1'
SOURCE=P0/'a5_source'
BASE=ROOT/'data/sift100k.fbin'; QUERY=ROOT/'data/sift1m_queries.fbin'
GT=ROOT/'experiments/H85/r85_b1_controlled/step8e_gt10k/sift100k_sift1mqueries10k_exact100.ibin'
EVAL=ROOT/'experiments/H85/r85_b1_controlled/step8e_native_eval/r85_b1_100k_graph_recall'
INPUT_SHA={
 'base':'e50ff1bc34bcc6d1c97dd001023c09a666971cde64605cc06671ed8a8ff1ed12',
 'query':'9b0082b67d0ac55b4c7d42216560344567ad87ce3e75a9d5214a0762f1c15d65',
 'gt':'70d25b3fff9d68ee3571931cc28e36f03d77c8bb4eea089ca206e5e709be8e28',
 'evaluator':'3698f915ef3b7369aee527b6bb126512c0e31eb677a46480a5526cf4f909c64a',
 'source_pipnn':'315747c65f10ce3783b0622682b1237741ac307e21a8484e627e18fb00c24340',
 'source_utils':'ee2048738ad4462f21bdfea4a1cf7c2ac140f72fbd8875d869bc4f613d93db53',
 'root_cmake':'198badc698ebd5a87fe10e854dca124ac94825535931f20265b86c5d6643c2f9'}
DEPS={
 'PARLAYLIB':(ROOT/'experiments/R86/r86_v1_2_builds/stock_off/_deps/parlaylib-src','51017699dcc421f80479cdb238d3092233ad0d26'),
 'EIGEN':(ROOT/'experiments/R86/r86_v1_2_builds/stock_off/_deps/eigen-src','3147391d946bb4b6c68edd901f2add6ac1f31f8c'),
 'ABSEIL-CPP':(ROOT/'experiments/R86/r86_v1_2_builds/stock_off/_deps/abseil-cpp-src','bc257a88f7c1939f24e0379f14a3589e926c950c'),
 'HIGHWAY':(ROOT/'experiments/H85/r85_0_matched_baseline/build_stock/_deps/highway-src','6bc2d47793bae9c521fb4150936669647700765d'),
 'GOOGLEBENCHMARK':(ROOT/'experiments/R86/r86_v1_2_builds/stock_off/_deps/googlebenchmark-src','d886e3177c5dc48f150fbfbf142be6e724a032a4')}
KNOWN_STOCK={'stock_N1':'67310319473693823c37bb441fdfb97ceb3c379f6da50f46e7623f8141559781',
 'stock_N2':'4998cb93784da92728f2f6bd02aee6d3006d44c2b80f7b8b5be2a7f85f27d3e1'}
QS={'q1':'0.01','q2':'0.02'}
BEAMS=(40,48,56,64,72,80,88,96,104,112,128,144,160,176,192,224,256,320)
TARGETS=(.990,.998)
EVAL_RX=re.compile(r'^R72_RECALL_ROW beam=(\d+) recall=([0-9.]+) qps=([0-9.]+) avg_cmps=([0-9.]+) avg_visited=([0-9.]+)\s*$',re.M)
COV_RX=re.compile(r'^R90_A5_LEAF_SCREEN total=(\d+) eligible=(\d+) WL_total=(\d+) WL_eligible=(\d+) gate=(\d+)\s*$',re.M)
SEL_RX=re.compile(r'^R90_A5_PASS1 selected=(\d+) n=(\d+) sort_comparisons=(\d+) GT_free=1\s*$',re.M)
BUD_RX=re.compile(r'^R90_P33_BUDGET target=(\d+) achieved=(\d+) max_leaf=(\d+) seed=(\d+)\s*$',re.M)

A_SETUP='''    std::string r90_mode = "off";
    if (const char* v = std::getenv("R90_A5_MODE")) r90_mode = v;'''
P_SETUP=A_SETUP+'''
    // R90 P3.3-A: matched W_L leaf randomization and independent graph seed.
    std::string r90_p33_selector = "low";
    if (const char* v = std::getenv("R90_P33_SELECTOR")) r90_p33_selector = v;
    if (r90_p33_selector != "low" && r90_p33_selector != "high") {
      std::cerr << "R90_P33_SELECTOR_INVALID" << std::endl; std::abort();
    }
    std::string r90_p33_policy = "selector";
    if (const char* v = std::getenv("R90_P33_POLICY")) r90_p33_policy = v;
    if (r90_p33_policy != "selector" && r90_p33_policy != "budget") {
      std::cerr << "R90_P33_POLICY_INVALID" << std::endl; std::abort();
    }'''
A_SORT='''          std::sort(ranks.begin(), ranks.end(),
                    [&](const auto& a, const auto& b) {
            ++comparisons;
            return a.first != b.first ? a.first < b.first : a.second < b.second;
          });'''
P_SORT='''          if (r90_p33_selector == "high") {
            std::sort(ranks.begin(), ranks.end(),
                      [&](const auto& a, const auto& b) {
              ++comparisons;
              return a.first != b.first ? a.first > b.first : a.second < b.second;
            });
          } else {
            // EXACT original A5 low sort; do not alter tie-breaking.
            std::sort(ranks.begin(), ranks.end(),
                      [&](const auto& a, const auto& b) {
              ++comparisons;
              return a.first != b.first ? a.first < b.first : a.second < b.second;
            });
          }'''
A_SELECT_START='''        } else if (r90_mode == "gate" || r90_mode == "dryrun") {
          std::vector<std::pair<size_t, size_t>> ranks;'''
P_SELECT_START='''        } else if (r90_mode == "gate" || r90_mode == "dryrun") {
          // In randomized leaf baseline, skip the degree sort entirely.
          if (r90_p33_policy != "budget") {
          std::vector<std::pair<size_t, size_t>> ranks;'''
A_SELECT_END='''          for (size_t p = 0; p < count; ++p) r90_selected[ranks[p].second] = 1;
        }
        std::cout << "R90_A5_PASS1 selected="'''
P_SELECT_END='''          for (size_t p = 0; p < count; ++p) r90_selected[ranks[p].second] = 1;
          }
        }
        std::cout << "R90_A5_PASS1 selected="'''
A_LEAF_COUNTER='''    std::atomic<size_t> r90_all_leaves(0), r90_eligible_leaves(0);
    std::atomic<size_t> r90_all_wl(0), r90_eligible_wl(0);'''
P_LEAF_COUNTER=A_LEAF_COUNTER+'''
    std::vector<unsigned char> r90_p33_budget_mask;
    if (r90_selected != nullptr && r90_gate && std::getenv("R90_P33_TARGET_WL")) {
      const char* v = std::getenv("R90_P33_TARGET_WL");
      char* end = nullptr;
      const unsigned long long target = std::strtoull(v, &end, 10);
      if (end == v || *end || !target) {
        std::cerr << "R90_P33_BUDGET_INVALID" << std::endl; std::abort();
      }
      const char* s = std::getenv("R90_P33_LEAF_SEED");
      if (!s) { std::cerr << "R90_P33_LEAF_SEED_MISSING" << std::endl; std::abort(); }
      char* se = nullptr;
      const unsigned long long lseed = std::strtoull(s, &se, 10);
      if (se == s || *se || lseed == 0) {
        std::cerr << "R90_P33_LEAF_SEED_INVALID" << std::endl; std::abort();
      }
      std::vector<size_t> order;
      for (size_t i = 0; i < buckets.size(); ++i)
        if (buckets[i].size() > 1) order.push_back(i);
      std::mt19937_64 rng(lseed);
      std::shuffle(order.begin(), order.end(), rng);
      r90_p33_budget_mask.assign(buckets.size(), 0);
      unsigned long long achieved = 0, max_leaf = 0, total = 0;
      for (size_t i : order) {
        const unsigned long long cost = static_cast<unsigned long long>(buckets[i].size()) * buckets[i].size();
        total += cost;
        if (cost > max_leaf) max_leaf = cost;
        if (achieved < target) {
          r90_p33_budget_mask[i] = 1;
          achieved += cost;
        }
      }
      if (target > total || achieved < target || achieved - target > max_leaf) {
        std::cerr << "R90_P33_BUDGET_OUT_OF_RANGE" << std::endl; std::abort();
      }
      std::cout << "R90_P33_BUDGET target=" << target << " achieved=" << achieved
                << " max_leaf=" << max_leaf << " seed=" << lseed << std::endl;
    }'''
A_ELIG='''           bool eligible = false;
           for (const auto u : buckets[i])
             if ((*r90_selected)[u]) { eligible = true; break; }'''
P_ELIG='''           bool eligible = false;
           if (!r90_p33_budget_mask.empty()) {
             eligible = r90_p33_budget_mask[i] != 0;
           } else {
             for (const auto u : buckets[i])
               if ((*r90_selected)[u]) { eligible = true; break; }
           }'''
A_SEED='''  size_t SEED = 555;'''
P_SEED='''  size_t SEED = []() -> size_t {
    const char* v = std::getenv("R90_P33_GRAPH_SEED");
    if (!v) return 555;
    char* end = nullptr;
    unsigned long long x = std::strtoull(v, &end, 10);
    if (end == v || *end || x < 1 || x > 4294967295ULL) {
      std::cerr << "R90_P33_GRAPH_SEED_INVALID" << std::endl; std::abort();
    }
    return static_cast<size_t>(x);
  }();'''

def ck(ok,msg):
    if not ok: raise RuntimeError('R90_P33_HOLD_'+msg)
def sha(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for part in iter(lambda:f.read(4*1024*1024),b''):h.update(part)
    return h.hexdigest()
def patch(s):
    replacements=[('MODE_SETUP',A_SETUP,P_SETUP),('SELECT_START',A_SELECT_START,P_SELECT_START),
                  ('SORT',A_SORT,P_SORT),('SELECT_END',A_SELECT_END,P_SELECT_END),
                  ('LEAF_COUNTER',A_LEAF_COUNTER,P_LEAF_COUNTER),('ELIG',A_ELIG,P_ELIG),('SEED',A_SEED,P_SEED)]
    for name,a,b in replacements:
        ck(s.count(a)==1,'PATCH_'+name+'_COUNT_'+str(s.count(a)))
        s=s.replace(a,b,1)
    ck(s.count('R90_P33_BUDGET target=')==1 and s.count('R90_P33_GRAPH_SEED')==2,'PATCH_RECEIPT')
    return s

def shape(p,b):
    with Path(p).open('rb') as f:h=f.read(8)
    ck(len(h)==8,'HEADER_'+Path(p).name)
    n,d=struct.unpack('<II',h)
    ck(Path(p).stat().st_size==8+n*d*b,'DATA_SIZE_'+Path(p).name)
    return n,d

def graph(p):
    p=Path(p);ck(p.is_file(),'GRAPH_MISSING_'+p.name)
    with p.open('rb') as f:hdr=f.read(8)
    ck(hdr==struct.pack('<II',100000,64) and p.stat().st_size>400008,'GRAPH_FORMAT_'+p.name)
    return p

def load(p): ck(Path(p).is_file(),'MISSING_'+Path(p).name);return json.loads(Path(p).read_text())
def store(p,data):
    p=Path(p);tmp=p.with_name(p.name+'.part')
    with tmp.open('w',encoding='utf8') as f:json.dump(data,f,indent=2,sort_keys=True);f.write('\n')
    tmp.replace(p)
def git_head(p):
    r=subprocess.run(['git','-C',str(p),'rev-parse','HEAD'],capture_output=True,text=True)
    ck(r.returncode==0,'GIT_'+Path(p).name)
    return r.stdout.strip()
def environment(seed,policy='off',selector='low',q='0.01',target=None,leaf_seed=None):
    e=os.environ.copy();e.update(PARLAY_NUM_THREADS='1',OMP_NUM_THREADS='1',LC_ALL='C',R90_P33_GRAPH_SEED=str(seed))
    for k in ('R90_A5_MODE','R90_A5_FRACTION','R90_P33_POLICY','R90_P33_SELECTOR','R90_P33_TARGET_WL','R90_P33_LEAF_SEED'):
        e.pop(k,None)
    if policy!='off':
        e.update(R90_A5_MODE='gate',R90_A5_FRACTION=str(q),R90_P33_SELECTOR=selector,
                 R90_P33_POLICY='budget' if policy=='budget' else 'selector')
    if target is not None:e['R90_P33_TARGET_WL']=str(target)
    if leaf_seed is not None:e['R90_P33_LEAF_SEED']=str(leaf_seed)
    return e

def run(cmd,log,timeout=3600,e=None):
    ck(not log.exists() and not log.is_symlink(),'LOG_EXISTS_'+log.name)
    with log.open('x',encoding='utf8') as f:
        p=subprocess.run([str(v) for v in cmd],stdout=f,stderr=subprocess.STDOUT,env=e,timeout=timeout,check=False)
    ck(p.returncode==0,'PROC_RC_'+str(p.returncode)+'_'+log.name)

def preflight(out,seed,cpu,need_fresh):
    ck(out.parent.is_dir(),'OUT_PARENT')
    if need_fresh:ck(not out.exists() and not out.is_symlink(),'OUT_EXISTS')
    ck(cpu in os.sched_getaffinity(0),'CPU_UNAVAILABLE')
    for p in ('cmake','taskset','git'):ck(shutil.which(p) is not None,'EXEC_'+p)
    ck(Path('/usr/bin/time').is_file(),'TIME_MISSING')
    for name,p in {'base':BASE,'query':QUERY,'gt':GT,'evaluator':EVAL,
       'source_pipnn':SOURCE/'algorithms/PipNN/pipnn.h','source_utils':SOURCE/'algorithms/PipNN/pipnn_utils.h',
       'root_cmake':SOURCE/'CMakeLists.txt'}.items():
        ck(p.is_file() and sha(p)==INPUT_SHA[name],'SHA_'+name)
    ck(shape(BASE,4)==(100000,128),'BASE_SHAPE')
    ck(shape(QUERY,4)==(10000,128),'QUERY_SHAPE')
    ck(shape(GT,8)==(10000,100),'GT_SHAPE')
    ck(os.access(EVAL,os.X_OK),'EVAL_EXEC')
    for name,(p,git_sha) in DEPS.items():ck(p.is_dir() and git_head(p)==git_sha,'DEP_'+name)
    m21=load(P21/'result_manifest.json');m32=load(P32/'result_manifest.json')
    ck(m21.get('status')=='NATIVE_SCREEN_COMPLETED' and m32.get('status')=='COMPLETE','PARENT_STATUS')
    for name,gs in KNOWN_STOCK.items():
        gp=P21/'graphs'/f'{name}.graph';ck(sha(graph(gp))==gs,'BASELINE_'+name)
    patch((SOURCE/'algorithms/PipNN/pipnn.h').read_text())
    ck(seed in (555,556,557),'GRAPH_SEED_OUTSIDE_PREREG')
    print('R90_P33_PREFLIGHT_PINNED_SOURCE_GT_EVAL_AND_PARENT_SHA_PASS',{'seed':seed,'cpu':cpu},flush=True)
    return m32

def bcmd(exe,out,n):
    return [exe,'-base_path',BASE,'-graph_outfile',out,'-num_clusters',str(n),
            '-cluster_size','1024','-table_size','160','-top_level_leaders','100',
            '-fanout_scheme','10,3,1','-mst_deg','2','-prune','1','-prune_all','1',
            '-prune_degree','64','-hash_bits','12','-alpha','1.1','-k','0']

def cov(s,policy,q):
    matches=COV_RX.findall(s)
    if policy=='off':ck(not matches,'STOCK_HAS_COV');return None
    ck(len(matches)==1,'COV_COUNT')
    total,eligible,total_wl,kept,gate=map(int,matches[0]);sel=SEL_RX.findall(s)
    ck(len(sel)==1 and gate==1,'SEL_COV_MARKERS')
    count,n,comparisons=map(int,sel[0]);ck(n==100000,'COUNT_N')
    if policy=='budget':ck(count==0 and comparisons==0,'BUDGET_SHOULD_SKIP_SELECTOR')
    else:ck(count==int(100000*float(q)) and comparisons>0,'SELECTOR_Q_COUNT')
    ck(0<=eligible<=total and 0<=kept<=total_wl and total_wl>0,'COV_RANGE')
    found=BUD_RX.findall(s)
    if policy=='budget':
        ck(len(found)==1,'BUDGET_MARKER')
        target,achieved,maxleaf,leafseed=map(int,found[0])
        ck(achieved==kept and 0<=achieved-target<=maxleaf,'BUDGET_COST')
    else:ck(len(found)==0,'UNEXPECTED_BUDGET')
    return dict(leaves=total,eligible_leaves=eligible,wl_total=total_wl,wl_kept=kept,
                wl_retained_pct=100*kept/total_wl,sort_comparisons=comparisons,
                budget=None if not found else dict(zip(('target','achieved','maxleaf','leafseed'),map(int,found[0]))))

def parse_eval(s,beams):
    ck(s.count('R72_RECALL_INPUT_PASS')==1 and s.count('R72_RECALL_EVAL_PASS')==1,'EVAL_MARKER')
    found=EVAL_RX.findall(s);ck(len(found)==len(beams),'EVAL_COUNT')
    rows=[]
    for z,b in zip(found,beams):
        beam=int(z[0]); r,q,c,v=map(float,z[1:]);ck(beam==b and 0<=r<=1 and q>0 and c>=0 and v>=0 and all(map(math.isfinite,(r,q,c,v))),'EVAL_ROW')
        rows.append(dict(beam=b,recall=r,qps=q,avg_cmps=c,avg_visited=v))
    return rows

def bracket(rows,target):
    for i,r in enumerate(rows):
        if r['recall']==target:return dict(b0=r['beam'],b1=r['beam'],t=0,r0=target,r1=target)
        if i and rows[i-1]['recall']<target<r['recall']:
            a=rows[i-1];return dict(b0=a['beam'],b1=r['beam'],r0=a['recall'],r1=r['recall'],t=(target-a['recall'])/(r['recall']-a['recall']))
    return None

def build_arm(state,out,exe,cpu,name,seed,n,policy='off',selector='low',q='0.01',target=None,leafseed=None):
    gp=out/'graphs'/f'{name}.graph';log=out/'logs'/f'{name}.build.stdout';tf=out/'logs'/f'{name}.build.time'
    e=environment(seed,policy,selector,q,target,leafseed)
    print('R90_P33_BUILD_START',name,'seed',seed,'target',target,flush=True)
    start=time.perf_counter()
    run(['/usr/bin/time','-v','-o',tf,'taskset','-c',cpu,*bcmd(exe,gp,n)],log,e=e)
    wall=time.perf_counter()-start
    gs=sha(graph(gp));data=cov(log.read_text(errors='replace'),policy,q)
    item=dict(arm=name,seed=seed,n=n,policy=policy,selector=selector,fraction=float(q),wall_s=wall,
              graph=str(gp),graph_sha=gs,stdout=str(log),stdout_sha=sha(log),timefile=str(tf),time_sha=sha(tf),coverage=data)
    state['builds'].append(item);store(out/'progress.json',state)
    print('R90_P33_BUILD_PASS',name,'wall_s',round(wall,4),'wl_kept',None if data is None else data['wl_kept'],flush=True)
    return item

def pilot(out,seed,cpu,random_reps,search_reps):
    old=preflight(out,seed,cpu,True)
    out.mkdir();(out/'logs').mkdir();(out/'graphs').mkdir()
    state=dict(status='RUNNING',seed=seed,script_sha=sha(Path(__file__).resolve()),
               random_reps=random_reps,search_reps=search_reps,cpu=cpu,builds=[],sweeps=[],repeats=[],summary=[],
               limits=['One graph seed per experiment; 3 graph seeds required for inference',
                       'Random leaf budget matched by squared leaf size, not actual CPU work',
                       'Only a randomized leaf set, no rank selector for randomized control',
                       'No exactly matched-Recall; interpolation on measured beam brackets',
                       'QPS timing noise; single-machine CPU pinned; not yet tuned stock Pareto'])
    store(out/'progress.json',state)
    shutil.copytree(SOURCE,out/'source',symlinks=True)
    h=out/'source/algorithms/PipNN/pipnn.h';h.write_text(patch(h.read_text()))
    state['source_sha']=sha(h);store(out/'progress.json',state)
    cmd=['cmake','-S',out/'source','-B',out/'build','-DCMAKE_BUILD_TYPE=Release',
         '-DCMAKE_CXX_FLAGS=-O3 -pthread','-DCMAKE_EXPORT_COMPILE_COMMANDS=ON',
         '-DFETCHCONTENT_FULLY_DISCONNECTED=ON','-DR90_A5_GATE=ON']
    for key,(p,_) in DEPS.items():cmd.append('-DFETCHCONTENT_SOURCE_DIR_'+key+'='+str(p))
    run(cmd,out/'configure.log',timeout=1800)
    run(['cmake','--build',out/'build','--target','neighbors-pipnn_FLOAT_T_EUCLIDEAN','--parallel','2'],out/'compile.log',timeout=3600)
    exe=out/'build/algorithms/PipNN/neighbors-pipnn_FLOAT_T_EUCLIDEAN'
    ck(exe.is_file() and os.access(exe,os.X_OK),'EXE_BUILD')
    state['elf_sha']=sha(exe);store(out/'progress.json',state)
    print('R90_P33_NATIVE_CPP_BUILD_PASS',state['elf_sha'],flush=True)
    # Stock N1 and N2 regenerated for *each* graph seed; same seed means same partition.
    build_arm(state,out,exe,cpu,'stock_N1',seed,1)
    build_arm(state,out,exe,cpu,'stock_N2',seed,2)
    targets={}
    for tag,q in QS.items():
        for selector in ('low','high'):
            name=f'{selector}_{tag}'
            b=build_arm(state,out,exe,cpu,name,seed,2,'selector',selector,q)
            targets[name]=b['coverage']['wl_kept']
    # Fail closed: changing only mode should preserve historical graph for seed=555.
    if seed==555:
        p32=old['builds'];older={z['arm']:z['graph_sha256'] for z in p32}
        for name,sha_expected in KNOWN_STOCK.items():
            got=next(b['graph_sha'] for b in state['builds'] if b['arm']==name)
            ck(got==sha_expected,'SEED555_PARITY_'+name)
        for name in targets:
            got=next(b['graph_sha'] for b in state['builds'] if b['arm']==name)
            ck(got==older[name],'SEED555_PARITY_'+name)
        print('R90_P33_ORIGINAL_555_GRAPH_SHA_EQUIVALENCE_PASS',flush=True)
    # Budget-matched random-leaf selection. Independent random seeds per budget.
    for tag,q in QS.items():
        for ref in ('low','high'):
            refname=f'{ref}_{tag}'
            for j in range(random_reps):
                leafseed=2026111701+100*seed+17*(tag=='q2')+j
                name=f'rleaf_{ref}_{tag}_r{j+1}'
                b=build_arm(state,out,exe,cpu,name,seed,2,'budget','low',q,targets[refname],leafseed)
                c=b['coverage'];parent=next(z for z in state['builds'] if z['arm']==refname)['coverage']
                ck(c['wl_total']==parent['wl_total'],'WLTOTAL_PAIR_'+name)
                ck(c['wl_kept']-targets[refname]<=c['budget']['maxleaf'],'BUDGET_MATCH_'+name)
                print('R90_P33_MATCHED_WL_PASS',name,'target',targets[refname],'actual',c['wl_kept'],flush=True)
    # Sweep the same frozen query set, evaluator and beams. Search logs immutable.
    for b in state['builds']:
        name=b['arm'];f=out/'logs'/f'{name}.sweep.stdout'
        print('R90_P33_SWEEP_START',name,flush=True)
        run(['taskset','-c',cpu,EVAL,b['graph'],BASE,QUERY,GT,','.join(map(str,BEAMS))],f,timeout=2400,
            e=environment(seed))
        rows=parse_eval(f.read_text(errors='replace'),BEAMS)
        ck(all(a['recall']<=v['recall']+1e-6 for a,v in zip(rows,rows[1:])),'NONMONOTONE_'+name)
        crossing={str(t):bracket(rows,t) for t in TARGETS}
        state['sweeps'].append(dict(arm=name,log=str(f),sha=sha(f),rows=rows,brackets=crossing))
        store(out/'progress.json',state)
        print('R90_P33_SWEEP_PASS',name,crossing,flush=True)
    bs={x['arm']:x['brackets'] for x in state['sweeps']}
    for rep in range(1,search_reps+1):
        order=list(state['builds'])
        if rep%2==0:order.reverse()
        else: order=order[(rep-1)%len(order):]+order[:(rep-1)%len(order)]
        for b in order:
            name=b['arm'];br=[x for x in bs[name].values() if x is not None]
            if not br:continue
            beams=sorted({int(x[z]) for x in br for z in ('b0','b1')})
            log=out/'logs'/f'{name}.repeat{rep}.stdout'
            run(['taskset','-c',cpu,EVAL,b['graph'],BASE,QUERY,GT,','.join(map(str,beams))],log,timeout=1800,e=environment(seed))
            rows=parse_eval(log.read_text(errors='replace'),beams)
            base={x['beam']:x for x in next(s for s in state['sweeps'] if s['arm']==name)['rows']}
            ck(all(abs(r['recall']-base[r['beam']]['recall'])<2e-6 for r in rows),'REPEAT_RECALL_'+name)
            state['repeats'].append(dict(arm=name,rep=rep,beams=beams,log=str(log),sha=sha(log),rows=rows))
            store(out/'progress.json',state)
            print('R90_P33_REPEAT_PASS',name,rep,flush=True)
    for b in state['builds']:
        name=b['arm'];cur=bs[name]
        for t in TARGETS:
            x=cur[str(t)]
            if x is None:
                row=dict(arm=name,seed=seed,target=t,status='NO_CROSSING_IN_SWEEP');state['summary'].append(row);continue
            rs=[z for z in state['repeats'] if z['arm']==name];ck(len(rs)==search_reps,'REPEAT_N_'+name)
            med={v:statistics.median(next(r['qps'] for r in z['rows'] if r['beam']==v) for z in rs) for v in (x['b0'],x['b1'])}
            qps=1e6/((1-x['t'])*1e6/med[x['b0']]+x['t']*1e6/med[x['b1']])
            row=dict(arm=name,seed=seed,target=t,status='INTERPOLATED_PILOT',build_s=b['wall_s'],
                     qps_latency_interp=qps,beam_bracket=[x['b0'],x['b1']],recall_bracket=[x['r0'],x['r1']],
                     median_endpoint_qps=med,avg_cmps_endpoints={v:statistics.median(next(r['avg_cmps'] for r in z['rows'] if r['beam']==v) for z in rs) for v in (x['b0'],x['b1'])},
                     avg_visited_endpoints={v:statistics.median(next(r['avg_visited'] for r in z['rows'] if r['beam']==v) for z in rs) for v in (x['b0'],x['b1'])},
                     wl_kept=None if b['coverage'] is None else b['coverage']['wl_kept'],
                     wl_total=None if b['coverage'] is None else b['coverage']['wl_total'])
            state['summary'].append(row)
            print('R90_P33_INTERP',json.dumps(row,sort_keys=True),flush=True)
    state['status']='COMPLETE';store(out/'result_manifest.json',state)
    audit(out,seed,cpu)
    print('R90_P33_PILOT_COMPLETE_ONE_GRAPH_SEED_NO_PAPER_CLAIMS',flush=True)

def audit(out,seed,cpu):
    preflight(out,seed,cpu,False)
    m=load(out/'result_manifest.json')
    ck(m['status']=='COMPLETE' and m['seed']==seed,'MANIFEST_SEED_STATUS')
    ck(sha(Path(__file__).resolve())==m['script_sha'],'SCRIPT_SHA')
    h=out/'source/algorithms/PipNN/pipnn.h';exe=out/'build/algorithms/PipNN/neighbors-pipnn_FLOAT_T_EUCLIDEAN'
    ck(sha(h)==m['source_sha'] and sha(exe)==m['elf_sha'],'BUILD_SOURCE_ELF_SHA')
    ck(len(m['builds'])==6+4*m['random_reps'],'COUNT_BUILDS')
    ck(len(m['sweeps'])==len(m['builds']),'COUNT_SWEEPS')
    ck(len(m['summary'])==len(m['builds'])*len(TARGETS),'COUNT_TARGETS')
    for b in m['builds']:
        ck(sha(graph(b['graph']))==b['graph_sha'],'GRAPH_SHA_'+b['arm'])
        ck(sha(b['stdout'])==b['stdout_sha'] and sha(b['timefile'])==b['time_sha'],'BUILD_LOG_SHA_'+b['arm'])
        ck(cov(Path(b['stdout']).read_text(errors='replace'),b['policy'],str(b['fraction']))==b['coverage'],'BUILD_PARSE_'+b['arm'])
    for typ in ('sweeps','repeats'):
        for x in m[typ]:
            ck(sha(x['log'])==x['sha'],'SEARCH_LOG_SHA_'+x['arm'])
            ck(parse_eval(Path(x['log']).read_text(errors='replace'),BEAMS if typ=='sweeps' else x['beams'])==x['rows'],'SEARCH_PARSE_'+x['arm'])
    n=sum(any(v is not None for v in s['brackets'].values()) for s in m['sweeps'])
    ck(len(m['repeats'])==n*m['search_reps'],'REPEAT_COUNT')
    print('R90_P33_AUDIT_ALL_SOURCE_ELF_GRAPH_BUILD_AND_SEARCH_SHA_PASS',flush=True)

def selftest():
    fake='\n'.join((A_SETUP,A_SELECT_START,A_SORT,A_SELECT_END,A_LEAF_COUNTER,A_ELIG,A_SEED))
    x=patch(fake)
    ck('R90_P33_BUDGET target=' in x and 'r90_p33_selector == "high"' in x,'PATCH_TEST')
    try:patch(x)
    except RuntimeError:pass
    else:ck(False,'PATCH_NONIDEMPOTENT')
    cost='R90_A5_PASS1 selected=1000 n=100000 sort_comparisons=120000 GT_free=1\nR90_A5_LEAF_SCREEN total=8000 eligible=4000 WL_total=100000 WL_eligible=70000 gate=1\n'
    ck(cov(cost,'selector','.01')['wl_kept']==70000,'COV_TEST')
    c='R90_A5_PASS1 selected=0 n=100000 sort_comparisons=0 GT_free=1\nR90_P33_BUDGET target=70000 achieved=70010 max_leaf=100 seed=33\nR90_A5_LEAF_SCREEN total=8000 eligible=4000 WL_total=100000 WL_eligible=70010 gate=1\n'
    ck(cov(c,'budget','.01')['budget']['target']==70000,'BUDGET_TEST')
    r=[dict(beam=64,recall=.985,qps=15000),dict(beam=72,recall=.995,qps=13000)]
    ck(abs(bracket(r,.99)['t']-.5)<1e-9,'BRACKET_TEST')
    ck(bracket(r,.998) is None,'NO_CROSSING_TEST')
    print('R90_P33_SELFTEST_PASS_EXACT_SOURCE_PATCH_BUDGET_AND_SEARCH_CONTRACT',flush=True)

def aggregate():
    """Paired, exploratory 3 graph-seed aggregation; no re-search or BUILD."""
    manifests={}
    for seed in (555,556,557):
        path=R90/f'r90_p33_budget_leaf_seed{seed}_v1/result_manifest.json'
        m=load(path)
        ck(m['status']=='COMPLETE' and m['seed']==seed,'AGG_SEED_'+str(seed))
        ck(m['script_sha']==sha(Path(__file__).resolve()),'AGG_SCRIPT_CHANGED_'+str(seed))
        ck(m['random_reps']>=2,'AGG_REQUIRES_2_RANDOM_LEAF_REPS_'+str(seed))
        manifests[seed]=m
    print('R90_P33_AGG_PAIRED_THREE_GRAPH_SEEDS_INPUT_PASS',flush=True)
    results=[]
    for tag in QS:
        for selector in ('low','high'):
            arm=f'{selector}_{tag}'
            for target in TARGETS:
                diffs=[]; seed_rows=[]
                for seed,m in manifests.items():
                    rows={z['arm']:z for z in m['summary'] if z['target']==target}
                    ck(arm in rows and rows[arm]['status']=='INTERPOLATED_PILOT','AGG_NO_SELECTOR_'+arm)
                    sel=rows[arm]
                    randoms=[z for k,z in rows.items() if k.startswith(f'rleaf_{selector}_{tag}_r')]
                    ck(len(randoms)==m['random_reps'] and all(z['status']=='INTERPOLATED_PILOT' for z in randoms),
                       'AGG_NO_RANDOM_'+arm)
                    rnd=statistics.mean(z['qps_latency_interp'] for z in randoms)
                    delta_pct=100*(sel['qps_latency_interp']/rnd-1)
                    diff_wl=[(z['wl_kept']-sel['wl_kept'])/sel['wl_total']*100 for z in randoms]
                    ck(all(0<=d<=0.2 for d in diff_wl),'AGG_BAD_WL_MATCH_'+arm)
                    diffs.append(delta_pct)
                    seed_rows.append(dict(seed=seed,selector_qps=sel['qps_latency_interp'],
                                          random_qps_mean=rnd,delta_pct=delta_pct,random_wl_excess_pp=diff_wl))
                sd=statistics.stdev(diffs)
                mean=statistics.mean(diffs)
                # Preregistered exploratory screening rule (NOT a statistical significance test).
                go=mean>0 and mean>2*sd and all(d>0 for d in diffs)
                entry=dict(selector=selector,q=tag,target=target,paired_deltas_pct=diffs,
                           mean_delta_pct=mean,sd_three_seeds_pct=sd,rows=seed_rows,
                           prereg_screen='GO' if go else 'HOLD',
                           limitations='3 seeds cannot establish reliable statistical significance; QPS interpolated')
                results.append(entry)
                print('R90_P33_AGG_ROW',json.dumps(entry,sort_keys=True),flush=True)
    out=R90/'r90_p33_paired_three_seed_aggregate_v1.json'
    ck(not out.exists() and not out.is_symlink(),'AGG_EXISTS')
    store(out,dict(status='EXPLORATORY_ONLY',randomized_baseline='uniform_random_leaf_order_matched_WL',
                   seeds=[555,556,557],results=results,
                   decision='Proceed only if high beats randomized leaf controls; preserve hold for RADAR kernel'))
    print('R90_P33_AGG_COMPLETE',out,flush=True)

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('phase',choices=('selftest','preflight','pilot','audit','aggregate'))
    ap.add_argument('--seed',type=int,default=555,choices=(555,556,557))
    ap.add_argument('--cpu',type=int,default=0)
    ap.add_argument('--random-reps',type=int,default=1,choices=(1,2,3))
    ap.add_argument('--search-reps',type=int,default=3,choices=(3,5))
    ap.add_argument('--out',type=Path)
    a=ap.parse_args()
    out=(a.out or R90/f'r90_p33_budget_leaf_seed{a.seed}_v1').expanduser().resolve(strict=False)
    if a.phase=='aggregate':aggregate()
    elif a.phase=='selftest':selftest()
    elif a.phase=='preflight':preflight(out,a.seed,a.cpu,True)
    elif a.phase=='pilot':pilot(out,a.seed,a.cpu,a.random_reps,a.search_reps)
    else:audit(out,a.seed,a.cpu)

if __name__=='__main__':
    try:main()
    except Exception as e:
        print('R90_P33_HOLD',type(e).__name__,str(e),file=sys.stderr,flush=True)
        sys.exit(2)
