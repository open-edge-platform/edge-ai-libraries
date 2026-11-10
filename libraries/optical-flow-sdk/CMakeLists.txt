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
option(OPTICALFLOW_BUILD_SHARED "Build shared liboptical_flow_sdk (deb / dynamic link)" OFF)
option(OPTICALFLOW_BUILD_OPENCV_ADAPTER
  "Build thin OpenCV Mat adapters and OpenCV-based diagnostics" OFF)
option(OPTICALFLOW_BUILD_BENCHMARKS "Build CPU microbench / OpenCV compare tools" ON)
option(OPTICALFLOW_ENABLE_OPENVINO
  "Link OpenVINO for SEA-RAFT-S Slow accuracy tier (P2)" OFF)
option(OPTICALFLOW_INSTALL_PYTHON
  "Install Python package next to the C++ install prefix (deb / system)" OFF)

if(NOT OPTICALFLOW_ENABLE_CPU AND NOT OPTICALFLOW_ENABLE_SYCL AND NOT OPTICALFLOW_ENABLE_OPENCL)
  message(FATAL_ERROR "At least one of OPTICALFLOW_ENABLE_CPU/SYCL/OPENCL must be ON")
endif()

# SparsePyrLK remains CPU; Farneback has CPU + OpenCL Farneback-class path.
# OpenCL/SYCL DIS are device-resident. SEA-RAFT needs OpenVINO.

set(OPTICALFLOW_HAS_CPU 0)
set(OPTICALFLOW_HAS_OPENCL 0)
set(OPTICALFLOW_HAS_SYCL 0)
set(OPTICALFLOW_HAS_OPENCV_ADAPTER 0)
set(OPTICALFLOW_HAS_OPENVINO 0)
if(OPTICALFLOW_ENABLE_CPU)
  set(OPTICALFLOW_HAS_CPU 1)
endif()
if(OPTICALFLOW_ENABLE_OPENCL)
  set(OPTICALFLOW_HAS_OPENCL 1)
endif()
if(OPTICALFLOW_ENABLE_SYCL)
  set(OPTICALFLOW_HAS_SYCL 1)
endif()
if(OPTICALFLOW_BUILD_OPENCV_ADAPTER)
  set(OPTICALFLOW_HAS_OPENCV_ADAPTER 1)
endif()
if(OPTICALFLOW_ENABLE_OPENVINO)
  find_package(OpenVINO REQUIRED COMPONENTS Runtime)
  set(OPTICALFLOW_HAS_OPENVINO 1)
endif()

configure_file(
  ${CMAKE_CURRENT_SOURCE_DIR}/include/optical_flow_sdk/version.hpp.in
  ${CMAKE_CURRENT_BINARY_DIR}/include/optical_flow_sdk/version.hpp
  @ONLY
)
set(OPTICALFLOW_GENERATED_INCLUDE_DIR ${CMAKE_CURRENT_BINARY_DIR}/include)

set(OPTICALFLOW_CORE_SOURCES
  src/optical_flow.cpp
  src/metrics.cpp
  src/sea_raft.cpp
)
if(OPTICALFLOW_ENABLE_CPU)
  list(APPEND OPTICALFLOW_CORE_SOURCES
    src/cpu/cpu_optical_flow.cpp
    src/cpu/farneback.cpp
    src/cpu/sparse_pyrlk.cpp
  )
endif()
if(OPTICALFLOW_ENABLE_OPENCL)
  # Lab hosts may ship the ICD without distro opencl-headers; allow an override.
  if(DEFINED OPTICALFLOW_OPENCL_INCLUDE_DIR AND OPTICALFLOW_OPENCL_INCLUDE_DIR)
    set(OpenCL_INCLUDE_DIR "${OPTICALFLOW_OPENCL_INCLUDE_DIR}" CACHE PATH "OpenCL headers" FORCE)
  endif()
  find_package(OpenCL REQUIRED)
  find_package(Threads REQUIRED)
  list(APPEND OPTICALFLOW_CORE_SOURCES
    src/opencl/opencl_optical_flow.cpp
    src/opencl/opencl_farneback.cpp
    src/opencl/opencl_sparse_pyrlk.cpp
  )
