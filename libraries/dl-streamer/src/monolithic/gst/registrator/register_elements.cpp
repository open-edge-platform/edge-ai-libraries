/*******************************************************************************
 * Copyright (C) 2018-2025 Intel Corporation
 *
 * SPDX-License-Identifier: MIT
 ******************************************************************************/

#include "config.h"

#include <gst/gst.h>

#include "gstgvaaudiodetect.h"
#include "gstgvaclassify.h"
#include "gstgvadetect.h"
#include "gstgvainference.h"

#include "gstgvametaaggregate.h"
#include "gstgvametaconvert.h"
#include "gstgvatrack.h"
#include "gstgvawatermarkimpl.h"
#include "gvawatermark.h"
#include "inference_backend/logger.h"
#include "logger_functions.h"

#include "gva_json_meta.h"
#include "gva_tensor_meta.h"

#include "inference_backend/logger.h"
#include "logger_functions.h"

#include "gvametapublish.hpp"
#include "gvametapublishfile.hpp"

static gboolean plugin_init(GstPlugin *plugin) {
    set_log_function(GST_logger);

    if (!gst_element_register(plugin, "gvainference", GST_RANK_NONE, gst_gva_inference_get_type()))
        return FALSE;
    if (!gst_element_register(plugin, "gvadetect", GST_RANK_NONE, gst_gva_detect_get_type()))
        return FALSE;
    if (!gst_element_register(plugin, "gvaclassify", GST_RANK_NONE, gst_gva_classify_get_type()))
        return FALSE;
    if (!gst_element_register(plugin, "gvaaudiodetect", GST_RANK_NONE, gst_gva_audio_detect_get_type()))
        return FALSE;
    if (!gst_element_register(plugin, "gvatrack", GST_RANK_NONE, GST_TYPE_GVA_TRACK))
        return FALSE;
    if (!gst_element_register(plugin, "gvawatermark", GST_RANK_NONE, GST_TYPE_GVA_WATERMARK))
        return FALSE;
    if (!gst_element_register(plugin, "gvametaconvert", GST_RANK_NONE, GST_TYPE_GVA_META_CONVERT))
        return FALSE;
    if (!gst_element_register(plugin, "gvawatermarkimpl", GST_RANK_NONE, GST_TYPE_GVA_WATERMARK_IMPL))
        return FALSE;
    if (!gst_element_register(plugin, "gvametaaggregate", GST_RANK_NONE, GST_TYPE_GVA_META_AGGREGATE))
        return FALSE;
#if _MSC_VER
    if (!gst_element_register(plugin, "gvametapublish", GST_RANK_NONE, GST_TYPE_GVA_META_PUBLISH))
        return FALSE;
    if (!gst_element_register(plugin, "gvametapublishfile", GST_RANK_NONE, GST_TYPE_GVA_META_PUBLISH_FILE))
        return FALSE;
#endif

    // register metadata
    gst_gva_json_meta_get_info();
    gst_gva_json_meta_api_get_type();
    gst_gva_tensor_meta_get_info();
    gst_gva_tensor_meta_api_get_type();
    return TRUE;
}

GST_PLUGIN_DEFINE(GST_VERSION_MAJOR, GST_VERSION_MINOR, videoanalytics, PRODUCT_FULL_NAME " elements", plugin_init,
                  PLUGIN_VERSION, PLUGIN_LICENSE, PACKAGE_NAME, GST_PACKAGE_ORIGIN)
