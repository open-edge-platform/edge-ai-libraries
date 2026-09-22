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

## Status

Under active development and testing against real sample applications (see
`edge-ai-suites/` in this directory). Expect breaking changes.
