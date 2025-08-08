# SPDX-License-Identifier: Apache-2.0
# Copyright (C) 2025 Intel Corporation
cmake_minimum_required(VERSION 3.5)
#project(OpenCVFuzzing)

set(CMAKE_C_COMPILER "/usr/bin/clang")
set(CMAKE_CXX_COMPILER "/usr/bin/clang++")

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED TRUE)

find_library(L0_LIB_PATH
  NAMES ze_loader
  PATHS ${SEARCH_LIB_PATH})
if(NOT L0_LIB_PATH)
  message(FATAL_ERROR
    "Level Zero loader is not found. "
    "You may need to install oneAPI Level Zero loader to fix this issue.")
else()
  message(STATUS
    "Level Zero loader is found at ${L0_LIB_PATH}")
endif()

# Find OpenCV package
find_package(OpenCV REQUIRED)

include_directories (
   ${CMAKE_CURRENT_LIST_DIR}/../../include
   ${CMAKE_CURRENT_LIST_DIR}/../../src
)


set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -fprofile-instr-generate -fcoverage-mapping -g")

add_executable(fuzzer_stereo fuzzer_stereo.cpp)
target_link_libraries(fuzzer_stereo "${CMAKE_CURRENT_LIST_DIR}/../../build/libgpu_orb.so" ${OpenCV_LIBS} ${L0_LIB_PATH})

# Enable libFuzzer
target_compile_options(fuzzer_stereo PRIVATE -fsanitize=fuzzer)
target_link_options(fuzzer_stereo PRIVATE -fsanitize=fuzzer)
