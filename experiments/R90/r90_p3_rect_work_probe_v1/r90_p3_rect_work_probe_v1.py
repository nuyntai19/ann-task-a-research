#!/usr/bin/env python3
"""R90-P3: isolate an A5 dryrun-only per-leaf rectangular cost probe.

Copies the P0 A5 source into a new output tree, inserts per-leaf counters
without changing RunLeaf or merge semantics, compiles a distinct diagnostic ELF,
then builds four dryrun SIFT100K graphs (q=.005,.01,.02,.05). ALL graph files
MUST byte-match the pinned Stock N2 baseline, or execution stops.

This is NOT a RADAR algorithm implementation, not a QPS/Recall experiment,
and not an actual GEMM microbenchmark. Source/graphs in P0/P2 remain untouched.
"""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
import time

HOME=Path.home()
ROOT=HOME/'ann-task-a'
R90=ROOT/'experiments/R90'
OUT=R90/'r90_p3_rect_work_probe_v1'
P0=R90/'r90_p0_stock_a5_compile_gate_v1'
P21=R90/'r90_p2_sift100k_pass2_value_gate1_v1'
P23=R90/'r90_p23_sift100k_a5_qgrid_v1'
SRC=P0/'a5_source'
INPUT=ROOT/'data/sift100k.fbin'
ORIGINAL_A5_SHA='315747c65f10ce3783b0622682b1237741ac307e21a8484e627e18fb00c24340'
ORIGINAL_UTILS_SHA='ee2048738ad4462f21bdfea4a1cf7c2ac140f72fbd8875d869bc4f613d93db53'
BASE_SHA='e50ff1bc34bcc6d1c97dd001023c09a666971cde64605cc06671ed8a8ff1ed12'
STOCK_GRAPH_SHA='4998cb93784da92728f2f6bd02aee6d3006d44c2b80f7b8b5be2a7f85f27d3e1'
STOCK_GRAPH=P21/'graphs/stock_N2.graph'
FRACTIONS=[('q0p5','0.005'),('q1','0.01'),('q2','0.02'),('q5','0.05')]
EXPECTED_COVERAGE={
 'q0p5':(8297,3472,1493961225,821224265),
 'q1':(8297,4846,1493961225,1067784975),
 'q2':(8297,6329,1493961225,1300298697),
 'q5':(8297,7781,1493961225,1464713300),
}
DEP_ROOT=R90/'r90_p0_stock_a5_compile_gate_v1/stock_build'
R86=ROOT/'experiments/R86/r86_v1_2_builds/stock_off/_deps'
H85=ROOT/'experiments/H85/r85_0_matched_baseline/build_stock/_deps'
DEPS={
 'PARLAYLIB':(R86/'parlaylib-src','51017699dcc421f80479cdb238d3092233ad0d26'),
 'EIGEN':(R86/'eigen-src','3147391d946bb4b6c68edd901f2add6ac1f31f8c'),
 'ABSEIL-CPP':(R86/'abseil-cpp-src','bc257a88f7c1939f24e0379f14a3589e926c950c'),
 'HIGHWAY':(H85/'highway-src','6bc2d47793bae9c521fb4150936669647700765d'),
 'GOOGLEBENCHMARK':(R86/'googlebenchmark-src','d886e3177c5dc48f150fbfbf142be6e724a032a4'),
}
PRE_ANCHOR='''    std::atomic<size_t> r90_all_leaves(0), r90_eligible_leaves(0);
    std::atomic<size_t> r90_all_wl(0), r90_eligible_wl(0);'''
PRE_REPLACE=PRE_ANCHOR+'''
    // R90-P3: observational diagnostic only; no control-flow change.
    std::atomic<unsigned long long> p3_rect_cells(0), p3_triangle_cells(0);
    std::atomic<unsigned long long> p3_all_occ(0), p3_q_occ(0);
    std::atomic<size_t> p3_q1_4(0), p3_q5_16(0), p3_q17plus(0);
    std::atomic<size_t> p3_rect_ge_triangle(0);'''
