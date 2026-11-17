#pragma once

#include <math.h>

#include <algorithm>
#include <queue>
#include <random>
// R85_B1_SNAPSHOT_INCLUDES_BEGIN
#include <algorithm>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <stdexcept>
#include <tuple>
#include <vector>
// R85_B1_SNAPSHOT_INCLUDES_END

#include <set>
#include <utility>
#include <bitset>

#include "../bench/parse_command_line.h"
#include "../utils/graph.h"
#ifdef R70_TWO_TIER
#include "../utils/r70_two_tier_lshgraph.h"
#endif // R70_COMPILE_TIME_RESERVOIR_SELECTION
#include "pipnn_utils.h"
#include "parlay/parallel.h"
#include "parlay/primitives.h"
#include "parlay/random.h"


namespace parlayANN {

std::atomic<size_t> leaf_count(0);

template <typename GraphH, typename Point, typename PointRange, typename indexType>
struct cluster {
  using distanceType = typename Point::distanceType;
  using edge = std::pair<indexType, indexType>;
  using labelled_edge = std::pair<edge, distanceType>;
  using GraphI = Graph<indexType>;
  using PR = PointRange;
  using Bucket = parlay::sequence<uint32_t>;

  struct CompareBucketsBySize {
    bool operator()(const Bucket &lhs, const Bucket &rhs) const {
      return lhs.size() > rhs.size();
    }
  };

  using utils = cluster_utils<Point, PointRange, indexType>;

  cluster() {}

  // ===== Shared helpers used by both LevelByLevelSketch and RecursivelySketch =====

  // Selects leaders by random sampling, assigns all points in `ids` to their
  // nearest leaders, and returns the resulting non-empty clusters.
  parlay::sequence<Bucket> SelectAndAssignLeaders(
      PR& Points, Bucket& ids, int depth, int initial_fanout,
      size_t seed, int fanout_levels, std::vector<int>& fanout_scheme,
      size_t fixed_leaders) {
    size_t num_leaders =
        (depth == 0) ? TOP_LEVEL_NUM_LEADERS : ids.size() * FRACTION_LEADERS;
    if (fixed_leaders != 0) num_leaders = fixed_leaders;
    num_leaders = std::min<size_t>(num_leaders, MAX_NUM_LEADERS);
    num_leaders = std::max<size_t>(num_leaders, 3);

    COMPARISONS.fetch_add(num_leaders * ids.size(), std::memory_order_relaxed);

    Bucket leaders;
    std::mt19937 prng(seed);
    leaders.resize(num_leaders);
    std::sample(ids.begin(), ids.end(), leaders.begin(), leaders.size(), prng);

    int fanout = initial_fanout;
    if (depth < (int)fanout_scheme.size()) {
      fanout = fanout_scheme[depth];
    }
    fanout = std::min<int>(fanout, (int)num_leaders);

    int granularity = 5000;
    parlay::sequence<std::pair<uint32_t, uint32_t>> flat(ids.size() * fanout);
    parlay::internal::timer t;
    t.start();
    assign_leaders(Points, ids, leaders, fanout, flat, granularity);
    if (depth == 0) {
      t.next("first level assign time");
    }

    parlay::sequence<Bucket> clusters =
        parlay::group_by_index(flat, leaders.size());
    leaders.clear();

    // Filter out empty clusters produced by group_by_index.
    clusters = parlay::filter(
        clusters, [](const Bucket& b) { return b.size() > 0; });
    return clusters;
  }

