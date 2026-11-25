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
#include <cmath>
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
    PROP_ATTACH_COST,
    PROP_EMIT_MOTION_ROIS,
    PROP_TRACK_MOTION_ROIS,
    PROP_ROI_BLOCK,
    PROP_ROI_MAG_THRESHOLD,
    PROP_TRACK_IOU_THRESHOLD
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

    // Lightweight IoU tracker for motion ROIs (gvatrack-compatible object_id prior).
    struct MotionTrack {
        int x = 0, y = 0, w = 0, h = 0;
        int id = 0;
        int missed = 0;
    };
    std::vector<MotionTrack> motion_tracks;
    int next_track_id = 1;
};

struct _GstGvaOpticalFlow {
    GstBaseTransform parent;
    GstVideoInfo vinfo;

    gchar *preset_str;
    gchar *device_str;
    gchar *algorithm_str;
    gboolean attach_cost;
    gboolean emit_motion_rois;
    gboolean track_motion_rois;
    gint roi_block;
    gdouble roi_mag_threshold;
    gdouble track_iou_threshold;
    gpointer va_dpy; // VADisplay when VAMemory context is provided

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

struct MotionDet {
    int x = 0, y = 0, w = 0, h = 0;
    double mag = 0.0;
    int track_id = 0; // 0 = unassigned
};

static double box_iou(int ax, int ay, int aw, int ah, int bx, int by, int bw, int bh) {
    const int x0 = std::max(ax, bx);
    const int y0 = std::max(ay, by);
    const int x1 = std::min(ax + aw, bx + bw);
    const int y1 = std::min(ay + ah, by + bh);
    const int iw = std::max(0, x1 - x0);
    const int ih = std::max(0, y1 - y0);
    const double inter = static_cast<double>(iw) * ih;
    if (inter <= 0.0)
        return 0.0;
    const double uni = static_cast<double>(aw) * ah + static_cast<double>(bw) * bh - inter;
    return uni > 0.0 ? inter / uni : 0.0;
}

// Greedy IoU association — zero-term imageless style prior for gvatrack / apps.
static void associate_motion_tracks(OpticalFlowContext *ctx, std::vector<MotionDet> &dets, double iou_thr) {
    std::vector<bool> track_used(ctx->motion_tracks.size(), false);
    std::vector<bool> det_used(dets.size(), false);

    for (std::size_t di = 0; di < dets.size(); ++di) {
        double best = iou_thr;
        int best_t = -1;
        for (std::size_t ti = 0; ti < ctx->motion_tracks.size(); ++ti) {
            if (track_used[ti])
                continue;
            const auto &t = ctx->motion_tracks[ti];
            const double iou = box_iou(dets[di].x, dets[di].y, dets[di].w, dets[di].h, t.x, t.y, t.w, t.h);
            if (iou > best) {
                best = iou;
                best_t = static_cast<int>(ti);
            }
        }
        if (best_t >= 0) {
            auto &t = ctx->motion_tracks[static_cast<std::size_t>(best_t)];
            t.x = dets[di].x;
            t.y = dets[di].y;
            t.w = dets[di].w;
            t.h = dets[di].h;
            t.missed = 0;
            dets[di].track_id = t.id;
            track_used[static_cast<std::size_t>(best_t)] = true;
            det_used[di] = true;
        }
    }

    for (std::size_t ti = 0; ti < ctx->motion_tracks.size(); ++ti) {
        if (!track_used[ti])
            ctx->motion_tracks[ti].missed += 1;
    }
    ctx->motion_tracks.erase(std::remove_if(ctx->motion_tracks.begin(), ctx->motion_tracks.end(),
                                            [](const OpticalFlowContext::MotionTrack &t) { return t.missed > 8; }),
                             ctx->motion_tracks.end());

    for (std::size_t di = 0; di < dets.size(); ++di) {
        if (det_used[di])
            continue;
        OpticalFlowContext::MotionTrack t;
        t.x = dets[di].x;
        t.y = dets[di].y;
        t.w = dets[di].w;
        t.h = dets[di].h;
        t.id = ctx->next_track_id++;
        t.missed = 0;
        dets[di].track_id = t.id;
        ctx->motion_tracks.push_back(t);
    }
}

// Motion ROIs as detection-shaped GstVideoRegionOfInterestMeta for gvatrack /
// gvawatermark. Optional IoU tracker assigns object_id (standalone prior).
static void attach_motion_rois(GstGvaOpticalFlow *self, GstBuffer *buf,
                               const optical_flow_sdk::FlowField &flow) {
    const bool emit = self->emit_motion_rois || self->track_motion_rois;
    if (!emit || flow.data.empty())
        return;

    const int bw = std::max(8, self->roi_block);
    const float thr = static_cast<float>(self->roi_mag_threshold);
    const int frame_w = flow.width > 0 ? flow.width : GST_VIDEO_INFO_WIDTH(&self->vinfo);
    const int frame_h = flow.height > 0 ? flow.height : GST_VIDEO_INFO_HEIGHT(&self->vinfo);
    if (frame_w <= 0 || frame_h <= 0)
        return;

    std::vector<MotionDet> dets;
    for (int by = 0; by + bw <= flow.height; by += bw) {
        for (int bx = 0; bx + bw <= flow.width; bx += bw) {
            double sum = 0.0;
            int n = 0;
            for (int y = by; y < by + bw; ++y) {
                for (int x = bx; x < bx + bw; ++x) {
                    sum += std::hypot(flow.dx(x, y), flow.dy(x, y));
                    ++n;
                }
            }
            if (n > 0 && (sum / n) >= thr) {
                MotionDet d;
                d.x = bx;
                d.y = by;
                d.w = bw;
                d.h = bw;
                d.mag = sum / n;
                dets.push_back(d);
            }
        }
    }

    if (self->track_motion_rois)
        associate_motion_tracks(self->ctx, dets, self->track_iou_threshold);

    for (const MotionDet &d : dets) {
        GstVideoRegionOfInterestMeta *meta = gst_buffer_add_video_region_of_interest_meta(
            buf, "optical-flow-motion", static_cast<guint>(d.x), static_cast<guint>(d.y),
            static_cast<guint>(d.w), static_cast<guint>(d.h));
        if (!meta)
            continue;

        // Match gvadetect / gvatrack detection tensor shape so convertRoisToDetectedObjects works.
        const double conf = std::clamp(d.mag / std::max(thr * 4.0, 1e-3), 0.0, 1.0);
        const double x_min = static_cast<double>(d.x) / frame_w;
        const double y_min = static_cast<double>(d.y) / frame_h;
        const double x_max = static_cast<double>(d.x + d.w) / frame_w;
        const double y_max = static_cast<double>(d.y + d.h) / frame_h;
        GstStructure *det = gst_structure_new(
            "detection", "confidence", G_TYPE_DOUBLE, conf, "label_id", G_TYPE_INT, 0, "x_min", G_TYPE_DOUBLE,
            x_min, "x_max", G_TYPE_DOUBLE, x_max, "y_min", G_TYPE_DOUBLE, y_min, "y_max", G_TYPE_DOUBLE, y_max,
            "model_name", G_TYPE_STRING, "optical-flow-sdk", "layer_name", G_TYPE_STRING, "motion-roi", NULL);
        gst_video_region_of_interest_meta_add_param(meta, det);

        if (d.track_id > 0) {
            GstStructure *oid =
                gst_structure_new("object_id", "id", G_TYPE_INT, d.track_id, NULL);
            gst_video_region_of_interest_meta_add_param(meta, oid);
        }
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
                attach_motion_rois(self, buf, flow);
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
    attach_motion_rois(self, buf, flow);

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
    case PROP_EMIT_MOTION_ROIS:
        self->emit_motion_rois = g_value_get_boolean(value);
        break;
    case PROP_TRACK_MOTION_ROIS:
        self->track_motion_rois = g_value_get_boolean(value);
        break;
    case PROP_ROI_BLOCK:
        self->roi_block = std::max(8, g_value_get_int(value));
        break;
    case PROP_ROI_MAG_THRESHOLD:
        self->roi_mag_threshold = std::max(0.0, g_value_get_double(value));
        break;
    case PROP_TRACK_IOU_THRESHOLD:
        self->track_iou_threshold = std::clamp(g_value_get_double(value), 0.0, 1.0);
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
    case PROP_EMIT_MOTION_ROIS:
        g_value_set_boolean(value, self->emit_motion_rois);
        break;
    case PROP_TRACK_MOTION_ROIS:
        g_value_set_boolean(value, self->track_motion_rois);
        break;
    case PROP_ROI_BLOCK:
        g_value_set_int(value, self->roi_block);
        break;
    case PROP_ROI_MAG_THRESHOLD:
        g_value_set_double(value, self->roi_mag_threshold);
        break;
    case PROP_TRACK_IOU_THRESHOLD:
        g_value_set_double(value, self->track_iou_threshold);
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
    self->emit_motion_rois = FALSE;
    self->track_motion_rois = FALSE;
    self->roi_block = 32;
    self->roi_mag_threshold = 1.0;
    self->track_iou_threshold = 0.3;
    self->va_dpy = nullptr;
    self->ctx = new OpticalFlowContext();
    gst_base_transform_set_in_place(GST_BASE_TRANSFORM(self), TRUE);
    gst_base_transform_set_passthrough(GST_BASE_TRANSFORM(self), FALSE);
}

static void gst_gva_optical_flow_set_context(GstElement *elem, GstContext *context) {
    GstGvaOpticalFlow *self = GST_GVA_OPTICAL_FLOW(elem);
    const gchar *ctype = context ? gst_context_get_context_type(context) : nullptr;
    if (ctype && g_strcmp0(ctype, "gst.va.display.handle") == 0) {
        const GstStructure *st = gst_context_get_structure(context);
        if (st && gst_structure_has_field(st, "va-display")) {
            self->va_dpy = g_value_get_pointer(gst_structure_get_value(st, "va-display"));
#if OPTICALFLOW_HAS_OPENCL
            try {
                optical_flow_sdk::opencl_set_va_display(self->va_dpy);
                GST_INFO_OBJECT(self, "Bound OpenCL context to VA display for media sharing");
            } catch (const std::exception &e) {
                GST_WARNING_OBJECT(self, "opencl_set_va_display: %s", e.what());
            }
#endif
        }
    }
    GST_ELEMENT_CLASS(gst_gva_optical_flow_parent_class)->set_context(elem, context);
}

static GstStaticPadTemplate sink_template = GST_STATIC_PAD_TEMPLATE(
    "sink", GST_PAD_SINK, GST_PAD_ALWAYS,
    GST_STATIC_CAPS("video/x-raw(memory:VAMemory), format=(string)NV12; "
                    "video/x-raw(memory:DMABuf), format=(string)NV12; " GST_VIDEO_CAPS_MAKE(
                        "{ GRAY8, NV12, NV21, RGB, BGR, RGBA, BGRA, RGBx, BGRx }")));

static GstStaticPadTemplate src_template = GST_STATIC_PAD_TEMPLATE(
    "src", GST_PAD_SRC, GST_PAD_ALWAYS,
    GST_STATIC_CAPS("video/x-raw(memory:VAMemory), format=(string)NV12; "
                    "video/x-raw(memory:DMABuf), format=(string)NV12; " GST_VIDEO_CAPS_MAKE(
                        "{ GRAY8, NV12, NV21, RGB, BGR, RGBA, BGRA, RGBx, BGRx }")));

static void gst_gva_optical_flow_class_init(GstGvaOpticalFlowClass *klass) {
    GObjectClass *gobject_class = G_OBJECT_CLASS(klass);
    GstElementClass *element_class = GST_ELEMENT_CLASS(klass);
    GstBaseTransformClass *base_class = GST_BASE_TRANSFORM_CLASS(klass);

    gobject_class->set_property = gst_gva_optical_flow_set_property;
    gobject_class->get_property = gst_gva_optical_flow_get_property;
    gobject_class->finalize = gst_gva_optical_flow_finalize;
    element_class->set_context = GST_DEBUG_FUNCPTR(gst_gva_optical_flow_set_context);

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
    g_object_class_install_property(
        gobject_class, PROP_EMIT_MOTION_ROIS,
        g_param_spec_boolean("emit-motion-rois", "Emit motion ROIs",
                             "Attach detection-shaped GstVideoRegionOfInterestMeta from flow "
                             "magnitude (gvatrack / gvawatermark consumers)",
                             FALSE, (GParamFlags)(G_PARAM_READWRITE | G_PARAM_STATIC_STRINGS)));
    g_object_class_install_property(
        gobject_class, PROP_TRACK_MOTION_ROIS,
        g_param_spec_boolean("track-motion-rois", "Track motion ROIs",
                             "IoU-associate motion ROIs across frames and attach object_id "
                             "(standalone gvatrack prior; also emits ROIs)",
                             FALSE, (GParamFlags)(G_PARAM_READWRITE | G_PARAM_STATIC_STRINGS)));
    g_object_class_install_property(
        gobject_class, PROP_ROI_BLOCK,
        g_param_spec_int("roi-block", "ROI block", "Block size (px) for emit-motion-rois grid", 8, 512, 32,
                         (GParamFlags)(G_PARAM_READWRITE | G_PARAM_STATIC_STRINGS)));
    g_object_class_install_property(
        gobject_class, PROP_ROI_MAG_THRESHOLD,
        g_param_spec_double("roi-mag-threshold", "ROI magnitude threshold",
                            "Mean |flow| (px/frame) to emit a motion ROI block", 0.0, 1000.0, 1.0,
                            (GParamFlags)(G_PARAM_READWRITE | G_PARAM_STATIC_STRINGS)));
    g_object_class_install_property(
        gobject_class, PROP_TRACK_IOU_THRESHOLD,
        g_param_spec_double("track-iou-threshold", "Track IoU threshold",
                            "Min IoU to associate a motion ROI with an existing track", 0.0, 1.0, 0.3,
                            (GParamFlags)(G_PARAM_READWRITE | G_PARAM_STATIC_STRINGS)));

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
