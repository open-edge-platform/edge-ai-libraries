# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
cmake_minimum_required(VERSION 3.20)
project(sift_extractor VERSION 0.1.0 LANGUAGES CXX)

include(CTest)

option(SIFT_ENABLE_SYCL "Build the SYCL reference backend" ON)
option(SIFT_ENABLE_OPENCL "Build the OpenCL device discovery backend" OFF)
option(SIFT_BUILD_TESTS "Build SIFT component tests" ${BUILD_TESTING})
option(SIFT_ENABLE_OPENCV_VALIDATION "Build optional real-pair diagnostic tools" OFF)
option(SIFT_BUILD_SAMPLES "Build native SIFT sample applications" ON)
option(SIFT_BUILD_PYTHON "Build Python bindings (requires pybind11)" OFF)
option(SIFT_BUILD_OPENCV_ADAPTER
  "Build thin OpenCV type adapters around the core Extractor" OFF)

set(SIFT_EXTRACTOR_HAS_OPENCL 0)
set(SIFT_EXTRACTOR_HAS_SYCL 0)
set(SIFT_EXTRACTOR_HAS_OPENCV_ADAPTER 0)
if(SIFT_ENABLE_OPENCL)
  set(SIFT_EXTRACTOR_HAS_OPENCL 1)
endif()
if(SIFT_ENABLE_SYCL)
  set(SIFT_EXTRACTOR_HAS_SYCL 1)
endif()
if(SIFT_BUILD_OPENCV_ADAPTER)
  set(SIFT_EXTRACTOR_HAS_OPENCV_ADAPTER 1)
endif()

configure_file(
  ${CMAKE_CURRENT_SOURCE_DIR}/include/sift_extractor/version.hpp.in
  ${CMAKE_CURRENT_BINARY_DIR}/include/sift_extractor/version.hpp
  @ONLY
)
set(SIFT_GENERATED_INCLUDE_DIR ${CMAKE_CURRENT_BINARY_DIR}/include)

