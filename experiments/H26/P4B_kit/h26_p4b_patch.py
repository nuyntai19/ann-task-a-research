#!/usr/bin/env python3
"""Strict, single-match H26-P4b patches. Observational lock sampling only."""
P4B_HELPER = r'''
// H26-P4b: low-rate sampled LSHGraph lock wait/hold telemetry.
// Observation only: sampled steady_clock elapsed times can include OS preemption.
namespace h26p4b {
using Clock = std::chrono::steady_clock;
using Tick = Clock::time_point;
inline unsigned long long ns(Tick a, Tick b) {
  return (unsigned long long)std::chrono::duration_cast<std::chrono::nanoseconds>(b-a).count();
}
struct Record {
  uint64_t wait_ns, hold_ns;
  uint32_t vertex, worker;
};
struct Recorder {
  bool enabled=false;
  unsigned sample_mod=1024;
  bool prepared=false;
  std::vector<Record> data;
  std::atomic<size_t> used{0};
  Recorder() {
    const char* on=std::getenv("H26P4B_LOCK_ENABLE");
    enabled = (on && std::strcmp(on,"1")==0);
    if (enabled) {
      const char* sm=std::getenv("H26P4B_SAMPLE_MOD");
      if (sm && *sm) {
        char *end=nullptr;
        unsigned long z=std::strtoul(sm,&end,10);
        if(!end || *end || z<512 || z>8192 || (z&(z-1))!=0) {
          std::fprintf(stderr,"H26P4B_FAIL_CLOSED: sample_mod must be power of two in [512,8192]\n");
          std::abort();
        }
        sample_mod=(unsigned)z;
      }
    }
  }
  void prepare(size_t buckets) {
    if(!enabled) return;
    if(prepared || buckets!=85529) {
      std::fprintf(stderr,"H26P4B_FAIL_CLOSED: unexpected leaf batch %zu\n",buckets);
      std::abort();
    }
    prepared=true;
    data.resize(300000); // P4b 120M calls, min 1/512 sampling; fail-closed if unexpectedly over cap.
  }
  inline bool sample() const {
    if(!enabled) return false;
    // Per-thread pseudo-random sample. No global shared counter on the hot path.
    static thread_local uint32_t state = 0x9e3779b9U ^
      (uint32_t)std::hash<std::thread::id>{}(std::this_thread::get_id());
    if(state==0) state=0x7f4a7c15U;
    state ^= state<<13; state ^= state>>17; state ^= state<<5;
    return (state & (sample_mod-1U))==0U;
  }
  inline uint32_t worker() const {
    static std::atomic<uint32_t> next{0};
    static thread_local uint32_t token=next.fetch_add(1,std::memory_order_relaxed);
    return token;
  }
  void record(uint32_t vertex, Tick before, Tick acquired, Tick before_unlock) {
    if(!prepared || before>acquired || acquired>before_unlock) {
      std::fprintf(stderr,"H26P4B_FAIL_CLOSED: invalid sampled interval\n");
      std::abort();
    }
    size_t ix=used.fetch_add(1,std::memory_order_relaxed);
    if(ix>=data.size()) {
      std::fprintf(stderr,"H26P4B_FAIL_CLOSED: lock sample buffer exhausted\n");
      std::abort();
    }
    data[ix]={ns(before,acquired),ns(acquired,before_unlock),vertex,worker()};
  }
  ~Recorder() {
    if(!enabled) {std::fprintf(stderr,"H26P4B_LOCK,enabled,0\n");return;}
    const char* path=std::getenv("H26P4B_LOCK_TRACE_FILE");
    if(!prepared || !path || !*path) {
      std::fprintf(stderr,"H26P4B_FAIL_CLOSED: missing output path/preparation\n");
      std::abort();
    }
    FILE* f=std::fopen(path,"w");
    if(!f) {std::fprintf(stderr,"H26P4B_FAIL_CLOSED: cannot create sample CSV\n");std::abort();}
    std::fprintf(f,"wait_ns,hold_ns,vertex,worker\n");
    size_t n=used.load(std::memory_order_relaxed);
    for(size_t i=0;i<n;++i) {
      const Record &v=data[i];
      std::fprintf(f,"%llu,%llu,%u,%u\n",(unsigned long long)v.wait_ns,
          (unsigned long long)v.hold_ns,v.vertex,v.worker);
    }
    if(std::fclose(f)!=0) {std::fprintf(stderr,"H26P4B_FAIL_CLOSED: CSV flush failed\n");std::abort();}
    std::fprintf(stderr,"H26P4B_LOCK,version,H26P4B_v1\n");
    std::fprintf(stderr,"H26P4B_LOCK,enabled,1\n");
    std::fprintf(stderr,"H26P4B_LOCK,sample_mod,%u\n",sample_mod);
    std::fprintf(stderr,"H26P4B_LOCK,samples,%llu\n",(unsigned long long)n);
  }
};
inline Recorder& recorder() {static Recorder r;return r;}
inline void prepare(size_t buckets) {recorder().prepare(buckets);}
} // namespace h26p4b
'''

