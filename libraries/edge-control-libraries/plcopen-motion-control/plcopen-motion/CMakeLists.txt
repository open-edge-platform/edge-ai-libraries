# SPDX-License-Identifier: Apache-2.0
# Copyright (C) 2025 Intel Corporation
cmake_minimum_required(VERSION 3.10)
project(RTmotion VERSION 0.3.0 LANGUAGES CXX)

# Default options:
# - test subfolder
# - plcopen_motion_deps.cmake
#     option(PLOT "Enable matplotlib c++" OFF)
#     option(TEST "Enable unit test" OFF)
# - xenomai_flags.cmake
#     option(COBALT "Enable compiling with Xenomai" OFF)
#     set(XENOMAI_DIR "/usr/xenomai" CACHE PATH "Root directory of Xenomai.")
#     set(XENO_BINDIR "${XENOMAI_DIR}/bin" CACHE PATH "Root directory of Xenomai.")
# - time_benchmark.cmake
#    option(TIME "Record time stamps" OFF)

option(DEBUG "Enable debug print" OFF)
if(DEBUG)
  add_definitions(-DDEBUG)
endif(DEBUG)
option(ADDR_CHECK "Enable memory address check" OFF)
if(ADDR_CHECK)
  add_definitions(-DADDR_CHECK)
endif(ADDR_CHECK)
option(CACHE_MISS_CHECK "Enable cache miss check" OFF)
if(CACHE_MISS_CHECK)
  add_definitions(-DCACHE_MISS_CHECK)
endif(CACHE_MISS_CHECK)

option(SRC_BUILD "Build RTmotion from source code" ON)

# Includes
include(plcopen_header.cmake)
include(xenomai_flags.cmake)
include(plcopen_motion_deps.cmake)
include(set_install_directories.cmake)
include(find_tcc.cmake)

include_directories(
  library
  util
)

# Generate coverage infomation, only used in unit test
if(WITH_COV)
  SET(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} --coverage")
endif(WITH_COV)

add_subdirectory(library)
add_subdirectory(demo)
add_subdirectory(test)

INSTALL(FILES
  plcopen_header.cmake
  plcopen_motion_deps.cmake
  xenomai_flags.cmake
  set_install_directories.cmake
  find_rtmotion.cmake
  DESTINATION ${CMAKE_INSTALL_INCLUDEDIR}
)
