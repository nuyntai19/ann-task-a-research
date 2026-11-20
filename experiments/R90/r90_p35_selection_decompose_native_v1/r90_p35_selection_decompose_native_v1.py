#!/usr/bin/env python3
"""R90-P3.5: Stock PiPNN graph-preserving Selection decomposition.

Phases: selftest, preflight, pilot10k, audit10k, pilot100k, audit100k.

Parent is R90-P3.4 native 100K PASS; the parent instrumented C++ source is
copied, NOT modified. The only new instrumentation splits P3.4 Selection into
pack / VQPartialSort / emit. P3.4 diag ELF is a separate native control.

No algorithmic optimization, Search or hardware-comparator counts claimed.
Source-level timing may be perturbed by per-row steady_clock calls.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path.home() / 'ann-task-a'
R90 = ROOT / 'experiments/R90'
P34 = R90 / 'r90_p34_leaf_native_profile_v1'
P34SCRIPT = Path.home() / 'Downloads/r90_p34_leaf_native_profile_v1.py'
P34_SCRIPT_SHA = '0361ed829b033e1796dc145364d6c109edabfdc0e82a5c91150e984d9676343d'
OUT = R90 / 'r90_p35_selection_decompose_native_v1'
GRAPHS = {
    10000:'59dd18da46ebb88604de4aa0d253df36b65ca5965de80af2f616d5f119a637a9',
    100000:'4998cb93784da92728f2f6bd02aee6d3006d44c2b80f7b8b5be2a7f85f27d3e1',
}
DEPS={
 'PARLAYLIB':(ROOT/'experiments/R86/r86_v1_2_builds/stock_off/_deps/parlaylib-src','51017699dcc421f80479cdb238d3092233ad0d26'),
 'EIGEN':(ROOT/'experiments/R86/r86_v1_2_builds/stock_off/_deps/eigen-src','3147391d946bb4b6c68edd901f2add6ac1f31f8c'),
 'ABSEIL-CPP':(ROOT/'experiments/R86/r86_v1_2_builds/stock_off/_deps/abseil-cpp-src','bc257a88f7c1939f24e0379f14a3589e926c950c'),
 'HIGHWAY':(ROOT/'experiments/H85/r85_0_matched_baseline/build_stock/_deps/highway-src','6bc2d47793bae9c521fb4150936669647700765d'),
 'GOOGLEBENCHMARK':(ROOT/'experiments/R86/r86_v1_2_builds/stock_off/_deps/googlebenchmark-src','d886e3177c5dc48f150fbfbf142be6e724a032a4')
}

# P3.4 stock diagnostic source (EXACT anchors, fail if changed).
REPORT_OLD = 'inline void r90p34_report() {\n  auto& s = r90p34();'
REPORT_NEW = '''struct R90P35SelectCounters {
  std::atomic<uint64_t> rows{0}, sort_inputs{0}, emitted_edges{0};
  std::atomic<uint64_t> pack_ns{0}, sort_ns{0}, emit_ns{0};
};
inline R90P35SelectCounters& r90p35() {
  static R90P35SelectCounters s;
  return s;
}
inline void r90p34_report() {
  auto& p35 = r90p35();
  std::cout << "R90_P35_SELECT_STATS"
    << " rows=" << p35.rows.load()
    << " sort_inputs=" << p35.sort_inputs.load()
    << " emitted_edges=" << p35.emitted_edges.load()
    << " pack_ns=" << p35.pack_ns.load()
    << " sort_ns=" << p35.sort_ns.load()
    << " emit_ns=" << p35.emit_ns.load()
    << " scope=PACK_SORT_EMIT_NOT_HIGHWAY_COMPARATORS"
    << std::endl;
  auto& s = r90p34();'''

KNN_OLD = '''  for (size_t i = 0; i < N; ++i) {
    Q.clear();
    for (indexType j = 0; j < N; ++j) {
      if (i == j) continue;
      float dist_ij = (i < j) ? dist_mat[j * N + i] : dist_mat[i * N + j];
      double packed = packFloatAndInt(dist_ij, j);
      Q.push_back(packed);
    }
    size_t limit = std::min(MST_DEG, Q.size());
    VQPartialSort(Q.data(), Q.data() + Q.size(), limit);
    
    uint32_t global_i = active_indices[i];
    for (size_t j = 0; j < limit; j++) {
      auto unpacked = unpackDouble(Q[j]);
      uint32_t global_neighbor = active_indices[unpacked.second];
      float dist = unpacked.first;
      directed_edges.emplace_back(global_i, global_neighbor, dist);
    }
  }

  const auto r90_p34_knn_t2 = std::chrono::steady_clock::now();'''
KNN_NEW = '''  uint64_t r90p35_pack_ns_local = 0;
  uint64_t r90p35_sort_ns_local = 0;
  uint64_t r90p35_emit_ns_local = 0;
  for (size_t i = 0; i < N; ++i) {
    const auto r90p35_t0 = std::chrono::steady_clock::now();
    Q.clear();
    for (indexType j = 0; j < N; ++j) {
      if (i == j) continue;
      float dist_ij = (i < j) ? dist_mat[j * N + i] : dist_mat[i * N + j];
      double packed = packFloatAndInt(dist_ij, j);
      Q.push_back(packed);
    }
    const auto r90p35_t1 = std::chrono::steady_clock::now();
    size_t limit = std::min(MST_DEG, Q.size());
    VQPartialSort(Q.data(), Q.data() + Q.size(), limit);
    const auto r90p35_t2 = std::chrono::steady_clock::now();
    uint32_t global_i = active_indices[i];
    for (size_t j = 0; j < limit; j++) {
      auto unpacked = unpackDouble(Q[j]);
      uint32_t global_neighbor = active_indices[unpacked.second];
      float dist = unpacked.first;
      directed_edges.emplace_back(global_i, global_neighbor, dist);
    }
    const auto r90p35_t3 = std::chrono::steady_clock::now();
    r90p35_pack_ns_local += static_cast<uint64_t>(
      std::chrono::duration_cast<std::chrono::nanoseconds>(r90p35_t1-r90p35_t0).count());
    r90p35_sort_ns_local += static_cast<uint64_t>(
      std::chrono::duration_cast<std::chrono::nanoseconds>(r90p35_t2-r90p35_t1).count());
    r90p35_emit_ns_local += static_cast<uint64_t>(
      std::chrono::duration_cast<std::chrono::nanoseconds>(r90p35_t3-r90p35_t2).count());
  }
  auto& r90p35_counts = r90p35();
  r90p35_counts.rows.fetch_add(static_cast<uint64_t>(N), std::memory_order_relaxed);
  r90p35_counts.sort_inputs.fetch_add(static_cast<uint64_t>(N)*(N-1), std::memory_order_relaxed);
  r90p35_counts.emitted_edges.fetch_add(static_cast<uint64_t>(directed_edges.size()), std::memory_order_relaxed);
  r90p35_counts.pack_ns.fetch_add(r90p35_pack_ns_local, std::memory_order_relaxed);
  r90p35_counts.sort_ns.fetch_add(r90p35_sort_ns_local, std::memory_order_relaxed);
  r90p35_counts.emit_ns.fetch_add(r90p35_emit_ns_local, std::memory_order_relaxed);

  const auto r90_p34_knn_t2 = std::chrono::steady_clock::now();'''

P34RX = re.compile(r'^R90_P34_LEAF_STATS (.+) comparator_scope=NOT_COUNTED_VQ_SORT_AND_LSH_MERGE\s*$', re.M)
P35RX = re.compile(r'^R90_P35_SELECT_STATS rows=(\d+) sort_inputs=(\d+) emitted_edges=(\d+) pack_ns=(\d+) sort_ns=(\d+) emit_ns=(\d+) scope=PACK_SORT_EMIT_NOT_HIGHWAY_COMPARATORS\s*$',re.M)


def hold(reason):raise RuntimeError('R90_P35_HOLD_'+reason)
def ck(cond,msg):
    if not cond:hold(msg)
def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(4*1024*1024),b''):h.update(b)
    return h.hexdigest()
def one(s,a,b,label):
    ck(s.count(a)==1,label+'_COUNT_'+str(s.count(a)))
    return s.replace(a,b,1)
def patch(s):
    s=one(s,REPORT_OLD,REPORT_NEW,'P34_REPORT')
    s=one(s,KNN_OLD,KNN_NEW,'STOCK_KNN')
    ck(s.count('R90_P35_SELECT_STATS')==1 and s.count('r90p35_pack_ns_local')==3,'PATCH_RECEIPT')
    return s

def p34_audit():
    ck(P34SCRIPT.is_file() and sha(P34SCRIPT)==P34_SCRIPT_SHA,'P34_SCRIPT_SHA')
    r=subprocess.run([sys.executable,str(P34SCRIPT),'audit100k'],capture_output=True,text=True)
    ck(r.returncode==0 and 'R90_P34_AUDIT_100K_3X_PAIRED_SOURCE_ELF_GRAPH_WORK_SHA_PASS' in r.stdout,
       'P34_AUDIT_100K_'+str(r.returncode)+'_'+(r.stderr+r.stdout)[-250:])
    for name in ('result_manifest_10k.json','result_manifest_100k.json'):
        ck((P34/name).is_file(),'P34_MANIFEST_'+name)
    m=json.loads((P34/'result_manifest_100k.json').read_text())
    ck(m['status']=='PASS_100K_GRAPH_PARITY_REP3' and len(m['builds'])==8,'P34_PARENT_STATE')
    ck(m['expected_graph_sha']['10000']==GRAPHS[10000] and m['expected_graph_sha']['100000']==GRAPHS[100000],
       'P34_GRAPH_PIN')
    ck(m['script_sha']==P34_SCRIPT_SHA,'P34_PARENT_SCRIPT_PIN')
    return m

def preflight(fresh=True):
    ck(R90.is_dir() and P34.is_dir(),'ROOT')
    if fresh: ck(not OUT.exists() and not OUT.is_symlink(),'OUT_EXISTS')
    for exe in ('cmake','git','taskset'):
        ck(shutil.which(exe) is not None,'BIN_'+exe)
    ck(Path('/usr/bin/time').is_file(),'TIME_BIN')
    ck(0 in os.sched_getaffinity(0),'CPU0')
    m=p34_audit()
    up=P34/'source/diag/algorithms/PipNN/pipnn_utils.h'
    ck(up.is_file() and sha(up)==m['diag_source_utils_sha'],'P34_DIAG_SOURCE_UTILS')
    patch(up.read_text())
    parent_elf=P34/'build/diag/algorithms/PipNN/neighbors-pipnn_FLOAT_T_EUCLIDEAN'
    ck(sha(parent_elf)==m['diag_elf_sha'],'P34_DIAG_ELF')
    base=ROOT/'data/sift100k.fbin'
    ck(base.is_file() and sha(base)==m['source_sha']['base'],'P34_BASE_DATA')
    for name,(p,rev) in DEPS.items():
        ck(p.is_dir(),'DEP_DIR_'+name)
        s=subprocess.run(['git','-C',str(p),'rev-parse','HEAD'],capture_output=True,text=True)
        ck(s.returncode==0 and s.stdout.strip()==rev,'DEP_'+name)
    print('R90_P35_PREFLIGHT_PARENT_P34_MANIFEST_SOURCE_ELF_SHA_AND_ANCHORS_PASS',flush=True)
    return m

def store(path,obj,overwrite=False):
    path=Path(path)
    if not overwrite:ck(not path.exists() and not path.is_symlink(),'JSON_EXISTS_'+path.name)
    temp=path.with_suffix(path.suffix+'.part')
    with temp.open('x' if not temp.exists() else 'w',encoding='utf8') as f:
        json.dump(obj,f,indent=2,sort_keys=True);f.write('\n')
    temp.replace(path)

def native(cmd,log,env=None,timeout=3600):
    ck(not log.exists() and not log.is_symlink(),'LOG_EXISTS_'+log.name)
    with log.open('x',encoding='utf8') as f:
        p=subprocess.run([str(v) for v in cmd],stdout=f,stderr=subprocess.STDOUT,env=env,timeout=timeout)
    ck(p.returncode==0,'PROC_RC_'+str(p.returncode)+'_'+log.name)

def parse(s,mode):
    a=P34RX.findall(s)
    ck(len(a)==1,'P34_COUNTER_LINE_'+mode)
    p34={}
    for field in a[0].split():
        name,sep,v=field.partition('=')
        ck(sep and v.isdigit(),'P34_COUNTER_FIELD_'+field)
        p34[name]=int(v)
    ck(p34.get('rows',0)>0 and p34.get('pack_values',0)>0,'P34_COUNTER_ZERO')
    result={'p34':p34}
    b=P35RX.findall(s)
    if mode=='split':
        ck(len(b)==1,'P35_COUNTER_LINE')
        names=('rows','sort_inputs','emitted_edges','pack_ns','sort_ns','emit_ns')
        p35=dict(zip(names,map(int,b[0])))
        ck(p35['rows']==p34['rows'] and p35['sort_inputs']==p34['pack_values'] and
           p35['emitted_edges']==p34['directed_edges'],'SPLIT_COUNTER_PARITY')
        ck(min(p35['pack_ns'],p35['sort_ns'],p35['emit_ns'])>0,'SPLIT_TIME_ZERO')
        ck(sum(p35[k] for k in ('pack_ns','sort_ns','emit_ns')) <= p34['selection_us']*1000,
           'SPLIT_TIME_EXCEEDS_SELECTION')
        result['p35']=p35
    else:ck(not b,'P35_COUNTER_IN_PARENT')
    return result

def env():
    x=os.environ.copy()
    x.update({'LC_ALL':'C','PARLAY_NUM_THREADS':'1','OMP_NUM_THREADS':'1'})
    for k in ('R90_A5_MODE','R90_A5_FRACTION','R90_P33_GRAPH_SEED','R90_P33_POLICY','R90_P33_SELECTOR'):
        x.pop(k,None)
    return x

def args(exe,base,graph):
    return [exe,'-base_path',base,'-graph_outfile',graph,'-num_clusters','2',
      '-cluster_size','1024','-table_size','160','-top_level_leaders','100',
      '-fanout_scheme','10,3,1','-mst_deg','2','-prune','1','-prune_all','1',
      '-prune_degree','64','-hash_bits','12','-alpha','1.1','-k','0']

def run_build(variant,n,rep,base):
    label=f'{n}_{variant}_r{rep}'
    exe=(OUT/'build/split/algorithms/PipNN/neighbors-pipnn_FLOAT_T_EUCLIDEAN') if variant=='split' else (P34/'build/diag/algorithms/PipNN/neighbors-pipnn_FLOAT_T_EUCLIDEAN')
    gp=OUT/'graphs'/f'{label}.graph'
    log=OUT/'logs'/f'{label}.stdout'
    tim=OUT/'logs'/f'{label}.time'
    print('R90_P35_BUILD_START',label,flush=True)
    t0=time.perf_counter()
    native(['/usr/bin/time','-v','-o',tim,'taskset','-c','0',*args(exe,base,gp)],log,env=env())
    wall=time.perf_counter()-t0
    with gp.open('rb') as f:
        import struct
        ck(f.read(8)==struct.pack('<II',n,64),'GRAPH_HEADER_'+label)
    graph_sha=sha(gp)
    ck(graph_sha==GRAPHS[n],'GRAPH_STOCK_SHA_'+label)
    counters=parse(log.read_text(errors='replace'),variant)
    row={'arm':variant,'n':n,'rep':rep,'wall_s':wall,'graph_sha':graph_sha,
         'graph':str(gp),'graph_bytes':gp.stat().st_size,'stdout':str(log),
         'stdout_sha':sha(log),'timefile':str(tim),'time_sha':sha(tim),'counters':counters}
    print('R90_P35_BUILD_PASS',label,'wall_s',round(wall,6),'graph_sha',graph_sha,
         'selection_us',counters['p34']['selection_us'],
         'split_ns',None if variant=='parent' else [counters['p35'][k] for k in ('pack_ns','sort_ns','emit_ns')],flush=True)
    return row

def pilot10k():
    m=preflight(True)
    OUT.mkdir();
    for name in ('source','build','graphs','logs'): (OUT/name).mkdir()
    dest=OUT/'source/split'
    shutil.copytree(P34/'source/diag',dest,symlinks=True)
    utils=dest/'algorithms/PipNN/pipnn_utils.h'
    utils.write_text(patch(utils.read_text()))
    state={'status':'RUNNING_10K','p35_script_sha':sha(Path(__file__).resolve()),
           'p34_script_sha':P34_SCRIPT_SHA,'parent_p34_manifest_sha':sha(P34/'result_manifest_100k.json'),
           'p34_diag_elf_sha':m['diag_elf_sha'],'p34_diag_source_utils_sha':m['diag_source_utils_sha'],
           'split_utils_sha':sha(utils),'split_pipnn_sha':sha(dest/'algorithms/PipNN/pipnn.h'),
           'builds':[],'limits':['This is timing instrumentation, not a proposed optimization',
                      'Per-row timers cause overhead; split times include clock effects',
                      'VQPartialSort Highway actual comparisons and assignments not counted',
                      'Three repetitions are same graph seed 555, not independent graph seeds']}
    store(OUT/'progress.json',state)
    cm=['cmake','-S',dest,'-B',OUT/'build/split','-DCMAKE_BUILD_TYPE=Release',
        '-DCMAKE_CXX_FLAGS=-O3 -pthread','-DCMAKE_EXPORT_COMPILE_COMMANDS=ON',
        '-DFETCHCONTENT_FULLY_DISCONNECTED=ON','-DR90_A5_GATE=OFF']
    for name,(p,_) in DEPS.items(): cm.append('-DFETCHCONTENT_SOURCE_DIR_'+name+'='+str(p))
    native(cm,OUT/'logs/configure.log',timeout=1800)
    native(['cmake','--build',OUT/'build/split','--target','neighbors-pipnn_FLOAT_T_EUCLIDEAN','--parallel','2'],OUT/'logs/compile.log')
    elf=OUT/'build/split/algorithms/PipNN/neighbors-pipnn_FLOAT_T_EUCLIDEAN'
    ck(elf.is_file() and os.access(elf,os.X_OK),'SPLIT_ELF')
    state['split_elf_sha']=sha(elf)
    print('R90_P35_CPP_SPLIT_PASS',state['split_elf_sha'],flush=True)
    store(OUT/'progress.json',state,overwrite=True)
    row=run_build('split',10000,1,P34/'data/sift10k.fbin')
    state['builds'].append(row)
    state['status']='PASS_10K';store(OUT/'result_manifest_10k.json',state)
    audit10k()
    print('R90_P35_10K_GRAPH_SHA_AND_SPLIT_WORK_PASS_READY_100K',flush=True)

def audit_common(m):
    ck(m['p35_script_sha']==sha(Path(__file__).resolve()),'P35_SCRIPT_SHA')
    ck(m['parent_p34_manifest_sha']==sha(P34/'result_manifest_100k.json'),'P34_PARENT_MANIFEST_SHA')
    ck(m['p34_diag_elf_sha']==sha(P34/'build/diag/algorithms/PipNN/neighbors-pipnn_FLOAT_T_EUCLIDEAN'),'P34_ELF_SHA')
    ck(m['split_utils_sha']==sha(OUT/'source/split/algorithms/PipNN/pipnn_utils.h'),'P35_UTILS_SHA')
    ck(m['split_pipnn_sha']==sha(OUT/'source/split/algorithms/PipNN/pipnn.h'),'P35_PIPNN_SHA')
    ck(m['split_elf_sha']==sha(OUT/'build/split/algorithms/PipNN/neighbors-pipnn_FLOAT_T_EUCLIDEAN'),'P35_ELF_SHA')
    for row in m['builds']:
        ck(row['graph_sha']==sha(row['graph'])==GRAPHS[row['n']],'GRAPH_SHA_'+row['arm']+str(row['rep']))
        ck(row['stdout_sha']==sha(row['stdout']) and row['time_sha']==sha(row['timefile']),'OUTPUT_SHA_'+row['arm']+str(row['rep']))
        ck(row['counters']==parse(Path(row['stdout']).read_text(errors='replace'),row['arm']),'LOG_COUNTER_PARITY')
    for n in (10000,100000):
        for rep in {r['rep'] for r in m['builds'] if r['n']==n}:
            rows=[r for r in m['builds'] if r['rep']==rep and r['n']==n]
            if n==100000:ck(len(rows)==2 and set(r['arm'] for r in rows)=={'split','parent'},'PAIR_100K_'+str(rep))

def audit10k():
    preflight(False)
    p=OUT/'result_manifest_10k.json'
    ck(p.is_file(),'10K_MANIFEST')
    m=json.loads(p.read_text())
    ck(m['status']=='PASS_10K' and len(m['builds'])==1 and m['builds'][0]['n']==10000,'10K_STATE')
    audit_common(m)
    print('R90_P35_AUDIT_10K_SOURCE_ELF_GRAPH_SHA_AND_SPLIT_COUNTERS_PASS',flush=True)

def pilot100k():
    audit10k()
    ck(not (OUT/'result_manifest_100k.json').exists(),'100K_EXISTS')
    m=json.loads((OUT/'result_manifest_10k.json').read_text())
    for rep in (1,2,3):
        variants=('parent','split') if rep%2 else ('split','parent')
        for variant in variants:
            row=run_build(variant,100000,rep,ROOT/'data/sift100k.fbin')
            m['builds'].append(row)
            store(OUT/'progress_100k.json',m,overwrite=True)
        print('R90_P35_GRAPH_PARITY_PASS_100K_REP',rep,flush=True)
    m['status']='PASS_100K_3PAIRS';store(OUT/'result_manifest_100k.json',m)
    audit100k()
    for row in m['builds']:
        if row['n']==100000 and row['arm']=='split':
            d=row['counters']['p35'];v=row['counters']['p34']
            print('R90_P35_PROFILE',json.dumps({'rep':row['rep'],'pack_s':d['pack_ns']/1e9,
              'vqpartialsort_s':d['sort_ns']/1e9,'emit_s':d['emit_ns']/1e9,
              'selection_s':v['selection_us']/1e6,'sort_inputs':d['sort_inputs'],
              'rows':d['rows'],'emitted_edges':d['emitted_edges'],
              'wall_s_DIAGNOSTIC_ONLY':row['wall_s']},sort_keys=True),flush=True)
    print('R90_P35_100K_3PAIR_NATIVE_GRAPH_SHA_SELECTION_DECOMPOSE_PASS',flush=True)

def audit100k():
    audit10k()
    p=OUT/'result_manifest_100k.json';ck(p.is_file(),'100K_MANIFEST')
    m=json.loads(p.read_text())
    ck(m['status']=='PASS_100K_3PAIRS' and len(m['builds'])==7,'100K_STATE')
    audit_common(m)
    print('R90_P35_AUDIT_100K_3PAIR_PARENT_ELF_GRAPH_LOG_SHA_PASS',flush=True)

def selftest():
    # Check patch using the EXACT P3.4 counter definition, plus the known
    # native source loop from stock pipnn_utils.h (frozen P0 source).
    text='xxx\n'+'''struct Example {\n'''+REPORT_OLD+'\n}\n'+KNN_OLD+'\n'
    p=patch(text)
    ck('R90_P35_SELECT_STATS' in p and p.count('VQPartialSort(Q.data(), Q.data() + Q.size(), limit);')==1,'SELFTEST_PATCH')
    ck(p.count('directed_edges.emplace_back(global_i, global_neighbor, dist);')==1,'SELFTEST_SEMANTICS')
    fake='R90_P35_SELECT_STATS rows=100 sort_inputs=9900 emitted_edges=200 pack_ns=18000 sort_ns=140000 emit_ns=2000 scope=PACK_SORT_EMIT_NOT_HIGHWAY_COMPARATORS\n'
    ck(len(P35RX.findall(fake))==1,'SELFTEST_REGEX')
    d={'rows':100,'pack_values':9900,'directed_edges':200,'selection_us':500}
    v=dict(zip(('rows','sort_inputs','emitted_edges','pack_ns','sort_ns','emit_ns'),map(int,P35RX.findall(fake)[0])))
    ck(v['rows']==d['rows'] and v['sort_inputs']==d['pack_values'] and v['emitted_edges']==d['directed_edges'],'SELFTEST_INVARIANTS')
    print('R90_P35_SELFTEST_PASS_STRICT_SELECTION_PATCH_AND_COUNTER_FORMULAE',flush=True)

def main():
    a=argparse.ArgumentParser(description=__doc__)
    a.add_argument('phase',choices=['selftest','preflight','pilot10k','audit10k','pilot100k','audit100k'])
    p=a.parse_args().phase
    if p=='selftest':selftest()
    elif p=='preflight':preflight(True)
    elif p=='pilot10k':pilot10k()
    elif p=='audit10k':audit10k()
    elif p=='pilot100k':pilot100k()
    elif p=='audit100k':audit100k()
if __name__=='__main__':
    try:main()
    except Exception as exc:
        print('R90_P35_HOLD',type(exc).__name__,str(exc),file=sys.stderr,flush=True)
        sys.exit(2)
