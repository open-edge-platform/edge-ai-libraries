# SPDX-License-Identifier: Apache-2.0
# Copyright (C) 2025 Intel Corporation
# Find RTmotion
find_library(
  RTMOTION_ALGO_COMMON_LIBRARY
  NAMES rtm_algo_com
  HINTS ${ROOTDIR}/usr/lib ${ROOTDIR}/usr/local/lib
)
if (NOT RTMOTION_ALGO_COMMON_LIBRARY)
  message(ERROR " RTmotion library not found under: ${ROOTDIR}/usr/lib ${ROOTDIR}/usr/local/lib")
endif()
message(STATUS "RTMOTION_ALGO_COMMON_LIBRARY: ${RTMOTION_ALGO_COMMON_LIBRARY}")

find_library(
  RTMOTION_ALGO_PUBLIC_LIBRARY
  NAMES rtm_algo_pub
  HINTS ${ROOTDIR}/usr/lib ${ROOTDIR}/usr/local/lib
)
if (NOT RTMOTION_ALGO_PUBLIC_LIBRARY)
  message(ERROR " RTmotion library not found under: ${ROOTDIR}/usr/lib ${ROOTDIR}/usr/local/lib")
endif()
message(STATUS "RTMOTION_ALGO_PUBLIC_LIBRARY: ${RTMOTION_ALGO_PUBLIC_LIBRARY}")

find_library(
  RTMOTION_ALGO_PRIVATE_LIBRARY
  NAMES rtm_algo_pri
  HINTS ${ROOTDIR}/usr/lib ${ROOTDIR}/usr/local/lib
)
if (NOT RTMOTION_ALGO_PRIVATE_LIBRARY)
  message(ERROR " RTmotion library not found under: ${ROOTDIR}/usr/lib ${ROOTDIR}/usr/local/lib")
endif()
message(STATUS "RTMOTION_ALGO_PRIVATE_LIBRARY: ${RTMOTION_ALGO_PRIVATE_LIBRARY}")

find_library(
  RTMOTION_FB_COMMON_LIBRARY
  NAMES rtm_fb_com
  HINTS ${ROOTDIR}/usr/lib ${ROOTDIR}/usr/local/lib
)
if (NOT RTMOTION_FB_COMMON_LIBRARY)
  message(ERROR " RTmotion library not found under: ${ROOTDIR}/usr/lib ${ROOTDIR}/usr/local/lib")
endif()
message(STATUS "RTMOTION_FB_COMMON_LIBRARY: ${RTMOTION_FB_COMMON_LIBRARY}")

find_library(
  RTMOTION_FB_PUBLIC_LIBRARY
  NAMES rtm_fb_pub
  HINTS ${ROOTDIR}/usr/lib ${ROOTDIR}/usr/local/lib
)
if (NOT RTMOTION_FB_PUBLIC_LIBRARY)
  message(ERROR " RTmotion library not found under: ${ROOTDIR}/usr/lib ${ROOTDIR}/usr/local/lib")
endif()
message(STATUS "RTMOTION_FB_PUBLIC_LIBRARY: ${RTMOTION_FB_PUBLIC_LIBRARY}")

find_library(
  RTMOTION_FB_PRIVATE_LIBRARY
  NAMES rtm_fb_pri
  HINTS ${ROOTDIR}/usr/lib ${ROOTDIR}/usr/local/lib
)
if (NOT RTMOTION_FB_PRIVATE_LIBRARY)
  message(ERROR " RTmotion library not found under: ${ROOTDIR}/usr/lib ${ROOTDIR}/usr/local/lib")
endif()
message(STATUS "RTMOTION_FB_PRIVATE_LIBRARY: ${RTMOTION_FB_PRIVATE_LIBRARY}")

SET(RTMOTION_LIBRARIES
  ${RTMOTION_ALGO_COMMON_LIBRARY}
  ${RTMOTION_ALGO_PUBLIC_LIBRARY}
  ${RTMOTION_ALGO_PRIVATE_LIBRARY}
  ${RTMOTION_FB_COMMON_LIBRARY}
  ${RTMOTION_FB_PUBLIC_LIBRARY}
  ${RTMOTION_FB_PRIVATE_LIBRARY}
)
message(STATUS "RTMOTION_LIBRARIES: ${RTMOTION_LIBRARIES}")

find_path(
  RTMOTION_INCLUDE_DIRS 
  NAMES algo fb
  HINTS ${ROOTDIR}/usr/include ${ROOTDIR}/usr/local/include)
if (NOT RTMOTION_INCLUDE_DIRS)
  message(ERROR " RTMOTION headers not found under:${ROOTDIR}/usr/include ${ROOTDIR}/usr/local/include")
endif()
message(STATUS "RTMOTION_INCLUDE_DIRS: ${RTMOTION_INCLUDE_DIRS}")

include_directories(
  ${RTMOTION_INCLUDE_DIRS}
)