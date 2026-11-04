# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

# DL Streamer Pipeline Server 2.0 (DLSPS 2.0)

> ⚠️ **Work in progress — Alpha.** This is an early, actively-developed rewrite of
> DL Streamer Pipeline Server. APIs, configuration formats, and behavior may change
> without notice. Not recommended for production use. For the stable, supported
> release, use [DL Streamer Pipeline Server 1.0](../README.md).

## What is this?

DLSPS 2.0 is a from-scratch reimplementation of the pipeline server, built on
FastAPI with a single shared worker for hosting GStreamer
pipelines, instead of one OS thread per pipeline in the
original design. It also ships a **legacy compatibility layer** so existing
`config.json`-based pipeline definitions and the `POST /pipelines/{name}/{version}`
REST route from 1.0 continue to work.

## Summary of changes vs. DLSPS 1.0

- **New REST surface**: adds `POST /pipelines` (submit a raw gst-launch pipeline
  string directly), alongside the legacy
  `POST /pipelines/{name}/{version}` route kept for backward compatibility.
- **Single shared GLib main loop**: all hosted pipelines share one background
  thread/`MainLoop` instead of a dedicated thread per pipeline, reducing
  per-stream thread/GIL overhead. Pipeline teardown is always done on a
  short-lived helper thread so a slow/blocking stop doesn't stall other
  running pipelines.
- **Known gaps (not yet ported from 1.0)**:
  - No per-frame pipeline latency tracking (`avg_pipeline_latency`/`frame_latency`).
  - Isolated pre-flight validation still spawns a separate subprocess per
    pipeline `start()`, which can transiently double resource usage during
    ramp-up of many concurrent streams — a known performance-parity gap vs 1.0.

## REST API

See the [DLSPS 2.0 REST API Reference](docs/api-reference.md).

## OpenTelemetry metrics

Set `ENABLE_OPEN_TELEMETRY=true` to push per-pipeline metrics to an OTLP/HTTP
collector at `http://${OTEL_COLLECTOR_HOST}:${OTEL_COLLECTOR_PORT}/v1/metrics`
every `OTEL_EXPORT_INTERVAL_MILLIS` (default `10000`). Each metric carries a
single attribute, `pipeline_id`.

| Metric | Unit | Description |
|--------|------|-------------|
| `fps_per_pipeline` | - | `avg_fps` of the instance. Not reported until warmup completes. |
| `frame_fps_per_pipeline` | - | `frame_fps` of the instance. |
| `frame_fps_window_seconds` | s | `frame_interval`: the window `frame_fps_per_pipeline` was measured over. |
| `pipeline_start_timestamp_seconds` | s | Unix time at which the instance started running (`start_time`). |
| `pipeline_first_frame_timestamp_seconds` | s | Unix time of the first frame (`first_frame_time`). Not reported until a frame arrives. |
| `pipeline_end_timestamp_seconds` | s | Unix time at which the instance stopped. Reported only after it stops, during the retention window below. |

Durations are derived in the backend, for example the time to first frame is
`pipeline_first_frame_timestamp_seconds - pipeline_start_timestamp_seconds`.

Running instances are reported live. A finished instance is reported for
`max(2 × export interval, 30 s)` after it stops, so the final values of short
runs still reach the backend. CPU and memory metrics from DLSPS 1.0 are not
ported, because pipelines run in worker subprocesses.

When an instance finishes (EOS, stop or error), DLSPS exports immediately
instead of waiting for the next interval. The flush runs after every event the
worker reported for that instance, including the last latency window posted at
EOS, so a short run's final values arrive promptly. It runs on a background
thread: `DELETE /pipelines/{instance_id}` still returns once the stop is
requested, as before, without waiting for the pipeline to stop or for the
export. Flush failures are logged and the periodic export carries on.

### DL Streamer latency and GenAI metrics

DL Streamer can post its own measurements on the pipeline bus as
`dlstreamer/*` element messages. The worker forwards them and they are exported
alongside the metrics above. DLSPS does not recompute them: nothing parses log
output, and nothing extra runs per frame in Python. Both producers are opt-in:

- **Pipeline latency** comes from `latency_tracer`. Tracers are process-wide, so
  enable it for the whole server, for example
  `GST_TRACERS=latency_tracer(flags=pipeline,interval=1000,post-metrics=true)`.
  Every pipeline is then measured.
- **GenAI request metrics** come from `gvagenai` with `post-metrics=true` in the
  pipeline (openvino-genai backend). `metrics=true` only attaches JSON metadata
  to frames and posts nothing.

| Metric | Type | Unit | Attributes | Description |
|--------|------|------|------------|-------------|
| `pipeline_latency_avg` | gauge | ms | `pipeline_id`, `source`, `sink` | Mean frame latency over the export period |
| `pipeline_latency_min`, `pipeline_latency_max` | gauge | ms | same | Extremes over the export period |
| `pipeline_latency_frames` | gauge | - | same | Frames behind the latency values of the period |
| `pipeline_latency_window` | gauge | ms | same | Tracer window time behind those frames. A throughput helper: `window / frames` is the mean output frame period (`1000 / fps`), not a latency. |
| `pipeline_latency_stddev` | gauge | ms | same | Population standard deviation of frame latency over the export period |
| `pipeline_latency_p50`, `pipeline_latency_p95`, `pipeline_latency_p99` | gauge | ms | same | Frame latency percentiles over the export period, estimated from the tracer's latency buckets |
| `genai_ttft`, `genai_tpot` | histogram | ms | `pipeline_id`, `element` | Time to first token and mean time per output token, one sample per generation request |
| `genai_generate_duration`, `genai_inference_duration`, `genai_prepare_embeddings_duration` | histogram | ms | same | Per-request durations |
| `genai_input_tokens`, `genai_generated_tokens` | histogram | - | same | Per-request token counts, in power-of-two buckets up to 65536 |

Latency is the `latency_tracer` frame latency: from the source pad of the source
element to the push into the sink. The tracer windows of one export period are
merged exactly per instance and branch: frame counts, latency sums, sums of
squares, bucket counts and window times add up, minimum and maximum compare, and
the average is the summed latency divided by the summed frame count. DLSPS
aggregates the tracer's histogram; it does not measure latency itself. Average,
minimum, maximum and standard deviation are exact. Percentiles are estimates
within the bucket resolution, about 25 % of the latency with the tracer's
default buckets: linear interpolation inside the bucket holding the rank, as in
Prometheus `histogram_quantile`, with the first bucket starting at the minimum,
the overflow bucket ending at the maximum, and the result clamped to both.

Latency gauges are reported only for export periods in which windows arrived.
Standard deviation and percentiles need a tracer that also posts `sum_sq_ms`,
`bucket_bounds_ms` and `bucket_counts`. They are left out of an export period in
which any window lacks them, has malformed values or uses other bucket bounds,
with one warning per reason; the other latency gauges are still reported. The
window still open at EOS is posted too, but a stopped or failed instance gets no
EOS, so its last partial window is lost.
Histograms use delta temporality, so each export holds only the requests
completed since the previous one.

Each message kind carries its own schema version. A message of an unknown kind
or an unsupported version is skipped, with one warning per kind and version.

## Status

Under active development and testing against real sample applications (see
`edge-ai-suites/` in this directory). Expect breaking changes.
