# SPDX-License-Identifier: Apache-2.0
# Copyright (C) 2025 Intel Corporation

cmake_minimum_required(VERSION 3.5)

project(shmringbuf VERSION 0.1.0)

include(GNUInstallDirs)

# Default options
option(WITH_COBALT "Build on Xenomai" OFF)

# Default file directory path
set(XENOMAI_ROOT_DIR "/usr/xenomai" CACHE PATH "Root directory of Xenomai.")
set(XENO_BINDIR "${XENOMAI_ROOT_DIR}/bin" CACHE PATH "Bin directory of Xenomai.")

# Add Xenomai compile flags
if (WITH_COBALT)
  execute_process(COMMAND ${XENO_BINDIR}/xeno-config --skin posix --cc OUTPUT_VARIABLE XENO_CC OUTPUT_STRIP_TRAILING_WHITESPACE)
  execute_process(COMMAND ${XENO_BINDIR}/xeno-config --skin posix --cflags OUTPUT_VARIABLE XENO_CFLAGS OUTPUT_STRIP_TRAILING_WHITESPACE)
  execute_process(COMMAND ${XENO_BINDIR}/xeno-config --skin posix --auto-init-solib --ldflags OUTPUT_VARIABLE XENO_LDFLAGS OUTPUT_STRIP_TRAILING_WHITESPACE)
  set(CMAKE_CC "${CMAKE_CC} ${XENO_CC}")
  set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} ${XENO_CFLAGS}")
  set(CMAKE_EXE_LINKER_FLAGS "${CMAKE_SHARED_LINKER_FLAGS} ${XENO_LDFLAGS}")
  link_directories(${XENOMAI_ROOT_DIR}/lib)
endif()

message(STATUS "XENO_CC: ${XENO_CC}")
message(STATUS "XENO_CFLAGS: ${XENO_CFLAGS}")
message(STATUS "XENO_LDFLAGS: ${XENO_LDFLAGS}")

set(CMAKE_ARCHIVE_OUTPUT_DIRECTORY ${CMAKE_BINARY_DIR}/lib)
set(CMAKE_LIBRARY_OUTPUT_DIRECTORY ${CMAKE_BINARY_DIR}/lib)
set(CMAKE_RUNTIME_OUTPUT_DIRECTORY ${CMAKE_BINARY_DIR}/bin)

add_subdirectory (src)
add_subdirectory (test)


