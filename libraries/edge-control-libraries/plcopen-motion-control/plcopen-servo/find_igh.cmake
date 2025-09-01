# SPDX-License-Identifier: Apache-2.0
# Copyright (C) 2025 Intel Corporation
# Find ighethercat
if(COBALT)
find_library(
    ETHERCAT_LIBRARIES
    NAMES ethercat_rtdm
    HINTS ${ROOTDIR}/usr/lib ${ROOTDIR}/usr/local/lib)
else()
find_library(
    ETHERCAT_LIBRARIES
    NAMES ethercat
    HINTS ${ROOTDIR}/usr/include ${ROOTDIR}/usr/local/include)
endif(COBALT)
find_path(
    ETHERCAT_INCLUDE_DIRS 
    NAMES ecrt.h
    HINTS ${ETHERCAT_HEADERDIR})
if (NOT ETHERCAT_LIBRARIES)
    message(ERROR " ETHERCAT library not found under: ${ROOTDIR}/usr/lib ${ROOTDIR}/usr/local/lib")
endif()
if (NOT ETHERCAT_INCLUDE_DIRS)
    message(ERROR " ETHERCAT headers not found under: ${ROOTDIR}/usr/include ${ROOTDIR}/usr/local/include")
endif()
message(STATUS "ETHERCAT_INCLUDE_DIRS: ${ETHERCAT_INCLUDE_DIRS}")
message(STATUS "ETHERCAT_LIBRARIES: ${ETHERCAT_LIBRARIES}")

include_directories(
    ${ETHERCAT_INCLUDE_DIRS}
)