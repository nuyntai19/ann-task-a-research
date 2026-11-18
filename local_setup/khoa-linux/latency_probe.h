#pragma once

#include <chrono>
#include <cstddef>
#include <fstream>
#include <iomanip>
#include <stdexcept>
#include <vector>

namespace local_latency {
// Each parallel worker writes one distinct element. The caller starts/ends
// collection outside qsearchAll, after Parlay has joined all workers.
inline std::vector<double> query_us;
inline bool collecting = false;

inline void begin(std::size_t count) {
  if (collecting) throw std::runtime_error("Latency collection already active");
  query_us.assign(count, -1.0);
  collecting = true;
}

class QueryTimer {
  using Clock = std::chrono::steady_clock;
  std::size_t id_;
  Clock::time_point start_;

 public:
  explicit QueryTimer(std::size_t id) : id_(id), start_(Clock::now()) {}
  QueryTimer(const QueryTimer&) = delete;
  QueryTimer& operator=(const QueryTimer&) = delete;
  ~QueryTimer() {
    if (collecting) {
      query_us[id_] = std::chrono::duration<double, std::micro>(Clock::now() - start_).count();
    }
  }
};

inline void write(std::ostream& output, long beam) {
  if (!collecting) throw std::runtime_error("Latency collection not active");
  collecting = false;
  output << std::setprecision(17);
  for (std::size_t i = 0; i < query_us.size(); ++i) {
    if (query_us[i] <= 0.0) throw std::runtime_error("Missing or nonpositive query latency");
    output << beam << ',' << i << ',' << query_us[i] << '\n';
  }
  if (!output) throw std::runtime_error("Failed to write query latency CSV");
}
}  // namespace local_latency
