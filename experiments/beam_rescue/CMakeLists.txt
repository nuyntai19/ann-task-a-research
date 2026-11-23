set(RESCUE_NATIVE "${CMAKE_CURRENT_SOURCE_DIR}/../adaptive_fanout_followup/source/algorithms/utils")
find_package(Python3 REQUIRED COMPONENTS Interpreter)
set(RESCUE_OUT "${CMAKE_CURRENT_BINARY_DIR}/generated")
set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS
  "${CMAKE_CURRENT_SOURCE_DIR}/generate.py" "${RESCUE_NATIVE}/beamSearch.h"
  "${RESCUE_NATIVE}/check_nn_recall.h")
execute_process(COMMAND "${Python3_EXECUTABLE}" "${CMAKE_CURRENT_SOURCE_DIR}/generate.py"
  "${RESCUE_NATIVE}" "${RESCUE_OUT}" COMMAND_ERROR_IS_FATAL ANY)
add_executable(beam_rescue_mine mine.cc)
add_executable(beam_rescue_eval ../adaptive_fanout_followup/evaluate.cc)
foreach(target beam_rescue_mine beam_rescue_eval)
  target_include_directories(${target} PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}"
    "${RESCUE_OUT}" "${RESCUE_NATIVE}" "${CMAKE_CURRENT_SOURCE_DIR}/../adaptive_fanout_followup")
  target_link_libraries(${target} PRIVATE parlay ParlayANN Eigen3::Eigen
    absl::synchronization absl::flat_hash_set absl::span)
endforeach()