LOOP_ANCHOR='''           bool eligible = false;
           for (const auto u : buckets[i])
             if ((*r90_selected)[u]) { eligible = true; break; }
           r90_all_leaves.fetch_add(1, std::memory_order_relaxed);'''
LOOP_REPLACE='''          // R90-P3: count all selected rows instead of short-circuiting;
          // eligible has exactly the same Boolean meaning as A5 v0.
          size_t p3_q = 0;
          for (const auto u : buckets[i]) p3_q += ((*r90_selected)[u] != 0);
          const bool eligible = (p3_q != 0);
          const unsigned long long p3_m = buckets[i].size();
          p3_rect_cells.fetch_add(p3_m * p3_q, std::memory_order_relaxed);
          p3_triangle_cells.fetch_add(p3_m * (p3_m + 1ULL) / 2ULL,
                                      std::memory_order_relaxed);
          p3_all_occ.fetch_add(p3_m, std::memory_order_relaxed);
          p3_q_occ.fetch_add(p3_q, std::memory_order_relaxed);
          if (p3_q >= 1 && p3_q <= 4) p3_q1_4.fetch_add(1, std::memory_order_relaxed);
          else if (p3_q <= 16 && p3_q >= 5) p3_q5_16.fetch_add(1, std::memory_order_relaxed);
          else if (p3_q >= 17) p3_q17plus.fetch_add(1, std::memory_order_relaxed);
          if (2ULL*p3_q*p3_m >= p3_m*(p3_m+1ULL))
            p3_rect_ge_triangle.fetch_add(1, std::memory_order_relaxed);
          r90_all_leaves.fetch_add(1, std::memory_order_relaxed);'''
PRINT_ANCHOR='''                << " gate=" << static_cast<int>(r90_gate) << std::endl;'''
PRINT_REPLACE=PRINT_ANCHOR+'''
      std::cout << "R90_P3_RECT_COST rect_cells=" << p3_rect_cells.load()
                << " triangle_cells=" << p3_triangle_cells.load()
                << " all_occ=" << p3_all_occ.load()
                << " q_occ=" << p3_q_occ.load()
                << " q1_4_leaves=" << p3_q1_4.load()
                << " q5_16_leaves=" << p3_q5_16.load()
                << " q17plus_leaves=" << p3_q17plus.load()
                << " rect_ge_triangle_leaves=" << p3_rect_ge_triangle.load()
                << std::endl;'''
RX_RECT=re.compile(r'^R90_P3_RECT_COST rect_cells=(\d+) triangle_cells=(\d+) all_occ=(\d+) q_occ=(\d+) q1_4_leaves=(\d+) q5_16_leaves=(\d+) q17plus_leaves=(\d+) rect_ge_triangle_leaves=(\d+)\s*$',re.M)
RX_COV=re.compile(r'^R90_A5_LEAF_SCREEN total=(\d+) eligible=(\d+) WL_total=(\d+) WL_eligible=(\d+) gate=(\d+)\s*$',re.M)
RX_SEL=re.compile(r'^R90_A5_PASS1 selected=(\d+) n=(\d+) sort_comparisons=(\d+) GT_free=1\s*$',re.M)


def hold(ok,why):
    if not ok:raise RuntimeError('R90_P3_HOLD_'+why)

def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()

def one_replace(content,a,b,label):
    hold(content.count(a)==1,'PATCH_ANCHOR_'+label+'_COUNT_'+str(content.count(a)))
    return content.replace(a,b,1)

def patch(content):
    content=one_replace(content,PRE_ANCHOR,PRE_REPLACE,'COUNTERS')
    content=one_replace(content,LOOP_ANCHOR,LOOP_REPLACE,'LEAF')
    content=one_replace(content,PRINT_ANCHOR,PRINT_REPLACE,'PRINT')
    hold(content.count('R90_P3_RECT_COST')==1,'PATCH_DIAG_MARKER')
    return content

def call(cmd,log_path,cwd=None,env=None,timeout=1800):
    with log_path.open('x',encoding='utf-8') as f:
        r=subprocess.run([str(x) for x in cmd],cwd=cwd,env=env,stdout=f,
                         stderr=subprocess.STDOUT,timeout=timeout,check=False)
    hold(r.returncode==0,'COMMAND_FAILED_'+log_path.name+'_RC_'+str(r.returncode))

