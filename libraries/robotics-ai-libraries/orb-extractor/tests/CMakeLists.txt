# SPDX-License-Identifier: Apache-2.0
# Copyright (C) 2025 Intel Corporation
cmake_minimum_required(VERSION 3.4)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED TRUE)
project (ORB_tests)
include(CTest)
if (CMAKE_VERSION VERSION_LESS 3.2)
    set(UPDATE_DISCONNECTED_IF_AVAILABLE "")
else()
    set(UPDATE_DISCONNECTED_IF_AVAILABLE "UPDATE_DISCONNECTED 1")
endif()

if(DEFINED ENV{LD_LIBRARY_PATH})
  string(COMPARE EQUAL "$ENV{LD_LIBRARY_PATH}" "" RESULT)
  if (NOT RESULT)
    string(REPLACE ":" ";" SEARCH_LIB_PATH $ENV{LD_LIBRARY_PATH})
  endif()
endif()

find_package(GTest REQUIRED)

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

add_subdirectory(fuzzer)

set_property(TARGET PROPERTY CXX_STANDARD 11)
find_package(OpenCV 4.2 REQUIRED)

include_directories (
   ${CMAKE_CURRENT_LIST_DIR}/../include
   ${CMAKE_CURRENT_LIST_DIR}/../src
)
###############
add_executable(gaussTest src/GaussianTest.cpp)
target_link_libraries(gaussTest GTest::gtest GTest::gtest_main "${CMAKE_CURRENT_LIST_DIR}/../build/libgpu_orb.so" ${OpenCV_LIBS} ${L0_LIB_PATH} )
add_test(gauss_test COMMAND gaussTest)
###############
add_executable(resizeTest src/ResizeTest.cpp)
target_link_libraries(resizeTest GTest::gtest GTest::gtest_main "${CMAKE_CURRENT_LIST_DIR}/../build/libgpu_orb.so" ${OpenCV_LIBS} ${L0_LIB_PATH} )
add_test(resize_test COMMAND resizeTest)
###############
add_executable(orbdescTest src/OrbDescriptorTest.cpp)
target_compile_definitions(orbdescTest PRIVATE -DOPENCV_BUILD)
target_link_libraries(orbdescTest GTest::gtest GTest::gtest_main "${CMAKE_CURRENT_LIST_DIR}/../build/libgpu_orb.so" ${OpenCV_LIBS} ${L0_LIB_PATH} )
add_test(orbdesc_test COMMAND orbdescTest)
###############
add_executable(fastTest src/FastTest.cpp)
target_compile_definitions(fastTest PRIVATE -DOPENCV_BUILD)
target_link_libraries(fastTest GTest::gtest GTest::gtest_main "${CMAKE_CURRENT_LIST_DIR}/../build/libgpu_orb.so" ${OpenCV_LIBS} ${L0_LIB_PATH} )
add_test(fastext_test COMMAND fastTest)
###############
add_executable(stereoTest src/StereoTest.cpp)
target_compile_definitions(stereoTest PRIVATE -DOPENCV_BUILD)
target_link_libraries(stereoTest GTest::gtest GTest::gtest_main "${CMAKE_CURRENT_LIST_DIR}/../build/libgpu_orb.so" ${OpenCV_LIBS} ${L0_LIB_PATH} )
add_test(stereo_test COMMAND stereoTest)
###############
add_executable(multicameraTest src/MulticameraTest.cpp)
target_compile_definitions(multicameraTest PRIVATE -DOPENCV_BUILD)
target_link_libraries(multicameraTest gtest_main GTest::gtest_main "${CMAKE_CURRENT_LIST_DIR}/../build/libgpu_orb.so" ${OpenCV_LIBS} ${L0_LIB_PATH} )
add_test(multicamera_test COMMAND multicameraTest)
###############
add_executable(multithreadTest src/MultithreadTest.cpp)
target_compile_definitions(multithreadTest PRIVATE -DOPENCV_BUILD)
target_link_libraries(multithreadTest gtest_main GTest::gtest_main "${CMAKE_CURRENT_LIST_DIR}/../build/libgpu_orb.so" ${OpenCV_LIBS} ${ZE_LOADER})
add_test(multithread_test COMMAND multithreadTest)
###############
add_executable(opencvfreeTest src/OpencvfreeTest.cpp)
target_compile_definitions(opencvfreeTest PRIVATE -DOPENCV_FREE)
target_link_libraries(opencvfreeTest gtest_main GTest::gtest_main "${CMAKE_CURRENT_LIST_DIR}/../build/libgpu_orb_ocvfree.so" ${OpenCV_LIBS} ${ZE_LOADER})
add_test(opencvfree_test COMMAND opencvfreeTest)

set_property(TARGET ${NAME} PROPERTY INSTALL_RPATH_USE_LINK_PATH TRUE)
