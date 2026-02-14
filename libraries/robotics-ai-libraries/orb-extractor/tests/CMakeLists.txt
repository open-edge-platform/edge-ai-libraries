# Copyright (C) 2025 Intel Corporation
#
# SPDX-License-Identifier: Apache-2.0

# Simple, standalone test build - no install operations
cmake_minimum_required(VERSION 3.4)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED TRUE)
project (ORB_tests)

# Enable testing for standalone builds without main project
enable_testing()

# Option for building OpenCV-dependent tests
option(ENABLE_OPENCV_TESTS "Build tests that require full OpenCV (not OPENCV_FREE)" OFF)

# Option for OpenCV-free mode
option(OPENCV_FREE "Build in OpenCV-free mode with minimal OpenCV dependencies" OFF)

string(APPEND CMAKE_CXX_FLAGS " -fsycl -Wno-deprecated-declarations")

if(WIN32)
set(CMAKE_GENERATOR_TOOLSET "Intel(R) oneAPI DPC++ Compiler 2025")
set(CMAKE_CXX_FLAGS_RELEASE "-O3 /EHa")
else()
set(CMAKE_CXX_COMPILER icpx)
string(APPEND CMAKE_CXX_FLAGS " -fPIC")
endif()

if(DEFINED ENV{LD_LIBRARY_PATH})
  string(COMPARE EQUAL "$ENV{LD_LIBRARY_PATH}" "" RESULT)
  if (NOT RESULT)
    string(REPLACE ":" ";" SEARCH_LIB_PATH $ENV{LD_LIBRARY_PATH})
  endif()
endif()

find_package(GTest REQUIRED)
find_package(OpenCV 4.2 REQUIRED)

# Find Level Zero
find_library(L0_LIB_PATH
  NAMES ze_loader
  PATHS ${SEARCH_LIB_PATH})
find_library(ZE_LOADER
  NAMES ze_loader
  PATHS ${SEARCH_LIB_PATH})

include_directories (
   ${CMAKE_CURRENT_LIST_DIR}/../include
   ${CMAKE_CURRENT_LIST_DIR}/../src/sycl_utils/include
   ${CMAKE_CURRENT_LIST_DIR}/../src
)
###############
# OpenCV-free tests (always built)
add_executable(resizeTest src/ResizeTest.cpp)
target_compile_definitions(resizeTest PRIVATE OPENCV_FREE)
target_link_libraries(resizeTest GTest::gtest GTest::gtest_main "${CMAKE_CURRENT_LIST_DIR}/../build/libgpu_orb_ocvfree.so" ${OpenCV_LIBS} ${L0_LIB_PATH} )
add_test(NAME resize_test COMMAND resizeTest)

add_executable(opencvfreeTest src/OpencvfreeTest.cpp)
target_compile_definitions(opencvfreeTest PRIVATE OPENCV_FREE)
target_link_libraries(opencvfreeTest gtest_main GTest::gtest_main "${CMAKE_CURRENT_LIST_DIR}/../build/libgpu_orb_ocvfree.so" ${OpenCV_LIBS} ${ZE_LOADER})
add_test(NAME opencvfree_test COMMAND opencvfreeTest)

