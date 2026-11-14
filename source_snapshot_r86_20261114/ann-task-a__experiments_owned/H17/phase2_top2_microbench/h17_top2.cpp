#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <iomanip>
#include <iostream>
#include <limits>
#include <random>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>
#include "hwy/contrib/sort/vqsort-inl.h"
#include "hwy/contrib/sort/vqsort.h"
#include "hwy/highway.h"

static_assert(sizeof(double) == 8 && sizeof(float) == 4, "IEEE floats required");
static uint64_t bits(double d) { uint64_t r; std::memcpy(&r,&d,sizeof r); return r; }
static uint32_t bitsf(float d) { uint32_t r; std::memcpy(&r,&d,sizeof r); return r; }

// Exact bit-level copy of PiPNN 443a328 packFloatAndInt for this microbenchmark.
static inline double packFloatAndInt(float f, uint16_t id) {
  uint64_t b = bits(static_cast<double>(f));
  b = (b & ~uint64_t(0x7ff)) | (uint64_t(id) & 0x7ff);
  double out; std::memcpy(&out,&b,sizeof out); return out;
}
static inline std::pair<float,uint32_t> unpackDouble(double d) {
  uint64_t b = bits(d);
  uint32_t id = static_cast<uint32_t>(b & 0x7ff);
  b &= ~uint64_t(0x7ff);
  double clear; std::memcpy(&clear,&b,sizeof clear);
  return {static_cast<float>(clear), id};
}

// A: PiPNN's real Highway routine, with the same packed-double candidates.
static void original(const float* row, size_t n, size_t self,
                     std::vector<double>& scratch, double out[2], size_t& k) {
  scratch.clear();
  for (size_t j=0; j<n; ++j) {
    if (j != self) scratch.push_back(packFloatAndInt(row[j], static_cast<uint16_t>(j)));
  }
  k=std::min<size_t>(2,scratch.size());
  if (k) hwy::VQPartialSort(scratch.data(), scratch.size(), k, hwy::SortAscending());
  if (k>0) out[0]=scratch[0];
  if (k>1) out[1]=scratch[1];
}

// B: ONE pass, retaining two smallest packed doubles. ID tie rule preserved
// by comparing the *packed double*, NOT comparing float distance alone.
static void streaming(const float* row, size_t n, size_t self,
                      double out[2], size_t& k) {
  double first=std::numeric_limits<double>::infinity();
  double second=std::numeric_limits<double>::infinity();
  k=0;
  for (size_t j=0; j<n; ++j) {
    if (j==self) continue;
    double d=packFloatAndInt(row[j],static_cast<uint16_t>(j));
    if (k==0 || d<first) {
      second=first; first=d;
    } else if (k==1 || d<second) {
      second=d;
    }
    if (k<2) ++k;
  }
  if (k>0) out[0]=first;
  if (k>1) out[1]=second;
}

static std::vector<float> make_rows(size_t n, size_t rows, int scenario, uint64_t seed) {
  std::mt19937_64 rng(seed + 193*scenario + 997*n);
  std::vector<float> x(n*rows);
  for (size_t i=0; i<x.size(); ++i) {
    uint32_t v=static_cast<uint32_t>(rng()%1000000);
    switch (scenario) {
      case 0: x[i]=static_cast<float>(v)*0.0007f; break;
      case 1: x[i]=100.0f; break;                            // all tied floats
      case 2: x[i]=static_cast<float>(v%4); break;           // repeated ties
      case 3: x[i]=static_cast<float>(v%101)*0.000001f; break;
      case 4: x[i]=static_cast<float>(v%2?0.0:200.0); break;
      case 5: x[i]=-static_cast<float>(v%23)*0.5f; break;   // packed negative keys
      case 6: x[i]=static_cast<float>(v%3==0?0.0:1.0); break;
      case 7: x[i]=static_cast<float>(v%2 ? 1.0 : 1.000001); break;
      default: x[i]=static_cast<float>(v)*0.0007f;
    }
  }
  return x;
}

