# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
cmake_minimum_required(VERSION 3.20)
project(optical_flow_sdk VERSION 0.1.0 LANGUAGES CXX)

include(CTest)
include(GNUInstallDirs)

option(OPTICALFLOW_ENABLE_CPU "Build the CPU DIS backend (always recommended)" ON)
option(OPTICALFLOW_ENABLE_SYCL "Build the SYCL backend (requires icpx / -fsycl)" OFF)
option(OPTICALFLOW_ENABLE_OPENCL "Build the OpenCL backend" OFF)
option(OPTICALFLOW_BUILD_TESTS "Build optical-flow-sdk tests" ${BUILD_TESTING})
option(OPTICALFLOW_BUILD_SAMPLES "Build native sample applications" ON)
option(OPTICALFLOW_BUILD_PYTHON "Build Python bindings (requires pybind11)" OFF)

if(NOT OPTICALFLOW_ENABLE_CPU AND NOT OPTICALFLOW_ENABLE_SYCL AND NOT OPTICALFLOW_ENABLE_OPENCL)
  message(FATAL_ERROR "At least one of OPTICALFLOW_ENABLE_CPU/SYCL/OPENCL must be ON")
endif()

# GPU backends currently fall back to the CPU DIS path until device kernels land.
if((OPTICALFLOW_ENABLE_SYCL OR OPTICALFLOW_ENABLE_OPENCL) AND NOT OPTICALFLOW_ENABLE_CPU)
  message(FATAL_ERROR
    "OPTICALFLOW_ENABLE_CPU is required while SYCL/OpenCL backends use the CPU fallback")
endif()

set(OPTICALFLOW_HAS_CPU 0)
set(OPTICALFLOW_HAS_OPENCL 0)
set(OPTICALFLOW_HAS_SYCL 0)
if(OPTICALFLOW_ENABLE_CPU)
  set(OPTICALFLOW_HAS_CPU 1)
endif()
if(OPTICALFLOW_ENABLE_OPENCL)
  set(OPTICALFLOW_HAS_OPENCL 1)
endif()
if(OPTICALFLOW_ENABLE_SYCL)
  set(OPTICALFLOW_HAS_SYCL 1)
endif()

configure_file(
  ${CMAKE_CURRENT_SOURCE_DIR}/include/optical_flow_sdk/version.hpp.in
  ${CMAKE_CURRENT_BINARY_DIR}/include/optical_flow_sdk/version.hpp
  @ONLY
)
set(OPTICALFLOW_GENERATED_INCLUDE_DIR ${CMAKE_CURRENT_BINARY_DIR}/include)

set(OPTICALFLOW_CORE_SOURCES src/optical_flow.cpp)
if(OPTICALFLOW_ENABLE_CPU)
  list(APPEND OPTICALFLOW_CORE_SOURCES src/cpu/cpu_optical_flow.cpp)
endif()
if(OPTICALFLOW_ENABLE_OPENCL)
  find_package(OpenCL REQUIRED)
  find_package(Threads REQUIRED)
  list(APPEND OPTICALFLOW_CORE_SOURCES src/opencl/opencl_optical_flow.cpp)
endif()
if(OPTICALFLOW_ENABLE_SYCL)
  list(APPEND OPTICALFLOW_CORE_SOURCES src/sycl/sycl_optical_flow.cpp)
endif()

add_library(optical_flow_sdk ${OPTICALFLOW_CORE_SOURCES})
add_library(optical_flow_sdk::optical_flow_sdk ALIAS optical_flow_sdk)
target_compile_features(optical_flow_sdk PUBLIC cxx_std_17)
target_include_directories(optical_flow_sdk
  PUBLIC
    $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
    $<BUILD_INTERFACE:${OPTICALFLOW_GENERATED_INCLUDE_DIR}>
    $<INSTALL_INTERFACE:include>
)
set_target_properties(optical_flow_sdk PROPERTIES
  POSITION_INDEPENDENT_CODE ON
  VERSION ${PROJECT_VERSION}
  SOVERSION ${PROJECT_VERSION_MAJOR}
)

if(OPTICALFLOW_ENABLE_OPENCL)
  target_link_libraries(optical_flow_sdk PUBLIC OpenCL::OpenCL Threads::Threads)
endif()

if(OPTICALFLOW_ENABLE_SYCL)
  # Prefer Intel oneAPI SYCL when the active compiler supports it.
  include(CheckCXXCompilerFlag)
  check_cxx_compiler_flag("-fsycl" OPTICALFLOW_COMPILER_HAS_FSYCL)
  if(OPTICALFLOW_COMPILER_HAS_FSYCL)
    target_compile_options(optical_flow_sdk PUBLIC -fsycl)
    target_link_options(optical_flow_sdk PUBLIC -fsycl)
  else()
    message(WARNING
      "OPTICALFLOW_ENABLE_SYCL=ON but the compiler does not accept -fsycl. "
      "Configure with -DCMAKE_CXX_COMPILER=icpx on a oneAPI host, or set "
      "OPTICALFLOW_ENABLE_SYCL=OFF.")
  endif()
