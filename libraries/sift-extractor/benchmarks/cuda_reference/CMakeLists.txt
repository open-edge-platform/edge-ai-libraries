# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

cmake_minimum_required(VERSION 3.24)

if(NOT CUDASIFT_REFERENCE_SOURCE OR
   NOT EXISTS "${CUDASIFT_REFERENCE_SOURCE}/cudaSiftH.cu")
  message(FATAL_ERROR "Set CUDASIFT_REFERENCE_SOURCE to the pinned CudaSift source tree")
endif()

if(NOT DEFINED CMAKE_CUDA_ARCHITECTURES)
  set(CMAKE_CUDA_ARCHITECTURES 120 CACHE STRING "Reference GPU architectures")
endif()

project(SiftCudaReference LANGUAGES CXX CUDA)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CUDA_STANDARD 17)
set(CMAKE_CUDA_STANDARD_REQUIRED ON)

find_package(OpenCV 4 REQUIRED COMPONENTS core imgproc imgcodecs highgui)

add_library(cuda_reference STATIC
  "${CUDASIFT_REFERENCE_SOURCE}/cudaImage.cu"
  "${CUDASIFT_REFERENCE_SOURCE}/cudaSiftH.cu"
  "${CUDASIFT_REFERENCE_SOURCE}/matching.cu"
  "${CUDASIFT_REFERENCE_SOURCE}/geomFuncs.cpp"
)
target_include_directories(cuda_reference PUBLIC
  "${CUDASIFT_REFERENCE_SOURCE}" ${OpenCV_INCLUDE_DIRS})
target_link_libraries(cuda_reference PUBLIC ${OpenCV_LIBS})
target_compile_options(cuda_reference PRIVATE
  "$<$<COMPILE_LANGUAGE:CUDA>:--use_fast_math;-O3;-lineinfo>"
  "$<$<COMPILE_LANGUAGE:CXX>:-O2>")
set_target_properties(cuda_reference PROPERTIES
  CUDA_SEPARABLE_COMPILATION OFF POSITION_INDEPENDENT_CODE ON)

enable_testing()
foreach(test_name IN ITEMS extract match homography)
  set(test_source "${CUDASIFT_REFERENCE_SOURCE}/tests/test_${test_name}.cpp")
  set_source_files_properties("${test_source}" PROPERTIES LANGUAGE CUDA)
  add_executable("test_${test_name}" "${test_source}")
  target_link_libraries("test_${test_name}" PRIVATE cuda_reference)
  add_test(NAME "cuda_reference.${test_name}" COMMAND "test_${test_name}")
  set_tests_properties("cuda_reference.${test_name}" PROPERTIES
    WORKING_DIRECTORY "${CUDASIFT_REFERENCE_SOURCE}" TIMEOUT 120)
endforeach()