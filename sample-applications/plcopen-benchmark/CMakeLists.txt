# SPDX-License-Identifier: Apache-2.0
# Copyright (C) 2025 Intel Corporation
cmake_minimum_required(VERSION 3.5)
project(plcopen_benchmark VERSION 0.1.0 LANGUAGES CXX)

# Default options
set(ROOTDIR "/" CACHE PATH "Root directory.")
# - plcopen_motion_deps.cmake
#     option(PLOT "Enable matplotlib c++" OFF)
# - xenomai_flags.cmake
#     option(COBALT "Enable compiling with Xenomai" OFF)
#     set(XENOMAI_DIR "/usr/xenomai" CACHE PATH "Root directory of Xenomai.")
#     set(XENO_BINDIR "${XENOMAI_DIR}/bin" CACHE PATH "Root directory of Xenomai.")

# Includes
find_path(
  PLCOPEN_CMAKE_MODULE_PATH
  NAMES plcopen_header.cmake
  HINTS ${ROOTDIR}/usr/include ${ROOTDIR}/usr/local/include
)
message(STATUS "PLCOPEN_CMAKE_MODULE_PATH: ${PLCOPEN_CMAKE_MODULE_PATH}")

include(${PLCOPEN_CMAKE_MODULE_PATH}/plcopen_header.cmake)
include(${PLCOPEN_CMAKE_MODULE_PATH}/plcopen_motion_deps.cmake)
include(${PLCOPEN_CMAKE_MODULE_PATH}/xenomai_flags.cmake)
include(${PLCOPEN_CMAKE_MODULE_PATH}/set_install_directories.cmake)
include(${PLCOPEN_CMAKE_MODULE_PATH}/find_rtmotion.cmake)
include(${PLCOPEN_CMAKE_MODULE_PATH}/find_igh.cmake)
include(${PLCOPEN_CMAKE_MODULE_PATH}/find_enablekit.cmake)
include(${PLCOPEN_CMAKE_MODULE_PATH}/find_plcopen_servo.cmake)

# Include headers
include_directories(include)

add_subdirectory(src)
add_subdirectory(test)

install(
  DIRECTORY include/
  DESTINATION ${CMAKE_INSTALL_INCLUDEDIR}
)

INSTALL(FILES
  plot_histogram.py
  plot_time_series.py
  setup_pmu.sh
  DESTINATION ${INSTALL_BINDIR}
)
