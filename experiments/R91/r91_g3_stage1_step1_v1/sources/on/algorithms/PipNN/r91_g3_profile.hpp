#pragma once
// R91-G3 diagnostic instrumentation only, NOT a production ANN algorithm.
// Tile-granular CLOCK_THREAD_CPUTIME_ID + steady_clock. Never instruments point loop.
#include <atomic>
#include <chrono>
#include <cstdint>
#include <cstdlib>
#include <ctime>
#include <iostream>

namespace r91g3 {
constexpr int DEPTHS = 32;
enum Phase { SAMPLE_ALLOC=0, LEADER_PACK=1, TILE_GATHER=2, GEMM=3,
             DIST_FINISH=4, SELECT=5, GROUP_FILTER=6, MERGE=7,
             SPLIT_FLATTEN=8, PHASES=9 };
inline const char* phase_names[PHASES] = {
 "sample_and_flat_alloc", "assign_leader_pack", "assign_tile_gather",
 "assign_gemm", "assign_dist_finish", "assign_select_vqsort",
 "group_by_index_filter", "merge_buckets", "split_and_flatten"};
inline std::atomic<std::uint64_t> cpu_ns[DEPTHS][PHASES]{};
inline std::atomic<std::uint64_t> wall_ns[DEPTHS][PHASES]{};
inline std::atomic<std::uint64_t> calls[DEPTHS][PHASES]{};
inline std::atomic<std::uint64_t> w_p[DEPTHS]{},w_a[DEPTHS]{},assigned[DEPTHS]{},leaders[DEPTHS]{},tiles[DEPTHS]{},fanout1[DEPTHS]{},fanout3[DEPTHS]{},fanout10[DEPTHS]{},fanout_other[DEPTHS]{};
inline std::uint64_t cpu_now() {
  timespec t{};
  if (::clock_gettime(CLOCK_THREAD_CPUTIME_ID,&t)) std::abort();
  return std::uint64_t(t.tv_sec)*1000000000ULL+std::uint64_t(t.tv_nsec);
}
inline std::uint64_t wall_now() {
 return std::chrono::duration_cast<std::chrono::nanoseconds>(std::chrono::steady_clock::now().time_since_epoch()).count();
}
inline int depth_slot(int d) { if(d<0 || d>=DEPTHS) {std::cerr<<"R91_G3_PROFILE_DEPTH_OVERFLOW\n";std::abort();}return d; }
struct Stamp {std::uint64_t cpu,wall;};
inline Stamp tic(){return {cpu_now(),wall_now()};}
inline void toc(Stamp st,Phase p,int d){
 auto nowcpu=cpu_now(),nowwall=wall_now(); d=depth_slot(d);
 cpu_ns[d][p].fetch_add(nowcpu-st.cpu,std::memory_order_relaxed);
 wall_ns[d][p].fetch_add(nowwall-st.wall,std::memory_order_relaxed);
 calls[d][p].fetch_add(1,std::memory_order_relaxed);
}
struct Scope {
 Stamp start; Phase phase; int depth;
 Scope(Phase p,int d):start(tic()),phase(p),depth(d){}
 ~Scope(){toc(start,phase,depth);}
 Scope(const Scope&)=delete;Scope& operator=(const Scope&)=delete;
};
inline void record_work(int depth,std::uint64_t n,std::uint64_t m,std::uint64_t fanout){
 int d=depth_slot(depth); w_p[d].fetch_add(n*m,std::memory_order_relaxed);
 w_a[d].fetch_add(n*fanout,std::memory_order_relaxed);
 assigned[d].fetch_add(n,std::memory_order_relaxed);
 leaders[d].fetch_add(m,std::memory_order_relaxed);
 (fanout==1?fanout1[d]:fanout==3?fanout3[d]:fanout==10?fanout10[d]:fanout_other[d]).fetch_add(1,std::memory_order_relaxed);
}
inline void record_tile(int depth){tiles[depth_slot(depth)].fetch_add(1,std::memory_order_relaxed);}
inline void reset(){
 for(int d=0;d<DEPTHS;d++){
  w_p[d].store(0);w_a[d].store(0);assigned[d].store(0);leaders[d].store(0);tiles[d].store(0);
  fanout1[d].store(0);fanout3[d].store(0);fanout10[d].store(0);fanout_other[d].store(0);
  for(int p=0;p<PHASES;p++){cpu_ns[d][p].store(0);wall_ns[d][p].store(0);calls[d][p].store(0);}
 }
}
inline void report(double bucket_wall_s){
 std::uint64_t sumcpu=0; for(int d=0;d<DEPTHS;d++)for(int p=0;p<PHASES;p++)sumcpu+=cpu_ns[d][p].load();
 int workers=1; if(const char* e=std::getenv("PARLAY_NUM_THREADS")){int x=std::atoi(e);if(x>0)workers=x;}
 std::cout<<"R91_G3_PROFILE_JSON {\"schema\":1,\"wall_buckets_s\":"<<bucket_wall_s
 <<",\"workers_env\":"<<workers<<",\"sum_exclusive_thread_cpu_s\":"<<(sumcpu*1e-9)
 <<",\"sampled_cpu_coverage_lower_bound\":"<<(bucket_wall_s>0?sumcpu*1e-9/(workers*bucket_wall_s):0)
 <<",\"note\":\"parent-scope CPU excludes child parallel work; scope wall across threads can overlap; do not force 100pct closure\",\"depth_work\":[";
 bool first=true;for(int d=0;d<DEPTHS;d++){if(!assigned[d].load()&&!tiles[d].load())continue;
  if(!first)std::cout<<",";first=false;
  std::cout<<"{\"depth\":"<<d<<",\"N_sum\":"<<assigned[d].load()
  <<",\"M_sum\":"<<leaders[d].load()<<",\"W_P\":"<<w_p[d].load()
  <<",\"W_A\":"<<w_a[d].load()<<",\"tiles\":"<<tiles[d].load()
  <<",\"fanout1_calls\":"<<fanout1[d].load()<<",\"fanout3_calls\":"<<fanout3[d].load()
  <<",\"fanout10_calls\":"<<fanout10[d].load()<<",\"fanout_other_calls\":"<<fanout_other[d].load()<<"}";
 }
 std::cout<<"],\"phases\":[";first=true;
 for(int d=0;d<DEPTHS;d++)for(int p=0;p<PHASES;p++)if(calls[d][p].load()){
  if(!first)std::cout<<",";first=false;
  std::cout<<"{\"depth\":"<<d<<",\"name\":\""<<phase_names[p]<<"\",\"calls\":"<<calls[d][p].load()
  <<",\"thread_cpu_s\":"<<(cpu_ns[d][p].load()*1e-9)
  <<",\"sum_wall_s\":"<<(wall_ns[d][p].load()*1e-9)<<"}";
 }
 std::cout<<"]}"<<std::endl;
}
} // namespace r91g3
