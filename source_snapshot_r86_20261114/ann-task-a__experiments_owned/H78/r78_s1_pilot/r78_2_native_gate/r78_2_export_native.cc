// R78.2 -- real PiPNN ExportToGraph + RobustPrune, with three reservoir types.
// No full PiPNN BUILD or ANN query. Creates only in-memory synthetic fixtures.
#include "PipNN/pipnn.h"
#include "r78_segmented_lshgraph.h"
#include "utils/r70_two_tier_lshgraph.h"

#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

namespace {
using Id=std::uint32_t;
using Item=std::pair<Id,float>;

struct TinyPoint {
  using T=float;
  using distanceType=float;
  std::array<float,8> coords{};
  float distance(const TinyPoint& other) const {
    float sum=0;
    for (unsigned j=0;j<coords.size();++j) {
      const float dx=coords[j]-other.coords[j];
      sum+=dx*dx;
    }
    return sum;
  }
};
struct TinyRange {
  using Point=TinyPoint;
  std::vector<TinyPoint> values;
  size_t size() const {return values.size();}
  const TinyPoint& operator[](size_t i) const {return values.at(i);}
  TinyPoint& operator[](size_t i) {return values.at(i);}
};
struct HashFixture {
  std::uint16_t relative_hash(size_t, Id pid) {
    return static_cast<std::uint16_t>(pid % 32749u);
  }
};
using Stock=parlayANN::LSHGraph<Id,float,HashFixture>;
using Tier=parlayANN::TwoTierLSHGraph<Id,float,HashFixture>;
using Seg=parlayANN::R78SegmentedLSHGraph<Id,float,HashFixture>;
using Graph=parlayANN::Graph<Id>;
using Index=parlayANN::pipnn_index<TinyPoint,TinyRange,Id>;

void check(bool cond,const std::string& message) {
  if (!cond)throw std::runtime_error(message);
}

TinyRange make_points(size_t n) {
  TinyRange out;
  out.values.resize(n);
  for(size_t i=0;i<n;++i) {
    for(size_t k=0;k<8;++k) {
      // Fixed deterministic synthetic points, not the SIFT dataset.
      const unsigned long long v=(i*1315423911ull + (k+1)*2654435761ull + i*i*(k+3))%1000003ull;
      out.values[i].coords[k]=float(v%10007ull)/97.0f;
    }
  }
  return out;
}

template<class Container>
void verify_row(const Stock& s,Container& other,size_t i) {
  // Stock::degree is not const; use a const_cast only on read-only Stock state.
  auto& src=const_cast<Stock&>(s);
  check(src.degree(i)==other.degree(i),"candidate degree mismatch");
  size_t j=0;
  for(const auto& cand:other.Neighbors(i)) {
    check(j<src.degree(i),"iterator overrun");
    const auto& original=src.get_candidate(i,j);
    check(original.point_id==cand.point_id && original.hash==cand.hash &&
          float(original.norm)==float(cand.norm),"candidate content/order mismatch");
    ++j;
  }
  check(j==src.degree(i),"iterator underrun");
}

void compare_graph(Graph& a,Graph& b,const char* label,size_t n) {
  std::size_t arc_count=0;
  for(size_t i=0;i<n;++i) {
    auto ar=a[static_cast<Id>(i)],br=b[static_cast<Id>(i)];
    check(ar.size()==br.size(),std::string(label)+" degree mismatch at "+std::to_string(i));
    for(size_t j=0;j<ar.size();++j)
      check(ar[j]==br[j],std::string(label)+" outgoing arc mismatch at "+std::to_string(i));
    arc_count+=ar.size();
  }
  check(arc_count>0,std::string(label)+" no graph arcs");
  std::cout<<"R78_2_EXPORT_GRAPH_PARITY_PASS variant="<<label
           <<" vertices="<<n<<" arcs="<<arc_count<<"\n";
}

int main_impl() {
  constexpr size_t N=257;
  constexpr long R=24;
  TinyRange p=make_points(N);
  HashFixture h;
  Stock a(N,160,h,true);
  Tier b(N,160,h,true);
  Seg c(N,160,h,true);
  const size_t counts[]={0,11,32,33,64,65,100,159,160,205};
  for(size_t i=0;i<N;++i) {
    std::vector<Item> offers;
    const size_t count=counts[i % (sizeof(counts)/sizeof(counts[0]))];
    for(size_t j=0;j<N && offers.size()<count;++j) {
      Id v=static_cast<Id>((i+j+1)%N);
      if(v==i)continue;
      offers.emplace_back(v,p.values[i].distance(p.values[v]));
    }
    std::stable_sort(offers.begin(),offers.end(),[](const Item& x,const Item& y){
      if(x.second!=y.second)return x.second<y.second;
      return x.first<y.first;
    });
    // 3 variants receive precisely the same ordered source proposals.
    a.merge_neighbors(i,offers);
    b.merge_neighbors(i,offers);
    c.merge_neighbors(i,offers);
    verify_row(a,b,i);
    verify_row(a,c,i);
  }

  Index ix;
  char arg0[]="r78_2_export";
  char* argv[]={arg0};
  commandLine cli(1,argv,"");
  for(int prune_all=0;prune_all<=1;++prune_all) {
    Graph sa,sb,sc;
    sa.allocate_graph(R,N);
    sb.allocate_graph(R,N);
    sc.allocate_graph(R,N);
    ix.ExportToGraph(a,cli,sa,p,prune_all!=0,R,1.1);
    ix.ExportToGraph(b,cli,sb,p,prune_all!=0,R,1.1);
    ix.ExportToGraph(c,cli,sc,p,prune_all!=0,R,1.1);
    compare_graph(sa,sb,prune_all?"tier_prune_all":"tier_prune_conditional",N);
    compare_graph(sa,sc,prune_all?"s1_prune_all":"s1_prune_conditional",N);
  }
  std::cout<<"R78_2_REAL_PIPNN_ROBUSTPRUNE_EXPORT_PASS\n";
  std::cout<<"R78_2_SYNTHETIC_EXPORT_NOT_FULL_BUILD_NOT_RECALL\n";
  return 0;
}
}

int main() {
  try {return main_impl();}
  catch(const std::exception& e) {
    std::cerr<<"R78_2_EXPORT_FAIL: "<<e.what()<<"\n";
    return 2;
  }
}
