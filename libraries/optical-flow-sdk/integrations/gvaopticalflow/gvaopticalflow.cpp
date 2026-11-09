/*******************************************************************************
 * Copyright (C) 2026 Intel Corporation
 *
 * SPDX-License-Identifier: MIT
 ******************************************************************************/

#include "gvaopticalflow.h"

#include <gst/base/gstbasetransform.h>
#include <gst/gst.h>
#include <gst/video/video.h>

#include "gva_tensor_meta.h"

#include <optical_flow_sdk/optical_flow.hpp>
#include <optical_flow_sdk/version.hpp>

#if OPTICALFLOW_HAS_OPENCL
#include <optical_flow_sdk/opencl_optical_flow.hpp>
#endif

#include <algorithm>
#include <cstring>
#include <memory>
#include <stdexcept>
#include <string>
#include <vector>

GST_DEBUG_CATEGORY_STATIC(gst_gva_optical_flow_debug);
#define GST_CAT_DEFAULT gst_gva_optical_flow_debug

enum {
    PROP_0,
    PROP_PRESET,
    PROP_DEVICE,
    PROP_ALGORITHM,
    PROP_ATTACH_COST
};

#define DEFAULT_PRESET "fast"
#define DEFAULT_DEVICE "GPU"
#define DEFAULT_ALGORITHM "dis"

struct OpticalFlowContext {
    optical_flow_sdk::Preset preset = optical_flow_sdk::Preset::Fast;
    optical_flow_sdk::Backend backend = optical_flow_sdk::Backend::Auto;
    optical_flow_sdk::Algorithm algorithm = optical_flow_sdk::Algorithm::Dis;

    std::unique_ptr<optical_flow_sdk::OpticalFlow> flow_cpu;
#if OPTICALFLOW_HAS_OPENCL
    std::unique_ptr<optical_flow_sdk::OpenCLOpticalFlow> flow_ocl;
    optical_flow_sdk::OpenCLU8Image prev_dev;
    optical_flow_sdk::OpenCLU8Image next_dev;
    optical_flow_sdk::OpenCLFlowBuffer flow_dev;
    bool ocl_bufs_ready = false;
#endif

    std::vector<std::uint8_t> prev_gray;
    std::vector<std::uint8_t> next_gray;
    int gray_w = 0;
    int gray_h = 0;
    bool have_prev = false;
    guint64 frame_index = 0;
};

struct _GstGvaOpticalFlow {
    GstBaseTransform parent;
    GstVideoInfo vinfo;

    gchar *preset_str;
    gchar *device_str;
    gchar *algorithm_str;
    gboolean attach_cost;

    OpticalFlowContext *ctx;
};

struct _GstGvaOpticalFlowClass {
    GstBaseTransformClass parent_class;
};

G_DEFINE_TYPE(GstGvaOpticalFlow, gst_gva_optical_flow, GST_TYPE_BASE_TRANSFORM);

static void copy_buffer_to_structure(GstStructure *structure, const void *buffer, size_t size) {
    GVariant *v = g_variant_new_fixed_array(G_VARIANT_TYPE_BYTE, buffer, size, 1);
    gsize n_elem = 0;
    gst_structure_set(structure, "data_buffer", G_TYPE_VARIANT, v, "data", G_TYPE_POINTER,
                      g_variant_get_fixed_array(v, &n_elem, 1), NULL);
}

static void set_dims_nhwc_hw2(GstStructure *s, int h, int w) {
    GValueArray *arr = g_value_array_new(4);
    GValue v = G_VALUE_INIT;
    g_value_init(&v, G_TYPE_UINT);
    const guint dims[4] = {1u, static_cast<guint>(h), static_cast<guint>(w), 2u};
    for (guint d : dims) {
        g_value_set_uint(&v, d);
        g_value_array_append(arr, &v);
    }
    gst_structure_set_array(s, "dims", arr);
    g_value_array_free(arr);
    g_value_unset(&v);
}

static optical_flow_sdk::Preset parse_preset(const gchar *s) {
    try {
        return optical_flow_sdk::preset_from_name(s ? s : DEFAULT_PRESET);
    } catch (...) {
        return optical_flow_sdk::Preset::Fast;
    }
}

static optical_flow_sdk::Algorithm parse_algorithm(const gchar *s) {
    try {
        return optical_flow_sdk::algorithm_from_name(s ? s : DEFAULT_ALGORITHM);
    } catch (...) {
        return optical_flow_sdk::Algorithm::Dis;
    }
}

