#!/usr/bin/env python3
"""R90-D6: source-pinned, instrumented Top-2 BUILD work counters (H17 vs Fast v2).

Only independent diagnostic source copies. Never modifies the frozen H17/P3.8
source, production ELFs or historical timing/graph evidence. Counts *executed*
Top-2 operations with a local per-leaf struct; relax-atomic aggregate once/leaf.
No measured time from this instrumented build may be cited as a speed benchmark.

Phases: selftest, preflight, pilot10k, audit10k, pilot100k, audit100k,
        pilot1m, audit1m.
"""
from __future__ import annotations
import argparse, csv, hashlib, importlib.util, json, os, re, shutil, struct, subprocess, sys
from pathlib import Path

H=Path.home(); ROOT=H/'ann-task-a'; R90=ROOT/'experiments/R90'
P38_ROOT=R90/'r90_p38_h17_top2_prefilter_native_v2'
P38_SCRIPT=H/'Downloads/r90_p38_h17_top2_prefilter_native_v2.py'
P38_SHA='6d4c8728fc7a4df449c2ffb68b6471c516270fd91b11fb7e18240c3e7a911515'
OUT=R90/'r90_d6_h17_fastv2_top2_exact_counters_v1'
DATA={10000:P38_ROOT/'data/sift10k.fbin',100000:ROOT/'data/sift100k.fbin',
      1000000:ROOT/'data/sift1m.fbin'}
DATA_SHA={100000:'e50ff1bc34bcc6d1c97dd001023c09a666971cde64605cc06671ed8a8ff1ed12',
          1000000:'8c7b3d999ba3133f865af72df078f77c2d248fdb80571d7ea1f1bb8e1750658e'}
EXPECTED_GRAPH={10000:'59dd18da46ebb88604de4aa0d253df36b65ca5965de80af2f616d5f119a637a9',
                100000:'8e42cae1fd72ceb2dd626a69cdffdc53604636c1debf84c887b52de6e8a1cc0e',
                1000000:'149711956a3c738bd183f7f78a5a269df4584caf99fc889d4fc08e8415d5cd8e'}
H17_UTILS_SHA='b4a7e39a1ddf6c9f41f136360773aa9aef50ae7d19921b0b49b6422408c4c520'
PRODUCTION_ELF_SHA={
 'ctrl':'92c22ad5d9d9022860725329ff097784e7c8a649460d03dd343cdb6adb90363e',
 'fast':'ab4a0c678b3a71b2896d6f4d4339131705a1758b0c5398ed8ac32dd656cd7e91'}
FIELDS=(
 'leaf_calls','leaf_point_visits','lower_triangle_pairs_theoretical',
 'candidates','fp32_checks','early_rejects','pack_calls',
 'packed_first_checks','packed_second_checks','first_branch_hits',
 'second_branch_hits','first_assignments','second_assignments',
 'cutoff_assignments','count_increments')


def ck(ok,code):
    if not ok: raise RuntimeError('R90_D6_HOLD_'+str(code))

def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as fd:
        for chunk in iter(lambda:fd.read(4<<20),b''): h.update(chunk)
    return h.hexdigest()

def ownsha(): return sha(Path(__file__).resolve())

def load_p38():
    ck(P38_SCRIPT.is_file() and not P38_SCRIPT.is_symlink() and sha(P38_SCRIPT)==P38_SHA,
       'P38_SCRIPT_SHA')
    spec=importlib.util.spec_from_file_location('r90_d6_frozen_p38',str(P38_SCRIPT))
    ck(spec is not None and spec.loader is not None,'P38_MODULE_SPEC')
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    return mod


