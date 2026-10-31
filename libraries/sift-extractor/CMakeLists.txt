cmake_minimum_required(VERSION 3.20)
project(sift_extractor VERSION 0.1.0 LANGUAGES CXX)

include(CTest)

option(SIFT_ENABLE_SYCL "Build the SYCL reference backend" ON)
option(SIFT_ENABLE_OPENCL "Build the OpenCL device discovery backend" OFF)
option(SIFT_BUILD_TESTS "Build SIFT component tests" ${BUILD_TESTING})

if(SIFT_ENABLE_OPENCL)
  find_path(SIFT_OPENCL_INCLUDE_DIR CL/cl.h
    HINTS
      "$ENV{ONEAPI_ROOT}/compiler/latest/include"
      /opt/intel/oneapi/compiler/latest/include
      /opt/intel/oneapi/compiler/2025.3/include
    REQUIRED
  )
  find_library(SIFT_OPENCL_LIBRARY
    NAMES OpenCL libOpenCL.so.1
    REQUIRED
  )

  add_library(sift_opencl_runtime STATIC
    src/opencl/opencl_device.cpp
    src/opencl/opencl_gaussian_blur.cpp
    src/opencl/opencl_gaussian_pyramid.cpp
    src/opencl/opencl_extrema.cpp
  )
  target_compile_features(sift_opencl_runtime PUBLIC cxx_std_17)
  target_include_directories(sift_opencl_runtime
    PUBLIC
      $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
      $<INSTALL_INTERFACE:include>
    PRIVATE ${SIFT_OPENCL_INCLUDE_DIR}
  )
  target_include_directories(sift_opencl_runtime PRIVATE
    ${CMAKE_CURRENT_SOURCE_DIR}/src/opencl
  )
  target_link_libraries(sift_opencl_runtime PUBLIC ${SIFT_OPENCL_LIBRARY})

  if(SIFT_BUILD_TESTS)
    add_executable(test_sift_opencl_device tests/opencl/test_opencl_device.cpp)
    target_link_libraries(test_sift_opencl_device PRIVATE sift_opencl_runtime)
    add_test(NAME sift_opencl_runtime.device_discovery
      COMMAND test_sift_opencl_device)

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

  if(SIFT_BUILD_TESTS)
    add_executable(test_sift_sycl_kernels
      tests/sycl_reference/test_sycl_kernels.cpp
    )
    target_link_libraries(test_sift_sycl_kernels PRIVATE sift_sycl_reference)
    add_test(NAME sift_sycl_reference.kernels COMMAND test_sift_sycl_kernels)

    add_executable(test_sift_sycl_extract
      tests/sycl_reference/test_sift_extract.cpp
    )
    target_link_libraries(test_sift_sycl_extract PRIVATE sift_sycl_reference)
    add_test(NAME sift_sycl_reference.extract COMMAND test_sift_sycl_extract)

    add_executable(test_sift_sycl_match
      tests/sycl_reference/test_sift_match.cpp
    )
    target_link_libraries(test_sift_sycl_match PRIVATE sift_sycl_reference)
    add_test(NAME sift_sycl_reference.match COMMAND test_sift_sycl_match)
  endif()
endif()

if(SIFT_ENABLE_OPENCL)
  install(TARGETS sift_opencl_runtime EXPORT sift_extractorTargets
    ARCHIVE DESTINATION lib
  )
  install(FILES include/sift_extractor/opencl_device.hpp DESTINATION include/sift_extractor)
endif()

if(SIFT_ENABLE_SYCL)
  install(TARGETS sift_sycl_reference EXPORT sift_extractorTargets
    ARCHIVE DESTINATION lib
  )
  install(FILES
    src/sycl_reference/syclImage.h
    src/sycl_reference/syclSift.h
    src/sycl_reference/syclSiftD.h
    src/sycl_reference/syclSiftH.h
    src/sycl_reference/syclutils.h
    DESTINATION include/sift_extractor/sycl_reference
  )
endif()

if(SIFT_ENABLE_SYCL OR SIFT_ENABLE_OPENCL)
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
endif()
