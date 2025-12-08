/*******************************************************************************
 * Copyright (C) 2023-2025 Intel Corporation
 *
 * SPDX-License-Identifier: MIT
 ******************************************************************************/

#include "latency_tracer.h"
#include "latency_tracer_meta.h"
#include <map>
#include <mutex>
#include <string>
#include <tuple>
#include <vector>
using namespace std;

#define ELEMENT_DESCRIPTION "Latency tracer to calculate time it takes to process each frame for element and pipeline"
GST_DEBUG_CATEGORY_STATIC(latency_tracer_debug);
G_DEFINE_TYPE(LatencyTracer, latency_tracer, GST_TYPE_TRACER);

static GstTracerRecord *tr_pipeline;
static GstTracerRecord *tr_element;
static GstTracerRecord *tr_element_interval;
static GstTracerRecord *tr_pipeline_interval;
static guint ns_to_ms = 1000000;
static guint ms_to_s = 1000;
using BufferListArgs = tuple<LatencyTracer *, guint64, GstPad *>;
#define UNUSED(x) (void)(x)

static GQuark data_string = g_quark_from_static_string("latency_tracer");

// Structure to track statistics per source-sink branch
struct BranchStats {
    string source_name;
    string sink_name;
    GstElement *source_element;
    GstElement *sink_element;
    gdouble total;
    gdouble min;
    gdouble max;
    guint frame_count;
    gdouble interval_total;
    gdouble interval_min;
    gdouble interval_max;
    guint interval_frame_count;
    GstClockTime interval_init_time;
    GstClockTime first_frame_init_ts;
    mutex mtx;

    BranchStats() {
        total = 0;
        min = G_MAXUINT;
        max = 0;
        frame_count = 0;
        interval_total = 0;
        interval_min = G_MAXUINT;
        interval_max = 0;
        interval_frame_count = 0;
        interval_init_time = 0;
        first_frame_init_ts = 0;
        source_element = nullptr;
        sink_element = nullptr;
    }

    void reset_interval(GstClockTime now) {
        interval_total = 0;
        interval_min = G_MAXUINT;
        interval_max = 0;
        interval_init_time = now;
        interval_frame_count = 0;
    }

    void cal_log_pipeline_latency(guint64 ts, guint64 init_ts, gint interval) {
        lock_guard<mutex> guard(mtx);
        frame_count += 1;
        gdouble frame_latency = (gdouble)GST_CLOCK_DIFF(init_ts, ts) / ns_to_ms;
        gdouble pipeline_latency_ns = (gdouble)GST_CLOCK_DIFF(first_frame_init_ts, ts) / frame_count;
        gdouble pipeline_latency = pipeline_latency_ns / ns_to_ms;
        total += frame_latency;
        gdouble avg = total / frame_count;
        gdouble fps = 0;
        if (pipeline_latency > 0)
            fps = ms_to_s / pipeline_latency;

        if (frame_latency < min)
            min = frame_latency;
        if (frame_latency > max)
            max = frame_latency;

        // Log with source and sink names
        GST_TRACE("[Latency Tracer] Source: %s -> Sink: %s - Frame: %u, Latency: %.2f ms, Avg: %.2f ms, Min: %.2f "
                  "ms, Max: %.2f ms, Pipeline Latency: %.2f ms, FPS: %.2f",
                  source_name.c_str(), sink_name.c_str(), frame_count, frame_latency, avg, min, max, pipeline_latency,
                  fps);

        gst_tracer_record_log(tr_pipeline, source_name.c_str(), sink_name.c_str(), frame_latency, avg, min, max,
                              pipeline_latency, fps, frame_count);
        cal_log_pipeline_interval(ts, frame_latency, interval);
    }

