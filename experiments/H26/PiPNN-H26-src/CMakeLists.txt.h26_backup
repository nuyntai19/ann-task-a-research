cmake_minimum_required(VERSION 3.15)
project(ParlayANN VERSION 1
        DESCRIPTION "ParlayANN is a library of approximate nearest neighbor search algorithms, along with a set of useful tools for designing such algorithms. It is written in C++ and uses parallel primitives from ParlayLib. Currently it includes implementations of the ANNS algorithms DiskANN, HNSW, HCNNG, and pyNNDescent."
        LANGUAGES CXX)

include(CheckCXXCompilerFlag)
include (FetchContent)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS ON)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

set(CMAKE_POSITION_INDEPENDENT_CODE TRUE)
set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -march=native -ffast-math")

FetchContent_Declare(parlaylib
  GIT_REPOSITORY  https://github.com/cmuparlay/parlaylib.git
  GIT_TAG         master
)
FetchContent_GetProperties(parlaylib)
if(NOT parlaylib_POPULATED)
  FetchContent_Populate(parlaylib)  
  add_subdirectory(${parlaylib_SOURCE_DIR} EXCLUDE_FROM_ALL)
endif()

FetchContent_Declare(Eigen
  GIT_REPOSITORY https://gitlab.com/libeigen/eigen.git
  GIT_TAG 3.4.0
)
FetchContent_MakeAvailable(Eigen)

FetchContent_Declare(abseil-cpp
  GIT_REPOSITORY  https://github.com/abseil/abseil-cpp.git
  GIT_TAG         20250512.0
)
FetchContent_MakeAvailable(abseil-cpp)

include(FetchContent)
FetchContent_Declare(highway
  GIT_REPOSITORY  https://github.com/google/highway/
  GIT_TAG         master
)
FetchContent_MakeAvailable(highway)

# Disable the Google Benchmark requirement on Google Test
set(BENCHMARK_ENABLE_TESTING NO)
FetchContent_Declare(googlebenchmark
    GIT_REPOSITORY "https://github.com/google/benchmark.git"
    GIT_TAG origin/main
)
FetchContent_MakeAvailable(googlebenchmark)

# Set module path
list(APPEND CMAKE_MODULE_PATH "${ParlayANN_SOURCE_DIR}/cmake")


add_library(ParlayANN INTERFACE)
set(ParlayANN_INCLUDE_DIR "${ParlayANN_SOURCE_DIR}/algorithms")
target_include_directories(ParlayANN INTERFACE
  $<BUILD_INTERFACE:${ParlayANN_INCLUDE_DIR}>
  $<INSTALL_INTERFACE:${CMAKE_INSTALL_INCLUDEDIR}>)

add_library(hnswlib INTERFACE)
target_include_directories(hnswlib INTERFACE
  ${CMAKE_CURRENT_SOURCE_DIR}/external/hnswlib
)
target_compile_features(hnswlib INTERFACE cxx_std_17)

set(FAISS_ENABLE_GPU OFF CACHE BOOL "" FORCE)
set(FAISS_ENABLE_RAFT OFF CACHE BOOL "" FORCE)
set(FAISS_ENABLE_PYTHON OFF CACHE BOOL "" FORCE)
set(FAISS_ENABLE_C_API OFF CACHE BOOL "" FORCE)
set(BUILD_TESTING OFF CACHE BOOL "" FORCE)
set(HWY_ENABLE_TESTS OFF CACHE BOOL "" FORCE)
set(BENCHMARK_ENABLE_TESTING OFF CACHE BOOL "" FORCE)
set(BENCHMARK_ENABLE_GTEST_TESTS OFF CACHE BOOL "" FORCE)
add_subdirectory(external/mirage)

add_subdirectory(algorithms)
add_subdirectory(analysis)
add_subdirectory(benchmark)
add_subdirectory(data_tools)
#add_subdirectory(range_search)


