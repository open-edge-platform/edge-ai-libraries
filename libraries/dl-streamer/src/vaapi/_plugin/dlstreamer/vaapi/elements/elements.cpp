/*******************************************************************************
 * Copyright (C) 2022-2025 Intel Corporation
 *
 * SPDX-License-Identifier: MIT
 ******************************************************************************/

#include "vaapi_batch_proc.h"
#include "vaapi_sync.h"

extern "C" {

#if !(_MSC_VER)
DLS_EXPORT const dlstreamer::ElementDesc *dlstreamer_elements[] = { //
#else
const dlstreamer::ElementDesc *dlstreamer_elements[] = { //
#endif
    &vaapi_sync, &vaapi_batch_proc,
    //
    nullptr};
}
