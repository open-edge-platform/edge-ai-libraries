/*******************************************************************************
 * Copyright (C) 2020 Intel Corporation
 *
 * SPDX-License-Identifier: MIT
 ******************************************************************************/

#ifndef _GST_UDF_LOADER_H_
#define _GST_UDF_LOADER_H_

#include "callback.h"
#include <gst/base/gstbasetransform.h>
#include <gst/video/video.h>
#include <gst/gst.h>

G_BEGIN_DECLS

#define GST_TYPE_UDF_LOADER (gst_udf_loader_get_type())
#define GST_UDF_LOADER(obj) (G_TYPE_CHECK_INSTANCE_CAST((obj), GST_TYPE_UDF_LOADER, GstUDFLoader))

typedef struct _GstUDFLoader GstUDFLoader;
typedef struct _GstUDFLoaderClass GstUDFLoaderClass;

struct _GstUDFLoader
{
    GstBaseTransform base_udfloader;
    gchar *config;
    GstVideoInfo *info;
    GstVideoInfo *renegotiation_info;
    struct Manager *manager;
};

struct _GstUDFLoaderClass
{
    GstBaseTransformClass base_udfloader_class;
};

GType gst_udf_loader_get_type(void);

G_END_DECLS

#endif