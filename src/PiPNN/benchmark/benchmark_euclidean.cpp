#include <benchmark/benchmark.h>
#include <vector>
#include <Eigen/Dense> // For Eigen operations
#include <random>      // For generating random matrix data
#include <algorithm>   // For std::generate

constexpr size_t dimension = 100;

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

// Very naively computes the squared Euclidean distance between all
// pairs of row vectors from an n x n matrix 'x_data' (stored row-major). 
// Each row of x_data is an n-dimensional vector.
// The result is stored in 'd_data' (n x n, row-major).
// This version wastes work by computing each entry twice.
static void NaiveSquaredEuclideanDistances(
    const std::vector<float>& x_data,
    int n, // Dimension of the matrix (n x n), and also dimension of each row vector
    std::vector<float>& d_data) {

    // Ensure output vector has the correct size.
    // In a benchmark, this might be pre-sized in the fixture's SetUp.
    if (d_data.size() != static_cast<size_t>(n * n)) {
        d_data.resize(static_cast<size_t>(n * n));
    }
    // It's also assumed x_data.size() is n*n, error checking omitted for brevity
    // but would be important in production code.

    for (int i = 0; i < n; ++i) {         // Iterate over the first vector (row X_i)
        for (int j = 0; j < n; ++j) {     // Iterate over the second vector (row X_j)
            float squared_distance = 0.0f;

            // The distance from a vector to itself is 0.
            if (i == j) {
                d_data[i * n + j] = 0.0f;
                continue;
            }

            // Compute squared Euclidean distance: sum((X_ik - X_jk)^2) for k from 0 to n-1
            for (int k = 0; k < dimension; ++k) { // Iterate over the dimensions of the vectors
                // Access element X_ik from x_data (row i, column k)
                float val_i_k = x_data[i * dimension + k];
                // Access element X_jk from x_data (row j, column k)
                float val_j_k = x_data[j * dimension + k];

                float diff = val_i_k - val_j_k;
                squared_distance += diff * diff;
            }
            d_data[i * n + j] = squared_distance;
        }
    }
}

// Computes the squared Euclidean distance between all pairs of row vectors
// from an n x n matrix 'x_data' (stored row-major).
// Optimized by using the symmetry of the distance matrix (D_ij = D_ji, D_ii = 0).
// The result is stored in 'd_data' (n x n, row-major).
static void SymmetricSquaredEuclideanDistances(
    const std::vector<float>& x_data,
    int n, // Dimension of the matrix (n x n), and also dimension of each row vector
    std::vector<float>& d_data) {

    // Ensure output vector has the correct size.
    // In a benchmark, this might be pre-sized in the fixture's SetUp.
    if (d_data.size() != static_cast<size_t>(n * n)) {
        d_data.resize(static_cast<size_t>(n * n));
    }
    // It's also assumed x_data.size() is n*n.

    for (int i = 0; i < n; ++i) {
        // 1. Set the diagonal element D_ii to 0.
        // The distance from a vector to itself is always 0.
        d_data[i * n + i] = 0.0f;

        // 2. Compute distances for the lower triangle (j < i).
        //    For each computed D_ij, also set D_ji.
        for (int j = 0; j < i; ++j) { // Iterate only for j < i
            float squared_distance = 0.0f;

            // Compute squared Euclidean distance: sum((X_ik - X_jk)^2) for k from 0 to n-1
            for (int k = 0; k < dimension; ++k) { // Iterate over the dimensions of the vectors
                // Access element X_ik from x_data (row i, column k)
                float val_i_k = x_data[i * dimension + k];
                // Access element X_jk from x_data (row j, column k)
                float val_j_k = x_data[j * dimension + k];

                float diff = val_i_k - val_j_k;
                squared_distance += diff * diff;
            }

            // Store the computed distance in the lower triangle
            d_data[i * n + j] = squared_distance;
            // By symmetry, D_ji = D_ij, so store it in the upper triangle as well
            d_data[j * n + i] = squared_distance;
        }
    }
}


