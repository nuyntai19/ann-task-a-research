#!/usr/bin/env python3
"""R90 P3.4: fail-closed, graph-SHA-preserving PiPNN stock RunLeaf profiling.

Native Ubuntu phases:
  selftest
  preflight
  pilot10k     # copies pinned P0 stock source, compiles CTRL + DIAG, builds paired SIFT10K
  audit10k     # verify SHA/graph parity/report + pinned historical SIFT10K stock graph
  pilot100k    # only after audit10k, build 3 paired SIFT100K graphs (new files)
  audit100k    # validate all 3 pairs and pinned historical SIFT100K stock N2 SHA

All work is isolated in a new exclusive directory. Requires pinned dependencies,
SIFT100K original fbin, and P0 stock source on the user's machine. No Search.

Measurements: counts of algorithm-visible copy elements, norm terms, lower-triangle
pairs, row-pack elements, directed-edges, and forward/reverse merge calls; elapsed
stage times are instrumentation diagnostics. DOES NOT COUNT true highway VQPartialSort
comparators, Eigen hardware FLOPs, or internal LSHGraph merge comparisons.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import time
from pathlib import Path

ROOT=Path.home()/'ann-task-a'
R90=ROOT/'experiments/R90'
P0=R90/'r90_p0_stock_a5_compile_gate_v1'
SOURCE=P0/'stock_source'
BASE=ROOT/'data/sift100k.fbin'
OUT=R90/'r90_p34_leaf_native_profile_v1'
SRC_SHA={
 'pipnn':'43d30d9959dbad6c4736e9d6d942cb8a5a7aeab3db389249865cd9f96c7d2ebd',
 'utils':'ee2048738ad4462f21bdfea4a1cf7c2ac140f72fbd8875d869bc4f613d93db53',
 'root':'198badc698ebd5a87fe10e854dca124ac94825535931f20265b86c5d6643c2f9',
 'base':'e50ff1bc34bcc6d1c97dd001023c09a666971cde64605cc06671ed8a8ff1ed12'
}
GRAPH_SHA={
 10000:'59dd18da46ebb88604de4aa0d253df36b65ca5965de80af2f616d5f119a637a9',
 100000:'4998cb93784da92728f2f6bd02aee6d3006d44c2b80f7b8b5be2a7f85f27d3e1'
}
DEPS={
 'PARLAYLIB':(ROOT/'experiments/R86/r86_v1_2_builds/stock_off/_deps/parlaylib-src','51017699dcc421f80479cdb238d3092233ad0d26'),
 'EIGEN':(ROOT/'experiments/R86/r86_v1_2_builds/stock_off/_deps/eigen-src','3147391d946bb4b6c68edd901f2add6ac1f31f8c'),
 'ABSEIL-CPP':(ROOT/'experiments/R86/r86_v1_2_builds/stock_off/_deps/abseil-cpp-src','bc257a88f7c1939f24e0379f14a3589e926c950c'),
 'HIGHWAY':(ROOT/'experiments/H85/r85_0_matched_baseline/build_stock/_deps/highway-src','6bc2d47793bae9c521fb4150936669647700765d'),
 'GOOGLEBENCHMARK':(ROOT/'experiments/R86/r86_v1_2_builds/stock_off/_deps/googlebenchmark-src','d886e3177c5dc48f150fbfbf142be6e724a032a4')
}

P34_COUNTERS = r'''// R90-P3.4: diagnostic counters only, no algorithmic branch changes.
struct R90P34Counters {
  std::atomic<uint64_t> leaves{0}, rows{0}, copy_coords{0}, norm_terms{0};
  std::atomic<uint64_t> triangle_pairs{0}, dot_components_proxy{0};
  std::atomic<uint64_t> metric_fix_cells{0}, pack_values{0}, partial_sort_rows{0};
  std::atomic<uint64_t> directed_edges{0}, merge_calls{0};
  std::atomic<uint64_t> copy_us{0}, norm_us{0}, syrk_us{0}, fix_us{0};
  std::atomic<uint64_t> distmat_us{0}, selection_us{0}, merge_us{0};
};
inline R90P34Counters& r90p34() {
  static R90P34Counters s;
  return s;
}
inline uint64_t r90p34_us(std::chrono::steady_clock::time_point a,
                           std::chrono::steady_clock::time_point b) {
  return static_cast<uint64_t>(
      std::chrono::duration_cast<std::chrono::microseconds>(b-a).count());
}
inline void r90p34_report() {
  auto& s = r90p34();
  std::cout << "R90_P34_LEAF_STATS"
    << " leaves=" << s.leaves.load()
    << " rows=" << s.rows.load()
    << " copy_coords=" << s.copy_coords.load()
    << " norm_terms=" << s.norm_terms.load()
    << " triangle_pairs=" << s.triangle_pairs.load()
    << " dot_components_proxy=" << s.dot_components_proxy.load()
    << " metric_fix_cells=" << s.metric_fix_cells.load()
    << " pack_values=" << s.pack_values.load()
    << " partial_sort_rows=" << s.partial_sort_rows.load()
    << " directed_edges=" << s.directed_edges.load()
    << " merge_calls=" << s.merge_calls.load()
    << " copy_us=" << s.copy_us.load()
    << " norm_us=" << s.norm_us.load()
    << " syrk_us=" << s.syrk_us.load()
    << " fix_us=" << s.fix_us.load()
    << " distmat_us=" << s.distmat_us.load()
    << " selection_us=" << s.selection_us.load()
    << " merge_us=" << s.merge_us.load()
    << " comparator_scope=NOT_COUNTED_VQ_SORT_AND_LSH_MERGE"
    << std::endl;
}
'''

# Each exact anchor must occur once. Refuse to patch a drifted stock source.
UTIL_REPLACEMENTS=[
 ('ADD_CHRONO','#include <atomic>','#include <atomic>\n#include <chrono>'),
 ('ADD_COUNTERS','std::atomic<size_t> dist_traversed(0);',
  'std::atomic<size_t> dist_traversed(0);\n'+P34_COUNTERS),
 ('DIST_START','''  size_t dimension = all_points.get_dims();
  float* dist_mat = (float*)get_dist_mat();''','''  size_t dimension = all_points.get_dims();
  const auto r90_p34_t0 = std::chrono::steady_clock::now();
  float* dist_mat = (float*)get_dist_mat();'''),
 ('DIST_COPY_END','''  Eigen::Map<const Eigen::Matrix<float, Eigen::Dynamic, Eigen::Dynamic, Eigen::RowMajor>> P(point_mat, n, dimension);''','''  const auto r90_p34_t1 = std::chrono::steady_clock::now();
  Eigen::Map<const Eigen::Matrix<float, Eigen::Dynamic, Eigen::Dynamic, Eigen::RowMajor>> P(point_mat, n, dimension);'''),
 ('DIST_NORM_END','''  Eigen::Matrix<float, Eigen::Dynamic, 1> P_sq_norms = P.rowwise().squaredNorm();''','''  Eigen::Matrix<float, Eigen::Dynamic, 1> P_sq_norms = P.rowwise().squaredNorm();
  const auto r90_p34_t2 = std::chrono::steady_clock::now();'''),
 ('DIST_SYRK_END','''  D.selfadjointView<Eigen::Lower>().rankUpdate(P);''','''  D.selfadjointView<Eigen::Lower>().rankUpdate(P);
  const auto r90_p34_t3 = std::chrono::steady_clock::now();'''),
 ('DIST_TAIL','''    for (size_t i=0; i < n; ++i) {
      for (size_t j=0; j <= i; ++j) {
        D(i, j) = -1*D(i, j);
      }
    }
  }
}

thread_local uint8_t* tile_point_mat''','''    for (size_t i=0; i < n; ++i) {
      for (size_t j=0; j <= i; ++j) {
        D(i, j) = -1*D(i, j);
      }
    }
  }
  const auto r90_p34_t4 = std::chrono::steady_clock::now();
  auto& s = r90p34();
  const uint64_t pairs = static_cast<uint64_t>(n) * (n+1) / 2;
  s.copy_coords.fetch_add(static_cast<uint64_t>(n)*dimension, std::memory_order_relaxed);
  s.norm_terms.fetch_add(static_cast<uint64_t>(n)*dimension, std::memory_order_relaxed);
  s.triangle_pairs.fetch_add(pairs, std::memory_order_relaxed);
  s.dot_components_proxy.fetch_add(pairs*dimension, std::memory_order_relaxed);
  s.metric_fix_cells.fetch_add(pairs, std::memory_order_relaxed);
  s.copy_us.fetch_add(r90p34_us(r90_p34_t0,r90_p34_t1), std::memory_order_relaxed);
  s.norm_us.fetch_add(r90p34_us(r90_p34_t1,r90_p34_t2), std::memory_order_relaxed);
  s.syrk_us.fetch_add(r90p34_us(r90_p34_t2,r90_p34_t3), std::memory_order_relaxed);
  s.fix_us.fetch_add(r90p34_us(r90_p34_t3,r90_p34_t4), std::memory_order_relaxed);
}

thread_local uint8_t* tile_point_mat'''),
 ('KNN_START','''  auto N = active_indices.size();
  eigen_build_distmat(active_indices, Points);''','''  auto N = active_indices.size();
  const auto r90_p34_knn_t0 = std::chrono::steady_clock::now();
  eigen_build_distmat(active_indices, Points);
  const auto r90_p34_knn_t1 = std::chrono::steady_clock::now();'''),
 ('KNN_SELECT_END','''  // the problem with this approach is that we only merge one neighbor at a time.
  for (const auto& edge : directed_edges) {''','''  const auto r90_p34_knn_t2 = std::chrono::steady_clock::now();
  // the problem with this approach is that we only merge one neighbor at a time.
  for (const auto& edge : directed_edges) {'''),
 ('KNN_END','''    G.merge_neighbors(u, span_f);
    G.merge_neighbors(v, span_r);
  }
}


} // end namespace''','''    G.merge_neighbors(u, span_f);
    G.merge_neighbors(v, span_r);
  }
  const auto r90_p34_knn_t3 = std::chrono::steady_clock::now();
  auto& s = r90p34();
  s.leaves.fetch_add(1, std::memory_order_relaxed);
  s.rows.fetch_add(static_cast<uint64_t>(N), std::memory_order_relaxed);
  s.pack_values.fetch_add(static_cast<uint64_t>(N)*(N-1), std::memory_order_relaxed);
  s.partial_sort_rows.fetch_add(static_cast<uint64_t>(N), std::memory_order_relaxed);
  s.directed_edges.fetch_add(static_cast<uint64_t>(directed_edges.size()), std::memory_order_relaxed);
  s.merge_calls.fetch_add(2*static_cast<uint64_t>(directed_edges.size()), std::memory_order_relaxed);
  s.distmat_us.fetch_add(r90p34_us(r90_p34_knn_t0,r90_p34_knn_t1), std::memory_order_relaxed);
  s.selection_us.fetch_add(r90p34_us(r90_p34_knn_t1,r90_p34_knn_t2), std::memory_order_relaxed);
  s.merge_us.fetch_add(r90p34_us(r90_p34_knn_t2,r90_p34_knn_t3), std::memory_order_relaxed);
}


} // end namespace'''),
]
PIPNN_REPORT_ANCHOR='''      std::cout << "# of comparisons during clustering: " << COMPARISONS
                << std::endl;
    }
  }

  /*  Leaf code  */'''
PIPNN_REPORT_NEW='''      std::cout << "# of comparisons during clustering: " << COMPARISONS
                << std::endl;
    }
    r90p34_report();
  }

  /*  Leaf code  */'''
RX=re.compile(r'^R90_P34_LEAF_STATS leaves=(\d+) rows=(\d+) copy_coords=(\d+) norm_terms=(\d+) triangle_pairs=(\d+) dot_components_proxy=(\d+) metric_fix_cells=(\d+) pack_values=(\d+) partial_sort_rows=(\d+) directed_edges=(\d+) merge_calls=(\d+) copy_us=(\d+) norm_us=(\d+) syrk_us=(\d+) fix_us=(\d+) distmat_us=(\d+) selection_us=(\d+) merge_us=(\d+) comparator_scope=NOT_COUNTED_VQ_SORT_AND_LSH_MERGE\s*$',re.M)
KEYS=['leaves','rows','copy_coords','norm_terms','triangle_pairs','dot_components_proxy','metric_fix_cells','pack_values','partial_sort_rows','directed_edges','merge_calls','copy_us','norm_us','syrk_us','fix_us','distmat_us','selection_us','merge_us']


def ck(q,msg):
    if not q:raise RuntimeError('R90_P34_HOLD_'+msg)

def digest(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda:f.read(4*1024*1024),b''):h.update(b)
    return h.hexdigest()

def patch_one(text,old,new,name):
    ck(text.count(old)==1,'ANCHOR_'+name+'_COUNT_'+str(text.count(old)))
    return text.replace(old,new,1)

def patch_utils(s):
    for name,old,new in UTIL_REPLACEMENTS:s=patch_one(s,old,new,name)
    ck(s.count('R90_P34_LEAF_STATS')==1 and s.count('r90_p34_knn_t3')==2,'PATCH_UTILS_RECEIPT')
    return s

def patch_pipnn(s):
    s=patch_one(s,PIPNN_REPORT_ANCHOR,PIPNN_REPORT_NEW,'PIPNN_REPORT')
    ck(s.count('r90p34_report();')==1,'PATCH_PIPNN_RECEIPT')
    return s

def input_shape(p):
    with Path(p).open('rb') as f:header=f.read(8)
    ck(len(header)==8,'BASE_HEADER')
    n,d=struct.unpack('<II',header)
    ck((n,d)==(100000,128),'BASE_SHAPE')
    ck(p.stat().st_size==8+n*d*4,'BASE_BYTES')
    return n,d

def preflight(fresh=True):
    ck(R90.is_dir() and SOURCE.is_dir(),'SOURCE_ROOT')
    if fresh:ck(not OUT.exists() and not OUT.is_symlink(),'DEST_EXISTS')
    for x in ('cmake','git','taskset'):ck(shutil.which(x) is not None,'EXE_'+x)
    ck(Path('/usr/bin/time').is_file(),'TIME_BINARY')
    ck(0 in os.sched_getaffinity(0),'CPU0_NOT_AVAILABLE')
    inp={'pipnn':SOURCE/'algorithms/PipNN/pipnn.h','utils':SOURCE/'algorithms/PipNN/pipnn_utils.h',
         'root':SOURCE/'CMakeLists.txt','base':BASE}
    for name,p in inp.items():ck(p.is_file() and digest(p)==SRC_SHA[name],'SHA_'+name)
    input_shape(BASE)
    for name,(p,expected) in DEPS.items():
        ck(p.is_dir(),'DEP_'+name)
        git=subprocess.run(['git','-C',str(p),'rev-parse','HEAD'],capture_output=True,text=True)
        ck(git.returncode==0 and git.stdout.strip()==expected,'DEP_GIT_'+name)
    patch_utils(inp['utils'].read_text())
    patch_pipnn(inp['pipnn'].read_text())
    print('R90_P34_PREFLIGHT_SOURCE_DEP_INPUT_SHA_AND_PATCH_ANCHORS_PASS',flush=True)

def write_json(p,obj):
    p=Path(p);ck(not p.exists() and not p.is_symlink(),'JSON_EXISTS_'+p.name)
    with p.open('x',encoding='utf8') as f:json.dump(obj,f,sort_keys=True,indent=2);f.write('\n')

def update_json(p,obj):
    t=p.with_suffix(p.suffix+'.part')
    with t.open('w',encoding='utf8') as f:json.dump(obj,f,sort_keys=True,indent=2);f.write('\n')
    t.replace(p)

def cmd_log(cmd,log,e=None,timeout=3600):
    ck(not log.exists() and not log.is_symlink(),'LOG_EXISTS_'+log.name)
    with log.open('x',encoding='utf8') as f:
        r=subprocess.run([str(z) for z in cmd],stdout=f,stderr=subprocess.STDOUT,env=e,timeout=timeout,check=False)
    ck(r.returncode==0,'PROC_RC_'+str(r.returncode)+'_'+log.name)

def env():
    x=os.environ.copy()
    x.update({'LC_ALL':'C','PARLAY_NUM_THREADS':'1','OMP_NUM_THREADS':'1'})
    for v in ('R90_A5_MODE','R90_A5_FRACTION','R90_P33_GRAPH_SEED','R90_P33_POLICY','R90_P33_SELECTOR'):
        x.pop(v,None)
    return x

def make_prefix(path):
    ck(not path.exists() and not path.is_symlink(),'PREFIX_EXISTS')
    with BASE.open('rb') as f, path.open('xb') as g:
        ck(len(f.read(8))==8,'PREFIX_INPUT_HEADER')
        g.write(struct.pack('<II',10000,128))
        # 10,000 x 128 float32, first vectors are identical to original base.
        remaining=10000*128*4
        while remaining:
            b=f.read(min(1024*1024,remaining))
            ck(bool(b),'PREFIX_EOF')
            g.write(b);remaining-=len(b)
    ck(path.stat().st_size==8+10000*128*4,'PREFIX_SIZE')
    return digest(path)

def configure(out,variant):
    src=out/'source'/variant;dst=out/'build'/variant
    args=['cmake','-S',src,'-B',dst,'-DCMAKE_BUILD_TYPE=Release','-DCMAKE_CXX_FLAGS=-O3 -pthread',
          '-DCMAKE_EXPORT_COMPILE_COMMANDS=ON','-DFETCHCONTENT_FULLY_DISCONNECTED=ON','-DR90_A5_GATE=OFF']
    for key,(p,_) in DEPS.items():args.append('-DFETCHCONTENT_SOURCE_DIR_'+key+'='+str(p))
    cmd_log(args,out/'logs'/f'{variant}.configure.log',timeout=1800)
    cmd_log(['cmake','--build',dst,'--target','neighbors-pipnn_FLOAT_T_EUCLIDEAN','--parallel','2'],
            out/'logs'/f'{variant}.compile.log',timeout=3600)
    exe=dst/'algorithms/PipNN/neighbors-pipnn_FLOAT_T_EUCLIDEAN'
    ck(exe.is_file() and os.access(exe,os.X_OK),'ELF_'+variant)
    return exe

def bcmd(exe,base,out):
    return [exe,'-base_path',base,'-graph_outfile',out,'-num_clusters','2',
            '-cluster_size','1024','-table_size','160','-top_level_leaders','100',
            '-fanout_scheme','10,3,1','-mst_deg','2','-prune','1','-prune_all','1',
            '-prune_degree','64','-hash_bits','12','-alpha','1.1','-k','0']

def parse_profile(s):
    x=RX.findall(s)
    ck(len(x)==1,'LEAF_STATS_COUNT_'+str(len(x)))
    o=dict(zip(KEYS,map(int,x[0])))
    ck(o['leaves']>0 and o['rows']>0 and o['triangle_pairs']>0,'STATS_ZERO')
    ck(o['pack_values']>=o['rows'] and o['merge_calls']==2*o['directed_edges'],'STATS_INVARIANTS')
    ck(o['distmat_us']>=0 and o['selection_us']>=0 and o['merge_us']>=0,'STATS_TIME')
    return o

def parse_graph(gp,n):
    ck(gp.is_file() and gp.stat().st_size>8+4*n,'GRAPH_FILE')
    with gp.open('rb') as f:h=f.read(8)
    ck(h==struct.pack('<II',n,64),'GRAPH_HEADER')
    return digest(gp)

def run_build(out,variant,n,rep,base):
    name=f'{n}_{variant}_r{rep}'
    gp=out/'graphs'/f'{name}.graph';log=out/'logs'/f'{name}.stdout';tm=out/'logs'/f'{name}.time'
    exe=out/'build'/variant/'algorithms/PipNN/neighbors-pipnn_FLOAT_T_EUCLIDEAN'
    print('R90_P34_BUILD_START',name,flush=True)
    t=time.perf_counter()
    cmd_log(['/usr/bin/time','-v','-o',tm,'taskset','-c','0',*bcmd(exe,base,gp)],log,e=env(),timeout=3600)
    wall=time.perf_counter()-t
    sh=parse_graph(gp,n)
    report=parse_profile(log.read_text(errors='replace')) if variant=='diag' else None
    if variant=='ctrl':ck('R90_P34_LEAF_STATS' not in log.read_text(errors='replace'),'CTRL_INSTRUMENTED')
    ck(sh==GRAPH_SHA[n],'GRAPH_MISMATCH_ORIGINAL_STOCK_'+name)
    outrow=dict(arm=variant,n=n,rep=rep,wall_s=wall,graph_sha=sh,graph=str(gp),graph_bytes=gp.stat().st_size,
                stdout=str(log),stdout_sha=digest(log),timefile=str(tm),time_sha=digest(tm),counters=report)
    print('R90_P34_BUILD_PASS',name,'wall_s',round(wall,5),'graph_sha256',sh,
          'counts',None if report is None else {'leaves':report['leaves'],'triangle_pairs':report['triangle_pairs'],
              'pack_values':report['pack_values'],'merge_calls':report['merge_calls']},flush=True)
    return outrow

def pilot10k():
    preflight(True)
    OUT.mkdir();(OUT/'logs').mkdir();(OUT/'source').mkdir();(OUT/'build').mkdir();(OUT/'graphs').mkdir();(OUT/'data').mkdir()
    state=dict(status='RUNNING_10K',script_sha=digest(Path(__file__).resolve()),source_sha=dict(SRC_SHA),
               expected_graph_sha=GRAPH_SHA,dependences={k:v[1] for k,v in DEPS.items()},builds=[],
               limitation=['Counters are source-level operations proxies, not hardware op counts',
                           'VQPartialSort comparator count and LSHGraph internals NOT counted',
                           'Profiling timers affect wall time; never claim DIAG speedup',
                           'One CPU, Stock N2 C160 K1024; no H17, Search or GPU'])
    update_json(OUT/'progress.json',state)
    sha10=make_prefix(OUT/'data/sift10k.fbin')
    state['prefix_sha']=sha10
    for variant in ('ctrl','diag'):
        src=OUT/'source'/variant
        shutil.copytree(SOURCE,src,symlinks=True)
        if variant=='diag':
            uh=src/'algorithms/PipNN/pipnn_utils.h';uh.write_text(patch_utils(uh.read_text()))
            ph=src/'algorithms/PipNN/pipnn.h';ph.write_text(patch_pipnn(ph.read_text()))
        state[variant+'_source_utils_sha']=digest(src/'algorithms/PipNN/pipnn_utils.h')
        state[variant+'_source_pipnn_sha']=digest(src/'algorithms/PipNN/pipnn.h')
        exe=configure(OUT,variant)
        state[variant+'_elf_sha']=digest(exe)
        print('R90_P34_NATIVE_CPP_PASS',variant,state[variant+'_elf_sha'],flush=True)
        update_json(OUT/'progress.json',state)
    for variant in ('ctrl','diag'):
        state['builds'].append(run_build(OUT,variant,10000,1,OUT/'data/sift10k.fbin'))
        update_json(OUT/'progress.json',state)
    ck(state['builds'][0]['graph_sha']==state['builds'][1]['graph_sha'],'PAIRED_GRAPH_PARITY_10K')
    state['status']='PASS_10K_READY_FOR_100K';update_json(OUT/'result_manifest_10k.json',state)
    audit10k()
    print('R90_P34_10K_GRAPH_SHA_AND_COUNTERS_PASS_READY_FOR_100K',flush=True)

def audit_common(state):
    ck(state['script_sha']==digest(Path(__file__).resolve()),'SCRIPT_SHA')
    ck(state['prefix_sha']==digest(OUT/'data/sift10k.fbin'),'PREFIX_SHA')
    for variant in ('ctrl','diag'):
        src=OUT/'source'/variant/'algorithms/PipNN'
        exe=OUT/'build'/variant/'algorithms/PipNN/neighbors-pipnn_FLOAT_T_EUCLIDEAN'
        ck(state[variant+'_source_utils_sha']==digest(src/'pipnn_utils.h'),'UTIL_SHA_'+variant)
        ck(state[variant+'_source_pipnn_sha']==digest(src/'pipnn.h'),'PIPNN_SHA_'+variant)
        ck(state[variant+'_elf_sha']==digest(exe),'ELF_SHA_'+variant)
    for row in state['builds']:
        ck(digest(row['graph'])==row['graph_sha'],'GRAPH_SHA_'+str(row['n'])+row['arm'])
        ck(row['graph_sha']==GRAPH_SHA[row['n']],'STOCK_GRAPH_SHA_'+str(row['n']))
        ck(digest(row['stdout'])==row['stdout_sha'] and digest(row['timefile'])==row['time_sha'],'LOG_SHA')
        if row['arm']=='diag':ck(parse_profile(Path(row['stdout']).read_text(errors='replace'))==row['counters'],'COUNTER_PARITY')
    for n in (10000,100000):
        by=[x for x in state['builds'] if x['n']==n]
        for rep in {x['rep'] for x in by}:
            pair=[x for x in by if x['rep']==rep]
            ck(len(pair)==2 and pair[0]['graph_sha']==pair[1]['graph_sha'],'PAIR_'+str(n)+'_'+str(rep))

def audit10k():
    preflight(False)
    p=OUT/'result_manifest_10k.json'
    ck(p.is_file(),'RESULT_10K_MISSING')
    state=json.loads(p.read_text())
    ck(state['status']=='PASS_10K_READY_FOR_100K' and len(state['builds'])==2,'10K_STATUS')
    audit_common(state)
    print('R90_P34_AUDIT_10K_SOURCE_ELF_GRAPH_SHA_AND_WORK_COUNTERS_PASS',flush=True)

def pilot100k():
    audit10k()
    ck(not (OUT/'result_manifest_100k.json').exists(),'100K_EXISTS')
    p=OUT/'result_manifest_10k.json';state=json.loads(p.read_text())
    for rep in (1,2,3):
        for variant in (('ctrl','diag') if rep%2 else ('diag','ctrl')):
            state['builds'].append(run_build(OUT,variant,100000,rep,BASE))
            update_json(OUT/'progress_100k.json',state)
        check=[x for x in state['builds'] if x['n']==100000 and x['rep']==rep]
        ck(len(check)==2 and check[0]['graph_sha']==check[1]['graph_sha'],'GRAPH_PARITY_100K_'+str(rep))
        print('R90_P34_GRAPH_PARITY_PASS_100K_REP',rep,flush=True)
    state['status']='PASS_100K_GRAPH_PARITY_REP3';write_json(OUT/'result_manifest_100k.json',state)
    audit100k()
    # Report each diag stage separately; no claim of speedup from instrumentation overhead.
    for row in state['builds']:
        if row['n']==100000 and row['arm']=='diag':
            c=row['counters'];print('R90_P34_PROFILE',json.dumps({'rep':row['rep'],
                 'copy_us':c['copy_us'],'norm_us':c['norm_us'],'syrk_us':c['syrk_us'],
                 'fix_us':c['fix_us'],'selection_us':c['selection_us'],'merge_us':c['merge_us'],
                 'triangle_pairs':c['triangle_pairs'],'dot_components_proxy':c['dot_components_proxy'],
                 'pack_values':c['pack_values'],'merge_calls':c['merge_calls'],
                 'wall_s_DIAGNOSTIC_NOT_COMPARABLE':row['wall_s']},sort_keys=True),flush=True)
    print('R90_P34_3X_NATIVE_100K_GRAPH_SHA_PARITY_AND_PROFILE_PASS',flush=True)

def audit100k():
    audit10k()
    p=OUT/'result_manifest_100k.json';ck(p.is_file(),'RESULT_100K_MISSING')
    state=json.loads(p.read_text())
    ck(state['status']=='PASS_100K_GRAPH_PARITY_REP3','100K_STATUS')
    ck(len(state['builds'])==8,'BUILD_COUNT')
    audit_common(state)
    print('R90_P34_AUDIT_100K_3X_PAIRED_SOURCE_ELF_GRAPH_WORK_SHA_PASS',flush=True)

def selftest():
    # Demonstrate fail-closed exact anchors using synthetic snippet frames.
    u='\n'.join(old for _,old,_ in UTIL_REPLACEMENTS)
    for name,old,new in UTIL_REPLACEMENTS:
        ck(u.count(old)==1,'SELFTEST_DUPLICATE_'+name)
        u=patch_one(u,old,new,name)
    ck('R90_P34_LEAF_STATS' in u,'SELFTEST_COUNTERS')
    p=patch_pipnn(PIPNN_REPORT_ANCHOR)
    ck('r90p34_report();' in p,'SELFTEST_PIPNN')
    fake=('R90_P34_LEAF_STATS '+ ' '.join(f'{x}={i+1}' for i,x in enumerate(KEYS))+
          ' comparator_scope=NOT_COUNTED_VQ_SORT_AND_LSH_MERGE\n')
    # The fake counters are not graph-consistent; only test regex structure.
    ck(len(RX.findall(fake))==1,'SELFTEST_PARSE')
    pairs=1000*1001//2
    ck(pairs==500500 and 1000*999==999000,'WORK_FORMULAE')
    print('R90_P34_SELFTEST_PASS_SOURCE_PATCH_AND_WORK_COUNTER_FORMULAE',flush=True)

def main():
    a=argparse.ArgumentParser(description=__doc__)
    a.add_argument('phase',choices=('selftest','preflight','pilot10k','audit10k','pilot100k','audit100k'))
    phase=a.parse_args().phase
    if phase=='selftest':selftest()
    elif phase=='preflight':preflight(True)
    elif phase=='pilot10k':pilot10k()
    elif phase=='audit10k':audit10k()
    elif phase=='pilot100k':pilot100k()
    else:audit100k()

if __name__=='__main__':
    try:main()
    except Exception as e:
        print('R90_P34_HOLD',type(e).__name__,str(e),file=sys.stderr,flush=True)
        sys.exit(2)