def prior(p38,full=False):
    original=P38_ROOT/'result_manifest_1m.json'
    ck(original.is_file() and not original.is_symlink(),'P38_1M_MANIFEST_MISSING')
    st=json.loads(original.read_text())
    ck(st.get('status')=='PASS_1M_3PAIRS' and len(st.get('runs',[]))==14,'P38_MANIFEST_STATE')
    ck(st.get('script_sha')==P38_SHA,'P38_MANIFEST_SCRIPT_SHA')
    ck(st.get('source',{}).get('source_hashes',{}).get('algorithms/PipNN/pipnn_utils.h')==H17_UTILS_SHA,
       'FROZEN_H17_PIN')
    for arm in ('ctrl','fast'):
        f=P38_ROOT/'build'/arm/'algorithms/PipNN/neighbors-pipnn_FLOAT_T_EUCLIDEAN'
        ck(f.is_file() and sha(f)==PRODUCTION_ELF_SHA[arm] and st['elf_sha'][arm]==PRODUCTION_ELF_SHA[arm],
           'PRODUCTION_ELF_DRIFT_'+arm)
        ck(p38.source_hashes(P38_ROOT/'source'/arm)==st['arm_source'][arm],
           'PRODUCTION_SOURCE_DRIFT_'+arm)
    ck(sha(P38_ROOT/'data/sift10k.fbin')==st.get('prefix_sha'),'10K_FROZEN_PREFIX')
    ck(DATA[100000].is_file() and sha(DATA[100000])==DATA_SHA[100000],'SIFT100K_SHA')
    ck(0 in os.sched_getaffinity(0),'CPU0_NOT_ALLOWED')
    if full:
        ck(DATA[1000000].is_file() and DATA[1000000].stat().st_size==512000008
           and sha(DATA[1000000])==DATA_SHA[1000000],'SIFT1M_DATA_SHA')
    # Validate cached dependency source snapshots used by the previous native compilation.
    for dep,(p,commit) in p38.DEPS.items():
        ck(p.is_dir() and (p/'CMakeLists.txt').is_file(),'DEP_MISSING_'+dep)
        if (p/'.git').exists():
            proc=subprocess.run(['git','-C',str(p),'rev-parse','HEAD'],capture_output=True,text=True)
            ck(proc.returncode==0 and proc.stdout.strip()==commit,'DEP_COMMIT_'+dep)
    return st

COUNTER_DECL='''
// R90-D6 separate diagnostic counters: EXACT executed Top2 selection operations.
// Per-leaf hot-path increments are thread-local stack fields; atomics occur ONCE per leaf.
struct R90D6Local {
  uint64_t leaf_calls=0, leaf_point_visits=0, lower_triangle_pairs_theoretical=0;
  uint64_t candidates=0, fp32_checks=0, early_rejects=0, pack_calls=0;
  uint64_t packed_first_checks=0, packed_second_checks=0;
  uint64_t first_branch_hits=0, second_branch_hits=0;
  uint64_t first_assignments=0, second_assignments=0, cutoff_assignments=0;
  uint64_t count_increments=0;
};
struct R90D6Global {
  std::atomic<uint64_t> leaf_calls{0}, leaf_point_visits{0}, lower_triangle_pairs_theoretical{0};
  std::atomic<uint64_t> candidates{0}, fp32_checks{0}, early_rejects{0}, pack_calls{0};
  std::atomic<uint64_t> packed_first_checks{0}, packed_second_checks{0};
  std::atomic<uint64_t> first_branch_hits{0}, second_branch_hits{0};
  std::atomic<uint64_t> first_assignments{0}, second_assignments{0}, cutoff_assignments{0};
  std::atomic<uint64_t> count_increments{0};
};
R90D6Global r90_d6_global;
inline void r90_d6_merge(const R90D6Local &c) {
  #define R90_D6_SUM(field) r90_d6_global.field.fetch_add(c.field,std::memory_order_relaxed)
  R90_D6_SUM(leaf_calls); R90_D6_SUM(leaf_point_visits); R90_D6_SUM(lower_triangle_pairs_theoretical);
  R90_D6_SUM(candidates); R90_D6_SUM(fp32_checks); R90_D6_SUM(early_rejects); R90_D6_SUM(pack_calls);
  R90_D6_SUM(packed_first_checks); R90_D6_SUM(packed_second_checks);
  R90_D6_SUM(first_branch_hits); R90_D6_SUM(second_branch_hits);
  R90_D6_SUM(first_assignments); R90_D6_SUM(second_assignments); R90_D6_SUM(cutoff_assignments);
  R90_D6_SUM(count_increments);
  #undef R90_D6_SUM
}
inline void r90_d6_report(const char *arm) {
  std::cout << "R90_D6_WORK arm=" << arm;
  #define R90_D6_PRINT(field) std::cout << " " #field "=" << r90_d6_global.field.load(std::memory_order_relaxed)
  R90_D6_PRINT(leaf_calls); R90_D6_PRINT(leaf_point_visits);
  R90_D6_PRINT(lower_triangle_pairs_theoretical); R90_D6_PRINT(candidates);
  R90_D6_PRINT(fp32_checks); R90_D6_PRINT(early_rejects); R90_D6_PRINT(pack_calls);
  R90_D6_PRINT(packed_first_checks); R90_D6_PRINT(packed_second_checks);
  R90_D6_PRINT(first_branch_hits); R90_D6_PRINT(second_branch_hits);
  R90_D6_PRINT(first_assignments); R90_D6_PRINT(second_assignments);
  R90_D6_PRINT(cutoff_assignments); R90_D6_PRINT(count_increments);
  #undef R90_D6_PRINT
  std::cout << std::endl;
}
// R90-D6 ends.
'''


