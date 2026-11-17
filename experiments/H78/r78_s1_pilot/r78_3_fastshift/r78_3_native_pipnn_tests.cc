// R78 native PiPNN differential test: uses REAL LSHGraph from original graph.h.
// Build ONLY in a separate H78 checkout with the real ParlayANN dependencies.
#include "utils/graph.h"
#include "r78_fast_segmented_lshgraph.h"
#include <algorithm>
#include <atomic>
#include <chrono>
#include <cstdint>
#include <cstring>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <numeric>
#include <random>
#include <stdexcept>
#include <string>
#include <thread>
#include <vector>

struct HashFixture {
  uint16_t relative_hash(size_t, uint32_t pid) {
    return static_cast<uint16_t>(pid % 32749u);
  }
};
using Stock = parlayANN::LSHGraph<uint32_t,float,HashFixture>;
using Seg = parlayANN::R78SegmentedFastShiftLSHGraph<uint32_t,float,HashFixture>;
using T = Seg::T;
using Item = std::pair<uint32_t,float>;
static_assert(sizeof(T)==8, "Expected 8-byte PiPNN LSHCandidate layout");
static_assert(sizeof(Eigen::bfloat16)==2, "BF16 fixture must occupy 2 bytes");

void need(bool ok, const std::string& why) {if(!ok) throw std::runtime_error(why);}


void parity(Stock& stock,const Seg& seg,size_t row,const char* where) {
  const size_t ds=stock.degree(row),dt=seg.degree(row);
  need(ds==dt,std::string(where)+": degree mismatch row "+std::to_string(row));
  need(std::memcmp((stock.candidates_begin(row)-1),&seg.get_sentinel(row),sizeof(T))==0,
       std::string(where)+": sentinel mismatch row "+std::to_string(row));
  auto view=seg.Neighbors(row);
  size_t j=0;
  uint16_t prev=0;
  for (const T& item: view) {
    need(j<ds,"view exceeds degree");
    need(std::memcmp(&stock.get_candidate(row,j),&item,sizeof(T))==0,
         std::string(where)+": candidate mismatch row "+std::to_string(row)+" slot "+std::to_string(j));
    if(j>0) need(prev<item.hash,"segmented iterator hash order error");
    prev=item.hash;
    ++j;
  }
  need(j==ds,"segmented iterator missing candidates");
}

void send(Stock& a,Seg& b,size_t row,uint32_t id,float distance,bool compare=true) {
  std::vector<Item> r{{id,distance}};
  a.merge_neighbors(row,r);
  b.merge_neighbors(row,r);
  if(compare)parity(a,b,row,"ordered-event parity");
}

