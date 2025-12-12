# SPDX-License-Identifier: Apache-2.0
# Copyright (C) 2025 Intel Corporation
set (SOURCE 
    ectask.cpp
    ecservo.cpp
)
add_library(ectask SHARED ${SOURCE})
set_target_properties(ectask PROPERTIES VERSION "${${PROJECT_NAME}_VERSION}")
target_link_libraries(ectask
${RTMOTION_LIBRARIES}
${ENABLEKIT_LIBRARIES}
${SERVO_LIBRARIES}
${LIBSHM_LIBRARIES}
)
install(TARGETS ectask
  LIBRARY DESTINATION ${CMAKE_INSTALL_LIBDIR}
)
