# SPDX-License-Identifier: Apache-2.0
# Copyright (C) 2025 Intel Corporation
cmake_minimum_required(VERSION 3.5)
project(EmbodiedEnablekit VERSION 0.1.0 LANGUAGES CXX)

find_package(Eigen3 3.3 REQUIRED NO_MODULE)
find_package(OpenVINO REQUIRED)

# Add the subdirectory containing the shared library
set(ROOTDIR "/" CACHE PATH "Root directory.")

# Includes
find_path(
    PLCOPEN_CMAKE_MODULE_PATH
    NAMES plcopen_header.cmake
    HINTS ${ROOTDIR}/usr/include ${ROOTDIR}/usr/local/include
)
message(STATUS "PLCOPEN_CMAKE_MODULE_PATH: ${PLCOPEN_CMAKE_MODULE_PATH}")

include(${PLCOPEN_CMAKE_MODULE_PATH}/plcopen_header.cmake)
include(${PLCOPEN_CMAKE_MODULE_PATH}/plcopen_motion_deps.cmake)
include(${PLCOPEN_CMAKE_MODULE_PATH}/set_install_directories.cmake)
include(${PLCOPEN_CMAKE_MODULE_PATH}/find_rtmotion.cmake)
include(${PLCOPEN_CMAKE_MODULE_PATH}/find_enablekit.cmake)
include(${PLCOPEN_CMAKE_MODULE_PATH}/find_plcopen_servo.cmake)
include(${PLCOPEN_CMAKE_MODULE_PATH}/find_libshm.cmake)

include_directories(
    ${EIGEN3_INCLUDE_DIRS}
    ${OpenVINO_INCLUDE_DIRS}
)

add_subdirectory(mc)
add_subdirectory(examples)
