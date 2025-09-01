# SPDX-License-Identifier: Apache-2.0
# Copyright (C) 2025 Intel Corporation
set(SOURCE
  src/axis.cpp
  src/execution_node.cpp
  src/fb_axis_admin.cpp
  src/fb_axis_motion.cpp
  src/fb_axis_node.cpp
  src/fb_axis_read.cpp
  src/fb_base.cpp
  src/motion_kernel.cpp
  src/planner.cpp
  src/servo.cpp
)
add_library(rtm_fb_com SHARED ${SOURCE})
set_target_properties(rtm_fb_com PROPERTIES VERSION "${${PROJECT_NAME}_VERSION}")
target_compile_options(rtm_fb_com PRIVATE -Wno-unused-variable)
if(SRC_BUILD)
  target_link_libraries(rtm_fb_com rtm_algo_com rtm_algo_pri rtm_algo_pub)
  add_dependencies(rtm_fb_com rtm_algo_com rtm_algo_pri rtm_algo_pub)
else()
  target_link_libraries(rtm_fb_com rtm_algo_com ${RTMOTION_ALGO_PRIVATE_LIBRARY} rtm_algo_pub)
endif()

install(
  DIRECTORY include/
  DESTINATION ${CMAKE_INSTALL_INCLUDEDIR}/fb/common/include
  FILES_MATCHING PATTERN "*.hpp"
)

install(
  TARGETS rtm_fb_com
  LIBRARY DESTINATION ${CMAKE_INSTALL_LIBDIR}
)