def selection_snippet(arm):
    x=['        float dist_ij = (i < j) ? dist_mat[j * N + i] : dist_mat[i * N + j];']
    if arm=='fast':
        x+=['        if (count == 2) {',
            '          ++r90_d6_local.fp32_checks;',
            '          if (dist_ij > r90_second_cutoff) {',
            '            ++r90_d6_local.early_rejects;',
            '            continue;',
            '          }',
            '        }']
    x+=['        ++r90_d6_local.pack_calls;',
        '        double d = packFloatAndInt(dist_ij, j);',
        '        if (count != 0) ++r90_d6_local.packed_first_checks;',
        '        if (count == 0 || d < first) {',
        '          ++r90_d6_local.first_branch_hits;',
        '          second = first;',
        '          ++r90_d6_local.second_assignments;',
        '          first = d;',
        '          ++r90_d6_local.first_assignments;']
    if arm=='fast':x+=['          r90_second_cutoff = static_cast<float>(second);',
                        '          ++r90_d6_local.cutoff_assignments;']
    x+=['        } else {',
        '          if (count != 1) ++r90_d6_local.packed_second_checks;',
        '          if (count == 1 || d < second) {',
        '            ++r90_d6_local.second_branch_hits;',
        '            second = d;',
        '            ++r90_d6_local.second_assignments;']
    if arm=='fast':x+=['            r90_second_cutoff = static_cast<float>(second);',
                        '            ++r90_d6_local.cutoff_assignments;']
    x+=['          }',
        '        }',
        '        if (count < 2) {',
        '          ++count;',
        '          ++r90_d6_local.count_increments;',
        '        }']
    return '\n'.join(x)


def patch_utils(text,p38,arm):
    ck(arm in ('ctrl','fast'),'ARM')
    ck(text.count('std::atomic<size_t> dist_traversed(0);')==1,'GLOBAL_COUNTER_ANCHOR')
    ck('R90D6Global' not in text,'DUPLICATE_DIAGNOSTIC')
    text=text.replace('std::atomic<size_t> dist_traversed(0);',COUNTER_DECL+'\nstd::atomic<size_t> dist_traversed(0);',1)
    b=text.index(p38.H17_BEGIN)
    e=text.index(p38.H17_END,b)
    segment=text[b:e]
    old=p38.SELECT_OLD if arm=='ctrl' else p38.SELECT_NEW
    ck(segment.count(old)==1,'SELECTION_ANCHOR_'+arm)
    ck(segment.count('        if (i == j) continue;')==1,'SELF_EXCLUSION_ANCHOR')
    ck(segment.count('  if (MST_DEG == 2) {')==1,'MST_DEG2_ANCHOR')
    segment=segment.replace('  if (MST_DEG == 2) {',
      '  if (MST_DEG == 2) {\n    R90D6Local r90_d6_local;\n'
      '    r90_d6_local.leaf_calls = 1;\n'
      '    r90_d6_local.leaf_point_visits = N;\n'
      '    r90_d6_local.lower_triangle_pairs_theoretical = N > 0 ? N * (N - 1) / 2 : 0;',1)
    segment=segment.replace('        if (i == j) continue;',
      '        if (i == j) continue;\n        ++r90_d6_local.candidates;',1)
    segment=segment.replace(old,selection_snippet(arm),1)
    # Exactly one merge AFTER ALL N selection rows, before fallback MST_DEG!=2.
    segment=segment.rstrip()+'\n    r90_d6_merge(r90_d6_local);\n'
    text=text[:b]+segment+text[e:]
    ck(text.count('r90_d6_merge(r90_d6_local);')==1,'MERGE_COUNT')
    ck(text.count('r90_d6_local.candidates')==1,'CANDIDATES_COUNT')
    ck(text.count('VQPartialSort(')>=1,'HIGHWAY_FALLBACK_PRESENT')
    return text


def patch_main(text,arm):
    anchor='    C.multiple_clustertrees(graph_h, Points, cluster_size, cluster_rounds);'
    ck(text.count(anchor)==1,'REPORT_ANCHOR_COUNT')
    ck('r90_d6_report' not in text,'ALREADY_PATCHED_MAIN')
    return text.replace(anchor,anchor+'\n    r90_d6_report("'+arm+'");',1)