  // Merges undersized clusters using a priority queue. Separates the input
  // clusters into:
  //   - finished_buckets: properly sized buckets (done, no further processing)
  //   - remaining_clusters: buckets that still need recursion or further splitting
  // When NO_MERGE is true, all clusters go directly to remaining_clusters.
  void MergeBuckets(
      parlay::sequence<Bucket>& clusters,
      std::vector<Bucket>& finished_buckets,
      parlay::sequence<Bucket>& remaining_clusters) {
    if (NO_MERGE) {
      remaining_clusters = std::move(clusters);
      return;
    }

    std::priority_queue<Bucket, std::vector<Bucket>, CompareBucketsBySize> pq;
    for (size_t i = 0; i < clusters.size(); ++i) {
      pq.push(std::move(clusters[i]));
    }
    clusters.resize(0);

    while (pq.size() > 1) {
      auto& top = pq.top();
      if (top.size() >= MIN_CLUSTER_SIZE) break;

      size_t merged_size = top.size();
      std::vector<Bucket> merged_buckets;
      merged_buckets.emplace_back(top);
      pq.pop();

      while (!pq.empty() && merged_size < MIN_CLUSTER_SIZE &&
             merged_size + pq.top().size() <= MAX_MERGED_CLUSTER_SIZE) {
        merged_size += pq.top().size();
        merged_buckets.emplace_back(pq.top());
        pq.pop();
      }

      if (merged_buckets.size() == 1) {
        CHECK(merged_buckets[0].size() <= MAX_CLUSTER_SIZE);
        if (merged_buckets[0].size() > MAX_CLUSTER_SIZE) {
          std::cout << "Pushing a cluster that is too large: "
                    << merged_buckets[0].size() << std::endl;
        }
        finished_buckets.emplace_back(std::move(merged_buckets[0]));
        break;
      }

      CHECK(merged_size > 0);
      auto new_bucket =
          parlay::sequence<uint32_t>::uninitialized(merged_size);
      size_t pos = 0;
      for (auto& b : merged_buckets) {
        std::memcpy(new_bucket.begin() + pos, b.begin(),
                    b.size() * sizeof(uint32_t));
        pos += b.size();
      }
      new_bucket = parlay::remove_duplicates(new_bucket);
      CHECK(new_bucket.size() > 0);

      if (new_bucket.size() >= MIN_CLUSTER_SIZE &&
          new_bucket.size() <= MAX_CLUSTER_SIZE) {
        finished_buckets.push_back(std::move(new_bucket));
      } else {
        pq.push(std::move(new_bucket));
      }
    }

    while (!pq.empty()) {
      remaining_clusters.emplace_back(pq.top());
      pq.pop();
    }
  }

  // Base-case handler for duplicates / near-duplicates. When recursion depth
  // is too deep or shrinkage ratio is too small, randomly shuffle and split
  // the bucket into MAX_CLUSTER_SIZE-sized pieces.
  void SplitDuplicates(
      Bucket& bucket, size_t seed, int depth, size_t parent_size,
      std::vector<Bucket>& output_buckets) {
    auto ids_copy = std::move(bucket);
    std::mt19937 prng(seed + depth + parent_size);
    std::shuffle(ids_copy.begin(), ids_copy.end(), prng);

    size_t full_blocks = ids_copy.size() / MAX_CLUSTER_SIZE;
    size_t remainder = ids_copy.size() - full_blocks * MAX_CLUSTER_SIZE;

    if (full_blocks > 0 && remainder < MIN_CLUSTER_SIZE) {
      full_blocks--;
      if (full_blocks > 0) {
        for (size_t k = 0; k < full_blocks; ++k) {
          auto& new_bucket = output_buckets.emplace_back();
          size_t start = MAX_CLUSTER_SIZE * k;
          size_t end = std::min(start + MAX_CLUSTER_SIZE, ids_copy.size());
          for (size_t j = start; j < end; ++j) new_bucket.push_back(ids_copy[j]);
          CHECK(new_bucket.size() <= MAX_CLUSTER_SIZE);
        }
      }
      size_t start = full_blocks * MAX_CLUSTER_SIZE;
      size_t end = ids_copy.size();
      size_t block_size = (end - start) / 2;
      if (block_size < MIN_CLUSTER_SIZE) {
        std::cout << "Violated expectation." << std::endl;
        exit(-1);
      }
      auto& new_bucket = output_buckets.emplace_back();
      for (size_t j = start; j < start + block_size; ++j)
        new_bucket.push_back(ids_copy[j]);
      CHECK(new_bucket.size() <= MAX_CLUSTER_SIZE);
      auto& next_bucket = output_buckets.emplace_back();
      for (size_t j = start + block_size; j < end; ++j)
        next_bucket.push_back(ids_copy[j]);
      CHECK(next_bucket.size() <= MAX_CLUSTER_SIZE);
    } else {
      for (size_t i = 0; i < ids_copy.size(); i += MAX_CLUSTER_SIZE) {
        auto& new_bucket = output_buckets.emplace_back();
        size_t start = i;
        size_t end = std::min(start + MAX_CLUSTER_SIZE, ids_copy.size());
        for (size_t j = start; j < end; ++j) new_bucket.push_back(ids_copy[j]);
      }
    }
  }

