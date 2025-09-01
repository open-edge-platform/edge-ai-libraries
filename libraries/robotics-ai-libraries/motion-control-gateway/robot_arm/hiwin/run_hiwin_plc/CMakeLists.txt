# SPDX-License-Identifier: Apache-2.0
# Copyright (C) 2025 Intel Corporation
cmake_minimum_required(VERSION 3.5)
project(run_hiwin_plc)

# Default to C++14
if(NOT CMAKE_CXX_STANDARD)
  set(CMAKE_CXX_STANDARD 14)
endif()

if(CMAKE_COMPILER_IS_GNUCXX OR CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  add_compile_options(-Wall -Wextra -Wpedantic)
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
find_package(rclcpp REQUIRED)
find_package(sensor_msgs REQUIRED)
find_package(trajectory_msgs REQUIRED)
find_package(moveit_msgs REQUIRED)

add_executable(run_hiwin_plc src/run_hiwin_plc.cpp)
ament_target_dependencies(run_hiwin_plc
  rclcpp
  sensor_msgs
  trajectory_msgs
  moveit_msgs
)
target_link_libraries(run_hiwin_plc ${LIBSHM_LIBRARIES})

install(TARGETS run_hiwin_plc
  DESTINATION lib/${PROJECT_NAME}
)
install(DIRECTORY launch
  DESTINATION share/${PROJECT_NAME}
) 

ament_package()
