# R71_H17_PACKED_TOP2_ISOLATED
option(R71_USE_H17 "Enable H17 packed top2 for MST_DEG==2" OFF)
option(R86_USE_COUNTERS "Enable R86 logical operation counters" OFF)
# R70_COMPILE_TIME_RESERVOIR_SELECTION (research-only isolated worktree)
option(R70_USE_TIER "R70 Two-Tier physical reservoir; logical C unchanged" OFF)
if(R86_USE_COUNTERS AND R70_USE_TIER)
  message(FATAL_ERROR "R86 counters only support Flat LSHGraph")
endif()
#add_executable(${TARGET_NAME} ../bench/neighborsTime.C)
#target_link_libraries(${TARGET_NAME} PRIVATE parlay ParlayANN Eigen3::Eigen)
#target_include_directories(${TARGET_NAME} PRIVATE ../bench)
#target_precompile_headers(${TARGET_NAME} PRIVATE neighbors.h)

# For iterating in CMake and for display/target names
set(CONFIG_DATATYPES_CMAKE INT8_T UINT8_T FLOAT_T)

set(CONFIG_DISTANCETYPES_CMAKE EUCLIDEAN MIPS)

# --- Loop through all combinations and create targets ---
foreach(CURRENT_DATATYPE_CMAKE ${CONFIG_DATATYPES_CMAKE})
    foreach(CURRENT_DISTANCETYPE_CMAKE ${CONFIG_DISTANCETYPES_CMAKE})
        # 1. Create a unique target name
        set(TARGET_NAME "neighbors-pipnn_${CURRENT_DATATYPE_CMAKE}_${CURRENT_DISTANCETYPE_CMAKE}")

        # 2. Define the compile-time definitions for C++
        set(DATATYPE_DEFINE "USE_DATATYPE_${CURRENT_DATATYPE_CMAKE}") # e.g., USE_DATATYPE_INT8T
        set(DISTANCETYPE_DEFINE "USE_DISTANCE_${CURRENT_DISTANCETYPE_CMAKE}") # e.g., USE_DISTANCE_EUCLIDEAN

        # 3. Add the executable target
        add_executable(${TARGET_NAME} ../bench/neighborsTime.C)

        # 4. Pass the definitions to the compiler for this specific target
        target_compile_definitions(${TARGET_NAME} PRIVATE
            ${DATATYPE_DEFINE}
            ${DISTANCETYPE_DEFINE}
        )

        target_link_libraries(${TARGET_NAME} PRIVATE parlay ParlayANN
          Eigen3::Eigen absl::synchronization absl::flat_hash_set
          absl::span hwy hwy_contrib)
        target_include_directories(${TARGET_NAME} PRIVATE ../bench ../../external/Parallel-KMeans/seeding)
        target_precompile_headers(${TARGET_NAME} PRIVATE neighbors.h)
        if(R71_USE_H17)
            target_compile_definitions(${TARGET_NAME} PRIVATE R71_H17_TOP2=1)
        endif()
        if(R70_USE_TIER)
            target_compile_definitions(${TARGET_NAME} PRIVATE R70_TWO_TIER=1)
        endif()
        if(R86_USE_COUNTERS)
            target_compile_definitions(${TARGET_NAME} PRIVATE R86_COUNTERS=1)
        endif()

        message(STATUS "Configured Target: ${TARGET_NAME} with Definitions: ${DATATYPE_DEFINE}, ${DISTANCETYPE_DEFINE}")
    endforeach()
endforeach()


# R70 research-only native correctness/microbench target (isolated worktree)
add_executable(r70_native_tests r70_native_tests.cc)
target_link_libraries(r70_native_tests PRIVATE parlay ParlayANN
  Eigen3::Eigen absl::synchronization absl::flat_hash_set absl::span hwy hwy_contrib)
target_include_directories(r70_native_tests PRIVATE ../bench ../../external/Parallel-KMeans/seeding)

# R70_RECALL_EVALUATOR_TARGET: reads saved graphs, does not build PiPNN graph
add_executable(r70_graph_recall r70_graph_recall.cc)
target_link_libraries(r70_graph_recall PRIVATE
  parlay ParlayANN Eigen3::Eigen absl::synchronization
  absl::flat_hash_set absl::span hwy hwy_contrib)
target_include_directories(r70_graph_recall PRIVATE
  ../bench ../../external/Parallel-KMeans/seeding)
target_compile_features(r70_graph_recall PRIVATE cxx_std_17)

# R72_SIFT1M_RECALL_EVALUATOR_TARGET: SIFT1M search-only; does NOT BUILD graph
add_executable(r72_graph_recall r72_graph_recall.cc)
target_link_libraries(r72_graph_recall PRIVATE
  parlay ParlayANN Eigen3::Eigen absl::synchronization
  absl::flat_hash_set absl::span hwy hwy_contrib)
target_include_directories(r72_graph_recall PRIVATE
  ../bench ../../external/Parallel-KMeans/seeding)
target_compile_features(r72_graph_recall PRIVATE cxx_std_17)
