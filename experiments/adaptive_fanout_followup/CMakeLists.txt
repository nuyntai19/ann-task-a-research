cmake_minimum_required(VERSION 3.15)
project(PiPNNLocal LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS ON)
set(CMAKE_POSITION_INDEPENDENT_CODE ON)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)
if(NOT CMAKE_BUILD_TYPE)
  set(CMAKE_BUILD_TYPE Release CACHE STRING "Build type" FORCE)
endif()
add_compile_options(-march=native -ffast-math)

get_filename_component(ANN_REPO "${CMAKE_CURRENT_SOURCE_DIR}/../.." ABSOLUTE)
set(ANN_SOURCE "${CMAKE_CURRENT_SOURCE_DIR}/source")
set(LOCAL_DEPS "${ANN_REPO}/local_setup/khoa-linux/deps")
foreach(dep parlaylib eigen abseil-cpp highway)
  if(NOT EXISTS "${LOCAL_DEPS}/${dep}/CMakeLists.txt")
    message(FATAL_ERROR "Missing ${dep}. Run: bash ${CMAKE_CURRENT_SOURCE_DIR}/setup.sh")
  endif()
endforeach()

# Build only PiPNN and its actual dependencies. The source-only mirror has no
# R86 external/mirage tree, and PiPNN itself does not need Mirage/Faiss/BLAS.
set(PARLAY_TEST OFF CACHE BOOL "" FORCE)
set(PARLAY_EXAMPLES OFF CACHE BOOL "" FORCE)
set(PARLAY_BENCHMARK OFF CACHE BOOL "" FORCE)
add_subdirectory("${LOCAL_DEPS}/parlaylib" "deps/parlaylib" EXCLUDE_FROM_ALL)

add_library(Eigen3::Eigen INTERFACE IMPORTED)
set_target_properties(Eigen3::Eigen PROPERTIES
  INTERFACE_INCLUDE_DIRECTORIES "${LOCAL_DEPS}/eigen")

set(ABSL_PROPAGATE_CXX_STD ON CACHE BOOL "" FORCE)
set(ABSL_BUILD_TESTING OFF CACHE BOOL "" FORCE)
set(ABSL_ENABLE_INSTALL OFF CACHE BOOL "" FORCE)
add_subdirectory("${LOCAL_DEPS}/abseil-cpp" "deps/abseil-cpp" EXCLUDE_FROM_ALL)
set(HWY_ENABLE_TESTS OFF CACHE BOOL "" FORCE)
set(HWY_ENABLE_EXAMPLES OFF CACHE BOOL "" FORCE)
set(HWY_ENABLE_CONTRIB ON CACHE BOOL "" FORCE)
set(HWY_ENABLE_INSTALL OFF CACHE BOOL "" FORCE)
add_subdirectory("${LOCAL_DEPS}/highway" "deps/highway" EXCLUDE_FROM_ALL)

add_library(ParlayANN INTERFACE)
target_include_directories(ParlayANN INTERFACE "${ANN_SOURCE}/algorithms" "${CMAKE_CURRENT_SOURCE_DIR}")
# Reuse the original targets, feature definitions and precompiled header.
add_subdirectory("${ANN_SOURCE}/algorithms/PipNN" "algorithms/PipNN")

find_package(Python3 COMPONENTS Interpreter REQUIRED)
set(LATENCY_HEADERS "${CMAKE_CURRENT_BINARY_DIR}/generated/local_latency")
set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS
  "${CMAKE_CURRENT_SOURCE_DIR}/instrument_latency.py"
  "${ANN_SOURCE}/algorithms/utils/beamSearch.h"
  "${ANN_SOURCE}/algorithms/utils/check_nn_recall.h")
execute_process(
  COMMAND "${Python3_EXECUTABLE}" "${CMAKE_CURRENT_SOURCE_DIR}/instrument_latency.py"
    --source "${ANN_SOURCE}/algorithms/utils" --output "${LATENCY_HEADERS}"
  RESULT_VARIABLE LATENCY_PATCH_RESULT)
if(NOT LATENCY_PATCH_RESULT EQUAL 0)
  message(FATAL_ERROR "Failed to instrument the native query loop for latency")
endif()
add_executable(local_graph_recall evaluate.cc)
target_include_directories(local_graph_recall PRIVATE
  "${CMAKE_CURRENT_SOURCE_DIR}" "${CMAKE_CURRENT_BINARY_DIR}/generated"
  "${ANN_SOURCE}/algorithms/utils")
target_link_libraries(local_graph_recall PRIVATE parlay ParlayANN Eigen3::Eigen
  absl::synchronization absl::flat_hash_set absl::span hwy hwy_contrib)

option(PIPNN_BUILD_BEAM_RESCUE "Build the isolated Beam-Rescue tools" OFF)
if(PIPNN_BUILD_BEAM_RESCUE)
  add_subdirectory(../beam_rescue beam_rescue)
endif()
