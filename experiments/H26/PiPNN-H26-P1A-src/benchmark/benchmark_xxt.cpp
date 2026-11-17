#include <benchmark/benchmark.h>
#include <vector>
#include <Eigen/Dense> // For Eigen operations
#include <random>      // For generating random matrix data
#include <algorithm>   // For std::generate

constexpr size_t dimension = 1024;

namespace utils {
// --- Helper function to generate random matrix data ---
static std::vector<float> GenerateRandomMatrixData(int n) {
    std::vector<float> data(n * dimension);
    std::random_device rd;
    std::mt19937 gen(rd());
    std::uniform_real_distribution<float> distrib(0.0f, 1.0f);
    std::generate(data.begin(), data.end(), [&]() { return distrib(gen); });
    return data;
}
}

// --- Naive ---
// Computes C = A * A^T, where A is an n x n matrix stored in row-major order.
static void NaiveMatrixMultiplyTranspose(const std::vector<float>& a_vec, int n, std::vector<float>& c_vec) {
    if (a_vec.size() != static_cast<size_t>(n * dimension) || c_vec.size() != static_cast<size_t>(n * n)) {
        // Or throw an exception, handle error appropriately
        return;
    }

    for (int i = 0; i < n; ++i) {
        for (int j = 0; j < n; ++j) {
            float sum = 0.0f;
            for (int k = 0; k < dimension; ++k) {
                // C(i, j) = sum over k of A(i, k) * A^T(k, j)
                // A^T(k, j) is A(j, k)
                sum += a_vec[i * dimension + k] * a_vec[j * dimension + k];
            }
            c_vec[i * n + j] = sum;
        }
    }
}

static void CurrentBlockedInnerProduct(const std::vector<float>& a_vec, int n, std::vector<float>& dist_mat) {
  for (size_t a = 0; a < 2; a++) {
    size_t i_min = a * n / 2, i_max = (a + 1) * n / 2;
    for (size_t b = a; b < 2; b++) {
      size_t j_min = b * n / 2, j_max = (b + 1) * n / 2;
      for (size_t i = i_min; i < i_max; ++i) {
        for (size_t j = std::max(i + 1, j_min); j < j_max; ++j) {
          float dist_ij = 0.0f;
          for (size_t k=0; k < dimension; ++k) {
            dist_ij += a_vec[i*dimension + k] * a_vec[j*dimension + k];
          }
          dist_mat[i * n + j] = dist_mat[j * n + i] = dist_ij;
        }
      }
    }
  }
}

// --- Eigen Implementation ---
// Computes C = A * A^T using Eigen.
static void EigenMatrixMultiplyTranspose(const std::vector<float>& a_vec, int n, std::vector<float>& c_vec) {
    if (a_vec.size() != static_cast<size_t>(n * dimension) || c_vec.size() != static_cast<size_t>(n * n)) {
        // Or throw an exception, handle error appropriately
        return;
    }

    // Map the std::vector to an Eigen Matrix.
    // Eigen::Map allows using existing memory without copying.
    Eigen::Map<const Eigen::Matrix<float, Eigen::Dynamic, Eigen::Dynamic, Eigen::RowMajor>> eigen_a(a_vec.data(), n, dimension);
    Eigen::Map<Eigen::Matrix<float, Eigen::Dynamic, Eigen::Dynamic, Eigen::RowMajor>> eigen_c(c_vec.data(), n, n);

    // Perform the multiplication: C = A * A^T
    eigen_c = eigen_a * eigen_a.transpose();
}


// --- Eigen Implementation ---
// Computes C = A * A^T using Eigen.
static void EigenSelfAdjoint(const std::vector<float>& a_vec, int n, std::vector<float>& c_vec) {
    if (a_vec.size() != static_cast<size_t>(n * dimension) || c_vec.size() != static_cast<size_t>(n * n)) {
        // Or throw an exception, handle error appropriately
        return;
    }

    // Map the std::vector to an Eigen Matrix.
    // Eigen::Map allows using existing memory without copying.
    Eigen::Map<const Eigen::Matrix<float, Eigen::Dynamic, Eigen::Dynamic, Eigen::RowMajor>> eigen_a(a_vec.data(), n, dimension);
    Eigen::Map<Eigen::Matrix<float, Eigen::Dynamic, Eigen::Dynamic, Eigen::RowMajor>> eigen_c(c_vec.data(), n, n);

    eigen_c.setZero();  // Important, since the next operation does C += XX^T
    eigen_c.template selfadjointView<Eigen::Lower>().rankUpdate(eigen_a);
}


