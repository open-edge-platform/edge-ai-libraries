# Pipeline Performance

This article describes how ViPPET collects and reports pipeline-level performance metrics: throughput (FPS),
end-to-end latency and VLM generation metrics.

## Throughput

Throughput is measured by the `gvafpscounter` element embedded in the GStreamer pipeline. The element counts
the number of buffers (frames) that pass through it per second and emits a log line that the `PipelineRunner`
extracts and pushes to the metrics service as the **FPS** metric.

## Latency

Latency measurement uses GStreamer's built-in `latency_tracer` infrastructure. When enabled, it tracks how long
each buffer takes to traverse the entire pipeline — from the source element to the sink element.

### How latency_tracer is activated

When a pipeline run has latency metrics enabled, the `PipelineRunner` sets the following environment variables
on the GStreamer subprocess:

| Environment variable             | Value                                                            | Purpose                                                                |
| -------------------------------- | ---------------------------------------------------------------- | ---------------------------------------------------------------------- |
| `GST_TRACERS`                    | `latency_tracer(flags=pipeline,interval=1000,post-metrics=true)` | Activates the tracer in pipeline mode with 1 000 ms reporting interval |
| `VIPPET_LATENCY_RECORD_FALLBACK` | `1`                                                              | Enables the tracer's text records, used only as a fallback             |

- **`flags=pipeline`** — measures the total source-to-sink latency (as opposed to per-element latency).
- **`interval=1000`** — the tracer reports statistics accumulated during each 1 000 ms window.
- **`post-metrics=true`** — the tracer posts every window as a `dlstreamer/latency-window` element message on the
  pipeline bus. The last, partial window is posted at end-of-stream.

### Latency window messages

`gst_runner.py` forwards each `dlstreamer/*` bus message to stdout as one `Pipeline metric: {json}` line. A
`dlstreamer/latency-window` message (version 1) carries the raw aggregates of one window of one source-sink branch:

| Field       | Description                                              |
| ----------- | -------------------------------------------------------- |
| `version`   | Message schema version; other versions are skipped       |
| `pipeline`  | Name of the pipeline                                     |
| `source`    | Name of the source element (identifies the stream)       |
| `sink`      | Name of the sink element                                 |
| `window_ms` | Actual length of the window (ms)                         |
| `count`     | Number of frames that reached the sink during the window |
| `sum_ms`    | Sum of the latencies of these frames (ms)                |
| `min_ms`    | Minimum frame latency during the window (ms)             |
| `max_ms`    | Maximum frame latency during the window (ms)             |

The `PipelineRunner` derives one sample per window, as the tracer does for its own records:

| Sample field  | Value               | Meaning                                                                              |
| ------------- | ------------------- | ------------------------------------------------------------------------------------ |
| `interval_ms` | `window_ms`         | Length of the window                                                                 |
| `avg_ms`      | `sum_ms / count`    | Mean source-to-sink latency of a frame                                               |
| `min_ms`      | `min_ms`            | Minimum source-to-sink latency of a frame                                            |
| `max_ms`      | `max_ms`            | Maximum source-to-sink latency of a frame                                            |
| `latency_ms`  | `window_ms / count` | **Deprecated.** Frame period (`1000 / fps`), a throughput measure, **not** a latency |

A frame's source-to-sink latency runs from the moment the source element outputs the frame to the moment the frame
is pushed into the sink, so the sink's own work is excluded. `latency_ms` is the mean time between output frames in
the window: it falls as throughput rises and says nothing about how long a frame spends in the pipeline. It is
deprecated and kept only for API compatibility; use `avg_ms` for the mean latency and `max_ms` for the worst case.

### Fallback for older DL Streamer versions

A `latency_tracer` that predates `post-metrics` ignores the parameter and only logs every window as a
`latency_tracer_pipeline_interval` record at GStreamer TRACE level, for example:

```text
latency_tracer_pipeline_interval, pipeline_name=(string)pipeline0, source_name=(string)src_p0_s0_0_0, sink_name=(string)sink_p0_s0_0_0, interval=(double)1000.25, avg=(double)364.31, min=(double)0.004, max=(double)529.26, latency=(double)21.28, fps=(double)46.99;
```

With `VIPPET_LATENCY_RECORD_FALLBACK=1`, `gst_runner.py` raises the `GST_TRACER` debug threshold to TRACE after
initializing GStreamer, and `gst_log_bridge()` promotes the interval records to INFO so that they reach the parent
process. As soon as the tracer posts its first window as a message, `gst_runner.py` stops promoting them and restores
the threshold the category had before, as set by `GST_DEBUG`, so the per-frame records are no longer formatted.

The tracer logs the record of a window just before it posts the message for the same window. The `PipelineRunner`
therefore holds a record back per stream until it knows the source of the run:

- A `latency-window` message arrives: the messages are used and the held records are dropped.
- A second record of the same stream arrives, or the run ends, without any message: the tracer does not support
  `post-metrics`. The records are parsed with a regular expression instead, and one warning is logged.

### Data flow

```text
GStreamer subprocess (gst_runner.py)
   │  bus: dlstreamer/latency-window   (fallback: latency_tracer TRACE records)
   ▼
"Pipeline metric: {json}" lines on stdout   (fallback: records promoted to INFO)
   │
   ▼
PipelineRunner (hot stdout reader loop)
   │  _record_latency_window()   (fallback: _parse_latency_record())
   ▼
_push_latency_sample()  ──▶  HTTP POST to metrics-manager:9090/api/v1/metrics
   │
   ▼
metrics-manager  ──▶  SSE stream at /metrics/stream
   │
   ▼
Browser (EventSource) → Redux store → Latency chart components
```

1. **gst_runner.py** — the subprocess entry point that wraps GStreamer execution. It forwards `dlstreamer/*` bus
   messages as `Pipeline metric:` lines, including messages still on the bus at shutdown.
1. **PipelineRunner** — the parent-process orchestrator reads each stdout line in a tight loop, and the output left
   when the subprocess exits. It derives a `LatencyTracerSample` from each window and calls `_push_latency_sample()`.
1. **metrics-manager** — receives an HTTP POST with a `pipeline_latency` measurement (fields: `avg_ms`,
   `min_ms`, `max_ms`, `latency_ms`; tags: `stream_id`, `job_id`). It stores the sample and pushes it
   to connected SSE clients.
1. **UI (browser)** — an `EventSource` connection to `/metrics/stream` dispatches incoming messages to
   the Redux store. The latency chart components render avg / min / max over time.

## VLM generation metrics

Pipelines with a `gvagenai` element that runs with `metrics=true` report the performance of every generation
request. `gst_runner.py` sets `post-metrics=true` on such an element when the installed `gvagenai` has the property.
The element then posts a `dlstreamer/genai-request` message (version 1) per request, and the `PipelineRunner` pushes
its `ttft_ms`, `tpot_ms` and `generate_duration_ms` as a `vlm_metrics` sample, tagged with the element name as
`stream_id`. These values describe that request only.

A `gvagenai` without the `post-metrics` property cannot be asked for these messages. The property is not added to
the pipeline description, because an unknown property fails parsing. For such an element the `PipelineRunner` falls
back to the `metrics` block of the JSON metadata the element logs, with one warning per run. That block holds the
means over every request since the element started (`ttft_mean`, `tpot_mean`, `generate_duration_mean`), not
per-request values.
