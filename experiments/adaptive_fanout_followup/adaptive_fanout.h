#pragma once
#include <algorithm>
#include <array>
#include <atomic>
#include <cmath>
#include <cstdint>
#include <cstdlib>
#include <fstream>
#include <iomanip>
#include <map>
#include <mutex>
#include <stdexcept>
#include <string>
#include <type_traits>
#include <unordered_map>
#include <utility>
#include <vector>

namespace af {
enum class Policy { fixed, v1, v2a, v2b, v3 };
struct Config {
  Policy policy = Policy::fixed;
  std::string mode = "fixed";
  bool calibrate = false;
  double margin = 0.0;
  double epsilon = 0.03;
  int min_depth = 1;
  unsigned min_fanout = 1;
  unsigned seed = 555;
  Config() {
    const char* mode = std::getenv("AF_MODE");
    this->mode = mode ? mode : "fixed";
    if (this->mode == "adaptive") policy = Policy::v1;
    else if (this->mode == "v2a") policy = Policy::v2a;
    else if (this->mode == "v2b") policy = Policy::v2b;
    else if (this->mode == "v3") policy = Policy::v3;
    else if (this->mode != "fixed") throw std::runtime_error("Invalid AF_MODE");
    calibrate = std::getenv("AF_CALIBRATE") != nullptr;
    if (const char* p = std::getenv("AF_MARGIN")) margin = std::stod(p);
    if (const char* p = std::getenv("AF_EPSILON")) epsilon = std::stod(p);
    if (const char* p = std::getenv("AF_MIN_DEPTH")) min_depth = std::stoi(p);
    if (const char* p = std::getenv("AF_MIN_FANOUT")) min_fanout = std::stoul(p);
    if (const char* p = std::getenv("AF_SEED")) seed = std::stoul(p);
    if (epsilon < 0 || epsilon > 10 || margin < 0 || min_depth < 0 || min_fanout < 1)
      throw std::runtime_error("Invalid adaptive fanout configuration");
  }
};
inline const Config& config() { static Config c; return c; }
inline bool eligible(int depth, std::size_t cap) {
  return config().policy != Policy::fixed && depth >= config().min_depth && cap > config().min_fanout;
}

// Distances are squared L2. epsilon is defined in ordinary L2 distance units.
inline std::size_t choose_count(const float* sorted_d2, std::size_t cap,
                                double epsilon, std::size_t floor) {
  if (!cap) return 0;
  floor = std::min(cap, std::max<std::size_t>(1, floor));
  const double factor = (1.0 + epsilon) * (1.0 + epsilon);
  const double threshold = std::max(0.0, double(sorted_d2[0])) * factor;
  const double tolerance = 1e-6 * std::max(1.0, threshold);
  std::size_t keep = floor;
  while (keep < cap && std::max(0.0, double(sorted_d2[keep])) <= threshold + tolerance) ++keep;
  return keep;
}

inline float margin_score(float d1_squared, float di_squared, float scale) {
  return (std::sqrt(std::max(0.0f, di_squared)) -
          std::sqrt(std::max(0.0f, d1_squared))) / scale;
}

struct DensitySample {
  float radius = 0;
  std::uint64_t distance_pairs = 0;
};

template <class PR, class Bucket>
DensitySample sample_density(PR& points, const Bucket& ids) {
  constexpr std::size_t refs_cap = 1024, anchors = 32, k = 8;
  const std::size_t refs = std::min(refs_cap, ids.size());
  if (refs <= k) return {};
  // Deterministic stratified samples. Midpoints for anchors, left endpoints
  // for references. Skip self by global ID even if the samples intersect.
  std::vector<float> radii;
  std::vector<float> distances;
  radii.reserve(anchors);
  distances.reserve(refs);
  DensitySample result;
  for (std::size_t a = 0; a < anchors; ++a) {
    const auto id = ids[(2 * a + 1) * ids.size() / (2 * anchors)];
    const auto point = points[id];
    distances.clear();
    for (std::size_t j = 0; j < refs; ++j) {
      const auto other = ids[j * ids.size() / refs];
      if (id != other) distances.push_back(point.distance(points[other]));
    }
    result.distance_pairs += distances.size();
    if (distances.size() < k) continue;
    auto kth = distances.begin() + k - 1;
    std::nth_element(distances.begin(), kth, distances.end());
    radii.push_back(std::sqrt(std::max(0.0f, *kth)));
  }
  if (radii.size() >= anchors / 2) {
    auto middle = radii.begin() + radii.size() / 2;
    std::nth_element(radii.begin(), middle, radii.end());
    result.radius = *middle;
  }
  return result;
}

class LeaderOverlap {
  std::vector<unsigned> counts;
  std::unordered_map<std::uint64_t, unsigned> intersections;

