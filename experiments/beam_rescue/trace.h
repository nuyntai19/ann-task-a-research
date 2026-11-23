#pragma once
#include <cstdint>
#include <vector>

namespace rescue {
using Id = std::uint32_t;
struct Step { Id source; float cutoff; };
enum class Event { cutoff, merge_drop, eviction };
struct Decision { Id id; Event event; };
struct Trace {
  std::vector<Step> steps;
  std::vector<Decision> decisions;
};
}