    void cal_log_pipeline_interval(guint64 ts, gdouble frame_latency, gint interval) {
        interval_frame_count += 1;
        interval_total += frame_latency;
        if (frame_latency < interval_min)
            interval_min = frame_latency;
        if (frame_latency > interval_max)
            interval_max = frame_latency;
        gdouble ms = (gdouble)GST_CLOCK_DIFF(interval_init_time, ts) / ns_to_ms;
        if (ms >= interval) {
            gdouble pipeline_latency = ms / interval_frame_count;
            gdouble fps = ms_to_s / pipeline_latency;
            gdouble interval_avg = interval_total / interval_frame_count;
            GST_TRACE("[Latency Tracer Interval] Source: %s -> Sink: %s - Interval: %.2f ms, Avg: %.2f ms, Min: %.2f "
                      "ms, Max: %.2f ms",
                      source_name.c_str(), sink_name.c_str(), ms, interval_avg, interval_min, interval_max);
            gst_tracer_record_log(tr_pipeline_interval, source_name.c_str(), sink_name.c_str(), ms, interval_avg,
                                  interval_min, interval_max, pipeline_latency, fps);
            reset_interval(ts);
        }
    }
};

// Helper function to create a branch key
static string create_branch_key(GstElement *source, GstElement *sink) {
    if (!source || !sink)
        return "";
    return string(GST_ELEMENT_NAME(source)) + "->" + string(GST_ELEMENT_NAME(sink));
}

// Type-safe accessors for C++ objects stored in C struct
static map<string, BranchStats> *get_branch_stats_map(LatencyTracer *lt) {
    if (!lt->branch_stats) {
        lt->branch_stats = new map<string, BranchStats>();
    }
    return static_cast<map<string, BranchStats> *>(lt->branch_stats);
}

static vector<GstElement *> *get_sources_list(LatencyTracer *lt) {
    if (!lt->sources_list) {
        lt->sources_list = new vector<GstElement *>();
    }
    return static_cast<vector<GstElement *> *>(lt->sources_list);
}

static vector<GstElement *> *get_sinks_list(LatencyTracer *lt) {
    if (!lt->sinks_list) {
        lt->sinks_list = new vector<GstElement *>();
    }
    return static_cast<vector<GstElement *> *>(lt->sinks_list);
}

static void latency_tracer_constructed(GObject *object) {
    LatencyTracer *lt = LATENCY_TRACER(object);
    gchar *params, *tmp;
    GstStructure *params_struct = NULL;
    g_object_get(lt, "params", &params, NULL);
    if (!params)
        return;

    tmp = g_strdup_printf("latency_tracer,%s", params);
    params_struct = gst_structure_from_string(tmp, NULL);
    g_free(tmp);

    if (params_struct) {
        const gchar *flags;
        /* Read the flags if available */
        flags = gst_structure_get_string(params_struct, "flags");
        if (flags) {
            lt->flags = static_cast<LatencyTracerFlags>(0);
            GStrv split = g_strsplit(flags, "+", -1);
            for (gint i = 0; split[i]; i++) {
                if (g_str_equal(split[i], "pipeline"))
                    lt->flags = static_cast<LatencyTracerFlags>(lt->flags | LATENCY_TRACER_FLAG_PIPELINE);
                else if (g_str_equal(split[i], "element"))
                    lt->flags = static_cast<LatencyTracerFlags>(lt->flags | LATENCY_TRACER_FLAG_ELEMENT);
                else
                    GST_WARNING_OBJECT(lt, "Invalid latency tracer flags %s", split[i]);
            }
            g_strfreev(split);
        }
        gst_structure_get_int(params_struct, "interval", &lt->interval);
        GST_INFO_OBJECT(lt, "interval set to %d ms", lt->interval);
        gst_structure_free(params_struct);
    }
    g_free(params);
}

static void latency_tracer_finalize(GObject *object) {
    LatencyTracer *lt = LATENCY_TRACER(object);

    // Clean up C++ objects
    if (lt->branch_stats) {
        delete static_cast<map<string, BranchStats> *>(lt->branch_stats);
        lt->branch_stats = nullptr;
    }
    if (lt->sources_list) {
        delete static_cast<vector<GstElement *> *>(lt->sources_list);
        lt->sources_list = nullptr;
    }
    if (lt->sinks_list) {
        delete static_cast<vector<GstElement *> *>(lt->sinks_list);
        lt->sinks_list = nullptr;
    }

    G_OBJECT_CLASS(latency_tracer_parent_class)->finalize(object);
}

