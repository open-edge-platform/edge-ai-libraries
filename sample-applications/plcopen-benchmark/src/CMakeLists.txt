# SPDX-License-Identifier: Apache-2.0
# Copyright (C) 2025 Intel Corporation
# Add source files
set(SOURCE break_trace.cpp perf_event_count.cpp)

# Create "servo" library
add_library(${PROJECT_NAME}_tool SHARED ${SOURCE})
set_target_properties(${PROJECT_NAME}_tool PROPERTIES VERSION "${${PROJECT_NAME}_VERSION}")
target_link_libraries(${PROJECT_NAME}_tool
  ${RTMOTION_LIBRARIES}
  ${SERVO_LIBRARIES}
  ${ENABLEKIT_LIBRARIES}
)

install(TARGETS ${PROJECT_NAME}_tool
  LIBRARY DESTINATION ${CMAKE_INSTALL_LIBDIR}
)