static optical_flow_sdk::Backend parse_device(const gchar *s) {
    if (!s)
        return optical_flow_sdk::Backend::Auto;
    if (g_ascii_strcasecmp(s, "CPU") == 0)
        return optical_flow_sdk::Backend::Cpu;
    if (g_ascii_strcasecmp(s, "GPU") == 0 || g_ascii_strcasecmp(s, "AUTO") == 0)
        return optical_flow_sdk::Backend::Auto;
    if (g_ascii_strcasecmp(s, "OPENCL") == 0)
        return optical_flow_sdk::Backend::OpenCL;
    return optical_flow_sdk::Backend::Auto;
}

static gboolean extract_gray(GstGvaOpticalFlow *self, GstBuffer *buf, std::vector<std::uint8_t> &out) {
    GstVideoFrame frame;
    if (!gst_video_frame_map(&frame, &self->vinfo, buf, GST_MAP_READ))
        return FALSE;

    const int w = GST_VIDEO_FRAME_WIDTH(&frame);
    const int h = GST_VIDEO_FRAME_HEIGHT(&frame);
    out.resize(static_cast<size_t>(w) * static_cast<size_t>(h));

    const GstVideoFormat fmt = GST_VIDEO_FRAME_FORMAT(&frame);
    if (fmt == GST_VIDEO_FORMAT_GRAY8) {
        const guint8 *src = static_cast<const guint8 *>(GST_VIDEO_FRAME_PLANE_DATA(&frame, 0));
        const gint stride = GST_VIDEO_FRAME_PLANE_STRIDE(&frame, 0);
        for (int y = 0; y < h; ++y)
            std::memcpy(out.data() + static_cast<size_t>(y) * w, src + static_cast<size_t>(y) * stride, w);
    } else if (fmt == GST_VIDEO_FORMAT_NV12 || fmt == GST_VIDEO_FORMAT_NV21) {
        const guint8 *src = static_cast<const guint8 *>(GST_VIDEO_FRAME_PLANE_DATA(&frame, 0));
        const gint stride = GST_VIDEO_FRAME_PLANE_STRIDE(&frame, 0);
        for (int y = 0; y < h; ++y)
            std::memcpy(out.data() + static_cast<size_t>(y) * w, src + static_cast<size_t>(y) * stride, w);
    } else if (fmt == GST_VIDEO_FORMAT_RGB || fmt == GST_VIDEO_FORMAT_BGR) {
        const guint8 *src = static_cast<const guint8 *>(GST_VIDEO_FRAME_PLANE_DATA(&frame, 0));
        const gint stride = GST_VIDEO_FRAME_PLANE_STRIDE(&frame, 0);
        const int channels = 3;
        for (int y = 0; y < h; ++y) {
            const guint8 *row = src + static_cast<size_t>(y) * stride;
            guint8 *dst = out.data() + static_cast<size_t>(y) * w;
            for (int x = 0; x < w; ++x) {
                const guint8 *px = row + x * channels;
                // BT.601 luma approximation
                dst[x] = static_cast<guint8>((77 * px[0] + 150 * px[1] + 29 * px[2]) >> 8);
            }
        }
    } else if (fmt == GST_VIDEO_FORMAT_RGBA || fmt == GST_VIDEO_FORMAT_BGRA || fmt == GST_VIDEO_FORMAT_RGBx ||
               fmt == GST_VIDEO_FORMAT_BGRx) {
        const guint8 *src = static_cast<const guint8 *>(GST_VIDEO_FRAME_PLANE_DATA(&frame, 0));
        const gint stride = GST_VIDEO_FRAME_PLANE_STRIDE(&frame, 0);
        for (int y = 0; y < h; ++y) {
            const guint8 *row = src + static_cast<size_t>(y) * stride;
            guint8 *dst = out.data() + static_cast<size_t>(y) * w;
            for (int x = 0; x < w; ++x) {
                const guint8 *px = row + x * 4;
                dst[x] = static_cast<guint8>((77 * px[0] + 150 * px[1] + 29 * px[2]) >> 8);
            }
        }
    } else {
        GST_ERROR_OBJECT(self, "Unsupported video format %s", gst_video_format_to_string(fmt));
        gst_video_frame_unmap(&frame);
        return FALSE;
    }

    self->ctx->gray_w = w;
    self->ctx->gray_h = h;
    gst_video_frame_unmap(&frame);
    return TRUE;
}

