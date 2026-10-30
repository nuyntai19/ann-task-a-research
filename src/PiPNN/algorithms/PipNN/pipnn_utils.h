// This code is part of the Problem Based Benchmark Suite (PBBS)
// Copyright (c) 2011 Guy Blelloch and the PBBS team
//
// Permission is hereby granted, free of charge, to any person obtaining a
// copy of this software and associated documentation files (the
// "Software"), to deal in the Software without restriction, including
// without limitation the rights (to use, copy, modify, merge, publish,
// distribute, sublicense, and/or sell copies of the Software, and to
// permit persons to whom the Software is furnished to do so, subject to
// the following conditions:
//
// The above copyright notice and this permission notice shall be included
// in all copies or substantial portions of the Software.
//
// THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS
// OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
// MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
// NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE
// LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION
// OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION
// WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

#pragma once

#include <math.h>

#include <algorithm>
#include <atomic>
#include <type_traits>
#include <Eigen/Dense>
#include <cfloat>


#include "../utils/graph.h"
#include "../utils/hash.h"
#include "parlay/parallel.h"
#include "parlay/primitives.h"
#include "parlay/random.h"

#include "hwy/contrib/sort/vqsort-inl.h"
#include "hwy/contrib/sort/vqsort.h"
#include "hwy/highway.h"
#include "h25_r1_hook.h"
#include <absl/types/span.h>


// #ifndef NDEBUG
#define CHECK(expr)                                                        \
  do {                                                                     \
    if (!(expr)) {                                                         \
      std::cerr << "CHECK FAILED: " << #expr << "\n    File: " << __FILE__ \
                << "\n    Line: " << __LINE__ << std::endl;                \
      std::abort();                                                        \
    }                                                                      \
  } while (0)
//#else
//#define CHECK(expr) ((void)0)
//#endif

namespace parlayANN {

std::atomic<size_t> dist_traversed(0);

//using GraphH = NghDistGraphHeap<uint32_t>;

// Forward declarations (defined later in this file).
template <class Iter> void VQSort(Iter b, Iter e);
double packFloatAndInt(float float_val, uint16_t int_val);
std::pair<float, uint32_t> unpackDouble(double packed_val);

template <typename Point, typename PointRange, typename indexType>
struct cluster_utils {
  using distanceType = typename Point::distanceType;
  using edge = std::pair<indexType, indexType>;
  using pid = std::pair<indexType, distanceType>;
  using GraphI = Graph<indexType>;
  using PR = PointRange;

  // using sketchHash = SketchHash<Point,PointRange,indexType>;
  // using GraphH = LSHGraph<indexType, float, sketchHash>;


  static constexpr indexType kNullId = std::numeric_limits<indexType>::max();
  static constexpr distanceType kNullDist =
      std::numeric_limits<distanceType>::max();
  using labelled_edge = std::pair<edge, distanceType>;
  static constexpr labelled_edge kNullEdge = {{kNullId, kNullId}, kNullDist};