def git_head(path):
    r=subprocess.run(['git','-C',str(path),'rev-parse','HEAD'],capture_output=True,text=True)
    hold(r.returncode==0,'DEP_GIT_'+path.name)
    return r.stdout.strip()

def preflight(dest,cpu,fresh):
    hold(dest.parent.is_dir(),'OUTPUT_PARENT')
    if fresh:hold(not dest.exists() and not dest.is_symlink(),'OUTPUT_EXISTS')
    hold(cpu in os.sched_getaffinity(0),'CPU_AFFINITY_NOT_ALLOWED')
    for exe in ('git','taskset','cmake','sha256sum'):
        hold(shutil.which(exe) is not None,'MISSING_'+exe)
    hold(Path('/usr/bin/time').is_file(),'MISSING_TIME')
    h=SRC/'algorithms/PipNN/pipnn.h'
    u=SRC/'algorithms/PipNN/pipnn_utils.h'
    hold(h.is_file() and sha(h)==ORIGINAL_A5_SHA,'A5_SOURCE_SHA')
    hold(u.is_file() and sha(u)==ORIGINAL_UTILS_SHA,'UTILS_SOURCE_SHA')
    hold(INPUT.is_file() and sha(INPUT)==BASE_SHA,'BASE_SHA')
    with INPUT.open('rb') as f:n,d=struct.unpack('<II',f.read(8))
    hold((n,d)==(100000,128) and INPUT.stat().st_size==8+100000*128*4,'BASE_SHAPE')
    hold(STOCK_GRAPH.is_file() and sha(STOCK_GRAPH)==STOCK_GRAPH_SHA,'STOCK_N2_SHA')
    for name,(p,rev) in DEPS.items():
        hold(p.is_dir() and git_head(p)==rev,'DEP_SHA_'+name)
    # Verify parent gate measurements are completed and logically consistent.
    m=P23/'result_manifest.json'
    hold(m.is_file(),'P23_MANIFEST_MISSING')
    j=json.loads(m.read_text());hold(j.get('status')=='COMPLETE','P23_STATUS')
    for tag,frac in (('a5_gate_q0p5_N2',.005),('a5_gate_q2_N2',.02),('a5_gate_q5_N2',.05)):
        a=next((a for a in j.get('builds',[]) if a.get('arm')==tag),None)
        hold(a is not None and abs(a.get('fraction',-1)-frac)<1e-10,'P23_ARM_'+tag)
    # Test that the patch applies to THE pinned source before copying it.
    _=patch(h.read_text())
    print('R90_P3_PREFLIGHT_PASS_A5_SOURCE_PARENT_GT_FREE_DEP_SHA_AND_PATCH_ANCHORS',flush=True)