  std::uint64_t key(std::uint32_t a, std::uint32_t b) const {
    if (a > b) std::swap(a, b);
    return std::uint64_t(a) * counts.size() + b;
  }

  double jaccard(std::uint32_t a, std::uint32_t b) const {
    const auto it = intersections.find(key(a, b));
    const unsigned intersection = it == intersections.end() ? 0 : it->second;
    return double(intersection) / (counts[a] + counts[b] - intersection);
  }

 public:
  LeaderOverlap(std::size_t num_leaders,
                const std::vector<std::array<std::uint32_t, 3>>& sample)
      : counts(num_leaders, 0) {
    intersections.reserve(3 * sample.size());
    for (const auto& row : sample) {
      for (auto id : row) ++counts[id];
      ++intersections[key(row[0], row[1])];
      ++intersections[key(row[0], row[2])];
      ++intersections[key(row[1], row[2])];
    }
  }

  bool prefer_third(std::uint32_t first, std::uint32_t second, std::uint32_t third) const {
    constexpr unsigned min_support = 8;
    constexpr double min_gain = 0.05;
    return counts[first] >= min_support && counts[second] >= min_support &&
           counts[third] >= min_support && jaccard(first, second) - jaccard(first, third) >= min_gain;
  }
};

inline bool close_alternative(float first, float second, float third) {
  // Squared L2: stay within 15% of the closest and 5% of the second.
  return third <= 1.3225f * first && third <= 1.1025f * second;
}

struct Depth {
  std::uint64_t buckets = 0, points = 0, leader_pairs = 0;
  std::uint64_t nominal = 0, actual = 0, reduced_points = 0;
  std::map<unsigned, std::uint64_t> histogram;
};
struct Stats {
  std::mutex mutex;
  std::map<int, Depth> depths;
  std::ofstream buckets, scores;
  std::string summary_path;
  std::atomic<std::uint64_t> leaf_count{0}, leaf_points{0}, leaf_squares{0}, proposals{0};
  std::uint64_t density_distance_pairs = 0, diversity_swaps = 0, overlap_samples = 0;
  std::uint64_t occupied = 0, full_nodes = 0, reservoir_capacity = 0;
  Stats() {
    const char* trace = std::getenv("AF_BUCKET_OUT");
    const char* summary = std::getenv("AF_STATS_OUT");
    if (!trace || !summary || *trace != '/' || *summary != '/')
      throw std::runtime_error("AF_BUCKET_OUT and AF_STATS_OUT must be absolute paths");
    if (std::ifstream(trace).good() || std::ifstream(summary).good())
      throw std::runtime_error("Refusing to overwrite adaptive experiment telemetry");
    if (config().calibrate) {
      const char* path = std::getenv("AF_SCORES_OUT");
      if (!path || *path != '/' || std::ifstream(path).good())
        throw std::runtime_error("Invalid AF_SCORES_OUT");
      scores.open(path);
      if (!scores) throw std::runtime_error("Cannot open AF_SCORES_OUT");
      scores << std::setprecision(9);
    }
    buckets.open(trace);
    if (!buckets) throw std::runtime_error("Cannot open AF_BUCKET_OUT");
    summary_path = summary;
  }
};
inline Stats& stats() { static Stats s; return s; }
inline void record_assignment(int depth, std::size_t n, std::size_t leaders,
                              std::size_t cap, const std::vector<std::uint64_t>& hist,
                              const std::vector<float>& sample, DensitySample density,
                              std::uint64_t swaps, std::uint64_t overlap_rows) {
  auto& s = stats();
  std::lock_guard<std::mutex> lock(s.mutex);
  s.density_distance_pairs += density.distance_pairs;
  s.diversity_swaps += swaps;
  s.overlap_samples += overlap_rows;
  for (float value : sample) s.scores << value << '\n';
  auto& d = s.depths[depth];
  ++d.buckets; d.points += n; d.leader_pairs += n * leaders; d.nominal += n * cap;
  std::uint64_t actual = 0, reduced = 0;
  for (unsigned f = 1; f < hist.size(); ++f) {
    actual += f * hist[f]; if (f < cap) reduced += hist[f];
    d.histogram[f] += hist[f];
  }
  d.actual += actual; d.reduced_points += reduced;
  s.buckets << "{\"depth\":" << depth << ",\"points\":" << n
            << ",\"leaders\":" << leaders << ",\"max_fanout\":" << cap
            << ",\"nominal_assignments\":" << n * cap << ",\"actual_assignments\":" << actual
            << ",\"density_radius\":" << density.radius
            << ",\"density_distance_pairs\":" << density.distance_pairs
            << ",\"diversity_swaps\":" << swaps
            << ",\"overlap_samples\":" << overlap_rows
            << ",\"fanout_histogram\":{";
  bool first = true;
  for (unsigned f = 1; f < hist.size(); ++f) if (hist[f]) {
    if (!first) s.buckets << ',';
    first = false; s.buckets << '"' << f << "\":" << hist[f];
  }
  s.buckets << "}}\n";
}
inline void record_leaf(std::size_t n) {
  auto& s = stats();
  s.leaf_count.fetch_add(1, std::memory_order_relaxed);
  s.leaf_points.fetch_add(n, std::memory_order_relaxed);
  s.leaf_squares.fetch_add(std::uint64_t(n) * n, std::memory_order_relaxed);
}
inline void record_proposals(std::size_t n) {
  stats().proposals.fetch_add(n, std::memory_order_relaxed);
}
template<class G, class = void> struct HasCapacity : std::false_type {};
template<class G> struct HasCapacity<G, std::void_t<decltype(std::declval<G&>().kMaxDegree)>> : std::true_type {};
template<class Graph> inline void record_reservoir(Graph& g, std::size_t n) {
  if constexpr (HasCapacity<Graph>::value) {
    auto& s = stats(); s.reservoir_capacity = g.kMaxDegree;
    for (std::size_t i = 0; i < n; ++i) {
      const auto d = g.degree(i); s.occupied += d; s.full_nodes += (d == g.kMaxDegree);
    }
  }
}
inline void dump() {
  auto& s = stats(); const auto& c = config();
  if (config().calibrate) {
    s.scores.flush();
    if (!s.scores) throw std::runtime_error("Failed to write sampled margins");
  }
  s.buckets.flush();
  if (!s.buckets) throw std::runtime_error("Failed to write bucket telemetry");
  std::ofstream out(s.summary_path);
  if (!out) throw std::runtime_error("Cannot open AF_STATS_OUT");
  std::uint64_t nominal = 0, actual = 0, pairs = 0;
  for (const auto& [depth,d] : s.depths) {nominal += d.nominal; actual += d.actual; pairs += d.leader_pairs;}
  out << std::setprecision(12) << "{\"mode\":\"" << c.mode
      << "\",\"epsilon_l2\":" << c.epsilon << ",\"min_depth\":" << c.min_depth
      << ",\"min_fanout\":" << c.min_fanout << ",\"seed\":" << c.seed
      << ",\"nominal_assignments\":" << nominal << ",\"actual_assignments\":" << actual
      << ",\"leader_distance_pairs\":" << pairs
      << ",\"density_distance_pairs\":" << s.density_distance_pairs
      << ",\"diversity_swaps\":" << s.diversity_swaps
      << ",\"overlap_samples\":" << s.overlap_samples << ",\"leaf_count\":" << s.leaf_count.load()
      << ",\"leaf_points\":" << s.leaf_points.load() << ",\"leaf_squared_work\":" << s.leaf_squares.load()
      << ",\"directed_proposals\":" << s.proposals.load()
      << ",\"expected_merge_calls\":" << 2 * s.proposals.load()
      << ",\"reservoir_capacity_per_node\":" << s.reservoir_capacity
      << ",\"reservoir_occupied_slots\":" << s.occupied << ",\"reservoir_full_nodes\":" << s.full_nodes
      << ",\"by_depth\":[";
  bool first = true;
  for (const auto& [depth,d] : s.depths) {
    if (!first) out << ','; first = false;
    out << "{\"depth\":" << depth << ",\"buckets\":" << d.buckets << ",\"points\":" << d.points
        << ",\"leader_distance_pairs\":" << d.leader_pairs << ",\"nominal_assignments\":" << d.nominal
        << ",\"actual_assignments\":" << d.actual << ",\"reduced_points\":" << d.reduced_points
        << ",\"fanout_histogram\":{";
    bool first_hist = true;
    for (auto [f,count] : d.histogram) { if (!first_hist) out << ','; first_hist = false; out << '"' << f << "\":" << count; }
    out << "}}";
  }
  out << "]}\n"; out.flush();
  if (!out) throw std::runtime_error("Failed to write AF_STATS_OUT");
}
}  // namespace af
