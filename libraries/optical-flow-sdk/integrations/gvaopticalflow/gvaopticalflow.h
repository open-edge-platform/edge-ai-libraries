/*******************************************************************************
 * Copyright (C) 2026 Intel Corporation
 *
 * SPDX-License-Identifier: MIT
 ******************************************************************************/

#pragma once
#include <gst/base/gstbasetransform.h>
#include <gst/gst.h>

G_BEGIN_DECLS

typedef struct _GstGvaOpticalFlow GstGvaOpticalFlow;
typedef struct _GstGvaOpticalFlowClass GstGvaOpticalFlowClass;

#define GST_TYPE_GVA_OPTICAL_FLOW (gst_gva_optical_flow_get_type())
GType gst_gva_optical_flow_get_type(void);

#define GST_GVA_OPTICAL_FLOW(obj) (G_TYPE_CHECK_INSTANCE_CAST((obj), GST_TYPE_GVA_OPTICAL_FLOW, GstGvaOpticalFlow))
#define GST_GVA_OPTICAL_FLOW_CLASS(klass)                                                                              \
    (G_TYPE_CHECK_CLASS_CAST((klass), GST_TYPE_GVA_OPTICAL_FLOW, GstGvaOpticalFlowClass))
#define GST_IS_GVA_OPTICAL_FLOW(obj) (G_TYPE_CHECK_INSTANCE_TYPE((obj), GST_TYPE_GVA_OPTICAL_FLOW))
#define GST_IS_GVA_OPTICAL_FLOW_CLASS(klass) (G_TYPE_CHECK_CLASS_TYPE((klass), GST_TYPE_GVA_OPTICAL_FLOW))

G_END_DECLS
