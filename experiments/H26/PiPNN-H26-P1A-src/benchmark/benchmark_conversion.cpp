#include <benchmark/benchmark.h>
#include <vector>
#include <Eigen/Dense>
#include <random>
#include <algorithm>
#include <iostream>

namespace utils {

static std::vector<int8_t> GenerateRandomMatrixData(int n) {
    std::vector<int8_t> data(n * n);
    std::random_device rd;
    std::mt19937 gen(rd());
    std::uniform_real_distribution<float> distrib(0.0f, 1.0f);
    std::generate(data.begin(), data.end(), [&]() { return static_cast<int8_t>(distrib(gen) * 128); });
    return data;
}

/**
 * @brief Checks if two floating-point numbers are "almost equal".
 *
 * This function compares two floating-point numbers (float or double) to see if
 * they are close enough to be considered equal. It uses a hybrid approach,
 * considering both an absolute epsilon and a relative epsilon.
 *
 * @tparam T A floating-point type (float, double, or long double).
 * @param a The first floating-point number.
 * @param b The second floating-point number.
 * @param epsilon The absolute tolerance. Defaults to the machine epsilon for the type.
 * This is useful when comparing numbers close to zero.
 * @param relativeEpsilon The relative tolerance. Defaults to the machine epsilon for the type.
 * This is useful when comparing numbers of larger magnitude.
 * @return True if the numbers are considered almost equal, false otherwise.
 *
 * @note
 * - Handles comparisons involving zero, infinity, and NaN.
 * - NaN is never equal to anything, including itself.
 * - Positive and negative infinity are only equal to themselves.
 */
template <typename T>
bool almost_equals(T a, T b,
                   T epsilon = std::numeric_limits<T>::epsilon(),
                   T relativeEpsilon = std::numeric_limits<T>::epsilon()) {
    static_assert(std::is_floating_point<T>::value, "Type T must be a floating-point type.");

    // Handle NaN: NaN is never equal to anything, including itself.
    if (std::isnan(a) || std::isnan(b)) {
        return false;
    }

    // Handle infinities: they are only equal if they are the same infinity.
    if (std::isinf(a) || std::isinf(b)) {
        return a == b; // This will be true if both are +inf or both are -inf
    }

    // Check for exact equality first (covers the case where a and b are both zero).
    if (a == b) {
        return true;
    }

    T diff = std::abs(a - b);

    // Check absolute difference - useful for comparisons near zero.
    if (diff <= epsilon) {
        return true;
    }

    // Check relative difference - useful for comparisons where numbers are not near zero.
    // The `std::max` is used to handle cases where one number is zero,
    // preventing division by zero and ensuring the relative comparison is meaningful.
    // Using `std::numeric_limits<T>::min()` as the smallest positive normal number
    // helps avoid issues if one number is very small but not zero.
    return diff <= relativeEpsilon * std::max({std::abs(a), std::abs(b), std::numeric_limits<T>::min()});
}

void VerifyAlmostEquals(std::vector<float>& x, std::vector<float>& y, size_t n) {

//  for (size_t i=0; i < n; ++i) {
//    for (size_t j=0; j < i; ++j) {
//      if (!almost_equals(x[i*n + j], y[i*n + j])) {
//        std::cout << x[i*n + j] << " " << y[i*n + j] << " not equal!" << std::endl;
//        std::cout << "Matrix sizes: " << x.size() << " " << y.size() << std::endl;
//        for (size_t k=0; k < x.size(); ++k) {
//          std::cout << x[k] << " " << y[k] << std::endl;
//        }
//        exit(-1);
//      }
//    }
//  }

  for (size_t i=0; i < x.size(); ++i) {
    if (!almost_equals(x[i], y[i])) {
      std::cout << x[i] << " " << y[i] << " not equal!" << std::endl;
      std::cout << "Matrix sizes: " << x.size() << " " << y.size() << std::endl;
      for (size_t j=0; j < x.size(); ++j) {
        std::cout << x[j] << " " << y[j] << std::endl;
      }
      exit(-1);
    }
  }
}

}  // namespace utils

