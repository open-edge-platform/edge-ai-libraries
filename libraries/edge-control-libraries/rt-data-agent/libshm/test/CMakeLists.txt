# SPDX-License-Identifier: Apache-2.0
# Copyright (C) 2025 Intel Corporation

set(THREADS_PREFER_PTHREAD_FLAG true)
find_package(Threads REQUIRED)

add_executable(shm_test shm_test.c)
add_executable(rt2nonrt_test rt2nonrt_test.c)
add_executable(sim_rt_send sim_rt_send.c)

target_link_libraries(shm_test
  PRIVATE
  ${PROJECT_NAME}
)
target_link_libraries(rt2nonrt_test
  PRIVATE
  ${PROJECT_NAME}
  Threads::Threads
)
target_link_libraries(sim_rt_send
  PRIVATE
  ${PROJECT_NAME}
  Threads::Threads
)

if(NOT INSTALL_BINDIR)
  set(INSTALL_BINDIR ${CMAKE_INSTALL_BINDIR})
endif()

install(TARGETS sim_rt_send
  RUNTIME DESTINATION ${INSTALL_BINDIR}
)

if(INSTALL_TESTS)
  install(TARGETS shm_test rt2nonrt_test
    RUNTIME DESTINATION ${INSTALL_BINDIR}
  )
endif()

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

  set(SRC ../src)
  include_directories(${SRC})

  add_executable(
    fuzz_libshm
    test-libshm_fuzztest.cpp
    ${SRC}/shmringbuf.c
  )

  target_link_libraries(fuzz_libshm PRIVATE safestring_shared)

  link_fuzztest(fuzz_libshm)

  gtest_discover_tests(fuzz_libshm)

endif(FUZZ)