if(SIFT_ENABLE_OPENCL)
  find_path(SIFT_OPENCL_INCLUDE_DIR CL/cl.h
    HINTS
      "$ENV{ONEAPI_ROOT}/compiler/latest/include"
      /opt/intel/oneapi/compiler/latest/include
      /opt/intel/oneapi/compiler/2025.3/include
    REQUIRED
  )
  find_package(OpenCL REQUIRED)
  find_package(Threads REQUIRED)

  add_library(sift_opencl_runtime STATIC
    src/opencl/opencl_device.cpp
    src/opencl/opencl_gaussian_blur.cpp
    src/opencl/opencl_gaussian_pyramid.cpp
    src/opencl/opencl_extrema.cpp
    src/opencl/opencl_matcher.cpp
    src/opencl_extractor.cpp
  )
  target_compile_features(sift_opencl_runtime PUBLIC cxx_std_17)
  target_include_directories(sift_opencl_runtime
    PUBLIC
      $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
      $<BUILD_INTERFACE:${SIFT_GENERATED_INCLUDE_DIR}>
      $<INSTALL_INTERFACE:include>
    PRIVATE ${SIFT_OPENCL_INCLUDE_DIR}
  )
  target_include_directories(sift_opencl_runtime PRIVATE
    ${CMAKE_CURRENT_SOURCE_DIR}/src/opencl
  )
  # Link the imported OpenCL target so install exports stay portable (no
  # absolute host .so path embedded in the CMake interface).
  target_link_libraries(sift_opencl_runtime PUBLIC OpenCL::OpenCL Threads::Threads)
  set_target_properties(sift_opencl_runtime PROPERTIES POSITION_INDEPENDENT_CODE ON)

  if(SIFT_ENABLE_OPENCV_VALIDATION)
    find_package(OpenCV REQUIRED COMPONENTS core imgproc imgcodecs features2d)
    add_executable(validate_sift_pair benchmarks/validate_pair.cpp)
    target_include_directories(validate_sift_pair PRIVATE
      ${CMAKE_CURRENT_SOURCE_DIR}/src/opencl ${OpenCV_INCLUDE_DIRS})
    target_link_libraries(validate_sift_pair PRIVATE sift_opencl_runtime ${OpenCV_LIBS})
    if(SIFT_BUILD_TESTS)
      find_program(SIFT_JQ_EXECUTABLE jq)
      if(SIFT_JQ_EXECUTABLE)
        set(SIFT_VALIDATION_EXPORT_BACKENDS opencv opencl)
        if(SIFT_ENABLE_SYCL)
          list(APPEND SIFT_VALIDATION_EXPORT_BACKENDS sycl)
        endif()
        add_test(NAME sift_validation.quality_scoring
          COMMAND bash ${CMAKE_CURRENT_SOURCE_DIR}/tests/test_quality_scoring.sh
            $<TARGET_FILE:validate_sift_pair> ${SIFT_VALIDATION_EXPORT_BACKENDS})
      endif()
    endif()
  endif()

  if(SIFT_BUILD_TESTS)
    add_executable(test_sift_opencl_device tests/opencl/test_opencl_device.cpp)
    target_link_libraries(test_sift_opencl_device PRIVATE sift_opencl_runtime)
    add_test(NAME sift_opencl_runtime.device_discovery
      COMMAND test_sift_opencl_device)

    add_executable(test_sift_opencl_match tests/opencl/test_opencl_match.cpp)
    target_link_libraries(test_sift_opencl_match PRIVATE sift_opencl_runtime)
    add_test(NAME sift_opencl_runtime.match COMMAND test_sift_opencl_match)

    add_executable(test_sift_opencl_match_resident
      tests/opencl/test_opencl_match_resident.cpp)
    target_link_libraries(test_sift_opencl_match_resident PRIVATE sift_opencl_runtime)
    add_test(NAME sift_opencl_runtime.match_resident
      COMMAND test_sift_opencl_match_resident)

    add_executable(test_sift_opencl_gaussian_blur
      tests/opencl/test_opencl_gaussian_blur.cpp
    )
    target_include_directories(test_sift_opencl_gaussian_blur PRIVATE
      ${CMAKE_CURRENT_SOURCE_DIR}/src/opencl
    )
    target_link_libraries(test_sift_opencl_gaussian_blur PRIVATE
      sift_opencl_runtime
    )
    add_test(NAME sift_opencl_runtime.gaussian_blur
      COMMAND test_sift_opencl_gaussian_blur)

    add_executable(test_sift_opencl_dog tests/opencl/test_opencl_dog.cpp)
    target_include_directories(test_sift_opencl_dog PRIVATE
      ${CMAKE_CURRENT_SOURCE_DIR}/src/opencl
    )
    target_link_libraries(test_sift_opencl_dog PRIVATE sift_opencl_runtime)
    add_test(NAME sift_opencl_runtime.dog COMMAND test_sift_opencl_dog)

    add_executable(test_sift_opencl_downsample
      tests/opencl/test_opencl_downsample.cpp
    )
    target_include_directories(test_sift_opencl_downsample PRIVATE
      ${CMAKE_CURRENT_SOURCE_DIR}/src/opencl
    )
    target_link_libraries(test_sift_opencl_downsample PRIVATE sift_opencl_runtime)
    add_test(NAME sift_opencl_runtime.downsample
      COMMAND test_sift_opencl_downsample)

    add_executable(test_sift_opencl_gaussian_pyramid
      tests/opencl/test_opencl_gaussian_pyramid.cpp
    )
    target_include_directories(test_sift_opencl_gaussian_pyramid PRIVATE
      ${CMAKE_CURRENT_SOURCE_DIR}/src/opencl
    )
    target_link_libraries(test_sift_opencl_gaussian_pyramid PRIVATE
      sift_opencl_runtime
    )
    add_test(NAME sift_opencl_runtime.gaussian_pyramid
      COMMAND test_sift_opencl_gaussian_pyramid)

    add_executable(test_sift_opencl_extrema tests/opencl/test_opencl_extrema.cpp)
    target_include_directories(test_sift_opencl_extrema PRIVATE
      ${CMAKE_CURRENT_SOURCE_DIR}/src/opencl
    )
    target_link_libraries(test_sift_opencl_extrema PRIVATE sift_opencl_runtime)
    add_test(NAME sift_opencl_runtime.extrema COMMAND test_sift_opencl_extrema)

    add_executable(test_sift_opencl_refinement
      tests/opencl/test_opencl_refinement.cpp
    )
    target_include_directories(test_sift_opencl_refinement PRIVATE
      ${CMAKE_CURRENT_SOURCE_DIR}/src/opencl
    )
    target_link_libraries(test_sift_opencl_refinement PRIVATE sift_opencl_runtime)
    add_test(NAME sift_opencl_runtime.refinement
      COMMAND test_sift_opencl_refinement)
  endif()