static void attach_flow_meta(GstGvaOpticalFlow *self, GstBuffer *buf, const optical_flow_sdk::FlowField &flow,
                             const optical_flow_sdk::CostMap *cost) {
    GstGVATensorMeta *meta = GST_GVA_TENSOR_META_ADD(buf);
    if (!meta || !meta->data)
        return;

    gst_structure_set(meta->data, "model_name", G_TYPE_STRING, "optical-flow-sdk", "layer_name", G_TYPE_STRING, "flow",
                      "format", G_TYPE_STRING, "optical_flow_dense", "precision", G_TYPE_INT,
                      static_cast<gint>(GVA_PRECISION_FP32), "layout", G_TYPE_INT, static_cast<gint>(GVA_LAYOUT_NHWC),
                      "rank", G_TYPE_INT, 4, "element_id", G_TYPE_STRING, GST_ELEMENT_NAME(self), "preset",
                      G_TYPE_STRING, optical_flow_sdk::preset_name(self->ctx->preset), "algorithm", G_TYPE_STRING,
                      optical_flow_sdk::algorithm_name(self->ctx->algorithm), "backend", G_TYPE_STRING,
                      optical_flow_sdk::backend_name(self->ctx->backend), NULL);
    set_dims_nhwc_hw2(meta->data, flow.height, flow.width);
    copy_buffer_to_structure(meta->data, flow.data.data(), flow.data.size() * sizeof(float));

    if (cost && self->attach_cost && !cost->data.empty()) {
        GstGVATensorMeta *cmeta = GST_GVA_TENSOR_META_ADD(buf);
        if (!cmeta || !cmeta->data)
            return;
        gst_structure_set(cmeta->data, "model_name", G_TYPE_STRING, "optical-flow-sdk", "layer_name", G_TYPE_STRING,
                          "cost", "format", G_TYPE_STRING, "optical_flow_cost", "precision", G_TYPE_INT,
                          static_cast<gint>(GVA_PRECISION_U8), "layout", G_TYPE_INT, static_cast<gint>(GVA_LAYOUT_NHWC),
                          "rank", G_TYPE_INT, 2, "element_id", G_TYPE_STRING, GST_ELEMENT_NAME(self), NULL);
        GValueArray *arr = g_value_array_new(2);
        GValue v = G_VALUE_INIT;
        g_value_init(&v, G_TYPE_UINT);
        g_value_set_uint(&v, static_cast<guint>(cost->height));
        g_value_array_append(arr, &v);
        g_value_set_uint(&v, static_cast<guint>(cost->width));
        g_value_array_append(arr, &v);
        gst_structure_set_array(cmeta->data, "dims", arr);
        g_value_array_free(arr);
        g_value_unset(&v);
        copy_buffer_to_structure(cmeta->data, cost->data.data(), cost->data.size());
    }
}

static gboolean ensure_engine(GstGvaOpticalFlow *self) {
    try {
        self->ctx->preset = parse_preset(self->preset_str);
        self->ctx->algorithm = parse_algorithm(self->algorithm_str);
        self->ctx->backend = parse_device(self->device_str);
        self->ctx->backend = optical_flow_sdk::resolve_backend(self->ctx->backend);

#if OPTICALFLOW_HAS_OPENCL
        if (self->ctx->backend == optical_flow_sdk::Backend::OpenCL && self->ctx->algorithm == optical_flow_sdk::Algorithm::Dis) {
            if (!self->ctx->flow_ocl)
                self->ctx->flow_ocl = std::make_unique<optical_flow_sdk::OpenCLOpticalFlow>(self->ctx->preset);
            self->ctx->flow_cpu.reset();
            return TRUE;
        }
#endif
        if (!self->ctx->flow_cpu)
            self->ctx->flow_cpu =
                std::make_unique<optical_flow_sdk::OpticalFlow>(self->ctx->backend, self->ctx->preset, self->ctx->algorithm);
#if OPTICALFLOW_HAS_OPENCL
        self->ctx->flow_ocl.reset();
        self->ctx->ocl_bufs_ready = false;
#endif
        return TRUE;
    } catch (const std::exception &e) {
        GST_ELEMENT_ERROR(self, LIBRARY, INIT, ("optical-flow-sdk init failed"), ("%s", e.what()));
        return FALSE;
    }
}