  // ===== Main sketch functions =====

  // Returns a collection of leaf buckets (iterative / BFS style).
  std::vector<Bucket> LevelByLevelSketch(
      GraphH &G,
      PR &Points, std::vector<Bucket> initial_buckets, long cluster_size,
      int initial_fanout, size_t seed, int fanout_levels,
      std::vector<int> &fanout_scheme, size_t fixed_leaders) {
    std::vector<Bucket> active_buckets = std::move(initial_buckets);
    std::vector<Bucket> finished_buckets;
    int depth = 0;

    while (!active_buckets.empty()) {
      std::vector<Bucket> to_process;
      for (auto& b : active_buckets) {
        if (b.size() <= (size_t)cluster_size) {
          finished_buckets.push_back(std::move(b));
        } else {
          to_process.push_back(std::move(b));
        }
      }
      active_buckets.clear();
      if (to_process.empty()) break;

      parlay::sequence<std::vector<Bucket>> next_level_results(to_process.size());

      parlay::parallel_for(0, to_process.size(), [&](size_t i) {
        Bucket& ids = to_process[i];
        std::vector<Bucket>& result_buckets = next_level_results[i];

        size_t current_seed = seed + depth * 1337 + i * 7;
        int effective_fanout = (depth >= fanout_levels) ? 1 : initial_fanout;

        parlay::sequence<Bucket> clusters = SelectAndAssignLeaders(
            Points, ids, depth, effective_fanout, current_seed,
            fanout_levels, fanout_scheme, fixed_leaders);

        std::vector<Bucket> merged_finished;
        parlay::sequence<Bucket> remaining;
        MergeBuckets(clusters, merged_finished, remaining);

        // Classify each output bucket.
        for (auto& b : merged_finished) {
          result_buckets.push_back(std::move(b));
        }
        for (auto& b : remaining) {
          if (depth > MAX_DEPTH ||
              (depth > CONCERNING_DEPTH &&
               b.size() > TOO_SMALL_SHRINKAGE_FRACTION * ids.size())) {
            SplitDuplicates(b, seed, depth, ids.size(), result_buckets);
          } else {
            result_buckets.push_back(std::move(b));
          }
        }
      });

      // Flatten results into active_buckets for the next level.
      for (size_t i = 0; i < next_level_results.size(); ++i) {
        for (auto& b : next_level_results[i]) {
          active_buckets.push_back(std::move(b));
        }
      }

      std::cout << "Processed level " << depth << std::endl;
      depth++;
      size_t sum_size = 0;
      size_t max_size = 0;
      size_t min_size = active_buckets.empty()
                            ? 0
                            : std::numeric_limits<size_t>::max();
      for (const auto& b : active_buckets) {
        sum_size += b.size();
        if (b.size() > max_size) max_size = b.size();
        if (b.size() < min_size) min_size = b.size();
      }
      std::cout << "Level " << depth
                << " active clusters: " << active_buckets.size()
                << " sum: " << sum_size << " max: " << max_size
                << " min: " << min_size << " avg: "
                << (active_buckets.empty()
                        ? 0
                        : (double)sum_size / active_buckets.size())
                << std::endl;

      if (depth > 100) break;
    }
    for (auto& b : active_buckets)
      finished_buckets.push_back(std::move(b));

    return finished_buckets;
  }

