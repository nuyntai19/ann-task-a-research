// R78.2 -- three-arm *isolated process* native reservoir microbenchmark.
// Not SIFT, not ANN full graph build; sizes/times are system-level observations.
#include "utils/graph.h"
#include "utils/r70_two_tier_lshgraph.h"
#include "r78_segmented_lshgraph.h"
#include "r78_fast_segmented_lshgraph.h"
#include <algorithm>
#include <chrono>
#include <cstdint>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <string>
#include <type_traits>
#include <vector>

namespace {
struct HashFixture {
  std::uint16_t relative_hash(size_t, std::uint32_t pid) {
    return static_cast<std::uint16_t>(pid % 32749u);
  }
};
using Stock=parlayANN::LSHGraph<std::uint32_t,float,HashFixture>;
using Tier=parlayANN::TwoTierLSHGraph<std::uint32_t,float,HashFixture>;
using Seg=parlayANN::R78SegmentedLSHGraph<std::uint32_t,float,HashFixture>;
using Fast=parlayANN::R78SegmentedFastShiftLSHGraph<std::uint32_t,float,HashFixture>;
using Item=std::pair<std::uint32_t,float>;

size_t vmhwm_kib(){
  std::ifstream f("/proc/self/status");
  std::string row;
  while(std::getline(f,row)) {
    if(row.rfind("VmHWM:",0)==0) {
      auto at=row.find_first_of("0123456789");
      if(at!=std::string::npos)return std::stoull(row.substr(at));
    }
  }
  return 0;
}
std::uint64_t mix(std::uint64_t x) {
  x+=0x9e3779b97f4a7c15ULL;
  x=(x^(x>>30))*0xbf58476d1ce4e5b9ULL;
  x=(x^(x>>27))*0x94d049bb133111ebULL;
  return x^(x>>31);
}
size_t intended_count(size_t i) {
  // R59-inspired categorical percentages, NOT original real-arrival streams.
  std::uint64_t gate=mix(i+20261105ULL)%1000000ULL;
  if(gate<57) return 160;
  if(gate<45804) return 84;
  if(gate<577816) return 41;
  return 27;
}

template<class G>
void bench(const std::string& arm,size_t n) {
  HashFixture h;
  const auto begin=std::chrono::steady_clock::now();
  G graph(n,160,h,true);
  std::vector<Item> offer;
  offer.reserve(160);
  std::uint64_t checksum=0, rows32=0,rows64=0,full=0;
  for(size_t i=0;i<n;++i) {
    const size_t count=intended_count(i);
    rows32+=(count>32);
    rows64+=(count>64);
    full+=(count==160);
    offer.clear();
    for(size_t j=0;j<count;++j) {
      const auto pid=static_cast<std::uint32_t>((i*17117ULL+j*71ULL+1ULL)%3000000000ULL);
      offer.emplace_back(pid,static_cast<float>(j)*0.125f+0.01f);
    }
    graph.merge_neighbors(i,offer); // input sorted by increasing distance
    checksum+=graph.degree(i);
  }
  const auto elapsed=std::chrono::duration<double>(std::chrono::steady_clock::now()-begin).count();
  std::cout<<"R78_3_MICROBENCH_RESULT variant="<<arm<<" nodes="<<n
           <<" input_rows_gt32="<<rows32<<" input_rows_gt64="<<rows64
           <<" input_full160="<<full<<" elapsed_s="<<elapsed
           <<" VmHWM_KiB="<<vmhwm_kib()<<" checksum="<<checksum;
  if constexpr (std::is_same_v<G,Seg> || std::is_same_v<G,Fast>)
    std::cout<<" middle="<<graph.mid_promotions()<<" high="<<graph.high_promotions()
             <<" nominal_candidate_bytes="<<graph.nominal_candidate_bytes();
  std::cout<<"\n";
}
}
int main(int argc,char**argv) {
  try {
    if(argc!=3)throw std::invalid_argument("usage: r78_2_microbench_native stock|tier|s1|fast NODE_COUNT");
    std::string arm=argv[1];
    size_t n=std::stoull(argv[2]);
    if(n<4096 || n>1000000)throw std::invalid_argument("node count must be in [4096,1000000]");
    if(arm=="stock")bench<Stock>(arm,n);
    else if(arm=="tier")bench<Tier>(arm,n);
    else if(arm=="s1")bench<Seg>(arm,n);
    else if(arm=="fast")bench<Fast>(arm,n);
    else throw std::invalid_argument("unknown variant");
    std::cout<<"R78_3_NOT_REAL_ANN_BUILD_OR_RECALL\n";
    return 0;
  } catch(const std::exception& e) {
    std::cerr<<"R78_3_MICROBENCH_FAIL: "<<e.what()<<"\n";
    return 2;
  }
}
