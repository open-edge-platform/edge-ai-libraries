# SPDX-License-Identifier: Apache-2.0
# Copyright (C) 2025 Intel Corporation
cmake_minimum_required(VERSION 3.4)

set(NAME feature_extract)
project (${NAME})

#set(OUTPUT_DIR "${CMAKE_CURRENT_SOURCE_DIR}/../../bin")
#set(CMAKE_RUNTIME_OUTPUT_DIRECTORY "${OUTPUT_DIR}")

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED TRUE)

add_compile_options(-Wpedantic -Werror)

option(BUILD_OPENCV_FREE "build independent of opencv" OFF)

find_package(gflags REQUIRED)
find_package(OpenCV 4.2 REQUIRED)
find_package(orblze REQUIRED)

if(NOT orblze_LIBS)
  message(FATAL_ERROR
    "GPU Level-Zero ORB Level Zero loader is not found. "
    "You may need to install oneAPI Level Zero loader to fix this issue.")
else()
  message(STATUS
    "Found GPU Level-Zero ORB ! \n"
    " INCLUDE path ${ORBLZE_INCLUDE_DIR} \n"
    " LIB path ${ORBLZE_LIB_DIR} \n"
    " Level-zero prebuilt KERNEL path ${ORBLZE_KERNEL_DIR}\n"
    " LIB linker options: -l${orblze_LIBS}"
    " LIB linker options: -l${orblzeocvfree_LIBS}"
    )
endif()

find_package(OpenCV 4.2 REQUIRED)

if (BUILD_OPENCV_FREE)
  add_definitions("-DOPENCV_FREE")
endif()

set_property(TARGET PROPERTY CXX_STANDARD 11)
add_executable(${NAME} main.cpp)

include_directories ( ${ORBLZE_INCLUDE_DIR} )

if (BUILD_OPENCV_FREE)
target_link_libraries(${NAME} ${orblzeocvfree_LIBS} ${OpenCV_LIBS} -lgflags)
else()
target_link_libraries(${NAME} ${orblze_LIBS} ${OpenCV_LIBS} -lgflags)
endif()

set_property(TARGET ${NAME} PROPERTY INSTALL_RPATH_USE_LINK_PATH TRUE)

