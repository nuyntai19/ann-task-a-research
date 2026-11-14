#!/usr/bin/env python3
"""Fail-closed instrumentation of upstream PiPNN 443a328 eigen_knn.
No writes unless --mode apply; destination is intended as a dedicated H26 git worktree.
"""
import argparse, pathlib, hashlib, sys

SCRIPT_VERSION = 'H26_P0_v1'
ANCHOR = '''template<typename GraphH, typename PR>
void eigen_knn(GraphH &G, parlay::sequence<uint32_t> &active_indices, PR &Points, size_t MST_DEG) {'''
PREP = '''  auto N = active_indices.size();
  eigen_build_distmat(active_indices, Points);
  float* dist_mat = (float*)get_dist_mat();'''
SORT = '''    size_t limit = std::min(MST_DEG, Q.size());
    VQPartialSort(Q.data(), Q.data() + Q.size(), limit);'''
SELECT_END = '''  }

  // the problem with this approach is that we only merge one neighbor at a time.'''
MERGE_END = '''    G.merge_neighbors(u, span_f);
    G.merge_neighbors(v, span_r);
  }
}'''
INCLUDES_ANCHOR = '#pragma once\n'
H26_INCLUDES = '''#include <chrono>
#include <cstdlib>
#include <cstring>
#include <cstdio>
#include <atomic>
#include <cstdint>
'''
H26_HELPERS = r'''
// H26-P0 profiling instrumentation, not an ANN contribution.
namespace h26exp {
using Clock = std::chrono::steady_clock;
inline unsigned long long ns(Clock::time_point a, Clock::time_point b) {
  return (unsigned long long)std::chrono::duration_cast<std::chrono::nanoseconds>(b-a).count();
}
struct Counters {
  std::atomic<unsigned long long> dist_ns{0}, select_ns{0}, merge_ns{0};
  std::atomic<unsigned long long> leaves{0}, rows{0}, proposals{0}, top2_checks{0};
  ~Counters() {
    const auto d=dist_ns.load(), s=select_ns.load(), m=merge_ns.load();
    const auto selector = std::getenv("H26_SELECTOR");
    std::fprintf(stderr,"H26_PROFILE,version,H26_P0_v1\n");
    std::fprintf(stderr,"H26_PROFILE,selector,%s\n",selector?selector:"stock");
    std::fprintf(stderr,"H26_PROFILE,dist_worker_ns,%llu\n",d);
    std::fprintf(stderr,"H26_PROFILE,select_worker_ns,%llu\n",s);
    std::fprintf(stderr,"H26_PROFILE,merge_worker_ns,%llu\n",m);
    std::fprintf(stderr,"H26_PROFILE,leaf_count,%llu\n",leaves.load());
    std::fprintf(stderr,"H26_PROFILE,rows,%llu\n",rows.load());
    std::fprintf(stderr,"H26_PROFILE,proposals,%llu\n",proposals.load());
    std::fprintf(stderr,"H26_PROFILE,top2_checks,%llu\n",top2_checks.load());
    std::fprintf(stderr,"H26_PROFILE,scope,worker_elapsed_sum_NOT_build_wall\n");
  }
};
inline Counters& counters() {static Counters c; return c;}
inline bool use_top2() {static const bool use = [](){
 const char* mode = std::getenv("H26_SELECTOR");
 return mode != nullptr && std::strcmp(mode,"top2")==0;
 }(); return use;
}
inline bool validation_enabled() {static const bool use = [](){
 const char* mode = std::getenv("H26_CHECK_TOP2");
 return mode != nullptr && std::strcmp(mode,"1")==0;
 }(); return use;
}
// Select exactly two smallest packed double values; only the first two slots
// are materialized. Does NOT change the number of leaf pair-distance calculations.
inline void scan2(std::vector<double>& q) {
  if (q.size()<2) return;
  double a=q[0], b=q[1];
  if (b<a) {const double t=a; a=b; b=t;}
  for(size_t j=2;j<q.size();++j) {
    const double v=q[j];
    if(v<a) {b=a; a=v;} else if(v<b) {b=v;}
  }
  q[0]=a; q[1]=b;
}
}
'''