def runproc(args,log,timeout=3600,env=None):
    ck(not log.exists() and not log.is_symlink(),'LOG_EXISTS_'+log.name)
    with log.open('x',encoding='utf-8') as fd:
        p=subprocess.run(list(map(str,args)),stdout=fd,stderr=subprocess.STDOUT,
                         timeout=timeout,env=env,check=False)
    ck(p.returncode==0,'SUBPROCESS_'+log.name+'_'+str(p.returncode))


def compile_one(arm,p38):
    src=OUT/'source'/arm;build=OUT/'build'/arm
    opts=['cmake','-S',src,'-B',build,'-DCMAKE_BUILD_TYPE=Release',
          '-DCMAKE_CXX_FLAGS=-O3 -pthread','-DCMAKE_EXPORT_COMPILE_COMMANDS=ON',
          '-DFETCHCONTENT_FULLY_DISCONNECTED=ON']
    for key,(path,_) in p38.DEPS.items():opts.append('-DFETCHCONTENT_SOURCE_DIR_'+key+'='+str(path))
    runproc(opts,OUT/'logs'/f'cmake_{arm}.stdout',1800)
    runproc(['cmake','--build',build,'--target','neighbors-pipnn_FLOAT_T_EUCLIDEAN','--parallel','2'],
            OUT/'logs'/f'compile_{arm}.stdout',3600)
    elf=build/'algorithms/PipNN/neighbors-pipnn_FLOAT_T_EUCLIDEAN'
    ck(elf.is_file() and os.access(elf,os.X_OK),'ELF_MISSING_'+arm)
    return sha(elf)


def parse_counter_log(path,arm):
    lines=[ln for ln in path.read_text(errors='replace').splitlines()
           if ln.startswith('R90_D6_WORK ')]
    ck(len(lines)==1,'WORK_REPORT_COUNT_'+arm)
    parts=lines[0].split()[1:]
    row={}
    for p in parts:
        ck(p.count('=')==1,'WORK_TOKEN')
        key,v=p.split('=',1)
        ck(key not in row,'DUP_WORK_KEY')
        row[key]=v if key=='arm' else int(v)
    ck(row.pop('arm',None)==arm,'WORK_ARM')
    ck(set(row)==set(FIELDS),'WORK_KEYS_'+str(sorted(set(row)^set(FIELDS))))
    ck(row['leaf_calls']>0 and row['candidates']>0,'NO_LEAF_WORK')
    ck(row['candidates']==2*row['lower_triangle_pairs_theoretical'],'PAIR_CONSERVATION')
    ck(row['candidates']==row['pack_calls']+row['early_rejects'],'PACK_REJECT_CONSERVATION')
    ck(row['packed_first_checks']+row['packed_second_checks']<=2*row['pack_calls'],
       'PACKED_COMPARISONS_UPPER_BOUND')
    ck(row['first_assignments']==row['first_branch_hits'],'FIRST_ASSIGNS')
    ck(row['second_assignments']==row['first_branch_hits']+row['second_branch_hits'],
       'SECOND_ASSIGNS')
    ck(row['count_increments']<=2*row['leaf_point_visits'],'COUNT_INCREMENT_UPPER_BOUND')
    if arm=='ctrl':
        ck(row['early_rejects']==row['fp32_checks']==row['cutoff_assignments']==0,
           'CTRL_EXTRA_WORK')
        ck(row['pack_calls']==row['candidates'],'CTRL_PACK_EVERY_CANDIDATE')
    else:
        ck(row['fp32_checks']>=row['early_rejects'] and row['fp32_checks']<=row['candidates'],
           'FAST_FP32_REJECT_BOUNDS')
        ck(row['cutoff_assignments']==row['first_branch_hits']+row['second_branch_hits'],
           'FAST_CUTOFF_ASSIGNS')
    row['packed_comparisons']=row['packed_first_checks']+row['packed_second_checks']
    row['value_comparisons']=row['fp32_checks']+row['packed_comparisons']
    row['top2_value_assignments']=row['first_assignments']+row['second_assignments']+row['cutoff_assignments']
    return row


def graph_check(path,n):
    ck(path.is_file() and path.stat().st_size>8+4*n,'GRAPH_SIZE')
    with path.open('rb') as fd:
        ck(fd.read(8)==struct.pack('<II',n,64),'GRAPH_HEADER')
    return sha(path)