static void CurrentBlockedInnerProduct(const std::vector<int8_t>& a_vec, int n, std::vector<float>& dist_mat) {
  for (size_t a = 0; a < 2; a++) {
    size_t i_min = a * n / 2, i_max = (a + 1) * n / 2;
    for (size_t b = a; b < 2; b++) {
      size_t j_min = b * n / 2, j_max = (b + 1) * n / 2;
      for (size_t i = i_min; i < i_max; ++i) {
        for (size_t j = std::max(i + 1, j_min); j < j_max; ++j) {
          float dist_ij = 0.0f;
          for (size_t k=0; k < n; ++k) {
            dist_ij += static_cast<float>(a_vec[i*n + k]) * static_cast<float>(a_vec[j*n + k]);
          }
          dist_mat[i * n + j] = dist_mat[j * n + i] = dist_ij;
        }
      }
    }
  }
}

static void CurrentBlockedSquareEuclidean(const std::vector<int8_t>& a_vec, int n, std::vector<float>& dist_mat) {
//  for (size_t i=0; i < n; ++i) {
//    for (size_t j=0; j < n; ++j) {
//      float dist_ij = 0.0f;
//      for (size_t k=0; k < n; ++k) {
//        dist_ij += (a_vec[i*n + k] - a_vec[j*n + k]) * (a_vec[i*n + k] - a_vec[j*n + k]);
//      }
//      dist_mat[i * n + j] = dist_ij;
//    }
//  }
  for (size_t a = 0; a < 2; a++) {
    size_t i_min = a * n / 2, i_max = (a + 1) * n / 2;
    for (size_t b = a; b < 2; b++) {
      size_t j_min = b * n / 2, j_max = (b + 1) * n / 2;
      for (size_t i = i_min; i < i_max; ++i) {
        for (size_t j = std::max(i + 1, j_min); j < j_max; ++j) {
          float dist_ij = 0.0f;
          for (size_t k=0; k < n; ++k) {
            float r = static_cast<float>(a_vec[i*n + k]) - static_cast<float>(a_vec[j*n + k]);
            dist_ij += r*r;
          }
          dist_mat[i * n + j] = dist_mat[j * n + i] = dist_ij;
        }
      }
    }
  }
}

// --- Eigen Implementation ---
// Computes C = A * A^T using Eigen.
static void EigenSelfAdjoint(const std::vector<int8_t>& a_vec, int n, std::vector<float>& c_vec) {
    if (a_vec.size() != static_cast<size_t>(n * n) || c_vec.size() != static_cast<size_t>(n * n)) {
        // Or throw an exception, handle error appropriately
        return;
    }

    // Create an Eigen::Map to the int8_t data
    Eigen::Map<const Eigen::Matrix<int8_t, Eigen::Dynamic, Eigen::Dynamic, Eigen::RowMajor>> int8MatrixMap(a_vec.data(), n, n);

    // Use the cast() method to convert to float
    auto eigen_a = int8MatrixMap.cast<float>();

    // Map the std::vector to an Eigen Matrix.
    // Eigen::Map allows using existing memory without copying.
    // Eigen::Map<const Eigen::Matrix<float, Eigen::Dynamic, Eigen::Dynamic, Eigen::RowMajor>> eigen_a(a_vec.data(), n, n);
    Eigen::Map<Eigen::Matrix<float, Eigen::Dynamic, Eigen::Dynamic, Eigen::RowMajor>> eigen_c(c_vec.data(), n, n);

    eigen_c.setZero();  // Important, since the next operation does C += XX^T
    //eigen_c.template selfadjointView<Eigen::Lower>().rankUpdate(eigen_a);
    eigen_c.template selfadjointView<Eigen::Lower>().rankUpdate(eigen_a);

//    eigen_c = eigen_c.selfadjointView<Eigen::Lower>();

//    std::vector<float> check(a_vec.size());
//    CurrentBlockedInnerProduct(a_vec, n, check);
//    utils::VerifyAlmostEquals(c_vec, check, n);
}


