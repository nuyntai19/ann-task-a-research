add_executable(benchmark_xxt benchmark_xxt.cpp)
target_link_libraries(benchmark_xxt PRIVATE parlay ParlayANN Eigen3::Eigen benchmark::benchmark)

add_executable(benchmark_conversion benchmark_conversion.cpp)
target_link_libraries(benchmark_conversion PRIVATE parlay ParlayANN Eigen3::Eigen benchmark::benchmark)

add_executable(benchmark_euclidean benchmark_euclidean.cpp)
target_link_libraries(benchmark_euclidean PRIVATE parlay ParlayANN Eigen3::Eigen benchmark::benchmark)
