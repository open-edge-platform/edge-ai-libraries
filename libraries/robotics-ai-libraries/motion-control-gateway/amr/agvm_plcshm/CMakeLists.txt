# SPDX-License-Identifier: Apache-2.0
# Copyright (C) 2025 Intel Corporation
cmake_minimum_required(VERSION 3.5)
project(agvm_plcshm)

# Default to C99
if(NOT CMAKE_C_STANDARD)
  set(CMAKE_C_STANDARD 99)
endif()

# Default to C++14
if(NOT CMAKE_CXX_STANDARD)
  set(CMAKE_CXX_STANDARD 14)
endif()

if(CMAKE_COMPILER_IS_GNUCXX OR CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  add_compile_options(-Wall -Wextra -Wpedantic -Wno-write-strings)
endif()

# find dependencies
find_package(ament_cmake REQUIRED)
find_package(rclcpp REQUIRED)
find_package(geometry_msgs REQUIRED)
find_package(nav_msgs REQUIRED)
find_package(std_msgs REQUIRED)
find_package(tf2_ros REQUIRED)
find_package(tf2_eigen REQUIRED)

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

add_executable(agvm_plcshm_node src/agvm_plcshm_node.cpp)
ament_target_dependencies(agvm_plcshm_node
  rclcpp
  geometry_msgs
  nav_msgs
  std_msgs
  tf2_ros
  tf2_eigen
)
target_link_libraries(agvm_plcshm_node ${LIBSHM_LIBRARIES})
install(TARGETS agvm_plcshm_node
  DESTINATION lib/${PROJECT_NAME}
)

add_executable(shm_init_node src/shm_init_node.cpp)
ament_target_dependencies(shm_init_node
  rclcpp
)
target_link_libraries(shm_init_node ${LIBSHM_LIBRARIES})
install(TARGETS shm_init_node
  DESTINATION lib/${PROJECT_NAME}
)
  
install(DIRECTORY 
  launch
  DESTINATION share/${PROJECT_NAME}
)

ament_package()