  // Returns a collection of leaf buckets (recursive / DFS style).
  std::vector<Bucket> RecursivelySketch(
      GraphH &G,
      PR &Points, Bucket &ids, long cluster_size, int depth, int fanout,
      size_t seed, int fanout_levels, std::vector<int> &fanout_scheme,
      size_t fixed_leaders) {
    if (ids.size() <= (size_t)cluster_size) {
      return {ids};
    }

    size_t next_seed = parlay::hash64(seed);

    parlay::sequence<Bucket> clusters = SelectAndAssignLeaders(
        Points, ids, depth, fanout, seed, fanout_levels, fanout_scheme,
        fixed_leaders);

    // Separate into finished buckets and clusters needing further recursion.
    std::vector<Bucket> buckets;
    parlay::sequence<Bucket> remaining;
    MergeBuckets(clusters, buckets, remaining);

    // Recurse on remaining clusters.
    parlay::sequence<std::vector<Bucket>> rec_buckets(remaining.size());
    parlay::parallel_for(
        0, remaining.size(),
        [&](size_t cluster_id) {
          std::vector<Bucket> recursive_buckets;
          if (depth > MAX_DEPTH ||
              (depth > CONCERNING_DEPTH &&
               remaining[cluster_id].size() >
                   TOO_SMALL_SHRINKAGE_FRACTION * ids.size())) {
            SplitDuplicates(remaining[cluster_id], seed, depth, ids.size(),
                            recursive_buckets);
          } else {
            auto local_fanout = (depth < fanout_levels) ? fanout : 1;
            recursive_buckets = RecursivelySketch(
                G, Points, remaining[cluster_id], cluster_size, depth + 1,
                /*fanout=*/local_fanout, next_seed + cluster_id, fanout_levels,
                fanout_scheme, fixed_leaders);
          }
          rec_buckets[cluster_id] = std::move(recursive_buckets);
        },
        1);

    for (size_t cluster_id = 0; cluster_id < remaining.size(); ++cluster_id) {
      while (!rec_buckets[cluster_id].empty()) {
        size_t index = rec_buckets[cluster_id].size();
        buckets.push_back(std::move(rec_buckets[cluster_id][index - 1]));
        rec_buckets[cluster_id].pop_back();
      }
    }

    return buckets;
  }

  auto recursively_sketch_wrapper(GraphH &G, PR &Points, size_t cluster_size) {
    // TODO: this is non-deterministic! wtf.
    // https://en.cppreference.com/w/cpp/numeric/random/random_device.html
    std::random_device rd;
    std::mt19937 rng(rd());
    std::uniform_int_distribution<int> uni(0, Points.size());
    parlay::random rnd(uni(rng));
    auto ids = parlay::tabulate(Points.size(), [&](uint32_t i) { return i; });
    parlay::internal::timer t;

    int fanout_per = FANOUT_PER_LEVEL;
    int fanout_levels = 0;
    auto local_fanout = FANOUT;
    std::cout << "FANOUT = " << FANOUT
              << " FANOUT_PER_LEVEL = " << FANOUT_PER_LEVEL << std::endl;

    if (fanout_per != 0) {
      // identify the number of levels to fanout at the per_level_fanout without
      // exceeding fanout. we are using a constant rate of fanout, which may not
      // be ideal. For power users, we may want to allow custom fanout
      // distributions. there may also be some way of dynamically adjusting the
      // fanout within the RecursivelySketch method based on distributional
      // properties of the data.
      local_fanout = fanout_per;
      int fprod = fanout_per;
      while (fprod * fanout_per <= FANOUT) {
        fprod *= fanout_per;
        fanout_levels++;
      }
    }
    std::cout << "number of levels to fanout: " << fanout_levels + 1
              << std::endl;
    std::cout << "fanout per level: " << local_fanout << std::endl;
    std::cout << "total fanout: " << std::pow(local_fanout, (fanout_levels + 1))
              << std::endl;
    std::cout << "total fanout allowance: " << FANOUT << std::endl;
    std::cout << "leader method: random" << std::endl;

    t.start();

    if (FIXED_NUM_LEADERS != 0) {
      std::cout << "Using fixed number of leaders: " << FIXED_NUM_LEADERS
                << std::endl;
    }

    std::vector<Bucket> buckets;
    if (LEVEL_BY_LEVEL) {
        std::vector<Bucket> initial_buckets;
        initial_buckets.push_back(std::move(ids));
        std::cout << "Calling LevelByLevelSketch" << std::endl;
        buckets = LevelByLevelSketch(
            G, Points, initial_buckets, cluster_size, local_fanout, SEED, fanout_levels,
            FANOUT_SCHEME, FIXED_NUM_LEADERS);
    } else {
        buckets = RecursivelySketch(
            G, Points, ids, cluster_size, 0, local_fanout, SEED, fanout_levels,
            FANOUT_SCHEME, FIXED_NUM_LEADERS);
    }

    SEED = parlay::hash64(SEED);
    t.next("buckets time");
    //get sizeof buckets in bytes
    size_t total_bytes = 0;
    size_t total_points = 0;
    for (size_t i = 0; i < buckets.size(); i++) {
      total_bytes += sizeof(buckets[i]);
      total_bytes += buckets[i].size() * sizeof(uint32_t);
      total_points += buckets[i].size();
    }
    std::cout << "buckets size (bytes): " << total_bytes << std::endl;
    std::cout << "Total buckets: " << buckets.size() << std::endl;
    std::cout << "Total points: " << total_points << std::endl;

    std::cout << "Computed buckets!" << std::endl;

    //G.allocate_graph(Points.size());
    // Build on each bucket. // note the hack of checking size. This is a hack
    // to get around the RecursivelySketch routine producing empty clusters...
    // Looking into it.
    std::cout << "Building leaves:" << std::endl;
     parlay::parallel_for(0, buckets.size(), [&](size_t i) {
       CHECK(buckets[i].size() <= MAX_CLUSTER_SIZE);
       if (buckets[i].size() > 1) RunLeaf(G, Points, buckets[i]);
       // Note we can still have some small clusters due to how sampling works.
     });
    t.next("build leaf time");
  }

