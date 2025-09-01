# SPDX-License-Identifier: Apache-2.0
# Copyright (C) 2025 Intel Corporation
# Find plcopen-servo
find_library(
  SERVO_LIBRARIES
  NAMES plcopen_servo
  HINTS ${ROOTDIR}/usr/lib ${ROOTDIR}/usr/local/lib)
find_path(
  SERVO_INCLUDE_DIRS 
  NAMES ecrt_servo.hpp
  HINTS ${ROOTDIR}/usr/include ${ROOTDIR}/usr/local/include)
if (NOT SERVO_LIBRARIES)
  message(ERROR " SERVO library not found under: ${ROOTDIR}/usr/lib ${ROOTDIR}/usr/local/lib")
endif()
if (NOT SERVO_INCLUDE_DIRS)
  message(ERROR " SERVO headers not found under: ${ROOTDIR}/usr/include ${ROOTDIR}/usr/local/include")
endif()
message(STATUS "SERVO_INCLUDE_DIRS: ${SERVO_INCLUDE_DIRS}")
message(STATUS "SERVO_LIBRARIES: ${SERVO_LIBRARIES}")

# Include servo headers
include_directories(
  ${SERVO_INCLUDE_DIRS}
)

# Find symg_servo
find_library(
    SYMG_SERVO_LIBRARIES
    NAMES plcopen_servo_symg
    HINTS ${ROOTDIR}/usr/lib ${ROOTDIR}/usr/local/lib)
find_path(
    SYMG_SERVO_INCLUDE_DIRS 
    NAMES symg_servo.hpp
    HINTS ${ROOTDIR}/usr/include ${ROOTDIR}/usr/local/include)
if (NOT SYMG_SERVO_LIBRARIES)
    message(ERROR " SERVO library not found under: ${ROOTDIR}/usr/lib ${ROOTDIR}/usr/local/lib")
endif()
if (NOT SYMG_SERVO_INCLUDE_DIRS)
    message(ERROR " SERVO headers not found under: ${ROOTDIR}/usr/include ${ROOTDIR}/usr/local/include")
endif()
message(STATUS "SYMG_SERVO_LIBRARIES: ${SYMG_SERVO_LIBRARIES}")
message(STATUS "SYMG_SERVO_INCLUDE_DIRS: ${SYMG_SERVO_INCLUDE_DIRS}")

# Include ighethercat headers
include_directories(
    ${SYMG_SERVO_INCLUDE_DIRS}
)