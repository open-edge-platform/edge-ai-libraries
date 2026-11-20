# Pipeline Performance

This article describes how ViPPET collects and reports pipeline-level performance metrics: throughput (FPS),
end-to-end latency and VLM generation metrics.

## Throughput

Pipelines run on DL Streamer Pipeline Server 2.0 (DLSPS), one server instance per stream. The server counts the
frames of each instance at one terminal sink and reports them as `frame_fps` over the last `frame_interval`
seconds in `GET /pipelines/{id}/status`. That sink is the one parsed last, so before starting an instance ViPPET
moves one branch to the end of the launch string: the branch with `gvafpscounter` if exactly one branch has it and
ends in a sink, otherwise the branch that ends in the stream's main sink. In a VLM pipeline whose `gvafpscounter`
sits after `gvagenai`, the FPS is therefore the rate of the VLM branch, not of the decode branch beside it.
`Dlsps2PipelineRunner` (`vippet/dlsps2_runner.py`) polls the status of each instance every
`DLSPS2_POLL_INTERVAL_S` seconds (default `1`). After a warm-up of `DLSPS2_WARMUP_S` seconds (default `5`, at
most half the run), counted from the moment every stream has reported its first frame, it sums each stream's
frames and seconds over the new windows. A stream's FPS is its frames over its seconds, and the slowest stream
judges the run. While the run lasts, the runner pushes the mean FPS per stream to metrics-manager as the live
**FPS** metric, tagged with the `job_id`.

## Latency

Latency measurement uses DL Streamer's `latency_tracer`. It tracks how long each buffer takes to traverse the
pipeline, from the source element to the sink element.

### How latency_tracer is activated

GStreamer tracers are set per process, so the tracer runs in the server for every pipeline the server runs,
including tests that do not ask for latency metrics. It is on by default and set with environment variables of
the `vippet` and `dlstreamer-pipeline-server` services in `compose.yml`:

| Environment variable      | Value                                                            | Purpose                                                                |
| ------------------------- | ---------------------------------------------------------------- | ---------------------------------------------------------------------- |
| `DLSPS2_GST_TRACERS`      | `latency_tracer(flags=pipeline,interval=1000,post-metrics=true)` | Passed to the server as `GST_TRACERS` (default); empty turns it off    |
| `DLSPS2_OTEL`             | `true` (default)                                                 | Server exports its metrics over OpenTelemetry to metrics-manager       |
| `DLSPS2_OTEL_INTERVAL_MS` | `1000` (default)                                                 | Export interval of the server, in milliseconds                         |

- **`flags=pipeline`** — measures the total source-to-sink latency (as opposed to per-element latency).
- **`interval=1000`** — the tracer reports statistics accumulated during each 1 000 ms window.
- **`post-metrics=true`** — the tracer posts every window as a `dlstreamer/latency-window` element message on the
  pipeline bus. The last, partial window is posted at end-of-stream.

A test with latency metrics enabled runs without them when `DLSPS2_OTEL` is not `true` or `DLSPS2_GST_TRACERS`
does not run `latency_tracer` with `post-metrics=true`: a warning is logged and the job details say so. A tracer
that predates
`post-metrics` posts no messages, so no samples arrive, and the runner logs a warning after the run.

### Latency samples

The server merges the windows of each source-sink branch over one export period and exports them, tagged with the
instance's `pipeline_id`, `source` and `sink`, as the `pipeline_latency_avg`, `_min`, `_max`, `_window` and
`_frames` gauges. `Dlsps2PipelineRunner` reads these series from metrics-manager every `DLSPS2_METRICS_POLL_S`
seconds (default `1`), only for its own instances, and derives one sample per export period:

| Sample field  | Value                                               | Meaning                                                                              |
| ------------- | --------------------------------------------------- | ------------------------------------------------------------------------------------ |
| `interval_ms` | `pipeline_latency_window`                           | Total length of the windows in the export period                                     |
| `avg_ms`      | `pipeline_latency_avg`                              | Mean source-to-sink latency of a frame                                               |
| `min_ms`      | `pipeline_latency_min`                              | Minimum source-to-sink latency of a frame                                            |
| `max_ms`      | `pipeline_latency_max`                              | Maximum source-to-sink latency of a frame                                            |
| `latency_ms`  | `pipeline_latency_window / pipeline_latency_frames` | **Deprecated.** Frame period (`1000 / fps`), a throughput measure, **not** a latency |

A frame's source-to-sink latency runs from the moment the source element outputs the frame to the moment the frame
is pushed into the sink, so the sink's own work is excluded. `latency_ms` is the mean time between output frames in
the period: it falls as throughput rises and says nothing about how long a frame spends in the pipeline. It is
deprecated and kept only for API compatibility; use `avg_ms` for the mean latency and `max_ms` for the worst case.

After the instances stop, the runner keeps reading until their final export arrives, for at most
`DLSPS2_OTEL_INTERVAL_MS` plus two seconds.

### Data flow

```text
DL Streamer Pipeline Server 2.0 (one instance per stream)
   │  bus: dlstreamer/latency-window, dlstreamer/genai-request
   ▼
OpenTelemetry export (OTLP/JSON, every DLSPS2_OTEL_INTERVAL_MS)
   │
   ▼
metrics-manager  (series tagged with the server's pipeline_id)
   │
   ▼
Dlsps2PipelineRunner (reads its own instances every DLSPS2_METRICS_POLL_S)
   │
   ▼
pipeline_latency / vlm_metrics samples  ──▶  HTTP POST to metrics-manager:9090/api/v1/metrics
   │
   ▼
metrics-manager  ──▶  SSE stream at /metrics/stream
   │
   ▼
Browser (EventSource) → Redux store → Latency chart components
```

1. **DL Streamer Pipeline Server 2.0** — runs each stream as its own instance. With the setup above, it exports
   the latency windows and `gvagenai` requests of every instance to metrics-manager, tagged with the instance's
   `pipeline_id`.
1. **Dlsps2PipelineRunner** — reads only the series of its own instances, and republishes each export period as
   ViPPET's own `pipeline_latency` and `vlm_metrics` samples with the job's tags.
1. **metrics-manager** — receives an HTTP POST with a `pipeline_latency` measurement (fields: `avg_ms`,
   `min_ms`, `max_ms`, `latency_ms`; tags: `stream_id`, `job_id`). It stores the sample and pushes it
   to connected SSE clients.
1. **UI (browser)** — an `EventSource` connection to `/metrics/stream` dispatches incoming messages to
   the Redux store. The latency chart components render avg / min / max over time.

## VLM generation metrics

Pipelines with a `gvagenai` element that runs with `metrics=true` report the performance of generation requests.
`Dlsps2PipelineRunner` asks the server for its `gvagenai` properties (`GET /elements/gvagenai`) and adds
`post-metrics=true` to such an element only when the server's `gvagenai` has the property, because an unknown
property fails parsing. The element then posts a `dlstreamer/genai-request` message per request, and the server
exports the `genai_ttft`, `genai_tpot` and `genai_generate_duration` histograms. The runner republishes them as a
`vlm_metrics` sample with `ttft_ms`, `tpot_ms` and `generate_duration_ms`, tagged with the element name as
`stream_id`. Each value is the mean over the requests of one export period.

Without the `post-metrics` property, a performance test falls back to the `metrics` block of the JSON answer each
`gvagenai` writes, read through the event files of `vippet/pipeline_events.py`, with one warning per run. That
block holds the means over every request since the element started, not per-period values. They are pushed as
`ttft_mean`, `tpot_mean` and `generate_duration_mean`.
