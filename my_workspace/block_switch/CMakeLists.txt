cmake_minimum_required(VERSION 3.10)
project(aac_lc_block_switch LANGUAGES C CXX)

get_filename_component(FDK_ROOT "${CMAKE_CURRENT_LIST_DIR}/../.." ABSOLUTE)

add_library(block_switch_native STATIC
  "${FDK_ROOT}/libAACenc/src/block_switch/block_switch.cpp"
  "${FDK_ROOT}/libSYS/src/genericStds.cpp")
target_include_directories(block_switch_native PUBLIC
  "${FDK_ROOT}/libAACenc/src"
  "${FDK_ROOT}/libFDK/include"
  "${FDK_ROOT}/libSYS/include")
target_compile_features(block_switch_native PUBLIC cxx_std_17)

add_library(block_switch_reference STATIC ref/ref_block_switch.cpp)
target_include_directories(block_switch_reference PUBLIC ref)
target_compile_features(block_switch_reference PUBLIC cxx_std_17)

add_executable(probe_block_switch
  tb/probe_block_switch.cpp "${FDK_ROOT}/wavreader.c")
target_include_directories(probe_block_switch PRIVATE "${FDK_ROOT}")
target_link_libraries(probe_block_switch PRIVATE block_switch_native)

add_executable(verify_block_switch tb/verify_block_switch.cpp)
target_link_libraries(verify_block_switch PRIVATE
  block_switch_native block_switch_reference)

if(UNIX)
  target_link_libraries(block_switch_reference PUBLIC m)
endif()
if(MSVC)
  target_compile_definitions(block_switch_reference PRIVATE _USE_MATH_DEFINES)
endif()

include(CTest)
if(BUILD_TESTING)
  add_test(NAME block_switch_reference_regression
    COMMAND verify_block_switch)
  add_test(NAME block_switch_silence_smoke
    COMMAND probe_block_switch --signal silence --frames 10)
  add_test(NAME block_switch_impulse_smoke
    COMMAND probe_block_switch --signal impulse --frames 10)
endif()