def json_write(path,obj):
    temp=Path(str(path)+'.part')
    ck(not temp.exists() and not temp.is_symlink(),'JSON_PART_EXISTS')
    with temp.open('x',encoding='utf-8') as fd:json.dump(obj,fd,indent=2,sort_keys=True);fd.write('\n')
    os.replace(temp,path)


def bcmd(elf,base,graph):
    return [str(elf),'-base_path',str(base),'-graph_outfile',str(graph),
            '-num_clusters','2','-cluster_size','1024','-table_size','160',
            '-top_level_leaders','100','-fanout_scheme','10,3,1','-mst_deg','2',
            '-prune','1','-prune_all','1','-prune_degree','64',
            '-hash_bits','12','-alpha','1.1','-k','0']


def diagnostic_build(arm,n):
    name=f'{n}_{arm}_r1'
    elf=OUT/'build'/arm/'algorithms/PipNN/neighbors-pipnn_FLOAT_T_EUCLIDEAN'
    graph=OUT/'graphs'/(name+'.graph')
    stdout=OUT/'logs'/(name+'.stdout')
    timefile=OUT/'logs'/(name+'.time')
    ck(not any(p.exists() or p.is_symlink() for p in (graph,stdout,timefile)),
       'BUILD_OUTPUT_EXISTS_'+name)
    env=os.environ.copy();env.update({'LC_ALL':'C','PARLAY_NUM_THREADS':'1','OMP_NUM_THREADS':'1'})
    print('R90_D6_BUILD_START',name,'1CPU0 INSTRUMENTED_NOT_TIMED_BENCHMARK',flush=True)
    runproc(['/usr/bin/time','-v','-o',timefile,'taskset','-c','0',
             *bcmd(elf,DATA[n],graph)],stdout,3600,env)
    result={'n':n,'arm':arm,'graph':str(graph),'graph_sha':graph_check(graph,n),
            'stdout':str(stdout),'stdout_sha':sha(stdout),'timefile':str(timefile),
            'timefile_sha':sha(timefile),'counts':parse_counter_log(stdout,arm)}
    print('R90_D6_BUILD_PASS',name,'candidate',result['counts']['candidates'],
          'pack',result['counts']['pack_calls'],'rejects',result['counts']['early_rejects'],
          'fp32_checks',result['counts']['fp32_checks'],
          'packed_checks',result['counts']['packed_comparisons'],
          'graph_sha',result['graph_sha'],flush=True)
    return result


def certify(st,n):
    assert set(st['source_hashes'])=={'ctrl','fast'}
    ck(st['script_sha']==ownsha(),'RUNNER_SHA_DRIFT')
    ck(st['p38_script_sha']==P38_SHA,'P38_SHA_STATE')
    p38=load_p38()
    prior(p38,full=(n==1000000))
    ck(sha(P38_ROOT/'result_manifest_1m.json')==st['frozen_manifest_sha'],
       'FROZEN_MANIFEST_SHA_DRIFT')
    for arm in ('ctrl','fast'):
        ck(p38.source_hashes(OUT/'source'/arm)==st['source_hashes'][arm],
           'DIAGNOSTIC_SOURCE_DRIFT_'+arm)
        elf=OUT/'build'/arm/'algorithms/PipNN/neighbors-pipnn_FLOAT_T_EUCLIDEAN'
        ck(elf.is_file() and sha(elf)==st['diagnostic_elf_sha'][arm],
           'DIAGNOSTIC_ELF_DRIFT_'+arm)
    if n>=100000:
        ck(sha(DATA[100000])==DATA_SHA[100000],'BASE100K_DRIFT')
    if n>=1000000:ck(sha(DATA[1000000])==DATA_SHA[1000000],'BASE1M_DRIFT')
    ck(sha(DATA[10000])==st['data_10k_sha'],'BASE10K_DRIFT')
    for r in st['runs']:
        ck(r['graph_sha']==sha(r['graph']),'GRAPH_SHA_DRIFT')
        ck(r['stdout_sha']==sha(r['stdout']),'STDOUT_SHA_DRIFT')
        ck(r['timefile_sha']==sha(r['timefile']),'RUSAGE_SHA_DRIFT')
        ck(r['counts']==parse_counter_log(Path(r['stdout']),r['arm']),'COUNTER_LOG_DRIFT')
        ck(r['graph_sha']==EXPECTED_GRAPH[r['n']],
           'FROZEN_1CPU_GRAPH_PARITY_'+str(r['n'])+'_'+r['arm'])
    for size in sorted({r['n'] for r in st['runs']}):
        aa=[r for r in st['runs'] if r['n']==size]
        ck(len(aa)==2 and {r['arm'] for r in aa}=={'ctrl','fast'},'PAIR_INCOMPLETE_'+str(size))
        ca=next(r for r in aa if r['arm']=='ctrl')['counts']
        fa=next(r for r in aa if r['arm']=='fast')['counts']
        ck(ca['candidates']==fa['candidates'],'WORK_CANDIDATES_DIFFER_'+str(size))
        ck(ca['leaf_calls']==fa['leaf_calls'],'WORK_LEAF_COUNT_DIFFER_'+str(size))
        ck(ca['first_branch_hits']==fa['first_branch_hits'] and
           ca['second_branch_hits']==fa['second_branch_hits'],
           'TOP2_SELECTION_DIVERGED_'+str(size))
    print('R90_D6_AUDIT_NATIVE_GRAPHS_COUNTERS_BINARY_SOURCE_SHA_PASS',
          'sizes',sorted({r['n'] for r in st['runs']}),flush=True)