  // robustPrune routine as found in DiskANN paper, with the exception that the
  // new candidate set is added to the field new_nbhs instead of directly
  // replacing the out_nbh of p
  template <class NghContainer>
  static void robustPrune(const NghContainer& neighbors, indexType p, PR &Points,
                          GraphI &G, double alpha, size_t degree) {
    // add out neighbors of p to the candidate set.
    thread_local std::vector<pid> candidates;
    candidates.clear();
    for (auto nghdist : neighbors) {
      candidates.push_back(std::make_pair(nghdist.point_id, nghdist.norm));
    }
    // Sort the candidate set by distance from p using VQSort.
    // Pack (distance, local_index) into doubles, sort, then unpack.
    thread_local std::vector<double> packed;
    packed.resize(candidates.size());
    for (size_t i = 0; i < candidates.size(); ++i) {
      packed[i] = packFloatAndInt(candidates[i].second, static_cast<uint16_t>(i));
    }
    VQSort(packed.data(), packed.data() + packed.size());
    thread_local std::vector<pid> sorted_candidates;
    sorted_candidates.resize(candidates.size());
    for (size_t i = 0; i < packed.size(); ++i) {
      auto [dist, local_idx] = unpackDouble(packed[i]);
      sorted_candidates[i] = candidates[local_idx];
    }
    std::swap(candidates, sorted_candidates);

    // No need to remove duplicates, as the neighbors container is
    // constructed out of a hash_set.

    std::vector<int> new_nbhs;
    new_nbhs.reserve(degree);

    float inverse_alpha = 1.0 / alpha;
    size_t candidate_idx = 0;
    while (new_nbhs.size() < degree && candidate_idx < candidates.size()) {
      // Don't need to do modifications.
      const indexType p_prime = candidates[candidate_idx].first;
      const auto dist_pprime = candidates[candidate_idx].second * inverse_alpha;
      candidate_idx++;
      if (p_prime == p) continue;
      bool add = true;
      for (auto p_star : new_nbhs) {
        const auto dist_starprime = Points[p_star].distance(Points[p_prime]);
        if (dist_starprime <= dist_pprime) {
          add = false;
          break;
        }
      }
      if (add) new_nbhs.push_back(p_prime);
    }
    dist_traversed.fetch_add(candidate_idx, std::memory_order_relaxed);
    G[p].update_neighbors(new_nbhs);
  }

};


template <class Iter>
void VQSort(Iter b, Iter e) {
  hwy::VQSort(b, e-b, hwy::SortAscending());
}

template <class Iter>
void VQPartialSort(Iter b, Iter e, size_t k) {
  hwy::VQPartialSort(b, e-b, k, hwy::SortAscending());
}

template <class Iter>
void VQSelect(Iter b, Iter e, size_t k) {
  hwy::VQSelect(b, e-b, k, hwy::SortAscending());
}

// A union allows us to access the same piece of memory in different ways.
// Here, we can write a 'double' and read its raw 64 bits as a 'uint64_t'.
union DoubleConverter {
    double d;
    uint64_t i;
};

/**
 * @brief Packs a float and an 11-bit integer into a double.
 *
 * The function converts the float to a double, then overwrites the
 * lowest 11 bits of the double's mantissa with the provided integer value.
 *
 * @param float_val The floating-point value to pack.
 * @param int_val The 11-bit integer value to pack (must be in range [0, 2047]).
 * @return A double containing the packed data.
 */
double packFloatAndInt(float float_val, uint16_t int_val) {
    DoubleConverter converter;

    // 1. Start by converting the float to a double. This sets the sign,
    //    exponent, and the most significant bits of the mantissa correctly.
    converter.d = static_cast<double>(float_val);

    // 2. Define masks for bitwise operations.
    // Mask to clear the lowest 11 bits (all 1s except for the last 11 bits).
    // ~0ULL is all 1s. (1ULL << 11) is 2048. 2048 - 1 is 2047 (0x7FF), which is 11 set bits.
    // The inverse gives us a mask to clear those bits.
    const uint64_t clear_mask = ~((1ULL << 11) - 1);

    // Mask to ensure the input integer is only 11 bits. 0x7FF is 0...011111111111.
    const uint64_t int_mask = 0x7FF;

    // 3. Clear the lowest 11 bits of the double's integer representation.
    converter.i &= clear_mask;

    // 4. Combine (OR) the cleared integer with the 11-bit value.
    // We mask int_val to be safe and ensure no higher bits are set.
    converter.i |= (static_cast<uint64_t>(int_val) & int_mask);

    // 5. Return the result as a double.
    return converter.d;
}

/**
 * @brief Unpacks a double back into a float and an 11-bit integer.
 *
 * @param packed_val The double containing the packed data.
 * @return A std::pair containing the extracted float and the 11-bit integer.
 */
std::pair<float, uint32_t> unpackDouble(double packed_val) {
    DoubleConverter converter;
    converter.d = packed_val;

    // 1. Define the mask to extract the lowest 11 bits.
    const uint64_t extract_mask = (1ULL << 11) - 1; // 0x7FF

    // 2. Extract the 11-bit integer by ANDing with the mask.
    uint32_t extracted_int = static_cast<uint16_t>(converter.i & extract_mask);

    // 3. To get the original float value, we must clear the packed integer bits
    //    from the double's representation.
    converter.i &= ~extract_mask;

    // 4. Convert the modified double back to a float.
    float extracted_float = static_cast<float>(converter.d);

    return {extracted_float, extracted_int};
}



thread_local uint8_t* tl_dist_mat = nullptr;
thread_local uint8_t* tl_point_mat = nullptr;
size_t kMaxClusterSize = 2048;
size_t kMaxDimension = 2048;

void* get_point_mat() {
  if (tl_point_mat == nullptr) {
    // Enough space for float points.
    tl_point_mat = (uint8_t*)_mm_malloc(kMaxClusterSize * kMaxDimension * sizeof(uint32_t), 64);
    for (size_t i=0; i < kMaxClusterSize * kMaxDimension * sizeof(uint32_t); ++i) {
      tl_point_mat[i] = 0;
    }
  }
  return tl_point_mat;
}

// n by n output matrix.
void* get_dist_mat() {
  if (tl_dist_mat == nullptr) {
    // Enough space for float distances.
    tl_dist_mat = (uint8_t*)_mm_malloc(kMaxClusterSize * kMaxClusterSize * sizeof(uint32_t), 64);
    for (size_t i=0; i < kMaxClusterSize * kMaxClusterSize * sizeof(uint32_t); ++i) {
      tl_dist_mat[i] = 0;
    }
  }
  return tl_dist_mat;
}


// Materializes the output floating-point distmat into the
// thread-local dist_mat variable above.
template <typename PR, typename Seq>
auto eigen_build_distmat(Seq& seq, PR& all_points) {
  size_t n = seq.size();
  using coord_type = typename PR::Point::T;

  size_t dimension = all_points.get_dims();
  float* dist_mat = (float*)get_dist_mat();
  float* point_mat = (float*)get_point_mat();

  // Copy the points into point_mat, and convert to floats.
  for (size_t i=0; i < n; ++i) {
    coord_type* loc = (coord_type*)all_points.location(seq[i]);
    for (size_t j=0; j < dimension; ++j) {
      point_mat[i*dimension + j] = static_cast<float>(loc[j]);
    }
  }

  Eigen::Map<const Eigen::Matrix<float, Eigen::Dynamic, Eigen::Dynamic, Eigen::RowMajor>> P(point_mat, n, dimension);
  // TODO: can we just do this once, offline for every point and
  // re-use?
  Eigen::Matrix<float, Eigen::Dynamic, 1> P_sq_norms = P.rowwise().squaredNorm();
  Eigen::Map<Eigen::Matrix<float, Eigen::Dynamic, Eigen::Dynamic, Eigen::RowMajor>> D(dist_mat, n, n);

  // Sets the lower-triangular D = P x P^T
  D.setZero();
  D.selfadjointView<Eigen::Lower>().rankUpdate(P);

  using Point = typename PR::Point;
  if (Point::is_metric()) {
    // Finish up square norm computation, if needed.
    for (size_t i=0; i < n; ++i) {
      for (size_t j=0; j <= i; ++j) {
        float tmp = D(i, j);
        D(i, j) = -2*tmp;
        D(i, j) += P_sq_norms[i] + P_sq_norms[j];
      }
    }
  } else {
    for (size_t i=0; i < n; ++i) {
      for (size_t j=0; j <= i; ++j) {
        D(i, j) = -1*D(i, j);
      }
    }
  }
}

thread_local uint8_t* tile_point_mat   = nullptr;
thread_local uint8_t* tile_dist_mat    = nullptr;
constexpr size_t kMaxTileSize   = 2048;
constexpr size_t kMaxLeaderSize = 2048;

static void* get_tile_point_mat() {
  if (!tile_point_mat)
    tile_point_mat = (uint8_t*)_mm_malloc(
      kMaxTileSize * kMaxDimension * sizeof(float), 64);
  return tile_point_mat;
}

static void* get_tile_dist_mat() {
  if (!tile_dist_mat)
    tile_dist_mat = (uint8_t*)_mm_malloc(
      kMaxTileSize * kMaxLeaderSize * sizeof(float), 64);
  return tile_dist_mat;
}


template <class PR, class Bucket>
void assign_leaders(PR& Points,
                    const Bucket& ids,
                    const Bucket& leaders,
                    size_t fanout,
                    parlay::sequence<std::pair<uint32_t,uint32_t>>& flat,
                    int granularity) {
  using coord_type = typename PR::Point::T;
  const size_t N   = ids.size();
  const size_t M   = leaders.size();
  const size_t dim = Points.dimension();

  //assert(M   <= kMaxLeaderSize);
  //assert(dim <= kMaxDimension);

  // this is a buffer for the leader points shared across all threads spawned here
  float* Lmat = (float*)_mm_malloc(M * dim * sizeof(float), 64);
  for (size_t j = 0; j < M; ++j) {
    coord_type* loc = reinterpret_cast<coord_type*>(Points.location(leaders[j]));
    for (size_t d = 0; d < dim; ++d) {
        Lmat[j*dim + d] = static_cast<float>(loc[d]);
    }
}
  //std::cout << "leader buffer allocated" << std::endl;
  // eigen map leader points
  Eigen::Map<Eigen::Matrix<float, Eigen::Dynamic, Eigen::Dynamic, Eigen::RowMajor>> L(Lmat, M, dim);
  // compute square norms of leaders
  Eigen::Matrix<float, Eigen::Dynamic, 1> leader_sq = L.rowwise().squaredNorm();

  // routine to do matrix multiplication and selection
  auto process_chunk = [&](size_t chunk_idx) {
    size_t start = chunk_idx * kMaxTileSize;
    size_t end   = std::min(start + kMaxTileSize, N);
    size_t T     = end - start;

    // copy queries into thread-local buffer
    float* Pmat = (float*)get_tile_point_mat();
    for (size_t ti = 0; ti < T; ++ti) {
      auto loc = (coord_type*)Points.location(ids[start + ti]);
      for (size_t d = 0; d < dim; ++d)
        Pmat[ti*dim + d] = static_cast<float>(loc[d]);
    }

    // map P and the output D
    Eigen::Map<
      Eigen::Matrix<float, Eigen::Dynamic, Eigen::Dynamic, Eigen::RowMajor>
    > P(Pmat, T, dim),
      D((float*)get_tile_dist_mat(), T, M);

    // GEMM + finish squared distances
    D.noalias() = P * L.transpose();
    Eigen::Matrix<float, Eigen::Dynamic,1> P_sq = P.rowwise().squaredNorm();


    using Point = typename PR::Point;

    if (Point::is_metric()) {
    // 1) scale the dot‐products by -2
    D *= -2.0f;

    // 2) add each query’s norm to its entire row:
    //    P_sq is a (T×1) vector, so colwise+= broadcasts it to every column
    D.colwise() += P_sq;

    // 3) add each leader’s norm to its entire column:
    //    leader_sq is (M×1), so we need it as a RowVector (1×M) to rowwise+=
    D.rowwise() += leader_sq.transpose();
    }
    else {
    // non‐metric: just negate the raw dot‐products
    D = -D;
    }

    std::vector<double> cc;
    cc.resize(M);
    for (size_t ti = 0; ti < T; ++ti) {
      float* row = reinterpret_cast<float*>(get_tile_dist_mat()) + ti * M;
      for (size_t j =0; j < M; ++j) {
        cc[j] = packFloatAndInt(row[j],j);
      }
      double* cd = (double*)cc.data();
      VQPartialSort(cd, cd + cc.size(), fanout);
      std::pair<float, uint32_t>* pairs = (std::pair<float, uint32_t>*)cd;
      for (size_t fn = 0; fn < fanout; ++fn) {
        double d = cd[fn];
        pairs[fn] = unpackDouble(d);
        flat[(start + ti)*fanout + fn] = std::make_pair(pairs[fn].second, ids[start + ti]);
      }
    }


  };

  size_t num_chunks = (N + kMaxTileSize - 1) / kMaxTileSize;
  if (N < (size_t)granularity) {
    for (size_t c = 0; c < num_chunks; ++c) process_chunk(c);
  } else {
    parlay::parallel_for(0, num_chunks,
      [&](size_t c){ process_chunk(c); }
    );
  }

  _mm_free(Lmat);
}


template<typename GraphH, typename PR>
void eigen_knn(GraphH &G, parlay::sequence<uint32_t> &active_indices, PR &Points, size_t MST_DEG, size_t h25_leaf_id) {
  auto N = active_indices.size();
  eigen_build_distmat(active_indices, Points);
  float* dist_mat = (float*)get_dist_mat();
  const bool h25_target = h25_r1::target_leaf(static_cast<uint32_t>(h25_leaf_id));
  if (h25_target && MST_DEG != 2) h25_r1::fail("MST_DEG must be 2 for this H18 capture");

  using indexType = uint32_t;
  // Step 1: Find all DIRECTED k-NN edges first.
  // Store them as {source, destination, distance} tuples.
  std::vector<std::tuple<uint32_t, uint32_t, float>> directed_edges;
  directed_edges.reserve(N * MST_DEG);

  std::vector<double> Q;
  Q.reserve(N);

  for (size_t i = 0; i < N; ++i) {
    Q.clear();
    for (indexType j = 0; j < N; ++j) {
      if (i == j) continue;
      float dist_ij = (i < j) ? dist_mat[j * N + i] : dist_mat[i * N + j];
      double packed = packFloatAndInt(dist_ij, j);
      Q.push_back(packed);
    }
    size_t limit = std::min(MST_DEG, Q.size());
    VQPartialSort(Q.data(), Q.data() + Q.size(), limit);
    
    uint32_t global_i = active_indices[i];
    if (h25_target) {
      if (limit != 2) h25_r1::fail("Local Top2 row must contain 2 candidates");
      auto h25_first = unpackDouble(Q[0]);
      auto h25_second = unpackDouble(Q[1]);
      h25_r1::check_row(static_cast<uint32_t>(h25_leaf_id), global_i,
                        active_indices[h25_first.second], active_indices[h25_second.second]);
    }
    for (size_t j = 0; j < limit; j++) {
      auto unpacked = unpackDouble(Q[j]);
      uint32_t global_neighbor = active_indices[unpacked.second];
      float dist = unpacked.first;
      if (h25_target) {
        uint32_t new_neighbor = h25_r1::replacement(static_cast<uint32_t>(h25_leaf_id), global_i, global_neighbor);
        if (new_neighbor != global_neighbor) {
          size_t local_new = N;
          for (size_t candidate = 0; candidate < N; ++candidate)
            if (active_indices[candidate] == new_neighbor) { local_new = candidate; break; }
          if (local_new >= N || local_new == i) h25_r1::fail("Replacement is not within original leaf");
          // Native eigen_build_distmat already computed this pair (upper-triangular access).
          dist = (i < local_new) ? dist_mat[local_new*N + i] : dist_mat[i*N + local_new];
          global_neighbor = new_neighbor;
        }
      }
      directed_edges.emplace_back(global_i, global_neighbor, dist);
    }
  }

  // the problem with this approach is that we only merge one neighbor at a time.
  for (const auto& edge : directed_edges) {
    uint32_t u = std::get<0>(edge);
    uint32_t v = std::get<1>(edge);
    float weight = std::get<2>(edge);
    
    // Create temporary spans for merging
    std::pair<uint32_t, float> forward_edge = {v, weight};
    std::pair<uint32_t, float> reverse_edge = {u, weight};
    
    auto span_f = absl::MakeSpan(&forward_edge, 1);
    auto span_r = absl::MakeSpan(&reverse_edge, 1);

    G.merge_neighbors(u, span_f);
    G.merge_neighbors(v, span_r);
  }
}


} // end namespace
