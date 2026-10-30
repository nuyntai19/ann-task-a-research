#!/usr/bin/env python3
"""H32-R45: copy-only native ParlayANN query trace and offline diagnostic.

- Pinned ParlayANN source commit, original binary SHA, original R26a graph SHA.
- No modification to the source repo, source binary, graph or candidate pool.
- Trace ONLY selected query IDs. R45 is a research diagnostic, not an ANN algorithm.
"""
from __future__ import annotations
import argparse
import collections
import hashlib
import json
import os
from pathlib import Path
import re
import random
import struct
import shutil
import subprocess
import sys
import tempfile
import textwrap

PARLAY_COMMIT='a48c6a34e5f959190992aa531cc18454cfcc3dd3'
BINARY_SHA='ee6b9c0bec2f32fe00607f3facc73691d2dca2d5158e84e69c226b3cd219c9a8'
GRAPH_SHA='d497f6d19fff4b7db6436f960d036755e375be92483c03ec0b9ed61968d17bef'
R26A_N=1_000_000
Q=100
K=10
DEFAULT_LIMIT=256

SEARCH_ANCHOR='  auto [beamElts, visitedElts] = pairElts;\n  if (beamElts.size() < QP.k) {'
EVAL_ANCHOR='  float recall = 0.0;'

SEARCH_HOOK=r'''  // R45 diagnostic. READ-ONLY, no mutation of search state.
  if (const char* r45_dir = std::getenv("ANN_R45_TRACE_DIR")) {
    const char* r45_id_list = std::getenv("ANN_R45_TRACE_QIDS");
    long r45_id = static_cast<long>(p.id());
    bool r45_selected = r45_id_list && r45_id >= 0 &&
      (std::string(",") + r45_id_list + ",").find(std::string(",") + std::to_string(r45_id) + ",") != std::string::npos;
    if (r45_selected && QP.beamSize == 100) {
      std::ofstream r45_out(std::string(r45_dir)+"/q_"+std::to_string(r45_id)+".trace", std::ios::app);
      if (!r45_out.is_open()) { std::cerr << "R45_TRACE_OPEN_ERROR q=" << r45_id << std::endl; std::abort(); }
      r45_out << "SEARCH|" << r45_id << "|" << QP.beamSize << "|" << QP.k
              << "|" << (use_rerank ? 1 : 0) << "|" << dist_cmps << "|";
      for (auto r45_x : beamElts) r45_out << r45_x.first << ",";
      r45_out << "|";
      for (auto r45_x : visitedElts) r45_out << r45_x.first << ",";
      r45_out << "\\n";
      if (!r45_out.good()) { std::cerr << "R45_TRACE_WRITE_ERROR q=" << r45_id << std::endl; std::abort(); }
    }
  }
'''.replace('"\\n"','"\n"')

EVAL_HOOK=r'''  // R45 evaluation trace: exactly the native tie-aware GT inclusion rule.
  if (const char* r45_dir = std::getenv("ANN_R45_TRACE_DIR")) {
    const char* r45_ids = std::getenv("ANN_R45_TRACE_QIDS");
    if (r45_ids && QP.beamSize == 100 && GT.size() > 0 && k > 0) {
      std::string r45_list = std::string(",") + r45_ids + ",";
      for (size_t r45_i = 0; r45_i < Query_Points.size(); ++r45_i) {
        if (r45_list.find(std::string(",")+std::to_string(r45_i)+",") == std::string::npos) continue;
        typename PointRange::Point r45_qp = Query_Points[r45_i];
        float r45_cut = r45_qp.distance(Base_Points[GT.coordinates(r45_i, k-1)]);
        std::ofstream r45_out(std::string(r45_dir)+"/q_"+std::to_string(r45_i)+".trace", std::ios::app);
        if (!r45_out.is_open()) { std::cerr << "R45_TRACE_EVAL_OPEN_ERROR" << std::endl; std::abort(); }
        r45_out << "EVAL|" << r45_i << "|" << QP.beamSize << "|" << k << "|";
        for (auto r45_x : all_ngh[r45_i]) r45_out << r45_x << ",";
        r45_out << "|";
        for (long r45_j=0; r45_j<k; ++r45_j) r45_out << GT.coordinates(r45_i,r45_j) << ",";
        r45_out << "|";
        for (long r45_j=0; r45_j<GT.dimension(); ++r45_j) {
          if (r45_j < k || r45_qp.distance(Base_Points[GT.coordinates(r45_i,r45_j)]) == r45_cut)
            r45_out << GT.coordinates(r45_i,r45_j) << ",";
        }
        r45_out << "\\n";
        if (!r45_out.good()) { std::cerr << "R45_TRACE_EVAL_WRITE_ERROR" << std::endl; std::abort(); }
      }
    }
  }
'''.replace('"\\n"','"\n"')

