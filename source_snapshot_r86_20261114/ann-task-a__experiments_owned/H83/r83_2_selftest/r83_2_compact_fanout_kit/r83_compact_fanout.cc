#include <parlay/primitives.h>
#include <parlay/parallel.h>
#include <parlay/sequence.h>

#include <chrono>
#include <cstdint>
#include <cstdlib>
#include <exception>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <string>
#include <utility>

using Clock = std::chrono::steady_clock;
using KV = std::pair<std::uint32_t, std::uint32_t>;

static double seconds(Clock::time_point a, Clock::time_point b) {
  return std::chrono::duration<double>(b - a).count();
}

static std::uint64_t parse_positive(const char* s) {
  auto v = std::stoull(std::string(s));
  if (v == 0) throw std::invalid_argument("numeric argument must be positive");
  return v;
}

static std::uint32_t key_at(std::size_t slot, std::size_t fanout,
                            std::uint32_t leaders, const std::string& pattern) {
  const std::uint64_t src = slot / fanout;
  const std::uint64_t choice = slot % fanout;
  if (pattern == "clustered") {
    return static_cast<std::uint32_t>(((src / 64) * 23 + choice * 19 +
                                      (src % 64) / 8) % leaders);
  }
  if (pattern == "uniform") {
    return static_cast<std::uint32_t>((src * 37 + choice * 19) % leaders);
  }
  throw std::invalid_argument("unknown pattern");
}

// Order-sensitive checksum over ALL member IDs and each bucket boundary.
// This is a strong diagnostic fingerprint, not a cryptographic certificate.
template <class B>
static std::uint64_t checksum(const B& buckets, std::uint64_t& total) {
  std::uint64_t h = 1469598103934665603ULL;
  total = 0;
  for (std::size_t j = 0; j < buckets.size(); ++j) {
    h ^= (static_cast<std::uint64_t>(j) << 32) ^ buckets[j].size();
    h *= 1099511628211ULL;
    for (const auto v : buckets[j]) {
      h ^= static_cast<std::uint64_t>(v) + 0x9e3779b97f4a7c15ULL;
      h *= 1099511628211ULL;
      ++total;
    }
  }
  return h;
}

int main(int argc, char** argv) {
  try {
    if (argc != 6) {
      std::cerr << "usage: <flat|compact> <points> <fanout> <leaders> <clustered|uniform>\n";
      return 2;
    }
    const std::string arm(argv[1]), pattern(argv[5]);
    const std::size_t points = parse_positive(argv[2]);
    const std::size_t fanout = parse_positive(argv[3]);
    const std::uint64_t m = parse_positive(argv[4]);
    if (arm != "flat" && arm != "compact") throw std::invalid_argument("arm");
    if (m > 512 || m > 65535 || m < fanout) throw std::invalid_argument("leader/fanout bound");
    if (points > UINT32_MAX || points > SIZE_MAX / fanout) throw std::invalid_argument("overflow");
    if (pattern != "clustered" && pattern != "uniform") throw std::invalid_argument("pattern");
    const std::size_t n = points * fanout;
    const std::uint32_t leaders = static_cast<std::uint32_t>(m);
    auto source_at = [fanout](std::size_t slot) -> std::uint32_t {
      return static_cast<std::uint32_t>(slot / fanout);
    };
    auto key = [=, &pattern](std::size_t slot) -> std::uint32_t {
      return key_at(slot, fanout, leaders, pattern);
    };

    auto begin = Clock::now();
    double populate_s = 0.0, group_s = 0.0;
    std::uint64_t entries = 0, digest = 0;
    if (arm == "flat") {
      parlay::sequence<KV> flat(n);
      parlay::parallel_for(0, n, [&](std::size_t i) {
        flat[i] = KV{key(i), source_at(i)};
      }, 2048);
      auto after_populate = Clock::now();
      auto grouped = parlay::group_by_index(flat, leaders);
      auto after_group = Clock::now();
      populate_s = seconds(begin, after_populate);
      group_s = seconds(after_populate, after_group);
      digest = checksum(grouped, entries);
    } else {
      parlay::sequence<std::uint16_t> compressed(n);
      parlay::parallel_for(0, n, [&](std::size_t i) {
        compressed[i] = static_cast<std::uint16_t>(key(i));
      }, 2048);
      auto after_populate = Clock::now();
      auto delayed = parlay::delayed_tabulate(n, [&](std::size_t i) -> KV {
        return KV{static_cast<std::uint32_t>(compressed[i]), source_at(i)};
      });
      auto grouped = parlay::group_by_index(delayed, leaders);
      auto after_group = Clock::now();
      populate_s = seconds(begin, after_populate);
      group_s = seconds(after_populate, after_group);
      digest = checksum(grouped, entries);
    }
    if (entries != n) throw std::runtime_error("output membership count mismatch");
    std::cout << "R83_2_ARM=" << arm
              << " pattern=" << pattern
              << " points=" << points
              << " fanout=" << fanout
              << " leaders=" << leaders
              << " slots=" << n
              << " populate_s=" << populate_s
              << " grouping_s=" << group_s
              << " subtotal_s=" << (populate_s+group_s)
              << " checksum=" << digest
              << " memberships=" << entries << "\n";
    std::cout << "R83_2_DIAGNOSTIC_ONLY_NOT_REAL_ASSIGNMENT_NOT_BUILD\n";
    return 0;
  } catch (const std::exception& e) {
    std::cerr << "R83_2_FAIL " << e.what() << "\n";
    return 3;
  }
}