static void latency_tracer_class_init(LatencyTracerClass *klass) {
    GObjectClass *gobject_class = G_OBJECT_CLASS(klass);
    gobject_class->constructed = latency_tracer_constructed;
    gobject_class->finalize = latency_tracer_finalize;
    tr_pipeline = gst_tracer_record_new(
        "latency_tracer_pipeline.class", "source_name", GST_TYPE_STRUCTURE,
        gst_structure_new("value", "type", G_TYPE_GTYPE, G_TYPE_STRING, "description", G_TYPE_STRING,
                          "Source element name", NULL),
        "sink_name", GST_TYPE_STRUCTURE,
        gst_structure_new("value", "type", G_TYPE_GTYPE, G_TYPE_STRING, "description", G_TYPE_STRING,
                          "Sink element name", NULL),
        "frame_latency", GST_TYPE_STRUCTURE,
        gst_structure_new("value", "type", G_TYPE_GTYPE, G_TYPE_DOUBLE, "description", G_TYPE_STRING,
                          "current frame latency in ms", NULL),
        "avg", GST_TYPE_STRUCTURE,
        gst_structure_new("value", "type", G_TYPE_GTYPE, G_TYPE_DOUBLE, "description", G_TYPE_STRING,
                          "Average frame latency in ms", NULL),
        "min", GST_TYPE_STRUCTURE,
        gst_structure_new("value", "type", G_TYPE_GTYPE, G_TYPE_DOUBLE, "description", G_TYPE_STRING,
                          "Min Per frame latency in ms", NULL),
        "max", GST_TYPE_STRUCTURE,
        gst_structure_new("value", "type", G_TYPE_GTYPE, G_TYPE_DOUBLE, "description", G_TYPE_STRING,
                          "Max Per frame latency in ms", NULL),
        "latency", GST_TYPE_STRUCTURE,
        gst_structure_new("value", "type", G_TYPE_GTYPE, G_TYPE_DOUBLE, "description", G_TYPE_STRING,
                          "pipeline latency in ms(if frames dropped this may result in invalid value)", NULL),
        "fps", GST_TYPE_STRUCTURE,
        gst_structure_new("value", "type", G_TYPE_GTYPE, G_TYPE_DOUBLE, "description", G_TYPE_STRING,
                          "pipeline fps(if frames dropped this may result in invalid value)", NULL),
        "frame_num", GST_TYPE_STRUCTURE,
        gst_structure_new("value", "type", G_TYPE_GTYPE, G_TYPE_UINT, "description", G_TYPE_STRING,
                          "NUmber of frame processed", NULL),
        NULL);

    tr_pipeline_interval = gst_tracer_record_new(
        "latency_tracer_pipeline_interval.class", "source_name", GST_TYPE_STRUCTURE,
        gst_structure_new("value", "type", G_TYPE_GTYPE, G_TYPE_STRING, "description", G_TYPE_STRING,
                          "Source element name", NULL),
        "sink_name", GST_TYPE_STRUCTURE,
        gst_structure_new("value", "type", G_TYPE_GTYPE, G_TYPE_STRING, "description", G_TYPE_STRING,
                          "Sink element name", NULL),
        "interval", GST_TYPE_STRUCTURE,
        gst_structure_new("value", "type", G_TYPE_GTYPE, G_TYPE_DOUBLE, "description", G_TYPE_STRING, "interval in ms",
                          NULL),
        "avg", GST_TYPE_STRUCTURE,
        gst_structure_new("value", "type", G_TYPE_GTYPE, G_TYPE_DOUBLE, "description", G_TYPE_STRING,
                          "Average interval frame latency in ms", NULL),
        "min", GST_TYPE_STRUCTURE,
        gst_structure_new("value", "type", G_TYPE_GTYPE, G_TYPE_DOUBLE, "description", G_TYPE_STRING,
                          "Min interval Per frame latency in ms", NULL),
        "max", GST_TYPE_STRUCTURE,
        gst_structure_new("value", "type", G_TYPE_GTYPE, G_TYPE_DOUBLE, "description", G_TYPE_STRING,
                          "Max interval Per frame latency in ms", NULL),
        "latency", GST_TYPE_STRUCTURE,
        gst_structure_new(
            "value", "type", G_TYPE_GTYPE, G_TYPE_DOUBLE, "description", G_TYPE_STRING,
            "pipeline latency within the interval in ms(if frames dropped this may result in invalid value)", NULL),
        "fps", GST_TYPE_STRUCTURE,
        gst_structure_new("value", "type", G_TYPE_GTYPE, G_TYPE_DOUBLE, "description", G_TYPE_STRING,
                          "pipeline fps ithin the interval(if frames dropped this may result in invalid value)", NULL),
        NULL);
    tr_element = gst_tracer_record_new("latency_tracer_element.class", "name", GST_TYPE_STRUCTURE,
                                       gst_structure_new("value", "type", G_TYPE_GTYPE, G_TYPE_STRING, "description",
                                                         G_TYPE_STRING, "Element Name", NULL),
                                       "frame_latency", GST_TYPE_STRUCTURE,
                                       gst_structure_new("value", "type", G_TYPE_GTYPE, G_TYPE_DOUBLE, "description",
                                                         G_TYPE_STRING, "current frame latency in ms", NULL),
                                       "avg", GST_TYPE_STRUCTURE,
                                       gst_structure_new("value", "type", G_TYPE_GTYPE, G_TYPE_DOUBLE, "description",
                                                         G_TYPE_STRING, "Average frame latency in ms", NULL),
                                       "min", GST_TYPE_STRUCTURE,
                                       gst_structure_new("value", "type", G_TYPE_GTYPE, G_TYPE_DOUBLE, "description",
                                                         G_TYPE_STRING, "Min Per frame latency in ms", NULL),
                                       "max", GST_TYPE_STRUCTURE,
                                       gst_structure_new("value", "type", G_TYPE_GTYPE, G_TYPE_DOUBLE, "description",
                                                         G_TYPE_STRING, "Max Per frame latency in ms", NULL),
                                       "frame_num", GST_TYPE_STRUCTURE,
                                       gst_structure_new("value", "type", G_TYPE_GTYPE, G_TYPE_UINT, "description",
                                                         G_TYPE_STRING, "Number of frame processed", NULL),
                                       "is_bin", GST_TYPE_STRUCTURE,
                                       gst_structure_new("value", "type", G_TYPE_GTYPE, G_TYPE_BOOLEAN, "description",
                                                         G_TYPE_STRING, "is element bin", NULL),
                                       NULL);
    tr_element_interval =
        gst_tracer_record_new("latency_tracer_element_interval.class", "name", GST_TYPE_STRUCTURE,
                              gst_structure_new("value", "type", G_TYPE_GTYPE, G_TYPE_STRING, "description",
                                                G_TYPE_STRING, "Element Name", NULL),
                              "interval", GST_TYPE_STRUCTURE,
                              gst_structure_new("value", "type", G_TYPE_GTYPE, G_TYPE_DOUBLE, "description",
                                                G_TYPE_STRING, "Interval ms", NULL),
                              "avg", GST_TYPE_STRUCTURE,
                              gst_structure_new("value", "type", G_TYPE_GTYPE, G_TYPE_DOUBLE, "description",
                                                G_TYPE_STRING, "Average interval latency in ms", NULL),
                              "min", GST_TYPE_STRUCTURE,
                              gst_structure_new("value", "type", G_TYPE_GTYPE, G_TYPE_DOUBLE, "description",
                                                G_TYPE_STRING, "Min interval frame latency in ms", NULL),
                              "max", GST_TYPE_STRUCTURE,
                              gst_structure_new("value", "type", G_TYPE_GTYPE, G_TYPE_DOUBLE, "description",
                                                G_TYPE_STRING, "Max interval frame latency in ms", NULL),
                              NULL);
    GST_DEBUG_CATEGORY_INIT(latency_tracer_debug, "latency_tracer", 0, "latency tracer");
}

