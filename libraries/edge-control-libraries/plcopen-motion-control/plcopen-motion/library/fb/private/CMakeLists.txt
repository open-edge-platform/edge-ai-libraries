# SPDX-License-Identifier: Apache-2.0
# Copyright (C) 2025 Intel Corporation
if(SRC_BUILD)
  set(SOURCE
    src/fb_cam_in.cpp
    src/fb_cam_out.cpp
    src/fb_cam_ref.cpp
    src/fb_cam_table_select.cpp
    src/fb_gear_in.cpp
    src/fb_gear_out.cpp
    src/fb_gear_in_pos.cpp
    src/fb_home.cpp
    src/fb_io_operation.cpp
    src/fb_jog.cpp
    src/fb_read_axis_info.cpp
    src/fb_move_superimposed.cpp
    src/fb_read_actual_torque.cpp
    src/fb_read_digital_input.cpp
    src/fb_read_digital_output.cpp
    src/fb_read_motion_state.cpp
    src/fb_read_raw_position.cpp
    src/fb_set_controller_mode.cpp
    src/fb_set_position.cpp
    src/fb_set_override.cpp
    src/fb_torque_control.cpp
    src/fb_write_digital_output.cpp
    src/io.cpp
    src/fb_digital_cam_switch.cpp
  )
  add_library(rtm_fb_pri SHARED ${SOURCE})
  set_target_properties(rtm_fb_pri PROPERTIES VERSION "${${PROJECT_NAME}_VERSION}")
  target_compile_options(rtm_fb_pri PRIVATE -Wno-unused-variable)
  target_link_libraries(rtm_fb_pri rtm_fb_com)
  add_dependencies(rtm_fb_pri rtm_fb_com)

  install(
    TARGETS rtm_fb_pri
    LIBRARY DESTINATION ${CMAKE_INSTALL_LIBDIR}
  )
else()
  find_library(
    RTMOTION_FB_PRIVATE_LIBRARY
    NAMES rtm_fb_pri
    HINTS ${CMAKE_CURRENT_SOURCE_DIR}
  )
  if (NOT RTMOTION_FB_PRIVATE_LIBRARY)
    message(ERROR " RTmotion private fb library not found under: ${CMAKE_CURRENT_SOURCE_DIR}")
  endif()
  message(STATUS "RTMOTION_FB_PRIVATE_LIBRARY: ${RTMOTION_FB_PRIVATE_LIBRARY}")

  INSTALL(FILES
    librtm*
    DESTINATION ${CMAKE_INSTALL_LIBDIR}
  )
endif()

install(
  DIRECTORY include/
  DESTINATION ${CMAKE_INSTALL_INCLUDEDIR}/fb/private/include
  FILES_MATCHING PATTERN "*.hpp"
)