endif()

if(SIFT_ENABLE_SYCL)
  if(NOT CMAKE_CXX_COMPILER_ID STREQUAL "IntelLLVM")
    message(FATAL_ERROR
      "SIFT_ENABLE_SYCL requires the Intel oneAPI DPC++ compiler (icpx). "
      "Configure with -DCMAKE_CXX_COMPILER=icpx or disable this backend.")
  endif()

  add_library(sift_sycl_reference STATIC
    src/sycl_reference/syclImage.cpp
    src/sycl_reference/syclSiftH.cpp
    src/sycl_reference/syclSiftD.cpp
    src/sycl_reference/syclMatchingCore.cpp
  )
  target_compile_features(sift_sycl_reference PUBLIC cxx_std_17)
  target_include_directories(sift_sycl_reference
    PUBLIC
      $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/src/sycl_reference>
      $<INSTALL_INTERFACE:include/sift_extractor/sycl_reference>
  )
  target_compile_options(sift_sycl_reference PUBLIC -fsycl -fsycl-targets=spir64)
  target_link_options(sift_sycl_reference PUBLIC -fsycl -fsycl-targets=spir64)
  set_target_properties(sift_sycl_reference PROPERTIES POSITION_INDEPENDENT_CODE ON)

  add_library(sift_sycl_extractor STATIC src/sycl_context.cpp)
  target_compile_features(sift_sycl_extractor PUBLIC cxx_std_17)
  target_include_directories(sift_sycl_extractor PUBLIC
    $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
    $<BUILD_INTERFACE:${SIFT_GENERATED_INCLUDE_DIR}>
    $<INSTALL_INTERFACE:include>)
  target_link_libraries(sift_sycl_extractor PUBLIC sift_sycl_reference)
  set_target_properties(sift_sycl_extractor PROPERTIES POSITION_INDEPENDENT_CODE ON)

  if(TARGET validate_sift_pair)
    target_compile_definitions(validate_sift_pair PRIVATE SIFT_VALIDATE_SYCL)
    target_link_libraries(validate_sift_pair PRIVATE sift_sycl_extractor)
  endif()
  if(TARGET sift_opencl_runtime AND OpenCV_FOUND)
    add_executable(resolution_ladder_bench benchmarks/resolution_ladder_bench.cpp)
    target_include_directories(resolution_ladder_bench PRIVATE
      ${CMAKE_CURRENT_SOURCE_DIR}/include
      ${CMAKE_CURRENT_SOURCE_DIR}/src/sycl_reference
      ${SIFT_GENERATED_INCLUDE_DIR}
      ${OpenCV_INCLUDE_DIRS})
    target_link_libraries(resolution_ladder_bench PRIVATE
      sift_opencl_runtime sift_sycl_reference ${OpenCV_LIBS})
    add_executable(match_opt_sweep benchmarks/match_opt_sweep.cpp)
    target_include_directories(match_opt_sweep PRIVATE
      ${CMAKE_CURRENT_SOURCE_DIR}/src/sycl_reference
      ${OpenCV_INCLUDE_DIRS})
    target_link_libraries(match_opt_sweep PRIVATE sift_sycl_reference ${OpenCV_LIBS})
  endif()

  if(SIFT_BUILD_TESTS)
    add_executable(test_sift_sycl_kernels
      tests/sycl_reference/test_sycl_kernels.cpp
    )
    target_link_libraries(test_sift_sycl_kernels PRIVATE sift_sycl_reference)
    add_test(NAME sift_sycl_reference.kernels COMMAND test_sift_sycl_kernels)

    add_executable(test_sift_sycl_extract
      tests/sycl_reference/test_sift_extract.cpp
    )
    target_link_libraries(test_sift_sycl_extract PRIVATE sift_sycl_extractor)
    add_test(NAME sift_sycl_reference.extract COMMAND test_sift_sycl_extract)

    add_executable(test_sift_sycl_match
      tests/sycl_reference/test_sift_match.cpp
    )
    target_link_libraries(test_sift_sycl_match PRIVATE sift_sycl_reference)
    add_test(NAME sift_sycl_reference.match COMMAND test_sift_sycl_match)
  endif()