// --- Google Benchmark Fixture (Optional but good for setup/teardown) ---
class MatrixBenchmark : public benchmark::Fixture {
public:
    void SetUp(const ::benchmark::State& state) override {
        matrix_size = state.range(0); // Get matrix size from benchmark arguments
        input_matrix = utils::GenerateRandomMatrixData(matrix_size);
        result_matrix.resize(matrix_size * matrix_size); // Ensure result vector has correct size
    }

    // Optional: Clean up resources if needed
    void TearDown(const ::benchmark::State&) override {
    }

protected:
    int matrix_size;
    std::vector<float> input_matrix;
    std::vector<float> result_matrix; // To store the output
};

// --- Benchmark for Naive Implementation ---
BENCHMARK_DEFINE_F(MatrixBenchmark, BM_NaiveMatrixMultiplyTranspose)(benchmark::State& state) {
    for (auto _ : state) {
        // This code gets timed
        NaiveMatrixMultiplyTranspose(input_matrix, matrix_size, result_matrix);
        // Clang might optimize away the call if result_matrix is not used.
        // To prevent this, you can use benchmark::DoNotOptimize or benchmark::ClobberMemory.
        benchmark::DoNotOptimize(result_matrix.data());
        benchmark::ClobberMemory();
    }
}

// --- Benchmark for Naive Implementation ---
BENCHMARK_DEFINE_F(MatrixBenchmark, BM_CurrentBlockedInnerProduct)(benchmark::State& state) {
    for (auto _ : state) {
        // This code gets timed
        CurrentBlockedInnerProduct(input_matrix, matrix_size, result_matrix);
        // Clang might optimize away the call if result_matrix is not used.
        // To prevent this, you can use benchmark::DoNotOptimize or benchmark::ClobberMemory.
        benchmark::DoNotOptimize(result_matrix.data());
        benchmark::ClobberMemory();
    }
}

// --- Benchmark for Eigen Implementation ---
BENCHMARK_DEFINE_F(MatrixBenchmark, BM_EigenMatrixMultiplyTranspose)(benchmark::State& state) {
    for (auto _ : state) {
        // This code gets timed
        EigenMatrixMultiplyTranspose(input_matrix, matrix_size, result_matrix);
        benchmark::DoNotOptimize(result_matrix.data());
        benchmark::ClobberMemory();
    }
}

// --- Benchmark for Eigen Implementation ---
BENCHMARK_DEFINE_F(MatrixBenchmark, BM_EigenSelfAdjoint)(benchmark::State& state) {
    for (auto _ : state) {
        // This code gets timed
        EigenSelfAdjoint(input_matrix, matrix_size, result_matrix);
        benchmark::DoNotOptimize(result_matrix.data());
        benchmark::ClobberMemory();
    }
}

// --- Register the benchmarks with different matrix sizes ---
// You can define a range of matrix sizes to test.
// For example: 8x8, 16x16, 32x32, 64x64, 128x128, 256x256
//BENCHMARK_REGISTER_F(MatrixBenchmark, BM_NaiveMatrixMultiplyTranspose)
//    ->RangeMultiplier(2)->Range(8, 1024); // Test sizes from 8 to 256, doubling each time

// Note that using non-pow-2 does not change the running times by
// much, but it is slower. The cost of a copy to pad is probably not
// worth it unless one is doing many successive operations.

BENCHMARK_REGISTER_F(MatrixBenchmark, BM_CurrentBlockedInnerProduct)
    ->RangeMultiplier(2)->Range(8, 1024);
//    ->Arg(31)
//    ->Arg(63)
//    ->Arg(127)
//    ->Arg(511)
//    ->Arg(1023);

BENCHMARK_REGISTER_F(MatrixBenchmark, BM_EigenMatrixMultiplyTranspose)
    ->RangeMultiplier(2)->Range(8, 1024);
//    ->Arg(31)
//    ->Arg(63)
//    ->Arg(127)
//    ->Arg(511)
//    ->Arg(1023);

BENCHMARK_REGISTER_F(MatrixBenchmark, BM_EigenSelfAdjoint)
    ->RangeMultiplier(2)->Range(8, 1024);
//    ->Arg(31)
//    ->Arg(63)
//    ->Arg(127)
//    ->Arg(511)
//    ->Arg(1023);

// --- Main function to run the benchmarks ---
// BENCHMARK_MAIN(); // You can use this, or define your own main for more control.
int main(int argc, char** argv) {
    // You can add any custom initialization here if needed
    ::benchmark::Initialize(&argc, argv);
    if (::benchmark::ReportUnrecognizedArguments(argc, argv)) return 1;
    ::benchmark::RunSpecifiedBenchmarks();
    ::benchmark::Shutdown();
    return 0;
}
