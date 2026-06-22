# Pipeline Performance

This article describes how ViPPET collects and reports pipeline-level performance metrics: throughput (FPS)
and end-to-end latency.

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

| Environment variable | Value                                          | Purpose                                                                |
| -------------------- | ---------------------------------------------- | ---------------------------------------------------------------------- |
| `GST_TRACERS`        | `latency_tracer(flags=pipeline,interval=1000)` | Activates the tracer in pipeline mode with 1 000 ms reporting interval |
| `GST_DEBUG`          | `GST_TRACER:7` (appended to existing value)    | Promotes tracer messages to a visible log level                        |

- **`flags=pipeline`** — measures the total source-to-sink latency (as opposed to per-element latency).
- **`interval=1000`** — the tracer emits a summary line every 1 000 ms containing statistics accumulated
  during that interval.

### Parsed output lines

The GStreamer subprocess writes trace messages to stderr. The `gst_log_bridge()` function in `gst_runner.py`
promotes lines prefixed with `latency_tracer_pipeline_interval,` from GStreamer's native TRACE level to
Python INFO, so they reach the parent process stdout.

A sample output line:

```text
latency_tracer_pipeline_interval, source_name=(string)src_p0_s0_0_0, sink_name=(string)sink_p0_s0_0_0, interval=(double)1000.25, avg=(double)364.31, min=(double)0.004, max=(double)529.26, latency=(double)21.28, fps=(double)46.99;
```

The `PipelineRunner` matches this line with a regex that extracts the following fields:

| Field         | Description                                        |
| ------------- | -------------------------------------------------- |
| `source_name` | Name of the source element (identifies the stream) |
| `sink_name`   | Name of the sink element                           |
| `interval`    | Actual reporting interval in milliseconds          |
| `avg`         | Average buffer latency during the interval (ms)    |
| `min`         | Minimum buffer latency during the interval (ms)    |
| `max`         | Maximum buffer latency during the interval (ms)    |
| `latency`     | Instantaneous latency of the last buffer (ms)      |
| `fps`         | Throughput measured by the tracer (frames/s)       |

Additionally, at pipeline EOS (end-of-stream), a `last latency_tracer_pipeline` message is emitted
containing the final cumulative latency statistics for the entire run.

### Data flow

```text
GStreamer subprocess (gst_runner.py)
   │  stderr: latency_tracer TRACE messages
   ▼
gst_log_bridge()  ──▶ promotes to INFO, writes to stdout
   │
   ▼
PipelineRunner (hot stdout reader loop)
   │  _parse_and_record_latency_sample() — regex extraction
   ▼
_push_latency_sample()  ──▶  HTTP POST to metrics-manager:9090/api/v1/metrics
   │
   ▼
metrics-manager  ──▶  SSE stream at /metrics/stream
   │
   ▼
Browser (EventSource) → Redux store → Latency chart components
```

1. **gst_runner.py** — the subprocess entry point that wraps GStreamer execution. Its `gst_log_bridge()`
   intercepts lines starting with `latency_tracer_pipeline_interval,` and re-emits them at INFO level.
2. **PipelineRunner** — the parent-process orchestrator reads each stdout line in a tight loop. When a
   latency line is detected, `_parse_and_record_latency_sample()` extracts the numeric fields into a
   `LatencyTracerSample` dataclass and calls `_push_latency_sample()`.
3. **metrics-manager** — receives an HTTP POST with a `pipeline_latency` measurement (fields: `avg_ms`,
   `min_ms`, `max_ms`, `latency_ms`; tags: `stream_id`, `job_id`). It stores the sample and pushes it
   to connected SSE clients.
4. **UI (browser)** — an `EventSource` connection to `/metrics/stream` dispatches incoming messages to
   the Redux store. The latency chart components render avg / min / max over time.