  void multiple_clustertrees(GraphH &G, PR &Points, long cluster_size,
                             long num_clusters) {
    G.allocate_graph(Points.size());
    for (auto i = 0; i < num_clusters; i++) {
      recursively_sketch_wrapper(G, Points, cluster_size);
      // R85_B1_SNAPSHOT_BEGIN -- observation only, after finished round.
      // The original BUILD graph and its candidate order are not modified.
      if (const char* b1_dir = std::getenv("R85_B1_SNAPSHOT_DIR")) {
        if (!*b1_dir) throw std::runtime_error("R85_B1_EMPTY_SNAPSHOT_DIR");
        const std::string b1_path = std::string(b1_dir) + "/pass" +
                                    std::to_string(i + 1) + ".tsv";
        {
          std::ifstream exists(b1_path);
          if (exists.good()) throw std::runtime_error("R85_B1_REFUSE_OVERWRITE " + b1_path);
        }
        std::ofstream b1_out(b1_path, std::ios::out | std::ios::trunc);
        if (!b1_out.good()) throw std::runtime_error("R85_B1_CANNOT_WRITE " + b1_path);
        uint64_t b1_total_candidates = 0;
        uint64_t b1_nonempty_rows = 0;
        for (size_t b1_row = 0; b1_row < G.size(); ++b1_row) {
          const size_t b1_degree = static_cast<size_t>(G.degree(b1_row));
          if (b1_degree > G.kMaxDegree) throw std::runtime_error("R85_B1_INVALID_DEGREE");
          const size_t b1_worst_index = G.get_furthest_index(b1_row);
          if (b1_degree != 0 && b1_worst_index >= b1_degree)
            throw std::runtime_error("R85_B1_INVALID_WORST_INDEX");
          float b1_worst_float = static_cast<float>(G.get_furthest(b1_row));
          uint32_t b1_worst_bits = 0;
          std::memcpy(&b1_worst_bits, &b1_worst_float, sizeof(b1_worst_bits));
          std::vector<std::tuple<uint64_t,uint16_t,uint32_t>> b1_entries;
          for (const auto& b1_c : G.Neighbors(b1_row)) {
            float b1_float = static_cast<float>(b1_c.norm);
            uint32_t b1_bits = 0;
            static_assert(sizeof(b1_float) == sizeof(b1_bits), "float must be 32 bits");
            std::memcpy(&b1_bits, &b1_float, sizeof(b1_bits));
            b1_entries.emplace_back(static_cast<uint64_t>(b1_c.point_id),
                                    static_cast<uint16_t>(b1_c.hash), b1_bits);
          }
          if (b1_entries.size() != b1_degree)
            throw std::runtime_error("R85_B1_DEGREE_MISMATCH");
          // Preserve live candidate order: lower_bound and worst_index use it.
          // All values are explicit; no padding, locks, unused slots or pointers.
          b1_total_candidates += b1_entries.size();
          b1_nonempty_rows += !b1_entries.empty();
          b1_out << b1_row << '\t' << b1_entries.size()
                 << '\t' << b1_worst_index << '\t' << b1_worst_bits;
          for (const auto& b1_c : b1_entries) {
            b1_out << '\t' << std::get<0>(b1_c) << ','
                   << std::get<1>(b1_c) << ',' << std::get<2>(b1_c);
          }
          b1_out << '\n';
        }
        b1_out.flush();
        if (!b1_out.good()) throw std::runtime_error("R85_B1_WRITE_ERROR " + b1_path);
        b1_out.close();
        std::cout << "R85_B1_SNAPSHOT_PASS round=" << (i + 1)
                  << " nodes=" << G.size()
                  << " nonempty=" << b1_nonempty_rows
                  << " candidates=" << b1_total_candidates
                  << " file=" << b1_path << std::endl;
      }
      // R85_B1_SNAPSHOT_END
      std::cout << "Built cluster " << i << " of " << num_clusters << std::endl;
      std::cout << "Leaf count: " << leaf_count << std::endl;
      std::cout << "# of comparisons during clustering: " << COMPARISONS
                << std::endl;
    }
  }

