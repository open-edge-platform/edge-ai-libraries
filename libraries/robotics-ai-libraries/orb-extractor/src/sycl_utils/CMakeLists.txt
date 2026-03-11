# Copyright (C) 2025 Intel Corporation
#
# SPDX-License-Identifier: Apache-2.0
set(CUR_LIB_TARGET SyclUtils)

string(APPEND CMAKE_CXX_FLAGS " -fsycl")

if(WIN32)
set(CMAKE_GENERATOR_TOOLSET "Intel(R) oneAPI DPC++ Compiler 2025")
set(CMAKE_CXX_FLAGS_RELEASE "-O3 /EHa")
set(CMAKE_WINDOWS_EXPORT_ALL_SYMBOLS ON)
else()
set(CMAKE_CXX_COMPILER icpx)
string(APPEND CMAKE_CXX_FLAGS " -fPIC")
endif()

file(GLOB LIB_SRC
  "src/*"
)
file(GLOB LIB_HDR
  "include/*.h"
)

add_library (${CUR_LIB_TARGET} SHARED
  ${LIB_SRC}
  ${LIB_HDR}
  )

target_compile_definitions(${CUR_LIB_TARGET} PRIVATE SYCL_UTILS_EXPORTS)

target_include_directories(${CUR_LIB_TARGET} PUBLIC
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  $<BUILD_INTERFACE:$ENV{ONEAPI_ROOT}/dpcpp-ct/latest/include>
)
