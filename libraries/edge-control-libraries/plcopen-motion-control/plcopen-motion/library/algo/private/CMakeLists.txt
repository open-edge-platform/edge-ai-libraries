# SPDX-License-Identifier: Apache-2.0
# Copyright (C) 2025 Intel Corporation
if(SRC_BUILD)
  set(SOURCE
    src/line_planner.cpp
    src/poly_five_planner.cpp
  )
  add_library(rtm_algo_pri SHARED ${SOURCE})
  set_target_properties(rtm_algo_pri PROPERTIES VERSION "${${PROJECT_NAME}_VERSION}")
  target_link_libraries(rtm_algo_pri rtm_algo_com)
  add_dependencies(rtm_algo_pri rtm_algo_com)

  install(
    TARGETS rtm_algo_pri
    LIBRARY DESTINATION ${CMAKE_INSTALL_LIBDIR}
  )
else()
  find_library(
    RTMOTION_ALGO_PRIVATE_LIBRARY
    NAMES rtm_algo_pri
    HINTS ${CMAKE_CURRENT_SOURCE_DIR}
  )
  if (NOT RTMOTION_ALGO_PRIVATE_LIBRARY)
    message(ERROR " RTmotion private algo library not found under: ${CMAKE_CURRENT_SOURCE_DIR}")
  endif()
  message(STATUS "RTMOTION_ALGO_PRIVATE_LIBRARY: ${RTMOTION_ALGO_PRIVATE_LIBRARY}")

  INSTALL(FILES
    librtm*
    DESTINATION ${CMAKE_INSTALL_LIBDIR}
  )
endif()

install(
  DIRECTORY include/
  DESTINATION ${CMAKE_INSTALL_INCLUDEDIR}/algo/private/include
  FILES_MATCHING PATTERN "*.hpp"
)