static GstElement *get_real_pad_parent(GstPad *pad) {
    GstObject *parent;
    if (!pad)
        return NULL;
    parent = gst_object_get_parent(GST_OBJECT_CAST(pad));
    /* if parent of pad is a ghost-pad, then pad is a proxy_pad */
    if (parent && GST_IS_GHOST_PAD(parent)) {
        GstObject *tmp;
        pad = GST_PAD_CAST(parent);
        tmp = gst_object_get_parent(GST_OBJECT_CAST(pad));
        gst_object_unref(parent);
        parent = tmp;
    }
    return GST_ELEMENT_CAST(parent);
}

struct ElementStats {
    gboolean is_bin;
    gdouble total;
    gdouble min;
    gdouble max;
    guint frame_count;
    gchar *name;
    gdouble interval_total;
    gdouble interval_min;
    gdouble interval_max;
    guint interval_frame_count;
    GstClockTime interval_init_time;
    mutex mtx;

    static void create(GstElement *elem, guint64 ts) {
        // This won't be converted to shared ptr because g_object_set_qdata_full destructor supports gpointer only
        auto *stats = new ElementStats{elem, ts};
        g_object_set_qdata_full(reinterpret_cast<GObject *>(elem), data_string, stats,
                                [](gpointer data) { delete static_cast<ElementStats *>(data); });
    }