def one(text, old, new, label):
    count=text.count(old)
    if count!=1: raise ValueError(f'{label}: expected 1 anchor, got {count}')
    return text.replace(old,new,1)

def transform(code):
    if 'H26_PROFILE,version' in code:
        raise ValueError('already instrumented; never apply twice')
    code=one(code,INCLUDES_ANCHOR,INCLUDES_ANCHOR+H26_INCLUDES,'includes')
    code=one(code,ANCHOR,H26_HELPERS+'\n'+ANCHOR+'\n  const auto h26_t0 = h26exp::Clock::now();','eigen_knn')
    code=one(code,PREP,'''  auto N = active_indices.size();
  eigen_build_distmat(active_indices, Points);
  const auto h26_t1 = h26exp::Clock::now();
  float* dist_mat = (float*)get_dist_mat();''','dist boundary')
    code=one(code,SORT,'''    size_t limit = std::min(MST_DEG, Q.size());
    if (h26exp::use_top2() && limit == 2) {
      // Optional sampled semantic validation: do not publish timing with this enabled.
      const bool verify = h26exp::validation_enabled() && ((active_indices[i] & 1023u)==0u);
      std::vector<double> ref;
      if (verify) {ref=Q; VQPartialSort(ref.data(),ref.data()+ref.size(),limit);}
      h26exp::scan2(Q);
      if (verify) {
        if (Q[0] != ref[0] || Q[1] != ref[1]) {
          std::fprintf(stderr,"H26_FAIL_CLOSED: Top2 mismatch at source %u\\n",active_indices[i]);
          std::abort();
        }
        h26exp::counters().top2_checks.fetch_add(1,std::memory_order_relaxed);
      }
    } else {
      VQPartialSort(Q.data(), Q.data() + Q.size(), limit);
    }''','sort')
    code=one(code,SELECT_END,'''  }
  const auto h26_t2 = h26exp::Clock::now();

  // the problem with this approach is that we only merge one neighbor at a time.''','selection boundary')
    code=one(code,MERGE_END,'''    G.merge_neighbors(u, span_f);
    G.merge_neighbors(v, span_r);
  }
  const auto h26_t3 = h26exp::Clock::now();
  auto& h26_c=h26exp::counters();
  h26_c.dist_ns.fetch_add(h26exp::ns(h26_t0,h26_t1),std::memory_order_relaxed);
  h26_c.select_ns.fetch_add(h26exp::ns(h26_t1,h26_t2),std::memory_order_relaxed);
  h26_c.merge_ns.fetch_add(h26exp::ns(h26_t2,h26_t3),std::memory_order_relaxed);
  h26_c.leaves.fetch_add(1,std::memory_order_relaxed);
  h26_c.rows.fetch_add(N,std::memory_order_relaxed);
  h26_c.proposals.fetch_add(directed_edges.size(),std::memory_order_relaxed);
}''','merge boundary')
    return code

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--file',required=True)
    p.add_argument('--mode',choices=['check','apply'],default='check')
    args=p.parse_args(); path=pathlib.Path(args.file)
    assert path.is_file(),f'File missing: {path}'
    old=path.read_text(encoding='utf-8')
    result=transform(old)
    print('H26_INSTRUMENT_CHECK_PASS', 'base_sha256='+hashlib.sha256(old.encode()).hexdigest(), 'patched_sha256='+hashlib.sha256(result.encode()).hexdigest())
    if args.mode=='apply':
        backup=path.with_suffix(path.suffix+'.H26_UNMODIFIED')
        if backup.exists(): raise RuntimeError('backup exists; refusing overwrite')
        backup.write_text(old,encoding='utf-8')
        path.write_text(result,encoding='utf-8')
        print('H26_INSTRUMENT_APPLIED',path)
    else: print('DRY_RUN_ONLY')
if __name__=='__main__':
    try:main()
    except Exception as exc: print('H26_FAIL_CLOSED:',exc,file=sys.stderr);sys.exit(2)
