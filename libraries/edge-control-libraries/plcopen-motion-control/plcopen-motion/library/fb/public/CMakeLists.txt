# SPDX-License-Identifier: Apache-2.0
# Copyright (C) 2025 Intel Corporation
set(SOURCE
  src/fb_halt.cpp
  src/fb_homing.cpp
  src/fb_move_absolute.cpp
  src/fb_move_additive.cpp
  src/fb_move_relative.cpp
  src/fb_move_velocity.cpp
  src/fb_power.cpp
  src/fb_read_actual_acceleration.cpp
  src/fb_read_actual_position.cpp
  src/fb_read_actual_velocity.cpp
  src/fb_read_axis_error.cpp
  src/fb_read_command_acceleration.cpp
  src/fb_read_command_position.cpp
  src/fb_read_command_velocity.cpp
  src/fb_read_status.cpp
  src/fb_reset.cpp
  src/fb_stop.cpp
)
add_library(rtm_fb_pub SHARED ${SOURCE})
set_target_properties(rtm_fb_pub PROPERTIES VERSION "${${PROJECT_NAME}_VERSION}")
target_compile_options(rtm_fb_pub PRIVATE -Wno-unused-variable)
target_link_libraries(rtm_fb_pub rtm_fb_com)
add_dependencies(rtm_fb_pub rtm_fb_com)

install(
  DIRECTORY include/
  DESTINATION ${CMAKE_INSTALL_INCLUDEDIR}/fb/public/include
  FILES_MATCHING PATTERN "*.hpp"
)

install(
  TARGETS rtm_fb_pub
  LIBRARY DESTINATION ${CMAKE_INSTALL_LIBDIR}
)