    static ElementStats *from_element(GstElement *elem) {
        if (!elem)
            return nullptr;
        return static_cast<ElementStats *>(g_object_get_qdata(G_OBJECT(elem), data_string));
    }

    ElementStats(GstElement *elem, GstClockTime ts) {
        is_bin = GST_IS_BIN(elem);
        total = 0;
        min = G_MAXUINT;
        max = 0;
        frame_count = 0;
        name = GST_ELEMENT_NAME(elem);
        reset_interval(ts);
    }

    void reset_interval(GstClockTime now) {
        interval_total = 0;
        interval_min = G_MAXUINT;
        interval_max = 0;
        interval_init_time = now;
        interval_frame_count = 0;
    }

    void cal_log_element_latency(guint64 src_ts, guint64 sink_ts, gint interval) {
        lock_guard<mutex> guard(mtx);
        frame_count += 1;
        gdouble frame_latency = (gdouble)GST_CLOCK_DIFF(sink_ts, src_ts) / ns_to_ms;
        total += frame_latency;
        gdouble avg = total / frame_count;
        if (frame_latency < min)
            min = frame_latency;
        if (frame_latency > max)
            max = frame_latency;
        gst_tracer_record_log(tr_element, name, frame_latency, avg, min, max, frame_count, is_bin);
        cal_log_interval(frame_latency, src_ts, interval);
    }

    void cal_log_interval(gdouble frame_latency, guint64 src_ts, gint interval) {
        interval_frame_count += 1;
        interval_total += frame_latency;
        if (frame_latency < interval_min)
            interval_min = frame_latency;
        if (frame_latency > interval_max)
            interval_max = frame_latency;
        gdouble ms = (gdouble)GST_CLOCK_DIFF(interval_init_time, src_ts) / ns_to_ms;
        if (ms >= interval) {
            gdouble interval_avg = interval_total / interval_frame_count;
            gst_tracer_record_log(tr_element_interval, name, ms, interval_avg, interval_min, interval_max);
            reset_interval(src_ts);
        }
    }
};

static bool is_parent_pipeline(LatencyTracer *lt, GstElement *elem) {
    GstElement *parent_elm = GST_ELEMENT_PARENT(elem);
    if (parent_elm != lt->pipeline)
        return false;
    return true;
}

// Recursively walk upstream from an element to find a tracked source
// This function performs topology analysis by traversing the pipeline graph
// upstream from a given element, following pad connections until it finds
// a source element that was discovered during pipeline initialization.
// This approach correctly identifies sources even when intermediate elements
// (like decodebin) create new buffers, unlike metadata-based tracking.
static GstElement *find_upstream_source(LatencyTracer *lt, GstElement *elem) {
    if (!elem)
        return nullptr;

    auto *sources = static_cast<vector<GstElement *> *>(lt->sources_list);
    if (!sources)
        return nullptr;

    // Check if this element itself is a tracked source
    for (auto *src : *sources) {
        if (src == elem)
            return src;
    }

    // Walk through all sink pads of this element
    GstIterator *iter = gst_element_iterate_sink_pads(elem);
    GValue val = G_VALUE_INIT;
    GstElement *found_source = nullptr;
    gboolean done = FALSE;

    while (!done) {
        switch (gst_iterator_next(iter, &val)) {
        case GST_ITERATOR_OK: {
            GstPad *sink_pad = GST_PAD(g_value_get_object(&val));
            GstPad *peer_pad = gst_pad_get_peer(sink_pad);

            if (peer_pad) {
                GstElement *upstream = get_real_pad_parent(peer_pad);
                gst_object_unref(peer_pad);

                // Recursively search upstream
                found_source = find_upstream_source(lt, upstream);
                if (found_source) {
                    g_value_unset(&val);
                    done = TRUE;
                    break;
                }
            }
            g_value_unset(&val);
            break;
        }
        case GST_ITERATOR_RESYNC:
            // Iterator was invalidated, resync and retry
            gst_iterator_resync(iter);
            break;
        case GST_ITERATOR_ERROR:
            // Error occurred, log with element context and stop
            if (elem) {
                GST_WARNING("Error while iterating sink pads for element %s", GST_ELEMENT_NAME(elem));
            } else {
                GST_WARNING("Error while iterating sink pads for unknown element");
            }
            done = TRUE;
            break;
        case GST_ITERATOR_DONE:
            done = TRUE;
            break;
        }
    }

    gst_iterator_free(iter);
    return found_source;
}

