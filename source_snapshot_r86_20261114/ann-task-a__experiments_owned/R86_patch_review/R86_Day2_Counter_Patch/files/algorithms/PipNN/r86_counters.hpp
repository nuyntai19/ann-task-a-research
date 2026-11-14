#pragma once
// R86 v1.0 candidate patch, manually reviewed source hooks, no dependency outside C++17.
// These are logical algorithm events, never hardware instructions.
#include <cstdint>
#include <string>
#if defined(R86_COUNTERS) && R86_COUNTERS
#include <array>
#include <atomic>
#include <cstdlib>
#include <fstream>
#include <mutex>
#include <stdexcept>
#include <vector>
#endif
namespace r86 {
enum class Metric : unsigned {
 W_P, W_A, W_L, W_pairs, leaf_count, leaf_size_sum, max_depth,
 proposals, merge_attempts, collision_same_id, collision_diff_id,
 hash_accept, hash_reject, hash_replace, hash_early_break, hash_full,
 prune_distance_calls, top2_comparisons, top2_assignments, top2_moves, COUNT
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
inline void note_depth(int depth) {
 std::size_t pos=index(active_pass(),-1,Metric::max_depth);
 Buffer& b=local();b.touched[pos]=1;
 if(static_cast<std::uint64_t>(depth)>b.counts[pos]) b.counts[pos]=depth;
}
inline void begin_pass(int pass) {
 set_active_pass(pass);
 // Declare measured event categories explicitly: measured zero != absent/not measured.
 for(Metric m : {Metric::W_P,Metric::W_A,Metric::W_L,Metric::W_pairs,
                 Metric::leaf_count,Metric::leaf_size_sum,Metric::max_depth,
                 Metric::proposals,Metric::merge_attempts,
                 Metric::collision_same_id,Metric::collision_diff_id,
                 Metric::hash_accept,Metric::hash_reject,Metric::hash_replace,
                 Metric::hash_early_break,Metric::hash_full}) declare_metric(m);
}
inline const char* metric_name(Metric m) {
 constexpr const char* names[]={"W_P","W_A","W_L","W_pairs","leaf_count",
 "leaf_size_sum","max_depth","proposals","merge_attempts",
 "collision_same_id","collision_diff_id","hash_accept","hash_reject",
 "hash_replace","hash_early_break","hash_full","prune_distance_calls",
 "top2_comparisons","top2_assignments","top2_moves"};
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
}
template<class Buckets>
inline void emit_leaf_sizes(const Buckets& buckets) {
 const char* p=std::getenv("R86_LEAF_SIZE_OUT");
 if(!p||!*p) throw std::runtime_error("R86_LEAF_SIZE_OUT unset");
 std::ofstream file(p,std::ios::app);
 if(!file) throw std::runtime_error("R86 cannot write leaf-size dump");
 const int pass=active_pass();
 for(const auto& b:buckets) {
   // Only buckets executed by RunLeaf are included.
   if(b.size()>1) file<<"{\"pass_id\":"<<pass<<",\"depth\":null,\"size\":"<<b.size()<<"}\n";
 }
 file.flush();
 if(!file) throw std::runtime_error("R86 failed leaf-size flush");
}
inline void dump_jsonl(const std::string& path) {
 std::vector<std::uint64_t> sum(TOTAL,0);
 std::vector<std::uint8_t> touched(TOTAL,0);
 auto& r=registry();
 // Only call after parallel work has fully joined. Never reset in multi-BUILD process.
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
    if(!touched[i]) continue; // absent = NOT_MEASURED; declared zero is emitted.
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
inline void note_depth(int) {}
inline void require_output_paths() {}
template<class Buckets> inline void emit_leaf_sizes(const Buckets&) {}
inline void dump_jsonl(const std::string&) {}
inline void dump_jsonl_from_env() {}
#endif
} // namespace r86