endif()
if(OPTICALFLOW_ENABLE_SYCL)
  list(APPEND OPTICALFLOW_CORE_SOURCES src/sycl/sycl_optical_flow.cpp)
endif()

if(OPTICALFLOW_BUILD_SHARED)
  add_library(optical_flow_sdk SHARED ${OPTICALFLOW_CORE_SOURCES})
else()
  add_library(optical_flow_sdk STATIC ${OPTICALFLOW_CORE_SOURCES})
endif()
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
  OUTPUT_NAME optical_flow_sdk
)

if(OPTICALFLOW_ENABLE_OPENCL)
  target_link_libraries(optical_flow_sdk PUBLIC OpenCL::OpenCL Threads::Threads ${CMAKE_DL_LIBS})
  find_package(OpenMP)
  if(OpenMP_CXX_FOUND)
    target_link_libraries(optical_flow_sdk PRIVATE OpenMP::OpenMP_CXX)
  endif()
endif()

if(OPTICALFLOW_ENABLE_OPENVINO)
  target_link_libraries(optical_flow_sdk PUBLIC openvino::runtime)
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

    add_executable(test_optical_flow_farneback tests/test_farneback_shift.cpp)
    target_link_libraries(test_optical_flow_farneback PRIVATE optical_flow_sdk)
    add_test(NAME optical_flow_sdk.farneback_shift COMMAND test_optical_flow_farneback)

    add_executable(test_optical_flow_sparse_pyrlk tests/test_sparse_pyrlk.cpp)
    target_link_libraries(test_optical_flow_sparse_pyrlk PRIVATE optical_flow_sdk)
    add_test(NAME optical_flow_sdk.sparse_pyrlk COMMAND test_optical_flow_sparse_pyrlk)

    add_executable(test_optical_flow_determinism tests/test_determinism.cpp)
    target_link_libraries(test_optical_flow_determinism PRIVATE optical_flow_sdk)
    add_test(NAME optical_flow_sdk.determinism COMMAND test_optical_flow_determinism)

    add_executable(test_optical_flow_algorithm tests/test_algorithm_resolve.cpp)
    target_link_libraries(test_optical_flow_algorithm PRIVATE optical_flow_sdk)
    add_test(NAME optical_flow_sdk.algorithm_resolve COMMAND test_optical_flow_algorithm)
  endif()

  if(OPTICALFLOW_ENABLE_OPENCL)
    add_executable(test_optical_flow_opencl_shift tests/test_opencl_synthetic_shift.cpp)
    target_link_libraries(test_optical_flow_opencl_shift PRIVATE optical_flow_sdk)
    add_test(NAME optical_flow_sdk.opencl_synthetic_shift COMMAND test_optical_flow_opencl_shift)

    add_executable(test_optical_flow_opencl_resident tests/test_opencl_device_resident.cpp)
    target_link_libraries(test_optical_flow_opencl_resident PRIVATE optical_flow_sdk)
    add_test(NAME optical_flow_sdk.opencl_device_resident COMMAND test_optical_flow_opencl_resident)
  endif()

  if(OPTICALFLOW_ENABLE_SYCL)
    add_executable(test_optical_flow_sycl_shift tests/test_sycl_synthetic_shift.cpp)
    target_link_libraries(test_optical_flow_sycl_shift PRIVATE optical_flow_sdk)
    add_test(NAME optical_flow_sdk.sycl_synthetic_shift COMMAND test_optical_flow_sycl_shift)

    add_executable(test_optical_flow_sycl_resident tests/test_sycl_device_resident.cpp)
    target_link_libraries(test_optical_flow_sycl_resident PRIVATE optical_flow_sdk)
    add_test(NAME optical_flow_sdk.sycl_device_resident COMMAND test_optical_flow_sycl_resident)
  endif()

  add_executable(test_optical_flow_metrics tests/test_metrics_flo.cpp)
  target_link_libraries(test_optical_flow_metrics PRIVATE optical_flow_sdk)
  add_test(NAME optical_flow_sdk.metrics_flo COMMAND test_optical_flow_metrics)
