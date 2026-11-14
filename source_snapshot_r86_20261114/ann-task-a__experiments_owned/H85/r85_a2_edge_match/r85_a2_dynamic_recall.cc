// R70 SEARCH evaluator. Based on the pinned PiPNN checkRecall implementation.
// Loads previously saved graphs; NEVER builds a new ANN graph.
#include <cmath>
#include <cstdint>
#include <iomanip>
#include <iostream>
#include <stdexcept>
#include <sstream>
#include <string>
#include <vector>
#include <set>

#include "/home/tai/ann-task-a/experiments/H70/pipnn-clean-443a328/algorithms/utils/euclidian_point.h"
#include "/home/tai/ann-task-a/experiments/H70/pipnn-clean-443a328/algorithms/utils/point_range.h"
#include "/home/tai/ann-task-a/experiments/H70/pipnn-clean-443a328/algorithms/utils/check_nn_recall.h"

int main(int argc, char **argv) {
  if (argc != 6) {
    std::cerr << "Usage: r72_graph_recall GRAPH.fbin BASE.fbin QUERIES.fbin GT.ibin BEAMS_CSV\n";
    return 2;
  }
  try {
    using namespace parlayANN;
    using Point = Euclidian_Point<float>;
    using PR = PointRange<Point>;
    using indexType = uint32_t;

    std::vector<long> beams;
    std::set<long> seen;
    std::stringstream ss(argv[5]);
    std::string piece;
    while (std::getline(ss, piece, ',')) {
      if (piece.empty()) throw std::invalid_argument("Empty beam");
      size_t consumed = 0;
      long beam = std::stol(piece, &consumed, 10);
      if (consumed != piece.size() || beam < 10 || beam > 512 || !seen.insert(beam).second)
        throw std::invalid_argument("Invalid or duplicated beam");
      beams.push_back(beam);
    }
    if (beams.empty()) throw std::invalid_argument("No beams supplied");
    std::cout << "R85_A1C_DYNAMIC_BEAMS count=" << beams.size() << "\n";

    // These are native PiPNN readers and native PiPNN search/recall routines.
    PR base(argv[2]);
    PR queries(argv[3]);
    groundTruth<indexType> gt(argv[4]);
    Graph<indexType> graph(argv[1]);

    if (base.size() != 1000000 || base.dimension() != 128 ||
        queries.size() != 10000 || queries.dimension() != 128 ||
        gt.size() != queries.size() || gt.dimension() < 10 ||
        graph.size() != base.size() || (graph.max_degree() < 1 || graph.max_degree() > 64)) {
      std::cerr << "R72_RECALL_INPUT_MISMATCH\n";
      return 3;
    }
    std::cout << "R72_RECALL_INPUT_PASS graph_nodes=" << graph.size()
              << " queries=" << queries.size() << " gt_k=" << gt.dimension()
              << "\n";
    std::cout << std::fixed << std::setprecision(8);
    for (long beam : beams) {
      QueryParams qp(10L, beam, 1.35, static_cast<long>(graph.size()),
                     graph.max_degree());
      auto result = checkRecall<PR, PR, PR, indexType>(
          graph, base, queries, base, queries, base, queries, gt,
          /*random=*/false, /*start_point=*/0u, /*k=*/10L,
          qp, /*verbose=*/false);
      if (!std::isfinite(result.recall) || !std::isfinite(result.QPS)) {
        std::cerr << "R72_RECALL_NONFINITE beam=" << beam << "\n";
        return 4;
      }
      std::cout << "R72_RECALL_ROW beam=" << beam
                << " recall=" << result.recall
                << " qps=" << result.QPS
                << " avg_cmps=" << result.avg_cmps
                << " avg_visited=" << result.avg_visited
                << "\n";
    }
    std::cout << "R72_RECALL_EVAL_PASS\n";
    return 0;
  } catch (const std::exception &e) {
    std::cerr << "R72_RECALL_ERROR " << e.what() << "\n";
    return 5;
  }
}
