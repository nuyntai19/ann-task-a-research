#pragma once
// R91-G4 v1 READ-ONLY diagnostics: bucket N/M/N*M exact population; selected
// leader margin threshold tables at recursion depth 0/1, without point logging.
// Never modifies selection, graph, scores, fanout or leader identities.
#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <functional>
#include <iomanip>
#include <iostream>
#include <limits>
#include <mutex>
#include <utility>
#include <vector>

namespace r91g4 {
constexpr int DEPTHS=32, MAXK=10, NT=9;
constexpr std::array<double,NT> TAU{{1.01,1.02,1.05,1.08,1.10,1.15,1.20,1.30,1.50}};
// r_k = sqrt(clamp(d_k^2)/clamp(d_1^2)). We test the equivalent
// squared-distance condition d_k^2 <= tau^2*d_1^2, excluding near-zero d1.
// Diagnostics are on already SELECTED top-K only; no added neighbor scoring.
struct Bucket { std::uint64_t n,m,fanout,wp; };
struct Margin {
 std::uint64_t total=0, valid=0, near_zero=0, nonfinite=0, negative_d1=0;
 std::uint64_t selected_negative=0, rank_inversions=0, ranks_omitted=0;
 std::uint64_t chosen[NT][MAXK+1]{};
 std::uint64_t rank_leq[ MAXK+1 ][ NT ]{};
 std::uint64_t rank_present[MAXK+1]{};
 void merge(const Margin& o){
  total+=o.total;valid+=o.valid;near_zero+=o.near_zero;nonfinite+=o.nonfinite;
  negative_d1+=o.negative_d1;selected_negative+=o.selected_negative;
  rank_inversions+=o.rank_inversions;ranks_omitted+=o.ranks_omitted;
  for(int t=0;t<NT;t++)for(int k=0;k<=MAXK;k++)chosen[t][k]+=o.chosen[t][k];
  for(int k=0;k<=MAXK;k++){
   rank_present[k]+=o.rank_present[k];
   for(int t=0;t<NT;t++)rank_leq[k][t]+=o.rank_leq[k][t];
  }
 }
};
inline std::mutex mu;
inline std::vector<Bucket> buckets[DEPTHS];
inline Margin margins[2];
inline void reset(){
 std::lock_guard<std::mutex> l(mu);
 for(auto& v:buckets)v.clear();
 for(auto& v:margins)v=Margin{};
}
inline bool finite_bits(float f){
 std::uint32_t u=0;std::memcpy(&u,&f,sizeof(u));
 return (u&0x7f800000u)!=0x7f800000u;
}
inline void record_bucket(int depth,std::uint64_t n,std::uint64_t m,std::uint64_t fanout){
 if(depth<0 || depth>=DEPTHS || n>UINT64_MAX/(m?m:1)){std::abort();}
 std::lock_guard<std::mutex> l(mu);
 buckets[depth].push_back({n,m,fanout,n*m});
}
struct TileMargin {
 int depth,k; Margin local;
 explicit TileMargin(int d,int fanout):depth(d),k(fanout){
  if((depth==0 || depth==1) && (k<2 || k>MAXK))std::abort();
 }
 inline void add(const std::pair<float,std::uint32_t>* selected,int count){
  if(depth!=0 && depth!=1)return;
  if(count!=k)std::abort();
  local.total++;
  float first=selected[0].first;
  if(!finite_bits(first)){local.nonfinite++;return;}
  if(first<0)local.negative_d1++;
  // Evaluate all selected values before classifying; never touch original memory.
  double ds[MAXK];ds[0]=std::max(0.0,double(first));
  for(int j=1;j<count;j++){
   float x=selected[j].first;
   if(!finite_bits(x)){local.nonfinite++;return;}
   if(x<0)local.selected_negative++;
   ds[j]=std::max(0.0,double(x));
   if(ds[j]<ds[j-1])local.rank_inversions++;
  }
  if(ds[0]<=1e-12){local.near_zero++;return;}
  // VQ sort should be monotone; if raw values disagree, do not invent a
  // monotone fanout distribution from them; drop only this point from valid.
  bool monotone=true;
  for(int j=1;j<count;j++)if(ds[j]<ds[j-1])monotone=false;
  if(!monotone){local.ranks_omitted++;return;}
  local.valid++;
  for(int j=2;j<=count;j++){
   local.rank_present[j]++;
   for(int t=0;t<NT;t++)if(ds[j-1]<=TAU[t]*TAU[t]*ds[0])local.rank_leq[j][t]++;
  }
  for(int t=0;t<NT;t++){
   int retained=1;
   for(int j=1;j<count;j++)if(ds[j]<=TAU[t]*TAU[t]*ds[0])retained++;
   local.chosen[t][retained]++;
  }
 }
 ~TileMargin(){
  if((depth!=0 && depth!=1) || local.total==0)return;
  std::lock_guard<std::mutex> l(mu);margins[depth].merge(local);
 }
 TileMargin(const TileMargin&)=delete;TileMargin& operator=(const TileMargin&)=delete;
};
inline std::uint64_t quantile(std::vector<std::uint64_t> x,double q){
 if(x.empty())return 0;
 std::sort(x.begin(),x.end());
 auto z=std::size_t(std::ceil(q*x.size()));return x[(z?z:1)-1];
}
inline void bucket_stats(int depth){
 const auto& b=buckets[depth];
 std::vector<std::uint64_t> ns,ms,ws;ns.reserve(b.size());ms.reserve(b.size());ws.reserve(b.size());
 std::uint64_t total=0,ceil512=0,floor3=0;
 for(const auto& x:b){ns.push_back(x.n);ms.push_back(x.m);ws.push_back(x.wp);total+=x.wp;ceil512+=(x.m==512);floor3+=(x.m==3);}
 const double qs[5]={.50,.90,.95,.99,1.0};
 auto outq=[&](const char* name,const std::vector<std::uint64_t>& vec){
  std::cout<<",\""<<name<<"_p50_p90_p95_p99_max\":[";
  for(int i=0;i<5;i++){if(i)std::cout<<",";std::cout<<quantile(vec,qs[i]);}
  std::cout<<"]";
 };
 std::cout<<"{\"depth\":"<<depth<<",\"calls\":"<<b.size()<<",\"total_wp\":"<<total<<",\"cap512_calls\":"<<ceil512<<",\"floor3_calls\":"<<floor3;
 outq("N",ns);outq("M",ms);outq("WP",ws);
 std::sort(ws.begin(),ws.end(),std::greater<std::uint64_t>());
 std::cout<<",\"wp_top1_top5_top10_share\":[";
 const double top[3]={.01,.05,.10};
 for(int j=0;j<3;j++){
  if(j)std::cout<<",";
  std::size_t count=std::max<std::size_t>(1,std::size_t(std::ceil(ws.size()*top[j])));
  std::uint64_t s=0;for(std::size_t i=0;i<count&&i<ws.size();i++)s+=ws[i];
  std::cout<<(total?double(s)/double(total):0.0);
 }
 std::cout<<"]}";
}
inline void margin_stats(int depth){
 const auto& m=margins[depth];
 std::cout<<"{\"depth\":"<<depth<<",\"total\":"<<m.total<<",\"valid\":"<<m.valid
  <<",\"near_zero_d1_squared_le_1e-12\":"<<m.near_zero<<",\"nonfinite\":"<<m.nonfinite
  <<",\"negative_d1\":"<<m.negative_d1<<",\"other_negative_selected\":"<<m.selected_negative
  <<",\"rank_inversions\":"<<m.rank_inversions<<",\"ranks_omitted\":"<<m.ranks_omitted
  <<",\"tau\":[";
 for(int t=0;t<NT;t++){if(t)std::cout<<",";std::cout<<TAU[t];}
 std::cout<<"],\"fanout_by_tau\":[";
 for(int t=0;t<NT;t++){
  if(t)std::cout<<",";
  std::uint64_t sum=0,work=0;for(int k=1;k<=MAXK;k++){sum+=m.chosen[t][k];work+=k*m.chosen[t][k];}
  std::cout<<"{\"tau\":"<<TAU[t]<<",\"counts_by_f1_to_f10\":[";
  for(int k=1;k<=MAXK;k++){if(k>1)std::cout<<",";std::cout<<m.chosen[t][k];}
  std::cout<<"],\"valid_points\":"<<sum<<",\"replicated_memberships\":"<<work<<",\"mean_f\":"<<(sum?double(work)/double(sum):0)<<"}";
 }
 std::cout<<"],\"rank_leq_by_k\":[";
 for(int k=2;k<=MAXK;k++){
  if(k>2)std::cout<<",";
  std::cout<<"{\"k\":"<<k<<",\"count\":"<<m.rank_present[k]<<",\"leq_tau\":[";
  for(int t=0;t<NT;t++){if(t)std::cout<<",";std::cout<<m.rank_leq[k][t];}
  std::cout<<"]}";
 }
 std::cout<<"]}";
}
inline void report(){
 std::lock_guard<std::mutex> l(mu);
 std::cout<<std::setprecision(17)
  <<"R91_G4_DIAG_JSON {\"schema\":1,\"margin_semantics\":\"L2 ratio sqrt(clamp(score_k)/clamp(score_1)), finite nonzero d1 only; compare squared score_k <= tau^2*score_1; selected topK only\""
  <<",\"bucket_statistics\":[";
 bool first=true;
 for(int d=0;d<DEPTHS;d++)if(!buckets[d].empty()){if(!first)std::cout<<",";first=false;bucket_stats(d);}
 std::cout<<"],\"margin_statistics\":[";
 margin_stats(0);std::cout<<",";margin_stats(1);
 std::cout<<"]}"<<std::endl;
}
} // namespace r91g4
