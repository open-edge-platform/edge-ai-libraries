# SPDX-License-Identifier: Apache-2.0
# Copyright (C) 2025 Intel Corporation
cmake_minimum_required(VERSION 3.5)
project(run_hiwin_plc_acrn)

# Default to C++14
if(NOT CMAKE_CXX_STANDARD)
  set(CMAKE_CXX_STANDARD 14)
endif()

if(CMAKE_COMPILER_IS_GNUCXX OR CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

#####
## Choose Shared memory methodolgy
## ENABLE_SHM_RINGBUF: enable RT-Data-Agent ring buffer btw RT and non-RT domain under an OS.
## ENABLE_SHM_ACRN:    enable ACRN shared memory among different VMs.
add_definitions(-DENABLE_SHM_RINGBUF)
set(ENABLE_SHM_RINGBUF TRUE)
add_definitions(-DENABLE_SHM_ACRN)
set(ENABLE_SHM_ACRN TRUE)

if (ENABLE_SHM_RINGBUF)
  # Find shmringbuf
  set(LIBSHM_ROOT_DIR "/usr/local" CACHE PATH "Root directory of libshm.")
  execute_process(COMMAND find ${LIBSHM_ROOT_DIR}/include -name "shmringbuf.h"
                  COMMAND head -n 1
                  COMMAND xargs dirname
                  OUTPUT_VARIABLE LIBSHM_INCLUDE_DIRS OUTPUT_STRIP_TRAILING_WHITESPACE)
  execute_process(COMMAND find ${LIBSHM_ROOT_DIR}/lib -name "*libshmringbuf.so"
                  COMMAND head -n 1
                  OUTPUT_VARIABLE LIBSHM_LIBRARIES OUTPUT_STRIP_TRAILING_WHITESPACE)
  message(STATUS "LIBSHM_INCLUDE_DIRS: ${LIBSHM_INCLUDE_DIRS}")
  message(STATUS "LIBSHM_LIBRARIES: ${LIBSHM_LIBRARIES}")

  include_directories(
    ${LIBSHM_INCLUDE_DIRS}
  )
endif()

include_directories(
  ${CMAKE_CURRENT_SOURCE_DIR}/include
)

# find dependencies
find_package(ament_cmake REQUIRED)
find_package(rclcpp REQUIRED)
find_package(sensor_msgs REQUIRED)
find_package(trajectory_msgs REQUIRED)

add_executable(run_hiwin_plc src/run_hiwin_plc.cpp)
ament_target_dependencies(run_hiwin_plc
  rclcpp
  sensor_msgs
  trajectory_msgs
)
target_link_libraries(run_hiwin_plc ${LIBSHM_LIBRARIES})

install(TARGETS run_hiwin_plc
  DESTINATION lib/${PROJECT_NAME}
)
install(DIRECTORY launch
  DESTINATION share/${PROJECT_NAME}
) 

ament_package()
