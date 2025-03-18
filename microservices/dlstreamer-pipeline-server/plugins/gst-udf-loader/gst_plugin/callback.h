/*******************************************************************************
 * Copyright (C) 2020 Intel Corporation
 *
 * SPDX-License-Identifier: MIT
 ******************************************************************************/

#pragma once

#include <gst/base/gstbasetransform.h>

#include "gst_udf_loader.h"

#ifdef __cplusplus
extern "C"
{
#endif
    struct _GstUDFLoader;
    typedef struct _GstUDFLoader GstUDFLoader;
    typedef struct Manager Manager;
    gboolean init_udfs(GstUDFLoader *udfloader);
    GstFlowReturn process_buffer(GstUDFLoader *udfloader, GstBuffer *buffer);
    void delete_udfs(GstUDFLoader *udfloader);

#ifdef __cplusplus
}
#endif
