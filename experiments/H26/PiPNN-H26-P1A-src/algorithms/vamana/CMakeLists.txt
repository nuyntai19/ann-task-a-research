#add_executable(neighbors-vamana ../bench/neighborsTime.C)
#  target_link_libraries(neighbors-vamana PRIVATE parlay)
#  target_precompile_headers(neighbors-vamana PRIVATE neighbors.h)

# For iterating in CMake and for display/target names
set(CONFIG_DATATYPES_CMAKE INT8_T UINT8_T FLOAT_T)

set(CONFIG_DISTANCETYPES_CMAKE EUCLIDEAN MIPS)

# --- Loop through all combinations and create targets ---
foreach(CURRENT_DATATYPE_CMAKE ${CONFIG_DATATYPES_CMAKE})
    foreach(CURRENT_DISTANCETYPE_CMAKE ${CONFIG_DISTANCETYPES_CMAKE})
        # 1. Create a unique target name
        set(TARGET_NAME "neighbors-vamana_${CURRENT_DATATYPE_CMAKE}_${CURRENT_DISTANCETYPE_CMAKE}")

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

        target_link_libraries(${TARGET_NAME} PRIVATE parlay ParlayANN Eigen3::Eigen absl::synchronization absl::flat_hash_set)
        target_include_directories(${TARGET_NAME} PRIVATE ../bench)
        target_precompile_headers(${TARGET_NAME} PRIVATE neighbors.h)

        message(STATUS "Configured Target: ${TARGET_NAME} with Definitions: ${DATATYPE_DEFINE}, ${DISTANCETYPE_DEFINE}")
    endforeach()
endforeach()

