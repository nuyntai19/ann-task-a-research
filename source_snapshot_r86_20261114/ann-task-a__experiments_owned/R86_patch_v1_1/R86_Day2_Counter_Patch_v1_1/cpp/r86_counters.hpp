#pragma once
// R86 v1.1 experimental instrumentation (logical work, not hardware instructions).
// Compile OFF by omitting R86_COUNTERS or defining it as 0.
#include <cstdint>
#include <string>
#if defined(R86_COUNTERS) && R86_COUNTERS
#include <array>
#include <atomic>
#include <cstdlib>
#include <fstream>
#include <initializer_list>
#include <mutex>
#include <stdexcept>
#include <vector>
#endif
namespace r86 {
enum class Metric : unsigned {
 W_P, W_A, W_L, W_pairs, leaf_count, leaf_size_sum, max_depth,
 proposals, merge_attempts, collision_same_id, collision_diff_id,
 hash_accept, hash_reject, hash_replace, hash_early_break, hash_full,
 hash_compute, hash_lb_compares, hash_moves, hash_worst_scan,
 hash_worst_compares, hash_insert_not_full, hash_replace_full,
 hash_same_id_rewrite, hash_diff_collision_rewrite, hash_diff_collision_reject,
 hash_bound_compares, hash_slot_writes,
 prune_distance_calls, top2_q_writes, partial_sort_calls,
 top2_comparisons, top2_assignments, top2_moves, COUNT
};
// A local per-call accumulator; HashPrune writes to it inside the node lock.
// Flushed to thread-local storage exactly once AFTER releasing the lock.
struct HashWork {
 std::uint64_t merge_attempts=0, collision_same_id=0, collision_diff_id=0;
 std::uint64_t hash_accept=0, hash_reject=0, hash_replace=0;
 std::uint64_t hash_early_break=0, hash_full=0, hash_compute=0;
 std::uint64_t hash_lb_compares=0, hash_moves=0, hash_worst_scan=0;
 std::uint64_t hash_worst_compares=0, hash_insert_not_full=0;
 std::uint64_t hash_replace_full=0, hash_same_id_rewrite=0;
 std::uint64_t hash_diff_collision_rewrite=0, hash_diff_collision_reject=0;
 std::uint64_t hash_bound_compares=0, hash_slot_writes=0;
};
#if defined(R86_COUNTERS) && R86_COUNTERS
constexpr unsigned MAX_PASSES=16;
constexpr unsigned MAX_DEPTH=64;
constexpr unsigned N_METRICS=static_cast<unsigned>(Metric::COUNT);
constexpr unsigned TOTAL=MAX_PASSES*(MAX_DEPTH+1)*N_METRICS;
struct Buffer {
 std::array<std::uint64_t,TOTAL> counts{};
 std::array<std::uint8_t,TOTAL> touched{};
};
struct Registry {
 std::mutex mutex;
 std::vector<Buffer*> buffers;
 std::atomic<int> active_pass{0};
};
inline Registry& registry() {static Registry* r=new Registry;return *r;}
inline Buffer& local() {
 static thread_local Buffer* p=[]() {
   Buffer* b=new Buffer;
   auto& r=registry();
   std::lock_guard<std::mutex> lk(r.mutex);
   r.buffers.push_back(b);
   return b;
 }();
 return *p;
}
inline std::size_t index(int pass,int depth,Metric m) {
 if(pass<0||pass>=static_cast<int>(MAX_PASSES)||depth < -1||depth>=static_cast<int>(MAX_DEPTH))
   throw std::out_of_range("R86 pass/depth out of range");
 return (static_cast<unsigned>(pass)*(MAX_DEPTH+1)+static_cast<unsigned>(depth+1))*N_METRICS+static_cast<unsigned>(m);
}
inline int active_pass() {return registry().active_pass.load(std::memory_order_relaxed);}
inline void set_active_pass(int pass) {
 if(pass<0||pass>=static_cast<int>(MAX_PASSES)) throw std::out_of_range("R86 pass id");
 registry().active_pass.store(pass,std::memory_order_release);
}
inline void declare_metric(Metric m,int depth=-1) {
 std::size_t pos=index(active_pass(),depth,m);
 local().touched[pos]=1;
}
inline void add(Metric m,std::uint64_t amount=1,int depth=-1) {
 std::size_t pos=index(active_pass(),depth,m);
 Buffer& b=local();b.touched[pos]=1;b.counts[pos]+=amount;
}
inline void record_hash_work(const HashWork& w) {
 // One registry load and one index base per merge, AFTER the node lock.
 // Counters here are logically independent; no atomic increments in the inner loop.
 auto& b=local();
 const std::size_t base=index(active_pass(),-1,Metric::W_P);
 auto store=[&](Metric m,std::uint64_t n) {
   const auto pos=base+static_cast<unsigned>(m);
   b.counts[pos]+=n;
   b.touched[pos]=1;
 };
 store(Metric::merge_attempts,w.merge_attempts);
 store(Metric::collision_same_id,w.collision_same_id);
 store(Metric::collision_diff_id,w.collision_diff_id);
 store(Metric::hash_accept,w.hash_accept);
 store(Metric::hash_reject,w.hash_reject);
 store(Metric::hash_replace,w.hash_replace);
 store(Metric::hash_early_break,w.hash_early_break);
 store(Metric::hash_full,w.hash_full);
 store(Metric::hash_compute,w.hash_compute);
 store(Metric::hash_lb_compares,w.hash_lb_compares);
 store(Metric::hash_moves,w.hash_moves);
 store(Metric::hash_worst_scan,w.hash_worst_scan);
 store(Metric::hash_worst_compares,w.hash_worst_compares);
 store(Metric::hash_insert_not_full,w.hash_insert_not_full);
 store(Metric::hash_replace_full,w.hash_replace_full);
 store(Metric::hash_same_id_rewrite,w.hash_same_id_rewrite);
 store(Metric::hash_diff_collision_rewrite,w.hash_diff_collision_rewrite);
 store(Metric::hash_diff_collision_reject,w.hash_diff_collision_reject);
 store(Metric::hash_bound_compares,w.hash_bound_compares);
 store(Metric::hash_slot_writes,w.hash_slot_writes);
}
inline void note_depth(int depth) {
 std::size_t pos=index(active_pass(),-1,Metric::max_depth);
 Buffer& b=local();b.touched[pos]=1;
 if(static_cast<std::uint64_t>(depth)>b.counts[pos]) b.counts[pos]=depth;
}
inline void begin_pass(int pass) {
 set_active_pass(pass);
 // A declared zero is different from a metric that was not instrumented.
 for(Metric m : {Metric::W_P,Metric::W_A,Metric::W_L,Metric::W_pairs,
                 Metric::leaf_count,Metric::leaf_size_sum,Metric::max_depth,
                 Metric::proposals,Metric::merge_attempts,
                 Metric::collision_same_id,Metric::collision_diff_id,
                 Metric::hash_accept,Metric::hash_reject,Metric::hash_replace,
                 Metric::hash_early_break,Metric::hash_full,
                 Metric::hash_compute,Metric::hash_lb_compares,Metric::hash_moves,
                 Metric::hash_worst_scan,Metric::hash_worst_compares,
                 Metric::hash_insert_not_full,Metric::hash_replace_full,
                 Metric::hash_same_id_rewrite,Metric::hash_diff_collision_rewrite,
                 Metric::hash_diff_collision_reject,Metric::hash_bound_compares,
                 Metric::hash_slot_writes,
                 Metric::top2_q_writes,Metric::partial_sort_calls}) declare_metric(m);
}
inline const char* metric_name(Metric m) {
 constexpr const char* names[]={"W_P","W_A","W_L","W_pairs","leaf_count",
 "leaf_size_sum","max_depth","proposals","merge_attempts",
 "collision_same_id","collision_diff_id","hash_accept","hash_reject",
 "hash_replace","hash_early_break","hash_full","hash_compute",
 "hash_lb_compares","hash_moves","hash_worst_scan","hash_worst_compares",
 "hash_insert_not_full","hash_replace_full","hash_same_id_rewrite",
 "hash_diff_collision_rewrite","hash_diff_collision_reject",
 "hash_bound_compares","hash_slot_writes","prune_distance_calls",
 "top2_q_writes","partial_sort_calls","top2_comparisons",
 "top2_assignments","top2_moves"};
 static_assert(sizeof(names)/sizeof(names[0])==N_METRICS,"metric names mismatch");
 return names[static_cast<unsigned>(m)];
}
inline std::string check_path(const char* env) {
 const char* p=std::getenv(env);
 if(!p||!*p||*p!='/') throw std::runtime_error(std::string("R86 requires absolute path env ")+env);
 std::ifstream existing(p);
 if(existing.good()) throw std::runtime_error(std::string("R86 refuses overwrite ")+p);
 return p;
}
inline void require_output_paths() {
 (void)check_path("R86_COUNTER_OUT");
 (void)check_path("R86_LEAF_SIZE_OUT");
 (void)check_path("R86_OCCUPANCY_OUT");
}
template<class Buckets>
inline void emit_leaf_sizes(const Buckets& buckets) {
 const char* p=std::getenv("R86_LEAF_SIZE_OUT");
 if(!p||!*p) throw std::runtime_error("R86_LEAF_SIZE_OUT unset");
 std::ofstream file(p,std::ios::app);
 if(!file) throw std::runtime_error("R86 cannot write leaf-size dump");
 const int pass=active_pass();
 for(const auto& b:buckets) {
   if(b.size()>1) file<<"{\"pass_id\":"<<pass<<",\"depth\":null,\"size\":"<<b.size()<<"}\n";
 }
 file.flush();
 if(!file) throw std::runtime_error("R86 failed leaf-size flush");
}
// Distinct, pre-prune, post-N-pass reservoir occupancy histogram.
// SFINAE/if constexpr keeps non-reservoir GraphH template instantiations buildable.
template<class G,class=void> struct has_capacity_degree : std::false_type {};
template<class G> struct has_capacity_degree<G, std::void_t<
 decltype(std::declval<G&>().kMaxDegree),
 decltype(std::declval<G&>().degree(std::size_t{}))>> : std::true_type {};
template<class GraphH>
inline void emit_reservoir_occupancy(GraphH& graph,std::size_t n) {
 if constexpr(has_capacity_degree<GraphH>::value) {
  const std::string path=check_path("R86_OCCUPANCY_OUT");
  const std::size_t cap=static_cast<std::size_t>(graph.kMaxDegree);
  std::vector<std::uint64_t> bins(cap+1,0);
  std::uint64_t total=0;
  for(std::size_t i=0;i<n;++i) {
   const std::size_t d=static_cast<std::size_t>(graph.degree(i));
   if(d>cap) throw std::runtime_error("R86 reservoir degree exceeds capacity");
   ++bins[d];total+=d;
  }
  std::ofstream out(path);
  if(!out) throw std::runtime_error("R86 cannot open reservoir occupancy output");
  out<<"{\"n\":"<<n<<",\"capacity\":"<<cap
     <<",\"occupied_slots\":"<<total
     <<",\"full_nodes\":"<<bins[cap]
     <<",\"mean_occupancy_exact\":"
     <<(n ? static_cast<double>(total)/n:0.0)
     <<",\"full_fraction\":"
     <<(n ? static_cast<double>(bins[cap])/n:0.0)
     <<",\"histogram\":{";
  for(std::size_t d=0;d<=cap;++d) {
   if(d)out<<',';
   out<<'"'<<d<<"\":"<<bins[d];
  }
  out<<"}}\n";
  out.flush();
  if(!out) throw std::runtime_error("R86 failed reservoir occupancy flush");
 }
}

inline void dump_jsonl(const std::string& path) {
 std::vector<std::uint64_t> sum(TOTAL,0);
 std::vector<std::uint8_t> touched(TOTAL,0);
 auto& r=registry();
 // Only after all parallel workers join. Never reset across multi-BUILD process.
 {
  std::lock_guard<std::mutex> lk(r.mutex);
  for(const Buffer* b:r.buffers)
   for(unsigned i=0;i<TOTAL;++i) {
    if(b->touched[i]) touched[i]=1;
    if(i%N_METRICS==static_cast<unsigned>(Metric::max_depth)) {
      if(b->counts[i]>sum[i]) sum[i]=b->counts[i];
    } else sum[i]+=b->counts[i];
   }
 }
 std::ofstream out(path);
 if(!out) throw std::runtime_error("R86 cannot open counter output");
 for(unsigned ps=0;ps<MAX_PASSES;++ps)
  for(unsigned dep=0;dep<=MAX_DEPTH;++dep)
   for(unsigned k=0;k<N_METRICS;++k) {
    const unsigned i=(ps*(MAX_DEPTH+1)+dep)*N_METRICS+k;
    if(!touched[i]) continue;
    out<<"{\"pass_id\":"<<ps<<",\"depth\":";
    if(dep==0) out<<"null"; else out<<(dep-1);
    out<<",\"metric_code\":\""<<metric_name(static_cast<Metric>(k))
       <<"\",\"observed\":"<<sum[i]<<"}\n";
   }
 out.flush();
 if(!out) throw std::runtime_error("R86 failed counter output");
}
inline void dump_jsonl_from_env() {
 const char* out=std::getenv("R86_COUNTER_OUT");
 if(!out||!*out) throw std::runtime_error("R86_COUNTER_OUT unset");
 dump_jsonl(out);
}
#else
inline void set_active_pass(int) {}
inline int active_pass() {return 0;}
inline void begin_pass(int) {}
inline void declare_metric(Metric,int=-1) {}
inline void add(Metric,std::uint64_t=1,int=-1) {}
inline void record_hash_work(const HashWork&) {}
template<class GraphH> inline void emit_reservoir_occupancy(GraphH&,std::size_t) {}
inline void note_depth(int) {}
inline void require_output_paths() {}
template<class Buckets> inline void emit_leaf_sizes(const Buckets&) {}
inline void dump_jsonl(const std::string&) {}
inline void dump_jsonl_from_env() {}
#endif
} // namespace r86
