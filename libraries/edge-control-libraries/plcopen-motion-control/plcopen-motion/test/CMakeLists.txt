# SPDX-License-Identifier: Apache-2.0
# Copyright (C) 2025 Intel Corporation
if(TEST)
  # Create scurve test executable
  add_executable(offline_scurve_test offline_scurve_test.cpp)
  target_link_libraries(offline_scurve_test
    rtm_algo_com
    rtm_algo_pub
    ${GTEST_BOTH_LIBRARIES}
    ${PYTHON_LIBRARIES}
    -lpthread
  )

  # Create scurve test executable
  add_executable(online_scurve_test online_scurve_test.cpp)
  target_link_libraries(online_scurve_test
    rtm_algo_com
    rtm_algo_pub
    ${GTEST_BOTH_LIBRARIES}
    ${PYTHON_LIBRARIES}
    -lpthread
  )

  # Create planner test executable
  add_executable(planner_test planner_test.cpp)
  target_link_libraries(planner_test
    rtm_algo_com
    rtm_algo_pub
    rtm_fb_com
    ${GTEST_BOTH_LIBRARIES}
    ${PYTHON_LIBRARIES}
    -lpthread
  )

  # Create function block test executable
  add_executable(function_block_test function_block_test.cpp)
  if(SRC_BUILD)
    target_link_libraries(function_block_test
      rtm_fb_com
      rtm_fb_pub
      rtm_fb_pri
      ${GTEST_BOTH_LIBRARIES}
      ${PYTHON_LIBRARIES}
      -lpthread
    )
  else()
    target_link_libraries(function_block_test
      rtm_fb_com
      rtm_fb_pub
      ${RTMOTION_FB_PRIVATE_LIBRARY}
      ${GTEST_BOTH_LIBRARIES}
      ${PYTHON_LIBRARIES}
      -lpthread
    )
  endif()

  # Create IO operation function block test executable
  add_executable(io_operation_test io_operation_test.cpp)
  if(SRC_BUILD)
    target_link_libraries(io_operation_test
      rtm_fb_com
      rtm_fb_pub
      rtm_fb_pri
      ${GTEST_BOTH_LIBRARIES}
      ${PYTHON_LIBRARIES}
      -lpthread
    )
  else()
    target_link_libraries(io_operation_test
      rtm_fb_com
      rtm_fb_pub
      ${RTMOTION_FB_PRIVATE_LIBRARY}
      ${GTEST_BOTH_LIBRARIES}
      ${PYTHON_LIBRARIES}
      -lpthread
    )
  endif()

  # Install test executables
  install(TARGETS offline_scurve_test online_scurve_test planner_test function_block_test io_operation_test
          RUNTIME DESTINATION ${INSTALL_BINDIR}
  )
endif(TEST)

if (FUZZ)
  cmake_minimum_required(VERSION 3.19)
  set(CMAKE_C_COMPILER "/usr/bin/clang")
  set(CMAKE_CXX_COMPILER "/usr/bin/clang++")
  set(CMAKE_BUILD_TYPE "RelWithDebug")

  # GoogleTest requires at least C++17
  set(CMAKE_CXX_STANDARD 17)
  set(FUZZTEST_FUZZING_MODE "on")
  add_subdirectory(fuzztest)
  enable_testing()
  include(GoogleTest)
  fuzztest_setup_fuzzing_flags()

  include_directories(../include)

  set(SRC ../src)
  include_directories(${SRC})

  add_executable(
    fuzz_algorithm
    test-algorithm_fuzztest.cpp
  )

  add_executable(
    fuzz_axis
    test-axis_fuzztest.cpp
  )

  add_executable(
    fuzz_fbs
    test-fbs_fuzztest.cpp
  )

  add_executable(
    fuzz_servo
    test-servo_fuzztest.cpp
  )

  target_link_libraries(fuzz_algorithm PRIVATE rtm_algo_com rtm_algo_pub rtm_fb_com -lpthread)
  target_link_libraries(fuzz_axis PRIVATE rtm_fb_com rtm_fb_pub -lpthread)
  if(SRC_BUILD)
    target_link_libraries(fuzz_fbs PRIVATE rtm_fb_com rtm_fb_pub rtm_fb_pri -lpthread)
  else()
    target_link_libraries(fuzz_fbs PRIVATE rtm_fb_com rtm_fb_pub ${RTMOTION_FB_PRIVATE_LIBRARY} -lpthread)
  endif()
  target_link_libraries(fuzz_servo PRIVATE rtm_fb_com -lpthread)

  link_fuzztest(fuzz_algorithm)
  link_fuzztest(fuzz_axis)
  link_fuzztest(fuzz_fbs)
  link_fuzztest(fuzz_servo)

  gtest_discover_tests(fuzz_algorithm)
  gtest_discover_tests(fuzz_axis)
  gtest_discover_tests(fuzz_fbs)
  gtest_discover_tests(fuzz_servo)

endif(FUZZ)