static int verify(int cases_per_size) {
  constexpr size_t sizes[]={2,3,4,8,16,32,64,128,256,352,512,1024};
  uint64_t checked=0;
  for (size_t n:sizes) {
    for (int scenario=0; scenario<8; ++scenario) {
      auto rows=make_rows(n,cases_per_size,scenario,20261023);
      std::vector<double> scratch; scratch.reserve(n);
      for (int r=0;r<cases_per_size;++r) {
        auto row=rows.data()+size_t(r)*n;
        double a[2]={},b[2]={};size_t ka=0,kb=0;
        original(row,n,size_t(r)%n,scratch,a,ka);
        streaming(row,n,size_t(r)%n,b,kb);
        if (ka!=kb || (ka>0 && bits(a[0])!=bits(b[0])) ||
            (ka>1 && bits(a[1])!=bits(b[1]))) {
          std::cerr << "FAIL n="<<n<<" scenario="<<scenario<<" row="<<r
                    <<" orig=("<<std::hex<<bits(a[0])<<","<<bits(a[1])
                    <<") scan=("<<bits(b[0])<<","<<bits(b[1])<<std::dec<<")\n";
          return 4;
        }
        for (size_t z=0;z<ka;++z) {
          auto ea=unpackDouble(a[z]); auto eb=unpackDouble(b[z]);
          if (ea.second!=eb.second || bitsf(ea.first)!=bitsf(eb.first)) {
            std::cerr<<"FAIL unpack n="<<n<<" row="<<r<<"\n";
            return 5;
          }
        }
        ++checked;
      }
    }
    std::cout<<"H17_CHECK size="<<n<<" status=PASS"<<std::endl;
  }
  std::cout<<"H17_VERIFY_PASS cases="<<checked<<""<<std::endl;
  return 0;
}

static volatile uint64_t sink=0;
static double measure(const std::vector<float>& data, size_t n,
                      size_t rows, bool use_stream) {
  std::vector<double> scratch; scratch.reserve(n);
  uint64_t check=0;
  auto t0=std::chrono::steady_clock::now();
  for(size_t r=0;r<rows;++r) {
    double out[2]={};size_t k=0;
    if (use_stream) streaming(data.data()+r*n,n,r%n,out,k);
    else original(data.data()+r*n,n,r%n,scratch,out,k);
    for(size_t j=0;j<k;++j) {
      // Prevent the compiler from deleting the measured work.
      auto unpacked=unpackDouble(out[j]);
      check += bits(out[j]) ^ uint64_t(unpacked.second+1)*0x9e3779b97f4a7c15ULL;
    }
  }
  auto t1=std::chrono::steady_clock::now();
  sink ^= check;
  return std::chrono::duration<double,std::milli>(t1-t0).count();
}

int main(int argc,char**argv) {
  int cases=160,reps=7; size_t rows=4096;
  for (int i=1;i<argc;++i) {
    std::string a=argv[i];
    if (i+1>=argc) throw std::runtime_error("Missing flag value: "+a);
    int v=std::stoi(argv[++i]);
    if(a=="--cases") cases=v;
    else if(a=="--reps") reps=v;
    else if(a=="--rows") rows=static_cast<size_t>(v);
    else throw std::runtime_error("Unknown argument "+a);
  }
  if (cases<1 || reps<1 || rows<16) throw std::runtime_error("Invalid cases/reps/rows");
  int rc=verify(cases);
  if (rc) return rc;
  for(size_t n:{size_t(64),size_t(128),size_t(256),size_t(352),size_t(512),size_t(1024)}) {
    auto data=make_rows(n,rows,0,20261023);
    // Warm both variants before timing; the input stays fixed across arms.
    measure(data,n,rows,false); measure(data,n,rows,true);
    for(int rep=0;rep<reps;++rep) {
      // ABBA-ish alternating order to reduce thermal/cache order bias.
      double a=0,b=0;
      if(rep%2==0){a=measure(data,n,rows,false);b=measure(data,n,rows,true);}
      else {b=measure(data,n,rows,true);a=measure(data,n,rows,false);}
      std::cout<<std::setprecision(12)<<"H17_BENCH n="<<n<<" rep="<<rep
               <<" original_ms="<<a<<" top2_ms="<<b
               <<" speedup="<<(a/b)<<std::endl;
    }
  }
  std::cout << "H17_END sink="<<sink<<std::endl;
  return 0;
}