endif()

if(SIFT_ENABLE_OPENCL OR SIFT_ENABLE_SYCL)
  add_library(sift_extractor STATIC src/extractor.cpp)
  target_compile_features(sift_extractor PUBLIC cxx_std_17)
  target_include_directories(sift_extractor PUBLIC
    $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
    $<BUILD_INTERFACE:${SIFT_GENERATED_INCLUDE_DIR}>
    $<INSTALL_INTERFACE:include>)
  set_target_properties(sift_extractor PROPERTIES POSITION_INDEPENDENT_CODE ON)
  set(SIFT_PKGCONFIG_LIBS "-lsift_extractor")
  set(SIFT_PKGCONFIG_CFLAGS "")
  if(SIFT_ENABLE_OPENCL)
    target_link_libraries(sift_extractor PUBLIC sift_opencl_runtime)
    string(APPEND SIFT_PKGCONFIG_LIBS " -lsift_opencl_runtime -lOpenCL")
  endif()
  if(SIFT_ENABLE_SYCL)
    target_link_libraries(sift_extractor PUBLIC sift_sycl_extractor)
    string(APPEND SIFT_PKGCONFIG_LIBS " -lsift_sycl_extractor -lsift_sycl_reference")
    string(APPEND SIFT_PKGCONFIG_CFLAGS " -fsycl -fsycl-targets=spir64")
  endif()

  if(SIFT_BUILD_SAMPLES)
    add_executable(extract_and_match samples/extract_and_match.cpp)
    target_link_libraries(extract_and_match PRIVATE sift_extractor)
    add_executable(time_sift_extract samples/time_sift_extract.cpp)
    target_link_libraries(time_sift_extract PRIVATE sift_extractor)
    add_executable(soak_sift_extract samples/soak_sift_extract.cpp)
    target_link_libraries(soak_sift_extract PRIVATE sift_extractor)
    find_package(Threads REQUIRED)
    target_link_libraries(soak_sift_extract PRIVATE Threads::Threads)
  endif()

  if(SIFT_BUILD_OPENCV_ADAPTER)
    find_package(OpenCV REQUIRED COMPONENTS core)
    add_library(sift_opencv_adapter STATIC src/opencv_adapter.cpp)
    target_compile_features(sift_opencv_adapter PUBLIC cxx_std_17)
    target_include_directories(sift_opencv_adapter PUBLIC
      $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
      $<BUILD_INTERFACE:${SIFT_GENERATED_INCLUDE_DIR}>
      $<INSTALL_INTERFACE:include>
      ${OpenCV_INCLUDE_DIRS})
    target_link_libraries(sift_opencv_adapter PUBLIC sift_extractor ${OpenCV_LIBS})
    set_target_properties(sift_opencv_adapter PROPERTIES POSITION_INDEPENDENT_CODE ON)
    if(SIFT_BUILD_SAMPLES)
      add_executable(extract_sift_opencv samples/extract_sift_opencv.cpp)
      target_link_libraries(extract_sift_opencv PRIVATE sift_opencv_adapter)
    endif()
    if(SIFT_BUILD_TESTS)
      add_executable(test_opencv_adapter tests/test_opencv_adapter.cpp)
      target_link_libraries(test_opencv_adapter PRIVATE sift_opencv_adapter)
      add_test(NAME sift_opencv_adapter.conversion COMMAND test_opencv_adapter)
    endif()
  endif()

  if(SIFT_BUILD_PYTHON)
    include(FetchContent)
    FetchContent_Declare(
      pybind11
      GIT_REPOSITORY https://github.com/pybind/pybind11.git
      GIT_TAG v2.13.6
    )
    FetchContent_MakeAvailable(pybind11)
    # Extension lives inside the sift_extractor package as _native.*.so so the
    # pure-Python __init__.py can document GPU stack deps and wrap ImportError.
    pybind11_add_module(sift_extractor_py MODULE python/sift_extractor_bindings.cpp)
    set_target_properties(sift_extractor_py PROPERTIES OUTPUT_NAME _native)
    target_link_libraries(sift_extractor_py PRIVATE sift_extractor)
    target_include_directories(sift_extractor_py PRIVATE ${SIFT_GENERATED_INCLUDE_DIR})
  endif()
endif()