def summary(st):
    out=[]
    for n in sorted({r['n'] for r in st['runs']}):
        c=next(r['counts'] for r in st['runs'] if r['n']==n and r['arm']=='ctrl')
        f=next(r['counts'] for r in st['runs'] if r['n']==n and r['arm']=='fast')
        saved=100*f['early_rejects']/f['candidates']
        out.append({'n':n,'candidate_scans':f['candidates'],
                    'leaf_calls':f['leaf_calls'],
                    'ctrl_pack_calls':c['pack_calls'],'fast_pack_calls':f['pack_calls'],
                    'fast_early_rejects':f['early_rejects'],
                    'pack_calls_reduced_pct':saved,
                    'ctrl_fp32_checks':c['fp32_checks'],'fast_fp32_checks':f['fp32_checks'],
                    'ctrl_packed_comparisons':c['packed_comparisons'],
                    'fast_packed_comparisons':f['packed_comparisons'],
                    'ctrl_value_comparisons':c['value_comparisons'],
                    'fast_value_comparisons':f['value_comparisons'],
                    'ctrl_first_assignments':c['first_assignments'],
                    'fast_first_assignments':f['first_assignments'],
                    'ctrl_second_assignments':c['second_assignments'],
                    'fast_second_assignments':f['second_assignments'],
                    'fast_cutoff_assignments':f['cutoff_assignments'],
                    'ctrl_top2_value_assignments':c['top2_value_assignments'],
                    'fast_top2_value_assignments':f['top2_value_assignments'],
                    'note':'Program-level executed counts; lower_triangle_pairs_theoretical is analytical leaf work proxy, not measured GEMM flops.'})
    return out


def csv_write(path,rows):
    keys=list(rows[0])
    with path.open('x',newline='',encoding='utf-8') as fd:
        writer=csv.DictWriter(fd,fieldnames=keys)
        writer.writeheader();writer.writerows(rows)


def csv_check(path,rows):
    ck(path.is_file(),'COUNTER_CSV_MISSING')
    with path.open(newline='',encoding='utf-8') as fd:
        actual=list(csv.DictReader(fd))
    ck(len(actual)==len(rows),'COUNTER_CSV_ROW_COUNT')
    for row,exp in zip(actual,rows):
        ck(set(row)==set(exp) and all(str(row[k])==str(v) for k,v in exp.items()),
           'COUNTER_CSV_CONTENT')


def preflight():
    p38=load_p38(); st=prior(p38)
    ck(not OUT.exists() and not OUT.is_symlink(),'OUT_EXISTS')
    # Exactly once assert our code rewrites both frozen original selection snippets.
    for arm in ('ctrl','fast'):
        a=(P38_ROOT/'source'/arm/'algorithms/PipNN/pipnn_utils.h').read_text()
        b=(P38_ROOT/'source'/arm/'algorithms/PipNN/pipnn.h').read_text()
        ck(a!=patch_utils(a,p38,arm) and b!=patch_main(b,arm),'PATCH_NO_DIFF')
    print('R90_D6_PREFLIGHT_FROZEN_P38_SCRIPT_H17_SOURCE_ELF_DATA_DEPS_CPU0_PATCH_ANCHORS_PASS',
          st['source']['source_hashes']['algorithms/PipNN/pipnn_utils.h'],flush=True)


