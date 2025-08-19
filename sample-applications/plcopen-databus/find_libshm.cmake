# SPDX-License-Identifier: Apache-2.0
# Copyright (C) 2025 Intel Corporation
# Find shmringbuf
find_library(
  LIBSHM_LIBRARIES
  NAMES shmringbuf
  HINTS ${ROOTDIR}/usr/lib ${ROOTDIR}/usr/local/lib)
find_path(
  LIBSHM_INCLUDE_DIRS 
  NAMES shmringbuf.h
  HINTS ${ROOTDIR}/usr/include ${ROOTDIR}/usr/local/include)
if (NOT LIBSHM_LIBRARIES)
  message(ERROR " Shared memory library not found under: ${ROOTDIR}/usr/lib ${ROOTDIR}/usr/local/lib")
endif()
if (NOT LIBSHM_INCLUDE_DIRS)
  message(ERROR " SERVO headers not found under: ${ROOTDIR}/usr/include ${ROOTDIR}/usr/local/include")
endif()
message(STATUS "LIBSHM_INCLUDE_DIRS: ${LIBSHM_INCLUDE_DIRS}")
message(STATUS "LIBSHM_LIBRARIES: ${LIBSHM_LIBRARIES}")

include_directories(
  ${LIBSHM_INCLUDE_DIRS}
)