  /*  Leaf code  */
  void RunLeaf(GraphH &G, PR &Points,
               parlay::sequence<uint32_t> &active_indices) {
    leaf_count++;
    EigenKNN(G, Points, active_indices);
  }

  void EigenKNN(GraphH &G, PR &Points,
                     parlay::sequence<uint32_t> &active_indices) {
    eigen_knn(G, active_indices, Points, MST_DEG);
  }

  size_t SEED = 555;
  double FRACTION_LEADERS = 0.005;
  size_t TOP_LEVEL_NUM_LEADERS = 950;
  size_t MAX_NUM_LEADERS = 512;
  size_t MAX_CLUSTER_SIZE = 5000;
  size_t MIN_CLUSTER_SIZE = 1;
  size_t MAX_MERGED_CLUSTER_SIZE = 2500;
  size_t FIXED_NUM_LEADERS = 0; //0 means use fraction
  int MAX_DEPTH = 3; // 8
  int CONCERNING_DEPTH = 2;  // 6
  double TOO_SMALL_SHRINKAGE_FRACTION = 0.8;
  size_t MST_DEG = 3;
  int FANOUT = 1;
  int FANOUT_PER_LEVEL = 1;
  bool LEVEL_BY_LEVEL = false;
  bool NO_MERGE = false;
  double ALPHA = 1;

  std::vector<int> FANOUT_SCHEME = {};
  std::atomic<size_t> COMPARISONS = 0;
};


template <typename Point, typename PointRange, typename indexType>
struct pipnn_index {
  using GraphI = Graph<indexType>;
  using PR = PointRange;

  using utils = cluster_utils<Point, PointRange, indexType>;

  pipnn_index() {}

  template <typename GraphH>
  void ExportToGraph(GraphH& graph, commandLine& P, GraphI G, PR& Points, bool prune_all, size_t prune_degree, double alpha) {
    parlay::internal::timer t;
    t.start();

    auto degree_seq = parlay::delayed_tabulate(Points.size(), [&] (size_t i) -> size_t {
      return graph.degree(i);
    });
    std::cout << "Average table size: " << (parlay::reduce(degree_seq) / Points.size()) << std::endl;

    graph.finalize();

    //create LSH table
    //auto H = SimHash<Point, PR, indexType>(12, Points.dimension());

    parlay::parallel_for(0, Points.size(), [&](size_t i) {
      if (prune_all || graph.degree(i) > prune_degree) {
        utils::robustPrune(graph.Neighbors(i), i, Points, G, alpha, prune_degree);

      } else {
        for (auto ngh : graph.Neighbors(i)) {
          G[i].append_neighbor(ngh.point_id);
        }
      }
			// G[i].random_permute();
    });
    t.next("Final prune time");
  }

