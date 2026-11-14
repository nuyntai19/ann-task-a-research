// R80: standalone model of the remaining-cluster drain in PiPNN MergeBuckets.
// NOT an ANN benchmark and NOT a complete replica of MergeBuckets's merge path.
#include <algorithm>
#include <atomic>
#include <chrono>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <iostream>
#include <numeric>
#include <queue>
#include <random>
#include <vector>

struct Bucket {
  std::vector<uint32_t> ids;
  static inline uint64_t copied_bytes = 0;
  Bucket() = default;
  explicit Bucket(std::vector<uint32_t> v) : ids(std::move(v)) {}
  Bucket(const Bucket& o) : ids(o.ids) { copied_bytes += o.ids.size() * sizeof(uint32_t); }
  Bucket(Bucket&&) noexcept = default;
  Bucket& operator=(Bucket&&) noexcept = default;
  Bucket& operator=(const Bucket& o) { ids = o.ids; copied_bytes += o.ids.size() * sizeof(uint32_t); return *this; }
  size_t size() const { return ids.size(); }
};
struct CompareBucketsBySize {
  bool operator()(const Bucket& l, const Bucket& r) const { return l.size() > r.size(); }
};

std::vector<Bucket> make_buckets(size_t n, uint32_t seed) {
  std::mt19937 rng(seed);
  std::uniform_int_distribution<int> sizes(0, 384);
  std::vector<Bucket> a;
  a.reserve(n);
  for (size_t k=0;k<n;k++) {
    size_t sz = static_cast<size_t>(sizes(rng));
    std::vector<uint32_t> ids(sz);
    for(size_t j=0;j<sz;j++) ids[j] = static_cast<uint32_t>(k * 401 + j);
    a.emplace_back(std::move(ids));
  }
  return a;
}

std::vector<Bucket> priority_queue_copy_drain(std::vector<Bucket> input) {
  std::priority_queue<Bucket,std::vector<Bucket>,CompareBucketsBySize> pq;
  for (auto& b: input) pq.push(std::move(b));
  std::vector<Bucket> remaining;
  remaining.reserve(pq.size());
  while(!pq.empty()) {
    remaining.emplace_back(pq.top()); // source-equivalent copy at pipnn.h:159-160
    pq.pop();
  }
  return remaining;
}

std::vector<Bucket> vector_heap_move_drain(std::vector<Bucket> input) {
  CompareBucketsBySize cmp;
  std::vector<Bucket> heap;
  heap.reserve(input.size());
  for (auto& b: input) { heap.push_back(std::move(b)); std::push_heap(heap.begin(),heap.end(),cmp); }
  std::vector<Bucket> remaining;
  remaining.reserve(heap.size());
  while (!heap.empty()) {
    std::pop_heap(heap.begin(),heap.end(),cmp);
    remaining.emplace_back(std::move(heap.back()));
    heap.pop_back();
  }
  return remaining;
}

uint64_t signature(const std::vector<Bucket>& v) {
  uint64_t h=1469598103934665603ull;
  for (auto& b:v) {
    h ^= b.size(); h *= 1099511628211ull;
    for (auto x:b.ids) {h ^= x;h *= 1099511628211ull;}
  }
  return h;
}

void check(size_t n, uint32_t seed) {
  auto input=make_buckets(n,seed);
  auto input2=input; // excluded from work-copy accounting
  Bucket::copied_bytes=0;
  auto t1=std::chrono::steady_clock::now();
  auto a=priority_queue_copy_drain(std::move(input));
  auto t2=std::chrono::steady_clock::now();
  auto refcopies=Bucket::copied_bytes;
  Bucket::copied_bytes=0;
  auto b=vector_heap_move_drain(std::move(input2));
  auto t3=std::chrono::steady_clock::now();
  auto newcopies=Bucket::copied_bytes;
  if(a.size()!=b.size()||signature(a)!=signature(b)) {
    std::cerr << "R80_HEAP_DRAIN_ORDER_MISMATCH n="<<n<<" seed="<<seed<<"\n";exit(2);
  }
  for(size_t i=0;i<a.size();i++) if(a[i].ids!=b[i].ids) {
    std::cerr << "R80_HEAP_DRAIN_BUCKET_MISMATCH\n";exit(3);
  }
  auto ms1=std::chrono::duration<double,std::milli>(t2-t1).count();
  auto ms2=std::chrono::duration<double,std::milli>(t3-t2).count();
  std::cout << "R80_PROBE_RESULT n="<<n<<" seed="<<seed
            <<" copied_bytes_reference="<<refcopies<<" copied_bytes_moveheap="<<newcopies
            <<" ref_ms="<<ms1<<" move_ms="<<ms2<<" signature="<<signature(a)<<"\n";
}

int main(int argc,char**argv){
  size_t n= (argc>1) ? std::strtoull(argv[1],nullptr,10) : 12000;
  if(n>100000) {std::cerr<<"max 100000 buckets\n";return 1;}
  for(uint32_t seed=1;seed<=4;seed++) check(n,seed*1777);
  std::cout<<"R80_HEAP_DRAIN_STANDALONE_PARITY_PASS\n";
  std::cout<<"R80_NOT_PIPNN_BUCKET_MERGE_NOT_FULL_BUILD_NOT_RSS\n";
}
