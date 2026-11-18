#pragma once
#include <algorithm>
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
#include <utility>
#include <vector>

namespace af {
struct Config {
  bool adaptive = false;
  double epsilon = 0.03;
  int min_depth = 1;
  unsigned min_fanout = 1;
  unsigned seed = 555;
  Config() {
    const char* mode = std::getenv("AF_MODE");
    std::string m = mode ? mode : "fixed";
    if (m != "fixed" && m != "adaptive") throw std::runtime_error("Invalid AF_MODE");
    adaptive = m == "adaptive";
    if (const char* p = std::getenv("AF_EPSILON")) epsilon = std::stod(p);
    if (const char* p = std::getenv("AF_MIN_DEPTH")) min_depth = std::stoi(p);
    if (const char* p = std::getenv("AF_MIN_FANOUT")) min_fanout = std::stoul(p);
    if (const char* p = std::getenv("AF_SEED")) seed = std::stoul(p);
    if (epsilon < 0 || epsilon > 10 || min_depth < 0 || min_fanout < 1)
      throw std::runtime_error("Invalid adaptive fanout configuration");
  }
};
inline const Config& config() { static Config c; return c; }
inline bool eligible(int depth, std::size_t cap) {
  return config().adaptive && depth >= config().min_depth && cap > config().min_fanout;
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

struct Depth {
  std::uint64_t buckets = 0, points = 0, leader_pairs = 0;
  std::uint64_t nominal = 0, actual = 0, reduced_points = 0;
  std::map<unsigned, std::uint64_t> histogram;
};
struct Stats {
  std::mutex mutex;
  std::map<int, Depth> depths;
  std::ofstream buckets;
  std::string summary_path;
  std::atomic<std::uint64_t> leaf_count{0}, leaf_points{0}, leaf_squares{0}, proposals{0};
  std::uint64_t occupied = 0, full_nodes = 0, reservoir_capacity = 0;
  Stats() {
    const char* trace = std::getenv("AF_BUCKET_OUT");
    const char* summary = std::getenv("AF_STATS_OUT");
    if (!trace || !summary || *trace != '/' || *summary != '/')
      throw std::runtime_error("AF_BUCKET_OUT and AF_STATS_OUT must be absolute paths");
    if (std::ifstream(trace).good() || std::ifstream(summary).good())
      throw std::runtime_error("Refusing to overwrite adaptive experiment telemetry");
    buckets.open(trace);
    if (!buckets) throw std::runtime_error("Cannot open AF_BUCKET_OUT");
    summary_path = summary;
  }
};
inline Stats& stats() { static Stats s; return s; }
inline void record_assignment(int depth, std::size_t n, std::size_t leaders,
                              std::size_t cap, const std::vector<std::uint64_t>& hist) {
  auto& s = stats();
  std::lock_guard<std::mutex> lock(s.mutex);
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
  s.buckets.flush();
  if (!s.buckets) throw std::runtime_error("Failed to write bucket telemetry");
  std::ofstream out(s.summary_path);
  if (!out) throw std::runtime_error("Cannot open AF_STATS_OUT");
  std::uint64_t nominal = 0, actual = 0, pairs = 0;
  for (const auto& [depth,d] : s.depths) {nominal += d.nominal; actual += d.actual; pairs += d.leader_pairs;}
  out << std::setprecision(12) << "{\"mode\":\"" << (c.adaptive ? "adaptive" : "fixed")
      << "\",\"epsilon_l2\":" << c.epsilon << ",\"min_depth\":" << c.min_depth
      << ",\"min_fanout\":" << c.min_fanout << ",\"seed\":" << c.seed
      << ",\"nominal_assignments\":" << nominal << ",\"actual_assignments\":" << actual
      << ",\"leader_distance_pairs\":" << pairs << ",\"leaf_count\":" << s.leaf_count.load()
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
