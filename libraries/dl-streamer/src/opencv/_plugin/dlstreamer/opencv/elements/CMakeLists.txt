# ==============================================================================
# Copyright (C) 2022-2025 Intel Corporation
#
# SPDX-License-Identifier: MIT
# ==============================================================================

set(TARGET_NAME "dlstreamer_opencv")

add_library(${TARGET_NAME} SHARED elements.cpp)
set_compile_flags(${TARGET_NAME})

target_link_libraries(${TARGET_NAME}
PUBLIC
    opencv_barcode_detector
    opencv_find_contours
    opencv_object_association
    opencv_tensor_normalize
    opencv_cropscale
    opencv_meta_overlay
    ${OpenCV_LIBS}
    dlstreamer_api
    opencv_remove_background
    tensor_postproc_human_pose
)

if (TARGET opencv_warp_affine) # available if DLS_HAVE_OPENCV_UMAT
    target_link_libraries(${TARGET_NAME} PUBLIC opencv_warp_affine)
endif()

install(TARGETS ${TARGET_NAME} DESTINATION ${DLSTREAMER_PLUGINS_INSTALL_PATH})

add_library(${TARGET_NAME}_static STATIC elements.cpp)
set_compile_flags(${TARGET_NAME}_static)

target_link_libraries(${TARGET_NAME}_static
PUBLIC
    opencv_barcode_detector
    opencv_find_contours
    opencv_object_association
    opencv_tensor_normalize
    opencv_cropscale
    opencv_meta_overlay
    ${OpenCV_LIBS}
    dlstreamer_api
    opencv_remove_background
    tensor_postproc_human_pose
)

if (TARGET opencv_warp_affine) # available if DLS_HAVE_OPENCV_UMAT
    target_link_libraries(${TARGET_NAME}_static PUBLIC opencv_warp_affine)
endif()

set_target_properties(${TARGET_NAME}_static PROPERTIES OUTPUT_NAME ${TARGET_NAME})
install(TARGETS ${TARGET_NAME}_static DESTINATION ${DLSTREAMER_PLUGINS_INSTALL_PATH})