#if OPTICALFLOW_HAS_OPENCL
// Map luma plane as ImageView (NV12/GRAY8). Caller must keep GstVideoFrame mapped.
static gboolean luma_view_from_frame(GstVideoFrame *frame, optical_flow_sdk::ImageView *view, int *w, int *h) {
    const GstVideoFormat fmt = GST_VIDEO_FRAME_FORMAT(frame);
    *w = GST_VIDEO_FRAME_WIDTH(frame);
    *h = GST_VIDEO_FRAME_HEIGHT(frame);
    if (fmt != GST_VIDEO_FORMAT_GRAY8 && fmt != GST_VIDEO_FORMAT_NV12 && fmt != GST_VIDEO_FORMAT_NV21)
        return FALSE;
    view->data = static_cast<const std::uint8_t *>(GST_VIDEO_FRAME_PLANE_DATA(frame, 0));
    view->width = *w;
    view->height = *h;
    view->stride = static_cast<std::size_t>(GST_VIDEO_FRAME_PLANE_STRIDE(frame, 0));
    return TRUE;
}
#endif

static GstFlowReturn gst_gva_optical_flow_transform_ip(GstBaseTransform *base, GstBuffer *buf) {
    GstGvaOpticalFlow *self = GST_GVA_OPTICAL_FLOW(base);
    if (!ensure_engine(self))
        return GST_FLOW_ERROR;

    ++self->ctx->frame_index;
    optical_flow_sdk::FlowField flow;
    optical_flow_sdk::CostMap cost;

    try {
#if OPTICALFLOW_HAS_OPENCL
        // OpenCL DIS: map Y in-place, strided upload (WriteBufferRect), device ping-pong.
        // Only one H2D of the new frame; prev stays on GPU. Flow D2H for meta v0 only.
        if (self->ctx->flow_ocl && !self->attach_cost) {
            GstVideoFrame frame;
            if (!gst_video_frame_map(&frame, &self->vinfo, buf, GST_MAP_READ))
                return GST_FLOW_ERROR;
            optical_flow_sdk::ImageView luma{};
            int w = 0, h = 0;
            if (!luma_view_from_frame(&frame, &luma, &w, &h)) {
                gst_video_frame_unmap(&frame);
                // RGB(A) etc.: fall back to packed gray extract path below.
            } else {
                self->ctx->gray_w = w;
                self->ctx->gray_h = h;
                if (!self->ctx->ocl_bufs_ready || self->ctx->prev_dev.width() != w ||
                    self->ctx->prev_dev.height() != h) {
                    self->ctx->prev_dev = self->ctx->flow_ocl->create_u8_image(w, h);
                    self->ctx->next_dev = self->ctx->flow_ocl->create_u8_image(w, h);
                    self->ctx->flow_dev = self->ctx->flow_ocl->create_flow_buffer(w, h);
                    self->ctx->ocl_bufs_ready = true;
                    self->ctx->have_prev = false;
                }
                if (!self->ctx->have_prev) {
                    self->ctx->flow_ocl->upload_u8(self->ctx->prev_dev, luma);
                    self->ctx->flow_ocl->finish();
                    self->ctx->have_prev = true;
                    gst_video_frame_unmap(&frame);
                    return GST_FLOW_OK;
                }
                self->ctx->flow_ocl->upload_u8(self->ctx->next_dev, luma);
                self->ctx->flow_ocl->calc_device(self->ctx->prev_dev, self->ctx->next_dev, self->ctx->flow_dev);
                self->ctx->flow_ocl->download_flow(self->ctx->flow_dev, flow);
                std::swap(self->ctx->prev_dev, self->ctx->next_dev);
                gst_video_frame_unmap(&frame);

                if (!gst_buffer_is_writable(buf))
                    buf = gst_buffer_make_writable(buf);
                attach_flow_meta(self, buf, flow, nullptr);
                return GST_FLOW_OK;
            }
        }
#endif
        if (!extract_gray(self, buf, self->ctx->next_gray))
            return GST_FLOW_ERROR;

        if (!self->ctx->have_prev) {
            self->ctx->prev_gray.swap(self->ctx->next_gray);
            self->ctx->have_prev = true;
            return GST_FLOW_OK;
        }

        optical_flow_sdk::ImageView prev_view{self->ctx->prev_gray.data(), self->ctx->gray_w, self->ctx->gray_h, 0};
        optical_flow_sdk::ImageView next_view{self->ctx->next_gray.data(), self->ctx->gray_w, self->ctx->gray_h, 0};

#if OPTICALFLOW_HAS_OPENCL
        if (self->ctx->flow_ocl) {
            self->ctx->flow_ocl->calc(prev_view, next_view, flow, cost);
        } else
#endif
        {
            if (self->attach_cost)
                self->ctx->flow_cpu->calc(prev_view, next_view, flow, cost);
            else
                self->ctx->flow_cpu->calc(prev_view, next_view, flow);
        }
    } catch (const std::exception &e) {
        GST_ELEMENT_ERROR(self, LIBRARY, FAILED, ("optical flow calc failed"), ("%s", e.what()));
        return GST_FLOW_ERROR;
    }

    if (!gst_buffer_is_writable(buf))
        buf = gst_buffer_make_writable(buf);
    attach_flow_meta(self, buf, flow, self->attach_cost ? &cost : nullptr);

    self->ctx->prev_gray.swap(self->ctx->next_gray);
    return GST_FLOW_OK;
}