static void reset_pipeline_interval(LatencyTracer *lt, GstClockTime now) {
    lt->interval_total = 0;
    lt->interval_min = G_MAXUINT;
    lt->interval_max = 0;
    lt->interval_init_time = now;
    lt->interval_frame_count = 0;
}

static void cal_log_pipeline_interval(LatencyTracer *lt, guint64 ts, gdouble frame_latency, const char *source_name,
                                      const char *sink_name) {
    lt->interval_frame_count += 1;
    lt->interval_total += frame_latency;
    if (frame_latency < lt->interval_min)
        lt->interval_min = frame_latency;
    if (frame_latency > lt->interval_max)
        lt->interval_max = frame_latency;
    gdouble ms = (gdouble)GST_CLOCK_DIFF(lt->interval_init_time, ts) / ns_to_ms;
    if (ms >= lt->interval) {
        gdouble pipeline_latency = ms / lt->interval_frame_count;
        gdouble fps = ms_to_s / pipeline_latency;
        gdouble interval_avg = lt->interval_total / lt->interval_frame_count;
        gst_tracer_record_log(tr_pipeline_interval, source_name, sink_name, ms, interval_avg, lt->interval_min,
                              lt->interval_max, pipeline_latency, fps);
        reset_pipeline_interval(lt, ts);
    }
}

static void cal_log_pipeline_latency(LatencyTracer *lt, guint64 ts, LatencyTracerMeta *meta) {
    GST_OBJECT_LOCK(lt);
    lt->frame_count += 1;
    gdouble frame_latency = (gdouble)GST_CLOCK_DIFF(meta->init_ts, ts) / ns_to_ms;
    gdouble pipeline_latency_ns = (gdouble)GST_CLOCK_DIFF(lt->first_frame_init_ts, ts) / lt->frame_count;
    gdouble pipeline_latency = pipeline_latency_ns / ns_to_ms;
    lt->toal_latency += frame_latency;
    gdouble avg = lt->toal_latency / lt->frame_count;
    gdouble fps = 0;
    if (pipeline_latency > 0)
        fps = ms_to_s / pipeline_latency;

    if (frame_latency < lt->min)
        lt->min = frame_latency;
    if (frame_latency > lt->max)
        lt->max = frame_latency;

    // Use topology analysis to find source for the sink
    const char *source_name = "unknown";
    const char *sink_name = "unknown";

    if (lt->sink_element) {
        sink_name = GST_ELEMENT_NAME(lt->sink_element);
        GstElement *source = find_upstream_source(lt, lt->sink_element);
        if (source) {
            source_name = GST_ELEMENT_NAME(source);
        }
    }

    gst_tracer_record_log(tr_pipeline, source_name, sink_name, frame_latency, avg, lt->min, lt->max, pipeline_latency,
                          fps, lt->frame_count);
    cal_log_pipeline_interval(lt, ts, frame_latency, source_name, sink_name);
    GST_OBJECT_UNLOCK(lt);
}