  void build_index(GraphI &G, commandLine& P, PR &Points, long cluster_rounds,
                   long cluster_size, long MSTDeg, bool prune,
                   bool prune_all, double alpha,
                   long prune_degree,
                   long top_level_leaders, int fanout,
                   int fanout_per_level, double fraction_leaders,
                   std::string fanout_scheme, int Hsize, long table_size,
                   bool no_reservoir, size_t fixed_num_leaders) {
    if (no_reservoir) {
        HashSetGraph<indexType> hash_set_graph;
        build_index_impl(G, P, Points, cluster_rounds, cluster_size, MSTDeg, prune, prune_all, alpha, prune_degree, top_level_leaders, fanout, fanout_per_level, fraction_leaders, fanout_scheme, Hsize, table_size, hash_set_graph, fixed_num_leaders);
    } else {
        parlay::internal::timer ht;
        ht.start();
        if (Hsize > 16) {
        std::cout << "Warning: at most 16 bits are supported for the hash size. "
                    << "Using 16 bits instead of " << Hsize << std::endl;
        Hsize = 16;
        }
        SketchHash<Point, PointRange, indexType> H(Hsize, Points.dimension(),Points);
        ht.next("SketchHash construction time");
        ht.stop();
        //get size of H in bytes
        size_t h_size = H.get_total_size_in_bytes();
        std::cout << "Size of SketchHash (bytes): " << h_size << std::endl;

        // R70_COMPILE_TIME_RESERVOIR_SELECTION: keep all caller arguments and logical C unchanged.
#ifdef R70_TWO_TIER
        using R70GraphStorage = TwoTierLSHGraph<indexType, float, SketchHash<Point, PointRange, indexType>>;
        std::cout << "R70_RESERVOIR_VARIANT=TIER_B64_C" << table_size << std::endl;
#else
        using R70GraphStorage = LSHGraph<indexType, float, SketchHash<Point, PointRange, indexType>>;
        std::cout << "R70_RESERVOIR_VARIANT=STOCK_FLAT_C" << table_size << std::endl;
#endif
        // R71_H17_PACKED_TOP2_ISOLATED: emit once per BUILD for binary provenance.
#ifdef R71_H17_TOP2
        std::cout << "R71_SELECTION_VARIANT=H17_PACKED_TOP2" << std::endl;
#else
        std::cout << "R71_SELECTION_VARIANT=STOCK_HIGHWAY" << std::endl;
#endif
        R70GraphStorage lsh_graph(Points.size(), (size_t)table_size, H, /*allocate=*/false);
        build_index_impl(G, P, Points, cluster_rounds, cluster_size, MSTDeg, prune, prune_all, alpha, prune_degree, top_level_leaders, fanout, fanout_per_level, fraction_leaders, fanout_scheme, Hsize, table_size, lsh_graph, fixed_num_leaders);
    }
  }

  template<typename GraphH>
  void build_index_impl(GraphI &G, commandLine& P, PR &Points, long cluster_rounds,
                   long cluster_size, long MSTDeg, bool prune,
                   bool prune_all, double alpha,
                   long prune_degree,
                   long top_level_leaders, int fanout,
                   int fanout_per_level, double fraction_leaders,
                   std::string fanout_scheme, int Hsize, long table_size,
                   GraphH& graph_h, size_t fixed_num_leaders) {
    cluster<GraphH, Point, PointRange, indexType> C;
    C.MST_DEG = MSTDeg;
    C.ALPHA = alpha;
    C.MAX_CLUSTER_SIZE = cluster_size;
    C.MAX_MERGED_CLUSTER_SIZE = cluster_size;
    C.MIN_CLUSTER_SIZE = cluster_size / 10;
    C.TOP_LEVEL_NUM_LEADERS = top_level_leaders;
    std::cout << "Set MSTDeg to: " << MSTDeg
              << " fanout: " << fanout
              << std::endl;
    C.FANOUT = fanout;
    C.FANOUT_PER_LEVEL = fanout_per_level;
    C.FRACTION_LEADERS = fraction_leaders;
    C.FIXED_NUM_LEADERS = fixed_num_leaders;
    C.LEVEL_BY_LEVEL = P.getOption("-levelbylevel");
    C.NO_MERGE = P.getOption("-nomerge");
    std::cout << "Sizeof indexType = " << sizeof(indexType) << std::endl;

    // parse fanout_scheme which will be something like "10,5,2,1" into a vector
    // of ints
    if (fanout_scheme != "") {
      std::stringstream ss(fanout_scheme);
      std::string token;
      while (std::getline(ss, token, ',')) {
        C.FANOUT_SCHEME.push_back(std::stoi(token));
      }
    }
    std::cout << "Fanout scheme: ";
    for (size_t i = 0; i < C.FANOUT_SCHEME.size(); i++) {
      std::cout << C.FANOUT_SCHEME[i] << " ";
    }
    std::cout << std::endl;

    C.multiple_clustertrees(graph_h, Points, cluster_size, cluster_rounds);

    // Export the edges from the hashgraph into G.
    std::cout << "Allocating graph, prune_degree = " << prune_degree << std::endl;
    G.allocate_graph(prune_degree, Points.size());
    assert(G.max_degree() == prune_degree);
    ExportToGraph(graph_h, P, G, Points, prune_all, prune_degree, alpha);
    std::cout << "Average distance traversed: " << (dist_traversed.load() / Points.size()) << std::endl;
  }
};

}  // namespace parlayANN