static gboolean gst_gva_optical_flow_set_caps(GstBaseTransform *base, GstCaps *incaps, GstCaps *outcaps) {
    (void)outcaps;
    GstGvaOpticalFlow *self = GST_GVA_OPTICAL_FLOW(base);
    if (!gst_video_info_from_caps(&self->vinfo, incaps))
        return FALSE;
    self->ctx->have_prev = false;
#if OPTICALFLOW_HAS_OPENCL
    self->ctx->ocl_bufs_ready = false;
#endif
    return TRUE;
}

static void gst_gva_optical_flow_set_property(GObject *object, guint prop_id, const GValue *value, GParamSpec *pspec) {
    GstGvaOpticalFlow *self = GST_GVA_OPTICAL_FLOW(object);
    switch (prop_id) {
    case PROP_PRESET:
        g_free(self->preset_str);
        self->preset_str = g_value_dup_string(value);
        self->ctx->flow_cpu.reset();
#if OPTICALFLOW_HAS_OPENCL
        self->ctx->flow_ocl.reset();
        self->ctx->ocl_bufs_ready = false;
#endif
        break;
    case PROP_DEVICE:
        g_free(self->device_str);
        self->device_str = g_value_dup_string(value);
        self->ctx->flow_cpu.reset();
#if OPTICALFLOW_HAS_OPENCL
        self->ctx->flow_ocl.reset();
        self->ctx->ocl_bufs_ready = false;
#endif
        break;
    case PROP_ALGORITHM:
        g_free(self->algorithm_str);
        self->algorithm_str = g_value_dup_string(value);
        self->ctx->flow_cpu.reset();
#if OPTICALFLOW_HAS_OPENCL
        self->ctx->flow_ocl.reset();
        self->ctx->ocl_bufs_ready = false;
#endif
        break;
    case PROP_ATTACH_COST:
        self->attach_cost = g_value_get_boolean(value);
        break;
    default:
        G_OBJECT_WARN_INVALID_PROPERTY_ID(object, prop_id, pspec);
    }
}

static void gst_gva_optical_flow_get_property(GObject *object, guint prop_id, GValue *value, GParamSpec *pspec) {
    GstGvaOpticalFlow *self = GST_GVA_OPTICAL_FLOW(object);
    switch (prop_id) {
    case PROP_PRESET:
        g_value_set_string(value, self->preset_str);
        break;
    case PROP_DEVICE:
        g_value_set_string(value, self->device_str);
        break;
    case PROP_ALGORITHM:
        g_value_set_string(value, self->algorithm_str);
        break;
    case PROP_ATTACH_COST:
        g_value_set_boolean(value, self->attach_cost);
        break;
    default:
        G_OBJECT_WARN_INVALID_PROPERTY_ID(object, prop_id, pspec);
    }
}

static void gst_gva_optical_flow_finalize(GObject *object) {
    GstGvaOpticalFlow *self = GST_GVA_OPTICAL_FLOW(object);
    g_free(self->preset_str);
    g_free(self->device_str);
    g_free(self->algorithm_str);
    delete self->ctx;
    self->ctx = nullptr;
    G_OBJECT_CLASS(gst_gva_optical_flow_parent_class)->finalize(object);
}

