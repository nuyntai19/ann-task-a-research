// Native PiPNN R70 primitive test, linked against real Eigen/Absl/Parlay.
// This is NOT a complete PiPNN graph build / ANN search benchmark.
#include <algorithm>
#include <atomic>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <random>
#include <stdexcept>
#include <string>
#include <thread>
#include <vector>

#include "utils/graph.h"
#include "utils/r70_two_tier_lshgraph.h"

struct DeterministicTestHash {
  // Synthetic intentionally collision-rich hash. Both graphs receive SAME H.
  uint16_t relative_hash(size_t, uint32_t pid) {
    return static_cast<uint16_t>(pid % 32749u);
  }
};
using Stock = parlayANN::LSHGraph<uint32_t,float,DeterministicTestHash>;
using Tier = parlayANN::TwoTierLSHGraph<uint32_t,float,DeterministicTestHash>;
using T = Stock::T;
using Item = std::pair<uint32_t, float>;
static_assert(sizeof(T)==8,"R70 precondition: eight-byte PiPNN LSHCandidate");

static void check(bool b,const std::string& msg) {if(!b) throw std::runtime_error(msg);}

static void same_row(Stock& s,Tier& t,size_t i,const char* ctx) {
  auto ds=s.degree(i), dt=t.degree(i);
  if(ds!=dt) throw std::runtime_error(std::string(ctx)+": degree mismatch row "+std::to_string(i));
  // Only occupied cells + sentinel: unused memory can have indeterminate bytes.
  for(size_t j=0;j<=ds;++j) {
    const T* a=(j==0)?s.candidates_begin(i)-1:&s.get_candidate(i,j-1);
    const T* b=(j==0)?t.candidates_begin(i)-1:&t.get_candidate(i,j-1);
    if(std::memcmp(a,b,sizeof(T))!=0)
      throw std::runtime_error(std::string(ctx)+": candidate/sentinel byte mismatch row "+
        std::to_string(i)+" slot "+std::to_string(j));
  }
}

static void send(Stock& s,Tier& t,size_t row, uint32_t pid, float distance) {
  const std::vector<Item> r{{pid,distance}};
  s.merge_neighbors(row,r);
  t.merge_neighbors(row,r);
  same_row(s,t,row,"identically ordered stream");
}

static void check_sorted(Tier& t,size_t row) {
  const auto d=t.degree(row);
  check(d<=160,"degree overflow");
  for(size_t j=1;j<d;++j)
    check(t.get_candidate(row,j-1).hash < t.get_candidate(row,j).hash,"hash order/collision violation");
  if(d>0) check(t.get_furthest_index(row)<d,"invalid worst index");
}

static void correctness(){
  DeterministicTestHash h;
  constexpr size_t N=128;
  Stock s(N,160,h,true);
  Tier t(N,160,h,true);
  check(t.promoted_rows()==0,"unexpected initial promotion");

  // Fill exactly to 64 without promotions; promote at 65.
  for(uint32_t j=1;j<=64;j++) send(s,t,0,j,float(j)+0.25f);
  check(!t.is_promoted(0),"premature promotion at 64");
  send(s,t,0,1+32749u,0.1f); // duplicate hash: replace, should NOT promote
  check(!t.is_promoted(0),"collision caused unnecessary promotion");
  send(s,t,0,65,65.25f);
  check(t.is_promoted(0),"no promotion at candidate 65");

  // Full reservoir, new hash insertion, worst replacement, early break.
  for(uint32_t j=66;j<=240;j++) send(s,t,0,j,200.0f-float(j)*0.73f);
  // Force collision at full capacity; include bf16 tie/rounding behavior.
  for(uint32_t j=1;j<=60;j++) {
    send(s,t,0,j+32749u,float(j)*0.79f);
    send(s,t,0,j+2*32749u,float(j)*0.79f+0.0001f);
  }
  for(uint32_t j=241;j<=600;j++) send(s,t,0,j,float(j%49)*0.103f);
  check_sorted(t,0);

  // Distinct rows: no collision, collision, equal/worse, boundary 64->65.
  for(size_t row=1;row<16;row++) {
    const uint32_t count=(row%3==0)?24u:((row%3==1)?64u:170u);
    for(uint32_t j=1;j<=count;j++) send(s,t,row,j+uint32_t(row*1000),float(j%21)+float(row)*0.01f);
    check(t.is_promoted(row)==(count>64),"mixed sequential row promotion mismatch");
    check_sorted(t,row);
  }

  // Multiple writers, but independent rows -> per-row ordered stream is equal.
  std::atomic<bool> failed{false};
  std::vector<std::thread> threads;
  for(size_t thread=0;thread<4;thread++) {
    threads.emplace_back([&,thread]() {
      try {
        for(size_t row=16+thread;row<N;row+=4) {
          const uint32_t count=(row%5==0)?0u:((row%5==1)?32u:((row%5==2)?64u:170u));
          for(uint32_t j=1;j<=count;j++) {
            // One identical ordered stream per source in both structures.
            const std::vector<Item> r{{j+uint32_t(row*1000),float(j%37)+float(row)*0.1f}};
            s.merge_neighbors(row,r);
            t.merge_neighbors(row,r);
          }
          same_row(s,t,row,"parallel distinct sources");
          check(t.is_promoted(row)==(count>64),"mixed parallel row promotion mismatch");
          check_sorted(t,row);
        }
      } catch (...) {failed.store(true);}
    });
  }
  for(auto& th:threads) th.join();
  check(!failed.load(),"parallel distinct source parity failed");
  for(size_t i=0;i<N;i++) same_row(s,t,i,"final all rows");
  check(t.promoted_rows()>0 && t.promoted_rows()<N,"must exercise promoted AND unpromoted final rows");
  std::cout<<"R70_MIXED_FINAL_ROW_PARITY_PASS promoted="<<t.promoted_rows()
           <<" unpromoted="<<(N-t.promoted_rows())<<"\n";

  // Concurrent SAME-SOURCE calls: tier-only structural stress, NOT byte parity.
  // The scheduling order is not constrained, so a second independent stock
  // execution cannot be assumed to receive an identical ordered stream.
  {
    Tier concurrent(2,160,h,true);
    std::vector<std::thread> writers;
    for(size_t worker=0;worker<4;worker++){
      writers.emplace_back([&,worker](){
        for(uint32_t j=1;j<=120;j++){
          std::vector<Item> r{{uint32_t(worker*10000+j), float(500-j-worker*10)}};
          concurrent.merge_neighbors(0,r);
        }
      });
    }
    for(auto& th:writers) th.join();
    check(concurrent.is_promoted(0),"same-source stress did not promote");
    check_sorted(concurrent,0);
    std::cout<<"R70_SAME_SOURCE_LOCK_STRESS_PASS (structural-only, nondeterministic order)\n";
  }
  std::cout<<"R70_NATIVE_PARITY_PASS nodes="<<N<<" promoted="<<t.promoted_rows()<<"\n";
  std::cout<<"R70_TEST_NOT_FULL_BUILD_NOT_QUERY_RECALL\n";
}