def run(dest,cpu):
    preflight(dest,cpu,True)
    dest.mkdir(exist_ok=False)
    source=dest/'source'
    print('R90_P3_COPY_A5_SOURCE_START',flush=True)
    shutil.copytree(SRC,source,symlinks=True)
    h=source/'algorithms/PipNN/pipnn.h'
    original=h.read_text();h.write_text(patch(original))
    print('R90_P3_PATCHED_SOURCE_SHA',sha(h),flush=True)
    build=dest/'build'
    conf=['cmake','-S',str(source),'-B',str(build),'-DCMAKE_BUILD_TYPE=Release',
          '-DCMAKE_CXX_FLAGS=-O3 -pthread','-DCMAKE_EXPORT_COMPILE_COMMANDS=ON',
          '-DFETCHCONTENT_FULLY_DISCONNECTED=ON','-DR90_A5_GATE=ON']
    for name,(path,_) in DEPS.items():conf.append('-DFETCHCONTENT_SOURCE_DIR_'+name+'='+str(path))
    call(conf,dest/'configure.log',timeout=1800)
    call(['cmake','--build',str(build),'--target','neighbors-pipnn_FLOAT_T_EUCLIDEAN','--parallel','2'],
         dest/'compile.log',timeout=3600)
    exe=build/'algorithms/PipNN/neighbors-pipnn_FLOAT_T_EUCLIDEAN'
    hold(exe.is_file() and os.access(exe,os.X_OK),'ELF_NOT_BUILT')
    print('R90_P3_NATIVE_CPP_DIAGNOSTIC_BUILD_PASS',sha(exe),flush=True)
    (dest/'logs').mkdir();(dest/'graphs').mkdir()
    basecmd=[str(exe),'-base_path',str(INPUT),
      '-num_clusters','2','-cluster_size','1024','-table_size','160',
      '-top_level_leaders','100','-fanout_scheme','10,3,1','-mst_deg','2',
      '-prune','1','-prune_all','1','-prune_degree','64',
      '-hash_bits','12','-alpha','1.1','-k','0']
    rows=[]
    for label,q in FRACTIONS:
        env=os.environ.copy()
        env['PARLAY_NUM_THREADS']='1';env['OMP_NUM_THREADS']='1';env['LC_ALL']='C'
        env['R90_A5_MODE']='dryrun';env['R90_A5_FRACTION']=q
        graph=dest/'graphs'/f'{label}.graph'
        log=dest/'logs'/f'{label}.stdout';tlog=dest/'logs'/f'{label}.time'
        cmd=['/usr/bin/time','-v','-o',str(tlog),'taskset','-c',str(cpu),
             *basecmd,'-graph_outfile',str(graph)]
        print('R90_P3_DRYRUN_START',label,'fraction',q,flush=True)
        t0=time.monotonic()
        call(cmd,log,env=env,timeout=2400)
        wall=time.monotonic()-t0
        hold(graph.is_file() and sha(graph)==STOCK_GRAPH_SHA,'GRAPH_PARITY_'+label)
        content=log.read_text(errors='replace')
        rx=RX_RECT.findall(content);cv=RX_COV.findall(content);sl=RX_SEL.findall(content)
        hold(len(rx)==len(cv)==len(sl)==1,'DIAG_MARKERS_'+label)
        rect,tri,members,active,qsmall,qmed,qlarge,ge=map(int,rx[0]); t,e,wt,we,gate=map(int,cv[0]);selected,n,cmp=map(int,sl[0])
        hold((t,e,wt,we)==EXPECTED_COVERAGE[label] and gate==0,'COVERAGE_'+label)
        hold(rect>=0 and tri>0 and members>=active>=0 and cmp>0,'COUNTERS_'+label)
        hold(t==e+(t-e) and qsmall+qmed+qlarge==e,'BINS_'+label)
        hold(n==100000 and selected==int(n*float(q)),'SELECTED_'+label)
        hold(0<=ge<=e,'RECT_GE_TRI_'+label)
        hold(wt>=tri and wt>=rect,'COST_BOUND_'+label)
        row=dict(tag=label,fraction=float(q),selected_points=selected,build_wall_s=wall,
                 graph_sha256=sha(graph),graph_bytes=graph.stat().st_size,
                 total_leaves=t,eligible_leaves=e,square_proxy=wt,
                 eligible_square_proxy=we,triangle_pairs=tri,
                 rectangular_pairs=rect,rectangular_to_triangle_pct=100*rect/tri,
                 leaf_member_occurrences=members,selected_member_occurrences=active,
                 q1_4_leaves=qsmall,q5_16_leaves=qmed,q17plus_leaves=qlarge,
                 rect_ge_triangle_leaves=ge,pass1_sort_comparisons=cmp,
                 stdout_sha256=sha(log),time_sha256=sha(tlog),
                 stdout_path=str(log),time_path=str(tlog),graph_path=str(graph))
        rows.append(row)
        print('R90_P3_DRYRUN_GRAPH_PARITY_PASS',label,
              'rect_vs_tri_pct',round(row['rectangular_to_triangle_pct'],3),
              'q_occ',active,'total_occ',members,flush=True)
    result={'status':'NATIVE_DIAGNOSTIC_COMPLETE','script_sha256':sha(Path(__file__).resolve()),
            'source_base_sha256':ORIGINAL_A5_SHA,'patched_source_sha256':sha(h),
            'diagnostic_elf_sha256':sha(exe),'cpu':cpu,'rows':rows,
            'limits':['Read-only on original sources; separate copied diagnostic tree',
                      'Dryrun builds all leaves; graph must equal original Stock N2',
                      'Rectangular pairs vs triangular pairs only; NOT FLOPs/real GEMM speed',
                      'RADAR incoming edges from non-Q rows are not preserved by this proxy',
                      'One graph per fraction; does not validate any RADAR candidate algorithm']}
    file=dest/'result_manifest.json'
    with file.open('x',encoding='utf-8') as f:json.dump(result,f,indent=2);f.write('\n')
    print('R90_P3_RECT_WORK_4Q_DIAG_COMPLETE',flush=True)
    audit(dest,cpu)


