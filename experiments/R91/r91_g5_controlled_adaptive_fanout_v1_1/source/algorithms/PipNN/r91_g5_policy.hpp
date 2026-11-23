#pragma once
// R91-G5 v1.1 source-controlled depth-0 fanout policy; no changes at depth>0.
// Do NOT call this a speedup or a matched-budget result without native Search tests.
#include <atomic>
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstddef>
#include <cstdlib>
#include <cstring>
#include <iostream>
#include <iomanip>
#include <limits>
#include <utility>

namespace r91g5 {
constexpr int MAX_DEPTH=32;
enum class Mode:int {FIXED=0, UNIFORM_MIX=1, ADAPTIVE_MARGIN=2};
struct Config {Mode mode=Mode::FIXED;double tau=1.05;int low=3;int hi_bps=0;std::uint64_t seed=20261123;};
inline Config cfg{};
inline std::atomic<int> next_pass{0};
inline int current_pass=0; // written at root start before nested workers; then read-only
inline std::atomic<std::uint64_t> memberships[MAX_DEPTH];
inline std::atomic<std::uint64_t> num_points[MAX_DEPTH];
inline std::atomic<std::uint64_t> retained_hist[11];
inline std::atomic<std::uint64_t> near_zero=0, nonfinite=0, negative_first=0, inversion=0;
inline void require(bool x){if(!x)std::abort();}
inline bool finite_bits(float f){std::uint32_t u=0;std::memcpy(&u,&f,sizeof(u));return (u&0x7f800000u)!=0x7f800000u;}
inline bool finite_double_bits(double d){std::uint64_t u=0;std::memcpy(&u,&d,sizeof(u));return (u&0x7ff0000000000000ULL)!=0x7ff0000000000000ULL;}
inline void configure(const char *name,double tau,int low,int hi_bps,std::uint64_t seed){
 require(name!=nullptr);
 if(std::strcmp(name,"fixed")==0)cfg.mode=Mode::FIXED;
 else if(std::strcmp(name,"uniform_mix")==0)cfg.mode=Mode::UNIFORM_MIX;
 else if(std::strcmp(name,"adaptive_margin")==0)cfg.mode=Mode::ADAPTIVE_MARGIN;
 else {std::cerr<<"R91_G5_HOLD_UNKNOWN_POLICY "<<name<<"\n";std::abort();}
 require(finite_double_bits(tau)&&tau>=1.0&&tau<=1.5);
 require(low>=1&&low<=10&&hi_bps>=0&&hi_bps<=10000);
 cfg.tau=tau;cfg.low=low;cfg.hi_bps=hi_bps;cfg.seed=seed;
}
inline bool modified(int depth){return depth==0&&cfg.mode!=Mode::FIXED;}
inline std::uint64_t hash64(std::uint64_t z){
 z+=0x9e3779b97f4a7c15ULL;z=(z^(z>>30))*0xbf58476d1ce4e5b9ULL;
 z=(z^(z>>27))*0x94d049bb133111ebULL;return z^(z>>31);
}
inline void begin_pass(){
 current_pass=next_pass.fetch_add(1,std::memory_order_relaxed)+1;
 for(auto& x:memberships)x.store(0,std::memory_order_relaxed);
 for(auto& x:num_points)x.store(0,std::memory_order_relaxed);
 for(auto& x:retained_hist)x.store(0,std::memory_order_relaxed);
 near_zero.store(0);nonfinite.store(0);negative_first.store(0);inversion.store(0);
}
inline int choose(int depth,int k,const std::pair<float,std::uint32_t>* top,std::uint32_t point_id){
 require(k>=1&&k<=10);
 if(!modified(depth))return k;
 if(cfg.mode==Mode::UNIFORM_MIX){
  require(cfg.low+1<=k || cfg.hi_bps==0);require(cfg.low<=k);
  std::uint64_t x=std::uint64_t(point_id) ^ cfg.seed ^ (0x9e3779b97f4a7c15ULL*std::uint64_t(current_pass));
  return cfg.low+(hash64(x)%10000ULL<std::uint64_t(cfg.hi_bps)?1:0);
 }
 float first=top[0].first;
 if(!finite_bits(first)){nonfinite.fetch_add(1,std::memory_order_relaxed);return k;}
 if(first<0)negative_first.fetch_add(1,std::memory_order_relaxed);
 const double d0=std::max(0.0,static_cast<double>(first));
 // Match the G4 original projected budget: near-zero gets FULL fanout,
 // not K=1. Alternative K=1 requires distinct arm and new budget estimates.
 if(d0<=1e-12){near_zero.fetch_add(1,std::memory_order_relaxed);return k;}
 int kept=1;double prev=d0;
 for(int j=1;j<k;j++){
  float fj=top[j].first;
  if(!finite_bits(fj)){nonfinite.fetch_add(1,std::memory_order_relaxed);return k;}
  const double dj=std::max(0.0,static_cast<double>(fj));
  if(dj<prev){inversion.fetch_add(1,std::memory_order_relaxed);return k;}
  prev=dj;
  if(dj<=cfg.tau*cfg.tau*d0)kept++;
 }
 return kept;
}
struct TileCounter {
 int depth,k;std::uint64_t actual=0,points=0,counts[11]{};
 TileCounter(int d,int kk):depth(d),k(kk){require(d>=0&&d<MAX_DEPTH);}
 void add(int retained){require(retained>=1&&retained<=k);actual+=retained;points++;if(depth==0)counts[retained]++;}
 ~TileCounter(){if(!points)return;memberships[depth].fetch_add(actual,std::memory_order_relaxed);num_points[depth].fetch_add(points,std::memory_order_relaxed);if(depth==0)for(int k=1;k<=10;k++)if(counts[k])retained_hist[k].fetch_add(counts[k],std::memory_order_relaxed);}
 TileCounter(const TileCounter&)=delete;TileCounter& operator=(const TileCounter&)=delete;
};
inline std::uint64_t actual(int depth){require(depth>=0&&depth<MAX_DEPTH);return memberships[depth].load(std::memory_order_relaxed);}
inline void validate_sentinel(std::size_t n,std::size_t fanout,std::size_t sentinel_size){
 require(n<=SIZE_MAX/fanout);
 require(actual(0)<=n*fanout);
 require(sentinel_size == n*fanout-actual(0));
}
inline void report(){
 std::cout<<std::setprecision(17)<<"R91_G5_POLICY_JSON {\"schema\":1,\"pass_index\":"<<current_pass
 <<",\"policy\":\""<<(cfg.mode==Mode::FIXED?"fixed":cfg.mode==Mode::UNIFORM_MIX?"uniform_mix":"adaptive_margin")
 <<"\",\"tau\":"<<cfg.tau<<",\"low\":"<<cfg.low<<",\"hi_bps\":"<<cfg.hi_bps
 <<",\"seed\":"<<cfg.seed<<",\"fallback_nearzero\":\"full\",\"actual_wa_per_depth\":[";
 for(int d=0;d<MAX_DEPTH;d++){if(d)std::cout<<",";std::cout<<actual(d);}
 std::cout<<"],\"points_per_depth\":[";
 for(int d=0;d<MAX_DEPTH;d++){if(d)std::cout<<",";std::cout<<num_points[d].load();}
 std::cout<<"],\"depth0_f_hist\":[";
 for(int j=1;j<=10;j++){if(j>1)std::cout<<",";std::cout<<retained_hist[j].load();}
 std::cout<<"],\"nearzero\":"<<near_zero.load()<<",\"negative_first\":"<<negative_first.load()
 <<",\"nonfinite\":"<<nonfinite.load()<<",\"rank_inversions\":"<<inversion.load()<<"}"<<std::endl;
}
}