set(SIFT_INSTALL_TARGETS)
if(SIFT_ENABLE_OPENCL)
  list(APPEND SIFT_INSTALL_TARGETS sift_opencl_runtime)
  install(FILES
    include/sift_extractor/opencl_device.hpp
    include/sift_extractor/opencl_extractor.hpp
    include/sift_extractor/opencl_matcher.hpp
    DESTINATION include/sift_extractor)
endif()
if(SIFT_ENABLE_SYCL)
  list(APPEND SIFT_INSTALL_TARGETS sift_sycl_reference sift_sycl_extractor)
  install(FILES include/sift_extractor/sycl_extractor.hpp DESTINATION include/sift_extractor)
  install(FILES
    src/sycl_reference/syclImage.h
    src/sycl_reference/syclSift.h
    src/sycl_reference/syclSiftD.h
    src/sycl_reference/syclSiftH.h
    src/sycl_reference/syclutils.h
    DESTINATION include/sift_extractor/sycl_reference
  )
  install(FILES
    LICENSES/MIT.txt
    third_party_programs.txt
    DESTINATION share/sift_extractor
  )
endif()
if(TARGET sift_extractor)
  list(APPEND SIFT_INSTALL_TARGETS sift_extractor)
endif()
if(TARGET extract_and_match)
  list(APPEND SIFT_INSTALL_TARGETS extract_and_match)
endif()
if(TARGET time_sift_extract)
  list(APPEND SIFT_INSTALL_TARGETS time_sift_extract)
endif()
if(TARGET soak_sift_extract)
  list(APPEND SIFT_INSTALL_TARGETS soak_sift_extract)
endif()
if(TARGET sift_opencv_adapter)
  list(APPEND SIFT_INSTALL_TARGETS sift_opencv_adapter)
endif()
if(TARGET extract_sift_opencv)
  list(APPEND SIFT_INSTALL_TARGETS extract_sift_opencv)
endif()

if(SIFT_INSTALL_TARGETS)
  install(TARGETS ${SIFT_INSTALL_TARGETS} EXPORT sift_extractorTargets
    ARCHIVE DESTINATION lib
    LIBRARY DESTINATION lib
    RUNTIME DESTINATION bin
  )
  install(FILES
    include/sift_extractor/features.hpp
    include/sift_extractor/backend.hpp
    include/sift_extractor/extractor.hpp
    ${CMAKE_CURRENT_BINARY_DIR}/include/sift_extractor/version.hpp
    DESTINATION include/sift_extractor
  )
  if(TARGET sift_opencv_adapter)
    install(FILES include/sift_extractor/opencv_adapter.hpp
      DESTINATION include/sift_extractor)
  endif()
  if(TARGET sift_extractor_py)
    install(TARGETS sift_extractor_py LIBRARY DESTINATION lib/python3/dist-packages/sift_extractor)
    install(FILES
      python/sift_extractor/__init__.py
      python/sift_extractor/py.typed
      DESTINATION lib/python3/dist-packages/sift_extractor)
    install(FILES python/time_sift_extract.py DESTINATION share/sift_extractor)
  endif()

  include(CMakePackageConfigHelpers)
  install(EXPORT sift_extractorTargets
    NAMESPACE sift_extractor::
    DESTINATION lib/cmake/sift_extractor
  )
  configure_package_config_file(
    cmake/sift_extractorConfig.cmake.in
    ${CMAKE_CURRENT_BINARY_DIR}/sift_extractorConfig.cmake
    INSTALL_DESTINATION lib/cmake/sift_extractor
  )
  write_basic_package_version_file(
    ${CMAKE_CURRENT_BINARY_DIR}/sift_extractorConfigVersion.cmake
    VERSION ${PROJECT_VERSION}
    COMPATIBILITY SameMajorVersion
  )
  install(FILES
    ${CMAKE_CURRENT_BINARY_DIR}/sift_extractorConfig.cmake
    ${CMAKE_CURRENT_BINARY_DIR}/sift_extractorConfigVersion.cmake
    DESTINATION lib/cmake/sift_extractor
  )
  configure_file(
    cmake/sift_extractor.pc.in
    ${CMAKE_CURRENT_BINARY_DIR}/sift_extractor.pc
    @ONLY
  )
  install(FILES ${CMAKE_CURRENT_BINARY_DIR}/sift_extractor.pc
    DESTINATION lib/pkgconfig)
endif()
