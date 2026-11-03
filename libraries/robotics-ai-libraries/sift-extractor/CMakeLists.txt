# Copyright (C) 2026 Intel Corporation
#
# SPDX-License-Identifier: Apache-2.0

cmake_minimum_required(VERSION 3.16)
project(siftlze VERSION 0.1.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_POSITION_INDEPENDENT_CODE ON)
include(GNUInstallDirs)
enable_testing()

option(ENABLE_OPENCV "Build OpenCV-linked libsift_lze" ON)
option(SIFTLZE_BUILD_SAMPLES "Build robotics SIFT samples" ON)
option(SIFTLZE_BUILD_TESTS "Build robotics SIFT smoke tests" ON)

# Prefer an installed/core build tree. Deb packaging stages core first.
# Core OpenCL export currently expects OpenCL::OpenCL to exist in the consumer.
find_package(OpenCL REQUIRED)
find_package(sift_extractor CONFIG REQUIRED)
if(NOT SIFT_EXTRACTOR_HAS_OPENCL AND NOT SIFT_EXTRACTOR_HAS_SYCL)
  message(FATAL_ERROR "sift_extractor was built without OpenCL or SYCL")
endif()
if(SIFT_EXTRACTOR_HAS_SYCL)
  # SYCL objects in the static core require the DPC++ driver when linking the wrapper.
  if(NOT CMAKE_CXX_COMPILER MATCHES "icpx" AND NOT CMAKE_CXX_COMPILER_ID STREQUAL "IntelLLVM")
    message(WARNING "SIFT SYCL core is enabled; prefer CMAKE_CXX_COMPILER=icpx when linking libsift_lze*")
  endif()
  string(APPEND CMAKE_CXX_FLAGS " -fsycl")
endif()

set(SIFTLZE_VERSION_MAJOR ${PROJECT_VERSION_MAJOR})
set(SIFTLZE_VERSION_MINOR ${PROJECT_VERSION_MINOR})
set(SIFTLZE_VERSION_PATCH ${PROJECT_VERSION_PATCH})
set(SIFTLZE_VERSION_STRING ${PROJECT_VERSION})

configure_file(${CMAKE_CURRENT_SOURCE_DIR}/cmake/config.h.in
               ${CMAKE_CURRENT_BINARY_DIR}/include/config.h @ONLY)

set(SIFTLZE_SOURCES src/sift_lze.cpp)
set(SIFTLZE_PUBLIC_HEADERS
  include/sift_lze.h
  include/sift_type.h
  ${CMAKE_CURRENT_BINARY_DIR}/include/config.h)

add_library(sift_lze_ocvfree SHARED ${SIFTLZE_SOURCES})
target_compile_definitions(sift_lze_ocvfree PUBLIC OPENCV_FREE)
target_include_directories(sift_lze_ocvfree
  PUBLIC
    $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
    $<BUILD_INTERFACE:${CMAKE_CURRENT_BINARY_DIR}/include>
    $<INSTALL_INTERFACE:${CMAKE_INSTALL_INCLUDEDIR}>
  PRIVATE
    ${CMAKE_CURRENT_SOURCE_DIR}/src)
target_link_libraries(sift_lze_ocvfree PRIVATE sift_extractor::sift_extractor)
set_target_properties(sift_lze_ocvfree PROPERTIES
  OUTPUT_NAME sift_lze_ocvfree
  VERSION ${PROJECT_VERSION}
  SOVERSION ${PROJECT_VERSION_MAJOR})

set(SIFTLZE_INSTALL_TARGETS sift_lze_ocvfree)

if(ENABLE_OPENCV)
  find_package(OpenCV 4.2 REQUIRED COMPONENTS core imgproc imgcodecs)
  add_library(sift_lze SHARED ${SIFTLZE_SOURCES})
  target_include_directories(sift_lze
    PUBLIC
      $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
      $<BUILD_INTERFACE:${CMAKE_CURRENT_BINARY_DIR}/include>
      $<INSTALL_INTERFACE:${CMAKE_INSTALL_INCLUDEDIR}>
    PRIVATE
      ${CMAKE_CURRENT_SOURCE_DIR}/src)
  target_link_libraries(sift_lze PRIVATE sift_extractor::sift_extractor)
  target_link_libraries(sift_lze PUBLIC ${OpenCV_LIBS})
  set_target_properties(sift_lze PROPERTIES
    OUTPUT_NAME sift_lze
    VERSION ${PROJECT_VERSION}
    SOVERSION ${PROJECT_VERSION_MAJOR})
  list(APPEND SIFTLZE_INSTALL_TARGETS sift_lze)
endif()

install(TARGETS ${SIFTLZE_INSTALL_TARGETS}
  EXPORT siftlzeTargets
  LIBRARY DESTINATION ${CMAKE_INSTALL_LIBDIR}
  ARCHIVE DESTINATION ${CMAKE_INSTALL_LIBDIR}
  RUNTIME DESTINATION ${CMAKE_INSTALL_BINDIR})

install(FILES include/sift_lze.h include/sift_type.h
  DESTINATION ${CMAKE_INSTALL_INCLUDEDIR})
install(FILES ${CMAKE_CURRENT_BINARY_DIR}/include/config.h
  DESTINATION ${CMAKE_INSTALL_INCLUDEDIR})

configure_file(${CMAKE_CURRENT_SOURCE_DIR}/siftlze.pc.in
               ${CMAKE_CURRENT_BINARY_DIR}/siftlze.pc @ONLY)
install(FILES ${CMAKE_CURRENT_BINARY_DIR}/siftlze.pc
  DESTINATION ${CMAKE_INSTALL_LIBDIR}/pkgconfig)

include(CMakePackageConfigHelpers)
set(INSTALL_CMAKE_DIR ${CMAKE_INSTALL_LIBDIR}/cmake/siftlze)
set(CONFIG_DIR_CONFIG ${CMAKE_INSTALL_PREFIX}/${INSTALL_CMAKE_DIR})
set(LIB_DIR_CONFIG ${CMAKE_INSTALL_PREFIX}/${CMAKE_INSTALL_LIBDIR})
set(INCLUDE_DIR_CONFIG ${CMAKE_INSTALL_PREFIX}/${CMAKE_INSTALL_INCLUDEDIR})
configure_package_config_file(
  ${CMAKE_CURRENT_SOURCE_DIR}/siftlzeConfig.cmake.in
  ${CMAKE_CURRENT_BINARY_DIR}/siftlzeConfig.cmake
  INSTALL_DESTINATION ${INSTALL_CMAKE_DIR}
  PATH_VARS CONFIG_DIR_CONFIG LIB_DIR_CONFIG INCLUDE_DIR_CONFIG)
write_basic_package_version_file(
  ${CMAKE_CURRENT_BINARY_DIR}/siftlzeConfigVersion.cmake
  VERSION ${PROJECT_VERSION}
  COMPATIBILITY SameMajorVersion)
install(FILES
  ${CMAKE_CURRENT_BINARY_DIR}/siftlzeConfig.cmake
  ${CMAKE_CURRENT_BINARY_DIR}/siftlzeConfigVersion.cmake
  DESTINATION ${INSTALL_CMAKE_DIR})
install(EXPORT siftlzeTargets
  FILE siftlzeTargets.cmake
  DESTINATION ${INSTALL_CMAKE_DIR})

if(SIFTLZE_BUILD_SAMPLES AND ENABLE_OPENCV)
  add_subdirectory(samples)
endif()
if(SIFTLZE_BUILD_TESTS)
  add_subdirectory(tests)
endif()
