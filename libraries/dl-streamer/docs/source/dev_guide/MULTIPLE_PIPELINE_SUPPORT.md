# Multiple Pipeline Support Enhancement for Latency Tracer

## Overview

This enhancement enables the latency tracer to track **multiple GStreamer pipelines** (both sequential and concurrent), removing the previous single-pipeline limitation.

## Problem Statement

Previously, the latency tracer could only track one pipeline at a time:
- ❌ Only the first pipeline was tracked
- ❌ Subsequent pipelines triggered a warning
- ❌ Elements from other pipelines were ignored

## Changes Made

### 1. **BranchKey Enhancement** (Line ~138-160)
Changed from `pair<source, sink>` to `tuple<source, sink, pipeline>` to separate statistics per pipeline.

```cpp
// OLD: Only source and sink
using BranchKey = pair<GstElement*, GstElement*>;

// NEW: Include pipeline to separate stats
using BranchKey = tuple<GstElement*, GstElement*, GstElement*>;
```

Added `BranchKeyHash` struct for proper tuple hashing and updated `create_branch_key()` helper.

### 2. **Pipeline Detection** (Line ~495-530)
Replaced `is_parent_pipeline()` with `is_in_pipeline()` to check if element is in **any** pipeline.

```cpp
// OLD: Check if element is in specific pipeline (lt->pipeline)
static bool is_parent_pipeline(LatencyTracer *lt, GstElement *elem)

// NEW: Check if element is in any pipeline
static bool is_in_pipeline(LatencyTracer *lt, GstElement *elem)
```

Added `find_pipeline_for_element()` helper to identify which pipeline an element belongs to.

### 3. **Element Tracking** (Line ~760-815)
Updated `on_element_change_state_post()` to discover elements in **all** pipelines transitioning to PLAYING state.

```cpp
// OLD: Only track lt->pipeline
if (GST_STATE_TRANSITION_NEXT(change) == GST_STATE_PLAYING && elem == lt->pipeline)

// NEW: Track all pipelines
if (GST_STATE_TRANSITION_NEXT(change) == GST_STATE_PLAYING && GST_IS_PIPELINE(elem))
```

### 4. **Pipeline Registration** (Line ~815-824)
Removed single-pipeline restriction in `on_element_new()`.

```cpp
// OLD: Store first pipeline only, warn about subsequent ones
if (!lt->pipeline)
    lt->pipeline = elem;
else
    GST_WARNING_OBJECT(lt, "pipeline already exists...");

// NEW: Log all pipelines for tracking
GST_INFO("Latency tracer will track pipeline: %s", GST_ELEMENT_NAME(elem));
```

### 5. **Data Structure Optimization**
Changed from `map` to `unordered_map` with custom hash for better performance with tuple keys.

## Benefits

✅ **Sequential pipelines**: Each pipeline tracked separately  
✅ **Concurrent pipelines**: Multiple pipelines running simultaneously  
✅ **Per-pipeline stats**: Stats separated by pipeline using tuple key  
✅ **Backward compatible**: Single pipeline case still works  
✅ **No API changes**: Same `GST_TRACERS` environment variable  

## Usage

### Sequential Pipelines (Python Example)

```python
import gi
gi.require_version('Gst', '1.0')
from gi.repository import Gst
import os

os.environ['GST_TRACERS'] = 'latency_tracer(flags=pipeline)'
Gst.init(None)

# Pipeline 1
pipe1 = Gst.parse_launch("videotestsrc num-buffers=100 ! fakesink")
pipe1.set_state(Gst.State.PLAYING)
pipe1.get_state(Gst.CLOCK_TIME_NONE)
pipe1.set_state(Gst.State.NULL)

# Pipeline 2 - Now tracked! ✓
pipe2 = Gst.parse_launch("videotestsrc num-buffers=100 ! fakesink")  
pipe2.set_state(Gst.State.PLAYING)
pipe2.get_state(Gst.CLOCK_TIME_NONE)
pipe2.set_state(Gst.State.NULL)
```

### Concurrent Pipelines (gst-launch Example)

```bash
# Terminal 1
GST_TRACERS="latency_tracer(flags=pipeline)" \
gst-launch-1.0 videotestsrc num-buffers=100 ! fakesink &

# Terminal 2
GST_TRACERS="latency_tracer(flags=pipeline)" \
gst-launch-1.0 videotestsrc num-buffers=100 ! fakesink &
```

## Expected Output

**With sequential pipelines**:
```
# Pipeline 1 running
source_name=videotestsrc0, sink_name=fakesink0, frame_num=100...

# Pipeline 2 running (now tracked!)
source_name=videotestsrc0, sink_name=fakesink0, frame_num=100...
```

**With concurrent pipelines**:
```
# Both tracked simultaneously
source_name=videotestsrc0, sink_name=fakesink0, frame_num=50... (pipeline1)
source_name=videotestsrc0, sink_name=fakesink0, frame_num=50... (pipeline2)
```

## Testing

Two test scripts are provided:

### 1. Sequential Pipeline Test
```bash
cd libraries/dl-streamer/docs/source/dev_guide
GST_TRACERS="latency_tracer(flags=pipeline)" \
GST_DEBUG="latency_tracer:5" \
python3 test_sequential_pipelines.py
```

### 2. Concurrent Pipeline Test
```bash
cd libraries/dl-streamer/docs/source/dev_guide
GST_TRACERS="latency_tracer(flags=pipeline)" \
GST_DEBUG="latency_tracer:5" \
python3 test_concurrent_pipelines.py
```

## Files Modified

- **latency_tracer.cpp**: All implementation changes
- **latency_tracer.h**: No changes (maintains binary compatibility)

## Technical Details

### BranchKey Hash Function
Uses boost::hash_combine pattern for efficient tuple hashing:
```cpp
h1 ^= h2 + 0x9e3779b9 + (h1 << 6) + (h1 >> 2);
h1 ^= h3 + 0x9e3779b9 + (h1 << 6) + (h1 >> 2);
```

### Pipeline Discovery
The new `find_pipeline_for_element()` walks up the element hierarchy to find the top-level pipeline:
```cpp
GstObject *parent = GST_OBJECT_CAST(elem);
while (parent) {
    if (GST_IS_PIPELINE(parent)) {
        return GST_ELEMENT_CAST(parent);
    }
    parent = GST_OBJECT_PARENT(parent);
}
```

## Backward Compatibility

- The `lt->pipeline` field is retained in the struct for binary compatibility
- Single pipeline tracking still works as before
- No changes to the public API or environment variables
- No changes to the header file

## Performance Considerations

- Uses `unordered_map` with custom hash for O(1) average lookup
- Pipeline pointer is cached with branch key to avoid repeated lookups
- Element type cache still provides O(1) type checking
- Topology cache still provides O(1) source lookup

## Future Enhancements

Possible future improvements:
- Add pipeline name to log output for better identification
- Add per-pipeline statistics summary on shutdown
- Add configuration option to limit tracked pipelines
