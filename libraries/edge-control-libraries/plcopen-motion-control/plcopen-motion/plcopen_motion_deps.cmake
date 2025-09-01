# SPDX-License-Identifier: Apache-2.0
# Copyright (C) 2025 Intel Corporation
option(PLOT "Enable matplotlib c++" OFF)
option(TEST "Enable unit test" OFF)

# Find ruckig
find_package(ruckig REQUIRED)

# Find matplotlib
if(PLOT)
  add_definitions(-DPLOT)
  add_definitions(-DWITHOUT_NUMPY)

  find_package(PythonLibs REQUIRED)
  include_directories(
    ${PYTHON_INCLUDE_DIRS}
  )
  message(STATUS "PYTHON_INCLUDE_DIRS: ${PYTHON_INCLUDE_DIRS}")
  message(STATUS "PYTHON_LIBRARIES: ${PYTHON_LIBRARIES}")
endif(PLOT)

# Find GTEST
if(TEST)
  find_package(GTest REQUIRED)
  message(STATUS "GTEST_INCLUDE_DIRS: ${GTEST_INCLUDE_DIRS}")
  message(STATUS "GTEST_BOTH_LIBRARIES: ${GTEST_BOTH_LIBRARIES}")
  # Include gtest headers
  include_directories(
    ${GTEST_INCLUDE_DIRS}
  )
endif(TEST)