def one(s,a,b,label):
    n=s.count(a)
    if n!=1: raise RuntimeError(f'{label}: expected 1 exact anchor; got {n}')
    return s.replace(a,b,1)

def patch_graph(src):
    if 'H26P4B_LOCK' in src:raise RuntimeError('Graph header already instrumented')
    anchor='#include <atomic>\n'
    extra='#include <chrono>\n#include <cstdint>\n#include <cstdlib>\n#include <cstring>\n#include <cstdio>\n#include <thread>\n#include <functional>\n#include <vector>\n'
    src=one(src,anchor,anchor+extra,'graph include')
    lsh='template<typename indexType_, typename distanceType_, typename sketchHash>\nstruct LSHGraph {'
    src=one(src,lsh,P4B_HELPER+'\n'+lsh,'insert helper before LSHGraph')
    start='template<typename rangeType>\nvoid merge_neighbors(const size_t i, const rangeType& r) {\n  locks[i].Lock();'
    replace='''template<typename rangeType>
void merge_neighbors(const size_t i, const rangeType& r) {
  const bool h26p4b_sample = h26p4b::recorder().sample();
  h26p4b::Tick h26p4b_before{}, h26p4b_acquired{}, h26p4b_end{};
  if(h26p4b_sample) h26p4b_before=h26p4b::Clock::now();
  locks[i].Lock();
  if(h26p4b_sample) h26p4b_acquired=h26p4b::Clock::now();'''
    src=one(src,start,replace,'active LSH merge acquire')
    end='''  sentinel->point_id = static_cast<indexType>(deg);
  locks[i].Unlock();
}

//   template<typename rangeType>'''
    replacement='''  sentinel->point_id = static_cast<indexType>(deg);
  if(h26p4b_sample) h26p4b_end=h26p4b::Clock::now();
  locks[i].Unlock();
  // Record AFTER unlock to exclude logging/atomic ticket from lock hold time.
  if(h26p4b_sample) h26p4b::recorder().record((uint32_t)i,h26p4b_before,h26p4b_acquired,h26p4b_end);
}

//   template<typename rangeType>'''
    src=one(src,end,replacement,'active LSH merge release')
    return src

def patch_cluster(src):
    if 'H26P4B_LOCK' in src:raise RuntimeError('Already patched cluster')
    anchor='''    std::cout << "Building leaves:" << std::endl;
     parlay::parallel_for(0, buckets.size(), [&](size_t i) {'''
    return one(src,anchor,'''    std::cout << "Building leaves:" << std::endl;
    h26p4b::prepare(buckets.size()); // P4b: one cluster-round SIFT1M
     parlay::parallel_for(0, buckets.size(), [&](size_t i) {''','parallel for anchor')

def patch_cmake(src):
    return one(src,'add_subdirectory(${parlaylib_SOURCE_DIR} EXCLUDE_FROM_ALL)',
               'add_subdirectory(${parlaylib_SOURCE_DIR} ${parlaylib_BINARY_DIR} EXCLUDE_FROM_ALL)',
               'out-of-tree Parlay CMake fix')
