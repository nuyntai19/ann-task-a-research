// Minimal compile-only compatibility layer for the R78 standalone differential test.
// Not a replacement for the real PiPNN/Parlay/Abseil/Eigen dependencies.
#pragma once
#include <cstdint>
#include <cstring>
#include <cmath>
#include <mutex>
#include <cstddef>
#include <utility>

namespace Eigen {
struct bfloat16 {
  uint16_t bits = 0;
  bfloat16() = default;
  explicit bfloat16(float x) {
    uint32_t v;
    std::memcpy(&v, &x, sizeof(v));
    // Round-to-nearest-even, finite Float32 values only in this fixture.
    v += 0x7fffu + ((v >> 16) & 1u);
    bits = static_cast<uint16_t>(v >> 16);
  }
  operator float() const {
    uint32_t v = static_cast<uint32_t>(bits) << 16;
    float result;
    std::memcpy(&result, &v, sizeof(result));
    return result;
  }
};
}
namespace absl {
class Mutex {
  std::mutex m_;
public:
  void Lock() { m_.lock(); }
  void Unlock() { m_.unlock(); }
};
class MutexLock {
  Mutex* p_;
public:
  explicit MutexLock(Mutex* p) : p_(p) { p_->Lock(); }
  ~MutexLock() { p_->Unlock(); }
  MutexLock(const MutexLock&) = delete;
  MutexLock& operator=(const MutexLock&) = delete;
};
}
namespace parlay {
template<class Fn> void parallel_for(size_t start, size_t end, Fn fn) {
  for(size_t i = start; i < end; ++i) fn(i);
}
}
namespace parlayANN {
template<class Index, class Distance> struct LSHCandidate {
  Index point_id;
  Eigen::bfloat16 norm;
  uint16_t hash;
};
}
