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

## Status

Under active development and testing against real sample applications (see
`edge-ai-suites/` in this directory). Expect breaking changes.