// Computes the squared Euclidean distance between all pairs of row vectors
// from an n x n matrix 'x_data' (stored row-major) using Eigen.
// Each row of x_data is an n-dimensional vector.
// The result is stored in 'd_data' (n x n, row-major).
static void EigenSquaredEuclideanDistances(
    const std::vector<float>& x_data,
    int n, // Dimension of the matrix (n x n), and also dimension of each row vector
    std::vector<float>& d_data) {

    // Basic size checking, ensure output vector can be mapped or resize.
    if (x_data.size() != static_cast<size_t>(n * dimension)) {
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


    // Map the input std::vector to an Eigen Matrix without copying.
    // eigen_x will be an n x n matrix.
    Eigen::Map<const Eigen::Matrix<float, Eigen::Dynamic, Eigen::Dynamic, Eigen::RowMajor>> eigen_x(x_data.data(), n, dimension);

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
BENCHMARK_DEFINE_F(MatrixBenchmark, BM_NaiveSquaredEuclideanDistances)(benchmark::State& state) {
    for (auto _ : state) {
        // This code gets timed
        NaiveSquaredEuclideanDistances(input_matrix, matrix_size, result_matrix);
        // Clang might optimize away the call if result_matrix is not used.
        // To prevent this, you can use benchmark::DoNotOptimize or benchmark::ClobberMemory.
        benchmark::DoNotOptimize(result_matrix.data());
        benchmark::ClobberMemory();
    }
//    state.SetComplexityN(state.range(0)); // For complexity analysis (N = matrix_size)
}

// --- Benchmark for Naive Implementation ---
BENCHMARK_DEFINE_F(MatrixBenchmark, BM_SymmetricSquaredEuclideanDistances)(benchmark::State& state) {
    for (auto _ : state) {
        // This code gets timed
        SymmetricSquaredEuclideanDistances(input_matrix, matrix_size, result_matrix);
        // Clang might optimize away the call if result_matrix is not used.
        // To prevent this, you can use benchmark::DoNotOptimize or benchmark::ClobberMemory.
        benchmark::DoNotOptimize(result_matrix.data());
        benchmark::ClobberMemory();
    }
//    state.SetComplexityN(state.range(0)); // For complexity analysis (N = matrix_size)
}

// --- Benchmark for Eigen Implementation ---
BENCHMARK_DEFINE_F(MatrixBenchmark, BM_EigenSquaredEuclideanDistances)(benchmark::State& state) {
    for (auto _ : state) {
        // This code gets timed
        EigenSquaredEuclideanDistances(input_matrix, matrix_size, result_matrix);
        benchmark::DoNotOptimize(result_matrix.data());
        benchmark::ClobberMemory();
    }
//    state.SetComplexityN(state.range(0));
}

//// --- Register the benchmarks with different matrix sizes ---
//// You can define a range of matrix sizes to test.
//// For example: 8x8, 16x16, 32x32, 64x64, 128x128, 256x256
//BENCHMARK_REGISTER_F(MatrixBenchmark, BM_NaiveSquaredEuclideanDistances)
//    ->RangeMultiplier(2)->Range(8, 1024) // Test sizes from 8 to 256, doubling each time
//    ->Complexity(benchmark::oN);       // Expected complexity (roughly N^3 for naive)

// --- Register the benchmarks with different matrix sizes ---
// You can define a range of matrix sizes to test.
// For example: 8x8, 16x16, 32x32, 64x64, 128x128, 256x256
BENCHMARK_REGISTER_F(MatrixBenchmark, BM_SymmetricSquaredEuclideanDistances)
    ->RangeMultiplier(2)->Range(8, 1024); // Test sizes from 8 to 256, doubling each time
//    ->Complexity(benchmark::oN);       // Expected complexity (roughly N^3 for naive)

BENCHMARK_REGISTER_F(MatrixBenchmark, BM_EigenSquaredEuclideanDistances)
    ->RangeMultiplier(2)->Range(8, 1024);
//    ->Complexity(benchmark::oN);       // Eigen is also N^3 but much more optimized

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