def pilot10k():
    preflight()
    OUT.mkdir()
    for d in ('source','build','logs','graphs'):(OUT/d).mkdir()
    p38=load_p38()
    st={'status':'RUNNING_10K','script_sha':ownsha(),'p38_script_sha':P38_SHA,
        'frozen_manifest_sha':sha(P38_ROOT/'result_manifest_1m.json'),
        'data_10k_sha':sha(DATA[10000]),'diagnostic_elf_sha':{},
        'source_hashes':{},'runs':[],
        'scope':'D6 diagnostic only, one CPU0, H17 C160 K1024 N2. Local leaf counters; NOT comparable wall time.'}
    json_write(OUT/'progress.json',st)
    for arm in ('ctrl','fast'):
        source=P38_ROOT/'source'/arm; target=OUT/'source'/arm
        shutil.copytree(source,target,symlinks=True,
                        ignore=shutil.ignore_patterns('build','_deps','.git','*.graph','*.fbin','*.log'))
        util=target/'algorithms/PipNN/pipnn_utils.h'
        head=target/'algorithms/PipNN/pipnn.h'
        util.write_text(patch_utils(util.read_text(),p38,arm))
        head.write_text(patch_main(head.read_text(),arm))
        st['source_hashes'][arm]=p38.source_hashes(target)
        st['diagnostic_elf_sha'][arm]=compile_one(arm,p38)
        json_write(OUT/'progress.json',st)
        print('R90_D6_COMPILE_PASS',arm,st['diagnostic_elf_sha'][arm],flush=True)
    for arm in ('ctrl','fast'):
        st['runs'].append(diagnostic_build(arm,10000))
        json_write(OUT/'progress.json',st)
    st['status']='PASS_10K';json_write(OUT/'manifest_10k.json',st)
    certify(st,10000)
    json_write(OUT/'work_summary_10k.json',summary(st))
    csv_write(OUT/'work_summary_10k.csv',summary(st))
    print('R90_D6_PILOT10K_PASS__READY_100K',flush=True)


def audit10k():
    ck((OUT/'manifest_10k.json').is_file(),'MANIFEST_10K_MISSING')
    st=json.loads((OUT/'manifest_10k.json').read_text())
    ck(st['status']=='PASS_10K' and len(st['runs'])==2,'10K_STATE')
    certify(st,10000)
    ck((OUT/'work_summary_10k.json').is_file(),'10K_SUMMARY_MISSING')
    ck(json.loads((OUT/'work_summary_10k.json').read_text())==summary(st),'10K_SUMMARY_DRIFT')
    csv_check(OUT/'work_summary_10k.csv',summary(st))
    print('R90_D6_AUDIT_10K_PASS',flush=True)


def pilot100k():
    audit10k()
    ck(not any((OUT/x).exists() for x in ('manifest_100k.json','work_summary_100k.json')),
       '100K_EXISTS')
    st=json.loads((OUT/'manifest_10k.json').read_text())
    for arm in ('ctrl','fast'):
        st['runs'].append(diagnostic_build(arm,100000))
        json_write(OUT/'progress_100k.json',st)
    st['status']='PASS_100K'
    json_write(OUT/'manifest_100k.json',st)
    certify(st,100000)
    json_write(OUT/'work_summary_100k.json',summary(st))
    csv_write(OUT/'work_summary_100k.csv',summary(st))
    print('R90_D6_PILOT100K_PASS__READY_1M',flush=True)


def audit100k():
    audit10k()
    ck((OUT/'manifest_100k.json').is_file(),'MANIFEST_100K_MISSING')
    st=json.loads((OUT/'manifest_100k.json').read_text())
    ck(st['status']=='PASS_100K' and len(st['runs'])==4,'100K_STATE')
    certify(st,100000)
    ck((OUT/'work_summary_100k.json').is_file(),'100K_SUMMARY_MISSING')
    ck(json.loads((OUT/'work_summary_100k.json').read_text())==summary(st),'100K_SUMMARY_DRIFT')
    csv_check(OUT/'work_summary_100k.csv',summary(st))
    print('R90_D6_AUDIT_100K_PASS',flush=True)


def pilot1m():
    audit100k()
    ck(not any((OUT/x).exists() for x in ('manifest_1m.json','work_summary_1m.json')),'1M_EXISTS')
    p38=load_p38(); prior(p38,True)
    st=json.loads((OUT/'manifest_100k.json').read_text())
    for arm in ('ctrl','fast'):
        st['runs'].append(diagnostic_build(arm,1000000))
        json_write(OUT/'progress_1m.json',st)
    st['status']='PASS_1M';json_write(OUT/'manifest_1m.json',st)
    certify(st,1000000)
    json_write(OUT/'work_summary_1m.json',summary(st))
    csv_write(OUT/'work_summary_1m.csv',summary(st))
    print('R90_D6_PILOT1M_PASS__COUNTERS_COMPLETE',flush=True)


