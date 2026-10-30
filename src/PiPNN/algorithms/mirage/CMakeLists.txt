set(CONFIG_DATATYPES_CMAKE INT8_T UINT8_T FLOAT_T)

set(CONFIG_DISTANCETYPES_CMAKE EUCLIDEAN MIPS)

foreach(CURRENT_DATATYPE_CMAKE ${CONFIG_DATATYPES_CMAKE})
    foreach(CURRENT_DISTANCETYPE_CMAKE ${CONFIG_DISTANCETYPES_CMAKE})
        if((CURRENT_DISTANCETYPE_CMAKE STREQUAL "MIPS") AND
            (CURRENT_DATATYPE_CMAKE STREQUAL "INT8_T" OR CURRENT_DATATYPE_CMAKE STREQUAL "UINT8_T"))
            message(STATUS "Skipping ${CURRENT_DATATYPE_CMAKE} with ${CURRENT_DISTANCETYPE_CMAKE}")
            continue()
        endif()

        set(TARGET_NAME "neighbors-mirage_${CURRENT_DATATYPE_CMAKE}_${CURRENT_DISTANCETYPE_CMAKE}")

        set(DATATYPE_DEFINE "USE_DATATYPE_${CURRENT_DATATYPE_CMAKE}") # e.g., USE_DATATYPE_INT8T
        set(DISTANCETYPE_DEFINE "USE_DISTANCE_${CURRENT_DISTANCETYPE_CMAKE}") # e.g., USE_DISTANCE_EUCLIDEAN

        add_executable(${TARGET_NAME} ../bench/neighborsTime.C)

        target_compile_definitions(${TARGET_NAME} PRIVATE
            ${DATATYPE_DEFINE}
            ${DISTANCETYPE_DEFINE}
        )

        target_link_libraries(${TARGET_NAME} PRIVATE parlay ParlayANN
          Eigen3::Eigen absl::synchronization absl::flat_hash_set
          absl::span hwy hwy_contrib faiss)
        target_include_directories(${TARGET_NAME} PRIVATE ../bench)
        target_precompile_headers(${TARGET_NAME} PRIVATE neighbors.h)

        message(STATUS "Configured Target: ${TARGET_NAME} with Definitions: ${DATATYPE_DEFINE}, ${DISTANCETYPE_DEFINE}")
    endforeach()
endforeach()
