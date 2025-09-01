# SPDX-License-Identifier: Apache-2.0
# Copyright (C) 2025 Intel Corporation
# Add source files
set(ECRT_SERVO_SOURCE ecrt_servo.cpp)
set(SYMG_SOURCE symg_servo.cpp)
set(ECRT_IO_SOURCE ecrt_io.cpp)

# Create "servo" library
add_library(${PROJECT_NAME} SHARED ${ECRT_SERVO_SOURCE})
set_target_properties(${PROJECT_NAME} PROPERTIES VERSION "${${PROJECT_NAME}_VERSION}")
target_link_libraries(${PROJECT_NAME}
${RTMOTION_LIBRARIES}
${ETHERCAT_LIBRARIES}
${ENABLEKIT_LIBRARIES}
)

# SYMG servo library and test samples
add_library(${PROJECT_NAME}_symg SHARED ${SYMG_SOURCE})
set_target_properties(${PROJECT_NAME}_symg PROPERTIES VERSION "${${PROJECT_NAME}_VERSION}")
target_compile_options(${PROJECT_NAME}_symg PRIVATE -Wno-missing-field-initializers)
target_link_libraries(${PROJECT_NAME}_symg
  ${RTMOTION_LIBRARIES}
  ${ETHERCAT_LIBRARIES}
  ${ENABLEKIT_LIBRARIES}
)

# Create "io" library
add_library(${PROJECT_NAME}_io SHARED ${ECRT_IO_SOURCE})
set_target_properties(${PROJECT_NAME}_io PROPERTIES VERSION "${${PROJECT_NAME}_VERSION}")
target_link_libraries(${PROJECT_NAME}_io
${RTMOTION_LIBRARIES}
${ETHERCAT_LIBRARIES}
${ENABLEKIT_LIBRARIES}
)

install(TARGETS ${PROJECT_NAME} ${PROJECT_NAME}_symg ${PROJECT_NAME}_io
  LIBRARY DESTINATION ${CMAKE_INSTALL_LIBDIR}
)