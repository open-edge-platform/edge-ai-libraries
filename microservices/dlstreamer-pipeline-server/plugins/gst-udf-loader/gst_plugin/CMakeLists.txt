# ==============================================================================
# Copyright (C) 2018-2021 Intel Corporation
#
# SPDX-License-Identifier: MIT
# ==============================================================================

cmake_minimum_required (VERSION 3.1)

set (TARGET_NAME "gstudfloader")

find_package(PkgConfig REQUIRED)
find_package(UDFLoader REQUIRED)
find_package(IntelSafeString REQUIRED)
find_package(EIIUtils REQUIRED)
find_package(Python3 COMPONENTS Development NumPy REQUIRED)
find_package(EIIMsgEnv REQUIRED)
pkg_check_modules(GSTREAMER gstreamer-1.0>=1.16 REQUIRED)
pkg_check_modules(GSTVIDEO gstreamer-video-1.0>=1.16 REQUIRED)
pkg_check_modules(GSTALLOC gstreamer-allocators-1.0 REQUIRED)
pkg_check_modules(GLIB2 glib-2.0 REQUIRED)


# Include header directories
include_directories(
    ${EIIMsgEnv_INCLUDE}
    ${EIIUtils_INCLUDE}
    ${Python3_INCLUDE_DIRS}
    ${Python3_NumPy_INCLUDE_DIRS}
    ${IntelSafeString_INCLUDE})

file (GLOB MAIN_SRC
    ${CMAKE_CURRENT_SOURCE_DIR}/*.c
    ${CMAKE_CURRENT_SOURCE_DIR}/*.cpp
)

file (GLOB MAIN_HEADERS
     ${CMAKE_CURRENT_SOURCE_DIR}/*.h
)

add_library(${TARGET_NAME} SHARED ${MAIN_SRC} ${MAIN_HEADERS})


# FIXME: implicit declaration of tracer functions
target_compile_options(${TARGET_NAME} PRIVATE -Wno-error=implicit-function-declaration)

target_include_directories(${TARGET_NAME}
PUBLIC
    ${CMAKE_CURRENT_SOURCE_DIR}
    gst_plugin
PRIVATE
    ${GSTREAMER_INCLUDE_DIRS}
    ${UDFLoader_INCLUDE}
)

target_link_libraries(${TARGET_NAME}
    PUBLIC
        ${UDFLoader_LIBRARIES}
        ${EIIMsgEnv_LIBRARIES}
        ${EIIUtils_LIBRARIES}
        ${Python3_LIBRARIES}
	dlstreamer_gst_meta
    PRIVATE
        ${GSTREAMER_LDFLAGS}
        ${GSTVIDEO_LDFLAGS}
        ${GLIB2_LIBRARIES}
        ${IntelSafeString_LIBRARIES}
        ${OpenCV_LIBRARIES}
    )


install(TARGETS ${TARGET_NAME} DESTINATION ${PLUGINS_INSTALL_PATH})