// Computes the squared Euclidean distance between all pairs of row vectors
// from an n x n matrix 'x_data' (stored row-major) using Eigen.
// Each row of x_data is an n-dimensional vector.
// The result is stored in 'd_data' (n x n, row-major).
static void EigenSquaredEuclideanDistances(
    const std::vector<int8_t>& x_data,
    int n, // Dimension of the matrix (n x n), and also dimension of each row vector
    std::vector<float>& d_data) {

//    std::cout << "n = " << n << std::endl;
//    for (size_t i=0; i < n; ++i) {
//      std::cout << "[";
//      for (size_t j=0; j < n; ++j) {
//        std::cout << static_cast<float>(x_data[i*n + j]) << ",";
//      }
//      std::cout << "]" << std::endl;
//    }
//    std::cout << "Matrix dumped." << std::endl;

    // Basic size checking, ensure output vector can be mapped or resize.
    if (x_data.size() != static_cast<size_t>(n * n)) {
        // Handle error: input data size mismatch
        // For a benchmark, this might be an assertion or pre-condition.
        // If d_data also needs to be valid for an error return, ensure it's empty or correctly sized.
        if (d_data.size() != 0) d_data.clear(); // Or some other error indication
        return;
    }
    if (d_data.size() != static_cast<size_t>(n * n)) {
        d_data.resize(static_cast<size_t>(n * n));
    }
    if (n == 0) { // Handle empty matrix case
        return;
    }

    // Create an Eigen::Map to the int8_t data
    Eigen::Map<const Eigen::Matrix<int8_t, Eigen::Dynamic, Eigen::Dynamic, Eigen::RowMajor>> int8MatrixMap(x_data.data(), n, n);
    // Use the cast() method to convert to float
    auto eigen_x = int8MatrixMap.cast<float>();

    // Map the output std::vector to an Eigen Matrix without copying.
    Eigen::Map<Eigen::Matrix<float, Eigen::Dynamic, Eigen::Dynamic, Eigen::RowMajor>> eigen_d(d_data.data(), n, n);

    // 1. Compute the Gramian matrix P = X * X^T.
    // P_ij = dot_product(X_i, X_j).
    // The result P is symmetric. We can give Eigen a hint for optimization.
    Eigen::Matrix<float, Eigen::Dynamic, Eigen::Dynamic, Eigen::RowMajor> P(n, n);
    P.setZero();
    P.selfadjointView<Eigen::Lower>().rankUpdate(eigen_x);
    // After this, P is a symmetric matrix where P_ij = X_i . X_j^T.
    // The .selfadjointView<Lower>() tells Eigen to compute the lower triangle
    // and fill the upper by symmetry. .noalias() avoids aliasing issues.

    // 2. Compute the squared L2 norm of each row vector X_i.
    // S_i = ||X_i||^2. This is also the diagonal of P.
    // eigen_x.rowwise().squaredNorm() would also compute this: VectorXf S(n); for(int k=0;k<n;++k) S(k) = eigen_x.row(k).squaredNorm();
    Eigen::VectorXf S = P.diagonal(); // S is an n x 1 column vector. S(i) = ||X_i||^2.

    // 3. Compute D_ij = S_i + S_j - 2 * P_ij using broadcasting.
    //    a) Set D_ij = S_i for all j (replicate S column-wise)
    eigen_d.colwise() = S;

    //    b) Add S_j to D_ij for all i (replicate S.transpose() row-wise and add)
    eigen_d.rowwise() += S.transpose();

    //    c) Subtract 2 * P_ij
    eigen_d -= 2 * P;

    // Note on D_ii: Mathematically, D_ii = S_i + S_i - 2 * P_ii = 2*S_i - 2*S_i = 0.
    // Floating point arithmetic might result in very small non-zero values for D_ii.
    // If strictly D_ii = 0 is required for all i, you could explicitly set it:
    // eigen_d.diagonal().setZero();
    // However, for most use cases, the tiny error (if any) is acceptable.

    // To populate the upper triangle too.
//    eigen_d = eigen_d.selfadjointView<Eigen::Lower>();

//    std::vector<float> check(d_data.size());
//    CurrentBlockedSquareEuclidean(x_data, n, check);
//    utils::VerifyAlmostEquals(d_data, check, n);
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
    std::vector<int8_t> input_matrix;
    std::vector<float> result_matrix; // To store the output
};

