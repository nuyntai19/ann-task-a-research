// R80.3: force full compiled BUILD / Final Prune with R80 move heap;
// no main, no execution, no binary, no ANN graph BUILD.
#include <cstdint>
#include <string>
#include "utils/euclidian_point.h"
#include "utils/point_range.h"
#include "PipNN/pipnn.h"

namespace r80_buildpath_gate {
using Id = std::uint32_t;
using Point = parlayANN::Euclidian_Point<float>;
using PR = parlayANN::PointRange<Point>;
using Hash = ::SketchHash<Point,PR,Id>;
using Tier = parlayANN::TwoTierLSHGraph<Id,float,Hash>;

void force_h17_tier_move_heap_build_path(parlayANN::Graph<Id>& out,
                                         ::commandLine& cli,
                                         PR& points,
                                         Tier& reservoir) {
  parlayANN::pipnn_index<Point,PR,Id> index;
  index.build_index_impl(
      out, cli, points,
      2L, 1024L, 2L,
      true, true, 1.1,
      64L, 100L, 1, 0, 0.005,
      std::string("10,3,1"), 12, 160L,
      reservoir, 0UL);
}
}
