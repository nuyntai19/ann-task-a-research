

/*
  Example usage:
    ./compute_groundtruth -base_path ~/data/sift/sift-1M
    -query_path ~/data/sift/query-10K -data_type uint8
    -dist_func Euclidian -k 100 -gt_path ~/data/sift/GT/sift-1M.gt
*/

#include <iostream>
#include <algorithm>
#include <cstdint>
#include <vector>
#include <queue>
#include "parlay/parallel.h"
#include "parlay/primitives.h"
#include "parlay/io.h"
#include "parlay/internal/get_time.h"
#include "utils/euclidian_point.h"
#include "utils/mips_point.h"
#include "utils/point_range.h"
#include "../algorithms/bench/parse_command_line.h"
#include <Eigen/Dense>

using pid = std::pair<int, float>;
using pid_flip = std::pair<float, int>;
using namespace parlayANN;

template<typename PointRange>
parlay::sequence<parlay::sequence<pid>> compute_groundtruth(PointRange &B,
  PointRange &Q, int k){
    parlay::internal::timer t;
    t.start();

    using T = typename PointRange::Point::T;
    using Point = typename PointRange::Point;

    size_t q_size = Q.size();
    size_t b_size = B.size();
    unsigned d = B.dimension();
    const size_t B_batch_size = 512;

    int num_threads = parlay::num_workers();
    size_t chunk_size = (b_size + num_threads - 1) / num_threads;

    auto thread_results = parlay::sequence<parlay::sequence<std::priority_queue<pid_flip>>>(num_threads);

    // Pre-materialize queries into an Eigen matrix
    Eigen::Matrix<float, Eigen::Dynamic, Eigen::Dynamic, Eigen::RowMajor> Q_mat(q_size, d);
    for (size_t i = 0; i < q_size; ++i) {
        T* coords = (T*)Q.location(i);
        for (unsigned j = 0; j < d; ++j) {
            Q_mat(i, j) = static_cast<float>(coords[j]);
        }
    }
    Eigen::Matrix<float, Eigen::Dynamic, 1> Q_sq_norms;
    if (Point::is_metric()) {
        Q_sq_norms = Q_mat.rowwise().squaredNorm();
    }

    parlay::parallel_for(0, num_threads, [&](int thread_id) {
        size_t start_idx = thread_id * chunk_size;
        size_t end_idx = std::min(start_idx + chunk_size, b_size);

        thread_results[thread_id] = parlay::sequence<std::priority_queue<pid_flip>>(q_size);

        for (size_t j = start_idx; j < end_idx; j += B_batch_size) {
            size_t current_batch_end = std::min(j + B_batch_size, end_idx);
            size_t current_batch_size = current_batch_end - j;

            if (current_batch_size == 0) continue;

            Eigen::Matrix<float, Eigen::Dynamic, Eigen::Dynamic, Eigen::RowMajor> B_chunk_mat(current_batch_size, d);
            for (size_t i = 0; i < current_batch_size; ++i) {
                T* coords = (T*)B.location(j + i);
                for (unsigned l = 0; l < d; ++l) {
                    B_chunk_mat(i, l) = static_cast<float>(coords[l]);
                }
            }

            Eigen::Matrix<float, Eigen::Dynamic, Eigen::Dynamic, Eigen::RowMajor> D(q_size, current_batch_size);

            if (Point::is_metric()) {
                Eigen::Matrix<float, Eigen::Dynamic, 1> B_chunk_sq_norms = B_chunk_mat.rowwise().squaredNorm();
                D.noalias() = -2 * Q_mat * B_chunk_mat.transpose();
                D.colwise() += Q_sq_norms;
                D.rowwise() += B_chunk_sq_norms.transpose();
            } else { // MIPS
                D.noalias() = -1 * Q_mat * B_chunk_mat.transpose();
            }

            for (size_t i = 0; i < q_size; ++i) {
                for (size_t batch_j = 0; batch_j < current_batch_size; ++batch_j) {
                    float dist = D(i, batch_j);
                    if (thread_results[thread_id][i].size() < (size_t)k) {
                        thread_results[thread_id][i].push({dist, (int)(j + batch_j)});
                    } else if (dist < thread_results[thread_id][i].top().first) {
                        thread_results[thread_id][i].pop();
                        thread_results[thread_id][i].push({dist, (int)(j + batch_j)});
                    }
                }
            }
        }
    }, 1);

    auto answers = parlay::tabulate(q_size, [&](size_t i) {
        std::priority_queue<pid_flip> final_top_k;
        for (int j = 0; j < num_threads; ++j) {
            if (thread_results[j].size() > i){
                 while(!thread_results[j][i].empty()){
                    pid_flip p = thread_results[j][i].top();
                    thread_results[j][i].pop();
                    if (final_top_k.size() < (size_t)k) {
                        final_top_k.push(p);
                    } else if (p.first < final_top_k.top().first) {
                        final_top_k.pop();
                        final_top_k.push(p);
                    }
                 }
            }
        }

        parlay::sequence<pid> result(final_top_k.size());
        size_t count = final_top_k.size();
        for(size_t l=0; l<count; l++){
            auto [pair_first, pair_second] = final_top_k.top();
            result[l] = {pair_second, pair_first};
            final_top_k.pop();
        }
        // noop?
        std::sort(result.begin(), result.end(), [&] (auto a, auto b) { return (a.second == b.second) ? (a.first < b.first) : a.second < b.second; });
        return result;
    });

    std::cout << "Done computing groundtruth in " << t.next_time() << " seconds" << std::endl;
    // for (size_t i=0; i < q_size; ++i) {
    //   std::cout << answers[i].size() << std::endl;
    //   for (size_t j=0; j < answers[i].size(); ++j) {
    //     std::cout << "i = " << i << " j = " << j << " dist = " << answers[i][j].first << " " << answers[i][j].second << std::endl;
    //   }
    // }
    return answers;
}


