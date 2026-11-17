// R78.1 -- compile-only instantiation. NO main, NO execution, NO graph BUILD.
#include <cstdint>
#include <string>
#include "utils/euclidian_point.h"
#include "utils/point_range.h"
#include "PipNN/pipnn.h"
#include "r78_segmented_lshgraph.h"

namespace r78_compile_gate {
using Id = std::uint32_t;
using Point = parlayANN::Euclidian_Point<float>;
using PR = parlayANN::PointRange<Point>;
using Hash = ::SketchHash<Point, PR, Id>;
using S1 = parlayANN::R78SegmentedLSHGraph<Id, float, Hash>;

// This is an ordinary (non-template) function. Its body forces the compiler
// to instantiate the real PiPNN BUILD leaf / Final Prune path with S1's
// segmented NeighborView. It is never called or linked.
void force_build_path_template_check(parlayANN::Graph<Id>& output,
                                     ::commandLine& cli,
                                     PR& points,
                                     S1& candidates) {
  parlayANN::pipnn_index<Point, PR, Id> index;
  index.build_index_impl(
      output, cli, points,
      2L, 1024L, 2L,
      true, true, 1.1,
      64L, 100L, 1, 0, 0.005,
      std::string("10,3,1"), 12, 160L,
      candidates, 0UL);
}
}  // namespace r78_compile_gate
