# Latency Tracer - Multi-Branch Support

## Overview

The latency_tracer has been enhanced to support tracking latency across multiple GStreamer pipeline branches, including multiple sources and multiple sinks within the same pipeline.

## Key Features

### 1. Multi-Branch Tracking
- Automatically discovers all source and sink elements in the pipeline
- Tracks independent latency statistics for each source-sink pair
- Works with simple linear pipelines, tee elements, and complex multi-branch topologies

### 2. Topology-Based Source Tracking
- Uses pipeline topology analysis instead of buffer metadata
- Recursively walks upstream from sink elements to find originating sources
- Works correctly even when elements like `decodebin` create new buffers

### 3. Per-Branch Statistics
- `BranchStats` structure maintains separate statistics for each source-sink pair
- Tracks: average, min, max latency, frame count, interval statistics
- Thread-safe with mutex protection

## Architecture

### Data Structures

#### BranchStats (latency_tracer.cpp)
```cpp
struct BranchStats {
    string source_name;      // Name of source element
    string sink_name;        // Name of sink element
    GstElement *source_element;
    GstElement *sink_element;
    gdouble total;          // Total latency
    gdouble min;            // Minimum latency
    gdouble max;            // Maximum latency
    guint frame_count;      // Number of frames
    // ... interval tracking fields
    mutex mtx;              // Thread safety
};
```

#### LatencyTracer Extensions (latency_tracer.h)
```cpp
struct LatencyTracer {
    // ... existing fields ...
    gpointer branch_stats;  // map<string, BranchStats>*
    gpointer sources_list;  // vector<GstElement*>*
    gpointer sinks_list;    // vector<GstElement*>*
};
```

#### LatencyTracerMeta (latency_tracer_meta.h)
```cpp
struct _LatencyTracerMeta {
    GstMeta meta;
    GstClockTime init_ts;
    GstClockTime last_pad_push_ts;
    GstElement *source_element;  // DEPRECATED: no longer used for tracking
};
```
Note: The `source_element` field is retained for backward compatibility but is no longer used. Source tracking is now done via topology analysis.

### Key Functions

#### Element Discovery (`on_element_change_state_post`)
- Iterates through all pipeline elements
- Identifies and stores all sources (GST_ELEMENT_FLAG_SOURCE)
- Identifies and stores all sinks (GST_ELEMENT_FLAG_SINK)
- Creates ElementStats for processing elements

#### Topology Analysis (`find_upstream_source`)
- Recursively walks upstream from a sink element
- Follows pad connections through the pipeline graph
- Identifies the originating source element feeding into the sink
- Handles complex topologies including tees, decoders, and transforming elements

#### Metadata Management (`add_latency_meta`)
- Attaches LatencyTracerMeta to buffers when first encountered
- Initializes timestamps for latency measurement
- No longer tracks source_element in metadata

#### Buffer Processing (`do_push_buffer_pre`)
- Checks if buffer is reaching a sink element
- Uses topology analysis to determine source-sink pair
- Creates BranchStats entry if this is a new source-sink pair
- Calculates and logs per-branch latency statistics

## Implementation Details

### C++ Objects in C Structs
To use C++ containers (map, vector) in the C-based GstTracer struct:
1. Store as `gpointer` (void*) in the struct
2. Provide type-safe accessor functions:
```cpp
static map<string, BranchStats>* get_branch_stats_map(LatencyTracer *lt) {
    if (!lt->branch_stats) {
        lt->branch_stats = new map<string, BranchStats>();
    }
    return static_cast<map<string, BranchStats>*>(lt->branch_stats);
}
```
3. Clean up in finalize function:
```cpp
static void latency_tracer_finalize(GObject *object) {
    LatencyTracer *lt = LATENCY_TRACER(object);
    if (lt->branch_stats) {
        delete static_cast<map<string, BranchStats>*>(lt->branch_stats);
        lt->branch_stats = nullptr;
    }
    // ... clean up other C++ objects
}
```

### Branch Identification
Branches are identified by creating a unique key:
```cpp
static string create_branch_key(GstElement *source, GstElement *sink) {
    return string(GST_ELEMENT_NAME(source)) + "->" + string(GST_ELEMENT_NAME(sink));
}
```

### Thread Safety
- BranchStats uses mutex for thread-safe statistics updates
- Each branch has its own mutex to allow concurrent updates to different branches

## Per-Branch Statistics

The implementation tracks statistics independently for each source-sink branch:
- Each source-sink pair maintains its own frame counter starting from 1
- Frame counters increment independently across branches
- No duplicate logging - each frame is logged exactly once per branch
- Legacy fields (`sink_element`, `frame_count`) retained in struct but no longer used for logging

## Usage Examples

### Simple Multi-Branch
```bash
GST_DEBUG="GST_TRACER:7" GST_TRACERS="latency_tracer" gst-launch-1.0 \
  videotestsrc name=src1 ! videoconvert ! fakesink name=sink1 \
  videotestsrc name=src2 ! videoconvert ! fakesink name=sink2
```

### Tee Element (Single Source, Multiple Sinks)
```bash
GST_DEBUG="GST_TRACER:7" GST_TRACERS="latency_tracer" gst-launch-1.0 \
  filesrc location=video.mp4 name=src ! decodebin ! tee name=t \
  t. ! queue ! videoconvert ! fakesink name=sink1 \
  t. ! queue ! videoconvert ! autovideosink name=sink2
```

## Output Format

The enhanced tracer produces output with per-branch frame numbering:
```
[Latency Tracer] Source: videotestsrc0 -> Sink: fakesink0 - Frame: 1, Latency: 15.23 ms, Avg: 15.23 ms, Min: 15.23 ms, Max: 15.23 ms, Pipeline Latency: 16.67 ms, FPS: 60.00
[Latency Tracer] Source: videotestsrc0 -> Sink: fakesink0 - Frame: 2, Latency: 15.10 ms, Avg: 15.17 ms, Min: 15.10 ms, Max: 15.23 ms, Pipeline Latency: 16.67 ms, FPS: 60.00
[Latency Tracer] Source: filesrc0 -> Sink: autovideosink0 - Frame: 1, Latency: 33.33 ms, Avg: 33.33 ms, Min: 33.33 ms, Max: 33.33 ms, Pipeline Latency: 33.33 ms, FPS: 30.00
[Latency Tracer] Source: filesrc0 -> Sink: autovideosink0 - Frame: 2, Latency: 33.40 ms, Avg: 33.37 ms, Min: 33.33 ms, Max: 33.40 ms, Pipeline Latency: 33.33 ms, FPS: 30.00
```

Note: Each branch maintains independent frame counters starting from 1.

## Testing

See `docs/source/dev_guide/latency_tracer_test_examples.sh` for interactive test examples.

## Future Enhancements

Possible future improvements:
- CSV export with source/sink identification
- Per-branch interval reporting in separate log streams
- Configuration to filter specific source-sink pairs
- Visualization tools for multi-branch latency analysis
- Support for dynamic pipeline topology changes

## Related Files

- `latency_tracer.h` - Header with struct definitions
- `latency_tracer.cpp` - Core implementation
- `latency_tracer_meta.h` - Metadata structure
- `latency_tracer_meta.cpp` - Metadata implementation
- `CMakeLists.txt` - Build configuration
- `docs/source/dev_guide/latency_tracer.md` - User documentation
