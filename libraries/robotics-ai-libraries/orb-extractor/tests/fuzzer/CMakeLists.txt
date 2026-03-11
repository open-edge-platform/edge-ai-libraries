# Copyright (C) 2025 Intel Corporation
#
# SPDX-License-Identifier: Apache-2.0

cmake_minimum_required(VERSION 3.4)
set(CMAKE_CXX_STANDARD 17) 
set(CMAKE_CXX_STANDARD_REQUIRED TRUE)
project(ORB_fuzzers)

# Find OpenCV
find_package(OpenCV 4.2 REQUIRED)

# Include directories  
include_directories(
   ${CMAKE_CURRENT_LIST_DIR}/../include
   ${CMAKE_CURRENT_LIST_DIR}/../src
)

# Create a simple fuzzer without complex SYCL linking
# Test basic API surface without GPU acceleration
set(CMAKE_CXX_FLAGS "-std=c++17 -O1 -g -fsanitize=fuzzer")

# Simple OpenCV-free API fuzzer - tests input validation
add_executable(simple_fuzzer_opencv_free simple_fuzzer_opencv_free.cpp)
target_compile_definitions(simple_fuzzer_opencv_free PRIVATE OPENCV_FREE)
target_link_libraries(simple_fuzzer_opencv_free ${OpenCV_LIBS})

# Simple OpenCV API fuzzer - tests input validation  
add_executable(simple_fuzzer_opencv simple_fuzzer_opencv.cpp)
target_link_libraries(simple_fuzzer_opencv ${OpenCV_LIBS})