void correctness(){
  HashFixture h;
  constexpr size_t N=128;
  Stock a(N,160,h);
  Seg b(N,160,h);
  need(b.mid_promotions()==0 && b.high_promotions()==0,"initial promotions must be zero");
  for(uint32_t j=1;j<=31;++j)send(a,b,0,j,float(j)+.25f);
  need(!b.has_mid(0),"premature mid segment at 31");
  send(a,b,0,32,32.25f);
  need(!b.has_mid(0),"premature mid segment at 32");
  send(a,b,0,1+32749u,0.1f); // collision at boundary does NOT consume a slot
  need(!b.has_mid(0),"same-hash replacement promoted mid segment");
  send(a,b,0,33,33.25f);
  need(b.has_mid(0) && !b.has_high(0),"33rd unique hash not in mid segment");
  for(uint32_t j=34;j<=64;++j)send(a,b,0,j,float(j)+.25f);
  need(!b.has_high(0),"premature high segment at 64");
  send(a,b,0,65,65.25f);
  need(b.has_high(0),"65th unique hash not in high segment");
  for(uint32_t j=66;j<=160;++j)send(a,b,0,j,float(j)+.25f);
  need(b.degree(0)==160,"failed to reach full C160");
  for(uint32_t j=161;j<=1200;++j) {
    float x=float((j*131)%311)*0.147f + float(j%7)*0.00013f;
    send(a,b,0,j,x);
    if(j%97==0)send(a,b,0,j+32749u,x+0.005f); // hash collision
  }
  for(size_t row=1;row<64;++row) {
    const uint32_t count=(row%5==0)?0u:(row%5==1)?24u:(row%5==2)?32u:(row%5==3)?64u:190u;
    for(uint32_t j=1;j<=count;++j) {
      uint32_t id=uint32_t(row*10000+j);
      const float x=float((j*7+row)%121)*0.03125f;
      send(a,b,row,id,x,false);
    }
    parity(a,b,row,"mixed rows");
    need(b.has_mid(row)==(count>32),"mid threshold mismatch");
    need(b.has_high(row)==(count>64),"high threshold mismatch");
  }
  // Multi-candidate batches exercise the Stock early-break assumption.
  // Each batch is sorted by increasing distance as required by Stock.
  for (size_t row=10;row<14;++row) {
    for (uint32_t batch=0;batch<25;++batch) {
      std::vector<Item> proposal;
      for (uint32_t k=0;k<9;++k)
        proposal.emplace_back(uint32_t(row*100000+batch*13+k),
                              float(batch*3+k)*0.001f);
      a.merge_neighbors(row,proposal);
      b.merge_neighbors(row,proposal);
      parity(a,b,row,"sorted proposal batch");
    }
  }
  // Randomized adversarial insertion orders, reproducible across runs.
  for (unsigned seed=1;seed<=7;++seed) {
    std::mt19937 rng(seed*7919);
    const size_t row=32+seed;
    for(size_t j=0;j<700;++j) {
      const uint32_t id=1u+rng()%60000u;
      const float dist=float(rng()%65536u)*0.000171f;
      std::vector<Item> proposal{{id,dist}};
      a.merge_neighbors(row,proposal);
      b.merge_neighbors(row,proposal);
      if(j%37==0)parity(a,b,row,"randomized arrival parity");
    }
    parity(a,b,row,"randomized row final");
  }
  std::atomic<bool> good{true};
  std::vector<std::thread> workers;
  for(size_t thread=0;thread<4;++thread) {
    workers.emplace_back([&,thread](){
      try {
        for(size_t row=64+thread;row<N;row+=4) {
          for(uint32_t j=1;j<=uint32_t(20+row*2);++j) {
            uint32_t id=uint32_t(row*10000+j);
            std::vector<Item> r{{id,float((j*11+row)%57)*.125f}};
            a.merge_neighbors(row,r);
            b.merge_neighbors(row,r);
          }
          parity(a,b,row,"parallel disjoint rows");
        }
      } catch (...) { good.store(false); }
    });
  }
  for(auto& t:workers)t.join();
  need(good.load(),"parallel disjoint row parity failed");
  for(size_t row=0;row<N;++row)parity(a,b,row,"final all rows");

  Seg shared(2,160,h);
  workers.clear();
  for(size_t thread=0;thread<4;++thread) {
    workers.emplace_back([&,thread](){
      for(uint32_t j=1;j<=160;++j) {
        std::vector<Item> r{{uint32_t(thread*10000+j),float(400-j-thread*10)}};
        shared.merge_neighbors(0,r);
      }
    });
  }
  for(auto& t:workers)t.join();
  size_t deg=shared.degree(0);
  need(deg<=160 && shared.has_high(0),"shared-row structural test failed");
  uint16_t prev=0;size_t j=0;
  for(const auto& x:shared.Neighbors(0)) {
    if(j>0)need(prev<x.hash,"shared-row hash order failure");
    prev=x.hash;++j;
  }
  need(j==deg,"shared-row segmented iterator wrong size");
  std::cout<<"R78_PIPNN_NATIVE_ORDERED_EVENT_PARITY_PASS nodes="<<N
           <<" middle="<<b.mid_promotions()<<" high="<<b.high_promotions()<<"\n";
  std::cout<<"R78_PIPNN_NATIVE_SHARED_SOURCE_STRUCTURAL_PASS degree="<<deg<<"\n";
  std::cout<<"R78_PIPNN_NATIVE_REAL_GRAPH_H_NOT_FULL_BUILD_NOT_QUERY_RECALL\n";
}

int main(int argc,char**argv) {
  try {
    const std::string mode=(argc>1)?argv[1]:"correctness";
    if(mode=="correctness")correctness();
    else throw std::invalid_argument("usage: r78_s1_tests correctness");
    return 0;
  } catch (const std::exception& e) {
    std::cerr<<"R78_PIPNN_NATIVE_FAIL: "<<e.what()<<"\n";
    return 2;
  }
}
