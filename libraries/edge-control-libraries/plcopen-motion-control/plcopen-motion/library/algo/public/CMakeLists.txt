# SPDX-License-Identifier: Apache-2.0
# Copyright (C) 2025 Intel Corporation
set(SOURCE
  src/offline_scurve_planner.cpp
  src/online_scurve_planner.cpp
  src/ruckig_planner.cpp
#   src/time_optimal_trajectory_generation.cpp
#   src/trajectory.cpp
)
add_library(rtm_algo_pub SHARED ${SOURCE})
set_target_properties(rtm_algo_pub PROPERTIES VERSION "${${PROJECT_NAME}_VERSION}")
target_compile_options(rtm_algo_pub PRIVATE -Wno-unused-variable)
target_link_libraries(rtm_algo_pub rtm_algo_com ruckig::ruckig)
add_dependencies(rtm_algo_pub rtm_algo_com ruckig::ruckig)

install(
  DIRECTORY include/
  DESTINATION ${CMAKE_INSTALL_INCLUDEDIR}/algo/public/include
  FILES_MATCHING PATTERN "*.hpp"
)

install(
  TARGETS rtm_algo_pub
  LIBRARY DESTINATION ${CMAKE_INSTALL_LIBDIR}
)