// ibin is the same as the binary groundtruth format used in the
// big-ann-benchmarks (see: https://big-ann-benchmarks.com/neurips21.html)
void write_ibin(parlay::sequence<parlay::sequence<pid>> &result, const std::string outFile, int k){
    std::cout << "Writing file with dimension " << result[0].size() << std::endl;
    std::cout << "File contains groundtruth for " << result.size() << " query points" << std::endl;

    auto less = [&] (pid a, pid b) {return a.second < b.second;};
    parlay::sequence<int> preamble = {static_cast<int>(result.size()), static_cast<int>(result[0].size())};
    size_t n = result.size();
    parlay::parallel_for(0, result.size(), [&] (size_t i){
      if(result[i].size() > (size_t)k) result[i].resize(k);
      parlay::sort_inplace(result[i], less);
    });
    auto ids = parlay::tabulate(result.size(), [&] (size_t i){
        parlay::sequence<int> data;
        for(int j=0; j<k; j++){
          if (j < result[i].size()) data.push_back(static_cast<int>(result[i][j].first));
          else data.push_back(-1); //padding
        }
        return data;
    });
    auto distances = parlay::tabulate(result.size(), [&] (size_t i){
        parlay::sequence<float> data;
        for(int j=0; j<k; j++){
          if (j < result[i].size()) data.push_back(static_cast<float>(result[i][j].second));
          else data.push_back(-1.0); //padding
        }
        return data;
    });
    parlay::sequence<int> flat_ids = parlay::flatten(ids);
    parlay::sequence<float> flat_dists = parlay::flatten(distances);

    auto pr = preamble.begin();
    auto id_data = flat_ids.begin();
    auto dist_data = flat_dists.begin();
    std::ofstream writer;
    writer.open(outFile, std::ios::binary | std::ios::out);
    writer.write((char *) pr, 2*sizeof(int));
    writer.write((char *) id_data, n * k * sizeof(int));
    writer.write((char *) dist_data, n * k * sizeof(float));
    writer.close();
}

int main(int argc, char* argv[]) {
  commandLine P(argc,argv,
  "[-base_path <b>] [-query_path <q>] "
      "[-data_type <d>] [-k <k> ] [-dist_func <d>] [-gt_path <outfile>]");

  char* gFile = P.getOptionValue("-gt_path");
  char* qFile = P.getOptionValue("-query_path");
  char* bFile = P.getOptionValue("-base_path");
  char* vectype = P.getOptionValue("-data_type");
  char* dfc = P.getOptionValue("-dist_func");
  int k = P.getOptionIntValue("-k", 100);

  std::string df = std::string(dfc);
  if(df != "Euclidian" && df != "mips"){
    std::cout << "Error: invalid distance type: specify Euclidian or mips" << std::endl;
    abort();
  }

  std::string tp = std::string(vectype);
  if((tp != "uint8") && (tp != "int8") && (tp != "float")){
    std::cout << "Error: data type not specified correctly, specify int8, uint8, or float" << std::endl;
    abort();
  }

  std::cout << "Computing the " << k << " nearest neighbors" << std::endl;

  parlay::sequence<parlay::sequence<pid>> answers;
  std::string base = std::string(bFile);
  std::string query = std::string(qFile);


  if(tp == "float"){
    std::cout << "Detected float coordinates" << std::endl;
    if(df == "Euclidian"){
      auto B = PointRange<Euclidian_Point<float>>(bFile);
      auto Q = PointRange<Euclidian_Point<float>>(qFile);
      answers = compute_groundtruth<PointRange<Euclidian_Point<float>>>(B, Q, k);
    } else if(df == "mips"){
      auto B = PointRange<Mips_Point<float>>(bFile);
      auto Q = PointRange<Mips_Point<float>>(qFile);
      answers = compute_groundtruth<PointRange<Mips_Point<float>>>(B, Q, k);
    }
  } else if(tp == "uint8"){
    std::cout << "Detected uint8 coordinates" << std::endl;
    if(df == "Euclidian"){
      auto B = PointRange<Euclidian_Point<uint8_t>>(bFile);
      auto Q = PointRange<Euclidian_Point<uint8_t>>(qFile);
      answers = compute_groundtruth<PointRange<Euclidian_Point<uint8_t>>>(B, Q, k);
    } else if(df == "mips"){
      auto B = PointRange<Mips_Point<uint8_t>>(bFile);
      auto Q = PointRange<Mips_Point<uint8_t>>(qFile);
      answers = compute_groundtruth<PointRange<Mips_Point<uint8_t>>>(B, Q, k);
    }
  } else if(tp == "int8"){
    std::cout << "Detected int8 coordinates" << std::endl;
    if(df == "Euclidian"){
      auto B = PointRange<Euclidian_Point<int8_t>>(bFile);
      auto Q = PointRange<Euclidian_Point<int8_t>>(qFile);
      answers = compute_groundtruth<PointRange<Euclidian_Point<int8_t>>>(B, Q, k);
    } else if(df == "mips"){
      auto B = PointRange<Mips_Point<int8_t>>(bFile);
      auto Q = PointRange<Mips_Point<int8_t>>(qFile);
      answers = compute_groundtruth<PointRange<Mips_Point<int8_t>>>(B, Q, k);
    }
  }
  write_ibin(answers, std::string(gFile), k);

  return 0;
}