endif()

if(OPTICALFLOW_BUILD_OPENCV_ADAPTER)
  find_package(OpenCV REQUIRED COMPONENTS core imgproc video imgcodecs)
  add_library(optical_flow_opencv_adapter src/opencv_adapter.cpp)
  add_library(optical_flow_sdk::opencv_adapter ALIAS optical_flow_opencv_adapter)
  target_compile_features(optical_flow_opencv_adapter PUBLIC cxx_std_17)
  target_link_libraries(optical_flow_opencv_adapter PUBLIC optical_flow_sdk ${OpenCV_LIBS})
  target_include_directories(optical_flow_opencv_adapter PUBLIC
    $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
    $<BUILD_INTERFACE:${OPTICALFLOW_GENERATED_INCLUDE_DIR}>
    $<INSTALL_INTERFACE:include>
    ${OpenCV_INCLUDE_DIRS}
  )
  set_target_properties(optical_flow_opencv_adapter PROPERTIES POSITION_INDEPENDENT_CODE ON)

  if(OPTICALFLOW_BUILD_TESTS)
    add_executable(test_optical_flow_opencv_adapter tests/test_opencv_adapter.cpp)
    target_link_libraries(test_optical_flow_opencv_adapter PRIVATE optical_flow_opencv_adapter)
    add_test(NAME optical_flow_sdk.opencv_adapter COMMAND test_optical_flow_opencv_adapter)

    add_executable(test_optical_flow_opencv_cpu_parity tests/test_opencv_cpu_parity.cpp)
    target_link_libraries(test_optical_flow_opencv_cpu_parity PRIVATE optical_flow_opencv_adapter)
    add_test(NAME optical_flow_sdk.opencv_cpu_parity COMMAND test_optical_flow_opencv_cpu_parity)
  endif()

  if(OPTICALFLOW_BUILD_BENCHMARKS)
    add_executable(compare_opencv_dis benchmarks/compare_opencv_dis.cpp)
    target_link_libraries(compare_opencv_dis PRIVATE optical_flow_opencv_adapter)

    add_executable(parity_opencv_datasets benchmarks/parity_opencv_datasets.cpp)
    target_link_libraries(parity_opencv_datasets PRIVATE optical_flow_opencv_adapter)
  endif()
endif()

if(OPTICALFLOW_BUILD_SAMPLES AND OPTICALFLOW_ENABLE_CPU)
  add_executable(sample_calc_flow_cpu samples/calc_flow_cpu.cpp)
  target_link_libraries(sample_calc_flow_cpu PRIVATE optical_flow_sdk)
  add_executable(sample_calc_flow_farneback samples/calc_flow_farneback.cpp)
  target_link_libraries(sample_calc_flow_farneback PRIVATE optical_flow_sdk)
  add_executable(sample_stabilize_global_flow samples/stabilize_global_flow.cpp)
  target_link_libraries(sample_stabilize_global_flow PRIVATE optical_flow_sdk)
  add_executable(sample_track_points samples/track_points.cpp)
  target_link_libraries(sample_track_points PRIVATE optical_flow_sdk)
  add_executable(sample_track_points_cpu samples/track_points_cpu.cpp)
  target_link_libraries(sample_track_points_cpu PRIVATE optical_flow_sdk)
  add_executable(sample_warp_with_flow samples/warp_with_flow.cpp)
  target_link_libraries(sample_warp_with_flow PRIVATE optical_flow_sdk)
endif()

