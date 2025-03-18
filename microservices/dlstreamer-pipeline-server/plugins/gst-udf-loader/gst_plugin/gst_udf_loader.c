/*******************************************************************************
 * Copyright (C) 2020-2021 Intel Corporation
 *
 * SPDX-License-Identifier: MIT
 ******************************************************************************/

#include "gst_udf_loader.h"
#include <stdio.h>

#define ELEMENT_LONG_NAME "udf loader"
#define ELEMENT_DESCRIPTION "udf loader"

GST_DEBUG_CATEGORY_STATIC(gst_udf_loader_debug_category);
#define GST_CAT_DEFAULT gst_udf_loader_debug_category

enum
{
    PROP_0,
    PROP_CONFIG
};

#define DEFAULT_CONFIG NULL
/* prototypes */
static void gst_udf_loader_set_property(GObject *object, guint property_id, const GValue *value, GParamSpec *pspec);
static void gst_udf_loader_get_property(GObject *object, guint property_id, GValue *value, GParamSpec *pspec);
static gboolean gst_udf_loader_set_caps(GstBaseTransform *trans, GstCaps *incaps, GstCaps *outcaps);
static gboolean gst_udf_loader_start(GstBaseTransform *trans);
static void gst_udf_loader_dispose(GObject *object);
static void gst_udf_loader_finalize(GObject *object);

static GstFlowReturn gst_udf_loader_transform_ip(GstBaseTransform *trans, GstBuffer *buf);

/* class initialization */
static void gst_udf_loader_init(GstUDFLoader *udf_loader);

G_DEFINE_TYPE_WITH_CODE(GstUDFLoader, gst_udf_loader, GST_TYPE_BASE_TRANSFORM,
                        GST_DEBUG_CATEGORY_INIT(gst_udf_loader_debug_category, "udfloader", 0,
                                                "debug category for UDFLoader element"))

static void gst_udf_loader_class_init(GstUDFLoaderClass *klass)
{
    GObjectClass *gobject_class = G_OBJECT_CLASS(klass);
    GstBaseTransformClass *base_transform_class = GST_BASE_TRANSFORM_CLASS(klass);
    GstElementClass *element_class = GST_ELEMENT_CLASS(klass);

    gst_element_class_add_pad_template(
        element_class, gst_pad_template_new("src", GST_PAD_SRC, GST_PAD_ALWAYS, gst_caps_from_string("video/x-raw,format={RGB,BGR}")));
    gst_element_class_add_pad_template(
        element_class, gst_pad_template_new("sink", GST_PAD_SINK, GST_PAD_ALWAYS, gst_caps_from_string("video/x-raw,format={RGB,BGR}")));

    gst_element_class_set_static_metadata(element_class, ELEMENT_LONG_NAME, "Video", ELEMENT_DESCRIPTION,
                                          "Intel Corporation");
    gobject_class->set_property = gst_udf_loader_set_property;
    gobject_class->get_property = gst_udf_loader_get_property;
    gobject_class->dispose = gst_udf_loader_dispose;
    gobject_class->finalize = gst_udf_loader_finalize;
    base_transform_class->start = GST_DEBUG_FUNCPTR(gst_udf_loader_start);
    base_transform_class->set_caps = GST_DEBUG_FUNCPTR(gst_udf_loader_set_caps);
    base_transform_class->transform = NULL;
    base_transform_class->transform_ip = GST_DEBUG_FUNCPTR(gst_udf_loader_transform_ip);

    g_object_class_install_property(
        gobject_class, PROP_CONFIG,
        g_param_spec_string("config", "ConfigFilePath",
                            "Absolute path to udf config", DEFAULT_CONFIG, G_PARAM_READWRITE | G_PARAM_STATIC_STRINGS));
}

static void gst_udf_loader_init(GstUDFLoader *udfloader)
{
    GST_DEBUG_OBJECT(udfloader, "udf_loader_init");

    if (udfloader == NULL)
        return;

    udfloader->info = NULL;
    udfloader->renegotiation_info = NULL;
}

