#pragma once
// R91-G6 V1: controlled depth==2 leader cap and read-only recursion/leaf counters.
// No changes to fanout, leader sampling, assignment order, or graph pruning.
#include <algorithm>
#include <atomic>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <cstdlib>
#include <iostream>
#include <vector>

namespace r91g6 {
inline std::atomic<int> cap{512};
inline std::atomic<std::uint64_t> depth2_calls{0},depth2_affected_calls{0};
inline std::atomic<std::uint64_t> depth2_n{0},depth2_affected_n{0};
inline std::atomic<std::uint64_t> depth2_wp_orig{0},depth2_wp_new{0};
inline std::atomic<std::uint64_t> fallback_max_calls{0},fallback_shrink_calls{0};
inline std::atomic<std::uint64_t> fallback_max_points{0},fallback_shrink_points{0};
// note_leaf is called sequentially once per completed recursive bucket.
inline std::vector<std::uint32_t> leaf_sizes;
inline void configure(int requested){
 if(requested!=512 && requested!=128 && requested!=64 && requested!=32){
   std::cerr << "R91_G6_INVALID_DEPTH2_CAP=" << requested << "\n";std::abort();
 }
 cap.store(requested,std::memory_order_relaxed);
}
inline void reset(){
 depth2_calls.store(0);depth2_affected_calls.store(0);depth2_n.store(0);
 depth2_affected_n.store(0);depth2_wp_orig.store(0);depth2_wp_new.store(0);
 fallback_max_calls.store(0);fallback_shrink_calls.store(0);
 fallback_max_points.store(0);fallback_shrink_points.store(0);
 leaf_sizes.clear();
}
inline std::size_t leader_cap(int depth,std::size_t n,std::size_t m){
 if(depth!=2) return m;
 const std::size_t capped=std::min(m,static_cast<std::size_t>(cap.load(std::memory_order_relaxed)));
 depth2_calls.fetch_add(1,std::memory_order_relaxed);
 depth2_n.fetch_add(n,std::memory_order_relaxed);
 depth2_wp_orig.fetch_add(static_cast<std::uint64_t>(n)*m,std::memory_order_relaxed);
 depth2_wp_new.fetch_add(static_cast<std::uint64_t>(n)*capped,std::memory_order_relaxed);
 if(capped<m){depth2_affected_calls.fetch_add(1,std::memory_order_relaxed);depth2_affected_n.fetch_add(n,std::memory_order_relaxed);}
 return capped;
}
inline void note_split(int depth,int max_depth,std::size_t n){
 if(depth>max_depth){fallback_max_calls.fetch_add(1,std::memory_order_relaxed);fallback_max_points.fetch_add(n,std::memory_order_relaxed);}
 else{fallback_shrink_calls.fetch_add(1,std::memory_order_relaxed);fallback_shrink_points.fetch_add(n,std::memory_order_relaxed);}
}
inline void note_leaf(std::size_t n){
 if(n>UINT32_MAX)std::abort();
 leaf_sizes.push_back(static_cast<std::uint32_t>(n));
}
inline std::size_t quantile_nearest_rank(const std::vector<std::uint32_t>& v,double p){
 if(v.empty())return 0;
 auto idx=static_cast<std::size_t>(std::ceil(p*v.size()));
 return v[std::min(v.size()-1,(idx>0?idx-1:0))];
}
inline void report(){
 auto v=leaf_sizes;std::sort(v.begin(),v.end());
 std::uint64_t total=0,executed=0,empty=0;
 for(auto n:v){total+=n;if(n>1)executed++;if(!n)empty++;}
 std::cout<<"R91_G6_CAP_JSON {\"schema\":1,\"cap\":"<<cap.load()
  <<",\"depth2_calls\":"<<depth2_calls.load()
  <<",\"depth2_affected_calls\":"<<depth2_affected_calls.load()
  <<",\"depth2_n\":"<<depth2_n.load()
  <<",\"depth2_affected_n\":"<<depth2_affected_n.load()
  <<",\"depth2_wp_original\":"<<depth2_wp_orig.load()
  <<",\"depth2_wp_actual\":"<<depth2_wp_new.load()
  <<",\"fallback_max_depth_calls\":"<<fallback_max_calls.load()
  <<",\"fallback_max_depth_points\":"<<fallback_max_points.load()
  <<",\"fallback_small_shrinkage_calls\":"<<fallback_shrink_calls.load()
  <<",\"fallback_small_shrinkage_points\":"<<fallback_shrink_points.load()
  <<",\"leaf_count\":"<<v.size()
  <<",\"leaf_executed_size_gt1\":"<<executed
  <<",\"leaf_empty_count\":"<<empty
  <<",\"total_leaf_points\":"<<total
  <<",\"leaf_p50\":"<<quantile_nearest_rank(v,.50)
  <<",\"leaf_p90\":"<<quantile_nearest_rank(v,.90)
  <<",\"leaf_max\":"<<(v.empty()?0:v.back())
  <<"}"<<std::endl;
}
} // namespace r91g6