endif()

if(OPTICALFLOW_BUILD_TESTS)
  add_executable(test_optical_flow_backend tests/test_backend_resolve.cpp)
  target_link_libraries(test_optical_flow_backend PRIVATE optical_flow_sdk)
  add_test(NAME optical_flow_sdk.backend_resolve COMMAND test_optical_flow_backend)

  add_executable(test_optical_flow_types tests/test_types.cpp)
  target_link_libraries(test_optical_flow_types PRIVATE optical_flow_sdk)
  add_test(NAME optical_flow_sdk.types COMMAND test_optical_flow_types)

  if(OPTICALFLOW_ENABLE_CPU)
    add_executable(test_optical_flow_cpu_shift tests/test_cpu_synthetic_shift.cpp)
    target_link_libraries(test_optical_flow_cpu_shift PRIVATE optical_flow_sdk)
    add_test(NAME optical_flow_sdk.cpu_synthetic_shift COMMAND test_optical_flow_cpu_shift)
  endif()
endif()

if(OPTICALFLOW_BUILD_SAMPLES AND OPTICALFLOW_ENABLE_CPU)
  add_executable(sample_calc_flow_cpu samples/calc_flow_cpu.cpp)
  target_link_libraries(sample_calc_flow_cpu PRIVATE optical_flow_sdk)
endif()

if(OPTICALFLOW_BUILD_PYTHON)
  find_package(pybind11 CONFIG REQUIRED)
  pybind11_add_module(optical_flow_sdk_py MODULE python/optical_flow_sdk_bindings.cpp)
  set_target_properties(optical_flow_sdk_py PROPERTIES
    OUTPUT_NAME _native
    INTERPROCEDURAL_OPTIMIZATION OFF
    LIBRARY_OUTPUT_DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR}/python/optical_flow_sdk
  )
  # Multi-config generators place outputs under $<CONFIG>; mirror for those.
  foreach(_cfg IN ITEMS Debug Release RelWithDebInfo MinSizeRel)
    set_target_properties(optical_flow_sdk_py PROPERTIES
      LIBRARY_OUTPUT_DIRECTORY_${_cfg} ${CMAKE_CURRENT_SOURCE_DIR}/python/optical_flow_sdk)
  endforeach()
  target_link_libraries(optical_flow_sdk_py PRIVATE optical_flow_sdk)
  target_include_directories(optical_flow_sdk_py PRIVATE
    ${CMAKE_CURRENT_SOURCE_DIR}/include
    ${OPTICALFLOW_GENERATED_INCLUDE_DIR}
  )
endif()

include(CMakePackageConfigHelpers)
configure_file(
  ${CMAKE_CURRENT_SOURCE_DIR}/cmake/optical_flow_sdk.pc.in
  ${CMAKE_CURRENT_BINARY_DIR}/optical_flow_sdk.pc
  @ONLY
)
configure_package_config_file(
  ${CMAKE_CURRENT_SOURCE_DIR}/cmake/optical_flow_sdkConfig.cmake.in
  ${CMAKE_CURRENT_BINARY_DIR}/optical_flow_sdkConfig.cmake
  INSTALL_DESTINATION ${CMAKE_INSTALL_LIBDIR}/cmake/optical_flow_sdk
)
write_basic_package_version_file(
  ${CMAKE_CURRENT_BINARY_DIR}/optical_flow_sdkConfigVersion.cmake
  VERSION ${PROJECT_VERSION}
  COMPATIBILITY SameMajorVersion
)

install(TARGETS optical_flow_sdk
  EXPORT optical_flow_sdkTargets
  ARCHIVE DESTINATION ${CMAKE_INSTALL_LIBDIR}
  LIBRARY DESTINATION ${CMAKE_INSTALL_LIBDIR}
  RUNTIME DESTINATION ${CMAKE_INSTALL_BINDIR}
)
install(DIRECTORY include/optical_flow_sdk
  DESTINATION ${CMAKE_INSTALL_INCLUDEDIR}
  FILES_MATCHING PATTERN "*.hpp"
)
install(FILES ${CMAKE_CURRENT_BINARY_DIR}/include/optical_flow_sdk/version.hpp
  DESTINATION ${CMAKE_INSTALL_INCLUDEDIR}/optical_flow_sdk
)
install(EXPORT optical_flow_sdkTargets
  NAMESPACE optical_flow_sdk::
  DESTINATION ${CMAKE_INSTALL_LIBDIR}/cmake/optical_flow_sdk
)
install(FILES
  ${CMAKE_CURRENT_BINARY_DIR}/optical_flow_sdkConfig.cmake
  ${CMAKE_CURRENT_BINARY_DIR}/optical_flow_sdkConfigVersion.cmake
  DESTINATION ${CMAKE_INSTALL_LIBDIR}/cmake/optical_flow_sdk
)
install(FILES ${CMAKE_CURRENT_BINARY_DIR}/optical_flow_sdk.pc
  DESTINATION ${CMAKE_INSTALL_LIBDIR}/pkgconfig
)
