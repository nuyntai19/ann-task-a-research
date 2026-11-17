// H32-R13: standalone diagnostic using pinned ParlayANN qsearchAll.
// It does not alter graph, base/query vectors, GT, original source, or original binary.
#include <algorithm>
#include <cstdint>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <set>
#include <stdexcept>
#include <string>
#include <vector>
#include "algorithms/utils/euclidian_point.h"
#include "algorithms/utils/point_range.h"
#include "algorithms/utils/beamSearch.h"

int main(int argc, char **argv) {
  if (argc != 6) {
    std::cerr << "Usage: diagnostic BASE.fbin QUERIES.fbin GRAPH.graph GT.ibin OUT.csv\n";
    return 2;
  }
  using namespace parlayANN;
  using Index = unsigned int;
  using PR = PointRange<Euclidian_Point<float>>;
  constexpr long k = 10, Q = 100;
  PR base(argv[1]);
  PR query(argv[2]);
  Graph<Index> graph(argv[3]);
  groundTruth<Index> gt(argv[4]);
  if (base.size() != 1000000 || query.size() != 10000 ||
      base.dimension() != 128 || query.dimension() != 128 ||
      graph.size() != base.size() || gt.size() != query.size() || gt.dimension() != 100) {
    std::cerr << "H32R13_FAIL_CLOSED: unsupported dataset shape\n";
    return 3;
  }
  stats<Index> queryStats(query.size());
  queryStats.clear();
  QueryParams qp(k, 0, static_cast<long>(graph.size()), graph.max_degree(), 10.0, .125);
  qp.beamSize = Q;
  // Match native Vamana call qsearchAll(Query,Query,Query,G,Base,Base,Base,Stats,0,QP,false).
  auto results = qsearchAll(query, query, query, graph, base, base, base, queryStats,
                            static_cast<Index>(0), qp, false);
  std::ofstream f(argv[5], std::ios::out | std::ios::trunc);
  if (!f) { std::cerr << "H32R13_FAIL_CLOSED: cannot write output\n"; return 4; }
  f << "query_index,id0,id1,id2,id3,id4,id5,id6,id7,id8,id9,strict_hits,tie_aware_hits\n";
  long long strict_hits = 0, tie_hits = 0;
  for (size_t i = 0; i < query.size(); ++i) {
    if (results[i].size() != k) { std::cerr << "H32R13_FAIL_CLOSED: wrong result length\n"; return 5; }
    std::set<Index> reported;
    f << i;
    for (size_t j = 0; j < k; ++j) {
      auto id = results[i][j];
      if (id >= base.size() || !reported.insert(id).second) {
        std::cerr << "H32R13_FAIL_CLOSED: invalid or duplicate result ID\n"; return 6;
      }
      f << ',' << id;
    }
    long local_strict = 0;
    for (long j = 0; j < k; ++j) if (reported.count(gt.coordinates(i,j))) ++local_strict;
    strict_hits += local_strict;
    // Copy the tie-aware evaluation rule of the pinned check_nn_recall.h.
    float cutoff = query[i].distance(base[gt.coordinates(i, k-1)]);
    long local_tie = local_strict;
    for (long j = k; j < gt.dimension(); ++j) {
      Index gtid = gt.coordinates(i,j);
      if (query[i].distance(base[gtid]) == cutoff && reported.count(gtid)) ++local_tie;
    }
    tie_hits += local_tie;
    f << ',' << local_strict << ',' << local_tie << '\n';
  }
  f.close();
  if (!f.good()) { std::cerr << "H32R13_FAIL_CLOSED: output write failure\n"; return 7; }
  std::cout << std::setprecision(12)
            << "H32R13_Q100_K10_ENTRY0_RANDOMFALSE\n"
            << "H32R13_STRICT_RECALL=" << static_cast<double>(strict_hits)/(k*query.size()) << "\n"
            << "H32R13_SOURCE_TIE_AWARE_RECALL=" << static_cast<double>(tie_hits)/(k*query.size()) << "\n"
            << "H32R13_PREDICTIONS=" << argv[5] << "\n";
  return 0;
}