static void gst_gva_optical_flow_init(GstGvaOpticalFlow *self) {
    gst_video_info_init(&self->vinfo);
    self->preset_str = g_strdup(DEFAULT_PRESET);
    self->device_str = g_strdup(DEFAULT_DEVICE);
    self->algorithm_str = g_strdup(DEFAULT_ALGORITHM);
    self->attach_cost = FALSE;
    self->ctx = new OpticalFlowContext();
    gst_base_transform_set_in_place(GST_BASE_TRANSFORM(self), TRUE);
    gst_base_transform_set_passthrough(GST_BASE_TRANSFORM(self), FALSE);
}

static GstStaticPadTemplate sink_template =
    GST_STATIC_PAD_TEMPLATE("sink", GST_PAD_SINK, GST_PAD_ALWAYS,
                            GST_STATIC_CAPS(GST_VIDEO_CAPS_MAKE("{ GRAY8, NV12, NV21, RGB, BGR, RGBA, BGRA, RGBx, BGRx }")));

static GstStaticPadTemplate src_template =
    GST_STATIC_PAD_TEMPLATE("src", GST_PAD_SRC, GST_PAD_ALWAYS,
                            GST_STATIC_CAPS(GST_VIDEO_CAPS_MAKE("{ GRAY8, NV12, NV21, RGB, BGR, RGBA, BGRA, RGBx, BGRx }")));

static void gst_gva_optical_flow_class_init(GstGvaOpticalFlowClass *klass) {
    GObjectClass *gobject_class = G_OBJECT_CLASS(klass);
    GstElementClass *element_class = GST_ELEMENT_CLASS(klass);
    GstBaseTransformClass *base_class = GST_BASE_TRANSFORM_CLASS(klass);

    gobject_class->set_property = gst_gva_optical_flow_set_property;
    gobject_class->get_property = gst_gva_optical_flow_get_property;
    gobject_class->finalize = gst_gva_optical_flow_finalize;

    g_object_class_install_property(
        gobject_class, PROP_PRESET,
        g_param_spec_string("preset", "Preset", "Optical-flow quality/speed preset: slow|medium|fast", DEFAULT_PRESET,
                            (GParamFlags)(G_PARAM_READWRITE | G_PARAM_STATIC_STRINGS)));
    g_object_class_install_property(
        gobject_class, PROP_DEVICE,
        g_param_spec_string("device", "Device", "Compute device: GPU|CPU|AUTO (GPU maps to OpenCL when available)",
                            DEFAULT_DEVICE, (GParamFlags)(G_PARAM_READWRITE | G_PARAM_STATIC_STRINGS)));
    g_object_class_install_property(
        gobject_class, PROP_ALGORITHM,
        g_param_spec_string("algorithm", "Algorithm", "Dense algorithm: dis|farneback|sea-raft", DEFAULT_ALGORITHM,
                            (GParamFlags)(G_PARAM_READWRITE | G_PARAM_STATIC_STRINGS)));
    g_object_class_install_property(
        gobject_class, PROP_ATTACH_COST,
        g_param_spec_boolean("attach-cost", "Attach cost", "Also attach NVOFA-shaped cost map as GstGVATensorMeta",
                             FALSE, (GParamFlags)(G_PARAM_READWRITE | G_PARAM_STATIC_STRINGS)));

    gst_element_class_set_static_metadata(element_class, "Optical Flow (Intel Optical Flow SDK)", "Filter/Analyzer/Video",
                                          "Dense optical flow via optical-flow-sdk; emits GstGVATensorMeta (flow)",
                                          "Intel Corporation");
    gst_element_class_add_static_pad_template(element_class, &sink_template);
    gst_element_class_add_static_pad_template(element_class, &src_template);

    base_class->set_caps = GST_DEBUG_FUNCPTR(gst_gva_optical_flow_set_caps);
    base_class->transform_ip = GST_DEBUG_FUNCPTR(gst_gva_optical_flow_transform_ip);

    GST_DEBUG_CATEGORY_INIT(gst_gva_optical_flow_debug, "gvaopticalflow", 0, "Intel optical flow element");
}

static gboolean plugin_init(GstPlugin *plugin) {
    return gst_element_register(plugin, "gvaopticalflow", GST_RANK_NONE, GST_TYPE_GVA_OPTICAL_FLOW);
}

#define PACKAGE "gvaopticalflow"

GST_PLUGIN_DEFINE(GST_VERSION_MAJOR, GST_VERSION_MINOR, gvaopticalflow, "Intel Optical Flow SDK GStreamer element",
                  plugin_init, "0.1.0", "MIT", "dlstreamer", "https://github.com/open-edge-platform/dlstreamer")
