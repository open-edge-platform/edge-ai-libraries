# ==============================================================================
# Copyright (C) 2022-2025 Intel Corporation
#
# SPDX-License-Identifier: MIT
# ==============================================================================

set(TARGET_NAME "dlstreamer_openvino")

find_package(OpenVINO REQUIRED)

pkg_search_module(VA va libva REQUIRED)

add_library(${TARGET_NAME} SHARED elements.cpp)
set_compile_flags(${TARGET_NAME})

target_link_directories(${TARGET_NAME} PUBLIC ${VA_LIBRARY_DIRS})

target_link_libraries(${TARGET_NAME}
PRIVATE
    openvino::runtime
    logger
    dlstreamer_api
    openvino_inference
)

install(TARGETS ${TARGET_NAME} DESTINATION ${DLSTREAMER_PLUGINS_INSTALL_PATH})

add_library(${TARGET_NAME}_static STATIC elements.cpp)
set_compile_flags(${TARGET_NAME}_static)

target_link_directories(${TARGET_NAME}_static PUBLIC ${VA_LIBRARY_DIRS})

target_link_libraries(${TARGET_NAME}_static
PRIVATE
    openvino::runtime
    logger
    dlstreamer_api
    openvino_inference
)

set_target_properties(${TARGET_NAME}_static PROPERTIES OUTPUT_NAME ${TARGET_NAME})
install(TARGETS ${TARGET_NAME}_static DESTINATION ${DLSTREAMER_PLUGINS_INSTALL_PATH})
