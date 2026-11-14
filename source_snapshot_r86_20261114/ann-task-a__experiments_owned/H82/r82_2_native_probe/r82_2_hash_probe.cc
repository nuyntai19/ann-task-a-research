// R82.2 research diagnostic. No ANN graph construction, no writes to data files.
#include <algorithm>
#include <array>
#include <cerrno>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <limits>
#include <memory>
#include <random>
#include <stdexcept>
#include <string>
#include <vector>
#include <sys/mman.h>
#include <sys/stat.h>
#include <fcntl.h>
#include <unistd.h>

// Real pinned original source supplies Hash_Family and Parlay random generator.
#include "algorithms/utils/hash.h"

struct R82Point {};
struct R82Range {};
constexpr std::uint32_t N = 1000000;
constexpr std::uint32_t D = 128;
constexpr std::uint32_t B = 12;
constexpr std::uint64_t EXPECT_BASE_BYTES = 8ull + 4ull * N * D;

struct ReadMapping {
  int fd = -1;
  std::size_t size = 0;
  void *ptr = MAP_FAILED;
  explicit ReadMapping(const char *path) {
    fd = open(path, O_RDONLY | O_CLOEXEC);
    if (fd < 0) throw std::runtime_error("R82_2_BASE_OPEN_FAIL");
    struct stat st{};
    if (fstat(fd, &st) != 0 || st.st_size != static_cast<off_t>(EXPECT_BASE_BYTES))
      throw std::runtime_error("R82_2_BASE_BYTE_LENGTH_FAIL");
    size = static_cast<std::size_t>(st.st_size);
    ptr = mmap(nullptr, size, PROT_READ, MAP_PRIVATE, fd, 0);
    if (ptr == MAP_FAILED) throw std::runtime_error("R82_2_BASE_MMAP_FAIL");
    std::uint32_t hdr[2]{};
    std::memcpy(hdr, ptr, 8);
    if (hdr[0] != N || hdr[1] != D)
      throw std::runtime_error("R82_2_BASE_HEADER_FAIL");
  }
  ~ReadMapping() {
    if (ptr != MAP_FAILED) munmap(ptr, size);
    if (fd >= 0) close(fd);
  }
  const float *points() const {
    return reinterpret_cast<const float *>(static_cast<const unsigned char *>(ptr) + 8);
  }
  ReadMapping(const ReadMapping&) = delete;
  ReadMapping& operator=(const ReadMapping&) = delete;
};

struct Stats {
  std::uint64_t count = 0, nominal = 0, certain = 0, possible = 0, sensitive = 0;
};

int main(int argc, char **argv) {
  try {
    if (argc != 2) {
      std::cerr << "Usage: r82_2_hash_probe sift1m.fbin < fixed-width-16B records\\n";
      return 2;
    }
    ReadMapping input(argv[1]);
    const float *points = input.points();
    // EXACT original hash family code, same (b,d,seed) as original PiPNN
    // SketchHash(b=12,dim=128,Points,seed=0). Sketch values recomputed only
    // for sampled unique point IDs, with straightforward float accumulation.
    Hash_Family<R82Point, R82Range, std::uint32_t> family(B, D, 0);
    std::vector<std::array<float, B>> sketch(N);
    std::vector<std::uint8_t> seen(N, 0);
    std::uint64_t unique_points = 0;

    auto get_sketch = [&](std::uint32_t id) -> const std::array<float, B>& {
      if (!seen[id]) {
        const float *v = points + static_cast<std::uint64_t>(id) * D;
        for (std::uint32_t h = 0; h < B; ++h) {
          const auto &plane = family.get_random_vector(h);
          float dot = 0.0f;
          for (std::uint32_t j = 0; j < D; ++j) dot += v[j] * plane[j];
          sketch[id][h] = dot;
        }
        seen[id] = 1;
        ++unique_points;
      }
      return sketch[id];
    };

    std::array<Stats, 128> leaves{};
    Stats all{};
    while (true) {
      std::uint32_t row[4]{}; // leaf-slot 0..127, source ID, v1, v2
      std::cin.read(reinterpret_cast<char *>(row), sizeof(row));
      if (!std::cin) {
        if (std::cin.eof() && std::cin.gcount() == 0) break;
        throw std::runtime_error("R82_2_TRUNCATED_STDIN_RECORD");
      }
      const std::uint32_t leaf = row[0], src = row[1], a = row[2], b = row[3];
      if (leaf >= leaves.size() || src >= N || a >= N || b >= N ||
          a == b || a == src || b == src)
        throw std::runtime_error("R82_2_ROW_ID_VALIDATION_FAIL");

      const auto &s = get_sketch(src);
      const auto &x = get_sketch(a);
      const auto &y = get_sketch(b);
      bool equal = true, same_certain = true, could_equal = true;
      bool sensitive = false;
      for (std::uint32_t h = 0; h < B; ++h) {
        const float dx = x[h] - s[h], dy = y[h] - s[h];
        const bool bx = (dx > 0), by = (dy > 0);
        if (bx != by) equal = false;
        // Conservative detector for potential FP accumulation / subtraction
        // differences; not a proven numerical error bound.
        const float tx = 1e-6f * std::max({1.0f, std::abs(x[h]), std::abs(s[h])});
        const float ty = 1e-6f * std::max({1.0f, std::abs(y[h]), std::abs(s[h])});
        const bool ax = !std::isfinite(dx) || std::abs(dx) <= tx;
        const bool ay = !std::isfinite(dy) || std::abs(dy) <= ty;
        sensitive |= ax || ay;
        if (ax || ay) same_certain = false;
        else if (bx != by) could_equal = false;
      }
      if (!equal) same_certain = false;
      const auto add = [&](Stats &st) {
        ++st.count;
        if (equal) ++st.nominal;
        if (same_certain) ++st.certain;
        if (could_equal) ++st.possible;
        if (sensitive) ++st.sensitive;
      };
      add(all);
      add(leaves[leaf]);
    }
    if (all.count == 0) throw std::runtime_error("R82_2_NO_ROWS");
    std::cout << "R82_2_COUNTS rows=" << all.count
              << " nominal=" << all.nominal
              << " definite=" << all.certain
              << " possible=" << all.possible
              << " sensitive=" << all.sensitive
              << " unique_points=" << unique_points << '\n';
    for (std::size_t k = 0; k < leaves.size(); ++k)
      std::cout << "R82_2_LEAF slot=" << k
                << " rows=" << leaves[k].count
                << " nominal=" << leaves[k].nominal
                << " definite=" << leaves[k].certain
                << " possible=" << leaves[k].possible
                << " sensitive=" << leaves[k].sensitive << '\n';
    std::cout << "R82_2_CPP_HASH_DIAGNOSTIC_PASS\n";
    return 0;
  } catch (const std::exception &e) {
    std::cerr << e.what() << '\n';
    return 3;
  }
}
