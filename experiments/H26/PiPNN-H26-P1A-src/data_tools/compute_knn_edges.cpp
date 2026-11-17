#include <algorithm>
#include <iostream>

#include "parlay/io.h"
#include "parlay/parallel.h"
#include "parlay/primitives.h"
#include "utils/euclidian_point.h"
#include "utils/mips_point.h"
#include "utils/point_range.h"
#include "../algorithms/bench/parse_command_line.h"

using namespace parlayANN;

using pid = std::pair<uint32_t, float>;

struct TopK {
  parlay::sequence<pid> topk;
  float topdist;
  uint32_t toppos;

  TopK(float topdist) : topdist(topdist) {}

  void insert(uint32_t id, float dist, uint32_t k, float d_min) {
    if (topk.size() < k) {
      if (dist > topdist) {
        topdist = dist;
        toppos = topk.size();
      }
      topk.push_back(std::make_pair(id, dist));
    } else if (dist < topdist) {
      float new_topdist = d_min;
      int new_toppos = 0;
      topk[toppos] = std::make_pair(id, dist);
      for (size_t l = 0; l < topk.size(); l++) {
        if (topk[l].second > new_topdist) {
          new_topdist = topk[l].second;
          new_toppos = (int)l;
        }
      }
      topdist = new_topdist;
      toppos = new_toppos;
    }
  }

  parlay::sequence<pid> extract() { return std::move(topk); }
};

template <typename PointRange>
parlay::sequence<std::pair<uint32_t, parlay::sequence<pid>>> compute_groundtruth(PointRange& B,
                                                            int k,
                                                            int sample_size) {
  unsigned d = B.dimension();
  size_t b = B.size();
  using T = typename PointRange::Point::T;
  size_t datapoint_size = d * sizeof(T);
  size_t query_block_size = 128;
  size_t cache_size_vecs = 1024 * 1024 / datapoint_size;
  size_t base_block_size = cache_size_vecs / query_block_size;
  std::cout << "base_block_size = " << base_block_size << std::endl;

  float d_min = B[0].d_min();
  size_t num_queries = sample_size;
  parlay::random r;
  parlay::sequence<uint32_t> pre_ids = parlay::tabulate(
      num_queries, [&](size_t i) { return (uint32_t)(r.ith_rand(i) % b); });
  auto ids = parlay::remove_duplicates(pre_ids);
  num_queries = ids.size();

  parlay::sequence<std::pair<uint32_t, parlay::sequence<pid>>> result(num_queries);

  size_t num_query_blocks =
      (num_queries + query_block_size - 1) / query_block_size;
  parlay::parallel_for(
      0, num_query_blocks,
      [&](size_t i) {
        size_t num_base_blocks =
            (B.size() + base_block_size - 1) / base_block_size;
        size_t query_start = i * query_block_size;
        size_t query_end = std::min((i + 1) * query_block_size, num_queries);
        size_t num_queries = query_end - query_start;
        parlay::sequence<TopK> topk(num_queries, TopK(d_min));

        for (size_t j = 0; j < num_base_blocks; ++j) {
          size_t base_start = j * base_block_size;
          size_t base_end = std::min((j + 1) * base_block_size, B.size());

          for (size_t q_i = query_start; q_i < query_end; ++q_i) {
            auto q_id = ids[q_i];
            for (size_t b_i = base_start; b_i < base_end; ++b_i) {
              if (q_id != b_i) {
                float dist = B[q_id].distance(B[b_i]);
                topk[q_i - query_start].insert(b_i, dist, k, d_min);
              }
            }
          }
        }

        for (size_t q_i = query_start; q_i < query_end; ++q_i) {
          auto q_id = ids[q_i];
          result[q_i] = std::make_pair(q_id, topk[q_i - query_start].extract());
        }
      },
      1);

  std::cout << "Done computing groundtruth" << std::endl;
  return result;
}

