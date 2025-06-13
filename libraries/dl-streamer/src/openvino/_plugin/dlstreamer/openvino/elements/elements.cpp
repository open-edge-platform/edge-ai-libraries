/*******************************************************************************
 * Copyright (C) 2022-2025 Intel Corporation
 *
 * SPDX-License-Identifier: MIT
 ******************************************************************************/

#include "openvino_inference.h"

extern "C" {

#if !(_MSC_VER)
DLS_EXPORT const dlstreamer::ElementDesc *dlstreamer_elements[] = { //
#else
const dlstreamer::ElementDesc *dlstreamer_elements[] = { //
#endif
    &openvino_tensor_inference, &openvino_video_inference, nullptr};
}