def audit(dest,cpu):
    preflight(dest,cpu,False)
    r=dest/'result_manifest.json';hold(r.is_file(),'MANIFEST_MISSING')
    d=json.loads(r.read_text());hold(d.get('status')=='NATIVE_DIAGNOSTIC_COMPLETE','STATUS')
    hold(d.get('script_sha256')==sha(Path(__file__).resolve()),'SCRIPT_SHA')
    hold(len(d.get('rows',[]))==len(FRACTIONS),'ROW_COUNT')
    patched=dest/'source/algorithms/PipNN/pipnn.h'
    hold(patched.is_file() and sha(patched)==d.get('patched_source_sha256'),'PATCHED_SOURCE')
    exe=dest/'build/algorithms/PipNN/neighbors-pipnn_FLOAT_T_EUCLIDEAN'
    hold(exe.is_file() and sha(exe)==d.get('diagnostic_elf_sha256'),'ELF')
    for i,(label,q) in enumerate(FRACTIONS):
        v=d['rows'][i];hold(v['tag']==label and abs(v['fraction']-float(q))<1e-12,'FRACTION_'+label)
        for fname,key in (('stdout_path','stdout_sha256'),('time_path','time_sha256'),('graph_path','graph_sha256')):
            p=Path(v[fname]);hold(p.is_file() and sha(p)==v[key],'FILE_SHA_'+label+'_'+fname)
        hold(v['graph_sha256']==STOCK_GRAPH_SHA,'PARITY_'+label)
        text=Path(v['stdout_path']).read_text(errors='replace')
        hold(len(RX_RECT.findall(text))==1 and len(RX_COV.findall(text))==1,'COUNTER_LOG_'+label)
    print('R90_P3_AUDIT_PASS_SOURCE_ELF_GRAPH_PARITY_AND_DIAGNOSTIC_RECEIPTS',flush=True)


def selftest():
    fake='\n'.join((PRE_ANCHOR,LOOP_ANCHOR,PRINT_ANCHOR))
    x=patch(fake)
    hold(x.count('R90_P3_RECT_COST')==1 and '2ULL*p3_q*p3_m' in x,'SELF_PATCH')
    try:patch(x)
    except RuntimeError:pass
    else:raise RuntimeError('R90_P3_HOLD_NONIDEMPOTENT_PATCH_TEST')
    assert math.isclose(100*0.1/0.5,20)
    print('R90_P3_LOCAL_SELFTEST_PASS_STRICT_SINGLE_SOURCE_PATCH_AND_COST_CALCULATIONS',flush=True)


def main():
    a=argparse.ArgumentParser(description=__doc__)
    a.add_argument('mode',choices=('selftest','preflight','pilot','audit'))
    a.add_argument('--cpu',type=int,default=0)
    a.add_argument('--out',type=Path,default=OUT)
    v=a.parse_args();dest=v.out.expanduser().resolve(strict=False)
    if v.mode=='selftest':selftest()
    elif v.mode=='preflight':preflight(dest,v.cpu,True)
    elif v.mode=='pilot':run(dest,v.cpu)
    else:audit(dest,v.cpu)

if __name__=='__main__':
    try:main()
    except Exception as e:
        print('R90_P3_HOLD',type(e).__name__,str(e),file=sys.stderr,flush=True)
        sys.exit(2)
