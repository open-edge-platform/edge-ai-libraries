# SPDX-License-Identifier: Apache-2.0
# Copyright (C) 2025 Intel Corporation
# Find ecat_enablekit
find_library(
  ENABLEKIT_LIBRARIES
  NAMES ecat
  HINTS ${ROOTDIR}/usr/lib ${ROOTDIR}/usr/local/lib)
find_path(
  ENABLEKIT_INCLUDE_DIRS 
  NAMES motionentry.h
  HINTS ${ROOTDIR}/usr/include ${ROOTDIR}/usr/local/include)
if (NOT ENABLEKIT_INCLUDE_DIRS)
  message(ERROR " ENABLEKIT headers not found under: ${ROOTDIR}/usr/include ${ROOTDIR}/usr/local/include")
endif()
if (NOT ENABLEKIT_LIBRARIES)
  message(ERROR " ENABLEKIT library not found under: ${ROOTDIR}/usr/lib ${ROOTDIR}/usr/local/lib")
endif()
message(STATUS "ENABLEKIT_INCLUDE_DIRS: ${ENABLEKIT_INCLUDE_DIRS}")
message(STATUS "ENABLEKIT_LIBRARIES: ${ENABLEKIT_LIBRARIES}")

include_directories(
  ${ENABLEKIT_INCLUDE_DIRS}
)