#pragma once
// R86 counting hooks for manual review before wiring into PiPNN.
// C++17; no third-party dependency. Counts are LOGICAL operations, not CPU instructions.
// Compile with -DR86_COUNTERS=1; without it all counter calls are no-op.
// A worker-local buffer prevents atomic increments on every operation. Only reading
// active_pass costs one relaxed atomic load per call when counters are enabled.
#include <cstdint>
#include <string>

#ifdef R86_COUNTERS
#include <array>
#include <atomic>
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
  prune_distance_calls, top2_comparisons, top2_assignments, top2_moves,
  COUNT
};

#ifdef R86_COUNTERS
constexpr unsigned MAX_PASSES=16;     // pass=0 means global/final prune
constexpr unsigned MAX_DEPTH=64;      // depth=-1 means aggregate across depths
constexpr unsigned NMETRICS=static_cast<unsigned>(Metric::COUNT);
struct Buffer {
  std::array<std::uint64_t, MAX_PASSES*(MAX_DEPTH+1)*NMETRICS> counts{};
};
struct Registry {
  std::mutex mutex;
  std::vector<Buffer*> buffers;
  std::atomic<int> active_pass{0};
};
inline Registry& registry() { static Registry* r=new Registry(); return *r; }
inline Buffer& local() {
  static thread_local Buffer* p=[]() {
    Buffer* b=new Buffer();
    auto& reg=registry();
    std::lock_guard<std::mutex> lk(reg.mutex);
    reg.buffers.push_back(b);
    return b;
  }();
  return *p;
}
inline void set_active_pass(int pass) {
  if(pass<0 || pass>=static_cast<int>(MAX_PASSES)) throw std::out_of_range("r86 pass id");
  registry().active_pass.store(pass,std::memory_order_release);
}
inline int active_pass() {return registry().active_pass.load(std::memory_order_relaxed);}
inline std::size_t index(int pass,int depth,Metric kind) {
  if(pass<0 || pass>=static_cast<int>(MAX_PASSES) || depth < -1 || depth >= static_cast<int>(MAX_DEPTH))
    throw std::out_of_range("r86 pass/depth scope");
  return (static_cast<unsigned>(pass)*(MAX_DEPTH+1)+static_cast<unsigned>(depth+1))*NMETRICS+static_cast<unsigned>(kind);
}
inline void note_depth(int depth) {
  std::uint64_t& max_so_far=local().counts[index(active_pass(),-1,Metric::max_depth)];
  if(static_cast<std::uint64_t>(depth)>max_so_far) max_so_far=static_cast<std::uint64_t>(depth);
}
inline void add(Metric kind,std::uint64_t amount=1,int depth=-1) {
  // DO NOT use per vector-distance scalar increments if batch dimensions are known.
  local().counts[index(active_pass(),depth,kind)] += amount;
}
inline const char* metric_name(Metric v) {
  constexpr const char* names[]={
    "W_P","W_A","W_L","W_pairs","leaf_count","leaf_size_sum","max_depth",
    "proposals","merge_attempts","collision_same_id","collision_diff_id",
    "hash_accept","hash_reject","hash_replace","hash_early_break","hash_full",
    "prune_distance_calls","top2_comparisons","top2_assignments","top2_moves"
  };
  return names[static_cast<unsigned>(v)];
}
inline void dump_jsonl(const std::string& filename) {
  std::vector<std::uint64_t> sum(MAX_PASSES*(MAX_DEPTH+1)*NMETRICS,0);
  auto& reg=registry();
  {
    std::lock_guard<std::mutex> lk(reg.mutex);
    for(const Buffer* p:reg.buffers)
      for(std::size_t i=0;i<sum.size();++i) {
        if(i%NMETRICS==static_cast<unsigned>(Metric::max_depth)) {
          if(p->counts[i]>sum[i]) sum[i]=p->counts[i];
        } else sum[i]+=p->counts[i];
      }
  }
  std::ofstream output(filename);
  if(!output) throw std::runtime_error("Cannot open R86 counter log "+filename);
  for(unsigned pass=0;pass<MAX_PASSES;++pass)
    for(unsigned dep=0;dep<=MAX_DEPTH;++dep)
      for(unsigned k=0;k<NMETRICS;++k) {
        std::uint64_t value=sum[(pass*(MAX_DEPTH+1)+dep)*NMETRICS+k];
        if(value==0) continue;  // Zero events are not measured absent events; completeness comes from protocol.
        output<<"{\"pass_id\":"<<pass<<",\"depth\":";
        if(dep==0) output<<"null"; else output<<(dep-1);
        output<<",\"metric_code\":\""<<metric_name(static_cast<Metric>(k))
              <<"\",\"observed\":"<<value<<"}\n";
      }
}
#else
inline void set_active_pass(int) {}
inline int active_pass() {return 0;}
inline void add(Metric,std::uint64_t=1,int=-1) {}
inline void note_depth(int) {}
inline void dump_jsonl(const std::string&) {}
#endif
}  // namespace r86
