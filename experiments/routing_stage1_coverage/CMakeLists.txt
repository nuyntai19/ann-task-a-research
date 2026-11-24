set(ALGORITHMS "${CMAKE_CURRENT_SOURCE_DIR}/../adaptive_fanout_followup/source/algorithms")
add_executable(staged_route_eval evaluate.cc)
target_include_directories(staged_route_eval PRIVATE "${ALGORITHMS}/utils")
target_link_libraries(staged_route_eval PRIVATE parlay ParlayANN Eigen3::Eigen
  absl::synchronization absl::flat_hash_set absl::span)
# Use an isolated copy of just the modified builder tree.
if(EXISTS "${CMAKE_CURRENT_SOURCE_DIR}/../routing_stage3_partition/source/algorithms/PipNN/pipnn.h")
  set(PART "${CMAKE_CURRENT_SOURCE_DIR}/../routing_stage3_partition/source")
  add_executable(staged_route_build "${PART}/algorithms/bench/neighborsTime.C")
  target_include_directories(staged_route_build PRIVATE "${PART}/algorithms/bench"
    "${PART}/algorithms" "${PART}/.."
    "${PART}/external/Parallel-KMeans/seeding")
  target_compile_definitions(staged_route_build PRIVATE USE_DATATYPE_FLOAT_T USE_DISTANCE_EUCLIDEAN R71_H17_TOP2=1)
  target_precompile_headers(staged_route_build PRIVATE "${PART}/algorithms/PipNN/neighbors.h")
  target_link_libraries(staged_route_build PRIVATE parlay ParlayANN Eigen3::Eigen
    absl::synchronization absl::flat_hash_set absl::span hwy hwy_contrib)
endif()
