# ==============================================================================
# Copyright (C) 2022-2025 Intel Corporation
#
# SPDX-License-Identifier: MIT
# ==============================================================================

set(TARGET_NAME "dlstreamer_vaapi")

pkg_search_module(VA va libva REQUIRED)

add_library(${TARGET_NAME} SHARED elements.cpp)
set_compile_flags(${TARGET_NAME})

target_include_directories(${TARGET_NAME}
PUBLIC
    ${CMAKE_CURRENT_SOURCE_DIR}/../../..
)

target_link_directories(${TARGET_NAME} PUBLIC ${VA_LIBRARY_DIRS})

target_link_libraries(${TARGET_NAME}
PUBLIC
    dlstreamer_api
    vaapi_sync
    vaapi_batch_proc
)

install(TARGETS ${TARGET_NAME} DESTINATION ${DLSTREAMER_PLUGINS_INSTALL_PATH})

add_library(${TARGET_NAME}_static STATIC elements.cpp)
set_compile_flags(${TARGET_NAME}_static)

target_include_directories(${TARGET_NAME}_static
PUBLIC
    ${CMAKE_CURRENT_SOURCE_DIR}/../../..
)

target_link_directories(${TARGET_NAME}_static PUBLIC ${VA_LIBRARY_DIRS})

target_link_libraries(${TARGET_NAME}_static
PUBLIC
    dlstreamer_api
    vaapi_sync
    vaapi_batch_proc
)

set_target_properties(${TARGET_NAME}_static PROPERTIES OUTPUT_NAME ${TARGET_NAME})
install(TARGETS ${TARGET_NAME}_static DESTINATION ${DLSTREAMER_PLUGINS_INSTALL_PATH})
