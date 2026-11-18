// Local adapter around the original native R86 reader and search evaluator.
// Unlike the archival R70/R72 executables, it accepts variable dataset sizes.
#include <cmath>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <stdexcept>
#include "utils/euclidian_point.h"
#include "utils/point_range.h"
#include "local_latency/check_nn_recall.h"

int main(int argc, char** argv) {
  if (argc != 5 && argc != 6) {
    std::cerr << "Usage: local_graph_recall GRAPH BASE.fbin QUERIES.fbin GT.ibin [LATENCY.csv]\n";
    return 2;
  }
  try {
    using namespace parlayANN;
    using PR = PointRange<Euclidian_Point<float>>;
    using Id = uint32_t;
    PR base(argv[2]), queries(argv[3]);
    groundTruth<Id> gt(argv[4]);
    Graph<Id> graph(argv[1]);
    if (base.size() < 100 || queries.size() == 0 ||
        base.dimension() != queries.dimension() || gt.size() != queries.size() ||
        gt.dimension() < 10 || graph.size() != base.size() || graph.max_degree() != 64) {
      throw std::runtime_error("Graph/base/query/GT shape mismatch");
    }
    const std::filesystem::path latency_path = argc == 6 ? argv[5] : "query_latency.csv";
    if (std::filesystem::exists(latency_path)) {
      throw std::runtime_error("Refusing to overwrite existing latency CSV");
    }
    std::ofstream latency_csv(latency_path);
    if (!latency_csv) throw std::runtime_error("Cannot create latency CSV");
    latency_csv << "beam,query_id,latency_us\n";
    std::cout << std::fixed << std::setprecision(8);
    for (long beam : {10L, 20L, 40L, 80L, 160L}) {
      QueryParams qp(10L, beam, 1.35, static_cast<long>(graph.size()), graph.max_degree());
      local_latency::begin(queries.size());
      auto result = checkRecall<PR, PR, PR, Id>(
          graph, base, queries, base, queries, base, queries, gt,
          false, 0u, 10L, qp, false);
      local_latency::write(latency_csv, beam);
      if (!std::isfinite(result.recall) || !std::isfinite(result.QPS)) {
        throw std::runtime_error("Nonfinite search result");
      }
      std::cout << "LOCAL_RECALL_ROW beam=" << beam << " recall=" << result.recall
                << " qps=" << result.QPS << " avg_cmps=" << result.avg_cmps << '\n';
    }
    latency_csv.flush();
    if (!latency_csv) throw std::runtime_error("Failed to flush latency CSV");
    std::cout << "LOCAL_LATENCY_CSV=" << latency_path.string() << '\n';
    std::cout << "LOCAL_RECALL_EVAL_PASS\n";
    return 0;
  } catch (const std::exception& error) {
    std::cerr << "LOCAL_RECALL_ERROR " << error.what() << '\n';
    return 1;
  }
}