static void add_latency_meta(LatencyTracer *lt, LatencyTracerMeta *meta, guint64 ts, GstBuffer *buffer) {
    if (!gst_buffer_is_writable(buffer)) {
        // Skip non-writable buffers - expected for shared/read-only buffers
        GST_TRACE("Skipping non-writable buffer for latency metadata");
        return;
    }
    meta = LATENCY_TRACER_META_ADD(buffer);
    meta->init_ts = ts;
    meta->last_pad_push_ts = ts;
    if (lt->first_frame_init_ts == 0) {
        reset_pipeline_interval(lt, ts);
        lt->first_frame_init_ts = ts;
    }
}

static void do_push_buffer_pre(LatencyTracer *lt, guint64 ts, GstPad *pad, GstBuffer *buffer) {
    GstElement *elem = get_real_pad_parent(pad);
    if (!is_parent_pipeline(lt, elem))
        return;
    LatencyTracerMeta *meta = LATENCY_TRACER_META_GET(buffer);
    if (!meta) {
        add_latency_meta(lt, meta, ts, buffer);
        return;
    }
    if (lt->flags & LATENCY_TRACER_FLAG_ELEMENT) {
        ElementStats *stats = ElementStats::from_element(elem);
        // log latency only if ts is greater than last logged ts to avoid duplicate logging for the same buffer
        if (stats != nullptr && ts > meta->last_pad_push_ts) {
            stats->cal_log_element_latency(ts, meta->last_pad_push_ts, lt->interval);
            meta->last_pad_push_ts = ts;
        }
    }

    // Check if the peer of this pad is a sink element
    GstPad *peer_pad = GST_PAD_PEER(pad);
    GstElement *peer_element = peer_pad ? get_real_pad_parent(peer_pad) : nullptr;

    if (lt->flags & LATENCY_TRACER_FLAG_PIPELINE && peer_element &&
        GST_OBJECT_FLAG_IS_SET(peer_element, GST_ELEMENT_FLAG_SINK)) {

        GstElement *sink = peer_element;

        // Use topology analysis to find the source feeding this sink
        GstElement *source = find_upstream_source(lt, sink);

        if (source && sink) {
            string branch_key = create_branch_key(source, sink);
            auto *stats_map = get_branch_stats_map(lt);

            // Initialize branch stats if this is the first time we see this source-sink pair
            if (stats_map->find(branch_key) == stats_map->end()) {
                BranchStats &branch = (*stats_map)[branch_key];
                branch.source_name = GST_ELEMENT_NAME(source);
                branch.sink_name = GST_ELEMENT_NAME(sink);
                branch.source_element = source;
                branch.sink_element = sink;
                branch.first_frame_init_ts = meta->init_ts;
                branch.reset_interval(ts);
                GST_INFO_OBJECT(lt, "Tracking new branch: %s -> %s", branch.source_name.c_str(),
                                branch.sink_name.c_str());
            }

            BranchStats &branch = (*stats_map)[branch_key];
            branch.cal_log_pipeline_latency(ts, meta->init_ts, lt->interval);
        }

        // Also log for backward compatibility with single sink tracking
        if (lt->sink_element == sink) {
            cal_log_pipeline_latency(lt, ts, meta);
        }
    }
}

static void do_pull_range_post(LatencyTracer *lt, guint64 ts, GstPad *pad, GstBuffer *buffer) {
    GstElement *elem = get_real_pad_parent(pad);
    if (!is_parent_pipeline(lt, elem))
        return;
    LatencyTracerMeta *meta = nullptr;
    add_latency_meta(lt, meta, ts, buffer);
}

static void do_push_buffer_list_pre(LatencyTracer *lt, guint64 ts, GstPad *pad, GstBufferList *list) {
    BufferListArgs args{lt, ts, pad};
    gst_buffer_list_foreach(
        list,
        [](GstBuffer **buffer, guint, gpointer user_data) -> gboolean {
            auto [lt, ts, pad] = *static_cast<BufferListArgs *>(user_data);
            do_push_buffer_pre(lt, ts, pad, *buffer);
            return TRUE;
        },
        &args);
}

