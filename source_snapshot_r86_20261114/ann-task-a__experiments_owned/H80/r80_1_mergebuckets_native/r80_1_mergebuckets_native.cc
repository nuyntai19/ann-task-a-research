// R80.1: exact function-level native PiPNN MergeBuckets differential test.
// Includes the pinned original pipnn.h and calls original cluster::MergeBuckets.
// Alternative changes only heap extraction from copy to move.
// No SIFT dataset, ANN graph BUILD, or H70 source modification.
#include "PipNN/pipnn.h"
#include <algorithm>
#include <chrono>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <iostream>
#include <numeric>
#include <queue>
#include <random>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

namespace {
using Id = std::uint32_t;
struct DummyGraph {};
struct DummyPoint { using distanceType = float; };
struct DummyRange { using Point = DummyPoint; };
using Cluster = parlayANN::cluster<DummyGraph,DummyPoint,DummyRange,Id>;
using Bucket = Cluster::Bucket;
using Seq = parlay::sequence<Bucket>;

struct PopCounters {
  std::uint64_t original_copy_id_bytes_avoided = 0;
  std::uint64_t popped = 0;
};

void check(bool ok, const std::string& why) {
  if (!ok) throw std::runtime_error(why);
}

// Source-equivalent MergeBuckets, but replaces priority_queue with a
// vector plus push_heap/pop_heap so the popped bucket can be moved.
// Intentionally does NOT bulk-make_heap or change comparator/tie behavior.
void move_heap_merge(Cluster& c, Seq& clusters,
                     std::vector<Bucket>& finished_buckets,
                     Seq& remaining_clusters, PopCounters& counts) {
  if (c.NO_MERGE) {
    remaining_clusters = std::move(clusters);
    return;
  }
  Cluster::CompareBucketsBySize cmp;
  std::vector<Bucket> heap;
  const auto push_bucket = [&](Bucket&& b) {
    heap.push_back(std::move(b));
    std::push_heap(heap.begin(), heap.end(), cmp);
  };
  const auto pop_bucket = [&]() -> Bucket {
    check(!heap.empty(), "attempted to pop empty heap");
    std::pop_heap(heap.begin(), heap.end(), cmp);
    const size_t len = heap.back().size();
    counts.original_copy_id_bytes_avoided += len * sizeof(Id);
    ++counts.popped;
    Bucket result = std::move(heap.back());
    heap.pop_back();
    return result;
  };

  for (size_t i = 0; i < clusters.size(); ++i) {
    push_bucket(std::move(clusters[i]));
  }
  clusters.resize(0);

  while (heap.size() > 1) {
    // Root stays in the heap while we inspect it, matching pq.top().
    if (heap.front().size() >= c.MIN_CLUSTER_SIZE) break;
    size_t merged_size = heap.front().size();
    std::vector<Bucket> merged_buckets;
    merged_buckets.emplace_back(pop_bucket());

    while (!heap.empty() && merged_size < c.MIN_CLUSTER_SIZE &&
           merged_size + heap.front().size() <= c.MAX_MERGED_CLUSTER_SIZE) {
      merged_size += heap.front().size();
      merged_buckets.emplace_back(pop_bucket());
    }

    if (merged_buckets.size() == 1) {
      CHECK(merged_buckets[0].size() <= c.MAX_CLUSTER_SIZE);
      if (merged_buckets[0].size() > c.MAX_CLUSTER_SIZE) {
        std::cout << "Pushing a cluster that is too large: "
                  << merged_buckets[0].size() << std::endl;
      }
      finished_buckets.emplace_back(std::move(merged_buckets[0]));
      break;
    }

    CHECK(merged_size > 0);
    auto new_bucket = parlay::sequence<Id>::uninitialized(merged_size);
    size_t pos = 0;
    for (auto& b : merged_buckets) {
      std::memcpy(new_bucket.begin() + pos, b.begin(),
                  b.size() * sizeof(Id));
      pos += b.size();
    }
    new_bucket = parlay::remove_duplicates(new_bucket);
    CHECK(new_bucket.size() > 0);
    if (new_bucket.size() >= c.MIN_CLUSTER_SIZE &&
        new_bucket.size() <= c.MAX_CLUSTER_SIZE) {
      finished_buckets.push_back(std::move(new_bucket));
    } else {
      push_bucket(std::move(new_bucket));
    }
  }
  while (!heap.empty()) {
    remaining_clusters.emplace_back(pop_bucket());
  }
}

Seq make_fixture(size_t n, unsigned seed, int kind) {
  std::mt19937 rng(seed);
  Seq out;
  out.resize(n);
  for (size_t i = 0; i < n; ++i) {
    size_t len;
    switch (kind) {
      case 0: len = 75 + (rng() % 180); break; // no merging, all >= minimum
      case 1: len = 1 + (rng() % 190); break; // mixed small/large
      case 2: len = 17; break; // equal-size small, heavy merging
      case 3: len = 88; break; // equal-size big, heap ties
      case 4: len = 1 + (rng() % 100); break; // duplicate-heavy merge
      case 5: len = 1 + (rng() % 390); break; // mixed with constrained max merger
      case 6: len = 1 + (rng() % 200); break; // NO_MERGE path
      default: throw std::runtime_error("unknown test fixture");
    }
    out[i].resize(len);
    for (size_t j = 0; j < len; ++j) {
      const std::uint64_t v = kind == 4
          ? ((i * 13 + j * 17 + seed) % 103u) // duplicate-rich
          : ((i * 113 + j * 17 + seed) % 1000003u);
      out[i][j] = static_cast<Id>(v);
    }
  }
  return out;
}

std::uint64_t signature(const Seq& remaining,
                        const std::vector<Bucket>& finished) {
  std::uint64_t h = 1469598103934665603ull;
  const auto add = [&](std::uint64_t x, std::uint64_t& val) {
    val ^= x;
    val *= 1099511628211ull;
  };
  add(0xFFFFFFFFu,h);
  for (const auto& b : finished) {
    add(b.size(),h);
    for (Id v : b) add(v,h);
  }
  add(0xEEEEEEEEu,h);
  for (const auto& b : remaining) {
    add(b.size(),h);
    for (Id v : b) add(v,h);
  }
  return h;
}

template <class S1, class S2>
void compare_bucket_vectors(const S1& a, const S2& b,
                            const char* kind, int fixture_kind, unsigned seed) {
  check(a.size() == b.size(), std::string(kind)+" bucket count mismatch");
  for (size_t i = 0; i < a.size(); ++i) {
    check(a[i].size() == b[i].size(), std::string(kind)+" size mismatch in case "+std::to_string(fixture_kind));
    for (size_t j = 0; j < a[i].size(); ++j)
      check(a[i][j] == b[i][j], std::string(kind)+" element/order mismatch case="+
            std::to_string(fixture_kind)+" seed="+std::to_string(seed)+
            " bucket="+std::to_string(i)+" pos="+std::to_string(j));
  }
}

void run_case(size_t n, unsigned seed, int kind) {
  auto original_input = make_fixture(n,seed,kind);
  auto optimized_input = original_input; // cloning outside timed region
  Cluster original;
  Cluster optimized;
  const size_t low = 64, high = 512;
  original.MIN_CLUSTER_SIZE = optimized.MIN_CLUSTER_SIZE = low;
  original.MAX_CLUSTER_SIZE = optimized.MAX_CLUSTER_SIZE = high;
  original.MAX_MERGED_CLUSTER_SIZE = optimized.MAX_MERGED_CLUSTER_SIZE =
      (kind == 5 ? 165u : high);
  original.NO_MERGE = optimized.NO_MERGE = kind == 6;

  std::vector<Bucket> ref_finished, out_finished;
  Seq ref_remaining, out_remaining;
  const auto t0 = std::chrono::steady_clock::now();
  original.MergeBuckets(original_input,ref_finished,ref_remaining);
  const auto t1 = std::chrono::steady_clock::now();
  PopCounters counters;
  move_heap_merge(optimized,optimized_input,out_finished,out_remaining,counters);
  const auto t2 = std::chrono::steady_clock::now();
  compare_bucket_vectors(ref_finished,out_finished,"finished",kind,seed);
  compare_bucket_vectors(ref_remaining,out_remaining,"remaining",kind,seed);
  const auto ref_sig = signature(ref_remaining,ref_finished);
  const auto out_sig = signature(out_remaining,out_finished);
  check(ref_sig == out_sig,"checksum mismatch");
  const double ref_ms = std::chrono::duration<double,std::milli>(t1-t0).count();
  const double opt_ms = std::chrono::duration<double,std::milli>(t2-t1).count();
  std::cout << "R80_1_NATIVE_CASE_PARITY_PASS fixture="<<kind
            << " seed="<<seed<<" inputs="<<n
            << " finished="<<ref_finished.size()
            << " remaining="<<ref_remaining.size()
            << " pop_events="<<counters.popped
            << " potential_copy_id_bytes="<<counters.original_copy_id_bytes_avoided
            << " reference_ms="<<ref_ms
            << " moveheap_ms="<<opt_ms
            << " signature="<<ref_sig <<"\n";
}

} // namespace

int main(int argc, char** argv) {
  try {
    const size_t n = argc > 1 ? std::strtoull(argv[1],nullptr,10) : 1600u;
    if (n < 64 || n > 5000) throw std::runtime_error("n must be in [64,5000]");
    for (int kind=0;kind<7;++kind)
      for (unsigned seed : {7u,191u,3889u})
        run_case(n,seed,kind);
    std::cout << "R80_1_REAL_PIPNN_MERGEBUCKETS_PARITY_PASS cases=21\n";
    std::cout << "R80_1_NOT_FULL_BUILD_NOT_BUILD_WALL_NOT_PEAK_RSS_NOT_RECALL\n";
    return 0;
  } catch (const std::exception& e) {
    std::cerr << "R80_1_NATIVE_MERGEBUCKETS_FAIL: " << e.what() << "\n";
    return 2;
  }
}