def audit1m():
    audit100k()
    ck((OUT/'manifest_1m.json').is_file(),'MANIFEST_1M_MISSING')
    st=json.loads((OUT/'manifest_1m.json').read_text())
    ck(st['status']=='PASS_1M' and len(st['runs'])==6,'1M_STATE')
    certify(st,1000000)
    ck((OUT/'work_summary_1m.json').is_file(),'1M_SUMMARY_MISSING')
    ck(json.loads((OUT/'work_summary_1m.json').read_text())==summary(st),'1M_SUMMARY_DRIFT')
    csv_check(OUT/'work_summary_1m.csv',summary(st))
    print('R90_D6_AUDIT_1M_PASS',flush=True)


def selftest():
    p38=load_p38()
    p38.selftest()  # 1,000 frozen FP32 special-value Top-2 packed-order equivalence rows
    # Synthetic source patch test; exact frozen production anchors, no native graph assumed.
    toy='std::atomic<size_t> dist_traversed(0);\n'+p38.H17_BEGIN+'\n'+p38.DECL_OLD+'\n'+(
        '        if (i == j) continue;\n'+p38.SELECT_OLD)+'\n'+p38.H17_END+'\nVQPartialSort(x,y,z);\n'
    # Synthetic branch validates anchors and declarative counter structure only.
    t=patch_utils(toy,p38,'ctrl')
    ck(t.count('r90_d6_merge(r90_d6_local);')==1,'SELFTEST_SOURCE_MERGE')
    ck(t.count('++r90_d6_local.packed_first_checks')==1,'SELFTEST_SHORTCIRCUIT_FIRST')
    ck(t.count('++r90_d6_local.packed_second_checks')==1,'SELFTEST_SHORTCIRCUIT_SECOND')
    fasttoy='std::atomic<size_t> dist_traversed(0);\n'+p38.H17_BEGIN+'\n'+p38.DECL_NEW+'\n'+(
        '        if (i == j) continue;\n'+p38.SELECT_NEW)+'\n'+p38.H17_END+'\nVQPartialSort(x,y,z);\n'
    tf=patch_utils(fasttoy,p38,'fast')
    ck('++r90_d6_local.early_rejects;' in tf and
       '++r90_d6_local.cutoff_assignments;' in tf,'SELFTEST_FAST_COUNTERS')
    ck('r90_d6_report("ctrl");' in patch_main('    C.multiple_clustertrees(graph_h, Points, cluster_size, cluster_rounds);', 'ctrl'),
       'SELFTEST_PRINT')
    # Verify count formulas and short-circuit via a small executable specification.
    import math, random
    rng=random.Random(555)
    for arm in ('ctrl','fast'):
        for rep in range(300):
            values=[rng.uniform(-100,100) for _ in range(42)]
            if rep%5==0: values=[1.0]*42
            count=0; first=float('inf');second=float('inf');cutoff=float('inf')
            cands=fc=rej=pack=pf=ps=0
            for j,x in enumerate(values):
                if j==0:continue
                cands+=1
                if arm=='fast' and count==2:
                    fc+=1
                    if x>cutoff:rej+=1;continue
                pack+=1
                d=p38._packed(p38._float32(x),j)
                if count!=0:pf+=1
                if count==0 or d<first:
                    second=first;first=d
                    if arm=='fast':cutoff=p38._float32(second)
                else:
                    if count!=1:ps+=1
                    if count==1 or d<second:
                        second=d
                        if arm=='fast':cutoff=p38._float32(second)
                if count<2:count+=1
            ck(cands==pack+rej,'SELFTEST_CONSERVATION')
            ck(pf+ps<=2*pack,'SELFTEST_PACKED_BRANCHES')
            ck((fc==rej==0) if arm=='ctrl' else fc>=rej,'SELFTEST_FLOAT_BRANCH')
    print('R90_D6_SELFTEST_PASS_SOURCE_PATCH_SHORTCIRCUIT_COUNTERS_600_SYNTHETIC_ROWS',flush=True)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('phase',choices=('selftest','preflight','pilot10k','audit10k',
                                    'pilot100k','audit100k','pilot1m','audit1m'))
    mode=p.parse_args().phase
    globals()[mode]()

if __name__=='__main__':
    try:main()
    except Exception as e:
        print('R90_D6_HOLD',type(e).__name__,str(e),file=sys.stderr,flush=True)
        sys.exit(2)
