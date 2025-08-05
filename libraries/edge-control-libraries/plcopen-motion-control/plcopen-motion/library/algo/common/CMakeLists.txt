# SPDX-License-Identifier: Apache-2.0
# Copyright (C) 2025 Intel Corporation
# Create RTmotion Algo Common library
set(SOURCE src/scurve_planner.cpp)
add_library(rtm_algo_com SHARED ${SOURCE})
set_target_properties(rtm_algo_com PROPERTIES VERSION "${${PROJECT_NAME}_VERSION}")
target_compile_options(rtm_algo_com PRIVATE -Wno-unused-parameter)

install(
  TARGETS rtm_algo_com
  LIBRARY DESTINATION ${CMAKE_INSTALL_LIBDIR}
)

install(
  DIRECTORY include/
  DESTINATION ${CMAKE_INSTALL_INCLUDEDIR}/algo/common/include
  FILES_MATCHING PATTERN "*.hpp"
)