//// --- Benchmark for Naive Implementation ---
//BENCHMARK_DEFINE_F(MatrixBenchmark, BM_NaiveMatrixMultiplyTranspose)(benchmark::State& state) {
//    for (auto _ : state) {
//        // This code gets timed
//        NaiveMatrixMultiplyTranspose(input_matrix, matrix_size, result_matrix);
//        // Clang might optimize away the call if result_matrix is not used.
//        // To prevent this, you can use benchmark::DoNotOptimize or benchmark::ClobberMemory.
//        benchmark::DoNotOptimize(result_matrix.data());
//        benchmark::ClobberMemory();
//    }
//}

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
BENCHMARK_DEFINE_F(MatrixBenchmark, BM_EigenSelfAdjoint)(benchmark::State& state) {
    for (auto _ : state) {
        // This code gets timed
        EigenSelfAdjoint(input_matrix, matrix_size, result_matrix);
        benchmark::DoNotOptimize(result_matrix.data());
        benchmark::ClobberMemory();
    }
}


// --- Benchmark for Naive Implementation ---
BENCHMARK_DEFINE_F(MatrixBenchmark, BM_CurrentBlockedSquaredEuclidean)(benchmark::State& state) {
    for (auto _ : state) {
        // This code gets timed
        CurrentBlockedSquareEuclidean(input_matrix, matrix_size, result_matrix);
        // Clang might optimize away the call if result_matrix is not used.
        // To prevent this, you can use benchmark::DoNotOptimize or benchmark::ClobberMemory.
        benchmark::DoNotOptimize(result_matrix.data());
        benchmark::ClobberMemory();
    }
}

// --- Benchmark for Eigen Implementation ---
BENCHMARK_DEFINE_F(MatrixBenchmark, BM_EigenSquaredEuclideanDistances)(benchmark::State& state) {
    for (auto _ : state) {
        // This code gets timed
        EigenSquaredEuclideanDistances(input_matrix, matrix_size, result_matrix);
        benchmark::DoNotOptimize(result_matrix.data());
        benchmark::ClobberMemory();
    }
}

// --- Register the benchmarks with different matrix sizes ---
// You can define a range of matrix sizes to test.
// For example: 8x8, 16x16, 32x32, 64x64, 128x128, 256x256
//BENCHMARK_REGISTER_F(MatrixBenchmark, BM_NaiveMatrixMultiplyTranspose)
//    ->RangeMultiplier(2)->Range(8, 1024); // Test sizes from 8 to 256, doubling each time

BENCHMARK_REGISTER_F(MatrixBenchmark, BM_CurrentBlockedInnerProduct)
    ->RangeMultiplier(2)->Range(8, 1024);

BENCHMARK_REGISTER_F(MatrixBenchmark, BM_EigenSelfAdjoint)
    ->RangeMultiplier(2)->Range(8, 1024);

BENCHMARK_REGISTER_F(MatrixBenchmark, BM_CurrentBlockedSquaredEuclidean)
    ->RangeMultiplier(2)->Range(8, 1024);

BENCHMARK_REGISTER_F(MatrixBenchmark, BM_EigenSquaredEuclideanDistances)
    ->RangeMultiplier(2)->Range(8, 1024);

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
