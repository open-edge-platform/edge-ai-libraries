# ==============================================================================
# Copyright (C) 2022-2025 Intel Corporation
#
# SPDX-License-Identifier: MIT
# ==============================================================================

set(TARGET_NAME "dlstreamer_opencl")

add_library(${TARGET_NAME} SHARED elements.cpp)
set_compile_flags(${TARGET_NAME})

target_link_libraries(${TARGET_NAME}
    PUBLIC
        opencl_tensor_normalize
    )

if(VA_FOUND)
    target_link_libraries(${TARGET_NAME}
    PUBLIC
        vaapi_to_opencl
    )
endif()

install(TARGETS ${TARGET_NAME} DESTINATION ${DLSTREAMER_PLUGINS_INSTALL_PATH})

add_library(${TARGET_NAME}_static STATIC elements.cpp)
set_compile_flags(${TARGET_NAME}_static)

target_link_libraries(${TARGET_NAME}_static
    PUBLIC
        opencl_tensor_normalize
    )

if(VA_FOUND)
    target_link_libraries(${TARGET_NAME}_static
    PUBLIC
        vaapi_to_opencl
    )
endif()

set_target_properties(${TARGET_NAME}_static PROPERTIES OUTPUT_NAME ${TARGET_NAME})
install(TARGETS ${TARGET_NAME}_static DESTINATION ${DLSTREAMER_PLUGINS_INSTALL_PATH})
