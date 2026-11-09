cmake_minimum_required(VERSION 3.16)
project(gvaopticalflow_standalone LANGUAGES C CXX)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_C_STANDARD 99)

find_package(PkgConfig REQUIRED)
pkg_check_modules(GST REQUIRED IMPORTED_TARGET gstreamer-1.0 gstreamer-base-1.0 gstreamer-video-1.0)
find_package(OpenMP)
find_package(Threads REQUIRED)
find_package(optical_flow_sdk REQUIRED CONFIG)

add_library(gstgvaopticalflow MODULE
  gvaopticalflow.cpp
  vendor/gva_tensor_meta.c
)
set_target_properties(gstgvaopticalflow PROPERTIES
  OUTPUT_NAME "gvaopticalflow"
  PREFIX "libgst"
  BUILD_RPATH "${GST_LIBRARY_DIRS}"
  INSTALL_RPATH "${GST_LIBRARY_DIRS}"
)
target_include_directories(gstgvaopticalflow PRIVATE ${CMAKE_CURRENT_SOURCE_DIR} ${CMAKE_CURRENT_SOURCE_DIR}/vendor)
target_link_libraries(gstgvaopticalflow PRIVATE PkgConfig::GST optical_flow_sdk::optical_flow_sdk)
if(OpenMP_CXX_FOUND)
  target_link_libraries(gstgvaopticalflow PRIVATE OpenMP::OpenMP_CXX)
endif()
target_compile_options(gstgvaopticalflow PRIVATE -Wno-deprecated-declarations)
