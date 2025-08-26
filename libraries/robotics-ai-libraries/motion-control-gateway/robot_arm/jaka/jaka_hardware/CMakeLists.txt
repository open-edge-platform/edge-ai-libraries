# SPDX-License-Identifier: Apache-2.0
# Copyright (C) 2025 Intel Corporation
cmake_minimum_required(VERSION 3.5)
project(jaka_hardware)

# Default to C++14
if(NOT CMAKE_CXX_STANDARD)
  set(CMAKE_CXX_STANDARD 14)
endif()

if(CMAKE_COMPILER_IS_GNUCXX OR CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  add_compile_options(-Wall -Wextra)
endif()

# Find shmringbuf
find_path(
  PLCOPEN_CMAKE_MODULE_PATH
  NAMES find_libshm.cmake
  HINTS ${ROOTDIR}/usr/include ${ROOTDIR}/usr/local/include
)
message(STATUS "PLCOPEN_CMAKE_MODULE_PATH: ${PLCOPEN_CMAKE_MODULE_PATH}")
include(${PLCOPEN_CMAKE_MODULE_PATH}/find_libshm.cmake)

include_directories(
  ${LIBSHM_INCLUDE_DIRS}
)

# find dependencies
find_package(ament_cmake REQUIRED)
find_package(hardware_interface REQUIRED)
find_package(pluginlib REQUIRED)
find_package(rclcpp REQUIRED)

## COMPILE
add_library(
  ${PROJECT_NAME}
  SHARED
  src/jaka_system_can.cpp
)
target_include_directories(
  ${PROJECT_NAME}
  PRIVATE
  include
)
ament_target_dependencies(
  ${PROJECT_NAME}
  hardware_interface
  pluginlib
  rclcpp
)

target_link_libraries(${PROJECT_NAME} ${LIBSHM_LIBRARIES})

pluginlib_export_plugin_description_file(hardware_interface jaka_hardware.xml)

# INSTALL
install(
  TARGETS ${PROJECT_NAME}
  DESTINATION lib
)
install(
  DIRECTORY include/
  DESTINATION include
)

if(BUILD_TESTING)
  find_package(ament_cmake_gtest REQUIRED)
endif()

## EXPORTS
ament_export_include_directories(
  include
)
ament_export_libraries(
  ${PROJECT_NAME}
)
ament_export_dependencies(
  hardware_interface
  pluginlib
  rclcpp
)
ament_package()
