// R70 SEARCH evaluator. Based on the pinned PiPNN checkRecall implementation.
// Loads previously saved graphs; NEVER builds a new ANN graph.
#include <cmath>
#include <cstdint>
#include <iomanip>
#include <iostream>
#include <stdexcept>

#include "../utils/euclidian_point.h"
#include "../utils/point_range.h"
#include "../utils/check_nn_recall.h"

int main(int argc, char **argv) {
  if (argc != 5) {
    std::cerr << "Usage: r70_graph_recall GRAPH.fbin BASE.fbin QUERIES.fbin GT.ibin\n";
    return 2;
  }
  try {
    using namespace parlayANN;
    using Point = Euclidian_Point<float>;
    using PR = PointRange<Point>;
    using indexType = uint32_t;

    // These are native PiPNN readers and native PiPNN search/recall routines.
    PR base(argv[2]);
    PR queries(argv[3]);
    groundTruth<indexType> gt(argv[4]);
    Graph<indexType> graph(argv[1]);

    if (base.size() != 100000 || base.dimension() != 128 ||
        queries.size() != 300 || queries.dimension() != 128 ||
        gt.size() != queries.size() || gt.dimension() < 10 ||
        graph.size() != base.size() || graph.max_degree() != 64) {
      std::cerr << "R70_RECALL_INPUT_MISMATCH\n";
      return 3;
    }
    std::cout << "R70_RECALL_INPUT_PASS graph_nodes=" << graph.size()
              << " queries=" << queries.size() << " gt_k=" << gt.dimension()
              << "\n";
    std::cout << std::fixed << std::setprecision(8);
    for (long beam : {10L, 20L, 40L, 80L, 160L}) {
      QueryParams qp(10L, beam, 1.35, static_cast<long>(graph.size()),
                     graph.max_degree());
      auto result = checkRecall<PR, PR, PR, indexType>(
          graph, base, queries, base, queries, base, queries, gt,
          /*random=*/false, /*start_point=*/0u, /*k=*/10L,
          qp, /*verbose=*/false);
      if (!std::isfinite(result.recall) || !std::isfinite(result.QPS)) {
        std::cerr << "R70_RECALL_NONFINITE beam=" << beam << "\n";
        return 4;
      }
      std::cout << "R70_RECALL_ROW beam=" << beam
                << " recall=" << result.recall
                << " qps=" << result.QPS
                << " avg_cmps=" << result.avg_cmps
                << " avg_visited=" << result.avg_visited
                << "\n";
    }
    std::cout << "R70_RECALL_EVAL_PASS\n";
    return 0;
  } catch (const std::exception &e) {
    std::cerr << "R70_RECALL_ERROR " << e.what() << "\n";
    return 5;
  }
}