void write_sparse_ibin(parlay::sequence<std::pair<uint32_t, parlay::sequence<pid>>>& result,
                const std::string outFile, int k) {
  std::cout << "Writing file with dimension " << result[0].second.size() << std::endl;
  std::cout << "File contains groundtruth for " << result.size()
            << " data points" << std::endl;

  auto less = [&](pid a, pid b) { return a.second < b.second; };
  parlay::sequence<int> preamble = {static_cast<int>(result.size()),
                                    static_cast<int>(result[0].second.size())};
  size_t n = result.size();
  parlay::parallel_for(0, result.size(), [&](size_t i) {
    parlay::sort_inplace(result[i].second, less);
  });
  auto source_ids = parlay::tabulate(result.size(), [&] (size_t i) {
    return result[i].first;
  });
  auto ids = parlay::tabulate(result.size(), [&](size_t i) {
    parlay::sequence<int> data;
    for (int j = 0; j < k; j++) {
      data.push_back(static_cast<int>(result[i].second[j].first));
    }
    return data;
  });
  auto distances = parlay::tabulate(result.size(), [&](size_t i) {
    parlay::sequence<float> data;
    for (int j = 0; j < k; j++) {
      data.push_back(static_cast<float>(result[i].second[j].second));
    }
    return data;
  });
  parlay::sequence<int> flat_ids = parlay::flatten(ids);
  parlay::sequence<float> flat_dists = parlay::flatten(distances);

  auto pr = preamble.begin();
  auto sources = source_ids.begin();
  auto id_data = flat_ids.begin();
  auto dist_data = flat_dists.begin();
  std::ofstream writer;
  writer.open(outFile, std::ios::binary | std::ios::out);
  writer.write((char*)pr, 2 * sizeof(int));
  writer.write((char*)sources, n * sizeof(int));
  writer.write((char*)id_data, n * k * sizeof(int));
  writer.write((char*)dist_data, n * k * sizeof(float));
  writer.close();
}

int main(int argc, char* argv[]) {
  commandLine P(
      argc, argv,
      "[-base_path <b>] [-query_path <q>] "
      "[-data_type <d>] [-k <k> ] [-dist_func <d>] [-gt_path <outfile>]");

  char* gFile = P.getOptionValue("-gt_path");
  char* bFile = P.getOptionValue("-base_path");
  char* vectype = P.getOptionValue("-data_type");
  char* dfc = P.getOptionValue("-dist_func");
  int k = P.getOptionIntValue("-k", 100);
  int sample_size = P.getOptionIntValue("-sample_size", 1000);

  std::string df = std::string(dfc);
  if (df != "Euclidian" && df != "mips") {
    std::cout << "Error: invalid distance type: specify Euclidian or mips"
              << std::endl;
    abort();
  }

  std::string tp = std::string(vectype);
  if ((tp != "uint8") && (tp != "int8") && (tp != "float")) {
    std::cout << "Error: data type not specified correctly, specify int8, "
                 "uint8, or float"
              << std::endl;
    abort();
  }

  std::cout << "Computing the " << k << " nearest neighbors" << std::endl;

  int maxDeg = 0;

  parlay::sequence<std::pair<uint32_t, parlay::sequence<pid>>> answers;
  std::string base = std::string(bFile);

  if (tp == "float") {
    std::cout << "Detected float coordinates" << std::endl;
    if (df == "Euclidian") {
      PointRange<Euclidian_Point<float>> B =
          PointRange<Euclidian_Point<float>>(bFile);
      answers = compute_groundtruth<PointRange<Euclidian_Point<float>>>(
          B, k, sample_size);
    } else if (df == "mips") {
      PointRange<Mips_Point<float>> B =
          PointRange<Mips_Point<float>>(bFile);
      answers = compute_groundtruth<PointRange<Mips_Point<float>>>(
          B, k, sample_size);
    }
  } else if (tp == "uint8") {
    std::cout << "Detected uint8 coordinates" << std::endl;
    if (df == "Euclidian") {
      PointRange<Euclidian_Point<uint8_t>> B =
          PointRange<Euclidian_Point<uint8_t>>(bFile);
      answers =
          compute_groundtruth<PointRange<Euclidian_Point<uint8_t>>>(
              B, k, sample_size);
    } else if (df == "mips") {
      PointRange<Mips_Point<uint8_t>> B =
          PointRange<Mips_Point<uint8_t>>(bFile);
      answers = compute_groundtruth<PointRange<Mips_Point<uint8_t>>>(
          B, k, sample_size);
    }
  } else if (tp == "int8") {
    std::cout << "Detected int8 coordinates" << std::endl;
    if (df == "Euclidian") {
      PointRange<Euclidian_Point<int8_t>> B =
          PointRange<Euclidian_Point<int8_t>>(bFile);
      answers =
          compute_groundtruth<PointRange<Euclidian_Point<int8_t>>>(
              B, k, sample_size);
    } else if (df == "mips") {
      PointRange<Mips_Point<int8_t>> B =
          PointRange<Mips_Point<int8_t>>(bFile);
      answers = compute_groundtruth<PointRange<Mips_Point<int8_t>>>(
          B, k, sample_size);
    }
  }
  write_sparse_ibin(answers, std::string(gFile), k);
  return 0;
}


