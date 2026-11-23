#pragma once
#include <algorithm>
#include <cstdlib>
#include <limits>
#include <numeric>
#include <random>
#include <stdexcept>
#include <vector>

namespace rescue {
inline auto leaders(std::size_t n, unsigned seed, std::size_t count = 100) {
  std::vector<std::uint32_t> ids(n), root;
  std::iota(ids.begin(), ids.end(), 0);
  std::mt19937 prng(seed);
  std::sample(ids.begin(), ids.end(), std::back_inserter(root), count, prng);
  return root;
}
inline std::vector<std::uint32_t> routing_leaders;
inline void configure_routing(std::size_t n) {
  if (const char* count = std::getenv("RESCUE_ROUTE_COUNT")) {
    auto k = std::stoul(count);
    if (k != 32 && k != 100) throw std::runtime_error("Unsupported router size");
    const char* seed = std::getenv("RESCUE_ROUTE_SEED");
    if (!seed || n < 100) throw std::runtime_error("Missing router seed or too few points");
    routing_leaders = leaders(n, std::stoul(seed));
    // Uniformly spaced indices of the original root sample, fixed across queries.
    auto root = routing_leaders;
    routing_leaders.resize(k);
    for (std::size_t i = 0; i < k; ++i) routing_leaders[i] = root[i * root.size() / k];
  }
}

template<class Point, class Range>
std::uint32_t entry(Point q, const Range& points) {
  float best = std::numeric_limits<float>::infinity();
  std::uint32_t winner = 0;
  for (auto id : routing_leaders) {
    auto d = q.distance(points[id]);
    if (d < best) {
      best = d;
      winner = id;
    }
  }
  return winner;
}
}
