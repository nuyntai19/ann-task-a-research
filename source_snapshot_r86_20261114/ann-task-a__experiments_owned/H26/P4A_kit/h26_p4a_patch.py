#!/usr/bin/env python3
"""H26-P4a trace additions to the exact H26-P0 instrumented pipnn_utils.h.
Does not change Top-2 semantics; fail closed if P0 code shape differs.
"""
import hashlib

VERSION = 'H26P4A_leaf_timeline_v1'
FUNC_ANCHOR = '''template<typename GraphH, typename PR>
void eigen_knn(GraphH &G, parlay::sequence<uint32_t> &active_indices, PR &Points, size_t MST_DEG) {'''
TAIL_ANCHOR = '''  h26_c.proposals.fetch_add(directed_edges.size(),std::memory_order_relaxed);
}'''
LOOP_ANCHOR = '''    std::cout << "Building leaves:" << std::endl;
     parlay::parallel_for(0, buckets.size(), [&](size_t i) {'''
INCLUDE_ANCHOR = '#include <cstdint>\n'
INCLUDE_EXTRA = '#include <vector>\n#include <algorithm>\n'

P4_HELPER = r'''
// H26-P4a leaf execution timeline (one row per eigen_knn leaf).
// Diagnostic only: elapsed intervals are NOT true CPU busy time or work/span.
namespace h26p4 {
using Clock = std::chrono::steady_clock;
inline uint64_t nanos(Clock::time_point t) {
  return (uint64_t)std::chrono::duration_cast<std::chrono::nanoseconds>(t.time_since_epoch()).count();
}
struct Event {
  uint64_t start_ns=0, end_ns=0, dist_ns=0, select_ns=0, merge_ns=0;
  uint32_t leaf_size=0, worker_token=0;
};
struct Recorder {
  bool enabled=false;
  std::vector<Event> events;
  std::atomic<size_t> count{0};
  size_t expected_buckets=0;
  bool prepared=false;
  Recorder() {
    const char* v=std::getenv("H26P4_TRACE");
    enabled = v && std::strcmp(v,"1")==0;
  }
  void prepare(size_t n) {
    if(!enabled) return;
    if(prepared || n==0 || n>250000) {
      std::fprintf(stderr,"H26P4_FAIL_CLOSED: unexpected bucket batch n=%zu\n",n);
      std::abort();
    }
    prepared=true; expected_buckets=n; events.resize(n);
  }
  void record(size_t n, Clock::time_point t0, Clock::time_point t1,
              Clock::time_point t2, Clock::time_point t3, uint32_t tid) {
    if(!enabled) return;
    const auto i=count.fetch_add(1,std::memory_order_relaxed);
    if(!prepared || i>=events.size() || t3<t2 || t2<t1 || t1<t0) {
      std::fprintf(stderr,"H26P4_FAIL_CLOSED: corrupt or overflow event\n");
      std::abort();
    }
    Event e;
    e.start_ns=nanos(t0); e.end_ns=nanos(t3);
    e.dist_ns=(uint64_t)h26exp::ns(t0,t1);
    e.select_ns=(uint64_t)h26exp::ns(t1,t2);
    e.merge_ns=(uint64_t)h26exp::ns(t2,t3);
    e.leaf_size=(uint32_t)n; e.worker_token=tid;
    events[i]=e; // distinct atomic tickets => no concurrent writes to the same cell
  }
  ~Recorder() {
    if(!enabled) { std::fprintf(stderr,"H26P4_TRACE,enabled,0\n"); return; }
    const char* path=std::getenv("H26P4_TRACE_FILE");
    if(!path || !*path || !prepared) {
      std::fprintf(stderr,"H26P4_FAIL_CLOSED: missing trace path or preparation\n");
      std::abort();
    }
    FILE* f=std::fopen(path,"w");
    if(!f) {
      std::fprintf(stderr,"H26P4_FAIL_CLOSED: cannot open trace file\n");
      std::abort();
    }
    std::fprintf(f,"start_ns,end_ns,dist_ns,select_ns,merge_ns,leaf_size,worker_token\n");
    const auto used=count.load(std::memory_order_relaxed);
    for(size_t i=0;i<used;i++) {
      const auto &e=events[i];
      std::fprintf(f,"%llu,%llu,%llu,%llu,%llu,%u,%u\n",
        (unsigned long long)e.start_ns,(unsigned long long)e.end_ns,
        (unsigned long long)e.dist_ns,(unsigned long long)e.select_ns,
        (unsigned long long)e.merge_ns,(unsigned)e.leaf_size,(unsigned)e.worker_token);
    }
    if(std::fclose(f)!=0) {
      std::fprintf(stderr,"H26P4_FAIL_CLOSED: fclose failed\n");
      std::abort();
    }
    std::fprintf(stderr,"H26P4_TRACE,version,H26P4A_leaf_timeline_v1\n");
    std::fprintf(stderr,"H26P4_TRACE,enabled,1\n");
    std::fprintf(stderr,"H26P4_TRACE,events,%llu\n",(unsigned long long)used);
    std::fprintf(stderr,"H26P4_TRACE,buckets,%llu\n",(unsigned long long)expected_buckets);
  }
};
inline Recorder& recorder(){static Recorder r;return r;}
inline void prepare(size_t n){recorder().prepare(n);}
inline uint32_t worker_token(){
  static std::atomic<uint32_t> next{0};
  static thread_local uint32_t token=next.fetch_add(1,std::memory_order_relaxed);
  return token;
}
inline void record_leaf(size_t n,Clock::time_point t0,Clock::time_point t1,
                        Clock::time_point t2,Clock::time_point t3) {
  auto& r=recorder();
  if(!r.enabled) return;
  r.record(n,t0,t1,t2,t3,worker_token());
}
} // namespace h26p4
'''

def one(src, old, new, name):
    c=src.count(old)
    if c!=1:raise ValueError(f'{name}: expected exactly 1 anchor, found {c}; fail-closed')
    return src.replace(old,new,1)

def instrument_p0(code):
    if 'H26_PROFILE,version,H26_P0_v1' not in code or 'H26_SELECTOR' not in code:
        raise ValueError('Expected genuine H26-P0 instrumented source; refuses stock/H25')
    if 'H26P4_TRACE' in code:raise ValueError('Already contains H26P4 trace')
    code=one(code,INCLUDE_ANCHOR,INCLUDE_ANCHOR+INCLUDE_EXTRA,'includes')
    code=one(code,FUNC_ANCHOR,P4_HELPER+'\n'+FUNC_ANCHOR,'helper')
    code=one(code,TAIL_ANCHOR,'''  h26_c.proposals.fetch_add(directed_edges.size(),std::memory_order_relaxed);
  h26p4::record_leaf(N,h26_t0,h26_t1,h26_t2,h26_t3);
}''','trace after merge')
    return code

def instrument_cluster(code):
    if 'H26P4_TRACE' in code:raise ValueError('Already instrumented pipnn.h')
    return one(code,LOOP_ANCHOR,'''    std::cout << "Building leaves:" << std::endl;
    h26p4::prepare(buckets.size()); // P4a only: single cluster-round experiments
     parlay::parallel_for(0, buckets.size(), [&](size_t i) {''','parallel leaf loop')

def instrument_cmake(code):
    old='add_subdirectory(${parlaylib_SOURCE_DIR} EXCLUDE_FROM_ALL)'
    new='add_subdirectory(${parlaylib_SOURCE_DIR} ${parlaylib_BINARY_DIR} EXCLUDE_FROM_ALL)'
    return one(code,old,new,'out-of-tree ParlayLib CMake fix')