static void on_element_change_state_post(LatencyTracer *lt, guint64 ts, GstElement *elem, GstStateChange change,
                                         GstStateChangeReturn result) {
    UNUSED(result);
    if (GST_STATE_TRANSITION_NEXT(change) == GST_STATE_PLAYING && elem == lt->pipeline) {
        auto *sources = get_sources_list(lt);
        auto *sinks = get_sinks_list(lt);

        GstIterator *iter = gst_bin_iterate_elements(GST_BIN_CAST(elem));
        while (true) {
            GValue gval = {};
            auto ret = gst_iterator_next(iter, &gval);
            if (ret != GST_ITERATOR_OK) {
                if (ret != GST_ITERATOR_DONE)
                    GST_ERROR_OBJECT(lt, "Got error while iterating pipeline");
                break;
            }
            auto *element = static_cast<GstElement *>(g_value_get_object(&gval));
            GST_INFO_OBJECT(lt, "Element %s ", GST_ELEMENT_NAME(element));

            if (GST_OBJECT_FLAG_IS_SET(element, GST_ELEMENT_FLAG_SINK)) {
                // Track all sink elements
                sinks->push_back(element);
                GST_INFO_OBJECT(lt, "Found sink element: %s", GST_ELEMENT_NAME(element));

                // Keep first sink for backward compatibility
                if (!lt->sink_element)
                    lt->sink_element = element;
            } else if (GST_OBJECT_FLAG_IS_SET(element, GST_ELEMENT_FLAG_SOURCE)) {
                // Track all source elements
                sources->push_back(element);
                GST_INFO_OBJECT(lt, "Found source element: %s", GST_ELEMENT_NAME(element));
            } else {
                // create ElementStats only once per each element (for non-source, non-sink elements)
                if (!ElementStats::from_element(element)) {
                    ElementStats::create(element, ts);
                }
            }
        }

        GST_INFO_OBJECT(lt, "Found %zu source(s) and %zu sink(s)", sources->size(), sinks->size());

        GstTracer *tracer = GST_TRACER(lt);
        gst_tracing_register_hook(tracer, "pad-push-pre", G_CALLBACK(do_push_buffer_pre));
        gst_tracing_register_hook(tracer, "pad-push-list-pre", G_CALLBACK(do_push_buffer_list_pre));
        gst_tracing_register_hook(tracer, "pad-pull-range-post", G_CALLBACK(do_pull_range_post));
    }
}
static void on_element_new(LatencyTracer *lt, guint64 ts, GstElement *elem) {
    UNUSED(ts);
    if (GST_IS_PIPELINE(elem)) {
        if (!lt->pipeline)
            lt->pipeline = elem;
        else
            GST_WARNING_OBJECT(lt, "pipeline %s already exists, multiple pipelines may not give right result %s",
                               GST_ELEMENT_NAME(lt->pipeline), GST_ELEMENT_NAME(elem));
    }
}

static void latency_tracer_init(LatencyTracer *lt) {
    GST_OBJECT_LOCK(lt);
    lt->toal_latency = 0;
    lt->frame_count = 0;
    lt->first_frame_init_ts = 0;
    lt->pipeline = nullptr;
    lt->sink_element = nullptr;
    lt->min = G_MAXUINT;
    lt->max = 0;
    lt->flags = static_cast<LatencyTracerFlags>(LATENCY_TRACER_FLAG_ELEMENT | LATENCY_TRACER_FLAG_PIPELINE);
    lt->interval = 1000;
    lt->branch_stats = nullptr;
    lt->sources_list = nullptr;
    lt->sinks_list = nullptr;

    GstTracer *tracer = GST_TRACER(lt);
    gst_tracing_register_hook(tracer, "element-new", G_CALLBACK(on_element_new));
    gst_tracing_register_hook(tracer, "element-change-state-post", G_CALLBACK(on_element_change_state_post));
    GST_OBJECT_UNLOCK(lt);
}

static gboolean plugin_init(GstPlugin *plugin) {
    if (!gst_tracer_register(plugin, "latency_tracer", latency_tracer_get_type()))
        return false;
    latency_tracer_meta_get_info();
    latency_tracer_meta_api_get_type();
    return true;
}

GST_PLUGIN_DEFINE(GST_VERSION_MAJOR, GST_VERSION_MINOR, latency_tracer, ELEMENT_DESCRIPTION, plugin_init,
                  PLUGIN_VERSION, PLUGIN_LICENSE, PACKAGE_NAME, GST_PACKAGE_ORIGIN)