# C++ snippets above need a literal backslash-n inside the generated file.
SEARCH_HOOK=SEARCH_HOOK.replace(r'\\n',r'\n')
EVAL_HOOK=EVAL_HOOK.replace(r'\\n',r'\n')


def hashfile(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for c in iter(lambda:f.read(4*1024*1024),b''): h.update(c)
    return h.hexdigest()

def cmdrun(cmd, cwd=None, env=None, logfile=None):
    if logfile:
        with open(logfile,'w') as f:
            cp=subprocess.run(cmd,cwd=cwd,env=env,stdout=f,stderr=subprocess.STDOUT,check=False)
        if cp.returncode: raise RuntimeError(f'Command failed exit={cp.returncode}: {cmd} — inspect {logfile}')
    else:
        subprocess.run(cmd,cwd=cwd,env=env,check=True)

def inject(h,snippet,anchor):
    if h.count(anchor)!=1:
        raise RuntimeError(f'Source anchor count {h.count(anchor)}, expected exactly one: {anchor[:64]!r}')
    return h.replace(anchor,anchor.split('\n')[0]+'\n'+snippet+anchor[len(anchor.split('\n')[0])+1:],1)

def patch_source(beam,recall):
    b=Path(beam).read_text()
    c=Path(recall).read_text()
    if 'R45 diagnostic.' in b or 'R45 evaluation trace' in c:
        raise ValueError('Already patched, refusing to apply twice')
    b=inject(b,SEARCH_HOOK,SEARCH_ANCHOR)
    c=inject(c,EVAL_HOOK,EVAL_ANCHOR)
    b=b.replace('#include <queue>','#include <queue>\n#include <cstdlib>\n#include <fstream>\n#include <string>',1)
    c=c.replace('#include <set>','#include <set>\n#include <cstdlib>\n#include <fstream>\n#include <string>',1)
    Path(beam).write_text(b)
    Path(recall).write_text(c)
    assert 'R45 diagnostic' in b and 'R45 evaluation trace' in c
    return b,c

def prepare(args):
    repo=Path(args.source).resolve(); out=Path(args.out).resolve()
    if not (repo/'algorithms/utils/beamSearch.h').is_file():raise ValueError('Not a ParlayANN source tree')
    head=subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD'],text=True).strip()
    if head!=PARLAY_COMMIT:raise RuntimeError(f'Wrong source commit {head}; expected {PARLAY_COMMIT}')
    for relative in ('algorithms/utils/beamSearch.h','algorithms/utils/check_nn_recall.h'):
        clean=subprocess.check_output(['git','-C',str(repo),'show',f'HEAD:{relative}'])
        actual=(repo/relative).read_bytes()
        if clean != actual:raise RuntimeError(f'Local pinned header modified: {relative}; refusing source instrumentation')
    if out.exists():raise FileExistsError(f'Refuse to overwrite copy {out}')
    try:
        shutil.copytree(repo,out,symlinks=True,ignore=shutil.ignore_patterns('.git','*.o','*.a'))
        before={p:hashfile(out/p) for p in ('algorithms/utils/beamSearch.h','algorithms/utils/check_nn_recall.h')}
        patch_source(out/'algorithms/utils/beamSearch.h',out/'algorithms/utils/check_nn_recall.h')
        manifest={'audit':'R45_NATIVE_QUERY_TRACE_SOURCE_COPY','pinned_commit':head,
                  'original_source':str(repo),'copy':str(out),
                  'header_original_sha256':before,
                  'header_patched_sha256':{p:hashfile(out/p) for p in before}}
        (out/'R45_TRACE_MANIFEST.json').write_text(json.dumps(manifest,indent=2)+'\n')
        print('R45_PATCH_COPY_PASS',out)
        if args.build:
            # Stock Makefile uses `neighbors` and src/bench dependencies.
            cmdrun(['make','-j2','OPENMP=1','neighbors'],cwd=out/'algorithms/vamana',logfile=out/'R45_BUILD.log')
            exe=out/'algorithms/vamana/neighbors'
            if not exe.is_file():raise RuntimeError('Build finished without neighbors executable')
            print('R45_BUILD_PASS',exe,'SHA',hashfile(exe))
    except Exception:
        print('ERROR: only the isolated copy might be partially written; original repo untouched',file=sys.stderr)
        raise

def parse_ids(s):
    if s and not s.endswith(','):raise ValueError('Expected trailing comma in ID list')
    return [int(z) for z in s.split(',') if z]

def read_trace(path):
    lines=Path(path).read_text().splitlines()
    S=[];E=[]
    for l in lines:
        parts=l.split('|')
        if parts[0]=='SEARCH' and len(parts)==8:
            _,qid,beam,k,rerank,cmps,front,visited=parts
            S.append({'qid':int(qid),'beam':int(beam),'k':int(k),'rerank':int(rerank),
                      'cmps':int(cmps),'frontier':parse_ids(front),'visited':parse_ids(visited)})
        elif parts[0]=='EVAL' and len(parts)==7:
            _,qid,beam,k,returned,gt10,gtallowed=parts
            E.append({'qid':int(qid),'beam':int(beam),'k':int(k),'returned':parse_ids(returned),
                      'gt10':parse_ids(gt10),'allowed':parse_ids(gtallowed)})
        else: raise ValueError(f'Unexpected trace record: {l[:200]}')
    return S,E

def parse_native(log):
    r=re.compile(r'search: Q=(\d+), k=(\d+), limit=(\d+), recall=([\d.eE+\-]+), visited=([\d.eE+\-]+), comparisons=([\d.eE+\-]+), QPS=([\d.eE+\-]+), ctime=([\d.eE+\-]+)')
    found=[{'Q':int(m[1]),'k':int(m[2]),'limit':int(m[3]),'recall':float(m[4]),
            'visited':float(m[5]),'comparisons':float(m[6]),'QPS':float(m[7])}
           for m in r.finditer(Path(log).read_text())]
    if len(found)!=5:raise ValueError(f'{log} expected 5 native search records, got {len(found)}')
    return found

def analyze(args):
    from ann_task_a_r37_coreslack import Graph
    graph=Path(args.graph).resolve()
    if hashfile(graph)!=GRAPH_SHA:raise RuntimeError('Graph SHA mismatch; refusing attribution')
    g=Graph(str(graph))
    if g.n!=R26A_N or g.maxdeg!=32:raise RuntimeError('Graph dimensions mismatch')
    trace_dir=Path(args.traces)
    selected=json.loads(Path(args.qids_file).read_text())
    ids=selected['selected_query_ids']
    if len(ids)!=args.limit or len(set(ids))!=len(ids) or ids!=sorted(ids):
        raise ValueError('Invalid deterministic query sample list/count')
    actual_sha=hashlib.sha256(struct.pack('<'+'I'*len(ids),*ids)).hexdigest()
    if actual_sha!=selected['sample_sha256']:raise ValueError('Sample SHA mismatch')
    files=sorted(trace_dir.glob('q_*.trace'))
    if len(files)!=args.limit:raise ValueError(f'Expected {args.limit} distinct query traces, found {len(files)}')
    if sorted(f.name for f in files)!=sorted(f'q_{i}.trace' for i in ids):raise ValueError('Trace IDs != selected query IDs')
    summary=collections.Counter()
    missed_by_q=[]
    same_5=0
    for i in ids:
        source=trace_dir/f'q_{i}.trace'
        S,E=read_trace(source)
        if len(S)!=5 or len(E)!=5:raise ValueError(f'q={i}: expect 5 SEARCH and 5 EVAL, got {len(S)},{len(E)}')
        if not all(t['qid']==i and t['beam']==Q and t['k']==K for t in S+E):raise ValueError(f'q={i}: wrong query/beam/k IDs')
        if any(t['rerank'] for t in S):raise RuntimeError(f'q={i}: quantized/rerank path unexpected; review code before interpreting')
        if len(set(map(str,S)))==1 and len(set(map(str,E)))==1: same_5+=1
        else:raise RuntimeError(f"q={i}: traces differ across native repeated passes; parity gate fails")
        s=S[0];e=E[0]; returned=set(e['returned']);visited=set(s['visited']);front=set(s['frontier'])
        if len(e['returned'])!=K or len(e['gt10'])!=K:raise ValueError('Malformed Top-k length')
        if len(front)!=len(s['frontier']) or len(visited)!=len(s['visited']):raise ValueError('Duplicate IDs in frontier/visited')
        if set(e['returned'])!=set(s['frontier'][:K]):raise RuntimeError(f'q={i}: returned Top-K differs from pre-rerank frontier')
        exposed=set()
        for v in visited:
            exposed.update(int(z) for z in g.neighbors(v))
        row=[]
        for t in e['gt10']:
            if t in returned:continue
            if t in visited:category='expanded_but_not_returned'
            elif t in front:category='final_frontier_outside_k'
            elif t in exposed:category='adjacent_to_expanded_but_not_returned'
            else:category='not_adjacent_to_expanded'
            summary[category]+=1
            row.append({'GT':t,'category':category,'was_expanded':t in visited,
                        'in_final_frontier':t in front,'adjacent_to_expanded':t in exposed})
        summary['strict_GT10_hit']+=len(set(e['gt10'])&returned)
        summary['native_tie_eligible_hit']+=len(set(e['allowed'])&returned)
        summary['first10_gt_total']+=K
        summary['queries_with_any_strict_miss']+=bool(row)
        if row:missed_by_q.append({'query_id':i,'misses':row,
                                   'strict_hits':K-len(row),'native_tie_eligible_hits':len(set(e['allowed'])&returned),
                                   'visited_count':len(visited),'frontier_count':len(front),
                                   'distance_cmps':s['cmps']})
    baseline=parse_native(args.baseline_log);traced=parse_native(args.traced_log)
    for j,(b,t) in enumerate(zip(baseline,traced)):
        for k in ('Q','k','limit'):
            if b[k]!=t[k]:raise RuntimeError(f'Protocol mismatch run{j} field{k}')
        for k in ('recall','visited','comparisons'):
            if abs(b[k]-t[k])>1e-6*max(1,abs(b[k])):
                raise RuntimeError(f'Baseline/traced native parity FAIL run{j} field{k}: {b[k]} != {t[k]}')
    summary['queries_with_no_strict_miss']=args.limit-summary['queries_with_any_strict_miss']
    report={'audit':'R45_PINNED_NATIVE_QUERY_TRACE_DIAGNOSTIC',
            'query_sample':selected,
            'protocol':{'n_base':g.n,'graph_sha256':hashfile(graph),'Q':Q,'k':K,'traced_queries':args.limit,
                        'native_process_repeats':5,'source_commit':PARLAY_COMMIT},
            'baseline_native':baseline,'traced_native':traced,'parity':'PASS_RECALL_VISITED_COMPARISONS',
            'all_traced_queries_deterministic_across_5_repeats':same_5==args.limit,
            'counts':dict(summary),'missed_query_details':missed_by_q,
            'interpretation':{'adjacent_to_expanded':'Graph edge exposed, NOT proof candidate scored/retained; has_been_seen/cutoff may skip',
              'not_adjacent_to_expanded':'No direct edge from actually expanded vertex; not proof of global graph disconnection',
              'strict_GT10':'Can differ from native tie-aware recall, which can credit GT IDs past rank10 tied at rank10 distance'}}
    dest=Path(args.output);dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_text(json.dumps(report,indent=2)+'\n')
    print('R45_PARITY_PASS, REPEATS_PASS',args.limit)
    print('COUNTS',json.dumps(dict(summary),sort_keys=True))
    print('OUTPUT',dest)

def safe_file(path,pin,name):
    if not Path(path).is_file(): raise FileNotFoundError(f'{name}: {path}')
    got=hashfile(path)
    if got!=pin:raise RuntimeError(f'{name} SHA mismatch: got={got}, expected={pin}')

def run(args):
    safe_file(args.graph,GRAPH_SHA,'R26a graph')
    safe_file(args.baseline_binary,BINARY_SHA,'stock ParlayANN binary')
    tracer=Path(args.traced_binary)
    if not tracer.is_file():raise FileNotFoundError(tracer)
    if hashfile(tracer)==BINARY_SHA:raise RuntimeError('Trace binary is identical to baseline; did patch compile?')
    out=Path(args.out).resolve()
    if out.exists(): raise FileExistsError(f'R45 run output exists: {out}')
    out.mkdir(parents=True)
    traces=out/'traces';traces.mkdir()
    baseargs=['-data_type','float','-dist_func','Euclidian','-base_path',str(Path(args.base).resolve()),
              '-query_path',str(Path(args.queries).resolve()),'-gt_path',str(Path(args.gt).resolve()),
              '-graph_path',str(Path(args.graph).resolve()),'-Q','100','-k','10','-verbose']
    env=os.environ.copy()
    env.update({'OPENBLAS_NUM_THREADS':'1','OMP_NUM_THREADS':'1','PARLAY_NUM_THREADS':'1'})
    cpus=subprocess.check_output(['taskset','-pc',str(os.getpid())],text=True).strip()
    if args.limit<=0 or args.limit>10000: raise ValueError('limit must be between 1 and 10000')
    qids=sorted(random.Random(args.seed).sample(range(10000),args.limit))
    sample_sha=hashlib.sha256(struct.pack('<'+'I'*len(qids),*qids)).hexdigest()
    sample={'sample_method':'uniform_sample_without_replacement','seed':args.seed,'query_count_total':10000,
            'sample_count':args.limit,'sample_sha256':sample_sha,'selected_query_ids':qids}
    (out/'selected_queries.json').write_text(json.dumps(sample,indent=2)+'\n')
    # Pin to the supplied CPU ID only if OS affinity permits it.
    def launch(binary,log,traced):
        e=env.copy()
        if traced:
            e['ANN_R45_TRACE_DIR']=str(traces)
            e['ANN_R45_TRACE_QIDS']=','.join(map(str,qids))
        else:
            e.pop('ANN_R45_TRACE_DIR',None);e.pop('ANN_R45_TRACE_QIDS',None)
        cmd=['taskset','-c',str(args.cpu),str(Path(binary).resolve())]+baseargs
        cmdrun(cmd,env=e,logfile=out/log)
    (out/'command_manifest.json').write_text(json.dumps({'graph':str(Path(args.graph).resolve()),
           'graph_sha256':GRAPH_SHA,'base':args.base,'queries':args.queries,'gt':args.gt,
           'baseline_binary':str(Path(args.baseline_binary).resolve()),
           'baseline_binary_sha256':BINARY_SHA,'traced_binary':str(tracer.resolve()),
           'traced_binary_sha256':hashfile(tracer),'cpu':args.cpu,'limit':args.limit,
           'affinity_before':cpus,'selected_query_ids_sha256':sample_sha,'seed':args.seed},indent=2)+'\n')
    launch(args.baseline_binary,'baseline_native.log',False)
    launch(tracer,'traced_native.log',True)
    res=argparse.Namespace(graph=args.graph,traces=str(traces),limit=args.limit,
        qids_file=str(out/'selected_queries.json'),
        baseline_log=str(out/'baseline_native.log'),traced_log=str(out/'traced_native.log'),
        output=str(out/'R45_native_query_trace.json'))
    analyze(res)

def selftest():
    b=textwrap.dedent('''\
        #include <queue>
        void x(){
          auto [beamElts, visitedElts] = pairElts;
          if (beamElts.size() < QP.k) {
        }
    ''')
    c=textwrap.dedent('''\
        #include <set>
        void x(){
          query_time = t.next_time();
          
          float recall = 0.0;
        }
    ''')
    with tempfile.TemporaryDirectory() as t:
        a=Path(t)/'beamSearch.h';e=Path(t)/'check_nn_recall.h'
        a.write_text(b);e.write_text(c)
        aa,ee=patch_source(a,e)
        assert aa.count('R45 diagnostic')==1 and ee.count('R45 evaluation')==1
        assert 'std::ofstream' in aa and 'std::ofstream' in ee
        assert '<< "\\n";' in aa and '<< "\\n";' in ee
        try:patch_source(a,e)
        except ValueError:pass
        else:raise AssertionError('Double patch not rejected')
        trace=Path(t)/'q_0.trace'
        trace.write_text('SEARCH|0|100|10|0|21|1,2,3,|1,4,\nEVAL|0|100|10|1,2,|2,5,|2,5,9,\n')
        ss,ev=read_trace(trace)
        assert ss[0]['visited']==[1,4] and ev[0]['allowed']==[2,5,9]
        assert ss[0]['beam']==100
        try:read_trace(Path(t)/'bogus')
        except FileNotFoundError:pass
        else:raise AssertionError('Missing trace not detected')
    print('R45_SELFTEST_PASS: unique source anchors, duplicate protection, escaped C++ newline, trace parser')

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    sub=ap.add_subparsers(dest='cmd',required=True)
    sub.add_parser('selftest')
    p=sub.add_parser('prepare');p.add_argument('--source',default='src/ParlayANN');p.add_argument('--out',default='experiments/H45/ParlayANN-native-trace');p.add_argument('--build',action='store_true')
    p=sub.add_parser('run');p.add_argument('--graph',required=True);p.add_argument('--base',default='data/sift1m.fbin');p.add_argument('--queries',default='data/sift1m_queries.fbin');p.add_argument('--gt',default='data/sift1m_gt.ibin');p.add_argument('--baseline-binary',default='src/ParlayANN/algorithms/vamana/neighbors');p.add_argument('--traced-binary',default='experiments/H45/ParlayANN-native-trace/algorithms/vamana/neighbors');p.add_argument('--cpu',type=int,default=0);p.add_argument('--limit',type=int,default=256);p.add_argument('--seed',type=int,default=20261104);p.add_argument('--out',default='experiments/H45/native_q100_256')
    p=sub.add_parser('analyze');p.add_argument('--graph',required=True);p.add_argument('--traces',required=True);p.add_argument('--limit',type=int,default=256);p.add_argument('--qids-file',required=True);p.add_argument('--baseline-log',required=True);p.add_argument('--traced-log',required=True);p.add_argument('--output',required=True)
    args=ap.parse_args()
    if args.cmd=='selftest':selftest()
    elif args.cmd=='prepare':prepare(args)
    elif args.cmd=='run':run(args)
    else:analyze(args)

if __name__=='__main__':main()