void gst_udf_loader_get_property(GObject *object, guint property_id, GValue *value, GParamSpec *pspec)
{
    GstUDFLoader *udfloader = GST_UDF_LOADER(object);
    GST_DEBUG_OBJECT(udfloader, "get_property");
    switch (property_id)
    {
    case PROP_CONFIG:
        g_value_set_string(value, udfloader->config);
        break;
    default:
        G_OBJECT_WARN_INVALID_PROPERTY_ID(object, property_id, pspec);
        break;
    }
}

void gst_udf_loader_set_property(GObject *object, guint property_id, const GValue *value, GParamSpec *pspec)
{
    GstUDFLoader *udfloader = GST_UDF_LOADER(object);
    GST_DEBUG_OBJECT(udfloader, "set_property");

    switch (property_id)
    {
    case PROP_CONFIG:
        g_free(udfloader->config);
        udfloader->config = g_value_dup_string(value);
        break;
    default:
        G_OBJECT_WARN_INVALID_PROPERTY_ID(object, property_id, pspec);
        break;
    }
}

static gboolean gst_udf_loader_start(GstBaseTransform *trans)
{
    GstUDFLoader *udfloader = GST_UDF_LOADER(trans);
    GST_DEBUG_OBJECT(udfloader, "start");
    if (udfloader->config == NULL)
    {
        GST_ELEMENT_ERROR(udfloader, RESOURCE, NOT_FOUND, ("'config' is not set"),
                          ("'config' property is not set"));
        return FALSE;
    }

    return init_udfs(udfloader);
}

static gboolean gst_udf_loader_set_caps(GstBaseTransform *trans, GstCaps *incaps, GstCaps *outcaps)
{
    GstUDFLoader *udfloader = GST_UDF_LOADER(trans);
    GST_DEBUG_OBJECT(udfloader, "set_caps");

    if (!udfloader->info)
    {
        udfloader->info = gst_video_info_new();
    }
    if (!udfloader->renegotiation_info)
    {
        udfloader->renegotiation_info = gst_video_info_new();
    }
    gst_video_info_from_caps(udfloader->renegotiation_info, incaps);
    gst_video_info_from_caps(udfloader->info, incaps);
    return TRUE;
}

void gst_udf_loader_dispose(GObject *object)
{
    GstUDFLoader *udfloader = GST_UDF_LOADER(object);

    /* clean up as possible.  may be called multiple times */
    GST_DEBUG_OBJECT(udfloader, "dispose");

    if (udfloader->info)
    {
        gst_video_info_free(udfloader->info);
        udfloader->info = NULL;
    }
    if (udfloader->renegotiation_info)
    {
        gst_video_info_free(udfloader->renegotiation_info);
        udfloader->renegotiation_info = NULL;
    }
    delete_udfs(udfloader);
    udfloader->manager = NULL;

    g_free(udfloader->config);
    udfloader->config = NULL;

    G_OBJECT_CLASS(gst_udf_loader_parent_class)->dispose(object);
}

void gst_udf_loader_finalize(GObject *object)
{
    GstUDFLoader *udfloader = GST_UDF_LOADER(object);

    GST_DEBUG_OBJECT(udfloader, "finalize");

    G_OBJECT_CLASS(gst_udf_loader_parent_class)->finalize(object);
}

static GstFlowReturn gst_udf_loader_transform_ip(GstBaseTransform *trans, GstBuffer *buf)
{
    GstUDFLoader *udfloader = GST_UDF_LOADER(trans);
    GST_DEBUG_OBJECT(udfloader, "transform_ip");

    return process_buffer(udfloader, buf);
}

static gboolean plugin_init(GstPlugin *plugin)
{
    if (!gst_element_register(plugin, "udfloader", GST_RANK_NONE, GST_TYPE_UDF_LOADER))
    {
        return FALSE;
    }
    return TRUE;
}

GST_PLUGIN_DEFINE(GST_VERSION_MAJOR, GST_VERSION_MINOR, udfloader, ELEMENT_DESCRIPTION, plugin_init, PLUGIN_VERSION,
                  PLUGIN_LICENSE, PACKAGE_NAME, GST_PACKAGE_ORIGIN)