# OpenCV-dependent tests (only built when ENABLE_OPENCV_TESTS=ON)
if(ENABLE_OPENCV_TESTS)
    message(STATUS "Building OpenCV-dependent tests")
    
    add_executable(fastTest src/FastTest.cpp)
    target_link_libraries(fastTest GTest::gtest GTest::gtest_main "${CMAKE_CURRENT_LIST_DIR}/../build/libgpu_orb.so" ${OpenCV_LIBS} ${L0_LIB_PATH} )
    add_test(NAME fast_test COMMAND fastTest)
    
    add_executable(gaussTest src/GaussianTest.cpp)
    target_link_libraries(gaussTest GTest::gtest GTest::gtest_main "${CMAKE_CURRENT_LIST_DIR}/../build/libgpu_orb.so" ${OpenCV_LIBS} ${L0_LIB_PATH} )
    add_test(NAME gauss_test COMMAND gaussTest)
    
    add_executable(orbdescTest src/OrbDescriptorTest.cpp)
    target_link_libraries(orbdescTest GTest::gtest GTest::gtest_main "${CMAKE_CURRENT_LIST_DIR}/../build/libgpu_orb.so" ${OpenCV_LIBS} ${L0_LIB_PATH} )
    add_test(NAME orbdesc_test COMMAND orbdescTest)
    
    add_executable(stereoTest src/StereoTest.cpp)
    target_link_libraries(stereoTest GTest::gtest GTest::gtest_main "${CMAKE_CURRENT_LIST_DIR}/../build/libgpu_orb.so" ${OpenCV_LIBS} ${L0_LIB_PATH} )
    add_test(NAME stereo_test COMMAND stereoTest)
    
    add_executable(imagemaskTest src/ImagemaskTest.cpp)
    target_link_libraries(imagemaskTest GTest::gtest GTest::gtest_main "${CMAKE_CURRENT_LIST_DIR}/../build/libgpu_orb.so" ${OpenCV_LIBS} ${L0_LIB_PATH} )
    add_test(NAME imagemask_test COMMAND imagemaskTest)
    
    add_executable(rectmaskTest src/RectmaskTest.cpp)
    target_link_libraries(rectmaskTest GTest::gtest GTest::gtest_main "${CMAKE_CURRENT_LIST_DIR}/../build/libgpu_orb.so" ${OpenCV_LIBS} ${L0_LIB_PATH} )
    add_test(NAME rectmask_test COMMAND rectmaskTest)
    
    add_executable(multicameraTest src/MulticameraTest.cpp)
    target_link_libraries(multicameraTest GTest::gtest_main "${CMAKE_CURRENT_LIST_DIR}/../build/libgpu_orb.so" ${OpenCV_LIBS} ${L0_LIB_PATH} )
    add_test(NAME multicamera_test COMMAND multicameraTest)
    
    add_executable(multithreadTest src/MultithreadTest.cpp)
    target_link_libraries(multithreadTest GTest::gtest_main "${CMAKE_CURRENT_LIST_DIR}/../build/libgpu_orb.so" ${OpenCV_LIBS} ${ZE_LOADER})
    add_test(NAME multithread_test COMMAND multithreadTest)
else()
    message(STATUS "Skipping OpenCV-dependent tests (ENABLE_OPENCV_TESTS=OFF). These tests require full OpenCV support.")
endif()
###############

# Build fuzzers based on OpenCV mode
if(NOT OPENCV_FREE AND OpenCV_FOUND)
  # Full OpenCV fuzzer (existing)
  add_executable(fuzzer_stereo fuzzer/fuzzer_stereo.cpp)
  target_compile_definitions(fuzzer_stereo PRIVATE ORBLZE_KERNEL_PATH_STRING="/usr/lib/x86_64-linux-gnu") 
  # Link against full OpenCV version (not ocvfree) since fuzzer needs OpenCV
  target_link_libraries(fuzzer_stereo "${CMAKE_CURRENT_LIST_DIR}/../build/libgpu_orb.so" ${OpenCV_LIBS} ${L0_LIB_PATH})
  target_compile_options(fuzzer_stereo PRIVATE -fsanitize=fuzzer -fprofile-instr-generate -fcoverage-mapping -g)
  target_link_options(fuzzer_stereo PRIVATE -fsanitize=fuzzer)
  message(STATUS "Built fuzzer_stereo for full OpenCV mode")
elseif(OPENCV_FREE AND OpenCV_FOUND)  
  # OpenCV-free fuzzer (new)
  add_executable(fuzzer_opencv_free fuzzer/fuzzer_opencv_free.cpp)
  target_compile_definitions(fuzzer_opencv_free PRIVATE OPENCV_FREE ORBLZE_KERNEL_PATH_STRING="/usr/lib/x86_64-linux-gnu")
  # Link against OpenCV-free version
  target_link_libraries(fuzzer_opencv_free "${CMAKE_CURRENT_LIST_DIR}/../build/libgpu_orb_ocvfree.so" ${OpenCV_LIBS} ${L0_LIB_PATH})
  target_compile_options(fuzzer_opencv_free PRIVATE -fsanitize=fuzzer -fprofile-instr-generate -fcoverage-mapping -g)
  target_link_options(fuzzer_opencv_free PRIVATE -fsanitize=fuzzer)
  message(STATUS "Built fuzzer_opencv_free for OpenCV-free mode")
else()
  message(STATUS "Skipping fuzzer builds - OpenCV not found or conflicting OPENCV_FREE setting")
endif()
