add_executable(compute_groundtruth compute_groundtruth.cpp)
  target_link_libraries(compute_groundtruth PRIVATE parlay ParlayANN
          Eigen3::Eigen absl::synchronization absl::flat_hash_set
          absl::span hwy hwy_contrib)


add_executable(crop crop.cpp)
  target_link_libraries(crop PRIVATE parlay ParlayANN
          Eigen3::Eigen absl::synchronization absl::flat_hash_set
          absl::span hwy hwy_contrib)