if(OPTICALFLOW_BUILD_SAMPLES AND OPTICALFLOW_ENABLE_OPENCL)
  add_executable(sample_calc_flow_opencl_device samples/calc_flow_opencl_device.cpp)
  target_link_libraries(sample_calc_flow_opencl_device PRIVATE optical_flow_sdk)
  add_executable(sample_fruc_opencl samples/fruc_opencl.cpp)
  target_link_libraries(sample_fruc_opencl PRIVATE optical_flow_sdk)
  add_executable(sample_fruc_video_opencl samples/fruc_video_opencl.cpp)
  target_link_libraries(sample_fruc_video_opencl PRIVATE optical_flow_sdk)
  find_library(OPTICALFLOW_LIBVA va)
  find_library(OPTICALFLOW_LIBVA_DRM va-drm)
  find_path(OPTICALFLOW_LIBVA_INCLUDE va/va.h)
  if(OPTICALFLOW_LIBVA AND OPTICALFLOW_LIBVA_DRM AND OPTICALFLOW_LIBVA_INCLUDE)
    add_executable(sample_va_import_opencl samples/va_import_opencl.cpp)
    target_include_directories(sample_va_import_opencl PRIVATE ${OPTICALFLOW_LIBVA_INCLUDE})
    target_link_libraries(sample_va_import_opencl PRIVATE optical_flow_sdk
                          ${OPTICALFLOW_LIBVA} ${OPTICALFLOW_LIBVA_DRM})
  else()
    message(STATUS "libva not found; skipping sample_va_import_opencl")
  endif()
endif()

if(OPTICALFLOW_BUILD_BENCHMARKS AND OPTICALFLOW_ENABLE_CPU)
  add_executable(microbench_cpu benchmarks/microbench_cpu.cpp)
  target_link_libraries(microbench_cpu PRIVATE optical_flow_sdk)
  add_executable(eval_flow_epe benchmarks/eval_flow_epe.cpp)
  target_link_libraries(eval_flow_epe PRIVATE optical_flow_sdk)
endif()

if(OPTICALFLOW_BUILD_BENCHMARKS AND OPTICALFLOW_ENABLE_OPENCL)
  add_executable(microbench_opencl benchmarks/microbench_opencl.cpp)
  add_executable(microbench_opencl_resident benchmarks/microbench_opencl_resident.cpp)
  target_link_libraries(microbench_opencl_resident PRIVATE optical_flow_sdk)
  target_link_libraries(microbench_opencl PRIVATE optical_flow_sdk)
endif()

if(OPTICALFLOW_BUILD_BENCHMARKS AND OPTICALFLOW_ENABLE_SYCL)
  add_executable(microbench_sycl benchmarks/microbench_sycl.cpp)
  target_link_libraries(microbench_sycl PRIVATE optical_flow_sdk)
  add_executable(microbench_sycl_resident benchmarks/microbench_sycl_resident.cpp)
  target_link_libraries(microbench_sycl_resident PRIVATE optical_flow_sdk)
endif()

if(OPTICALFLOW_BUILD_PYTHON)
  find_package(pybind11 CONFIG QUIET)
  if(NOT pybind11_FOUND)
    include(FetchContent)
    FetchContent_Declare(
      pybind11
      GIT_REPOSITORY https://github.com/pybind/pybind11.git
      GIT_TAG v2.13.6
      GIT_SHALLOW TRUE)
    FetchContent_MakeAvailable(pybind11)
  endif()
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
  # Wheel (SKBUILD) or deb/system install of the Python package.
  if(OPTICALFLOW_INSTALL_PYTHON OR SKBUILD)
    if(SKBUILD)
      set(_OF_PY_DEST optical_flow_sdk)
    else()
      # Debian / prefix-relative (works with DESTDIR staging).
      set(_OF_PY_DEST lib/python3/dist-packages/optical_flow_sdk)
    endif()
    install(TARGETS optical_flow_sdk_py
      LIBRARY DESTINATION ${_OF_PY_DEST}
      RUNTIME DESTINATION ${_OF_PY_DEST}
      ARCHIVE DESTINATION ${_OF_PY_DEST})
    install(FILES python/optical_flow_sdk/__init__.py DESTINATION ${_OF_PY_DEST})
  endif()
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