static long hwm_kib() {
  std::ifstream f("/proc/self/status");
  std::string line;
  while(std::getline(f,line)){
    if(line.rfind("VmHWM:",0)==0){
      size_t a=line.find_first_of("0123456789");
      return a!=std::string::npos?std::stol(line.substr(a)):-1;
    }
  }
  return -1;
}

template <class Graph>
static void benchmark(const char* name,size_t n,size_t high_per_mille) {
  DeterministicTestHash h;
  auto start=std::chrono::steady_clock::now();
  Graph g(n,160,h,true);
  // On most rows produce <=64 candidates; a controlled subset crosses the gate.
  // This synthetic occupancy is a probe, NOT a replay of PiPNN R60 proposals.
  std::vector<Item> r;
  r.reserve(130);
  uint64_t check_sum=0;
  for(size_t i=0;i<n;i++) {
    const bool high=(i%1000)<high_per_mille;
    const size_t count=high?110:32+(i%31);
    r.clear();
    for(size_t j=0;j<count;++j) {
      uint32_t pid=uint32_t((i*137ull + j*71ull)%1000000007ull+1ull);
      r.emplace_back(pid, float(count-j)*0.125f+0.0001f*float(i%13));
    }
    // Input is sorted ascending by distance, matching original early-break assumption.
    std::sort(r.begin(),r.end(),[](const Item&a,const Item&b){return a.second<b.second;});
    g.merge_neighbors(i,r);
    check_sum+=g.degree(i);
  }
  auto end=std::chrono::steady_clock::now();
  std::cout<<"R70_SYNTHETIC_BENCH variant="<<name
    <<" nodes="<<n<<" high_per_mille="<<high_per_mille
    <<" elapsed_ms="<<std::chrono::duration_cast<std::chrono::milliseconds>(end-start).count()
    <<" VmHWM_KiB="<<hwm_kib()<<" checksum="<<check_sum<<"\n";
}

int main(int argc,char** argv){
  try {
    std::string mode=argc>1?argv[1]:"correctness";
    if(mode=="correctness") correctness();
    else if(mode=="stock"||mode=="tier"){
      const size_t n=argc>2?std::stoull(argv[2]):100000;
      const size_t high=argc>3?std::stoull(argv[3]):46;
      check(high<=1000 && n>=100,"invalid bench args");
      if(mode=="stock") benchmark<Stock>("stock",n,high);
      else benchmark<Tier>("tier",n,high);
    } else throw std::invalid_argument("usage: r70_native_tests correctness|stock|tier [nodes] [high_per_mille]");
    return 0;
  }catch(const std::exception& e){
    std::cerr<<"R70_NATIVE_FAIL "<<e.what()<<"\n";
    return 2;
  }
}
